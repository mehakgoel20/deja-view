"""Optional Neo4j backing for the service graph.

NetworkX is the default: the graph is small, queries are sub-millisecond and
it needs no extra infrastructure. Neo4j is worth it when the topology is
already maintained there, or when it is large enough that you want Cypher and
persistence rather than a file.

Enable with:
    RCA_NEO4J_URI=bolt://localhost:7687
    RCA_NEO4J_USER=neo4j
    RCA_NEO4J_PASSWORD=...

    store = Neo4jServiceStore()
    store.push(graph)                  # mirror a ServiceGraph into Neo4j
    g = store.pull()                   # and back out again

`pull()` returns a plain ServiceGraph, so every query in service_graph.py
works unchanged regardless of where the topology was stored.
"""
from __future__ import annotations

import os

from .service_graph import ServiceGraph

LABEL = "Service"
REL = "DEPENDS_ON"


class Neo4jServiceStore:
    def __init__(self, uri: str | None = None, user: str | None = None,
                 password: str | None = None):
        self.uri = uri or os.getenv("RCA_NEO4J_URI", "")
        self.user = user or os.getenv("RCA_NEO4J_USER", "neo4j")
        self.password = password or os.getenv("RCA_NEO4J_PASSWORD", "")
        self._driver = None

    def configured(self) -> bool:
        return bool(self.uri and self.password)

    def driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as e:
                raise ImportError(
                    "pip install neo4j to use the Neo4j backend") from e
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    # ---- write ----------------------------------------------------------
    def push(self, graph: ServiceGraph, wipe: bool = False) -> dict:
        """Mirror a ServiceGraph into Neo4j. Idempotent via MERGE."""
        spec = graph.to_dict()
        with self.driver().session() as s:
            if wipe:
                s.run(f"MATCH (n:{LABEL}) DETACH DELETE n")
            for svc in spec["services"]:
                s.run(
                    f"MERGE (n:{LABEL} {{name: $name}}) "
                    "SET n.kind = $kind, n.tier = $tier, n.owner = $owner",
                    name=svc["name"], kind=svc.get("kind", "service"),
                    tier=svc.get("tier", "important"), owner=svc.get("owner", ""))
            for dep in spec["dependencies"]:
                s.run(
                    f"MATCH (a:{LABEL} {{name: $f}}), (b:{LABEL} {{name: $t}}) "
                    f"MERGE (a)-[r:{REL}]->(b) SET r.dep_type = $ty",
                    f=dep["from"], t=dep["to"], ty=dep.get("type", "sync"))
        return {"services": len(spec["services"]),
                "dependencies": len(spec["dependencies"])}

    # ---- read -----------------------------------------------------------
    def pull(self) -> ServiceGraph:
        """Read the topology out of Neo4j into a ServiceGraph."""
        g = ServiceGraph()
        with self.driver().session() as s:
            for rec in s.run(
                    f"MATCH (n:{LABEL}) RETURN n.name AS name, n.kind AS kind, "
                    "n.tier AS tier, n.owner AS owner"):
                g.add_service(rec["name"], kind=rec["kind"] or "service",
                              tier=rec["tier"] or "important",
                              owner=rec["owner"] or "")
            for rec in s.run(
                    f"MATCH (a:{LABEL})-[r:{REL}]->(b:{LABEL}) "
                    "RETURN a.name AS f, b.name AS t, r.dep_type AS ty"):
                g.add_dependency(rec["f"], rec["t"], rec["ty"] or "sync")
        return g

    def blast_radius(self, service: str, max_hops: int = 6) -> list[dict]:
        """Blast radius in Cypher, for when the graph is too large to pull."""
        q = (f"MATCH path = (caller:{LABEL})-[:{REL}*1..{max_hops}]->"
             f"(target:{LABEL} {{name: $name}}) "
             "RETURN DISTINCT caller.name AS service, caller.tier AS tier, "
             "min(length(path)) AS hops ORDER BY hops, service")
        with self.driver().session() as s:
            return [dict(r) for r in s.run(q, name=service)]
