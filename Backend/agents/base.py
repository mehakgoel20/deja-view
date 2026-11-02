"""Agent contract for the multi-agent RCA system (feature 2).

Each agent is a specialist that reads the shared `Context` and returns
`Finding` objects. Agents never talk to each other directly - the
orchestrator collects their findings and passes them on - so one agent
failing or being unconfigured degrades the investigation instead of breaking
it.

Every agent does as much as it can deterministically before reaching for the
LLM. That keeps the investigation testable offline (`llm=False`) and stops a
model from being asked to summarise evidence it could have computed exactly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

# What an agent is asserting.
FINDING_OBSERVATION = "observation"      # a fact read off the evidence
FINDING_HYPOTHESIS = "hypothesis"        # a claim about cause
FINDING_RECOMMENDATION = "recommendation"
FINDING_GAP = "gap"                      # evidence that is missing


@dataclass
class Finding:
    agent: str
    kind: str
    statement: str
    confidence: float = 0.5
    evidence_ids: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Context:
    """Everything the agents may read. Any field may be absent."""

    text: str = ""
    window: object | None = None          # observability.TimeWindow
    signals: list = field(default_factory=list)
    correlation: dict = field(default_factory=dict)
    service_graph: object | None = None    # graph.ServiceGraph
    kb: object | None = None               # rag.kb.KnowledgeBase
    neighbours: list = field(default_factory=list)   # retrieval results
    causal: dict = field(default_factory=dict)
    timeline: dict = field(default_factory=dict)
    reported_at: datetime | None = None
    use_llm: bool = True

    def signals_of_kind(self, *kinds) -> list:
        return [s for s in self.signals if s.kind in kinds]

    def failing_services(self) -> list[str]:
        return sorted({s.service for s in self.signals if s.service})


class Agent:
    """Base class. Subclasses set `name`/`role` and implement `run`."""

    name = "agent"
    role = ""
    #: agents with the same stage run concurrently; stages run in order
    stage = 1

    def run(self, ctx: Context) -> list[Finding]:
        raise NotImplementedError

    # ---- helpers --------------------------------------------------------
    def finding(self, kind: str, statement: str, confidence: float = 0.5,
                evidence_ids: list[str] | None = None, **detail) -> Finding:
        return Finding(agent=self.name, kind=kind, statement=statement,
                       confidence=round(max(0.0, min(1.0, confidence)), 3),
                       evidence_ids=evidence_ids or [], detail=detail)

    def ask_llm(self, system: str, user: str, schema: dict, name: str):
        """Call the project's LLM wrapper, returning None if unavailable.

        An agent must never fail an investigation because a key is missing or
        a model is down, so every error becomes "no LLM contribution".
        """
        try:
            from rag.llm import chat_json
            return chat_json(system, user, schema, name)
        except Exception:
            return None
