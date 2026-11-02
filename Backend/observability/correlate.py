"""Collect from every configured provider and correlate the result.

Two jobs:

1. `collect_signals` fans out across providers in parallel and returns one
   flat, time-sorted list of signals plus a status row per provider, so an
   operator can tell "nothing found" apart from "nothing configured".
2. `correlate` scores how tightly the signals cluster in time and whether a
   change (deploy) precedes the symptoms. That ordering is what turns a pile
   of simultaneous alerts into an argument about cause.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from .base import (KIND_DEPLOY, KIND_LOG_BURST, KIND_METRIC_SPIKE,
                   KIND_SERVICE_RESTART, KIND_TRACE_ERROR, Provider, Signal,
                   TimeWindow)
from .grafana import GrafanaProvider
from .loki import LokiProvider
from .otel import OTelProvider
from .prometheus import PrometheusProvider

# A deploy this long before the first symptom is still a plausible trigger.
TRIGGER_LOOKBACK = timedelta(minutes=30)
SYMPTOM_KINDS = (KIND_METRIC_SPIKE, KIND_LOG_BURST, KIND_TRACE_ERROR,
                 KIND_SERVICE_RESTART)


def default_providers() -> list[Provider]:
    return [PrometheusProvider(), LokiProvider(), GrafanaProvider(), OTelProvider()]


def collect_signals(window: TimeWindow, hints: dict | None = None,
                    providers: list[Provider] | None = None):
    """Gather signals from all providers. Never raises; always returns both lists."""
    providers = providers if providers is not None else default_providers()
    signals: list[Signal] = []

    def run(p: Provider):
        try:
            return p.collect(window, hints)
        except Exception:
            # A provider must not break an investigation. status() carries why.
            return []

    active = [p for p in providers if p.configured()]
    if active:
        with ThreadPoolExecutor(max_workers=max(1, len(active))) as ex:
            for got in ex.map(run, active):
                signals.extend(got)

    signals.sort(key=lambda s: s.at)
    return signals, [p.status().to_dict() for p in providers]


def correlate(signals: list[Signal], window: TimeWindow) -> dict:
    """Describe how the signals relate in time.

    Returns the first symptom, any change that preceded it, which services are
    implicated, and a 0-1 `confidence` that the signals describe one event
    rather than unrelated noise.
    """
    if not signals:
        return {"signal_count": 0, "confidence": 0.0,
                "summary": "No observability signals available for this window.",
                "first_symptom": None, "likely_trigger": None,
                "services": [], "by_kind": {}, "window": window.to_dict()}

    by_kind: dict[str, int] = {}
    for s in signals:
        by_kind[s.kind] = by_kind.get(s.kind, 0) + 1

    symptoms = [s for s in signals if s.kind in SYMPTOM_KINDS]
    deploys = [s for s in signals if s.kind == KIND_DEPLOY]
    first_symptom = min(symptoms, key=lambda s: s.at) if symptoms else None

    trigger = None
    if first_symptom and deploys:
        # the latest change that still precedes the first symptom
        prior = [d for d in deploys
                 if d.at <= first_symptom.at
                 and first_symptom.at - d.at <= TRIGGER_LOOKBACK]
        if prior:
            trigger = max(prior, key=lambda d: d.at)

    services = sorted({s.service for s in signals if s.service})

    # Confidence: signals agreeing in time and across sources is evidence of
    # one event. A preceding change is the strongest single clue.
    confidence = 0.0
    if symptoms:
        confidence += 0.3
    if len({s.source for s in signals}) >= 2:
        confidence += 0.2
    if trigger is not None:
        confidence += 0.3
    if symptoms:
        spread = (max(s.at for s in symptoms) - min(s.at for s in symptoms)).total_seconds()
        if spread <= 600:            # all symptoms inside 10 minutes
            confidence += 0.2
        elif spread <= 1800:
            confidence += 0.1
    confidence = round(min(confidence, 1.0), 2)

    bits = [f"{len(signals)} signals from {len({s.source for s in signals})} source(s)"]
    if first_symptom:
        bits.append(f"first symptom at {first_symptom.at.isoformat()}: {first_symptom.summary}")
    if trigger:
        gap = int((first_symptom.at - trigger.at).total_seconds() // 60)
        bits.append(f"preceded {gap} min earlier by {trigger.summary}")
    if services:
        bits.append("services implicated: " + ", ".join(services[:6]))

    return {
        "signal_count": len(signals),
        "confidence": confidence,
        "summary": ". ".join(bits) + ".",
        "first_symptom": first_symptom.to_dict() if first_symptom else None,
        "likely_trigger": trigger.to_dict() if trigger else None,
        "services": services,
        "by_kind": by_kind,
        "window": window.to_dict(),
    }


def evidence_block(signals: list[Signal], limit: int = 20) -> str:
    """Render signals as text an LLM can cite, mirroring the incident block style."""
    if not signals:
        return "LIVE OBSERVABILITY: none available."
    lines = []
    for s in signals[:limit]:
        svc = f" | {s.service}" if s.service else ""
        lines.append(f"[{s.id}] {s.at.isoformat()} | {s.kind} | {s.severity}{svc}\n"
                     f"  {s.summary}")
    more = f"\n  (+{len(signals) - limit} more)" if len(signals) > limit else ""
    return "LIVE OBSERVABILITY:\n" + "\n".join(lines) + more
