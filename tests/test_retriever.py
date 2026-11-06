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


def test_tokenize_reduces_word_forms_to_the_same_stem():
    assert tokenize("infringed") == tokenize("infringement") == tokenize("infringes")


def test_tokenize_splits_trademark_like_the_acts_do():
    assert tokenize("trademark") == tokenize("trade mark") == tokenize("trade-mark")


def test_search_matches_different_word_forms():
    # The question says "infringing", the section says "infringed"
    results = BM25Retriever(SECTIONS).search("infringing")

    assert results[0].section.section == "3"


def test_best_match_comes_first():
    results = BM25Retriever(SECTIONS).search("term of patent")

    assert results[0].section.section == "2"


def test_omitted_sections_are_never_returned():
    results = BM25Retriever(SECTIONS).search("old rule about patent")

    assert all(r.section.status != "omitted" for r in results)


def test_no_results_when_no_word_matches():
    assert BM25Retriever(SECTIONS).search("zebra") == []


def test_heading_words_count_more_than_body_words():
    sections = [
        # "renewal" appears twice, but only in the body
        make_section("10", "Fees", "Fees for renewal. A renewal fee is payable."),
        # "renewal" appears once in the body, but it is also the heading
        make_section("11", "Renewal", "Renewal is allowed every ten years."),
    ]

    with_boost = BM25Retriever(sections, heading_weight=5).search("renewal")
    without_boost = BM25Retriever(sections, heading_weight=0).search("renewal")

    assert with_boost[0].section.section == "11"
    assert without_boost[0].section.section == "10"


def test_top_k_limits_number_of_results():
    results = BM25Retriever(SECTIONS).search("patent mark act", top_k=1)

    assert len(results) == 1


def test_only_acts_of_enabled_domains_are_searched():
    from scripts.search import enabled_source_ids

    sources = [{"id": "copyright_act_1957", "domain": "ipr"}, {"id": "bns_2023", "domain": "criminal"}]
    assert enabled_source_ids(sources, ["ipr"]) == ["copyright_act_1957"]
    assert enabled_source_ids(sources, ["ipr", "criminal"]) == ["copyright_act_1957", "bns_2023"]
