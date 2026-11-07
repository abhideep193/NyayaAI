"""Measure 'Explain my document' on outputs/test_cases/document_eval.json (calls the OpenAI API).

Automatic checks (acceptance rules 1-3, fixed before the feature was built):
  1. every must_quote is shown inside a document quote that code verified against the document;
  2. no date, amount, duration or time in NyayaAI's own words is missing from the document/law;
  3. every law the document mentions is listed: covered ones linked to the expected section,
     missing ones marked not covered.
Rule 4 (also_check) is a hand check: read the markdown file this script writes.

Run from the project root:
    python -m scripts.evaluate_documents
    python -m scripts.evaluate_documents --cases my_documents.json
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from app import config
from app.services.citation_verifier import normalise_for_matching

EVAL_FILE = Path("outputs/test_cases/document_eval.json")
OUT_DIR = Path("outputs/document_eval")


def build_explainer():
    """The same explainer the chat page uses (search included)."""
    from scripts.search import build_document_explainer

    return build_document_explainer()


def score(doc: dict, result) -> dict:
    shown = [q.quote for q in result.deadlines_and_amounts + result.key_points if q.verified]
    quotes_ok = {mq: any(normalise_for_matching(mq) in normalise_for_matching(s) for s in shown)
                 for mq in doc["must_quote"]}
    laws_ok = {}
    for law in doc["laws"]:
        if law["covered"]:
            laws_ok[law["as_written"]] = any(m.section_id == law["section_id"] for m in result.laws)
        else:
            laws_ok[law["as_written"]] = any(not m.covered and normalise_for_matching(m.as_written)
                                             in normalise_for_matching(law["as_written"]) for m in result.laws)
    return {
        "rule1_quotes": quotes_ok,
        "rule2_unverified_figures": [f"{f.kind}: {f.text}" for f in result.unverified_figures],
        "rule3_laws": laws_ok,
        "passed": all(quotes_ok.values()) and not result.unverified_figures and all(laws_ok.values()),
    }


def to_markdown(doc: dict, result, checks: dict, seconds: float) -> str:
    lines = [f"## {doc['id']} ({doc['kind']})", "",
             f"**Automatic result:** {'PASS' if checks['passed'] else 'FAIL'}  ",
             f"**Confidence:** {result.confidence} (model said: {result.model_confidence})  ",
             f"**Time:** {seconds:.1f} s  ", f"**Hand check (also_check):** {doc['also_check']}", "",
             f"**Type:** {result.document_type}", "", f"**Summary:** {result.summary}", "",
             "**Deadlines and amounts:**"]
    lines += [f"- {'VERIFIED' if q.verified else 'NOT IN DOCUMENT'} \"{q.quote}\": {q.meaning}"
              for q in result.deadlines_and_amounts]
    lines += ["", "**Key points:**"]
    lines += [f"- {'VERIFIED' if q.verified else 'NOT IN DOCUMENT'} \"{q.quote}\": {q.meaning}" for q in result.key_points]
    lines += ["", "**Laws mentioned (found by code):**"]
    lines += [f"- {m.as_written}: {'covered -> ' + m.section_id if m.section_id else 'covered (whole Act)' if m.covered else 'NOT COVERED'}"
              for m in result.laws]
    lines += ["", f"**What the law says:** {result.law_explanation}", "", "**Citations:**"]
    lines += [f"- {'VERIFIED' if c.verified else 'REJECTED'} {c.citation or c.section_id}: \"{c.quote}\""
              for c in result.citations]
    lines += ["", "**Next steps:**"] + [f"- {s}" for s in result.next_steps]
    lines += ["", f"**Figures checked:** " + (", ".join(f"{f.text} ({'ok' if f.found else 'NOT FOUND'})"
                                                       for f in result.figures) or "none"),
              f"**Rule 1 quotes:** {checks['rule1_quotes']}  ", f"**Rule 3 laws:** {checks['rule3_laws']}", "", "---", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(EVAL_FILE))
    args = parser.parse_args()
    docs = json.loads(Path(args.cases).read_text(encoding="utf-8"))["documents"]

    explainer = build_explainer()
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records, markdown = [], [f"# Explain-my-document evaluation {stamp} ({config.OPENAI_MODEL})", "",
                             "Unedited output. Rules fixed before building: see document_eval.json.", ""]
    for doc in docs:
        start = time.perf_counter()
        result = explainer.explain(doc["text"])
        seconds = time.perf_counter() - start
        checks = score(doc, result)
        print(f"{'PASS' if checks['passed'] else 'FAIL'}  {doc['id']:28} {seconds:5.1f} s  "
              f"unverified figures: {checks['rule2_unverified_figures']}  quotes: {checks['rule1_quotes']}  laws: {checks['rule3_laws']}")
        markdown.append(to_markdown(doc, result, checks, seconds))
        records.append({"id": doc["id"], "seconds": round(seconds, 1), **checks,
                        "confidence": result.confidence, "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens})

    name = f"{stamp}_{config.OPENAI_MODEL}_{Path(args.cases).stem}"
    (OUT_DIR / f"{name}.json").write_text(json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / f"{name}.md").write_text("\n".join(markdown), encoding="utf-8")
    print(f"\n{sum(r['passed'] for r in records)}/{len(records)} passed automatic rules 1-3. "
          f"Hand-check file: {OUT_DIR / (name + '.md')}")


if __name__ == "__main__":
    main()
