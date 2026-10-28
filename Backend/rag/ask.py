"""Ask the engine about one incident from the terminal.

    python -m rag.ask "EU users get 502s right after the morning deploy"
    python -m rag.ask --mode llm "..."      # LLM only, no retrieval
    python -m rag.ask --mode both "..."     # RAG and LLM-only side by side
    python -m rag.ask --rerank / --no-rerank "..."  # override the RCA_RERANK default
    python -m rag.ask --json "..."          # raw JSON
"""
import argparse
import json

from .engine import Engine


def show(title, result):
    a = result["analysis"]
    print(f"\n=== {title}  ({result['mode']}, {result['timing_s']['total']}s) ===")
    print(f"summary : {a['summary']}")
    print(f"category: {a['category']}  (confidence {a['category_confidence']:.2f})")
    print(f"severity: {a['severity']}  (confidence {a['severity_confidence']:.2f})")
    print("root-cause hypotheses:")
    for i, h in enumerate(a["hypotheses"], 1):
        cites = ", ".join(h["evidence_ids"]) or "no citation"
        print(f"  {i}. [{h['likelihood']:.2f}] {h['cause']}\n     evidence: {cites}")
    print("first checks:")
    for step in a["first_checks"]:
        print(f"  - {step}")
    print("fix steps:")
    for step in a["fix_steps"]:
        print(f"  - {step}")
    if result["mode"] == "RAG":
        print("similar past incidents:")
        for s in result["similar_incidents"]:
            score = s["scores"].get("relevance", s["scores"].get("cosine"))
            print(f"  {s['id']}  {s['org']:<14} {s['category']:<26} score {score}  {s['source_url']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("incident")
    parser.add_argument("--mode", choices=["rag", "llm", "both"], default="rag")
    # Default comes from RCA_RERANK: on for OpenAI, off for local models.
    parser.add_argument("--rerank", dest="rerank", action="store_true", default=None)
    parser.add_argument("--no-rerank", dest="rerank", action="store_false")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    engine = Engine("full")
    runs = []
    if args.mode in ("rag", "both"):
        runs.append(("RAG", engine.run(args.incident, rerank=args.rerank)))
    if args.mode in ("llm", "both"):
        runs.append(("LLM-only", engine.run(args.incident, rerank=False, use_context=False)))
    for title, result in runs:
        result.pop("trace")
        if args.json:
            print(json.dumps({"engine": title, **result}, indent=1, ensure_ascii=False))
        else:
            show(title, result)


if __name__ == "__main__":
    main()
