# Answer experiments

Full pipeline (hybrid retrieval -> `gpt-6.1-terra` -> citation verifier) on the 28 questions in
`outputs/test_cases/retrieval_eval.json` (15 tuning, 10 held-out, 3 out-of-scope).
Contextual accuracy graded by `scripts/judge_citations.py` (`gpt-6.1-sol`, evaluation only), spot-checked by hand.

## Context sections: 8 vs 15 (2026-11-05)

Files: `answer_eval/2026-11-05_234543_gpt-6.1-terra_ctx8*.json` (A),
`answer_eval/2026-11-05_235113_gpt-6.1-terra_ctx15*.json` (B).
Repeatability check: an earlier identical ctx-8 run (`2026-11-05_232740_...`) retrieved identical
sources for 28/28 questions and differed in only 1 answer's confidence level.

| Metric | A: 8 sections | B: 15 sections |
|---|---|---|
| Correct law retrieved (25 in-scope) | 17/25 | 21/25 |
| Correct law cited & verified | 17/25 | 21/25 |
| - tuning | 13/15 | 13/15 |
| - held-out | 4/10 | 8/10 |
| Abstained on in-scope questions | 4 | 1 |
| Abstained although correct law was retrieved | 0 | 0 |
| Out-of-scope correctly refused | 3/3 | 3/3 |
| Citations verified (word for word) | 118/118 | 154/155 |
| Judge: citations fully supported | 116/118 | 150/155 |
| Judge: partially supported / out of context / not supported | 2 / 0 / 0 | 5 / 0 / 0 |
| Judge: answers with no issues | 14/21 | 17/24 |
| Judge: significant issues | 0 | 0 |
| Median / max latency | 10.6 s / 21.2 s | 11.9 s / 23.3 s |
| Input tokens per question | ~5,800 | ~10,000 |
| Answer cost per question / total | $0.0094 / $0.26 | $0.0144 / $0.40 |
| Judge cost (evaluation only) | $0.22 | $0.28 |

The one rejected citation (B, Patents s.50) stitched two parts of a sentence into a "quote";
the verifier rejected it correctly.

**Decision (2026-11-06): use 15 sections** (default in `app/config.py`). Held-out correct law
cited 4/10 -> 8/10 and in-scope abstentions 4 -> 1, with no new citation errors, for +$0.005 per question.

## With query rewriting + multilingual + out-of-scope redirect (2026-11-06)

File: `answer_eval/2026-11-06_133348_gpt-6.1-terra_ctx15.json` (45 questions; rewrite model `gpt-6-luna`).
Prompt changes: reply in the user's language with quotes kept verbatim in English; non-IPR questions get
"NyayaAI covers only copyright, trade marks and patents" + "speak to a qualified lawyer", no other laws named.

| Set | Correct law retrieved | Correct law cited & verified |
|---|---|---|
| Tuning (15) | 13/15 | 13/15 |
| Held-out (10) | 10/10 | 10/10 (was 8/10 without rewriting) |
| Fresh (9) | 9/9 | 9/9 |
| Fresh2 (2, owner) | 2/2 | 1/2 |
| Multilingual (3, Hindi/Hinglish) | 2/3 | 2/3 |
| Out of scope (6) | - | 6/6 correctly declined |

Citations: 219 verified, 0 rejected. Median latency 13.4 s (max 24.9 s). Cost $0.0153 per question.
Remaining failures: "Is software patentable?" (s.3 never retrieved); unregistered company name and "sue for
unregistered brand" (answers cite ss.11/134/135 for passing off - substantively right, but s.27 not cited);
Hindi "register my brand name" (s.18 not retrieved; answer honestly says the sources don't give the procedure).

## Judge reliability (manual spot-check)

- Correct: s.52 proviso requires acknowledgment for criticism/review; answers omitted it.
- Correct: s.111(3) restriction applies only to amendments by disclaimer, correction or explanation.
- Wrong: flagged "equipment" in s.58 as unsupported, but s.2(t) defines "plate" to include
  "duplicating equipment". The judge only saw the cited section, not the definition.
- Lenient: rated the s.11(3)(a) passing-off quote "supported"; it is accurate but indirect
  (s.27(2) and s.134(1)(c) are the direct provisions).

## Metric review: "Can I sue ... if I never registered it?"

Expected: TM s.27. s.27(1) bars infringement actions for unregistered marks; s.27(2) preserves passing off.
Answers cited s.11(3)(a) and s.134(1)(c) ("passing off ... whether registered or unregistered").
Verdict: valid alternative explanation, substantively correct, but omits that an infringement
action is not available. Dataset NOT changed; strict score kept.
