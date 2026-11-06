"""Build NyayaAI's scope text from data, so areas of law can be switched on and off.

data/legal_sources/domains.json describes each area of law (IPR, criminal, ...).
sources.json says which Acts belong to which area. ENABLED_DOMAINS (app/config.py)
says which areas are switched on. From these we build:
  - the answer instructions (what NyayaAI covers, what to say for other areas)
  - the search-rewrite instructions (which Acts exist, which legal words to use)

With only "ipr" enabled, both prompts are exactly the ones NyayaAI used before
domains existed (checked by tests/test_domains.py), so IPR behaviour is unchanged.
"""

import json
from pathlib import Path

from app.services.answer_generator import SYSTEM_PROMPT_TEMPLATE
from app.services.query_rewriter import REWRITE_PROMPT_TEMPLATE

NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
                8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def load_domains(domains_file: Path) -> dict[str, dict]:
    return json.loads(domains_file.read_text(encoding="utf-8"))["domains"]


def _join(items: list[str], last: str = " and ") -> str:
    """["a", "b", "c"] -> "a, b and c"."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + last + items[-1]


def enabled(domains: dict[str, dict], enabled_ids: list[str]) -> list[dict]:
    unknown = [d for d in enabled_ids if d not in domains]
    if unknown:
        raise ValueError(f"ENABLED_DOMAINS has unknown domain(s) {unknown}; known: {list(domains)}")
    return [domains[d] for d in enabled_ids]


def build_system_prompt(domains: dict[str, dict], enabled_ids: list[str]) -> str:
    on = enabled(domains, enabled_ids)
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        intro=_join([f"{d['label']} ({d['covers']})" for d in on]),
        scope=_join([d["scope"] for d in on], last=", and "),
    )
    # Area-specific rules (e.g. tone and safety for criminal law), numbered after the 8 general rules.
    extra = [rule for d in on for rule in d.get("extra_rules", [])]
    for number, rule in enumerate(extra, start=9):
        prompt += f"\n{number}. {rule}"
    return prompt


def build_rewrite_prompt(domains: dict[str, dict], enabled_ids: list[str], sources: list[dict]) -> str:
    on = enabled(domains, enabled_ids)
    titles = [s["title"] for s in sources if s["domain"] in enabled_ids]
    acts = [("the" + t[3:]) if t.startswith("The ") else t for t in titles]  # "The Copyright Act" -> "the Copyright Act"
    words = [w for d in on for w in d["search_words"]]
    return REWRITE_PROMPT_TEMPLATE.format(
        count=NUMBER_WORDS.get(len(acts), str(len(acts))),
        acts=_join(acts),
        words=", ".join(f'"{w}"' for w in words),
        rewrite_scope=_join([d["rewrite_scope"] for d in on], last=", or "),
    )


ROUTING_INSTRUCTION = """
Also return "areas": the IDs of the areas of law the question is about, chosen only from:
{area_list}
Include every ID that applies. Return an empty list if none applies."""


def build_routing_prompt(domains: dict[str, dict], enabled_ids: list[str], sources: list[dict]) -> str:
    """The rewrite prompt plus the instruction to choose area(s) of law (used when 2+ areas are enabled)."""
    area_list = "\n".join(f"- {d}: {domains[d]['label']} ({domains[d]['covers']})" for d in enabled_ids)
    return build_rewrite_prompt(domains, enabled_ids, sources) + ROUTING_INSTRUCTION.format(area_list=area_list)
