"""Prometheus provider: range queries plus error-spike detection.

Enable with:
    RCA_PROMETHEUS_URL=http://localhost:9090

The default queries cover the signals that matter for first-response RCA -
error rate, latency, restarts, saturation. Override them per deployment with
RCA_PROM_QUERIES (a JSON object of {label: promql}).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .base import (KIND_METRIC_SPIKE, KIND_SERVICE_RESTART, Provider, Signal,
                   TimeWindow, signal_id)

# label -> PromQL. {svc} is replaced with a service filter when a hint is given.
DEFAULT_QUERIES = {
    "error_rate": 'sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)',
    "latency_p99": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))',
    "restarts": 'increase(kube_pod_container_status_restarts_total[15m])',
    "cpu_saturation": 'sum(rate(container_cpu_usage_seconds_total[5m])) by (service)',
    "memory_bytes": 'sum(container_memory_working_set_bytes) by (service)',
}

# A series is "spiking" when its peak in the window is this many times its own
# median. Median rather than mean so one big spike does not hide itself.
SPIKE_RATIO = float(os.getenv("RCA_PROM_SPIKE_RATIO", "3.0"))
MIN_SAMPLES = 4


def _queries() -> dict:
    raw = os.getenv("RCA_PROM_QUERIES")
    if not raw:
        return dict(DEFAULT_QUERIES)
    try:
        q = json.loads(raw)
        return q if isinstance(q, dict) else dict(DEFAULT_QUERIES)
    except json.JSONDecodeError:
        return dict(DEFAULT_QUERIES)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def detect_spike(points: list[tuple[float, float]], ratio: float = SPIKE_RATIO):
    """Find the largest deviation above the series median.

    Returns (peak_timestamp, peak_value, baseline, multiple) or None. Pure
    function so it is unit-testable without a Prometheus server.
    """
    values = [v for _, v in points if v == v]  # drop NaN
    if len(values) < MIN_SAMPLES:
        return None
    baseline = _median(values)
    peak_ts, peak = max(points, key=lambda p: p[1])
    if peak <= 0:
        return None
    # A flat-zero baseline means anything non-zero is a spike; guard the ratio.
    multiple = peak / baseline if baseline > 0 else float("inf")
    if multiple < ratio:
        return None
    return peak_ts, peak, baseline, multiple


class PrometheusProvider(Provider):
    name = "prometheus"
    env_url = "RCA_PROMETHEUS_URL"

    def query_range(self, promql: str, window: TimeWindow, step: str = "60s"):
        data = self._get_json("/api/v1/query_range", {
            "query": promql,
            "start": window.start.timestamp(),
            "end": window.end.timestamp(),
            "step": step,
        })
        if not data or data.get("status") != "success":
            return []
        return data.get("data", {}).get("result", [])

    def collect(self, window: TimeWindow, hints: dict | None = None) -> list[Signal]:
        if not self.configured():
            return []
        hints = hints or {}
        service = hints.get("service")
        signals: list[Signal] = []
        n = 0
        for label, promql in _queries().items():
            if service and "{svc}" in promql:
                promql = promql.replace("{svc}", f'service="{service}"')
            for series in self.query_range(promql, window):
                points = []
                for ts, raw in series.get("values", []):
                    try:
                        points.append((float(ts), float(raw)))
                    except (TypeError, ValueError):
                        continue
                found = detect_spike(points)
                if not found:
                    continue
                peak_ts, peak, baseline, multiple = found
                metric = series.get("metric", {})
                svc = metric.get("service") or metric.get("pod") or metric.get("job")
                n += 1
                kind = KIND_SERVICE_RESTART if label == "restarts" else KIND_METRIC_SPIKE
                mult = "∞" if multiple == float("inf") else f"{multiple:.1f}x"
                signals.append(Signal(
                    id=signal_id(self.name, kind, n),
                    source=self.name,
                    kind=kind,
                    at=datetime.fromtimestamp(peak_ts, tz=timezone.utc),
                    summary=f"{label} on {svc or 'unknown service'} peaked at "
                            f"{peak:.4g} ({mult} its median {baseline:.4g})",
                    severity="critical" if multiple >= 2 * SPIKE_RATIO else "warn",
                    service=svc,
                    detail={"metric": label, "promql": promql, "peak": peak,
                            "baseline": baseline, "multiple": None if multiple == float("inf") else round(multiple, 2),
                            "labels": metric},
                ))
        return signals
