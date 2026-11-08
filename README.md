# NyayaAI

**Plain-language legal information for people in India, answered only from the official text of the law.**

Ask a question in English, Hindi or Hinglish, for example *"Someone is using my logo"* or *"The police refused to
register my FIR"*. NyayaAI finds the relevant sections of the Acts, writes a short answer with practical next steps,
and shows every quote it relied on. Each quote is checked word for word against the official text before you see it.

You can also **attach a legal notice or letter (PDF or a phone photo)** and NyayaAI explains it: what it says,
every deadline and amount (quoted word for word and checked against the document by code), which laws it mentions
and whether NyayaAI has them, and what to do next. Questions can be **spoken** (microphone); the words NyayaAI heard
are shown for checking before anything is sent.

After an answer, NyayaAI can **draft a letter or complaint** (a refund demand, consumer complaint, letter to a
landlord, police complaint or copyright notice), but only if the person says yes. It asks only for missing facts
(never names or addresses: those stay as **[BLANKS]** the person fills in), uses only the person's own facts and law
that was verified in the answer, and code checks every quote, date and amount in the draft. It can then show a
**step-by-step filing guide** (where to file, official portals such as e-Jagriti and cybercrime.gov.in, what to keep,
how to get an acknowledgement). The guides are fixed text checked on official government websites, not written by
the AI, and NyayaAI never files anything itself.

NyayaAI gives legal information, not legal advice. It says so, and it says when a question is outside what it covers.

Built for the Kuku *AI Generalist* assignment, Problem 2 ("Build an AI Lawyer").

**Live demo:** https://nyayaai-j6jrrcqxexfz2umjqgdodp.streamlit.app/ (open to try; if it is asleep, click the
button to wake it and wait about a minute).

---

## What it covers

Acts downloaded from [India Code](https://www.indiacode.nic.in), each with its "as on" date (where India Code prints
one) and SHA-256 fingerprint recorded in [`data/legal_sources/sources.json`](data/legal_sources/sources.json):

| Area | Acts |
|---|---|
| Intellectual property | Copyright Act 1957, Trade Marks Act 1999, Patents Act 1970 |
| Criminal law | Bharatiya Nyaya Sanhita 2023 (BNS), Bharatiya Nagarik Suraksha Sanhita 2023 (BNSS), Information Technology Act 2000, POCSO Act 2012, POSH Act 2013, Protection of Women from Domestic Violence Act 2005, Dowry Prohibition Act 1961, SC/ST (Prevention of Atrocities) Act 1989, NDPS Act 1985 (drugs) |
| Property and tenancy | Transfer of Property Act 1882, Specific Relief Act 1963, Registration Act 1908, Delhi Rent Control Act 1958 |
| Consumer | Consumer Protection Act 2019, Sale of Goods Act 1930 |
| Contracts | Indian Contract Act 1872 (agreements, money owed, deposits and advances not returned, penalty clauses) |

India has no Central law written specifically about returning a rent **security deposit**: it is returned under the
rent agreement, which the Contract Act governs. NyayaAI says so, and never invents a deposit time limit. (The Model
Tenancy Act 2021 is a model for States, not law in force, so it is deliberately not included.)

**Every State has its own rent law.** NyayaAI answers property questions from the Central Acts that apply everywhere,
plus Delhi's rent law as the first State-level one. Whenever property law is used, code adds a fixed note saying the
user's own State law may change the answer. State amendments that India Code prints *inside* the Central Acts
(41 blocks in the Registration Act) are removed from the text and replaced by a note naming those States, so a
State-only rule is never quoted as law for all of India.

**Not covered:** Rules and notifications, court judgments, State laws (other than Delhi rent control), inheritance,
land records, stamp duty, the old IPC/CrPC, and other areas such as family and employment law. For these NyayaAI
says it cannot answer and suggests a lawyer, instead of guessing.

## How it avoids inventing laws

1. **Only real text goes in.** The Acts are split into sections and checked against each Act's own table of
   contents (all 19 match). The model is given only the sections that search found, never "general knowledge".
2. **Every legal claim needs a quote.** The model must return each claim with a section ID and words copied
   exactly from that section (OpenAI Structured Outputs enforce the format).
3. **Code checks every quote.** `app/services/citation_verifier.py` confirms the section was really retrieved and the
   quote really appears in it. Unverified citations are shown as "Could not verify" and lower the answer's confidence label.
4. **Safety information is added by code, not by the model.** Helplines (112, 181, 1098, 1930) come from official
   government sources in [`safety.json`](data/legal_sources/safety.json), and so does the warning that the old IPC/CrPC
   may apply to events before 1 July 2024.

Verification proves a quote is *real*, not that the legal reasoning is *right*: during evaluation, a quote from the BNSS
offence table was correctly verified but labelled with the wrong section number (a splitting bug, now fixed). That is
why answers are also reviewed by hand (see Evaluation).

## How it works

```
question ─► rewrite into legal terms + choose area of law (small LLM)
         ─► search only that area's Acts: keyword (BM25) + meaning (bge-small embeddings), fused with RRF
         ─► top 15 sections ─► answer model (structured: answer, citations, confidence, next steps)
         ─► citation verifier ─► safety notes ─► chat page (or JSON API)
```

- **Chat page:** `streamlit_app.py` (Streamlit), with follow-up questions, Stop and Edit.
- **Explain my document:** `app/services/document_explainer.py`. PDF text via pypdf, photos read by a vision model.
  Our code (not the model) finds every "section X of the Y Act" in the document and looks it up; laws NyayaAI does
  not have are marked "not covered" and the model is told not to explain them. Code then checks every quote from
  the document, every date/amount/duration the explanation writes, and every legal citation.
- **Voice:** `app/services/voice.py` (OpenAI speech-to-text); the text is shown for correction before sending.
- **API:** `app/main.py` (FastAPI, `POST /ask`).
- **Areas of law are data, not code:** `data/legal_sources/domains.json`. Adding an area means adding its Acts and
  test questions; the prompts are built from the data.
- **Models are settings:** `OPENAI_MODEL` and `QUERY_REWRITE_MODEL` in `.env` (defaults `gpt-6.1-terra` and `gpt-6-luna`).

## Evaluation (honest numbers)

All test questions were written **before** the feature they test was built, and expected sections were checked
against the Act text. Details and every experiment, including rejected ones: [`outputs/retrieval_experiments.md`](outputs/retrieval_experiments.md),
[`outputs/answer_experiments.md`](outputs/answer_experiments.md). Raw answers: [`outputs/answer_eval/`](outputs/answer_eval/).

Final run with the submitted version (all 63 answers, unedited:
[`outputs/raw_outputs/`](outputs/raw_outputs/)):

| Question set | Result |
|---|---|
| IPR questions (39: tuning, held-out, fresh, owner-written, Hindi/Hinglish) | correct law cited in **36/39** |
| Criminal-law questions (15: 7 owner-written, 8 assistant-written) | correct law cited in **13/15** |
| Out-of-scope questions (6) | correctly declined **6/6** |
| Property questions (10 scored: 4 owner-written, 6 assistant-written), separate run 2026-11-08 | correct law cited in **9/10**; State-law note on 11/11 |
| Consumer questions (11: 6 owner-written, 5 assistant-written), separate run 2026-11-08 | correct law cited in **11/11**; 61/61 quotes verified |
| Contract questions (8: 1 owner-written, 7 assistant-written), separate run 2026-11-08 | correct law cited in **8/8**; 23/23 quotes verified |
| Drafting conversations (8, rules fixed before building: [`drafting_eval.json`](outputs/test_cases/drafting_eval.json)) | no unverified law **8/8**, no invented date or amount **8/8**, names left blank **8/8**, right document and filing guide **8/8**; out-of-scope question gets no draft offer |
| Real-life questions typed by the owner while testing (3) | shown, not scored |
| Citations checked word for word (the 63-answer run) | **310/312** verified (the 2 rejected quotes were too short to prove anything, and were flagged) |

Property, consumer and contract law were each accepted only after search for the existing areas stayed within the
limits set in advance (3 runs each). Consumer answers never state complaint fees or which Commission hears a case by
value: those limits were changed by Rules that NyayaAI does not have, so answers say they must be checked. The first
drafting run offered no letter after the owner's deposit question (no law on deposits yet, so the answer was "not
covered"); adding the Contract Act fixed that, as measured in the second run.

**Explain my document** (4 fictional notices written before the feature was built, rules fixed in advance:
[`document_eval.json`](outputs/test_cases/document_eval.json); unedited output in [`outputs/document_eval/`](outputs/document_eval/)):
every deadline and amount shown and verified 8/8; no unverified date or amount 4/4; laws mentioned correctly linked
or marked "not covered" 7/7 (including a cheque-bounce notice under the Negotiable Instruments Act, which NyayaAI
does not have and did not explain from memory); hand check 4/4. A simulated phone photo was read with 0 errors in
185 words, but it was an easy photo: real photos with folds, stamps or handwriting are not yet tested.

Cost about **$0.015 per question**; median answer time about **15 s**. Results vary slightly between runs because
the search-rewrite step uses an LLM (the previous full run scored 37/39 on IPR).

**Known failures:** "Is software patentable?" (Patents s.3(k) never found by search); unregistered brand-name
questions (Trade Marks s.27 not cited); "neighbour punched me" (BNS s.115 not found by search); and over-caution
in 3 criminal answers: for the POCSO teacher and sexual-assault questions the model cited the right sections but
labelled its answer "not covered", and for the 2023 case it was given the right transition sections (BNS s.358,
BNSS s.531) but still declined. The code-added old-law warning was shown in that case anyway.

**Open regression (found by the owner while testing):** *"Someone uploaded my entire YouTube video ... monetised it.
What legal action can I take, and can I get the video removed?"* The rewritten search query ranks Copyright Act s.55
(civil remedies: injunction, damages, accounts) first, but merging it with the original question's ranking pushes it
to 17th, outside the 15 sections the model reads, so the answer says it cannot explain the remedies. A fix (searching
deeper) was tested and **rejected** because it lowered other results (IPR 36.0 -> 35.0, criminal 13.7 -> 12.0 over
3 runs). The case is kept as a test marked "expected to fail": `tests/test_regression_youtube_reupload.py`.

## Run it yourself

Requires Python 3.14 and an OpenAI API key.

```bash
git clone <this repository>
cd NyayaAI
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
# then open .env and set OPENAI_API_KEY=...

streamlit run streamlit_app.py  # chat page at http://localhost:8501
uvicorn app.main:app --reload   # optional JSON API at http://127.0.0.1:8000/docs
```

The first start downloads the embedding model (~130 MB). Search indexes are included in the repository.

```bash
python -m pytest                                     # unit tests (no API calls)
python -m scripts.evaluate_retrieval                 # search quality (no API calls)
python -m scripts.evaluate_answers --cases outputs/test_cases/criminal_eval.json   # full answers (uses the API)
python -m scripts.evaluate_documents                 # explain-my-document test notices (uses the API)
python -m scripts.evaluate_drafting                  # letter/complaint drafting conversations (uses the API)
```

To rebuild the law data from the PDFs: `python -m scripts.extract_sources` then `python -m scripts.split_sections`
(each PDF's SHA-256 is checked first).

## Privacy

Questions are sent to OpenAI to write the answer (with `store=False`). NyayaAI does not save conversations or log
question text. Please do not include names or other personal details. Attached documents and voice recordings
are also sent to OpenAI (to read and transcribe them) and are not saved by NyayaAI; documents often contain names
and addresses, so cover them if you can. The public demo has a monthly spending limit on the developer's
OpenAI account; an optional access code (`APP_ACCESS_CODE`) can be switched on if needed.

## Project layout

```
app/                  pipeline: search, answer generation, citation verification, safety notes, API
data/legal_sources/   the Acts (PDFs), sources.json, domains.json, safety.json
data/processed/       extracted text, sections, search indexes
scripts/              ingestion, evaluation, deployment
outputs/              test questions, experiment logs, raw evaluation answers
tests/                149 tests (+1 known regression marked expected-to-fail)
streamlit_app.py      chat page
```

## License

NyayaAI's code is released under the [MIT License](LICENSE). The text of the Acts comes from India Code
(Government of India) and is not covered by this license.
