"""Tests for app/services/section_splitter.py, using a small fake Act."""

from app.services.section_splitter import (
    compare_with_toc,
    parse_toc_numbers,
    split_sections,
    split_toc_and_body,
)

# A tiny made-up Act that copies the layout of India Code PDFs:
# table of contents, enacting formula, chapters, an inserted section (1[2A.),
# a footnote, an omitted section, a page break, and a Statement of Objects at the end.
FAKE_ACT = """[[PAGE 1]]
The Example Act, 2000
ARRANGEMENT OF SECTIONS
CHAPTER I
PRELIMINARY
1. Short title.
2. Definitions.
2A. Special rule.
3. [Omitted.]

[[PAGE 2]]
BE it enacted by Parliament as follows:—
CHAPTER I
PRELIMINARY
1. Short title.—This Act may be called the Example Act, 2000.
2. Definitions.—In this Act, "work" means any work.
1[2A. Special rule.—A special rule applies.]
1. Ins. by Act 5 of 2010, s. 2 (w.e.f. 1-1-2011).

[[PAGE 3]]
CHAPTER II
OTHER MATTERS
3. [Old rule.] Omitted by Act 5 of 2010.
STATEMENT OF OBJECTS AND REASONS
1. This Bill aims to do something.—Explanation here.
"""


def split_fake_act():
    toc, body = split_toc_and_body(FAKE_ACT)
    sections = split_sections(body, source_id="example_act_2000", act_title="The Example Act, 2000")
    return toc, sections


def test_table_of_contents_numbers():
    toc, _ = split_fake_act()

    assert parse_toc_numbers(toc) == ["1", "2", "2A", "3"]


def test_finds_every_section_in_order():
    _, sections = split_fake_act()

    assert [s.section for s in sections] == ["1", "2", "2A", "3"]


def test_section_details():
    _, sections = split_fake_act()
    section_2 = sections[1]

    assert section_2.heading == "Definitions"
    assert section_2.status == "in_force"
    assert section_2.chapter == "CHAPTER I — PRELIMINARY"
    assert section_2.page_start == 2
    assert section_2.citation == "Section 2, The Example Act, 2000"
    assert section_2.text == '2. Definitions.—In this Act, "work" means any work.'


def test_inserted_section_and_footnote_is_not_a_section():
    _, sections = split_fake_act()
    section_2a = sections[2]

    # "1[2A." is recognised as section 2A ...
    assert section_2a.heading == "Special rule"
    # ... and the footnote "1. Ins. by ..." stays inside its text, not as a new section 1
    assert "1. Ins. by Act 5 of 2010" in section_2a.text


def test_omitted_section():
    _, sections = split_fake_act()
    section_3 = sections[3]

    assert section_3.status == "omitted"
    assert section_3.heading == "Old rule"
    assert section_3.chapter == "CHAPTER II — OTHER MATTERS"
    assert section_3.page_start == 3


def test_statement_of_objects_is_not_part_of_the_act():
    _, sections = split_fake_act()

    assert all("This Bill aims" not in s.text for s in sections)


def test_compare_with_toc_reports_problems():
    _, sections = split_fake_act()

    report = compare_with_toc(["1", "2", "2A", "3", "4"], sections[:3])

    assert report == {"missing": ["3", "4"], "unexpected": []}
