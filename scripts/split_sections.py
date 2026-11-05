"""Split each extracted Act (data/processed/<id>.txt) into sections.

Writes data/processed/<id>_sections.json and checks the result against the
Act's own table of contents.

Run from the project root (after scripts.extract_sources):
    python -m scripts.split_sections
"""

import json
from dataclasses import asdict
from pathlib import Path

from app.services.section_splitter import (
    compare_with_toc,
    parse_toc_numbers,
    split_sections,
    split_toc_and_body,
)

SOURCES_FILE = Path("data/legal_sources/sources.json")
PROCESSED_DIR = Path("data/processed")


def main() -> None:
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    all_ok = True

    for source in sources:
        document = (PROCESSED_DIR / f"{source['id']}.txt").read_text(encoding="utf-8")

        toc, body = split_toc_and_body(document)
        toc_numbers = parse_toc_numbers(toc)
        sections = split_sections(body, source_id=source["id"], act_title=source["title"])
        report = compare_with_toc(toc_numbers, sections)

        output_path = PROCESSED_DIR / f"{source['id']}_sections.json"
        output_path.write_text(
            json.dumps([asdict(s) for s in sections], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        omitted = sum(1 for s in sections if s.status == "omitted")
        print(f"\n{source['title']}")
        print(f"  table of contents lists: {len(toc_numbers)} sections")
        print(f"  found in body:           {len(sections)} sections ({omitted} omitted)")
        print(f"  missing:                 {report['missing'] or 'none'}")
        print(f"  unexpected:              {report['unexpected'] or 'none'}")
        print(f"  saved to:                {output_path}")

        if report["missing"] or report["unexpected"]:
            all_ok = False

    print("\nRESULT:", "all sections match the tables of contents" if all_ok else "MISMATCHES FOUND - check above")


if __name__ == "__main__":
    main()
