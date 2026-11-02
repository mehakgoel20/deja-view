"""Rank causal hypotheses on supporting *and* contradicting evidence.

Similarity retrieval ranks by "how much does this look like the new
incident". That is the wrong question: two incidents with identical symptoms
often have different causes, so a confident wrong answer is the default
failure mode.

A hypothesis here is scored on four things:

* **coverage** - how many of the observed symptoms it explains;
* **support** - evidence for it (preceding change, dependency path, precedent);
* **contradiction** - evidence against it, which actively subtracts;
* **specificity** - whether it names a mechanism or just restates the symptom.

Contradictions are the part usually missing. "Latency rose" does not support
"bad deploy" if the deploy landed *after* the latency rose, and a cause whose
service nothing downstream depends on cannot explain a downstream symptom.
Those checks demote plausible-sounding but unsupportable causes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .model import (BASIS_COOCCURRENCE, BASIS_MECHANISM, BASIS_PRECEDENT,
                    BASIS_TEMPORAL, BASIS_TOPOLOGY, NODE_SYMPTOM, CausalGraph)

# How much each supporting fact adds.
W_COVERAGE = 0.40
W_SUPPORT = 0.35
W_SPECIFICITY = 0.25
# How much each contradiction removes. Deliberately steep: a cause that is
# ordered wrongly is not a weak hypothesis, it is the wrong hypothesis.
W_CONTRADICTION = 0.30

# Prior by node kind. A named mechanism is what an RCA should report; a change
# is the trigger that exposed it; a latent condition only contributed.
KIND_PRIOR = {"mechanism": 1.00, "change": 0.85, "condition": 0.55,
              "symptom": 0.0}


@dataclass
class Evidence:
    kind: str           # "support" | "contradiction"
    basis: str
    statement: str
    refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Hypothesis:
    node_id: str
    cause: str
    score: float = 0.0
    likelihood: float = 0.0
    is_root_cause: bool = True
    explains: list[str] = field(default_factory=list)
    support: list[Evidence] = field(default_factory=list)
    contradictions: list[Evidence] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["support"] = [e.to_dict() for e in self.support]
        d["contradictions"] = [e.to_dict() for e in self.contradictions]
        return d


def _specificity(label: str) -> float:
    """Does the label name a mechanism, or merely restate a symptom?

    Mirrors the rule used when the gold set was built: a cause has to say what
    broke, not that something was slow.
    """
    low = label.lower()
    vague = ("error rate rises", "latency rises", "requests fail", "requests time out",
             "service is down", "degraded", "an issue", "a problem", "outage")
    if any(v in low for v in vague):
        return 0.15
    mechanism_words = (
        "config", "deploy", "index", "pool", "connection", "memory", "leak",
        "certificate", "expired", "dns", "resolution", "schema", "migration",
        "lock", "race", "quota", "limit", "capacity", "disk", "node",
        "upstream", "dependency", "rollback", "regression", "defect", "bug",
        "credential", "token", "permission", "timeout", "threshold")
    hits = sum(1 for w in mechanism_words if w in low)
    return min(1.0, 0.35 + 0.18 * hits)


def collect_evidence(graph: CausalGraph, node_id: str,
                     observed_symptoms: set[str] | None = None):
    """Gather support and contradictions for one candidate cause."""
    support: list[Evidence] = []
    contra: list[Evidence] = []
    node = graph.nodes[node_id]
    observed = observed_symptoms or {s.id for s in graph.symptoms()}

    out_edges = [e for e in graph.edges if e.cause == node_id]
    reach = graph.downstream(node_id)
    explained = sorted(observed & reach)

    for e in out_edges:
        effect = graph.nodes[e.effect]
        if e.basis == BASIS_TEMPORAL:
            support.append(Evidence("support", e.basis,
                                    f"Preceded in time: {e.note or effect.label}",
                                    node.evidence))
        elif e.basis == BASIS_TOPOLOGY:
            support.append(Evidence("support", e.basis,
                                    f"Dependency path explains propagation: {e.note}",
                                    node.evidence))
        elif e.basis == BASIS_MECHANISM:
            support.append(Evidence("support", e.basis,
                                    f"Known mechanism produces: {effect.label}",
                                    node.evidence))

    # Precedent: historical incident ids attached to the node.
    precedents = [r for r in node.evidence if r.startswith("GOLD-")]
    if precedents:
        support.append(Evidence("support", BASIS_PRECEDENT,
                                f"{len(precedents)} past incident(s) show this mechanism",
                                precedents))

    # ---- contradictions -------------------------------------------------
    if not explained and observed:
        contra.append(Evidence("contradiction", "no-coverage",
                               "Explains none of the observed symptoms", []))
    # A cause whose only link is co-occurrence is not ordered evidence.
    if out_edges and all(e.basis == BASIS_COOCCURRENCE for e in out_edges):
        contra.append(Evidence("contradiction", "co-occurrence-only",
                               "Only co-occurs with the symptoms; no ordering or "
                               "dependency path establishes direction", []))
    # Ordered after a symptom it is supposed to cause.
    if node.at is not None:
        for sid in explained:
            s = graph.nodes[sid]
            if s.at is not None and s.at < node.at:
                contra.append(Evidence(
                    "contradiction", "wrong-order",
                    f"Occurred after '{s.label[:60]}', which it cannot have caused",
                    node.evidence))
                break
    if _specificity(node.label) <= 0.15:
        contra.append(Evidence("contradiction", "restates-symptom",
                               "Restates a symptom rather than naming a mechanism", []))
    return support, contra, explained


def rank(graph: CausalGraph, limit: int = 5) -> list[Hypothesis]:
    """Score every root candidate and return the best, most likely first."""
    observed = {s.id for s in graph.symptoms()}
    total_observed = max(1, len(observed))

    # Candidates: nodes nothing explains, plus mechanism nodes (a mechanism
    # with a known trigger still is the root cause worth reporting).
    candidates = {n.id for n in graph.root_candidates()}
    candidates |= {n.id for n in graph.nodes.values()
                   if n.kind == "mechanism"}

    hypotheses: list[Hypothesis] = []
    for nid in candidates:
        node = graph.nodes[nid]
        if node.kind == NODE_SYMPTOM:
            continue
        support, contra, explained = collect_evidence(graph, nid, observed)
        coverage = len(explained) / total_observed
        support_strength = min(1.0, 0.25 * len(support))
        spec = _specificity(node.label)
        score = (W_COVERAGE * coverage
                 + W_SUPPORT * support_strength
                 + W_SPECIFICITY * spec
                 - W_CONTRADICTION * len(contra))
        score *= KIND_PRIOR.get(node.kind, 0.7)
        score = max(0.0, round(score, 4))
        hypotheses.append(Hypothesis(
            node_id=nid,
            cause=node.label,
            score=score,
            is_root_cause=not graph.is_symptom(nid),
            explains=explained,
            support=support,
            contradictions=contra,
            evidence_ids=list(dict.fromkeys(node.evidence)),
            reasoning=_reasoning(node.label, explained, support, contra),
        ))

    hypotheses.sort(key=lambda h: -h.score)
    hypotheses = hypotheses[:limit]
    total = sum(h.score for h in hypotheses)
    for h in hypotheses:
        h.likelihood = round(h.score / total, 3) if total else 0.0
    return hypotheses


def _reasoning(label: str, explained: list[str], support, contra) -> str:
    bits = []
    if explained:
        bits.append(f"explains {len(explained)} observed symptom(s)")
    else:
        bits.append("explains none of the observed symptoms")
    if support:
        bits.append("supported by " + "; ".join(s.basis for s in support[:3]))
    if contra:
        bits.append("but contradicted by " + "; ".join(c.basis for c in contra[:2]))
    return f"{label}: " + ", ".join(bits) + "."


def render(hypotheses: list[Hypothesis]) -> str:
    if not hypotheses:
        return "CAUSAL HYPOTHESES: none could be formed."
    lines = []
    for i, h in enumerate(hypotheses, 1):
        tag = "root cause" if h.is_root_cause else "symptom of something upstream"
        lines.append(f"  {i}. [{h.likelihood:.2f}] {h.cause[:90]}  ({tag})")
        for s in h.support[:3]:
            lines.append(f"       + {s.statement[:100]}")
        for c in h.contradictions[:2]:
            lines.append(f"       - {c.statement[:100]}")
    return "CAUSAL HYPOTHESES:\n" + "\n".join(lines)
