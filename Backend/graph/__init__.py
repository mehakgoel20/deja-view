"""Service dependency graph (feature 3).

    from graph import ServiceGraph

    g = ServiceGraph.from_dict({
        "api-gateway": ["auth-service"],
        "auth-service": ["postgres", {"to": "redis", "type": "cache"}],
    })
    g.blast_radius("redis")["summary"]
    g.rank_suspects(["api-gateway", "auth-service"])

Backed by NetworkX. Point RCA_TOPOLOGY_PATH at a YAML or JSON topology, or
drop Backend/data/topology.yaml in place, and `load_default_graph()` picks it
up. Neo4j is supported through the same interface for teams already running
it - see neo4j_store.py.
"""
from .service_graph import (EDGE_WEIGHTS, TIER_BEST_EFFORT, TIER_CRITICAL,
                            TIER_IMPORTANT, Service, ServiceGraph,
                            default_topology_path, load_default_graph)

__all__ = ["ServiceGraph", "Service", "EDGE_WEIGHTS", "TIER_CRITICAL",
           "TIER_IMPORTANT", "TIER_BEST_EFFORT", "load_default_graph",
           "default_topology_path"]
