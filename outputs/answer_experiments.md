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

## Switching criminal law on (rules fixed 2026-11-06 BEFORE running)

Setup: ENABLED_DOMAINS=ipr,criminal, domain routing (accepted in retrieval_experiments.md),
criminal answer rules 9-13 (domains.json), safety notes added by code (safety.json).
Questions: all IPR sets + out_of_scope (retrieval_eval.json) + criminal_eval.json (15, written before building).
Baseline (2026-11-06_133348, IPR only): IPR correct law cited 35/39, out_of_scope 6/6, 219/219 verified.

Criminal law becomes the default only if ALL hold:
1. IPR correct law cited >= 33/39 (baseline - 2; search alone varies 34-37/39 between identical runs),
   and no IPR set more than 1 below baseline.
2. out_of_scope >= 5/6; every failure is read by hand and reported.
3. Criminal correct law cited >= 12/15.
4. Citation verification rate >= 95%.
5. Hand review of all 15 criminal answers against their "also_check" notes: no promised outcome,
   no helpline numbers written by the model, no old IPC/CrPC section numbers. Any violation is fixed
   (and re-tested) before switching on.

### Result of the first run (2026-11-06_184410, ipr+criminal)
Rules 1-4 met: IPR correct law cited 37/39 (baseline 35), out_of_scope 6/6, criminal 15/15,
303/304 citations verified (99.7%; the 1 rejected was an IPR misquote of Trade Marks s.135, flagged as designed).
Rule 5 (hand review) found a REAL ERROR that verification cannot catch: the splitter did not stop at
"THE FIRST SCHEDULE", so the BNSS's whole First/Second Schedule (offence classification table and forms,
199,000 characters) was stored as part of section 531. Five answers quoted genuine schedule text
(e.g. "Cognizable. Bailable.") but labelled it "Section 531". The same bug attached the SC/ST Act's
schedule (a list of old IPC section numbers) to its section 23. No promised outcomes, no helpline numbers
written by the model, no old IPC section numbers found.
Fix: the body now ends at "THE FIRST/SECOND/... SCHEDULE" (also with an amendment mark "1[").
BNSS s.531 now 1,886 characters; IPR sections unchanged. Criminal answers re-run below (IPR unaffected:
its sections and index are unchanged).

### Re-run after the schedule fix (2026-11-06_185342, criminal sets only)
| | first run (schedules wrongly inside s.531) | re-run (fixed) |
|---|---|---|
| criminal correct law cited | 15/15 | **13/15** |
| citations verified | 100% | 100% (67/67) |
| answered "insufficient" | 0 | 3 |
The first run's 15/15 was partly inflated by the bug: the mislabelled schedule text helped the OTP-fraud and
March-2023 questions. 13/15 is the honest number.
Failures: OTP fraud (BNS s.318/319 not retrieved), March-2023 old-law question (s.358/531 not retrieved; said it
cannot tell). Over-caution: POCSO teacher answer correctly states the duty to report (s.19) but labels itself
"insufficient" because s.21 (penalty) was not retrieved; "neighbour punched me" similar. Not tuned: these are
test questions; fixing the prompt would need new, unseen questions to check.

Rule 5 (hand review of the re-run): no promised outcomes, no model-written helplines, no IPC section numbers.
DECISION: rules 1-5 met -> criminal law ON by default (ENABLED_DOMAINS=ipr,criminal).

Safety gap found in the review and fixed (designed AFTER seeing these answers; affects only the code-added
notes, not any scored result): notes depended only on the model's citations, so the OTP answer (cited s.314)
lost the 1930 helpline and the March-2023 answer (no citations) lost the old-law notice. Now, when criminal law
was searched, the old-law notice and keyword helplines (OTP, UPI, phishing...) are also checked. Replayed on the
saved answers: exactly these two notes added, nothing else changed.
Known limitation: sexual-assault answer citing only BNSS s.173 shows 112 but not the Women Helpline 181.
