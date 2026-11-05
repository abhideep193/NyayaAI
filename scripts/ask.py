"""Ask NyayaAI a question from the terminal.

Run from the project root (needs OPENAI_API_KEY in .env):
    python -m scripts.ask "Can I use a song in my YouTube video?"
"""

import sys
import textwrap

from app import config
from scripts.search import build_assistant


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # so Windows terminals can print “ ” and —

    if len(sys.argv) < 2:
        print('Usage: python -m scripts.ask "your question"')
        return
    if not config.OPENAI_API_KEY:
        print("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
        return

    question = " ".join(sys.argv[1:])
    response = build_assistant().ask(question)

    wrap = lambda text, indent="": textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent)

    print(f"\nQUESTION: {response.question}\n")
    print("ANSWER:")
    print(wrap(response.answer, "  "))
    print(f"\nCONFIDENCE: {response.confidence}  (model said: {response.model_confidence})")

    print("\nCITATIONS:")
    if not response.citations:
        print("  (none)")
    for check in response.citations:
        status = "VERIFIED" if check.verified else "REJECTED"
        where = f"{check.citation}, page {check.page}" if check.citation else check.section_id
        print(f"  [{status}] {where}")
        print(wrap(f'"{check.quote}"', "      "))
        print(wrap(f"supports: {check.supports}", "      "))
        if not check.verified:
            print(f"      reason: {check.reason}")

    print("\nNEXT STEPS:")
    for step in response.next_steps:
        print(wrap(f"- {step}", "  "))

    print(f"\n{wrap(response.disclaimer)}")
    print(f"\n[model: {response.model} | tokens in: {response.input_tokens:,} out: {response.output_tokens:,}]")
    print("[sources given to the model: " + "; ".join(response.sources_considered) + "]")


if __name__ == "__main__":
    main()
