"""Split the cleaned text of an Indian Act (from India Code) into its sections.

Input:  the text produced by pdf_extractor.build_document(), with [[PAGE n]] markers.
Output: a list of Section objects, one per section of the Act.
"""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Patterns (regular expressions) that describe the layout of an India Code Act
# ---------------------------------------------------------------------------

# "[[PAGE 9]]" -> captures 9
PAGE_MARKER = re.compile(r"^\[\[PAGE (\d+)\]\]$")

# A line that might start a section, e.g.
#   "52. Certain acts not to be infringement of copyright.—(1) ..."
#   "1[52A. Particulars to be included in ..."   (1[ = "inserted, see footnote 1")
# Captures: (1) the section number such as "52" or "52A", (2) the rest of the line.
SECTION_START = re.compile(r"^\s*(?:\d+\[)?(\d+[A-Z]*)\.\s*(.*)$")

# Footnotes also start with "number. ", e.g. "1. Subs. by Act 38 of 1994 ...".
# If the text after the number starts with one of these, it is a footnote.
FOOTNOTE_START = re.compile(
    r"^(Subs\.|Ins\.|Rep\.|Omitted|Added|The words|Cl\.|Clause|Sub-section"
    r"|Section|Proviso|Vide|See |Came into force|Renumbered)"
)

# "CHAPTER XI" or "1[CHAPTER VIIA" -> captures "XI" / "VIIA"
CHAPTER_START = re.compile(r"^\s*(?:\d+\[)?CHAPTER\s+([IVXLC]+[A-Z]?)\b")

# Table of contents entry, e.g. "52A. Particulars to be included ..." -> captures "52A"
TOC_ENTRY = re.compile(r"^\s*(\d+[A-Z]*)\.\s+\S")

# The law itself starts at the enacting formula ...
BODY_START = re.compile(r"^BE it enacted", re.IGNORECASE | re.MULTILINE)
# ... and ends where the Schedule or the Statement of Objects and Reasons begins.
# \b = "whole word only", so that "THE SCHEDULED CASTES ..." (an Act's own title) does not count as "THE SCHEDULE".
BODY_END = re.compile(r"^\s*(THE SCHEDULE\b|STATEMENT OF OBJECTS AND REASONS)", re.MULTILINE)

TOC_START = "ARRANGEMENT OF SECTIONS"
# The dash that ends a section heading in the body. Most Acts use the long dash "—";
# some (IT Act 2000, sections 1-2 of the BNS) use the shorter "–" or "––".
DASH = re.compile(r"[—–]")
# A heading's end: full stop, optional space, then the dash, e.g. "... under the Act. —"
HEADING_END = re.compile(r"\.\s*[—–]")
MAX_HEADING_LENGTH = 250  # a heading longer than this is not a heading


@dataclass
class Section:
    """One section of an Act, with everything needed to cite it."""

    source_id: str
    act_title: str
    section: str  # "52", "52A"
    heading: str  # "Certain acts not to be infringement of copyright"
    status: str  # "in_force" or "omitted"
    chapter: str | None  # "CHAPTER XI — INFRINGEMENT OF COPYRIGHT"
    page_start: int | None  # page of the official PDF where it starts
    page_end: int | None  # page where it ends
    text: str  # the full original text of the section
    citation: str  # "Section 52, The Copyright Act, 1957"


# ---------------------------------------------------------------------------
# Step 1: separate the table of contents from the body of the Act
# ---------------------------------------------------------------------------


def split_toc_and_body(document: str) -> tuple[str, str]:
    """Return (table_of_contents, body) of an Act."""
    start = BODY_START.search(document)
    if start is None:
        raise ValueError("Could not find 'BE it enacted' - is this an India Code Act?")

    # Begin the body at the page marker just before "BE it enacted", so the
    # body knows which page it starts on.
    body_start = start.start()
    markers_before = list(re.finditer(r"^\[\[PAGE \d+\]\]$", document[:body_start], re.MULTILINE))
    if markers_before:
        body_start = markers_before[-1].start()

    toc = document[:body_start]
    body = document[body_start:]

    # Keep only the part of the table of contents after "ARRANGEMENT OF SECTIONS".
    if TOC_START in toc:
        toc = toc.split(TOC_START, 1)[1]

    # Cut off the Schedule / Statement of Objects and Reasons at the end.
    end = BODY_END.search(body)
    if end is not None:
        body = body[: end.start()]

    return toc, body


def parse_toc_numbers(toc: str) -> list[str]:
    """List every section number in the table of contents, in order."""
    numbers = []
    for line in toc.splitlines():
        match = TOC_ENTRY.match(line)
        if match:
            numbers.append(match.group(1))
    return numbers


# ---------------------------------------------------------------------------
# Step 2: find where each section starts in the body
# ---------------------------------------------------------------------------


def _clean_heading(raw: str) -> str:
    """Tidy a heading: drop amendment markers like '2[' and ']', extra spaces, final '.'."""
    heading = re.sub(r"\d+\[|\[|\]", "", raw)
    heading = " ".join(heading.split())
    return heading.rstrip(" .")


def _sort_key(number: str) -> tuple[int, str]:
    """Turn "52A" into (52, "A") so section numbers can be compared."""
    match = re.match(r"(\d+)([A-Z]*)", number)
    return int(match.group(1)), match.group(2)


def match_section_start(lines: list[str], index: int) -> tuple[str, str, str] | None:
    """If lines[index] starts a section, return (number, heading, status); else None."""
    match = SECTION_START.match(lines[index])
    if match is None:
        return None

    number, rest = match.groups()

    # A heading can wrap onto the next line, so look at the next two lines too
    # (skipping page markers).
    following = [line for line in lines[index + 1 : index + 3] if not PAGE_MARKER.match(line)]
    lookahead = " ".join([rest] + following)

    footnote = FOOTNOTE_START.match(rest)
    if footnote:
        # Some real headings begin with "Section", e.g. SC/ST Act s.18:
        # "18. Section 438 of the Code not to apply ... under the Act. —Nothing in ..."
        # They end with a heading dash; footnotes ("1. Section 3 renumbered ...") do not.
        heading_end = HEADING_END.search(lookahead)
        starts_with_section = footnote.group(1) == "Section"
        if not (starts_with_section and heading_end and heading_end.start() <= MAX_HEADING_LENGTH):
            return None

    # Omitted section: "25. [Term of copyright in photographs .] Omitted by ..."
    if rest.startswith("["):
        closing = lookahead.find("]")
        if closing != -1 and "Omitted" in lookahead[closing : closing + 40]:
            return number, _clean_heading(lookahead[1:closing]), "omitted"
        return None

    # Normal section: "52. Certain acts not to be infringement of copyright .—(1) ..."
    dash = DASH.search(lookahead)
    if dash is None or dash.start() > MAX_HEADING_LENGTH:
        return None
    return number, _clean_heading(lookahead[: dash.start()]), "in_force"


# ---------------------------------------------------------------------------
# Step 3: walk through the body line by line and build the sections
# ---------------------------------------------------------------------------


def _fix_merged_footnote_number(start: tuple[str, str, str], toc_numbers: set[str]):
    """Undo a footnote mark glued onto a section number.

    In the IT Act PDF, "2[66A." (footnote 2) is printed as "266A.". If "266A" is not in the
    table of contents but "66A" is, the section is 66A.
    """
    number, heading, status = start
    if toc_numbers and number not in toc_numbers and number[1:] in toc_numbers:
        return number[1:], heading, status
    return start


def split_sections(body: str, source_id: str, act_title: str,
                   toc_numbers: list[str] | None = None) -> list[Section]:
    """Split the body of an Act into Section objects.

    toc_numbers (optional): the section numbers from the Act's table of contents,
    used only to repair numbers damaged in the PDF (see _fix_merged_footnote_number).
    """
    known_numbers = set(toc_numbers or [])
    lines = body.splitlines()
    sections: list[Section] = []
    current_lines: list[str] = []  # text lines of the section being built

    page: int | None = None
    chapter: str | None = None
    expecting_chapter_title = False
    last_key: tuple[int, str] | None = None

    for index, line in enumerate(lines):
        # Page markers: remember the page, but do not put them in the text.
        page_marker = PAGE_MARKER.match(line)
        if page_marker:
            page = int(page_marker.group(1))
            continue

        # Chapter headings: "CHAPTER XI" followed by a title line.
        chapter_match = CHAPTER_START.match(line)
        if chapter_match:
            chapter = f"CHAPTER {chapter_match.group(1)}"
            expecting_chapter_title = True
            continue
        if expecting_chapter_title and line.strip():
            chapter = f"{chapter} — {line.strip()}"
            expecting_chapter_title = False
            continue

        # A new section starts here? Section numbers only go up, so anything
        # numbered lower than the previous section is not a new section.
        start = match_section_start(lines, index)
        if start is not None:
            start = _fix_merged_footnote_number(start, known_numbers)
        if start is not None and (last_key is None or _sort_key(start[0]) > last_key):
            number, heading, status = start
            current_lines = [line]
            sections.append(
                Section(
                    source_id=source_id,
                    act_title=act_title,
                    section=number,
                    heading=heading,
                    status=status,
                    chapter=chapter,
                    page_start=page,
                    page_end=page,
                    text=line.strip(),
                    citation=f"Section {number}, {act_title}",
                )
            )
            last_key = _sort_key(number)
            continue

        # Otherwise this line belongs to the current section.
        if sections:
            current_lines.append(line)
            sections[-1].page_end = page
            sections[-1].text = "\n".join(current_lines).strip()

    return sections


def compare_with_toc(toc_numbers: list[str], sections: list[Section]) -> dict[str, list[str]]:
    """Check the sections we found against the table of contents."""
    found = [section.section for section in sections]
    return {
        "missing": [number for number in toc_numbers if number not in found],
        "unexpected": [number for number in found if number not in toc_numbers],
    }
