"""Causal analysis engine (feature 4).

Builds a cause-effect graph from live signals, service topology, known failure
mechanisms and retrieved precedent, then ranks root-cause hypotheses using
supporting *and* contradicting evidence - so a cause ordered after its own
symptom is demoted rather than reported confidently.

    from causal import analyse_causally
    res = analyse_causally(text, signals=signals, service_graph=g, neighbours=nb)
"""
from .engine import analyse_causally, build_graph, separate_symptoms
from .hypothesis import Evidence, Hypothesis, collect_evidence, rank
from .model import (BASIS_COOCCURRENCE, BASIS_MECHANISM, BASIS_PRECEDENT,
                    BASIS_TEMPORAL, BASIS_TOPOLOGY, NODE_CHANGE,
                    NODE_CONDITION, NODE_MECHANISM, NODE_SYMPTOM, CausalEdge,
                    CausalGraph, CausalNode)
from .rules import MECHANISMS, apply_mechanism_rules, apply_signal_rules

__all__ = ["analyse_causally", "build_graph", "separate_symptoms",
           "CausalGraph", "CausalNode", "CausalEdge", "Hypothesis", "Evidence",
           "rank", "collect_evidence", "MECHANISMS", "apply_mechanism_rules",
           "apply_signal_rules", "NODE_CHANGE", "NODE_MECHANISM",
           "NODE_SYMPTOM", "NODE_CONDITION", "BASIS_TEMPORAL",
           "BASIS_TOPOLOGY", "BASIS_PRECEDENT", "BASIS_MECHANISM",
           "BASIS_COOCCURRENCE"]
