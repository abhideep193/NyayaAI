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
# "1[53A." and, in the older PDFs (Transfer of Property Act), "1 [53A." and "3[119 ." with spaces.
SECTION_START = re.compile(r"^\s*(?:\d+\s?\[)?(\d+[A-Z]*)\s?\.\s*(.*)$")

# State amendments printed inside a Central Act (e.g. 41 blocks in the Registration Act, 1908):
#   STATE AMENDMENT / Karnataka / Insertion of new section 18A ... / [Vide Karnataka Act 55 of 1976, s. 16]
# They change the law ONLY in that State, so they must not be quoted as law for all of India.
# When a source asks for it (sources.json "strip_state_amendments": true) their text is removed and the
# section gets a note naming the States instead.
STATE_AMENDMENT_START = re.compile(r"^\s*STATE AMENDMENTS?\s*$")
STATES = {
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Orissa", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir",
    "Puducherry", "Pondicherry", "Chandigarh", "Ladakh", "Andaman and Nicobar Islands", "Lakshadweep",
    "Dadra and Nagar Haveli", "Daman and Diu", "Bombay", "Madras", "Mysore",
}

# Footnotes also start with "number. ", e.g. "1. Subs. by Act 38 of 1994 ...".
# If the text after the number starts with one of these, it is a footnote.
FOOTNOTE_START = re.compile(
    r"^(Subs\.|Ins\.|Rep\.|Omitted|Added|The words|Cl\.|Clause|Sub-section"
    r"|Section|Proviso|Vide|See |Came into force|Renumbered"
    # Older Acts' footnotes about where the Act applies, e.g. Transfer of Property Act footnote
    # "5. The Act has been extended to — The Presidency of Bombay ..." (it contains a dash, so
    # without this it was taken for section 5 and swallowed the real sections 2-5).
    r"|The Act has been|This Act has been|The application of this Act|The Act was|This Act was)"
)

# "CHAPTER XI" or "1[CHAPTER VIIA" -> captures "XI" / "VIIA"
CHAPTER_START = re.compile(r"^\s*(?:\d+\[)?CHAPTER\s+([IVXLC]+[A-Z]?)\b")

# Table of contents entry, e.g. "52A. Particulars to be included ..." -> captures "52A"
TOC_ENTRY = re.compile(r"^\s*(\d+[A-Z]*)\.\s+\S")

# The law itself starts at the enacting formula ...
BODY_START = re.compile(r"^BE it enacted", re.IGNORECASE | re.MULTILINE)
# Older Acts (Transfer of Property Act 1882, Registration Act 1908) have a preamble instead:
# "WHEREAS it is expedient ...; It is hereby enacted as follows". Used only when "BE it enacted" is absent.
OLD_BODY_START = re.compile(r"it\s+is\s+hereby\s+enacted", re.IGNORECASE)
# ... and ends where the Schedule or the Statement of Objects and Reasons begins.
# \b = "whole word only", so that "THE SCHEDULED CASTES ..." (an Act's own title) does not count as "THE SCHEDULE".
# Also "THE FIRST SCHEDULE" (BNSS) and "1[THE FIRST SCHEDULE" (IT Act, "1[" = amendment mark):
# without this, the BNSS's 199,000-character schedules were glued onto section 531.
BODY_END = re.compile(
    r"^\s*(?:\d+\[)?\[?(THE (?:(?:FIRST|SECOND|THIRD|FOURTH|FIFTH) )?SCHEDULE\b|STATEMENT OF OBJECTS AND REASONS)",
    re.MULTILINE,
)

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
    start = BODY_START.search(document) or OLD_BODY_START.search(document)
    if start is None:
        raise ValueError("Could not find 'BE it enacted' or 'it is hereby enacted' - is this an India Code Act?")

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
        after = lookahead[closing : closing + 40]
        # Newer Acts write "Omitted by ..."; older ones "Rep. by ..." or "Repealed. by ..." (also stored as omitted).
        if closing != -1 and ("Omitted" in after or re.search(r"\][\s—–-]*(Rep\.|Repealed)", after)):
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
                   toc_numbers: list[str] | None = None, strip_state_amendments: bool = False) -> list[Section]:
    """Split the body of an Act into Section objects.

    toc_numbers (optional): the section numbers from the Act's table of contents,
    used only to repair numbers damaged in the PDF (see _fix_merged_footnote_number),
    and to recognise the end of a State amendment block.
    strip_state_amendments: remove State amendment blocks, noting the States (see STATE_AMENDMENT_START).
    """
    known_numbers = set(toc_numbers or [])
    lines = body.splitlines()
    sections: list[Section] = []
    current_lines: list[str] = []  # text lines of the section being built

    page: int | None = None
    chapter: str | None = None
    expecting_chapter_title = False
    last_key: tuple[int, str] | None = None
    in_state_amendment = False
    amended_in: dict[int, list[str]] = {}  # index in `sections` -> States that amended it

    for index, line in enumerate(lines):
        # Page markers: remember the page, but do not put them in the text.
        page_marker = PAGE_MARKER.match(line)
        if page_marker:
            page = int(page_marker.group(1))
            continue

        if strip_state_amendments:
            if STATE_AMENDMENT_START.match(line):
                in_state_amendment = True
                continue
            if in_state_amendment:
                # The block ends where the next real section (one listed in the table of contents,
                # numbered higher than the last) or a new chapter begins.
                start = match_section_start(lines, index)
                if start is not None:
                    start = _fix_merged_footnote_number(start, known_numbers)
                ends_block = CHAPTER_START.match(line) or (
                    start is not None and (not known_numbers or start[0] in known_numbers)
                    and (last_key is None or _sort_key(start[0]) > last_key))
                if not ends_block:
                    state = line.strip().rstrip(".").strip()
                    if state in STATES and sections:
                        names = amended_in.setdefault(len(sections) - 1, [])
                        if state not in names:
                            names.append(state)
                    continue
                in_state_amendment = False

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

    for position, states in amended_in.items():
        sections[position].text += (
            f"\n[NOTE ADDED BY NYAYAAI: this section has been amended for {', '.join(states)} by State law. "
            "Those State amendments are not included here; in those States the rule may be different.]")
    return sections


def compare_with_toc(toc_numbers: list[str], sections: list[Section]) -> dict[str, list[str]]:
    """Check the sections we found against the table of contents."""
    found = [section.section for section in sections]
    return {
        "missing": [number for number in toc_numbers if number not in found],
        "unexpected": [number for number in found if number not in toc_numbers],
    }
