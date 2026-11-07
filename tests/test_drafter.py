"""Tests for drafting letters/complaints (app/services/drafter.py). No API calls.

Made-up snippets only; the evaluation conversations in outputs/test_cases/drafting_eval.json are
kept for measuring, not for tuning.
"""

from types import SimpleNamespace

from app.services.citation_verifier import CitationCheck
from app.services.drafter import (DRAFT_LABEL, MAX_QUESTIONS, DraftDocument, Drafter, DraftPlan, LawReference,
                                  is_consent)
from app.services.section_splitter import Section


def make_section(source_id, number, text):
    return Section(source_id=source_id, act_title="Act", section=number, heading="Heading", status="in_force",
                   chapter=None, page_start=1, page_end=1, text=text, citation=f"Section {number}, Act")


SECTIONS = {
    "consumer_protection_act_2019:39": make_section(
        "consumer_protection_act_2019", "39",
        "39. Findings of District Commission.—the District Commission may order the opposite party to replace "
        "the goods with new goods of similar description"),
    "consumer_protection_act_2019:2": make_section(
        "consumer_protection_act_2019", "2", "2. Definitions.—refusing, after selling goods, to take back or "
                                             "withdraw defective goods"),
}


def answer_with(verified_ids, unverified_ids=()):
    checks = [CitationCheck(i, "q", "s", True, "ok") for i in verified_ids]
    checks += [CitationCheck(i, "q", "s", False, "no") for i in unverified_ids]
    return SimpleNamespace(answer="You may complain to the District Commission.", citations=checks)


class FakeClient:
    """Returns the queued parsed objects in order, and records what was sent."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.sent = []
        self.responses = self

    def parse(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(output_parsed=self.outputs.pop(0),
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


PLAN = DraftPlan(document_type="consumer_complaint", guide="consumer_complaint", recipient="the seller",
                 questions=[])


def write(document, answer=None, problem="My washing machine bought for ₹35,000 stopped working.",
          facts="I bought it on 2 October 2026."):
    drafter = Drafter(FakeClient(document), "model", SECTIONS)
    return drafter.write(problem, answer or answer_with(["consumer_protection_act_2019:39"]), PLAN,
                         consent="yes", facts=facts)


def test_only_law_verified_in_the_answer_is_offered_and_kept():
    doc = DraftDocument(
        title="Complaint", body="I request a replacement under the provisions listed below.",
        law_references=[
            LawReference(section_id="consumer_protection_act_2019:39",
                         quote="may order the opposite party to replace the goods", relevance="replacement"),
            # Section 2 exists in NyayaAI but was NOT verified in the answer: must be rejected.
            LawReference(section_id="consumer_protection_act_2019:2",
                         quote="to take back or withdraw defective goods", relevance="refusal"),
        ],
        check_before_sending=["Check the date"])
    draft = write(doc, answer_with(["consumer_protection_act_2019:39"], ["consumer_protection_act_2019:2"]))
    assert [c.section_id for c in draft.verified_law] == ["consumer_protection_act_2019:39"]
    assert [c.section_id for c in draft.removed_law] == ["consumer_protection_act_2019:2"]
    text = draft.full_text()
    assert "Section 39, Act" in text and "Section 2, Act" not in text


def test_law_prompt_contains_only_verified_sections():
    doc = DraftDocument(title="T", body="B", law_references=[], check_before_sending=[])
    drafter = Drafter(FakeClient(doc), "model", SECTIONS)
    drafter.write("p", answer_with(["consumer_protection_act_2019:39"], ["consumer_protection_act_2019:2"]), PLAN)
    sent = drafter.client.sent[0]["input"]
    assert "[consumer_protection_act_2019:39]" in sent
    assert "[consumer_protection_act_2019:2]" not in sent


def test_misquoted_law_is_rejected():
    doc = DraftDocument(title="T", body="B", check_before_sending=[], law_references=[
        LawReference(section_id="consumer_protection_act_2019:39", quote="must refund the full price with interest",
                     relevance="x")])
    draft = write(doc)
    assert draft.verified_law == [] and len(draft.removed_law) == 1


def test_invented_figures_are_flagged_and_given_ones_pass():
    doc = DraftDocument(
        title="Complaint",
        body="I bought the machine on 2 October 2026 for Rs. 35,000. It failed on 9 October 2026. "
             "Please pay Rs. 5,000 compensation within 15 days.",
        law_references=[], check_before_sending=[])
    draft = write(doc)
    flagged = {f.text for f in draft.unverified_figures}
    assert "9 October 2026" in flagged and "Rs. 5,000" in flagged and "15 days" in flagged
    assert "2 October 2026" not in flagged and "Rs. 35,000" not in flagged


def test_blanks_are_listed_and_law_in_body_is_flagged():
    doc = DraftDocument(
        title="Complaint to [SHOP NAME]",
        body="From: [YOUR NAME], [YOUR ADDRESS]\nUnder Section 39 of the Consumer Protection Act, 2019 ...",
        law_references=[], check_before_sending=[])
    draft = write(doc)
    assert draft.blanks == ["[SHOP NAME]", "[YOUR NAME]", "[YOUR ADDRESS]"]
    assert draft.law_in_body  # section numbers belong only in the verified block


def test_plan_caps_questions_and_never_needs_personal_details_in_prompt():
    plan = DraftPlan(document_type="landlord_letter", guide="landlord_letter", recipient="the landlord",
                     questions=["When did you move out?", "", "Q2", "Q3", "Q4", "Q5"])
    drafter = Drafter(FakeClient(plan), "model", SECTIONS)
    result = drafter.plan("My landlord kept my deposit", answer_with([]), consent="yes")
    assert len(result.plan.questions) == MAX_QUESTIONS and "" not in result.plan.questions
    assert result.label == "Letter to the landlord"
    assert "NEVER ask for names, addresses, phone numbers" in drafter.client.sent[0]["instructions"]


def test_draft_label_says_draft_and_not_filed():
    assert DRAFT_LABEL.startswith("DRAFT")
    assert "does not send or file anything" in DRAFT_LABEL


def test_typed_consent():
    for yes in ["yes", "Yes, please help me", "haan please, maine 1 October ko flat khali kiya", "ok", "हाँ",
                "sure.", "theek hai"]:
        assert is_consent(yes), yes
    for other in ["Can the landlord also keep my furniture?", "yesterday he called me", "no thanks", "",
                  "okra prices", "hai kya koi rasta?"]:
        assert not is_consent(other), other


def test_hindi_durations_written_by_the_person_count():
    from app.services.document_explainer import check_figures

    checks = check_figures("The agreement was for 11 months; I left 3 days ago.",
                           "Rent agreement 11 mahine ka tha, 3 din pehle chhoda", "")
    assert all(c.found for c in checks) and len(checks) == 2
    assert not check_figures("for 12 months", "11 mahine", "")[0].found  # a different number is still flagged


def test_quotes_in_the_letter_are_cleaned_for_display_only():
    from app.services.citation_verifier import normalise_for_matching
    from app.services.drafter import clean_quote

    raw = "(c) in the case of an artistic work,—\n5[(i) to reproduce the work"
    assert clean_quote(raw) == "(c) in the case of an artistic work,— (i) to reproduce the work"
    assert normalise_for_matching(clean_quote(raw)) == normalise_for_matching(raw)  # same words
