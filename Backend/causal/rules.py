"""Causal rules: turn observations into cause-effect links without an LLM.

Two sources of links:

1. **Temporal + topological.** If A precedes B and B's service depends on A's
   service, that is a defensible causal direction. Co-occurrence alone is the
   weakest basis and is marked as such.
2. **Known failure mechanisms.** A library of mechanism patterns ("memory
   grows without bound -> OOM kill -> restart loop") drawn from the recurring
   shapes in the 2,856-incident gold set. Each pattern knows which of its
   nodes is the mechanism and which are symptoms, which is what lets the
   engine answer "is this a symptom?" rather than guessing.

Keeping this deterministic matters: the LLM can then be asked to critique a
causal graph it did not invent, instead of inventing and grading its own.
"""
from __future__ import annotations

import re
from datetime import timedelta

from observability.base import KIND_DEPLOY, KIND_SERVICE_RESTART, Signal

from .model import (BASIS_MECHANISM, BASIS_TEMPORAL, BASIS_TOPOLOGY,
                    NODE_CHANGE, NODE_CONDITION, NODE_MECHANISM, NODE_SYMPTOM,
                    CausalGraph, CausalNode)

# A precedes B by at most this and we are willing to call it ordering.
MAX_CAUSAL_GAP = timedelta(minutes=45)


class Mechanism:
    """A recurring failure shape: trigger -> mechanism -> symptoms."""

    def __init__(self, key: str, label: str, trigger: str, mechanism: str,
                 symptoms: list[str], patterns: list[str],
                 conditions: list[str] | None = None):
        self.key = key
        self.label = label
        self.trigger = trigger
        self.mechanism = mechanism
        self.symptoms = symptoms
        self.conditions = conditions or []
        self.regex = re.compile("|".join(patterns), re.I)

    def matches(self, text: str) -> bool:
        return bool(self.regex.search(text))


# Drawn from the dominant categories in the gold set: configuration_deployment,
# database_issue, api_latency, hardware_infra, networking_dns, memory_leak.
MECHANISMS = [
    Mechanism(
        "config_rollout", "Bad configuration reached production",
        trigger="A configuration or release change was applied",
        mechanism="The new value was invalid or incompatible for the consuming service",
        symptoms=["Requests fail or are rejected", "Error rate rises sharply"],
        patterns=[r"config(uration)?\s+(change|error|push|rollout)", r"misconfigur",
                  r"feature flag", r"wrong (value|default|setting)", r"env(ironment)? var"],
        conditions=["The rollout had no staged health gate"],
    ),
    Mechanism(
        "bad_deploy", "A deploy introduced a regression",
        trigger="A new version was deployed",
        mechanism="The new build contained a defect on a production code path",
        symptoms=["Error rate rises sharply", "Requests fail or are rejected"],
        patterns=[r"\bdeploy", r"\brelease\b", r"rollout", r"new version",
                  r"regression", r"rolled back", r"revert"],
        conditions=["The defective path was not covered pre-production"],
    ),
    Mechanism(
        "connection_exhaustion", "Connection or pool exhaustion",
        trigger="Load rose or connections stopped being released",
        mechanism="The connection pool reached its ceiling and refused new work",
        symptoms=["Requests time out", "Latency rises", "Error rate rises sharply"],
        patterns=[r"connection(s)? (pool|limit|exhaust|refus)", r"too many connections",
                  r"pool (saturat|exhaust|full)", r"max_connections"],
        conditions=["Pool size was fixed rather than scaled with the fleet"],
    ),
    Mechanism(
        "slow_query", "A query stopped using its index",
        trigger="A schema change, data growth or plan flip",
        mechanism="Queries fell back to full scans and saturated the database",
        symptoms=["Latency rises", "Requests time out", "Database CPU saturates"],
        patterns=[r"\bindex\b", r"full (table )?scan", r"query plan", r"slow quer",
                  r"schema (change|migration)", r"missing index"],
    ),
    Mechanism(
        "memory_leak", "Unbounded memory growth",
        trigger="Sustained traffic over time",
        mechanism="Memory was retained and never released, exhausting the limit",
        symptoms=["Process is OOM-killed", "Service restarts repeatedly",
                  "Latency rises"],
        patterns=[r"memory leak", r"out of memory", r"\boom\b", r"heap (growth|exhaust)",
                  r"memory (grew|growth|climb|exhaust)"],
        conditions=["No alert fired on memory trend before the ceiling"],
    ),
    Mechanism(
        "cert_expiry", "A certificate or credential expired",
        trigger="A certificate or token reached its expiry",
        mechanism="Peers rejected the expired credential, so authentication failed",
        symptoms=["Requests fail or are rejected", "Authentication fails"],
        patterns=[r"certificat", r"\btls\b", r"\bssl\b", r"expir(ed|y|ation)",
                  r"token (expired|rotation)", r"credential (expired|rotat)"],
        conditions=["Automated renewal was failing silently"],
    ),
    Mechanism(
        "dns_resolution", "Name resolution broke",
        trigger="A DNS or service-discovery change",
        mechanism="Consumers could not resolve the name and never opened a connection",
        symptoms=["Requests fail or are rejected", "Service cannot reach dependency"],
        patterns=[r"\bdns\b", r"resolv", r"name resolution", r"service discovery",
                  r"\bnxdomain\b", r"zone file"],
    ),
    Mechanism(
        "upstream_dependency", "An upstream provider failed",
        trigger="A third-party or cloud provider degraded",
        mechanism="A dependency this service calls synchronously stopped responding",
        symptoms=["Requests time out", "Error rate rises sharply",
                  "Service cannot reach dependency"],
        patterns=[r"upstream", r"third[- ]party", r"\bvendor\b", r"provider (outage|incident)",
                  r"\baws\b|\bazure\b|\bgcp\b|cloud provider"],
        conditions=["The call had no timeout, fallback or circuit breaker"],
    ),
    Mechanism(
        "capacity_shortfall", "Capacity could not meet demand",
        trigger="Traffic rose or capacity was removed",
        mechanism="The service had fewer workers than its load required and shed work",
        symptoms=["Requests time out", "Latency rises", "Queue depth grows"],
        patterns=[r"capacity", r"saturat", r"overload", r"traffic (spike|surge|increase)",
                  r"scale (out|up)", r"autoscal", r"queue (depth|backlog)"],
    ),
    Mechanism(
        "disk_or_node", "A node or disk failed",
        trigger="Hardware or an availability zone failed",
        mechanism="The node stopped serving while still appearing healthy to the scheduler",
        symptoms=["Requests fail or are rejected", "Service restarts repeatedly"],
        patterns=[r"disk (fail|full|space)", r"\bnode (fail|degrad|unhealthy)",
                  r"hardware", r"availability zone", r"power (loss|outage)"],
        conditions=["The health probe tested liveness, not useful work"],
    ),
]


def _node(graph: CausalGraph, nid: str, kind: str, label: str, **kw) -> CausalNode:
    return graph.add_node(CausalNode(id=nid, kind=kind, label=label, **kw))


def apply_mechanism_rules(graph: CausalGraph, text: str,
                          evidence: list[str] | None = None) -> list[str]:
    """Add trigger -> mechanism -> symptom chains for every matching pattern.

    Returns the keys of the mechanisms that matched.
    """
    matched = []
    for m in MECHANISMS:
        if not m.matches(text):
            continue
        matched.append(m.key)
        trig = _node(graph, f"trigger::{m.key}", NODE_CHANGE, m.trigger,
                     evidence=list(evidence or []), confidence=0.5)
        mech = _node(graph, f"mech::{m.key}", NODE_MECHANISM, m.mechanism,
                     evidence=list(evidence or []), confidence=0.6)
        graph.add_edge(trig.id, mech.id, BASIS_MECHANISM,
                       note=f"{m.label}: known failure shape")
        for i, sym in enumerate(m.symptoms):
            s = _node(graph, f"sym::{_slug(sym)}", NODE_SYMPTOM, sym,
                      confidence=0.5)
            graph.add_edge(mech.id, s.id, BASIS_MECHANISM,
                           note=f"{m.label}: expected symptom {i + 1}")
        for cond in m.conditions:
            c = _node(graph, f"cond::{_slug(cond)}", NODE_CONDITION, cond,
                      confidence=0.4)
            graph.add_edge(c.id, mech.id, BASIS_MECHANISM,
                           note=f"{m.label}: latent precondition")
    return matched


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def apply_signal_rules(graph: CausalGraph, signals: list[Signal],
                       service_graph=None) -> None:
    """Link observed signals by time order, strengthened by topology.

    A deploy before a symptom is a candidate trigger. A symptom in service B
    after a symptom in service A, where B depends on A, is propagation.
    """
    for s in signals:
        kind = (NODE_CHANGE if s.kind == KIND_DEPLOY else
                NODE_SYMPTOM if s.kind != KIND_SERVICE_RESTART else NODE_SYMPTOM)
        _node(graph, f"sig::{s.id}", kind, s.summary, at=s.at,
              service=s.service, evidence=[s.id],
              confidence=0.8 if s.severity == "critical" else 0.6)

    ordered = sorted(signals, key=lambda s: s.at)
    for i, earlier in enumerate(ordered):
        for later in ordered[i + 1:]:
            gap = later.at - earlier.at
            if gap > MAX_CAUSAL_GAP:
                break
            a, b = f"sig::{earlier.id}", f"sig::{later.id}"
            # A deploy preceding anything is the classic trigger relationship.
            if earlier.kind == KIND_DEPLOY and later.kind != KIND_DEPLOY:
                graph.add_edge(a, b, BASIS_TEMPORAL,
                               note=f"change {int(gap.total_seconds() // 60)} min before symptom")
                continue
            # Otherwise require a dependency path to claim direction.
            if (service_graph is not None and earlier.service and later.service
                    and earlier.service != later.service):
                try:
                    dependents = service_graph.dependents_of(earlier.service)
                except Exception:
                    dependents = []
                if later.service in dependents:
                    graph.add_edge(a, b, BASIS_TOPOLOGY,
                                   note=f"{later.service} depends on {earlier.service}")


def apply_precedent_rules(graph: CausalGraph, neighbours_text: list[tuple[str, str]]) -> None:
    """Fold retrieved past incidents in as precedent for a mechanism.

    `neighbours_text` is [(incident_id, root_cause_text)]. A past incident that
    matches a mechanism pattern raises that mechanism's confidence and is
    recorded as its evidence - which is how a hypothesis ends up citing both a
    live signal and a historical precedent.
    """
    for inc_id, cause_text in neighbours_text:
        for m in MECHANISMS:
            if not m.matches(cause_text or ""):
                continue
            node = graph.nodes.get(f"mech::{m.key}")
            if node is None:
                node = _node(graph, f"mech::{m.key}", NODE_MECHANISM, m.mechanism,
                             confidence=0.5)
                for sym in m.symptoms:
                    s = _node(graph, f"sym::{_slug(sym)}", NODE_SYMPTOM, sym)
                    graph.add_edge(node.id, s.id, BASIS_MECHANISM)
            if inc_id not in node.evidence:
                node.evidence.append(inc_id)
            # Each independent precedent is worth a little more confidence.
            node.confidence = round(min(0.95, node.confidence + 0.08), 3)
