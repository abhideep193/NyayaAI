"""Tests for app/services/citation_verifier.py."""

from app.services.citation_verifier import (
    CitationCheck,
    adjust_confidence,
    normalise_for_matching,
    verify_citation,
)
from app.services.section_splitter import Section

# Real-looking text, including PDF quirks: a split word ("und er"), curly quotes,
# an em dash and amendment markers ("7[sixty years]").
SECTION_TEXT = (
    "22. Term of copyright.—Copyright shall subsist in any “literary work” published und er "
    "the lifetime of the author until 7[sixty years] from the beginning of the calendar year."
)

SECTION = Section(
    source_id="copyright_act_1957",
    act_title="The Copyright Act, 1957",
    section="22",
    heading="Term of copyright",
    status="in_force",
    chapter=None,
    page_start=17,
    page_end=17,
    text=SECTION_TEXT,
    citation="Section 22, The Copyright Act, 1957",
)
RETRIEVED = {"copyright_act_1957:22": SECTION}


def check(section_id: str, quote: str) -> CitationCheck:
    return verify_citation(section_id, quote, supports="test claim", retrieved=RETRIEVED)


def test_exact_quote_is_verified():
    result = check("copyright_act_1957:22", "until sixty years from the beginning of the calendar year")

    assert result.verified
    assert result.citation == "Section 22, The Copyright Act, 1957"
    assert result.page == 17


def test_quote_matches_despite_split_words_curly_quotes_and_markers():
    # The model writes "under" and straight quotes; the PDF text has "und er", curly quotes, "7[".
    result = check("copyright_act_1957:22", 'any "literary work" published under the lifetime of the author')

    assert result.verified


def test_section_that_was_not_retrieved_is_rejected():
    result = check("copyright_act_1957:52", "until sixty years from the beginning of the calendar year")

    assert not result.verified
    assert "not among the sections" in result.reason


def test_invented_quote_is_rejected():
    # Changed one word: "seventy" instead of "sixty"
    result = check("copyright_act_1957:22", "until seventy years from the beginning of the calendar year")

    assert not result.verified
    assert "do not appear" in result.reason


def test_too_short_quote_is_rejected():
    assert not check("copyright_act_1957:22", "Copyright").verified


def test_normalise_removes_spaces_markers_and_case():
    assert normalise_for_matching("7[Sixty  years] — “x”") == 'sixtyyears-"x"'


def make_check(verified: bool) -> CitationCheck:
    return CitationCheck("id", "quote", "claim", verified=verified, reason="")


def test_confidence_drops_to_low_when_nothing_is_verified():
    assert adjust_confidence("high", [make_check(False), make_check(False)]) == "low"


def test_confidence_drops_to_low_when_there_are_no_citations():
    assert adjust_confidence("high", []) == "low"


def test_confidence_capped_at_medium_when_some_citations_fail():
    assert adjust_confidence("high", [make_check(True), make_check(False)]) == "medium"


def test_confidence_unchanged_when_all_verified():
    assert adjust_confidence("high", [make_check(True), make_check(True)]) == "high"


def test_insufficient_stays_insufficient():
    assert adjust_confidence("insufficient", []) == "insufficient"
