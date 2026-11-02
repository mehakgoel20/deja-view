"""Live observability integration (feature 1).

Pulls real operational evidence - metrics, logs, deploy markers and failing
traces - for the window around an incident, so the RCA rests on what the
system actually did rather than only on the reporter's description.

Every backend is optional. With nothing configured the package returns no
signals and the pipeline behaves exactly as it did before.

    from observability import TimeWindow, collect_signals, correlate

    window = TimeWindow.last(minutes=90)
    signals, status = collect_signals(window, {"service": "checkout"})
    print(correlate(signals, window)["summary"])

Environment:
    RCA_PROMETHEUS_URL   e.g. http://localhost:9090
    RCA_LOKI_URL         e.g. http://localhost:3100
    RCA_GRAFANA_URL      + RCA_GRAFANA_TOKEN
    RCA_TEMPO_URL        or RCA_JAEGER_URL
"""
from .base import (KIND_ANNOTATION, KIND_DEPLOY, KIND_LOG_BURST,
                   KIND_METRIC_SPIKE, KIND_RECOVERY, KIND_SERVICE_RESTART,
                   KIND_TRACE_ERROR, Provider, ProviderStatus, Signal,
                   TimeWindow, utcnow)
from .correlate import (collect_signals, correlate, default_providers,
                        evidence_block)
from .grafana import GrafanaProvider
from .loki import LokiProvider, cluster_lines, normalise_line
from .otel import OTelProvider
from .prometheus import PrometheusProvider, detect_spike

__all__ = [
    "TimeWindow", "Signal", "Provider", "ProviderStatus", "utcnow",
    "KIND_METRIC_SPIKE", "KIND_LOG_BURST", "KIND_DEPLOY", "KIND_TRACE_ERROR",
    "KIND_ANNOTATION", "KIND_SERVICE_RESTART", "KIND_RECOVERY",
    "PrometheusProvider", "LokiProvider", "GrafanaProvider", "OTelProvider",
    "collect_signals", "correlate", "default_providers", "evidence_block",
    "detect_spike", "normalise_line", "cluster_lines",
]
