# Raw outputs (unedited)

Every answer below is exactly as NyayaAI produced it during evaluation: not rewritten, shortened or filtered.
Each file lists, per question: the answer, confidence, safety notes added by code, next steps, every citation
(verified or not) and the sections the model was given.

| File | What it is | Questions |
|---|---|---|
| [2026-11-06_233821 … ipr+criminal](2026-11-06_233821_gpt-6.1-terra_ctx15_ipr+criminal.md) | Main run: IPR (39), criminal (15), out of scope (6), owner's real-life questions (3) | 63 |
| [2026-11-08_003737 … property](2026-11-08_003737_gpt-6.1-terra_ctx15_ipr+criminal+property.md) | Property and tenancy law (incl. owner's deposit question, then "not covered") | 17 |
| [2026-11-08_010738 … consumer](2026-11-08_010738_gpt-6.1-terra_ctx15_ipr+criminal+property+consumer.md) | Consumer law | 17 |
| [2026-11-08_033553 … contract](2026-11-08_033553_gpt-6.1-terra_ctx15_ipr+criminal+property+consumer+contract.md) | Contract law (owner's deposit question, now answered) + out of scope | 14 |
| [2026-11-08_114826 … contract](2026-11-08_114826_gpt-6.1-terra_ctx15_ipr+criminal+property+consumer+contract.md) | Drug law (NDPS Act, inside criminal law) + out of scope | 11 |

Other unedited outputs:
- Drafted letters and complaints (8 scripted conversations, two runs): [`../draft_eval/`](../draft_eval/)
- "Explain my document" (4 fictional notices + a simulated phone photo): [`../document_eval/`](../document_eval/)
- Machine-readable versions of all answer runs: [`../answer_eval/`](../answer_eval/)

The rules each run was judged against, written before the run, are in
[`../answer_experiments.md`](../answer_experiments.md).
