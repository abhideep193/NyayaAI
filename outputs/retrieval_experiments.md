# Retrieval experiments

Evaluation set: `outputs/test_cases/retrieval_eval.json` (15 tuning + 10 held-out questions).
Score = questions whose correct section appears in the top K results.

| Method | Tuning @5 | Tuning @15 | Held-out @5 | Held-out @15 | Median latency | Status |
|---|---|---|---|---|---|---|
| BM25 (stemming, heading boost, synonyms) | 9/15 | 13/15 | 2/10 | 5/10 | 1 ms | kept (part of hybrid) |
| Embeddings (`BAAI/bge-small-en-v1.5`) | 12/15 | 13/15 | 4/10 | 6/10 | 71 ms | kept (part of hybrid) |
| **Hybrid (BM25 + embeddings, RRF)** | **13/15** | **13/15** | **4/10** | **8/10** | **79 ms** | **in use** |
| Hybrid + cross-encoder rerank (`BAAI/bge-reranker-base`, top 20) | 9/15 | 13/15 | 6/10 | 8/10 | 33,370 ms | **removed** |

## LLM query rewriting (2026-11-06) - ACCEPTED with documented exceptions

Change: `gpt-6-luna` rewrites the question into the vocabulary of the three Acts (no answering, no section
numbers); hybrid search runs on the original AND the rewrite; rankings fused with RRF.
Pre-set rules: no set worse at @5/@15; >= +2 questions overall; < 2 s extra.

| Hybrid | Tuning @5/@15 | Held-out @5/@15 | Fresh @5/@15 |
|---|---|---|---|
| Current | 13/15, 13/15 | 4/10, 8/10 | 8/9, 9/9 |
| + rewrite | 13/15, 13/15 | 8/10, 10/10 | 8/9, 8/9 |

Failed two rules: fresh @15 9 -> 8 (owner's "patent a software application" question lost) and +2.5 s median.
Owner chose to accept only if confirmed on NEW owner-written questions ('fresh2'), rule fixed beforehand:
not worse than current at @5 and @15. Result: fresh2 1/2 -> 1/2 at both cutoffs (Instagram reel rank 4 -> 2;
unregistered company name not found by either). Confirmation is weak (only 2 in-scope questions).
Accepted exceptions: one fresh question lost at @15; +2.5-4.5 s per question. Rewrite cost ~$0.0001/question.

## Clause-level embedding chunks (2026-11-06)

Goal: fix "Is software patentable in India?" (Patents s.3(k) ranked 43rd in hybrid search).
Hypothesis: clause (k) is buried in a ~1,200-character chunk with clauses (j)-(p).
Change tested: split sections at clause markers "(a)", "(k)", "(1)"... for embedding search only.
Tested on a new 'fresh' set of 9 questions (5 written by the project owner) written before the experiment.

| Hybrid | Tuning @5 | Tuning @15 | Held-out @5 | Held-out @15 | Fresh @5 | Fresh @15 |
|---|---|---|---|---|---|---|
| Current (section chunks) | 13/15 | 13/15 | 4/10 | 8/10 | 8/9 | 9/9 |
| Clause-level chunks | 13/15 | 13/15 | 3/10 | 10/10 | 8/9 | 8/9 |

Result: "Is software patentable?" still not found; the owner's question "Can I patent a software
application or mobile app idea?" went from rank 7 to not found. Rejected; app code never changed.
Finding: the current search already handles most list-style questions (fresh 9/9 in top 15);
the failure is specific to very short questions with few clues.

## Reranker experiment (2026-11-05)

Acceptance criteria were fixed before running: held-out @5 improves by at least 2,
tuning does not get worse, latency under 3 s per question.

Result: held-out @5 +2 (met), tuning @5 -4 (failed), latency 33 s on a laptop CPU (failed).
Net over all 25 questions: 17 -> 15 in the top 5. Removed.

Likely causes: model trained on general web text, not statutes; ~100 chunk pairs scored
per question on CPU. Revisit only with a GPU or a reranker suited to legal text,
and evaluate on a larger held-out set.
