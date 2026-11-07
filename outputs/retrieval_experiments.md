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

## Adding criminal law: does it hurt IPR search? + domain routing (2026-11-06)

8 criminal-law Acts added (1,815 sections). Criminal test set written BEFORE this work:
outputs/test_cases/criminal_eval.json (7 owner questions, 8 assistant questions).
Method in the app: hybrid + LLM query rewriting. Same code, same day.

| hybrid+rewrite @5 / @15 | tuning | held_out | fresh | fresh2 | multilingual | criminal_owner | criminal |
|---|---|---|---|---|---|---|---|
| IPR Acts only | 13/13 of 15 | 8 / 10 | 9 / 9 | 1 / 2 | 0 / 3 | - | - |
| IPR + criminal in one index | 13/13 of 15 | 7 / 9 | 8 / 8 | 1 / 1 | 1 / 2 | 6/7 / 7/7 | 5/8 / 8/8 |

IPR total @15 fell from 37/39 to 33/39: criminal sections crowd out IPR sections
(rewrite is an LLM step, so part of this is run-to-run noise, but every change is downward).

### Experiment: domain routing (criteria fixed BEFORE running)
Change: the rewrite call also returns which area(s) of law the question is about; each area
has its own search index; search only the chosen area(s) (merge with RRF if several; search all
if none is chosen or the rewrite fails). IPR-only mode is untouched (no routing with one area).

Accept routing only if ALL hold, compared with the table above:
1. IPR total @15 >= 36/39, and no IPR set more than 1 lower at @15 than "IPR Acts only".
2. Criminal total @15 >= 14/15 (currently 15/15 unrouted).
3. Median latency increase <= 1 s compared with unrouted hybrid+rewrite.
Otherwise reject and look for another fix before enabling criminal law.

### Result (same run, both areas enabled)

| @5 / @15 | tuning | held_out | fresh | fresh2 | multilingual | IPR total @15 | criminal_owner | criminal | latency |
|---|---|---|---|---|---|---|---|---|---|
| IPR Acts only (baseline above) | 13/13 | 8/10 | 9/9 | 1/2 | 0/3 | 37/39 | - | - | 1.9 s |
| hybrid+rewrite, one index | 13/13 | 8/9 | 8/8 | 1/1 | 2/2 | 33/39 | 5/7 | 6/8 | 2.5 s |
| routed | 13/13 | 8/10 | 9/9 | 1/1 | 0/2 | **35/39** | 4/7 | 6/8 | 2.7 s |

Criteria: (1) IPR total @15 >= 36/39 -> 35/39, FAILED by one question (no set more than 1 lower: met);
(2) criminal @15 >= 14/15 -> 15/15, met; (3) latency +0.24 s, met.
The two IPR questions lost (fresh2 "company name ... never registered", Hindi "register brand") were
both at rank 15 - the last place counted - in the IPR-only run. Not accepted on this run; decision
on next step recorded below.

### Second test: is the 1-question gap noise? (owner's decision; rule fixed BEFORE running)
The first test above FAILED rule 1. The owner chose a noise test, with this rule written before running:
run "IPR Acts only" (hybrid+rewrite) and "routed" (both areas enabled) 3 times each, same code.
Accept routing only if BOTH hold:
1. Mean IPR total @15 of routed >= mean IPR total @15 of IPR-only minus 1.
2. Criminal total @15 >= 14/15 in EVERY routed run.
The first test's numbers are not included in these means.

### Second test result: routing ACCEPTED

| run | IPR only: IPR total @15 | routed: IPR total @15 | routed: criminal @15 | one index (no routing): criminal @15 |
|---|---|---|---|---|
| 1 | 34/39 | 36/39 | 14/15 | 14/15 |
| 2 | 36/39 | 35/39 | 14/15 | 13/15 |
| 3 | 35/39 | 34/39 | 15/15 | 13/15 |
| mean | 35.0 | 35.0 | - | - |

Rule 1: routed mean 35.0 >= 35.0 - 1 -> met. Rule 2: 14, 14, 15 -> met. Accepted.
Finding: the same IPR-only setup varies 34-37/39 between runs (LLM rewrite), so a single run
cannot detect a 1-2 question change. Without routing, criminal search falls below 14/15 in 2 of 3 runs.
Known weak questions: owner's "neighbour punched me" (BNS s.115 missed in 1-2 of 3 runs);
Hindi dowry question and OTP fraud question sometimes near rank 15.

## 2026-11-07: Fusion depth 30 -> 60 (owner's YouTube re-upload regression)

Diagnosis: for "Someone uploaded my entire YouTube video ... monetised it ... legal action ... removed?",
the rewrite ranks Copyright s.55 (civil remedies) #1, but s.55 is not in the ORIGINAL question's top 30,
so RRF gives it one vote and it lands at #17 (outside the 15 sections given to the model).
Change tested: DomainRoutedRetriever candidates 30 -> 60 (each list searched to depth 60 before fusing).
Simulated on 4 logged rewrites before this test: s.55 moves to #8-12.

Method (fixed BEFORE running): paired test. In each run, every question is rewritten/routed ONCE
and both depths are scored on that same rewrite, so LLM rewrite noise affects both equally. 3 runs.
Question sets: retrieval_eval.json + criminal_eval.json (the regression question is NOT counted here).
Accept depth 60 only if ALL hold:
1. tests/test_regression_youtube_reupload.py passes at depth 60.
2. Mean IPR total @15 at depth 60 >= 35.0 AND >= mean at depth 30.
3. Mean criminal total @15 at depth 60 >= mean at depth 30.
Otherwise keep 30 and revert.

### Result: depth 60 REJECTED (2026-11-07)

| run | depth 30: IPR @15 | depth 60: IPR @15 | depth 30: criminal @15 | depth 60: criminal @15 |
|---|---|---|---|---|
| 1 | 35/39 | 34/39 | 13/15 | 12/15 |
| 2 | 35/39 | 35/39 | 13/15 | 12/15 |
| 3 | 38/39 | 36/39 | 15/15 | 12/15 |
| mean | 36.0 | 35.0 | 13.67 | 12.0 |

Rule 2 (IPR mean >= 35.0 AND >= depth 30): 35.0 < 36.0 -> FAILED. Rule 3 (criminal not lower): 12.0 < 13.67 -> FAILED.
Deeper lists let more weakly-matching sections collect a second vote. Lost in every run: held-out "A company copied
my patented invention. What can a court order..." and criminal "cheated me of Rs 2 lakh in March 2023".
Gained once: "Is software patentable in India?". Not applied; the app keeps depth 30.
The YouTube regression test stays marked as an expected failure (known limitation). Ideas not yet tested:
search with the rewrite alone when it is available, or a fixed number of guaranteed places for each list's top results.
