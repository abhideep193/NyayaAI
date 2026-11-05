"""Tests for the text-cleaning functions in app/services/pdf_extractor.py.

These use small fake page strings, so they run instantly and need no PDF.
"""

from app.services.pdf_extractor import build_document, clean_page


def test_clean_page_removes_page_number_and_watermark():
    raw = "9 \n \n(n) lecture includes address, speech and sermon; \nIndiaCode"

    assert clean_page(raw, page_number=9) == "(n) lecture includes address, speech and sermon;"


def test_clean_page_keeps_a_number_that_is_not_the_page_number():
    # "52" on page 9 is legal content (e.g. a section number), not a page number
    raw = "52 \nCertain acts not to be infringement of copyright."

    assert clean_page(raw, page_number=9).startswith("52")


def test_clean_page_works_without_watermark():
    # The Patents Act PDF has no watermark
    raw = "3 \nThe Patents Act, 1970"

    assert clean_page(raw, page_number=3) == "The Patents Act, 1970"


def test_clean_page_collapses_blank_lines():
    raw = "1 \nLine one\n \n \n \nLine two"

    assert clean_page(raw, page_number=1) == "Line one\n\nLine two"


def test_build_document_adds_page_markers():
    pages = ["1 \nFirst page IndiaCode", "2 \nSecond page"]

    document = build_document(pages)

    assert document == "[[PAGE 1]]\nFirst page\n\n[[PAGE 2]]\nSecond page\n"
