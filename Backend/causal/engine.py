"""Causal analysis engine (feature 4): build the graph, then rank hypotheses.

    from causal import analyse_causally

    result = analyse_causally(
        text="Checkout 500s after the 13:00 release",
        signals=signals,              # from observability
        service_graph=graph,          # from graph
        neighbours=[(id, root_cause)] # from retrieval
    )
    result["hypotheses"][0]["cause"]
    result["graph"]["symptoms"]

Everything here is deterministic. The LLM is not asked to invent causality;
it is given this graph as evidence and asked to critique or extend it, so its
claims can be checked against a structure built from the observations.
"""
from __future__ import annotations

from .hypothesis import Hypothesis, rank, render as render_hypotheses
from .model import CausalGraph
from .rules import (apply_mechanism_rules, apply_precedent_rules,
                    apply_signal_rules)


def build_graph(text: str = "", signals=None, service_graph=None,
                neighbours: list[tuple[str, str]] | None = None) -> CausalGraph:
    """Assemble a causal graph from every available source of structure."""
    graph = CausalGraph()
    if text:
        apply_mechanism_rules(graph, text)
    if neighbours:
        apply_precedent_rules(graph, neighbours)
    if signals:
        apply_signal_rules(graph, signals, service_graph)
    return graph


def analyse_causally(text: str = "", signals=None, service_graph=None,
                     neighbours: list[tuple[str, str]] | None = None,
                     limit: int = 5) -> dict:
    """Build the causal graph and rank root-cause hypotheses over it."""
    graph = build_graph(text, signals, service_graph, neighbours)
    hypotheses: list[Hypothesis] = rank(graph, limit=limit)

    symptoms = graph.symptoms()
    roots = graph.root_candidates()
    top = hypotheses[0] if hypotheses else None

    # Which observed symptoms no hypothesis accounts for - the honest gap.
    explained = set()
    for h in hypotheses:
        explained |= set(h.explains)
    unexplained = [graph.nodes[s.id].label for s in symptoms
                   if s.id not in explained]

    return {
        "graph": graph.to_dict(),
        "graph_text": graph.render(),
        "hypotheses": [h.to_dict() for h in hypotheses],
        "hypotheses_text": render_hypotheses(hypotheses),
        "top_cause": top.cause if top else None,
        "top_likelihood": top.likelihood if top else 0.0,
        "symptom_count": len(symptoms),
        "root_candidate_count": len(roots),
        "unexplained_symptoms": unexplained,
        "summary": _summary(hypotheses, symptoms, unexplained),
    }


def _summary(hypotheses, symptoms, unexplained) -> str:
    if not hypotheses:
        return ("No causal structure could be established from the available "
                "evidence; the analysis rests on the text description alone.")
    top = hypotheses[0]
    bits = [f"Most likely root cause ({top.likelihood:.0%}): {top.cause}"]
    if top.explains:
        bits.append(f"it accounts for {len(top.explains)} of {len(symptoms)} observed symptoms")
    if top.contradictions:
        bits.append(f"{len(top.contradictions)} contradiction(s) noted")
    runner = hypotheses[1] if len(hypotheses) > 1 else None
    if runner and runner.likelihood > 0 and top.likelihood - runner.likelihood < 0.1:
        bits.append(f"close alternative: {runner.cause}")
    if unexplained:
        bits.append(f"{len(unexplained)} symptom(s) remain unexplained")
    return ". ".join(bits) + "."


def separate_symptoms(result: dict) -> dict:
    """Split the graph's nodes into causes and symptoms, for display."""
    nodes = {n["id"]: n for n in result["graph"]["nodes"]}
    return {
        "root_causes": [nodes[i]["label"] for i in result["graph"]["root_candidates"]
                        if i in nodes],
        "symptoms": [nodes[i]["label"] for i in result["graph"]["symptoms"]
                     if i in nodes],
    }
