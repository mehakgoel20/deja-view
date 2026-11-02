"""Shared types for live observability providers.

Every provider turns whatever its backend returns into a list of `Signal`
objects, so the agents, timeline and causal engine downstream never need to
know whether a fact came from Prometheus, Loki, Grafana or OpenTelemetry.

Providers are optional by design. A provider with no URL configured reports
`configured() == False` and returns no signals, so the whole pipeline runs
offline and degrades to the text-only RCA it did before.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone

# signal kinds, used by the timeline and causal engine to order and weight facts
KIND_METRIC_SPIKE = "metric_spike"
KIND_LOG_BURST = "log_burst"
KIND_DEPLOY = "deploy"
KIND_TRACE_ERROR = "trace_error"
KIND_ANNOTATION = "annotation"
KIND_SERVICE_RESTART = "service_restart"
KIND_RECOVERY = "recovery"

SEVERITIES = ("info", "warn", "critical")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TimeWindow:
    """The period an investigation looks at. Always timezone-aware UTC."""

    start: datetime
    end: datetime

    @classmethod
    def around(cls, at: datetime, before_minutes: int = 60, after_minutes: int = 15) -> "TimeWindow":
        return cls(at - timedelta(minutes=before_minutes), at + timedelta(minutes=after_minutes))

    @classmethod
    def last(cls, minutes: int = 60) -> "TimeWindow":
        end = utcnow()
        return cls(end - timedelta(minutes=minutes), end)

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def contains(self, at: datetime) -> bool:
        return self.start <= at <= self.end

    def to_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


@dataclass
class Signal:
    """One observation from a monitoring backend.

    `id` is stable within a run so hypotheses and timeline entries can cite it
    the same way the text pipeline cites incident ids.
    """

    id: str
    source: str
    kind: str
    at: datetime
    summary: str
    severity: str = "info"
    service: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["at"] = self.at.isoformat()
        return d


@dataclass
class ProviderStatus:
    name: str
    configured: bool
    reachable: bool | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Provider:
    """Base class for an observability backend.

    Subclasses set `name`, read their own environment variables in `__init__`
    and implement `collect`. They must never raise: a backend that is down
    returns an empty list and explains itself through `status()`.
    """

    name = "provider"
    env_url = ""

    def __init__(self, url: str | None = None, timeout: float = 10.0):
        self.url = (url or os.getenv(self.env_url, "")).rstrip("/")
        self.timeout = timeout
        self._last_error = ""

    def configured(self) -> bool:
        return bool(self.url)

    def status(self) -> ProviderStatus:
        if not self.configured():
            return ProviderStatus(self.name, False, None,
                                  f"set {self.env_url} to enable")
        return ProviderStatus(self.name, True, not self._last_error,
                              self._last_error or "ok")

    def collect(self, window: TimeWindow, hints: dict | None = None) -> list[Signal]:
        raise NotImplementedError

    # ---- helpers for subclasses -----------------------------------------
    def _get_json(self, path: str, params: dict | None = None, headers: dict | None = None):
        """GET JSON, returning None on any failure and recording the reason.

        `requests` is imported lazily so the package imports cleanly in an
        environment that only runs the offline tests.
        """
        if not self.configured():
            return None
        try:
            import requests
        except ImportError:  # pragma: no cover - requests is in requirements
            self._last_error = "requests not installed"
            return None
        try:
            r = requests.get(f"{self.url}{path}", params=params or {},
                             headers=headers or {}, timeout=self.timeout)
            if r.status_code >= 400:
                self._last_error = f"HTTP {r.status_code} from {path}"
                return None
            self._last_error = ""
            return r.json()
        except Exception as e:  # network, DNS, JSON - all non-fatal
            self._last_error = f"{type(e).__name__}: {e}"
            return None


def signal_id(source: str, kind: str, n: int) -> str:
    return f"{source[:4].upper()}-{kind[:3].upper()}-{n:03d}"
