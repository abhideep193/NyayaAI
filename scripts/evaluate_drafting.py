"""Measure letter/complaint drafting on outputs/test_cases/drafting_eval.json (calls the OpenAI API).

Each case is a scripted conversation, run exactly as the chat page runs it:
  answer the problem -> (offer shown?) -> consent -> plan (questions) -> facts reply -> draft.

Automatic checks (rules fixed in drafting_eval.json BEFORE the feature was built):
  R1 no law reference rejected by the verifier, and no section number / Act name inside the letter body
  R2 no date/amount/duration/time that is not in the person's messages (or, for amounts/durations, a verified quote)
  R3 (automatic part) the sender's name is a [BLANK]; the rest of 'must_be_blank' is a hand check
  R4 every 'must_include' fact appears in the draft
  R6 the offer is shown after the answer; for consent_cases, no offer when out of scope
  R7 document type, R8 filing guide id
R5 (DRAFT label) and the R6 UI behaviour are covered by tests/test_streamlit_app.py; R9 is a hand check:
read the markdown file this script writes.

Run from the project root:
    python -m scripts.evaluate_drafting
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

EVAL_FILE = Path("outputs/test_cases/drafting_eval.json")
OUT_DIR = Path("outputs/draft_eval")
DRAFT_YES = "Yes, please help me draft it."  # the button text (same as streamlit_app.py)
NAME_BLANK = re.compile(r"\[(?:YOUR|COMPLAINANT'?S?|SENDER'?S?|OWNER'?S?|PHOTOGRAPHER'?S?|TENANT'?S?)[^\]]*NAME[^\]]*\]",
                        re.IGNORECASE)


def offers_draft(response) -> bool:  # same rule as streamlit_app.offers_draft
    return response.confidence != "insufficient" and any(c.verified for c in response.citations)


def squash(text: str) -> str:
    return re.sub(r"[\s,]+", "", text.lower())


def run_case(case: dict, assistant, drafter) -> dict:
    started = time.monotonic()
    answer = assistant.ask(case["problem"])
    consent = DRAFT_YES if case["consent"] == "button" else case["consent"]
    questions = drafter.plan(case["problem"], answer, consent)
    facts = case["facts_reply"] if questions.plan.questions else ""
    draft = drafter.write(case["problem"], answer, questions.plan, consent, facts)
    text = draft.full_text()

    checks = {
        "R1_no_unverified_law": not draft.removed_law and not draft.law_in_body,
        "R2_no_invented_figures": not draft.unverified_figures,
        "R3_name_is_blank": bool(NAME_BLANK.search(text)),
        "R4_includes_user_facts": all(squash(f) in squash(text) for f in case["must_include"])
                                  if questions.plan.questions or not case.get("facts_reply") else
                                  all(squash(f) in squash(text) for f in case["must_include"]
                                      if squash(f) in squash(case["problem"] + consent)),
        "R6_offer_shown": offers_draft(answer),
        "R7_right_document": draft.document_type == case["expected_document"],
        "R8_right_guide": draft.guide == case["expected_guide"],
    }
    return {
        "id": case["id"], "author": case["author"], "checks": checks,
        "answer_confidence": answer.confidence,
        "answer_verified_sections": [c.section_id for c in answer.citations if c.verified],
        "questions_asked": questions.plan.questions, "facts_reply_used": facts,
        "document_type": draft.document_type, "guide": draft.guide,
        "draft_text": text, "blanks": draft.blanks,
        "law": [{"section_id": c.section_id, "verified": c.verified, "quote": c.quote} for c in draft.law],
        "unverified_figures": [f.text for f in draft.unverified_figures], "law_in_body": draft.law_in_body,
        "check_before_sending": draft.check_before_sending, "must_be_blank (hand check)": case["must_be_blank"],
        "seconds": round(time.monotonic() - started, 1),
    }


def main() -> None:
    from scripts.search import build_assistant, build_drafter

    data = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    assistant = build_assistant()
    drafter = build_drafter(client=assistant.client)

    results = []
    for case in data["cases"]:
        print(f"- {case['id']} ...", flush=True)
        results.append(run_case(case, assistant, drafter))
        print("  ", {k: v for k, v in results[-1]["checks"].items()})

    consent_results = []
    for case in data["consent_cases"]:
        if "then_typed" in case:  # UI behaviour: covered by tests/test_streamlit_app.py
            consent_results.append({"id": case["id"], "result": "covered by test_new_question_after_offer_is_answered_normally"})
            continue
        answer = assistant.ask(case["problem"])
        consent_results.append({"id": case["id"], "confidence": answer.confidence,
                                "offer_shown": offers_draft(answer), "pass": not offers_draft(answer)})

    totals = {rule: sum(r["checks"][rule] for r in results) for rule in results[0]["checks"]}
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {"run_at": stamp, "totals": totals, "cases": len(results), "results": results,
           "consent_cases": consent_results}
    (OUT_DIR / f"{stamp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# Drafting evaluation {stamp}", "", "Unedited output. Rules: outputs/test_cases/drafting_eval.json", "",
             "| Rule | Passed |", "|---|---|"]
    lines += [f"| {rule} | {n}/{len(results)} |" for rule, n in totals.items()]
    lines += ["", "Consent cases: " + json.dumps(consent_results, ensure_ascii=False), ""]
    for r in results:
        lines += [f"## {r['id']} ({r['author']})", "", f"Checks: {r['checks']}", "",
                  f"Verified in answer: {r['answer_verified_sections']}", "",
                  f"Questions asked: {r['questions_asked']}", "", f"Must be blank (hand check): {r['must_be_blank (hand check)']}",
                  "", f"Unverified figures: {r['unverified_figures']}; law in body: {r['law_in_body']}", "",
                  "```", r["draft_text"], "```", "", f"Check before sending: {r['check_before_sending']}", ""]
    (OUT_DIR / f"{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nTotals:", totals, "\nConsent:", consent_results)
    print(f"Written to {OUT_DIR / stamp}.md")


if __name__ == "__main__":
    main()
