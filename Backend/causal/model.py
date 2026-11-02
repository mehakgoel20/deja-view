"""Causal graph: the data model that lets us say "X caused Y", not "X and Y".

A node is one fact about the incident. An edge is a claimed causal link with
a confidence and the evidence behind it. From that structure two questions
become answerable mechanically:

* **Is this a symptom or a root cause?** A node with incoming causal edges is
  an effect of something else. A node with none is a candidate root cause.
  This is the distinction similarity search cannot make: retrieval finds
  incidents that *look* alike, and two incidents with identical symptoms
  routinely have different causes.
* **How much does a candidate explain?** The set of symptoms reachable
  downstream of it. A cause that explains five observed symptoms beats one
  that explains one, even if the second scored higher on text similarity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

# What kind of fact a node represents.
NODE_CHANGE = "change"          # a deploy, config edit, migration - a trigger
NODE_MECHANISM = "mechanism"    # the failure mode itself (the root cause)
NODE_SYMPTOM = "symptom"        # customer- or monitor-visible effect
NODE_CONDITION = "condition"    # a latent precondition (no headroom, no alert)

# Why we believe an edge exists. Ordered weakest to strongest.
BASIS_COOCCURRENCE = "co-occurrence"    # happened around the same time
BASIS_TEMPORAL = "temporal-order"       # A measurably preceded B
BASIS_TOPOLOGY = "dependency-path"      # B depends on A in the service graph
BASIS_PRECEDENT = "known-precedent"     # a past incident shows this mechanism
BASIS_MECHANISM = "stated-mechanism"    # the report or a postmortem says so

BASIS_WEIGHT = {
    BASIS_COOCCURRENCE: 0.25,
    BASIS_TEMPORAL: 0.45,
    BASIS_TOPOLOGY: 0.60,
    BASIS_PRECEDENT: 0.70,
    BASIS_MECHANISM: 0.90,
}


@dataclass
class CausalNode:
    id: str
    kind: str
    label: str
    at: datetime | None = None
    service: str | None = None
    evidence: list[str] = field(default_factory=list)   # signal / incident ids
    confidence: float = 0.5

    def to_dict(self) -> dict:
        d = asdict(self)
        d["at"] = self.at.isoformat() if self.at else None
        return d


@dataclass
class CausalEdge:
    cause: str
    effect: str
    basis: str
    confidence: float
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class CausalGraph:
    """A DAG of causal claims. Cycles are refused so "explains" terminates."""

    def __init__(self):
        self.nodes: dict[str, CausalNode] = {}
        self.edges: list[CausalEdge] = []

    # ---- construction ---------------------------------------------------
    def add_node(self, node: CausalNode) -> CausalNode:
        existing = self.nodes.get(node.id)
        if existing:
            # keep the stronger claim and merge evidence
            existing.confidence = max(existing.confidence, node.confidence)
            for e in node.evidence:
                if e not in existing.evidence:
                    existing.evidence.append(e)
            return existing
        self.nodes[node.id] = node
        return node

    def add_edge(self, cause: str, effect: str, basis: str,
                 confidence: float | None = None, note: str = "") -> bool:
        """Add a causal link. Returns False if it would create a cycle."""
        if cause not in self.nodes or effect not in self.nodes or cause == effect:
            return False
        if self._reaches(effect, cause):
            return False            # would make a cycle
        conf = BASIS_WEIGHT.get(basis, 0.3) if confidence is None else confidence
        for e in self.edges:
            if e.cause == cause and e.effect == effect:
                if conf > e.confidence:     # a stronger basis supersedes
                    e.basis, e.confidence, e.note = basis, conf, note
                return True
        self.edges.append(CausalEdge(cause, effect, basis, round(conf, 3), note))
        return True

    # ---- traversal ------------------------------------------------------
    def _out(self, node_id: str) -> list[CausalEdge]:
        return [e for e in self.edges if e.cause == node_id]

    def _in(self, node_id: str) -> list[CausalEdge]:
        return [e for e in self.edges if e.effect == node_id]

    def _reaches(self, start: str, target: str) -> bool:
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur == target:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack += [e.effect for e in self._out(cur)]
        return False

    def downstream(self, node_id: str) -> set[str]:
        """Everything this node causes, transitively."""
        seen, stack = set(), [node_id]
        while stack:
            for e in self._out(stack.pop()):
                if e.effect not in seen:
                    seen.add(e.effect)
                    stack.append(e.effect)
        return seen

    def upstream(self, node_id: str) -> set[str]:
        seen, stack = set(), [node_id]
        while stack:
            for e in self._in(stack.pop()):
                if e.cause not in seen:
                    seen.add(e.cause)
                    stack.append(e.cause)
        return seen

    # ---- the questions we actually care about ---------------------------
    def symptoms(self) -> list[CausalNode]:
        """The effects to be explained.

        Only nodes typed as symptoms count. Having an incoming edge is not
        enough: in a trigger -> mechanism -> symptom chain the mechanism has a
        cause upstream and is still the thing you report as the root cause.
        """
        return [n for n in self.nodes.values() if n.kind == NODE_SYMPTOM]

    def root_candidates(self) -> list[CausalNode]:
        """Nodes nothing in the graph explains - the possible root causes."""
        return [n for n in self.nodes.values()
                if not self._in(n.id) and n.kind != NODE_SYMPTOM]

    def is_symptom(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        return node is not None and node.kind == NODE_SYMPTOM

    def explains(self, node_id: str) -> list[str]:
        """Which observed symptoms this node accounts for."""
        reach = self.downstream(node_id)
        return sorted(s.id for s in self.symptoms() if s.id in reach)

    def chain_to(self, node_id: str, target: str) -> list[str]:
        """A causal chain from node to target, for explaining the reasoning."""
        path: list[str] = []

        def walk(cur, acc):
            nonlocal path
            if cur == target:
                path = acc + [cur]
                return True
            for e in sorted(self._out(cur), key=lambda e: -e.confidence):
                if e.effect in acc:
                    continue
                if walk(e.effect, acc + [cur]):
                    return True
            return False

        walk(node_id, [])
        return path

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
            "root_candidates": [n.id for n in self.root_candidates()],
            "symptoms": [n.id for n in self.symptoms()],
        }

    def render(self) -> str:
        """Text rendering of the causal chains, strongest first."""
        if not self.edges:
            return "CAUSAL GRAPH: no causal links established."
        lines = []
        for e in sorted(self.edges, key=lambda e: -e.confidence):
            c, f = self.nodes[e.cause], self.nodes[e.effect]
            lines.append(f"  {c.label[:60]}  ──({e.basis} {e.confidence:.2f})──>  "
                         f"{f.label[:60]}")
        roots = [n.label for n in self.root_candidates()]
        out = "CAUSAL GRAPH:\n" + "\n".join(lines)
        if roots:
            out += "\nUNEXPLAINED (root candidates): " + "; ".join(r[:70] for r in roots)
        return out
