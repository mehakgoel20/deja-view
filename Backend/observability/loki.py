"""Loki provider: pull error logs for the incident window and cluster them.

Enable with:
    RCA_LOKI_URL=http://localhost:3100

Raw log lines are useless to an LLM in bulk - a thousand near-identical
stack traces say one thing. So lines are normalised (numbers, UUIDs, hex and
quoted values replaced with placeholders) and grouped into templates; each
template becomes one signal carrying its count and first occurrence.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime, timezone

from .base import KIND_LOG_BURST, Provider, Signal, TimeWindow, signal_id

DEFAULT_SELECTOR = os.getenv(
    "RCA_LOKI_SELECTOR",
    '{level=~"error|critical|fatal"}')
MAX_LINES = int(os.getenv("RCA_LOKI_LIMIT", "1000"))
TOP_TEMPLATES = int(os.getenv("RCA_LOKI_TOP", "8"))

# Numbers with an optional unit suffix, so "1500ms" and "2.5s" collapse too.
_NUM = re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m|h|d|kb|mb|gb|tb|b|%)?\b", re.I)
_HEX = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_QUOTED = re.compile(r"'[^']{0,80}'|\"[^\"]{0,80}\"")
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
_PATHISH = re.compile(r"/[\w./-]{4,}")


def normalise_line(line: str) -> str:
    """Collapse a log line to its template so repeats group together."""
    s = _UUID.sub("<uuid>", line)
    s = _IP.sub("<ip>", s)
    s = _HEX.sub("<hex>", s)
    s = _QUOTED.sub("<str>", s)
    s = _PATHISH.sub("<path>", s)
    s = _NUM.sub("<n>", s)
    return re.sub(r"\s+", " ", s).strip()[:300]


def cluster_lines(entries: list[tuple[datetime, str, dict]], top: int = TOP_TEMPLATES):
    """Group (timestamp, line, labels) into templates, most frequent first."""
    groups: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "first": None, "last": None, "sample": "", "labels": {}})
    for at, line, labels in entries:
        key = normalise_line(line)
        if not key:
            continue
        g = groups[key]
        g["count"] += 1
        if g["first"] is None or at < g["first"]:
            g["first"] = at
        if g["last"] is None or at > g["last"]:
            g["last"] = at
        if not g["sample"]:
            g["sample"] = line[:400]
            g["labels"] = labels
    ordered = sorted(groups.items(), key=lambda kv: -kv[1]["count"])
    return [(template, g) for template, g in ordered[:top]]


class LokiProvider(Provider):
    name = "loki"
    env_url = "RCA_LOKI_URL"

    def query_range(self, selector: str, window: TimeWindow, limit: int = MAX_LINES):
        data = self._get_json("/loki/api/v1/query_range", {
            "query": selector,
            "start": int(window.start.timestamp() * 1e9),
            "end": int(window.end.timestamp() * 1e9),
            "limit": limit,
            "direction": "forward",
        })
        if not data or data.get("status") != "success":
            return []
        return data.get("data", {}).get("result", [])

    def collect(self, window: TimeWindow, hints: dict | None = None) -> list[Signal]:
        if not self.configured():
            return []
        hints = hints or {}
        selector = hints.get("loki_selector") or DEFAULT_SELECTOR
        service = hints.get("service")
        if service and "service=" not in selector:
            selector = selector.rstrip("}") + f',service="{service}"}}'

        entries: list[tuple[datetime, str, dict]] = []
        for stream in self.query_range(selector, window):
            labels = stream.get("stream", {})
            for ns, line in stream.get("values", []):
                try:
                    at = datetime.fromtimestamp(int(ns) / 1e9, tz=timezone.utc)
                except (TypeError, ValueError):
                    continue
                entries.append((at, line, labels))

        signals = []
        for n, (template, g) in enumerate(cluster_lines(entries), start=1):
            signals.append(Signal(
                id=signal_id(self.name, KIND_LOG_BURST, n),
                source=self.name,
                kind=KIND_LOG_BURST,
                at=g["first"],
                summary=f"{g['count']}x error log: {template[:160]}",
                severity="critical" if g["count"] >= 100 else "warn",
                service=g["labels"].get("service") or service,
                detail={"template": template, "count": g["count"],
                        "first_seen": g["first"].isoformat() if g["first"] else None,
                        "last_seen": g["last"].isoformat() if g["last"] else None,
                        "sample": g["sample"], "labels": g["labels"],
                        "selector": selector},
            ))
        return signals
