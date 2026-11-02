"""OpenTelemetry provider: failing traces via a Tempo/Jaeger-compatible API.

Enable with one of:
    RCA_TEMPO_URL=http://localhost:3200     # Tempo (TraceQL)
    RCA_JAEGER_URL=http://localhost:16686   # Jaeger query API

Traces are the one source that shows *direction* - which service called which
when it failed. That edge information is handed to the dependency graph and
the causal engine, where "A failed because its call to B failed" is a far
stronger claim than two services erroring at the same time.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .base import KIND_TRACE_ERROR, Provider, Signal, TimeWindow, signal_id

MAX_TRACES = int(os.getenv("RCA_TRACE_LIMIT", "40"))


class OTelProvider(Provider):
    """Reads failing spans from Tempo or Jaeger, whichever is configured."""

    name = "otel"
    env_url = "RCA_TEMPO_URL"

    def __init__(self, url: str | None = None, timeout: float = 10.0):
        self.flavour = "tempo"
        resolved = url or os.getenv("RCA_TEMPO_URL", "")
        if not resolved:
            resolved = os.getenv("RCA_JAEGER_URL", "")
            if resolved:
                self.flavour = "jaeger"
        super().__init__(resolved, timeout)

    def status(self):
        s = super().status()
        if not self.configured():
            s.detail = "set RCA_TEMPO_URL or RCA_JAEGER_URL to enable"
        else:
            s.detail = f"{self.flavour}: {s.detail}"
        return s

    # ---- Tempo ----------------------------------------------------------
    def _tempo_errors(self, window: TimeWindow, service: str | None):
        q = '{status=error}' if not service else f'{{status=error && resource.service.name="{service}"}}'
        data = self._get_json("/api/search", {
            "q": q,
            "start": int(window.start.timestamp()),
            "end": int(window.end.timestamp()),
            "limit": MAX_TRACES,
        })
        out = []
        for t in (data or {}).get("traces", []) or []:
            try:
                at = datetime.fromtimestamp(int(t.get("startTimeUnixNano", 0)) / 1e9,
                                            tz=timezone.utc)
            except (TypeError, ValueError):
                continue
            out.append({
                "trace_id": t.get("traceID"),
                "service": t.get("rootServiceName"),
                "operation": t.get("rootTraceName"),
                "at": at,
                "duration_ms": t.get("durationMs"),
            })
        return out

    # ---- Jaeger ---------------------------------------------------------
    def _jaeger_errors(self, window: TimeWindow, service: str | None):
        if not service:
            # Jaeger requires a service; ask it which ones exist and take the first.
            svcs = (self._get_json("/api/services") or {}).get("data") or []
            if not svcs:
                return []
            service = svcs[0]
        data = self._get_json("/api/traces", {
            "service": service,
            "start": int(window.start.timestamp() * 1e6),
            "end": int(window.end.timestamp() * 1e6),
            "tags": '{"error":"true"}',
            "limit": MAX_TRACES,
        })
        out = []
        for t in (data or {}).get("data", []) or []:
            spans = t.get("spans") or []
            if not spans:
                continue
            root = min(spans, key=lambda s: s.get("startTime", 0))
            try:
                at = datetime.fromtimestamp(int(root.get("startTime", 0)) / 1e6,
                                            tz=timezone.utc)
            except (TypeError, ValueError):
                continue
            procs = t.get("processes") or {}
            svc = (procs.get(root.get("processID"), {}) or {}).get("serviceName", service)
            out.append({
                "trace_id": t.get("traceID"),
                "service": svc,
                "operation": root.get("operationName"),
                "at": at,
                "duration_ms": round(root.get("duration", 0) / 1000, 1),
                "span_count": len(spans),
            })
        return out

    def collect(self, window: TimeWindow, hints: dict | None = None) -> list[Signal]:
        if not self.configured():
            return []
        service = (hints or {}).get("service")
        traces = (self._tempo_errors(window, service) if self.flavour == "tempo"
                  else self._jaeger_errors(window, service))
        # One signal per (service, operation): 40 traces of the same broken
        # endpoint is one fact, not forty.
        grouped: dict[tuple, dict] = {}
        for t in traces:
            key = (t.get("service"), t.get("operation"))
            g = grouped.setdefault(key, {"count": 0, "at": t["at"], "trace_ids": [],
                                         "duration_ms": t.get("duration_ms")})
            g["count"] += 1
            g["at"] = min(g["at"], t["at"])
            if len(g["trace_ids"]) < 5:
                g["trace_ids"].append(t.get("trace_id"))

        signals = []
        for n, ((svc, op), g) in enumerate(
                sorted(grouped.items(), key=lambda kv: -kv[1]["count"]), start=1):
            signals.append(Signal(
                id=signal_id(self.name, KIND_TRACE_ERROR, n),
                source=self.name,
                kind=KIND_TRACE_ERROR,
                at=g["at"],
                summary=f"{g['count']} failing traces on {svc or 'unknown'}"
                        f"{f' ({op})' if op else ''}",
                severity="critical" if g["count"] >= 10 else "warn",
                service=svc,
                detail={"operation": op, "count": g["count"],
                        "trace_ids": g["trace_ids"],
                        "duration_ms": g["duration_ms"], "backend": self.flavour},
            ))
        return signals
