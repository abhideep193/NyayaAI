"""Tests for 'Explain my document' (app/services/document_explainer.py). No API calls.

The documents here are small made-up snippets, NOT the evaluation documents in
outputs/test_cases/document_eval.json (those are kept for measuring, not for tuning).
"""

from types import SimpleNamespace

from app.services.answer_generator import Citation
from app.services.document_explainer import (DocumentExplainer, DocumentExplanation, DocumentQuote,
                                             check_document_quote, check_figures, find_law_mentions)
from app.services.section_splitter import Section

SOURCES = [
    {"id": "posh_act_2013", "title": "The Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013"},
    {"id": "bns_2023", "title": "The Bharatiya Nyaya Sanhita, 2023"},
]


def make_section(source_id, number, text, act="Act"):
    return Section(source_id=source_id, act_title=act, section=number, heading="Heading", status="in_force",
                   chapter=None, page_start=3, page_end=3, text=text, citation=f"Section {number}, {act}")


SECTIONS = {
    "posh_act_2013:13": make_section("posh_act_2013", "13", "13. Inquiry report.—the Internal Committee shall provide a report of its findings to the employer within a period of ten days"),
    "bns_2023:351": make_section("bns_2023", "351", "351. Criminal intimidation.—Whoever threatens another with any injury to his person, reputation or property"),
}


def test_finds_named_sections_and_said_act():
    text = ("Complaint under section 13 of the Sexual Harassment of Women at Workplace (Prevention, "
            "Prohibition and Redressal) Act, 2013. See also section 13 of the said Act.")
    mentions = find_law_mentions(text, SOURCES, SECTIONS)
    assert [(m.section, m.section_id) for m in mentions] == [("13", "posh_act_2013:13")]


def test_law_not_in_nyayaai_is_marked_not_covered():
    text = "I shall file a complaint u/s 420 of the Some Other Act, 1999 within 10 days."
    [mention] = find_law_mentions(text, SOURCES, SECTIONS)
    assert mention.source_id is None and not mention.covered
    assert mention.act == "Some Other Act, 1999"


def test_known_act_but_unknown_section_is_not_covered():
    text = "Notice under section 9999 of the Bharatiya Nyaya Sanhita, 2023."
    [mention] = find_law_mentions(text, SOURCES, SECTIONS)
    assert mention.source_id == "bns_2023" and mention.section_id is None and not mention.covered


def test_subsection_kept_but_section_linked():
    text = "Sections: 351(2) of the Bharatiya Nyaya Sanhita, 2023"
    [mention] = find_law_mentions(text, SOURCES, SECTIONS)
    assert mention.section == "351(2)" and mention.section_id == "bns_2023:351"


def test_act_named_without_section_listed_once():
    text = "This is governed by the Bharatiya Nyaya Sanhita, 2023 and the Bharatiya Nyaya Sanhita, 2023."
    [mention] = find_law_mentions(text, SOURCES, SECTIONS)
    assert mention.section is None and mention.covered


def test_document_quote_check_tolerates_spacing_but_not_changes():
    doc = "pay a sum of Rs. 50,000\n(Rupees Fifty Thousand only) within 7 days"
    assert check_document_quote("pay a sum of Rs. 50,000 (Rupees Fifty Thousand only)", doc)
    assert not check_document_quote("pay a sum of Rs. 5,000", doc)


def test_figures_must_come_from_document():
    doc = "Hearing on 3 March 2027 at 10:30 AM. Pay Rs. 12,500 within 7 days."
    law = "within a period of ten days ... a fine of 5000 rupees"
    checks = check_figures("Hearing is on March 3, 2027 at 10:30 am; pay ₹12,500 within 7 days. "
                           "Fine of 5000 rupees. Pay by 10 March 2027 or Rs. 20,000 within 30 days.", doc, law)
    found = {c.text: c.found for c in checks}
    assert found["March 3, 2027"] and found["10:30 am"] and found["₹12,500"] and found["7 days"]
    assert found["5000 rupees"]  # from the law text given to the model
    assert not found["10 March 2027"] and not found["Rs. 20,000"] and not found["30 days"]


class FakeResponses:
    def __init__(self, parsed):
        self.parsed, self.calls = parsed, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed, usage=SimpleNamespace(input_tokens=900, output_tokens=300))


def make_explainer(parsed):
    client = SimpleNamespace(responses=FakeResponses(parsed))
    return DocumentExplainer(client, "test-model", SOURCES, list(SECTIONS.values())), client


DOC = ("NOTICE. You are required to attend the inquiry on 3 March 2027 under section 13 of the Sexual "
       "Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013. "
       "Also section 138 of the Negotiable Instruments Act, 1881.")


def test_pipeline_checks_quotes_figures_and_citations():
    parsed = DocumentExplanation(
        document_type="Inquiry notice",
        summary="You must attend on 3 March 2027. Reply by 9 March 2027.",  # 9 March is invented
        deadlines_and_amounts=[DocumentQuote(quote="attend the inquiry on 3 March 2027", meaning="Hearing date")],
        key_points=[DocumentQuote(quote="you are guilty", meaning="invented")],
        law_explanation="The committee reports its findings [posh_act_2013:13].",
        citations=[Citation(section_id="posh_act_2013:13", quote="provide a report of its findings to the employer",
                            supports="The committee reports its findings.")],
        next_steps=["Consult a lawyer."], confidence="high",
    )
    explainer, client = make_explainer(parsed)
    result = explainer.explain(DOC)

    assert result.deadlines_and_amounts[0].verified
    assert not result.key_points[0].verified  # not in the document
    assert [f.text for f in result.unverified_figures] == ["9 March 2027"]
    assert result.citations[0].verified
    assert result.confidence == "medium"  # lowered: an invented date and an unverified quote
    assert [m.covered for m in result.laws] == [True, False]

    prompt = client.responses.calls[0]["input"]
    assert "NOT AVAILABLE" in prompt and "Negotiable Instruments Act, 1881" in prompt
    assert "[posh_act_2013:13]" in prompt  # the named section's real text is given to the model
    assert client.responses.calls[0]["store"] is False


def test_long_document_is_cut_and_flagged():
    parsed = DocumentExplanation(document_type="x", summary="x", deadlines_and_amounts=[], key_points=[],
                                 law_explanation="", citations=[], next_steps=[], confidence="insufficient")
    explainer, _ = make_explainer(parsed)
    result = explainer.explain("word " * 10_000)
    assert result.truncated and result.confidence == "insufficient"


def test_durations_in_words_are_checked_too():
    doc = "Reply within fifteen days. The inquiry takes 90 days."
    found = {c.text: c.found for c in check_figures("Reply within 15 days; inquiry in ninety days; appeal in thirty days.", doc, "")}
    assert found["15 days"] and found["ninety days"] and not found["thirty days"]
