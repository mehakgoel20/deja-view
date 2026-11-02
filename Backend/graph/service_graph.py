"""Service dependency graph (feature 3).

A directed graph of services where an edge A -> B means "A depends on B", so
a failure in B propagates *up* the edges to A. That direction matters: when
Redis fails, the question is which services call Redis, not what Redis calls.

NetworkX is the default backend because the graph is small and shipping it
needs no extra infrastructure. Neo4j is available through the same API for
teams that already run it (see neo4j_store.py).

    g = ServiceGraph.from_file("topology.yaml")
    g.blast_radius("redis")          # everything that breaks if redis does
    g.critical_path("api-gateway")   # what api-gateway ultimately rests on
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import networkx as nx
except ImportError:  # pragma: no cover - networkx is in requirements
    nx = None

# Impact weight by dependency type. A synchronous call fails the caller
# immediately; an async one usually degrades it instead.
EDGE_WEIGHTS = {"sync": 1.0, "async": 0.4, "cache": 0.6, "storage": 0.9,
                "optional": 0.2, "unknown": 0.7}

TIER_CRITICAL = "critical"
TIER_IMPORTANT = "important"
TIER_BEST_EFFORT = "best_effort"


@dataclass
class Service:
    name: str
    kind: str = "service"          # service | datastore | queue | external
    tier: str = TIER_IMPORTANT
    owner: str = ""
    metadata: dict = field(default_factory=dict)


class ServiceGraph:
    """Directed dependency graph with blast-radius and path queries."""

    def __init__(self):
        if nx is None:
            raise ImportError("networkx is required for ServiceGraph")
        self.g = nx.DiGraph()

    # ---- construction ---------------------------------------------------
    def add_service(self, name: str, **attrs) -> None:
        svc = Service(name=name, **{k: v for k, v in attrs.items()
                                    if k in {"kind", "tier", "owner", "metadata"}})
        self.g.add_node(name, kind=svc.kind, tier=svc.tier, owner=svc.owner,
                        metadata=svc.metadata)

    def add_dependency(self, caller: str, dependency: str, dep_type: str = "sync") -> None:
        """Record that `caller` depends on `dependency`."""
        for n in (caller, dependency):
            if n not in self.g:
                self.add_service(n)
        self.g.add_edge(caller, dependency, dep_type=dep_type,
                        weight=EDGE_WEIGHTS.get(dep_type, EDGE_WEIGHTS["unknown"]))

    @classmethod
    def from_dict(cls, spec: dict) -> "ServiceGraph":
        """Build from {"services": [...], "dependencies": [...]}.

        Also accepts the terse form {"api": ["auth", "redis"], ...}.
        """
        g = cls()
        if "dependencies" in spec or "services" in spec:
            for s in spec.get("services", []) or []:
                if isinstance(s, str):
                    g.add_service(s)
                else:
                    g.add_service(s["name"], **{k: v for k, v in s.items() if k != "name"})
            for d in spec.get("dependencies", []) or []:
                if isinstance(d, (list, tuple)):
                    g.add_dependency(d[0], d[1], d[2] if len(d) > 2 else "sync")
                else:
                    g.add_dependency(d["from"], d["to"], d.get("type", "sync"))
        else:
            for caller, deps in spec.items():
                g.add_service(caller)
                for dep in deps or []:
                    if isinstance(dep, str):
                        g.add_dependency(caller, dep)
                    else:
                        g.add_dependency(caller, dep["to"], dep.get("type", "sync"))
        return g

    @classmethod
    def from_file(cls, path: str | Path) -> "ServiceGraph":
        path = Path(path)
        text = path.read_text()
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as e:  # pragma: no cover
                raise ImportError("pyyaml is required to read YAML topologies") from e
            spec = yaml.safe_load(text)
        else:
            spec = json.loads(text)
        return cls.from_dict(spec)

    @classmethod
    def from_signals(cls, signals) -> "ServiceGraph":
        """Infer a rough graph from trace signals, when no topology file exists.

        Traces give caller/callee pairs; everything else only gives us nodes.
        A graph built this way is partial, so `inferred` is set on each edge.
        """
        g = cls()
        for s in signals:
            if s.service:
                g.add_service(s.service)
            caller = (s.detail or {}).get("caller")
            callee = (s.detail or {}).get("callee") or s.service
            if caller and callee and caller != callee:
                g.add_dependency(caller, callee, "sync")
                g.g.edges[caller, callee]["inferred"] = True
        return g

    # ---- queries --------------------------------------------------------
    @staticmethod
    def _reachable(graph, source: str, depth: int | None) -> set:
        """Nodes reachable from `source`, optionally within `depth` hops."""
        if depth is None:
            return nx.descendants(graph, source)
        seen, frontier = set(), {source}
        for _ in range(depth):
            nxt = set()
            for node in frontier:
                nxt |= set(graph.successors(node))
            nxt -= seen | {source}
            if not nxt:
                break
            seen |= nxt
            frontier = nxt
        return seen

    def dependencies_of(self, service: str, depth: int | None = None) -> list[str]:
        """What `service` needs, transitively (follows edges forward)."""
        if service not in self.g:
            return []
        return sorted(self._reachable(self.g, service, depth))

    def dependents_of(self, service: str, depth: int | None = None) -> list[str]:
        """What needs `service`, transitively (follows edges backward)."""
        if service not in self.g:
            return []
        return sorted(self._reachable(self.g.reverse(copy=False), service, depth))

    def blast_radius(self, service: str) -> dict:
        """Who is affected if `service` fails, and how badly.

        Impact decays along the path: a direct synchronous caller is hit hard,
        something three optional hops away barely notices.
        """
        if service not in self.g:
            return {"service": service, "known": False, "affected": [], "summary":
                    f"{service} is not in the dependency graph."}
        rev = self.g.reverse(copy=False)
        impact: dict[str, float] = {}
        hops: dict[str, int] = {}
        frontier = {service: 1.0}
        seen = {service}
        hop = 0
        while frontier and hop < 10:
            hop += 1
            nxt: dict[str, float] = {}
            for node, carried in frontier.items():
                for caller in rev.successors(node):
                    w = self.g.edges[caller, node].get("weight", 0.7)
                    score = carried * w
                    if score <= 0.05:
                        continue
                    if score > impact.get(caller, 0):
                        impact[caller] = score
                        hops[caller] = hop
                    if caller not in seen:
                        seen.add(caller)
                        nxt[caller] = max(nxt.get(caller, 0), score)
            frontier = nxt
        affected = [
            {"service": s, "impact": round(v, 3), "hops": hops[s],
             "tier": self.g.nodes[s].get("tier", TIER_IMPORTANT)}
            for s, v in sorted(impact.items(), key=lambda kv: -kv[1])
        ]
        critical = [a["service"] for a in affected if a["tier"] == TIER_CRITICAL]
        parts = [f"{len(affected)} service(s) depend on {service}"]
        if critical:
            parts.append("including critical: " + ", ".join(critical[:5]))
        direct = [a["service"] for a in affected if a["hops"] == 1]
        if direct:
            parts.append("directly: " + ", ".join(direct[:6]))
        return {"service": service, "known": True, "affected": affected,
                "critical_affected": critical,
                "summary": "; ".join(parts) + "."}

    def critical_path(self, service: str) -> list[str]:
        """The heaviest dependency chain under `service` - what it really rests on."""
        if service not in self.g:
            return []
        best: list[str] = []
        best_score = -1.0

        def walk(node, path, score):
            nonlocal best, best_score
            outs = list(self.g.successors(node))
            if not outs or len(path) > 12:
                if score > best_score:
                    best, best_score = list(path), score
                return
            for nb in outs:
                if nb in path:          # cycle guard
                    continue
                walk(nb, path + [nb], score + self.g.edges[node, nb].get("weight", 0.7))

        walk(service, [service], 0.0)
        return best

    def shared_dependencies(self, services: list[str]) -> list[str]:
        """Dependencies common to all the given services.

        When several services fail together, a shared dependency is a far
        better explanation than a coincidence in each of them.
        """
        sets = [set(self.dependencies_of(s)) for s in services if s in self.g]
        if not sets:
            return []
        common = set.intersection(*sets) if len(sets) > 1 else sets[0]
        return sorted(common)

    def rank_suspects(self, failing: list[str]) -> list[dict]:
        """Rank services by how well each explains the observed failures.

        A node scores for every failing service that depends on it, weighted by
        path impact, plus a bonus for being a datastore (shared infrastructure
        fails more often than it is blamed).
        """
        failing = [f for f in failing if f in self.g]
        if not failing:
            return []
        scores: dict[str, float] = {}
        for f in failing:
            scores[f] = scores.get(f, 0) + 0.5     # it may simply be itself
            for dep in self.dependencies_of(f):
                depth = 1
                try:
                    depth = nx.shortest_path_length(self.g, f, dep)
                except nx.NetworkXNoPath:           # pragma: no cover
                    pass
                scores[dep] = scores.get(dep, 0) + 1.0 / depth
        out = []
        for svc, score in scores.items():
            kind = self.g.nodes[svc].get("kind", "service")
            if kind in ("datastore", "queue"):
                score *= 1.2
            explains = sum(1 for f in failing
                           if svc == f or svc in self.dependencies_of(f))
            out.append({"service": svc, "score": round(score, 3), "kind": kind,
                        "explains": explains, "of_failing": len(failing)})
        return sorted(out, key=lambda d: (-d["explains"], -d["score"]))

    # ---- serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "services": [{"name": n, **{k: v for k, v in d.items() if k != "metadata"}}
                         for n, d in self.g.nodes(data=True)],
            "dependencies": [{"from": u, "to": v, "type": d.get("dep_type", "sync")}
                             for u, v, d in self.g.edges(data=True)],
        }

    def stats(self) -> dict:
        cycles = []
        try:
            cycles = [c for c in nx.simple_cycles(self.g)][:5]
        except Exception:               # pragma: no cover
            pass
        return {"services": self.g.number_of_nodes(),
                "dependencies": self.g.number_of_edges(),
                "cycles": cycles,
                "datastores": [n for n, d in self.g.nodes(data=True)
                               if d.get("kind") in ("datastore", "queue")]}


def default_topology_path() -> Path | None:
    """RCA_TOPOLOGY_PATH, or Backend/data/topology.(yaml|json) if present."""
    env = os.getenv("RCA_TOPOLOGY_PATH")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parents[1] / "data"
    for name in ("topology.yaml", "topology.yml", "topology.json"):
        if (here / name).exists():
            return here / name
    return None


def load_default_graph() -> ServiceGraph | None:
    path = default_topology_path()
    if not path:
        return None
    try:
        return ServiceGraph.from_file(path)
    except Exception:
        return None
