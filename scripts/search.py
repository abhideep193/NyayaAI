"""Search the IPR Acts from the terminal.

Run from the project root:
    python -m scripts.search "someone copied my brand logo"
"""

import json
import sys
from pathlib import Path

from app.services.retriever import BM25Retriever, load_sections

SOURCES_FILE = Path("data/legal_sources/sources.json")
PROCESSED_DIR = Path("data/processed")


def build_retriever() -> BM25Retriever:
    """Load every Act listed in sources.json and build the search index."""
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    sections = load_sections(PROCESSED_DIR, [source["id"] for source in sources])
    return BM25Retriever(sections)


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m scripts.search "your question"')
        return

    question = " ".join(sys.argv[1:])
    retriever = build_retriever()

    print(f"Question: {question}\n")
    for rank, result in enumerate(retriever.search(question, top_k=5), start=1):
        s = result.section
        print(f"{rank}. [{result.score:.2f}] {s.citation} - {s.heading} (page {s.page_start})")


if __name__ == "__main__":
    main()
