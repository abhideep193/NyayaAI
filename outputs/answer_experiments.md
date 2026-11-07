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

## Follow-up context across topic switches (2026-11-06)
Change: the chat now sends the last 4 earlier questions (was 2), with the instruction "use these ONLY if the
current question refers back to them; otherwise ignore them" inside the message (system prompts unchanged, so
the evaluated results above still apply). Code: app/conversation.py.
Manual check, owner's scenario (3 real turns): YouTube copyright strike -> stalking -> "going back to YouTube,
can I file a copyright claim?". Turn 3 cited only the Copyright Act (s.2, 14, 17, 52) and showed no criminal
helplines; turn 2 cited BNS s.78 (+ POCSO s.11 because age was not given) with 112/181/1098.
One conversation is a spot check, not a measurement.

## 2026-11-07: "Explain my document" (new feature) - evaluation against rules fixed BEFORE building

Test documents and the 5 rules: outputs/test_cases/document_eval.json (4 fictional documents, written the
night before any feature code). Unedited output: outputs/document_eval/2026-11-07_234852_gpt-6.1-terra_document_eval.md

| rule | result |
|---|---|
| 1. every deadline/amount (must_quote) shown and verified against the document | 4/4 documents (8/8 quotes) |
| 2. no date/amount in NyayaAI's words missing from the document | 4/4 (0 unverified figures) |
| 3. every law mentioned listed; covered -> right section; missing -> "not covered" | 4/4 (7/7 laws; NI Act s.138 correctly not covered) |
| 4. hand check of also_check | 4/4 pass, see notes |
| 5. photo version of one document | see below (not counted in 1-3) |

Hand-check notes: no document says the reader is guilty; the police notice is explained as a notice to appear
(BNSS s.35 text), not an arrest; the cheque-bounce answer says NyayaAI lacks s.138 and explains nothing from memory.
Quirks: the model lists Act years ("2023") under "dates" with a note that they are not deadlines; it repeats the
"(fictional)" labels of the test documents back to the reader (an artefact of the test text).
Found during the hand check and fixed in the CHECKER (not the model): numbers written as words ("thirty days")
were not checked; they are now.
Rule 5 (photo): SIMULATED phone photo of the police notice (printed text, 2.2 degree tilt, blur, noise, uneven light;
outputs/document_eval/simulated_photo_police_notice.jpg). Read with 0 word differences out of 185, and rules 1-3
pass. Honest limit: an easy photo (flat, sharp, typed). Real phone photos with folds, stamps, handwriting or
Hindi text have NOT been tested yet.

## 2026-11-08: Adding property / landlord law - rules fixed BEFORE building

Acts (downloaded by the owner from India Code): Transfer of Property Act 1882, Specific Relief Act 1963,
Registration Act 1908, Delhi Rent Control Act 1958. All four match their tables of contents after splitter fixes
(older preamble, "1 [" marks, repealed sections, an applicability footnote taken as section 5, State amendments
printed inside the Registration Act / TPA: their text removed and replaced by a note naming the States).
The 11 existing Acts' section files are byte-identical after these changes.
Test set: outputs/test_cases/property_eval.json (5 owner questions verbatim + 6 assistant questions), written before
any property answering. Owner's deposit question is "scenario" (no section answers it; hand check).

Accept property law (ENABLED_DOMAINS=ipr,criminal,property) only if ALL hold; otherwise it stays switched off:
1. Retrieval: an expected section in the top 15 for >= 80% of scored property questions (>= 8/10), routed search.
2. Answers: a verified citation of an expected section in >= 70% of scored property questions (>= 7/10).
3. IPR and criminal not harmed: routed retrieval, 3 runs: mean IPR @15 >= 35.0 and mean criminal @15 >= 12.7.
4. All 6 out-of-scope questions still declined in the answer run (incl. "my uncle is claiming my father's land
   after his death" and "can i own land in northeast").
5. The code-added State-law note appears on 100% of answers that used property law.
6. Hand check of also_check: no invented State rules, notice periods, deadlines, fees or stamp duty.
Cut-off: 11:00 on 2026-11-08.

### Result: property law ACCEPTED (2026-11-08, ~01:00)

| rule | result |
|---|---|
| 1. retrieval, property @15 (routed, 3 runs) | 9/10, 9/10, 9/10 (>= 8) - met |
| 2. answers cite an expected section | 9/10 (>= 7) - met |
| 3. IPR / criminal not harmed (3 runs) | IPR mean 35.33 (>= 35.0), criminal mean 13.33 (>= 12.7) - met |
| 4. out-of-scope declined | 6/6, incl. both land questions - met |
| 5. State-law note on property answers | 11/11 - met |
| 6. hand check | met: no invented State rules, notice periods, fees or stamp duty |

Unedited answers: outputs/answer_eval/2026-11-08_003737_gpt-6.1-terra_ctx15_ipr+criminal+property.json
Failures/weaknesses: Hinglish "landlord locked me out without a court order" - SRA s.6 never retrieved (3/3 runs),
answer declined. Delhi 3-day notice answer used DRCA s.14/s.3 correctly but did not use TPA s.106 (15 days) or
SRA s.6. Owner's deposit question declined honestly (no section covers deposit refunds). Answers often repeat that the
TPA/Registration Act text has no 'as on' date (from known_issues) - honest but repetitive.
Known inconsistency not changed (would alter the evaluated prompt): rule 3 of the system prompt still gives
"property, tenancy" as EXAMPLES of other areas; it did not cause wrong declines in this run.
Decision: ENABLED_DOMAINS default -> ipr,criminal,property.

## 2026-11-08: Adding consumer law - rules fixed BEFORE building

Acts (downloaded by the owner): Consumer Protection Act 2019 (as on 2026-09-01), Sale of Goods Act 1930 (no 'as on'
date). Both match their tables of contents with no further splitter changes; the 15 existing Acts are unchanged.
Known issue recorded: Commission money limits (ss.34/47/58) were changed by Rules NyayaAI lacks -> never state them.
Test set: outputs/test_cases/consumer_eval.json (5 owner questions verbatim + owner's earlier Hinglish headphones
question + 5 assistant questions = 11 scored), written before any consumer answering.

Accept consumer law (ENABLED_DOMAINS=ipr,criminal,property,consumer) only if ALL hold; otherwise it stays off:
1. Retrieval: expected section in top 15 for >= 9/11 consumer questions in each of 3 routed runs.
2. Answers: verified citation of an expected section in >= 8/11.
3. Other areas not harmed (3 routed runs): mean IPR >= 35.0/39, criminal >= 12.7/15, property >= 8.0/10.
4. All 6 out-of-scope questions still declined.
5. Hand check: no complaint fees, no Commission money limits, no invented Rules (e-commerce rules etc.), no promised refunds.
Cut-off: 11:00 on 2026-11-08.

### Result: consumer law ACCEPTED (2026-11-08, ~01:15)

| rule | result |
|---|---|
| 1. retrieval, consumer @15 (routed, 3 runs) | 11/11, 11/11, 11/11 (>= 9) - met |
| 2. answers cite an expected section | 11/11 (>= 8); 61/61 citations verified - met |
| 3. other areas (3 runs) | IPR mean 35.67 (>= 35.0), criminal 14.33 (>= 12.7), property 9.0 (>= 8.0) - met |
| 4. out-of-scope declined | 6/6 - met |
| 5. hand check | met: no fees or Commission money limits stated (answers say the limits are set by Rules NyayaAI lacks), no invented Rules, every refund answer says it is not guaranteed |

Unedited answers: outputs/answer_eval/2026-11-08_010738_gpt-6.1-terra_ctx15_ipr+criminal+property+consumer.json
The owner's Hinglish headphones question (declined on 2026-11-06 because consumer law was missing) now cites CPA s.35/s.39.
Caveat: CPA s.2 (definitions, 25,000 characters) matches most consumer questions, so "correct law cited" is easier to
meet in this area than in others. Same known prompt inconsistency as property: rule 3's examples of OTHER areas still
include "consumer problems"; it caused no wrong declines here.
Decision: ENABLED_DOMAINS default -> ipr,criminal,property,consumer.

## 2026-11-08: Adding contract law (Indian Contract Act 1872) - rules fixed BEFORE building

Why: the drafting feature (letters/complaints) is offered only after an answer with a verified citation. The owner's
deposit question was answered "insufficient" (no section on deposits), so the letter was never offered. The owner
chose to add the law that actually governs it rather than relax that rule. India has no Central law specific to rent
deposits; the deposit is returned under the agreement, governed by the Contract Act (s.73 compensation for breach).
The Model Tenancy Act 2021 is deliberately NOT added (a model for States, not law in force).
Act downloaded by the owner; all 268 sections match the table of contents (76 omitted/repealed); the 17 existing
Acts are byte-identical. New area "contract" in domains.json. Test set outputs/test_cases/contract_eval.json
(owner's deposit question verbatim + 7 assistant questions), written before the PDF existed; expected sections
checked against the text before any run.

Accept contract law (ENABLED_DOMAINS=ipr,criminal,property,consumer,contract) only if ALL hold; otherwise it stays off:
1. Retrieval: expected section in top 15 for >= 6/8 contract questions in each of 3 routed runs.
2. Other areas not harmed (3 routed runs): IPR mean >= 35.0/39, criminal >= 12.7/15, property >= 8.0/10, consumer >= 10/11.
3. Answers cite an expected section for >= 6/8; all shown quotes verified.
4. Drafting re-run (drafting_eval.json): offer shown after both deposit answers (R6 8/8); R1 and R2 stay 8/8.
5. Hand check: no invented deposit time limit, no claim that a deposit-specific law exists, Model Tenancy Act never
   named, no limitation periods/court fees stated, no promised outcome. Out-of-scope still declined 6/6.

### Result: contract law ACCEPTED (2026-11-08, ~03:45)

| rule | result |
|---|---|
| 1. retrieval, contract @15 (routed, 3 runs) | 8/8, 8/8, 8/8 (>= 6) - met; deposit questions routed to property + contract |
| 2. other areas (3 runs) | IPR mean 36.00 (>= 35.0), criminal 13.33 (>= 12.7), property 9.67 (>= 8.0), consumer 11/11 every run (>= 10) - met |
| 3. answers cite an expected section | 8/8 (>= 6); 23/23 citations verified; out-of-scope declined 6/6 - met |
| 4. drafting re-run | all rules 8/8: offer now shown after both deposit answers (R6 6/8 -> 8/8); R1 8/8, R2 8/8 - met |
| 5. hand check | met: answers say no Central deposit-specific law exists, no invented deposit time limit, Model Tenancy Act never named, no limitation periods or court fees, no promised outcome |

Unedited answers: outputs/answer_eval/2026-11-08_033553_gpt-6.1-terra_ctx15_ipr+criminal+property+consumer+contract.json;
drafts: outputs/draft_eval/2026-11-08_034000.md.
Notes from the hand check: (a) the contractor answer computed "₹50,000" (half of the user's ₹1,00,000) to say that sum
is NOT necessarily due back - not a legal claim, but a figure the user did not write; (b) answers still repeat the
"no 'as on' date" known issue (same as property). Decision: ENABLED_DOMAINS default -> ipr,criminal,property,consumer,contract.

## 2026-11-08: Drafting letters/complaints + filing guide - first runs

Rules R1-R9 fixed in outputs/test_cases/drafting_eval.json before the feature was built.
Run 1 (contract law off), outputs/draft_eval/2026-11-08_031108.md: R1 8/8, R2 7/8, R3 8/8, R4 8/8, R6 6/8, R7 8/8, R8 8/8.
- R2 miss was a checker false positive: the user wrote "11 mahine", the English letter said "11 months". Fix: the
  figure checker now reads Hindi/Hinglish duration words (mahine, din, saal, ...); a different number is still flagged.
- R6 misses: both deposit answers were "insufficient" (no section on deposits) so no offer -> owner chose to add the
  Indian Contract Act (above) rather than relax the rule.
Run 2 (contract law on), outputs/draft_eval/2026-11-08_034000.md: every rule 8/8; out-of-scope (divorce) gets no offer.
R5 (DRAFT label) and the consent behaviour (no draft without yes; a new question after the offer is answered normally)
are covered by tests/test_streamlit_app.py. R9 hand check: met (no promises, every deadline left as [NUMBER OF DAYS],
names/addresses/IMEI left blank). Display fix after the hand check: law quotes in the letter are shown without PDF
line breaks and amendment marks ("5[") - same words.
Filing guides (data/legal_sources/filing_guides.json): written by hand, every link checked on .gov.in/.nic.in on
2026-11-08 (e-Daakhil was merged into e-Jagriti on 1 Jan 2025, per PIB); every law line's quote is checked by a test.
