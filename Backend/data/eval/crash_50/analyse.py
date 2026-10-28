"""Summarise runs.jsonl into report.json: RAG vs LLM-only on the 50 outage incidents.

    cd Backend && python data/eval/crash_50/analyse.py
"""
import json
import statistics
import sys
from collections import Counter
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rag.config import CLEAN_PATH, SEVERITIES  # noqa: E402

HERE = Path(__file__).resolve().parent
runs = [json.loads(line) for line in (HERE / "runs.jsonl").read_text().splitlines() if line]
entries = {e["id"]: e for e in json.loads(CLEAN_PATH.read_text())}
n = len(runs)
pct = lambda k, total=None: round(100 * k / (total or n), 1)


def sign_test(wins, losses):
    """Two-sided exact sign test on the pairs that differ."""
    m = wins + losses
    if m == 0:
        return 1.0
    k = min(wins, losses)
    return round(min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m), 3)


def root_cause(side):
    top1 = [r[side]["judge"]["scores"][0] if r[side]["judge"]["scores"] else 0 for r in runs]
    best = [max(r[side]["judge"]["scores"]) if r[side]["judge"]["scores"] else 0 for r in runs]
    return {
        "top1_exact_pct": pct(sum(s == 2 for s in top1)),
        "top1_partial_or_better_pct": pct(sum(s >= 1 for s in top1)),
        "top1_wrong_pct": pct(sum(s == 0 for s in top1)),
        "any_of_3_exact_pct": pct(sum(s == 2 for s in best)),
        "any_of_3_partial_or_better_pct": pct(sum(s >= 1 for s in best)),
        "mean_top1_score_of_2": round(sum(top1) / n, 2),
    }, top1, best


rag_rc, rag_top1, rag_best = root_cause("rag")
llm_rc, llm_top1, llm_best = root_cause("llm_only")


def paired(a, b):
    wins = sum(x > y for x, y in zip(a, b))
    losses = sum(x < y for x, y in zip(a, b))
    return {"rag_better": wins, "same": n - wins - losses, "llm_only_better": losses, "sign_test_p": sign_test(wins, losses)}


def classify(side_cat, side_sev):
    idx = {s: i for i, s in enumerate(SEVERITIES)}
    tc = [r["truth"]["category"] for r in runs]
    ts = [r["truth"]["severity"] for r in runs]
    return {
        "category_accuracy_pct": pct(sum(t == p for t, p in zip(tc, side_cat))),
        "severity_accuracy_pct": pct(sum(t == p for t, p in zip(ts, side_sev))),
        "severity_within_one_pct": pct(sum(p in idx and abs(idx[t] - idx[p]) <= 1 for t, p in zip(ts, side_sev))),
    }


# Retrieval
top_rel = [r["rag"]["top_relevance"] for r in runs]
same_org_any = [r["org"] in r["rag"]["neighbour_orgs"] for r in runs]
same_org_top = [bool(r["rag"]["neighbour_orgs"]) and r["rag"]["neighbour_orgs"][0] == r["org"] for r in runs]
cat_hit = [r["truth"]["category"] in r["rag"]["neighbour_categories"] for r in runs]


def bucket(lo, hi):
    idx = [i for i, r in enumerate(runs) if r["rag"]["top_relevance"] is not None and lo <= r["rag"]["top_relevance"] <= hi]
    if not idx:
        return None
    return {
        "n": len(idx),
        "rag_top1_exact_pct": pct(sum(rag_top1[i] == 2 for i in idx), len(idx)),
        "llm_only_top1_exact_pct": pct(sum(llm_top1[i] == 2 for i in idx), len(idx)),
        "rag_top1_partial_or_better_pct": pct(sum(rag_top1[i] >= 1 for i in idx), len(idx)),
        "llm_only_top1_partial_or_better_pct": pct(sum(llm_top1[i] >= 1 for i in idx), len(idx)),
    }


def split_by(flags):
    out = {}
    for name, want in (("yes", True), ("no", False)):
        idx = [i for i, f in enumerate(flags) if f == want]
        if idx:
            out[name] = {"n": len(idx),
                         "rag_top1_exact_pct": pct(sum(rag_top1[i] == 2 for i in idx), len(idx)),
                         "llm_only_top1_exact_pct": pct(sum(llm_top1[i] == 2 for i in idx), len(idx)),
                         "rag_top1_partial_or_better_pct": pct(sum(rag_top1[i] >= 1 for i in idx), len(idx)),
                         "llm_only_top1_partial_or_better_pct": pct(sum(llm_top1[i] >= 1 for i in idx), len(idx))}
    return out


# Is the stated likelihood of the top hypothesis a usable confidence?
def calibration(side):
    out = {}
    for lo, hi in ((0, 0.5), (0.5, 0.7), (0.7, 1.01)):
        idx = [i for i, r in enumerate(runs) if r[side]["hypotheses"] and lo <= r[side]["hypotheses"][0]["likelihood"] < hi]
        scores = rag_top1 if side == "rag" else llm_top1
        if idx:
            out[f"{lo:.1f}-{min(hi, 1):.1f}"] = {"n": len(idx), "top1_exact_pct": pct(sum(scores[i] == 2 for i in idx), len(idx)),
                                                  "top1_partial_or_better_pct": pct(sum(scores[i] >= 1 for i in idx), len(idx))}
    return out


hyps = [h for r in runs for h in r["rag"]["hypotheses"]]
cited_top = [bool(r["rag"]["hypotheses"] and r["rag"]["hypotheses"][0]["evidence_ids"]) for r in runs]
rag_lat = sorted(r["rag"]["latency_s"] for r in runs)
llm_lat = sorted(r["llm_only"]["latency_s"] for r in runs)
q = lambda xs, f: round(xs[int(f * (len(xs) - 1))], 1)

report = {
    "n": n,
    "selection": "held-out test split; Critical or High; clear published cause; outage or crash wording; not in the earlier 100",
    "severity_mix": dict(Counter(r["truth"]["severity"] for r in runs)),
    "category_mix": dict(Counter(r["truth"]["category"] for r in runs).most_common()),
    "organisations": len({r["org"] for r in runs}),
    "root_cause": {"rag": rag_rc, "llm_only": llm_rc,
                   "paired_top1": paired(rag_top1, llm_top1), "paired_any_of_3": paired(rag_best, llm_best)},
    "classification": {
        "rag": classify([r["rag"]["category"] for r in runs], [r["rag"]["severity"] for r in runs]),
        "llm_only": classify([r["llm_only"]["category"] for r in runs], [r["llm_only"]["severity"] for r in runs]),
        "knn_vote": classify([r["rag"]["baseline"]["category"] for r in runs], [r["rag"]["baseline"]["severity"] for r in runs]),
    },
    "retrieval": {
        "mode_counts": dict(Counter(r["rag"]["mode"] for r in runs)),
        "top_relevance_distribution": dict(sorted(Counter(top_rel).items(), key=lambda kv: -1 if kv[0] is None else kv[0])),
        "median_top_relevance": statistics.median(x for x in top_rel if x is not None),
        "true_category_among_5_pct": pct(sum(cat_hit)),
        "same_org_among_5_pct": pct(sum(same_org_any)),
        "same_org_is_top_match_pct": pct(sum(same_org_top)),
    },
    "by_top_relevance": {name: b for name, (lo, hi) in {"0-3 (gated, no context)": (0, 3), "4-6": (4, 6), "7-8": (7, 8), "9-10": (9, 10)}.items() if (b := bucket(lo, hi))},
    "by_same_org_precedent_retrieved": split_by(same_org_any),
    "by_true_category_retrieved": split_by(cat_hit),
    "confidence_calibration_top_hypothesis": {"rag": calibration("rag"), "llm_only": calibration("llm_only")},
    "grounding": {
        "hypotheses": len(hyps),
        "hypotheses_citing_an_incident_pct": pct(sum(bool(h["evidence_ids"]) for h in hyps), len(hyps)),
        "top_hypothesis_cites_an_incident_pct": pct(sum(cited_top)),
        "invalid_citations_dropped": sum(len(r["rag"]["dropped_citations"]) for r in runs),
        "top1_exact_pct_when_top_cited": pct(sum(rag_top1[i] == 2 for i, c in enumerate(cited_top) if c), max(1, sum(cited_top))),
    },
    "latency_s": {"rag": {"median": q(rag_lat, 0.5), "p90": q(rag_lat, 0.9), "max": rag_lat[-1]},
                  "rag_retrieval_share_median": round(statistics.median(r["rag"]["retrieve_s"] / r["rag"]["latency_s"] for r in runs), 2),
                  "llm_only": {"median": q(llm_lat, 0.5), "p90": q(llm_lat, 0.9), "max": llm_lat[-1]}},
    "examples": {
        "rag_better": [r["id"] for r, a, b in zip(runs, rag_top1, llm_top1) if a > b],
        "llm_only_better": [r["id"] for r, a, b in zip(runs, rag_top1, llm_top1) if a < b],
        "both_wrong": [r["id"] for r, a, b in zip(runs, rag_top1, llm_top1) if a == 0 and b == 0],
    },
}
(HERE / "report.json").write_text(json.dumps(report, indent=1))
print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=1))
print("examples:", {k: len(v) for k, v in report["examples"].items()})
