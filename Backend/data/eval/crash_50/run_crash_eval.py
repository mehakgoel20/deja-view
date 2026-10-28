"""RAG vs LLM-only on 50 held-out production outages and crashes.

    cd Backend && python data/eval/crash_50/run_crash_eval.py

Selection: incidents from the held-out test split (never in the "train" index the
engine searches here) that are Critical or High severity, have a clearly published
cause, describe an outage or crash, and were not among the 100 already evaluated in
data/eval/runs_gpt-4.1-mini.jsonl. A fixed-seed sample of 50 is taken from that pool.

Appends to runs.jsonl next to this file and skips ids already there, so it can be
interrupted and resumed.
"""
import json
import random
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rag.analyze import analyze  # noqa: E402
from rag.config import EVAL_DIR, LLM_MODEL  # noqa: E402
from rag.engine import Engine  # noqa: E402
from rag.evaluate import PER_ORG_CAP, judge, load_eval_data, tuned_alpha  # noqa: E402
from rag.predict import vote  # noqa: E402
from rag.retrieve import diversify  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs.jsonl"
SAMPLE_SIZE = 50
SEED = 2026
CRASH = re.compile(
    r"\b(outage|down\b|downtime|unavailable|unavailability|crash|crashed|crashing|"
    r"not (?:be )?(?:able|reachable|accessible|responding)|unreachable|inaccessible|unresponsive|"
    r"failed to (?:load|start|connect)|service disruption|5\d\d errors?|"
    r"could not (?:log ?in|access|connect))", re.I)


def select(entries, split):
    earlier = EVAL_DIR / "runs_gpt-4.1-mini.jsonl"
    done = {json.loads(line)["id"] for line in earlier.read_text().splitlines() if line} if earlier.exists() else set()
    pool = sorted(i for i in split["test"]
                  if i not in done and not entries[i]["cause_is_vague"]
                  and entries[i]["severity"] in ("Critical", "High") and CRASH.search(entries[i]["issue"]))
    return sorted(random.Random(SEED).sample(pool, SAMPLE_SIZE)), len(pool)


def evaluate(engine, entry, vector):
    kb = engine.kb
    rag = engine.run(entry["issue"], query_vector=vector)
    trace = rag["trace"]
    fused = [{"row": r} for r in trace["fused"]]
    no_rerank = [kb.docs[c["row"]]["category"] for c in diversify(kb, fused, 5, PER_ORG_CAP)]
    t0 = time.time()
    llm_only, _ = analyze(kb, entry["issue"], [], vote(kb, [], engine.alpha))
    llm_latency = round(time.time() - t0, 2)
    top = rag["similar_incidents"][0]["scores"] if rag["similar_incidents"] else {}
    return {
        "id": entry["id"],
        "org": entry["org"],
        "truth": {k: entry[k] for k in ("category", "severity", "cause_is_vague")},
        "rag": {
            "mode": rag["mode"],
            "category": rag["analysis"]["category"],
            "severity": rag["analysis"]["severity"],
            "category_confidence": rag["analysis"]["category_confidence"],
            "hypotheses": rag["analysis"]["hypotheses"],
            "baseline": {k: rag["baseline"][k] for k in ("category", "severity")},
            "neighbour_ids": [s["id"] for s in rag["similar_incidents"]],
            "neighbour_orgs": [s["org"] for s in rag["similar_incidents"]],
            "neighbour_categories": [s["category"] for s in rag["similar_incidents"]],
            "neighbour_relevance": [s["scores"].get("relevance") for s in rag["similar_incidents"]],
            "no_rerank_categories": no_rerank,
            "top_relevance": top.get("relevance"),
            "top_cosine": top.get("cosine"),
            "rewrite": trace.get("rewrite"),
            "dropped_citations": rag["validation"]["dropped_citations"],
            "latency_s": rag["timing_s"]["total"],
            "retrieve_s": rag["timing_s"]["retrieve"],
            "judge": judge(entry, rag["analysis"]["hypotheses"]),
        },
        "llm_only": {
            "category": llm_only["category"],
            "severity": llm_only["severity"],
            "hypotheses": llm_only["hypotheses"],
            "latency_s": llm_latency,
            "judge": judge(entry, llm_only["hypotheses"]),
        },
    }


def main():
    entries, split, vector_of = load_eval_data()
    ids, pool_size = select(entries, split)
    (HERE / "ids.json").write_text(json.dumps({"seed": SEED, "pool_size": pool_size, "ids": ids}, indent=1))
    done = {json.loads(line)["id"] for line in RUNS.read_text().splitlines() if line} if RUNS.exists() else set()
    todo = [i for i in ids if i not in done]
    print(f"model {LLM_MODEL} | pool {pool_size} | sample {len(ids)} | already done {len(done)} | running {len(todo)}")
    engine = Engine("train", alpha=tuned_alpha())
    failures = 0
    with ThreadPoolExecutor(6) as pool, RUNS.open("a") as out:
        futures = {pool.submit(evaluate, engine, entries[i], vector_of[i]): i for i in todo}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                out.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
                out.flush()
            except Exception:
                failures += 1
                print(f"FAILED {futures[future]}\n{traceback.format_exc()}")
            if n % 10 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
    print(f"done, {failures} failures")


if __name__ == "__main__":
    main()
