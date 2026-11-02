"""Benchmark runner: basic RAG vs hybrid RAG vs hybrid RAG + multi-agent.

    python -m benchmark.run --limit 50                  # all three pipelines
    python -m benchmark.run --pipelines hybrid,agentic
    python -m benchmark.run --report                     # re-print saved results

The three configurations isolate what each layer actually buys:

| pipeline | retrieval            | rerank | agents |
|----------|----------------------|--------|--------|
| basic    | dense only           | no     | no     |
| hybrid   | dense + BM25 (RRF)   | yes    | no     |
| agentic  | dense + BM25 (RRF)   | yes    | yes    |

Evaluation holds out the test split and, for each incident, excludes the
incident itself from retrieval - otherwise the answer is in the context and
every metric is meaningless.

Heavy imports are deliberately lazy so `benchmark.metrics` stays importable
(and unit-testable) in an environment without faiss or an API key.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .metrics import (citation_metrics, graded_gain, hallucination_rate,
                      latency_report, recommendation_usefulness,
                      retrieval_report, root_cause_accuracy, token_f1)

PIPELINES = ("basic", "hybrid", "agentic")


def _paths():
    from rag.config import EVAL_DIR
    out = Path(EVAL_DIR) / "benchmark"
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_test_entries(limit: int | None = None):
    """Held-out incidents, from the split the RAG pipeline already uses."""
    from rag.config import CLEAN_PATH, SPLIT_PATH
    docs = json.loads(Path(CLEAN_PATH).read_text())
    split = json.loads(Path(SPLIT_PATH).read_text())
    test_ids = set(split["test"])
    entries = [d for d in docs if d["id"] in test_ids]
    entries.sort(key=lambda d: d["id"])
    return entries[:limit] if limit else entries


def _retrieve_for(kb, entry, pipeline: str, k: int = 10):
    """Retrieve neighbours for one entry, excluding the entry itself."""
    from rag.retrieve import diversify, hybrid_candidates, llm_rerank
    from rag.llm import embed

    text = entry["issue"]
    mode = "dense" if pipeline == "basic" else "hybrid"
    rewrite = pipeline != "basic"
    dense_text = text
    lexical = text
    if rewrite:
        from rag.retrieve import rewrite_query
        rw = rewrite_query(text)
        dense_text = rw["symptom"]
        lexical = f"{text} {rw['symptom']} {' '.join(rw['keywords'])}"
    vector = embed([dense_text])[0]
    candidates = hybrid_candidates(kb, vector, lexical, mode=mode)
    # never let the incident retrieve itself
    own_row = kb.by_id.get(entry["id"])
    candidates = [c for c in candidates if c["row"] != own_row]
    if pipeline != "basic" and candidates:
        candidates = llm_rerank(kb, dense_text, candidates)
    return diversify(kb, candidates, k)


def _score_retrieval(kb, entry, neighbours):
    """Relevance flags and graded gains against the held-out truth."""
    truth_cat = entry["category"]
    truth_cause = entry.get("root_cause", "")
    flags, gains, ids = [], [], []
    for c in neighbours:
        d = kb.docs[c["row"]]
        flags.append(d["category"] == truth_cat)
        gains.append(graded_gain(d["category"], truth_cat,
                                 d.get("root_cause", ""), truth_cause))
        ids.append(d["id"])
    # The corpus holds hundreds of same-category incidents, so raw recall over
    # all of them is meaningless for a top-k list. Use the standard capped
    # denominator: min(total relevant, k) is the most any top-k list could find.
    total_relevant = sum(1 for d in kb.docs
                         if d["category"] == truth_cat and d["id"] != entry["id"])
    return {"relevant": flags, "gains": gains, "ids": ids,
            "corpus_relevant": total_relevant,
            "total_relevant": None}


def run_one(engine, kb, entry, pipeline: str):
    """Evaluate one incident through one pipeline."""
    t0 = time.time()
    neighbours = _retrieve_for(kb, entry, pipeline)
    retrieval = _score_retrieval(kb, entry, neighbours)
    allowed = set(retrieval["ids"])
    supporting = {kb.docs[c["row"]]["id"] for c in neighbours
                  if kb.docs[c["row"]]["category"] == entry["category"]}

    if pipeline == "agentic":
        from agents import investigate
        from rag.predict import vote
        described = [engine._describe(c) for c in neighbours]
        report = investigate(entry["issue"], neighbours=described,
                             collect_live=False, remediate=True)
        hyps = report.get("hypotheses", [])
        predicted = hyps[0]["statement"] if hyps else ""
        cited = [i for h in hyps for i in h.get("evidence_ids", [])]
        fixes = [a["action"] for a in
                 (report.get("remediation") or {}).get("actions", [])]
        uncited = sum(1 for h in hyps if not h.get("evidence_ids"))
        # The agents reason about mechanism, not taxonomy, so take the category
        # from the same neighbour vote the other pipelines use. Without this the
        # comparison could not report category accuracy for this pipeline.
        pred_category = vote(kb, neighbours)["category"]
    else:
        from rag.predict import vote
        baseline = vote(kb, neighbours)
        from rag.analyze import analyze
        analysis, validation = analyze(kb, entry["issue"], neighbours, baseline)
        predicted = (analysis["hypotheses"][0]["cause"]
                     if analysis["hypotheses"] else "")
        cited = [i for h in analysis["hypotheses"] for i in h["evidence_ids"]]
        fixes = analysis.get("fix_steps", [])
        pred_category = analysis.get("category")
        uncited = sum(1 for h in analysis["hypotheses"] if not h["evidence_ids"])

    citations = citation_metrics(cited, allowed, supporting)
    return {
        "id": entry["id"],
        "pipeline": pipeline,
        "truth_category": entry["category"],
        "predicted_category": pred_category,
        "category_correct": pred_category == entry["category"] if pred_category else None,
        "root_cause_correct": root_cause_accuracy(predicted, entry.get("root_cause", "")),
        "root_cause_f1": token_f1(predicted, entry.get("root_cause", "")),
        "predicted_cause": predicted[:300],
        "citations": citations,
        "claims_without_citation": uncited,
        "recommendation": recommendation_usefulness(fixes, entry.get("solution") or ""),
        "retrieval": retrieval,
        "latency_s": round(time.time() - t0, 3),
    }


def aggregate(runs: list[dict]) -> dict:
    """Roll per-incident runs up into one scorecard."""
    if not runs:
        return {}
    n = len(runs)
    cat = [r for r in runs if r.get("category_correct") is not None]
    rec_hits = sum(1 for r in runs if r["recommendation"]["hit"])
    return {
        "incidents": n,
        "retrieval": retrieval_report([r["retrieval"] for r in runs]),
        "root_cause_accuracy": round(
            sum(1 for r in runs if r["root_cause_correct"]) / n, 4),
        "root_cause_f1_mean": round(sum(r["root_cause_f1"] for r in runs) / n, 4),
        "category_accuracy": (round(sum(1 for r in cat if r["category_correct"]) / len(cat), 4)
                              if cat else None),
        "citation": {
            "mean_precision": round(
                sum(r["citations"]["precision"] for r in runs) / n, 4),
            "answers_with_invented_id": sum(
                1 for r in runs if r["citations"]["has_invented"]),
            "mean_supporting_citations": round(
                sum(r["citations"]["supporting"] for r in runs) / n, 4),
        },
        **{"hallucination": hallucination_rate(runs)},
        "recommendation": {
            "hit_rate": round(rec_hits / n, 4),
            "best_f1_mean": round(
                sum(r["recommendation"]["best_f1"] for r in runs) / n, 4),
        },
        "latency": latency_report([r["latency_s"] for r in runs]),
    }


def compare(results: dict) -> dict:
    """Side-by-side table of the pipelines on the headline metrics."""
    rows = []
    for name in PIPELINES:
        agg = results.get(name)
        if not agg:
            continue
        rows.append({
            "pipeline": name,
            "incidents": agg["incidents"],
            "recall@5": agg["retrieval"].get("recall_at_5"),
            "precision@5": agg["retrieval"].get("precision_at_5"),
            "mrr": agg["retrieval"].get("mrr"),
            "ndcg@5": agg["retrieval"].get("ndcg_at_5"),
            "root_cause_acc": agg["root_cause_accuracy"],
            "citation_precision": agg["citation"]["mean_precision"],
            "hallucination_rate": agg["hallucination"].get("hallucination_rate"),
            "recommendation_hit": agg["recommendation"]["hit_rate"],
            "p95_latency_s": agg["latency"].get("p95_s"),
        })
    return {"table": rows, "metric_notes": {
        "relevance": "a retrieved incident counts as relevant when its category "
                     "matches the held-out incident's",
        "root_cause_acc": "token-F1 >= 0.30 against the published cause, so "
                          "paraphrase counts as correct",
        "hallucination_rate": "share of answers with an invented citation or an "
                              "uncited hypothesis",
    }}


def render(results: dict) -> str:
    cmp = compare(results)
    rows = cmp["table"]
    if not rows:
        return "No benchmark results."
    cols = ["pipeline", "incidents", "recall@5", "precision@5", "mrr", "ndcg@5",
            "root_cause_acc", "citation_precision", "hallucination_rate",
            "recommendation_hit", "p95_latency_s"]
    width = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    head = "  ".join(c.ljust(width[c]) for c in cols)
    sep = "  ".join("-" * width[c] for c in cols)
    body = "\n".join("  ".join(str(r.get(c, "")).ljust(width[c]) for c in cols)
                     for r in rows)
    return f"{head}\n{sep}\n{body}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=50,
                    help="held-out incidents to evaluate (default 50)")
    ap.add_argument("--pipelines", default=",".join(PIPELINES))
    ap.add_argument("--report", action="store_true",
                    help="print the saved results without re-running")
    args = ap.parse_args()
    out_dir = _paths()
    results_path = out_dir / "results.json"

    if args.report:
        if not results_path.exists():
            raise SystemExit("no saved results; run without --report first")
        saved = json.loads(results_path.read_text())
        print(render(saved["aggregate"]))
        return

    from rag.engine import Engine
    engine = Engine("full")
    kb = engine.kb
    entries = load_test_entries(args.limit)
    wanted = [p for p in args.pipelines.split(",") if p in PIPELINES]
    print(f"{len(entries)} held-out incidents x {len(wanted)} pipeline(s)")

    all_runs: dict[str, list[dict]] = {}
    aggregate_out: dict[str, dict] = {}
    for pipeline in wanted:
        runs = []
        t0 = time.time()
        for i, entry in enumerate(entries, 1):
            try:
                runs.append(run_one(engine, kb, entry, pipeline))
            except Exception as e:
                print(f"  {entry['id']} failed: {type(e).__name__}: {e}")
            if i % 10 == 0:
                print(f"  {pipeline}: {i}/{len(entries)}")
        all_runs[pipeline] = runs
        aggregate_out[pipeline] = aggregate(runs)
        print(f"  {pipeline} done in {time.time() - t0:.0f}s")

    payload = {"aggregate": aggregate_out, "runs": all_runs,
               "comparison": compare(aggregate_out)}
    results_path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {results_path}\n")
    print(render(aggregate_out))


if __name__ == "__main__":
    main()
