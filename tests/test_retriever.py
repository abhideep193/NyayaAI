"""Tests for app/services/retriever.py, using a few fake sections."""

from app.services.retriever import BM25Retriever, tokenize
from app.services.section_splitter import Section


def make_section(number: str, heading: str, text: str, status: str = "in_force") -> Section:
    return Section(
        source_id="example_act",
        act_title="The Example Act",
        section=number,
        heading=heading,
        status=status,
        chapter=None,
        page_start=1,
        page_end=1,
        text=text,
        citation=f"Section {number}, The Example Act",
    )


SECTIONS = [
    make_section("1", "Short title", "This Act may be called the Example Act."),
    make_section("2", "Term of patent", "The term of every patent shall be twenty years."),
    make_section("3", "Infringement", "A registered mark is infringed by unauthorised use."),
    make_section("4", "Old rule about patent", "Omitted.", status="omitted"),
]


def test_tokenize_lowercases_and_removes_stopwords():
    assert tokenize("What is the Term of a Patent?") == ["term", "patent"]


def test_best_match_comes_first():
    results = BM25Retriever(SECTIONS).search("term of patent")

    assert results[0].section.section == "2"


def test_omitted_sections_are_never_returned():
    results = BM25Retriever(SECTIONS).search("old rule about patent")

    assert all(r.section.status != "omitted" for r in results)


def test_no_results_when_no_word_matches():
    assert BM25Retriever(SECTIONS).search("zebra") == []


def test_top_k_limits_number_of_results():
    results = BM25Retriever(SECTIONS).search("patent mark act", top_k=1)

    assert len(results) == 1
