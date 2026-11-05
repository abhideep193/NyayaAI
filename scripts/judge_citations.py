"""EVALUATION ONLY: check whether citations are used in the right legal context.

The citation verifier proves a quote EXISTS in a section. It cannot tell whether
the quote is used correctly. This script asks a separate, stronger "judge" model
to read each answer next to the FULL text of every section it cites, and grade:
  - each citation: supported / partially_supported / not_supported / out_of_context
  - claims in the answer that go beyond what the cited sections establish
  - provisions that are combined incorrectly

The judge is itself an AI and can be wrong: its verdicts must be spot-checked
by a human. This is a measurement tool, not part of the NyayaAI app.

Usage (costs money - see the estimate it prints):
    python -m scripts.judge_citations outputs/answer_eval/<results file>.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

import openai
from pydantic import BaseModel, Field

from app import config
from app.services.retriever import load_sections
from scripts.search import PROCESSED_DIR, SOURCES_FILE

# A stronger model than the one that wrote the answers, to reduce self-grading bias.
JUDGE_MODEL = "gpt-6.1-sol"
# For the cost estimate only (https://developers.openai.com/api/docs/models, checked 2026-11-05).
JUDGE_PRICE_PER_MILLION_INPUT = 2.00
JUDGE_PRICE_PER_MILLION_OUTPUT = 10.00


class CitationJudgement(BaseModel):
    index: int = Field(description="The citation number as given in the prompt")
    verdict: Literal["supported", "partially_supported", "not_supported", "out_of_context"]
    explanation: str = Field(description="One or two sentences, referring to the section text")


class AnswerJudgement(BaseModel):
    citations: list[CitationJudgement]
    unsupported_claims: list[str] = Field(
        description="Legal statements in the answer that NO cited section establishes (quote the statement)"
    )
    combination_errors: list[str] = Field(
        description="Places where provisions are combined or applied incorrectly (e.g. a rule for one "
                    "situation applied to another, or conditions from different sections mixed up)"
    )
    misleading_omissions: list[str] = Field(
        description="Conditions or exceptions IN THE CITED SECTIONS whose omission makes the answer misleading"
    )
    overall: Literal["accurate", "minor_issues", "significant_issues"]


JUDGE_PROMPT = """You are a meticulous reviewer of legal answers about Indian intellectual property law.

You receive a QUESTION, an ANSWER written for a non-lawyer, its numbered CITATIONS (a quote plus the \
statement it is meant to support), and the FULL TEXT of every cited section.

Judge ONLY against the provided section texts. Do not use outside knowledge to rescue a claim: if a \
statement is not established by the cited sections, it is unsupported even if it may be true in reality.

For each citation decide:
- supported: the quote, read in the context of its section, establishes the statement.
- partially_supported: it establishes part of the statement, or the statement overgeneralises it.
- out_of_context: the words are genuine, but in their section they serve a different purpose \
(e.g. a condition for refusing registration used as a general rule about remedies).
- not_supported: the quote does not establish the statement.

Also list unsupported claims, incorrect combinations of provisions, and misleading omissions of \
conditions or exceptions found in the cited sections. Be precise; do not invent problems. Plain \
simplification for a non-lawyer is acceptable if it does not change the legal meaning."""


def build_judge_input(response: dict, section_text: dict[str, str]) -> str:
    parts = [f"QUESTION:\n{response['question']}", f"ANSWER:\n{response['answer']}", "CITATIONS:"]
    for index, c in enumerate(response["citations"], start=1):
        parts.append(f"[{index}] section {c['section_id']}\n  quote: \"{c['quote']}\"\n  supports: {c['supports']}")
    parts.append("FULL TEXT OF CITED SECTIONS:")
    for sid in dict.fromkeys(c["section_id"] for c in response["citations"]):
        parts.append(f"=== {sid} ===\n{section_text.get(sid, '(section not found)')}")
    return "\n\n".join(parts)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("results_file", type=Path)
    args = parser.parse_args()

    data = json.loads(args.results_file.read_text(encoding="utf-8"))
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    sections = load_sections(PROCESSED_DIR, [s["id"] for s in sources])
    section_text = {f"{s.source_id}:{s.section}": s.text for s in sections}
    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

    tokens_in = tokens_out = 0
    for number, record in enumerate(data["results"], start=1):
        response = record["response"]
        if not response["citations"]:
            record["judgement"] = None  # nothing to judge (e.g. abstained)
            continue
        result = client.responses.parse(
            model=JUDGE_MODEL,
            instructions=JUDGE_PROMPT,
            input=build_judge_input(response, section_text),
            text_format=AnswerJudgement,
            store=False,
        )
        tokens_in += result.usage.input_tokens
        tokens_out += result.usage.output_tokens
        judgement = result.output_parsed
        record["judgement"] = judgement.model_dump() if judgement else None
        verdicts = [c.verdict for c in judgement.citations] if judgement else []
        print(f"{number:2}. {judgement.overall if judgement else 'NO VERDICT':19} {verdicts}  {response['question'][:60]}")

    cost = tokens_in / 1e6 * JUDGE_PRICE_PER_MILLION_INPUT + tokens_out / 1e6 * JUDGE_PRICE_PER_MILLION_OUTPUT
    data["judge"] = {"model": JUDGE_MODEL, "input_tokens": tokens_in, "output_tokens": tokens_out,
                     "estimated_cost_usd": round(cost, 3)}
    output = args.results_file.with_name(args.results_file.stem + "_judged.json")
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\njudge tokens: {tokens_in:,} in, {tokens_out:,} out -> estimated ${cost:.3f}")
    print(f"saved to {output}")


if __name__ == "__main__":
    main()
