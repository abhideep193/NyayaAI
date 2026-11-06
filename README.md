# NyayaAI

**Plain-language legal information for people in India, answered only from the official text of the law.**

Ask a question in English, Hindi or Hinglish, for example *"Someone is using my logo"* or *"The police refused to
register my FIR"*. NyayaAI finds the relevant sections of the Acts, writes a short answer with practical next steps,
and shows every quote it relied on. Each quote is checked word for word against the official text before you see it.

NyayaAI gives legal information, not legal advice. It says so, and it says when a question is outside what it covers.

Built for the Kuku *AI Generalist* assignment, Problem 2 ("Build an AI Lawyer").

---

## What it covers

11 Central Acts, downloaded from [India Code](https://www.indiacode.nic.in), each with its "as on" date and SHA-256
fingerprint recorded in [`data/legal_sources/sources.json`](data/legal_sources/sources.json):

| Area | Acts |
|---|---|
| Intellectual property | Copyright Act 1957, Trade Marks Act 1999, Patents Act 1970 |
| Criminal law | Bharatiya Nyaya Sanhita 2023 (BNS), Bharatiya Nagarik Suraksha Sanhita 2023 (BNSS), Information Technology Act 2000, POCSO Act 2012, POSH Act 2013, Protection of Women from Domestic Violence Act 2005, Dowry Prohibition Act 1961, SC/ST (Prevention of Atrocities) Act 1989 |

**Not covered:** Rules and notifications, court judgments, State laws (rent, land, stamp duty), the old IPC/CrPC,
and other areas such as consumer, property, family and employment law. For these NyayaAI says it cannot answer
and suggests a lawyer, instead of guessing.

## How it avoids inventing laws

1. **Only real text goes in.** The Acts are split into sections and checked against each Act's own table of
   contents (all 11 match). The model is given only the sections that search found, never "general knowledge".
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
- **API:** `app/main.py` (FastAPI, `POST /ask`).
- **Areas of law are data, not code:** `data/legal_sources/domains.json`. Adding an area means adding its Acts and
  test questions; the prompts are built from the data.
- **Models are settings:** `OPENAI_MODEL` and `QUERY_REWRITE_MODEL` in `.env` (defaults `gpt-6.1-terra` and `gpt-6-luna`).

## Evaluation (honest numbers)

All test questions were written **before** the feature they test was built, and expected sections were checked
against the Act text. Details and every experiment, including rejected ones: [`outputs/retrieval_experiments.md`](outputs/retrieval_experiments.md),
[`outputs/answer_experiments.md`](outputs/answer_experiments.md). Raw answers: [`outputs/answer_eval/`](outputs/answer_eval/).

| Question set | Result |
|---|---|
| IPR questions (39: tuning, held-out, fresh, owner-written, Hindi/Hinglish) | correct law cited in **37/39** |
| Criminal-law questions (15: 7 owner-written, 8 assistant-written) | correct law cited in **13/15** |
| Out-of-scope questions (6) | correctly declined **6/6** |
| Citations checked word for word | **303/304** verified in the full run (the 1 failure was flagged to the user) |

Cost about **$0.01-0.03 per question**; median answer time about **15 s**.

**Known failures:** "Is software patentable?" (Patents s.3(k) never found by search); an OTP-fraud question where
search missed BNS s.318/319; a question about a 2023 case where the transition sections were not found; the model
sometimes labels a partly covered answer "not covered". Search quality varies a little between runs because the
rewrite step uses an LLM.

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
```

To rebuild the law data from the PDFs: `python -m scripts.extract_sources` then `python -m scripts.split_sections`
(each PDF's SHA-256 is checked first).

## Privacy

Questions are sent to OpenAI to write the answer (with `store=False`). NyayaAI does not save conversations or log
question text. Please do not include names or other personal details. The public demo asks for an access code
because every question is paid for by the developer.

## Project layout

```
app/                  pipeline: search, answer generation, citation verification, safety notes, API
data/legal_sources/   the Acts (PDFs), sources.json, domains.json, safety.json
data/processed/       extracted text, sections, search indexes
scripts/              ingestion, evaluation, deployment
outputs/              test questions, experiment logs, raw evaluation answers
tests/                110 unit tests
streamlit_app.py      chat page
```
