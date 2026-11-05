"""Extract and clean text from official legal PDFs (downloaded from India Code)."""

from pathlib import Path

from pypdf import PdfReader

# India Code stamps this watermark at the end of every page of some PDFs.
WATERMARK = "IndiaCode"


def extract_pages(pdf_path: Path) -> list[str]:
    """Return the raw text of every page in the PDF, in order."""
    reader = PdfReader(pdf_path)
    # extract_text() can return None for an empty page; use "" instead.
    return [page.extract_text() or "" for page in reader.pages]


def clean_page(text: str, page_number: int) -> str:
    """Remove the page number and watermark from one page, and tidy blank lines.

    The legal text itself is never changed.
    """
    # Split into lines and remove trailing spaces from each line.
    lines = [line.rstrip() for line in text.strip().splitlines()]

    # 1. Remove the page number if it is the first line, e.g. "9".
    if lines and lines[0].strip() == str(page_number):
        lines.pop(0)

    # 2. Remove the watermark from the end of the last line.
    if lines and lines[-1].endswith(WATERMARK):
        lines[-1] = lines[-1][: -len(WATERMARK)].rstrip()

    # 3. Collapse runs of blank lines into a single blank line.
    cleaned: list[str] = []
    for line in lines:
        is_blank = line.strip() == ""
        previous_is_blank = not cleaned or cleaned[-1] == ""
        if is_blank and previous_is_blank:
            continue
        cleaned.append("" if is_blank else line)

    return "\n".join(cleaned).strip()


def build_document(pages: list[str]) -> str:
    """Clean every page and join them, marking where each PDF page begins.

    The [[PAGE n]] markers let us later tell a user which page of the
    official PDF a section came from.
    """
    parts = []
    for page_number, text in enumerate(pages, start=1):
        parts.append(f"[[PAGE {page_number}]]\n{clean_page(text, page_number)}")
    return "\n\n".join(parts) + "\n"
