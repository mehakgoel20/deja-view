"""Step 8: evaluate on the held-out split.

    python -m rag.evaluate tune        # leave-one-out on train: pick the vote's alpha (no LLM)
    python -m rag.evaluate retrieval   # test set: dense vs BM25 vs hybrid (no LLM)
    python -m rag.evaluate full        # test set: full RAG pipeline vs LLM-only, judged by LLM
    python -m rag.evaluate report      # aggregate into data/eval/report_<model>.json
    python -m rag.evaluate all
    python -m rag.evaluate full --sample 10 --workers 1      # same 10 incidents for every model
    python -m rag.evaluate compare --models gpt-4.1-mini qwen3-8b

`full` appends to data/eval/runs_<model>.jsonl and skips ids already there, so it can
be interrupted and resumed.
"""
import argparse
import json
import random
import statistics
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from pathlib import Path

import numpy as np

from .analyze import analyze
from .config import (CATEGORIES, CLEAN_PATH, EMB_META_PATH, EMB_PATH, EVAL_DIR, LLM_MODEL,
                     SEVERITIES, SPLIT_PATH, SPLIT_SEED)
from .engine import GATE_RELEVANCE, Engine
from .kb import KnowledgeBase
from .llm import chat_json
from .predict import DEFAULT_ALPHA, vote
from .retrieve import PER_ORG_CAP, diversify, hybrid_candidates

JUDGE_MODEL = "gpt-4.1"
ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0]
# One results file per model under test, so runs can be compared side by side.
MODEL_TAG = LLM_MODEL.replace("/", "_").replace(":", "-")
RUNS_PATH = EVAL_DIR / f"runs_{MODEL_TAG}.jsonl"
REPORT_PATH = EVAL_DIR / f"report_{MODEL_TAG}.json"


# ---------------------------------------------------------------- metrics

def accuracy(truth, pred):
    return sum(t == p for t, p in zip(truth, pred)) / len(truth) if truth else 0.0


def macro_f1(truth, pred, labels):
    f1s = []
    for label in labels:
        if label not in truth:
            continue
        tp = sum(t == p == label for t, p in zip(truth, pred))
        fp = sum(p == label and t != label for t, p in zip(truth, pred))
        fn = sum(t == label and p != label for t, p in zip(truth, pred))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def per_class_recall(truth, pred, labels):
    out = {}
    for label in labels:
        n = sum(t == label for t in truth)
        if n:
            out[label] = {"n": n, "recall": round(sum(t == p == label for t, p in zip(truth, pred)) / n, 3)}
    return out


def within_one(truth, pred):
    idx = {s: i for i, s in enumerate(SEVERITIES)}
    pairs = [(t, p) for t, p in zip(truth, pred) if p in idx]
    return sum(abs(idx[t] - idx[p]) <= 1 for t, p in pairs) / len(truth) if truth else 0.0


def classification_metrics(truth_cat, pred_cat, truth_sev, pred_sev):
    return {
        "category_accuracy": round(accuracy(truth_cat, pred_cat), 3),
        "category_macro_f1": round(macro_f1(truth_cat, pred_cat, CATEGORIES), 3),
        "severity_accuracy": round(accuracy(truth_sev, pred_sev), 3),
        "severity_within_one": round(within_one(truth_sev, pred_sev), 3),
    }


def retrieval_metrics(truth_cat, neighbour_cats):
    hit = [t in cats for t, cats in zip(truth_cat, neighbour_cats)]
    precision = [sum(c == t for c in cats) / len(cats) if cats else 0
                 for t, cats in zip(truth_cat, neighbour_cats)]
    top1 = [bool(cats) and cats[0] == t for t, cats in zip(truth_cat, neighbour_cats)]
    return {"category_hit_at_5": round(sum(hit) / len(hit), 3),
            "category_precision_at_5": round(sum(precision) / len(precision), 3),
            "top1_same_category": round(sum(top1) / len(top1), 3)}


# ---------------------------------------------------------------- data

def load_eval_data():
    entries = {e["id"]: e for e in json.loads(CLEAN_PATH.read_text())}
    split = json.loads(SPLIT_PATH.read_text())
    meta = json.loads(EMB_META_PATH.read_text())
    vectors = np.load(EMB_PATH)
    vector_of = {i: vectors[r] for r, i in enumerate(meta["ids"])}
    return entries, split, vector_of


def local_neighbours(kb, text, vector, mode, exclude_row=None, k=5):
    candidates = hybrid_candidates(kb, vector, text, mode=mode)
    candidates = [c for c in candidates if c["row"] != exclude_row]
    return diversify(kb, candidates, k)


# ---------------------------------------------------------------- tune

def cmd_tune():
    """Leave-one-out over the training index: each train incident queries the rest."""
    entries, split, vector_of = load_eval_data()
    kb = KnowledgeBase("train")
    truth_cat, truth_sev, neighbour_sets = [], [], []
    for row, doc in enumerate(kb.docs):
        neighbours = local_neighbours(kb, doc["issue"], vector_of[doc["id"]], "hybrid", exclude_row=row)
        neighbour_sets.append(neighbours)
        truth_cat.append(doc["category"])
        truth_sev.append(doc["severity"])
    results = {}
    for alpha in ALPHAS:
        votes = [vote(kb, n, alpha) for n in neighbour_sets]
        results[str(alpha)] = classification_metrics(
            truth_cat, [v["category"] for v in votes], truth_sev, [v["severity"] for v in votes])
    best = max(ALPHAS, key=lambda a: results[str(a)]["category_macro_f1"])
    out = {"n": len(kb.docs), "by_alpha": results, "best_alpha": best}
    (EVAL_DIR / "tune.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


def tuned_alpha():
    path = EVAL_DIR / "tune.json"
    return json.loads(path.read_text())["best_alpha"] if path.exists() else DEFAULT_ALPHA


# ---------------------------------------------------------------- retrieval

def cmd_retrieval():
    entries, split, vector_of = load_eval_data()
    kb = KnowledgeBase("train")
    alpha = tuned_alpha()
    tests = [entries[i] for i in split["test"]]
    truth_cat = [e["category"] for e in tests]
    truth_sev = [e["severity"] for e in tests]
    out = {"n": len(tests), "alpha": alpha}
    for mode in ("dense", "bm25", "hybrid"):
        sets = [local_neighbours(kb, e["issue"], vector_of[e["id"]], mode) for e in tests]
        cats = [[kb.docs[c["row"]]["category"] for c in s] for s in sets]
        votes = [vote(kb, s, alpha) for s in sets]
        out[mode] = {
            **retrieval_metrics(truth_cat, cats),
            "knn_vote": classification_metrics(truth_cat, [v["category"] for v in votes],
                                               truth_sev, [v["severity"] for v in votes]),
        }
    # Near-duplicate check: how close is each test incident to its nearest train incident?
    top_cos = [kb.dense_search(vector_of[e["id"]], 1)[0][1] for e in tests]
    out["nearest_train_cosine"] = {
        "median": round(statistics.median(top_cos), 3),
        "max": round(max(top_cos), 3),
        "count_above_0.9": sum(c > 0.9 for c in top_cos),
    }
    (EVAL_DIR / "retrieval.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


# ---------------------------------------------------------------- full

_JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scores", "reason"],
    "properties": {"scores": {"type": "array", "items": {"type": "integer"}},
                   "reason": {"type": "string"}},
}
_JUDGE_SYSTEM = """You grade root-cause hypotheses against the published root cause of a real incident.
Score each hypothesis, in the order given:
2 = names the same mechanism (same failing component and same kind of failure),
1 = partially right (right component or right kind of failure, but not both; or correct but
    too generic to act on),
0 = wrong or unrelated.
Return one integer per hypothesis and a one-sentence reason."""


def judge(entry, hypotheses):
    if not hypotheses:
        return {"scores": [], "reason": "no hypotheses"}
    lines = "\n".join(f"{i + 1}. {h['cause']}" for i, h in enumerate(hypotheses))
    user = (f"INCIDENT SYMPTOM: {entry['issue']}\nPUBLISHED ROOT CAUSE: {entry['root_cause']}\n"
            f"PUBLISHED FIX (context only): {entry['solution']}\n\nHYPOTHESES:\n{lines}")
    # The judge always runs on OpenAI, whichever model is under test.
    result = chat_json(_JUDGE_SYSTEM, user, _JUDGE_SCHEMA, "judge", model=JUDGE_MODEL,
                       base_url=None, reasoning=None)
    result["scores"] = [max(0, min(2, s)) for s in result["scores"][:len(hypotheses)]]
    return result


def _ids(kb, rows):
    return [kb.docs[r]["id"] for r in rows]


def evaluate_one(engine, entry, vector):
    kb = engine.kb
    rag = engine.run(entry["issue"], query_vector=vector)
    trace = rag["trace"]
    # Reconstruct the top-5 a pipeline without rerank would have used.
    fused = [{"row": r} for r in trace["fused"]]
    no_rerank = [kb.docs[c["row"]]["category"] for c in diversify(kb, fused, 5, PER_ORG_CAP)]
    llm_only, _ = analyze(kb, entry["issue"], [], vote(kb, [], engine.alpha))
    top = rag["similar_incidents"][0]["scores"] if rag["similar_incidents"] else {}
    return {
        "id": entry["id"],
        "truth": {k: entry[k] for k in ("category", "severity", "cause_is_vague")},
        "rag": {
            "mode": rag["mode"],
            "category": rag["analysis"]["category"],
            "severity": rag["analysis"]["severity"],
            "category_confidence": rag["analysis"]["category_confidence"],
            "hypotheses": rag["analysis"]["hypotheses"],
            "baseline": {k: rag["baseline"][k] for k in ("category", "severity")},
            "neighbour_ids": [s["id"] for s in rag["similar_incidents"]],
            "neighbour_categories": [s["category"] for s in rag["similar_incidents"]],
            "no_rerank_categories": no_rerank,
            "top_relevance": top.get("relevance"),
            "top_cosine": top.get("cosine"),
            "rewrite": trace.get("rewrite"),
            "dropped_citations": rag["validation"]["dropped_citations"],
            "latency_s": rag["timing_s"]["total"],
            "judge": judge(entry, rag["analysis"]["hypotheses"]),
        },
        "llm_only": {
            "category": llm_only["category"],
            "severity": llm_only["severity"],
            "hypotheses": llm_only["hypotheses"],
            "judge": judge(entry, llm_only["hypotheses"]),
        },
    }


def sample_ids(test_ids, n):
    """A fixed random sample of the test set, identical for every model."""
    return sorted(random.Random(SPLIT_SEED).sample(sorted(test_ids), n))


def cmd_full(limit=None, workers=8, sample=None):
    entries, split, vector_of = load_eval_data()
    engine = Engine("train", alpha=tuned_alpha())
    done = set()
    if RUNS_PATH.exists():
        done = {json.loads(line)["id"] for line in RUNS_PATH.read_text().splitlines() if line}
    ids = sample_ids(split["test"], sample) if sample else split["test"]
    todo = [i for i in ids if i not in done][:limit]
    print(f"{len(done)} already evaluated, running {len(todo)} with {workers} workers")
    failures = 0
    with ThreadPoolExecutor(workers) as pool, RUNS_PATH.open("a") as out:
        futures = {pool.submit(evaluate_one, engine, entries[i], vector_of[i]): i for i in todo}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                out.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
                out.flush()
            except Exception:
                failures += 1
                print(f"FAILED {futures[future]}\n{traceback.format_exc()}")
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}")
    print(f"done, {failures} failures")


# ---------------------------------------------------------------- report

def _rc_metrics(runs, side):
    graded = [r for r in runs if not r["truth"]["cause_is_vague"] and r[side]["judge"]["scores"]]
    top1 = [r[side]["judge"]["scores"][0] for r in graded]
    best = [max(r[side]["judge"]["scores"]) for r in graded]
    return {
        "n_graded": len(graded),
        "top1_exact": round(sum(s == 2 for s in top1) / len(graded), 3),
        "top1_at_least_partial": round(sum(s >= 1 for s in top1) / len(graded), 3),
        "best_of_3_exact": round(sum(s == 2 for s in best) / len(graded), 3),
        "best_of_3_at_least_partial": round(sum(s >= 1 for s in best) / len(graded), 3),
        "mean_top1_score": round(sum(top1) / len(graded), 3),
    }


def _relevance_buckets(runs):
    buckets = [("0-3", 0, 3), ("4-5", 4, 5), ("6-7", 6, 7), ("8-10", 8, 10)]
    out = {}
    for name, lo, hi in buckets:
        rs = [r for r in runs if r["rag"]["top_relevance"] is not None
              and lo <= r["rag"]["top_relevance"] <= hi]
        if not rs:
            continue
        def rc(side):
            graded = [r for r in rs if not r["truth"]["cause_is_vague"] and r[side]["judge"]["scores"]]
            return round(sum(r[side]["judge"]["scores"][0] == 2 for r in graded) / len(graded), 3) if graded else None
        out[name] = {
            "n": len(rs),
            "rag_category_acc": round(accuracy([r["truth"]["category"] for r in rs], [r["rag"]["category"] for r in rs]), 3),
            "llm_only_category_acc": round(accuracy([r["truth"]["category"] for r in rs], [r["llm_only"]["category"] for r in rs]), 3),
            "rag_rc_top1_exact": rc("rag"),
            "llm_only_rc_top1_exact": rc("llm_only"),
        }
    return out


def _calibration(runs):
    bins = [(0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01)]
    out = {}
    for lo, hi in bins:
        rs = [r for r in runs if lo <= r["rag"]["category_confidence"] < hi]
        if rs:
            out[f"{lo:.2f}-{min(hi, 1):.2f}"] = {
                "n": len(rs),
                "accuracy": round(accuracy([r["truth"]["category"] for r in rs], [r["rag"]["category"] for r in rs]), 3),
            }
    return out


def cmd_report():
    runs = [json.loads(line) for line in RUNS_PATH.read_text().splitlines() if line]
    tc = [r["truth"]["category"] for r in runs]
    ts = [r["truth"]["severity"] for r in runs]
    side = lambda key, field: [r[key][field] for r in runs]
    base_cat = [r["rag"]["baseline"]["category"] for r in runs]
    base_sev = [r["rag"]["baseline"]["severity"] for r in runs]
    hyps = [h for r in runs for h in r["rag"]["hypotheses"]]
    latency = sorted(r["rag"]["latency_s"] for r in runs)
    report = {
        "n_test": len(runs),
        "llm_model": LLM_MODEL,
        "judge_model": JUDGE_MODEL,
        "gate_relevance": GATE_RELEVANCE,
        "classification": {
            "knn_vote_baseline": classification_metrics(tc, base_cat, ts, base_sev),
            "llm_only": classification_metrics(tc, side("llm_only", "category"), ts, side("llm_only", "severity")),
            "rag": classification_metrics(tc, side("rag", "category"), ts, side("rag", "severity")),
        },
        "per_class_recall": {
            "knn_vote_baseline": per_class_recall(tc, base_cat, CATEGORIES),
            "llm_only": per_class_recall(tc, side("llm_only", "category"), CATEGORIES),
            "rag": per_class_recall(tc, side("rag", "category"), CATEGORIES),
        },
        "root_cause": {"rag": _rc_metrics(runs, "rag"), "llm_only": _rc_metrics(runs, "llm_only")},
        "retrieval": {
            "hybrid_rewrite_no_rerank": retrieval_metrics(tc, [r["rag"]["no_rerank_categories"] for r in runs]),
            "hybrid_rewrite_rerank": retrieval_metrics(tc, [r["rag"]["neighbour_categories"] for r in runs]),
        },
        "relevance_buckets": _relevance_buckets(runs),
        "category_confidence_calibration": _calibration(runs),
        "grounding": {
            "mode_counts": dict(Counter(r["rag"]["mode"] for r in runs)),
            "hypotheses_total": len(hyps),
            "hypotheses_with_citation": round(sum(bool(h["evidence_ids"]) for h in hyps) / len(hyps), 3),
            "invalid_citations_dropped": sum(len(r["rag"]["dropped_citations"]) for r in runs),
        },
        "latency_s": {"median": round(statistics.median(latency), 2),
                      "p95": round(latency[int(0.95 * (len(latency) - 1))], 2)},
        "confusions_rag": Counter(f"{t} -> {p}" for t, p in zip(tc, side("rag", "category")) if t != p).most_common(10),
    }
    for name in ("tune", "retrieval"):
        path = EVAL_DIR / f"{name}.json"
        if path.exists():
            report[name] = json.loads(path.read_text())
    REPORT_PATH.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


def cmd_compare(tags, eval_dir=EVAL_DIR):
    """Compare models on the incidents every one of them was evaluated on."""
    runs = {}
    for tag in tags:
        path = eval_dir / f"runs_{tag}.jsonl"
        runs[tag] = {r["id"]: r for r in map(json.loads, path.read_text().splitlines()) if r}
    common = sorted(set.intersection(*(set(r) for r in runs.values())))
    rows = {}
    for tag in tags:
        rs = [runs[tag][i] for i in common]
        tc = [r["truth"]["category"] for r in rs]
        ts = [r["truth"]["severity"] for r in rs]
        for side in ("rag", "llm_only"):
            rc = _rc_metrics(rs, side)
            row = {
                "category_acc": round(accuracy(tc, [r[side]["category"] for r in rs]), 3),
                "severity_acc": round(accuracy(ts, [r[side]["severity"] for r in rs]), 3),
                "rc_top1_exact": rc["top1_exact"],
                "rc_top1_partial_or_better": rc["top1_at_least_partial"],
                "rc_best3_exact": rc["best_of_3_exact"],
            }
            if side == "rag":
                row["median_latency_s"] = round(statistics.median(r["rag"]["latency_s"] for r in rs), 1)
            rows[f"{tag} {side}"] = row
    out = {"n_common": len(common), "ids": common, "rows": rows}
    (eval_dir / f"compare_{'_vs_'.join(tags)}.json").write_text(json.dumps(out, indent=1))
    print(f"compared on {len(common)} common incidents")
    cols = list(next(iter(rows.values())).keys())
    print(f"{'':32s}" + "".join(f"{c:>27s}" for c in cols))
    for name, row in rows.items():
        print(f"{name:32s}" + "".join(f"{row.get(c, ''):>27}" for c in cols))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["tune", "retrieval", "full", "report", "compare", "all"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample", type=int, help="evaluate a fixed random sample of N test incidents")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--models", nargs="+", help="model tags for compare, e.g. gpt-4.1-mini qwen3-8b")
    parser.add_argument("--dir", help="results folder for compare (default data/eval)")
    args = parser.parse_args()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    if args.command in ("tune", "all"):
        cmd_tune()
    if args.command in ("retrieval", "all"):
        cmd_retrieval()
    if args.command in ("full", "all"):
        cmd_full(args.limit, args.workers, args.sample)
    if args.command in ("report", "all"):
        cmd_report()
    if args.command == "compare":
        cmd_compare(args.models, Path(args.dir) if args.dir else EVAL_DIR)


if __name__ == "__main__":
    main()
