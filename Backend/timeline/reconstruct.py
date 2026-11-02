"""Incident timeline reconstruction (feature 5).

Merges everything that carries a timestamp - deploy markers, metric spikes,
log bursts, restarts, failing traces, recovery - into one ordered narrative,
then labels the phases: what changed, when it started hurting, when it
recovered.

The point is ordering. "The deploy went out four minutes before the error
rate moved" is an argument; "there was a deploy and there were errors" is not.
`what_happened_first` is deliberately conservative: it only nominates a
trigger when a change precedes the first symptom inside a plausible window.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from observability.base import (KIND_DEPLOY, KIND_LOG_BURST,
                                KIND_METRIC_SPIKE, KIND_RECOVERY,
                                KIND_SERVICE_RESTART, KIND_TRACE_ERROR,
                                Signal, TimeWindow)

# A change this far ahead of the first symptom can still be its trigger.
TRIGGER_WINDOW = timedelta(minutes=30)

CHANGE_KINDS = (KIND_DEPLOY,)
SYMPTOM_KINDS = (KIND_METRIC_SPIKE, KIND_LOG_BURST, KIND_TRACE_ERROR,
                 KIND_SERVICE_RESTART)

PHASE_PRE = "pre-incident"
PHASE_TRIGGER = "trigger"
PHASE_ONSET = "onset"
PHASE_IMPACT = "impact"
PHASE_RECOVERY = "recovery"


@dataclass
class TimelineEvent:
    at: datetime
    kind: str
    source: str
    summary: str
    phase: str = PHASE_IMPACT
    severity: str = "info"
    service: str | None = None
    signal_id: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["at"] = self.at.isoformat()
        return d


def from_signals(signals: list[Signal]) -> list[TimelineEvent]:
    return [TimelineEvent(at=s.at, kind=s.kind, source=s.source,
                          summary=s.summary, severity=s.severity,
                          service=s.service, signal_id=s.id, detail=s.detail)
            for s in signals]


def add_reported_event(events: list[TimelineEvent], reported_at: datetime,
                       text: str) -> list[TimelineEvent]:
    """Place the human report on the timeline.

    Worth keeping separate: the gap between first symptom and first report is
    the detection delay, which is often the most actionable number in a
    postmortem.
    """
    events.append(TimelineEvent(at=reported_at, kind="report", source="human",
                                summary=f"Incident reported: {text[:200]}",
                                severity="info"))
    return events


def _assign_phases(events: list[TimelineEvent]) -> None:
    symptoms = [e for e in events if e.kind in SYMPTOM_KINDS]
    if not symptoms:
        return
    onset = min(s.at for s in symptoms)
    recoveries = [e for e in events if e.kind == KIND_RECOVERY]
    recovered_at = min((r.at for r in recoveries), default=None)
    for e in events:
        if e.kind in CHANGE_KINDS and e.at <= onset and onset - e.at <= TRIGGER_WINDOW:
            e.phase = PHASE_TRIGGER
        elif e.at < onset:
            e.phase = PHASE_PRE
        elif recovered_at and e.at >= recovered_at:
            e.phase = PHASE_RECOVERY
        elif e.at <= onset + timedelta(minutes=5):
            e.phase = PHASE_ONSET
        else:
            e.phase = PHASE_IMPACT


def what_happened_first(events: list[TimelineEvent]) -> dict:
    """Identify the first symptom and, if there is one, the change before it."""
    symptoms = [e for e in events if e.kind in SYMPTOM_KINDS]
    changes = [e for e in events if e.kind in CHANGE_KINDS]
    if not symptoms:
        return {"first_symptom": None, "trigger": None, "lead_time_minutes": None,
                "verdict": "No symptom events on the timeline."}
    first = min(symptoms, key=lambda e: e.at)
    prior = [c for c in changes
             if c.at <= first.at and first.at - c.at <= TRIGGER_WINDOW]
    if not prior:
        unexplained = ("A change was recorded but after the first symptom, so it is "
                       "not the trigger." if changes else
                       "No change was recorded before the first symptom, so the "
                       "trigger is not a deploy visible to this pipeline.")
        return {"first_symptom": first.to_dict(), "trigger": None,
                "lead_time_minutes": None, "verdict": unexplained}
    trigger = max(prior, key=lambda c: c.at)
    lead = (first.at - trigger.at).total_seconds() / 60
    return {
        "first_symptom": first.to_dict(),
        "trigger": trigger.to_dict(),
        "lead_time_minutes": round(lead, 1),
        "verdict": (f"{trigger.summary} preceded the first symptom by "
                    f"{lead:.0f} min, making it the most likely trigger."),
    }


def detection_delay(events: list[TimelineEvent]) -> float | None:
    """Minutes between the first symptom and the human report, if both exist."""
    symptoms = [e for e in events if e.kind in SYMPTOM_KINDS]
    reports = [e for e in events if e.kind == "report"]
    if not symptoms or not reports:
        return None
    gap = min(r.at for r in reports) - min(s.at for s in symptoms)
    return round(gap.total_seconds() / 60, 1)


def reconstruct(signals: list[Signal], window: TimeWindow | None = None,
                reported_at: datetime | None = None,
                reported_text: str = "") -> dict:
    """Build the full timeline with phases and an ordering verdict."""
    events = from_signals(signals)
    if reported_at is not None:
        add_reported_event(events, reported_at, reported_text)
    events.sort(key=lambda e: e.at)
    _assign_phases(events)
    ordering = what_happened_first(events)
    by_phase: dict[str, int] = {}
    for e in events:
        by_phase[e.phase] = by_phase.get(e.phase, 0) + 1
    span = None
    if events:
        span = round((events[-1].at - events[0].at).total_seconds() / 60, 1)
    return {
        "events": [e.to_dict() for e in events],
        "event_count": len(events),
        "span_minutes": span,
        "by_phase": by_phase,
        "ordering": ordering,
        "detection_delay_minutes": detection_delay(events),
        "window": window.to_dict() if window else None,
    }


def render(timeline: dict, limit: int = 30) -> str:
    """Plain-text timeline for an LLM prompt or a terminal."""
    events = timeline.get("events", [])
    if not events:
        return "TIMELINE: no timestamped events available."
    lines = []
    for e in events[:limit]:
        at = e["at"][11:19] if len(e["at"]) > 19 else e["at"]
        svc = f" {e['service']}" if e.get("service") else ""
        ref = f" [{e['signal_id']}]" if e.get("signal_id") else ""
        lines.append(f"  {at} {e['phase']:<12}{svc} {e['summary'][:120]}{ref}")
    out = "TIMELINE:\n" + "\n".join(lines)
    if len(events) > limit:
        out += f"\n  (+{len(events) - limit} more)"
    verdict = (timeline.get("ordering") or {}).get("verdict")
    if verdict:
        out += f"\nORDERING: {verdict}"
    delay = timeline.get("detection_delay_minutes")
    if delay is not None:
        out += f"\nDETECTION DELAY: {delay} min from first symptom to report."
    return out
