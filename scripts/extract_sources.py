"""Extract clean text from every PDF listed in data/legal_sources/sources.json.

Run from the project root (the NyayaAI folder):
    python -m scripts.extract_sources
"""

import hashlib
import json
from pathlib import Path

from app.services.pdf_extractor import build_document, extract_pages

SOURCES_DIR = Path("data/legal_sources")
OUTPUT_DIR = Path("data/processed")


def sha256_of(path: Path) -> str:
    """Compute the SHA-256 fingerprint of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sources_file = SOURCES_DIR / "sources.json"
    sources = json.loads(sources_file.read_text(encoding="utf-8"))["sources"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for source in sources:
        pdf_path = SOURCES_DIR / source["file"]

        # Refuse to process a PDF that differs from the one we verified.
        if sha256_of(pdf_path) != source["sha256"]:
            raise ValueError(f"{pdf_path} does not match the sha256 in sources.json")

        pages = extract_pages(pdf_path)
        text = build_document(pages)

        output_path = OUTPUT_DIR / f"{source['id']}.txt"
        output_path.write_text(text, encoding="utf-8")

        print(f"{source['title']}: {len(pages)} pages, {len(text):,} characters -> {output_path}")


if __name__ == "__main__":
    main()
