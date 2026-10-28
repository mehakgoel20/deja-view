"""Run the 50 hand-written test queries in data/test_queries.json.

    python -m rag.batch                       # RAG on all 50
    python -m rag.batch --mode both           # RAG and LLM-only
    python -m rag.batch --only 1 9 28         # just these query numbers

Results go to data/eval/batch_<model>.jsonl (one line per query and engine)
and a summary table is printed. `expected` in the query file is a best-guess
category, not ground truth: these queries are not from the dataset.
"""
import argparse
import json
from collections import defaultdict

from .config import DATA_DIR, EVAL_DIR, LLM_MODEL
from .engine import Engine
from .evaluate import MODEL_TAG

QUERIES_PATH = DATA_DIR / "test_queries.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rag", "llm", "both"], default="rag")
    parser.add_argument("--only", type=int, nargs="+", help="query numbers to run")
    args = parser.parse_args()

    queries = json.loads(QUERIES_PATH.read_text())
    if args.only:
        queries = [q for q in queries if q["n"] in args.only]
    engines = {"rag": ["RAG"], "llm": ["LLM-only"], "both": ["RAG", "LLM-only"]}[args.mode]
    engine = Engine("full")
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"batch_{MODEL_TAG}.jsonl"
    hits = defaultdict(int)

    print(f"model {LLM_MODEL}, {len(queries)} queries -> {out_path}\n")
    print(f"{'#':>3} {'engine':8} {'expected':27} {'predicted':27} {'ok':2} {'sec':>5}  top cause")
    with out_path.open("a") as out:
        for q in queries:
            for name in engines:
                result = engine.run(q["query"], use_context=(name == "RAG"))
                a = result["analysis"]
                ok = a["category"] == q["expected"]
                hits[name] += ok
                top = a["hypotheses"][0]["cause"] if a["hypotheses"] else "-"
                print(f"{q['n']:>3} {name:8} {q['expected']:27} {a['category']:27} "
                      f"{'✓' if ok else '✗':2} {result['timing_s']['total']:>5}  {top[:70]}")
                out.write(json.dumps({
                    **q, "engine": name, "model": LLM_MODEL, "mode": result["mode"],
                    "predicted": a["category"], "severity": a["severity"], "match": ok,
                    "hypotheses": a["hypotheses"], "fix_steps": a["fix_steps"],
                    "similar_ids": [s["id"] for s in result["similar_incidents"]],
                    "latency_s": result["timing_s"]["total"],
                }, ensure_ascii=False) + "\n")
                out.flush()
    print()
    for name in engines:
        print(f"{name}: category matches expected on {hits[name]}/{len(queries)}")


if __name__ == "__main__":
    main()
