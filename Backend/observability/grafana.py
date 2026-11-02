"""Grafana provider: annotations, which are where deploys usually live.

Enable with:
    RCA_GRAFANA_URL=http://localhost:3000
    RCA_GRAFANA_TOKEN=glsa_...

Grafana annotations are the cheapest reliable source of "what changed at
13:42" - most teams already push deploy markers into them. Annotations whose
text or tags mention a release are emitted as deploy signals, which the
timeline treats as candidate triggers rather than symptoms.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from .base import (KIND_ANNOTATION, KIND_DEPLOY, Provider, Signal, TimeWindow,
                   signal_id)

DEPLOY_HINT = re.compile(
    r"deploy|release|rollout|ship|rollback|revert|migrat|upgrade|canary|"
    r"helm|argocd|terraform", re.I)
MAX_ANNOTATIONS = int(os.getenv("RCA_GRAFANA_LIMIT", "100"))


class GrafanaProvider(Provider):
    name = "grafana"
    env_url = "RCA_GRAFANA_URL"

    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 10.0):
        super().__init__(url, timeout)
        self.token = token or os.getenv("RCA_GRAFANA_TOKEN", "")

    def configured(self) -> bool:
        # Annotations need a token; a URL alone cannot read them.
        return bool(self.url and self.token)

    def status(self):
        s = super().status()
        if self.url and not self.token:
            s.configured = False
            s.detail = "set RCA_GRAFANA_TOKEN as well"
        return s

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def annotations(self, window: TimeWindow, tags: list[str] | None = None):
        params = {
            "from": int(window.start.timestamp() * 1000),
            "to": int(window.end.timestamp() * 1000),
            "limit": MAX_ANNOTATIONS,
        }
        if tags:
            params["tags"] = tags
        data = self._get_json("/api/annotations", params, self._headers())
        return data if isinstance(data, list) else []

    def collect(self, window: TimeWindow, hints: dict | None = None) -> list[Signal]:
        if not self.configured():
            return []
        hints = hints or {}
        signals = []
        for n, a in enumerate(self.annotations(window, hints.get("grafana_tags")), start=1):
            text = (a.get("text") or "").strip()
            tags = a.get("tags") or []
            blob = f"{text} {' '.join(tags)}"
            is_deploy = bool(DEPLOY_HINT.search(blob))
            try:
                at = datetime.fromtimestamp(int(a.get("time", 0)) / 1000, tz=timezone.utc)
            except (TypeError, ValueError):
                continue
            kind = KIND_DEPLOY if is_deploy else KIND_ANNOTATION
            signals.append(Signal(
                id=signal_id(self.name, kind, n),
                source=self.name,
                kind=kind,
                at=at,
                summary=(f"deploy/change marker: {text[:160]}" if is_deploy
                         else f"annotation: {text[:160]}"),
                severity="warn" if is_deploy else "info",
                service=(a.get("dashboardUID") or None),
                detail={"tags": tags, "text": text, "id": a.get("id"),
                        "dashboard_uid": a.get("dashboardUID"),
                        "panel_id": a.get("panelId")},
            ))
        return signals
