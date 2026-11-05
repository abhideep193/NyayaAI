# Retrieval experiments

Evaluation set: `outputs/test_cases/retrieval_eval.json` (15 tuning + 10 held-out questions).
Score = questions whose correct section appears in the top K results.

| Method | Tuning @5 | Tuning @15 | Held-out @5 | Held-out @15 | Median latency | Status |
|---|---|---|---|---|---|---|
| BM25 (stemming, heading boost, synonyms) | 9/15 | 13/15 | 2/10 | 5/10 | 1 ms | kept (part of hybrid) |
| Embeddings (`BAAI/bge-small-en-v1.5`) | 12/15 | 13/15 | 4/10 | 6/10 | 71 ms | kept (part of hybrid) |
| **Hybrid (BM25 + embeddings, RRF)** | **13/15** | **13/15** | **4/10** | **8/10** | **79 ms** | **in use** |
| Hybrid + cross-encoder rerank (`BAAI/bge-reranker-base`, top 20) | 9/15 | 13/15 | 6/10 | 8/10 | 33,370 ms | **removed** |

## Reranker experiment (2026-11-05)

Acceptance criteria were fixed before running: held-out @5 improves by at least 2,
tuning does not get worse, latency under 3 s per question.

Result: held-out @5 +2 (met), tuning @5 -4 (failed), latency 33 s on a laptop CPU (failed).
Net over all 25 questions: 17 -> 15 in the top 5. Removed.

Likely causes: model trained on general web text, not statutes; ~100 chunk pairs scored
per question on CPU. Revisit only with a GPU or a reranker suited to legal text,
and evaluate on a larger held-out set.
