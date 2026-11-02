"""Incident timeline reconstruction (feature 5).

    from timeline import reconstruct, render

    tl = reconstruct(signals, window, reported_at=when, reported_text=text)
    print(render(tl))
    tl["ordering"]["verdict"]   # what happened first, and what likely triggered it
"""
from .reconstruct import (PHASE_IMPACT, PHASE_ONSET, PHASE_PRE,
                          PHASE_RECOVERY, PHASE_TRIGGER, TimelineEvent,
                          detection_delay, from_signals, reconstruct, render,
                          what_happened_first)

__all__ = ["reconstruct", "render", "TimelineEvent", "from_signals",
           "what_happened_first", "detection_delay", "PHASE_PRE",
           "PHASE_TRIGGER", "PHASE_ONSET", "PHASE_IMPACT", "PHASE_RECOVERY"]
