"""Tests for app/domains.py: prompts built from the enabled areas of law."""

import json
from pathlib import Path

import pytest

from app.domains import build_rewrite_prompt, build_system_prompt, load_domains

ROOT = Path(__file__).parent.parent
DOMAINS = load_domains(ROOT / "data/legal_sources/domains.json")
SOURCES = json.loads((ROOT / "data/legal_sources/sources.json").read_text(encoding="utf-8"))["sources"]
FROZEN = json.loads((Path(__file__).parent / "fixtures/ipr_prompts.json").read_text(encoding="utf-8"))


def test_ipr_only_prompts_are_exactly_the_old_ones():
    # IPR behaviour must not change: same prompts as before domains existed (commit d8ad54a).
    assert build_system_prompt(DOMAINS, ["ipr"]) == FROZEN["system_prompt"]
    assert build_rewrite_prompt(DOMAINS, ["ipr"], SOURCES) == FROZEN["rewrite_prompt"]


def test_criminal_enabled_prompts_name_criminal_law_and_its_acts():
    system = build_system_prompt(DOMAINS, ["ipr", "criminal"])
    assert "copyright, trade marks and patents, and criminal law (" in system
    assert "Use ONLY the SOURCES" in system  # the rules are unchanged

    rewrite = build_rewrite_prompt(DOMAINS, ["ipr", "criminal"], SOURCES)
    assert "13 Indian Acts" in rewrite  # 3 IPR + 10 criminal (NDPS and JJ added 2026-11-08)
    assert "the Bharatiya Nyaya Sanhita, 2023" in rewrite
    assert '"offence"' in rewrite


def test_unknown_domain_is_an_error_not_silently_ignored():
    with pytest.raises(ValueError, match="unknown domain"):
        build_system_prompt(DOMAINS, ["ipr", "crimnal"])


def test_every_source_belongs_to_a_known_domain():
    assert {s["domain"] for s in SOURCES} <= set(DOMAINS)


def test_criminal_rules_are_added_only_when_criminal_is_enabled():
    ipr = build_system_prompt(DOMAINS, ["ipr"])
    both = build_system_prompt(DOMAINS, ["ipr", "criminal"])
    assert "Never promise an outcome" not in ipr
    assert "\n9. For crimes, violence" in both
    assert "Do not write helpline or emergency numbers yourself" in both
