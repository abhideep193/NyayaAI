"""Step-by-step filing guides, shown by code after a draft (never written by the model).

The text, links and law quotes live in data/legal_sources/filing_guides.json, each checked on an
official source. tests/test_filing_guides.py checks every quote against the Act text.
"""

import json
from pathlib import Path

FILING_GUIDES_FILE = Path("data/legal_sources/filing_guides.json")


def load_filing_guides(path: Path = FILING_GUIDES_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def guide_for(guides: dict, guide_id: str | None) -> dict | None:
    """The guide with this id, or None (then only the free legal-aid line is shown)."""
    return next((g for g in guides["guides"] if g["id"] == guide_id), None)
