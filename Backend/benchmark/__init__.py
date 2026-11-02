"""RCA evaluation and benchmarking (feature 7).

Adds the IR metrics the project lacked (Recall@K, Precision@K, MRR, NDCG),
plus citation correctness, hallucination rate, recommendation usefulness and
end-to-end latency - then compares three pipelines on the same held-out split:

    python -m benchmark.run --limit 50

| pipeline | retrieval          | rerank | agents |
|----------|--------------------|--------|--------|
| basic    | dense only         | no     | no     |
| hybrid   | dense + BM25 (RRF) | yes    | no     |
| agentic  | dense + BM25 (RRF) | yes    | yes    |

`benchmark.metrics` is pure and importable without faiss or an API key.
"""
from .metrics import (citation_metrics, graded_gain, hallucination_rate,
                      latency_report, ndcg_at_k, precision_at_k,
                      recall_at_k, reciprocal_rank, recommendation_usefulness,
                      retrieval_report, root_cause_accuracy, token_f1)

__all__ = ["recall_at_k", "precision_at_k", "reciprocal_rank", "ndcg_at_k",
           "graded_gain", "retrieval_report", "root_cause_accuracy",
           "token_f1", "citation_metrics", "hallucination_rate",
           "recommendation_usefulness", "latency_report"]
