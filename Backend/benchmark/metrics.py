"""Metrics for RCA evaluation (feature 7). Pure functions, no I/O.

Retrieval is scored with the standard IR measures, which the existing
`rag.evaluate` did not cover: Recall@K, Precision@K, MRR and NDCG. All of
them need a notion of relevance; here a retrieved incident counts as relevant
when it shares the held-out incident's category, the same proxy the project
already used for precision@5. `relevance_fn` lets you swap in a stricter
definition (same mechanism, human labels) without touching the metrics.

Generation is scored on three things that matter more than category accuracy:

* **citation correctness** - are the cited ids real and actually retrieved?
* **hallucination rate** - the share of answers containing at least one
  invented id or an unsupported claim. A fluent answer citing GOLD-9999 is
  worse than no answer.
* **recommendation usefulness** - overlap between proposed fixes and what
  actually resolved the incident, measured by token F1 so paraphrase still
  scores.
"""
from __future__ import annotations

import math
import re


# ---------------------------------------------------------------- retrieval

def recall_at_k(relevant_flags: list[bool], k: int, total_relevant: int | None = None) -> float:
    """Share of relevant items found in the top k.

    `total_relevant` is the number of relevant items that exist in the corpus.
    When it is unknown, fall back to "did we find any", which is Recall@k in
    the single-relevant-item sense.
    """
    if k <= 0:
        return 0.0
    found = sum(1 for r in relevant_flags[:k] if r)
    if total_relevant:
        return min(1.0, found / total_relevant)
    return 1.0 if found else 0.0


def precision_at_k(relevant_flags: list[bool], k: int) -> float:
    if k <= 0:
        return 0.0
    window = relevant_flags[:k]
    if not window:
        return 0.0
    return sum(1 for r in window if r) / len(window)


def reciprocal_rank(relevant_flags: list[bool]) -> float:
    """1/rank of the first relevant item, 0 if none. Mean over queries = MRR."""
    for i, r in enumerate(relevant_flags, start=1):
        if r:
            return 1.0 / i
    return 0.0


def dcg(gains: list[float], k: int | None = None) -> float:
    gains = gains if k is None else gains[:k]
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(gains: list[float], k: int, ideal: list[float] | None = None) -> float:
    """Normalised DCG. `gains` may be graded, not just 0/1."""
    actual = dcg(gains, k)
    best = dcg(sorted(ideal if ideal is not None else gains, reverse=True), k)
    return round(actual / best, 4) if best > 0 else 0.0


def graded_gain(retrieved_category: str, truth_category: str,
                retrieved_cause: str = "", truth_cause: str = "") -> float:
    """Graded relevance: 2 = same category and overlapping mechanism, 1 = same
    category only, 0 = unrelated. Graded gains make NDCG meaningful - binary
    relevance cannot distinguish a good ranking from a lucky one.
    """
    if retrieved_category != truth_category:
        return 0.0
    if retrieved_cause and truth_cause:
        overlap = token_f1(retrieved_cause, truth_cause)
        if overlap >= 0.25:
            return 2.0
    return 1.0


def retrieval_report(runs: list[dict], ks=(1, 3, 5, 10)) -> dict:
    """Aggregate retrieval metrics.

    Each run is {"relevant": [bool, ...], "gains": [float, ...],
    "total_relevant": int|None}.
    """
    if not runs:
        return {}
    out: dict = {"queries": len(runs)}
    for k in ks:
        out[f"recall_at_{k}"] = round(
            sum(recall_at_k(r["relevant"], k, r.get("total_relevant")) for r in runs) / len(runs), 4)
        out[f"precision_at_{k}"] = round(
            sum(precision_at_k(r["relevant"], k) for r in runs) / len(runs), 4)
        out[f"ndcg_at_{k}"] = round(
            sum(ndcg_at_k(r.get("gains") or [1.0 if x else 0.0 for x in r["relevant"]], k)
                for r in runs) / len(runs), 4)
    out["mrr"] = round(sum(reciprocal_rank(r["relevant"]) for r in runs) / len(runs), 4)
    out["queries_with_no_relevant_hit"] = sum(
        1 for r in runs if not any(r["relevant"]))
    return out


# --------------------------------------------------------------- generation

_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("""a an the and or of to in on for with by at from as is are was were be been
being this that these those it its we our us you your they their there here which who what
when where how some any all can could would should will may might not no but if then than
so such into out over under up down after before during while about between also has have
had do does did more most other only own same very just because via per new had's""".split())


def tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower())
            if w not in _STOP and len(w) > 2}


def token_f1(a: str, b: str) -> float:
    """Token-overlap F1. Paraphrase-tolerant, unlike exact match."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    if not overlap:
        return 0.0
    precision = overlap / len(ta)
    recall = overlap / len(tb)
    return round(2 * precision * recall / (precision + recall), 4)


def root_cause_accuracy(predicted: str, truth: str, threshold: float = 0.30) -> bool:
    """Did the prediction name the same mechanism?

    Token F1 against the published cause, with a threshold. Deliberately not
    exact match: "the connection pool was exhausted" and "pool reached its
    ceiling and refused connections" are the same answer.
    """
    return token_f1(predicted, truth) >= threshold


def citation_metrics(cited_ids: list[str], allowed_ids: set[str],
                     supporting_ids: set[str] | None = None) -> dict:
    """Are the cited ids real, and do they support the claim?

    - valid: the id was actually retrieved and shown to the model
    - invented: the id does not exist in the evidence at all (hallucination)
    - supporting: among the ids genuinely relevant to the truth
    """
    if not cited_ids:
        return {"cited": 0, "valid": 0, "invented": 0, "precision": 0.0,
                "supporting": 0, "has_invented": False}
    valid = [i for i in cited_ids if i in allowed_ids]
    invented = [i for i in cited_ids if i not in allowed_ids]
    supporting = ([i for i in valid if i in supporting_ids]
                  if supporting_ids else [])
    return {
        "cited": len(cited_ids),
        "valid": len(valid),
        "invented": len(invented),
        "precision": round(len(valid) / len(cited_ids), 4),
        "supporting": len(supporting),
        "has_invented": bool(invented),
    }


def hallucination_rate(runs: list[dict]) -> dict:
    """Share of answers with an invented citation or an uncited claim.

    Two separate failures, reported separately because they need different
    fixes: invented ids are a grounding failure, uncited claims are a
    discipline failure.
    """
    if not runs:
        return {}
    invented = sum(1 for r in runs if r.get("citations", {}).get("has_invented"))
    uncited = sum(1 for r in runs if r.get("claims_without_citation", 0) > 0)
    either = sum(1 for r in runs
                 if r.get("citations", {}).get("has_invented")
                 or r.get("claims_without_citation", 0) > 0)
    return {
        "answers": len(runs),
        "invented_citation_rate": round(invented / len(runs), 4),
        "uncited_claim_rate": round(uncited / len(runs), 4),
        "hallucination_rate": round(either / len(runs), 4),
    }


def recommendation_usefulness(proposed: list[str], actual_fix: str) -> dict:
    """How close the proposed fixes come to what actually fixed it."""
    if not proposed or not actual_fix:
        return {"best_f1": 0.0, "mean_f1": 0.0, "hit": False, "proposed": len(proposed)}
    scores = [token_f1(p, actual_fix) for p in proposed]
    best = max(scores)
    return {
        "best_f1": round(best, 4),
        "mean_f1": round(sum(scores) / len(scores), 4),
        "hit": best >= 0.25,          # a recognisably similar action was proposed
        "proposed": len(proposed),
    }


def latency_report(samples: list[float]) -> dict:
    """End-to-end latency. p95 matters more than the mean for on-call use."""
    if not samples:
        return {}
    s = sorted(samples)

    def pct(p):
        if not s:
            return 0.0
        idx = min(len(s) - 1, int(p / 100 * len(s)))
        return round(s[idx], 3)

    return {"n": len(s), "mean_s": round(sum(s) / len(s), 3),
            "p50_s": pct(50), "p95_s": pct(95), "max_s": round(s[-1], 3)}
