"""Tests for chunking (app/services/embeddings.py) and rank fusion (app/services/hybrid.py).

These tests do NOT load the embedding model, so they stay fast.
"""

from app.services.embeddings import chunk_section, chunk_text
from app.services.hybrid import reciprocal_rank_fusion
from app.services.retriever import SearchResult
from app.services.section_splitter import Section


def make_section(number: str, text: str = "Some text.") -> Section:
    return Section(
        source_id="example_act",
        act_title="The Example Act",
        section=number,
        heading=f"Heading {number}",
        status="in_force",
        chapter=None,
        page_start=1,
        page_end=1,
        text=text,
        citation=f"Section {number}, The Example Act",
    )


# --- chunking ---------------------------------------------------------------


def test_short_text_is_one_chunk():
    assert chunk_text("line one\nline two", max_chars=100) == ["line one\nline two"]


def test_long_text_is_split_between_lines_and_nothing_is_lost():
    lines = [f"line {i} " + "x" * 30 for i in range(10)]  # 10 lines of ~38 characters
    text = "\n".join(lines)

    chunks = chunk_text(text, max_chars=100)

    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "\n".join(chunks) == text  # joining the chunks gives back the original


def test_every_chunk_starts_with_act_section_and_heading():
    section = make_section("7", text="\n".join(["y" * 50] * 60))  # long section

    chunks = chunk_section(section)

    assert len(chunks) > 1
    assert all(chunk.startswith("The Example Act, Section 7: Heading 7\n") for chunk in chunks)


# --- reciprocal rank fusion -------------------------------------------------


def results(*numbers: str) -> list[SearchResult]:
    return [SearchResult(section=make_section(n), score=0.0) for n in numbers]


def test_section_ranked_well_by_both_lists_wins():
    keyword = results("1", "2", "3")
    meaning = results("4", "2", "5")

    fused = reciprocal_rank_fusion([keyword, meaning])

    # "2" is only 2nd in each list, but it is the only one found by BOTH.
    assert fused[0].section.section == "2"


def test_fusion_keeps_every_section_once():
    fused = reciprocal_rank_fusion([results("1", "2"), results("2", "3")])

    assert sorted(r.section.section for r in fused) == ["1", "2", "3"]
