"""Search the IPR Acts from the terminal.

Run from the project root:
    python -m scripts.search "someone copied my brand logo"
"""

import json
import sys
from pathlib import Path

from app.services.embeddings import EmbeddingRetriever
from app.services.hybrid import HybridRetriever
from app.services.retriever import BM25Retriever, load_sections

SOURCES_FILE = Path("data/legal_sources/sources.json")
PROCESSED_DIR = Path("data/processed")
EMBEDDINGS_CACHE = PROCESSED_DIR / "embeddings_cache.npz"


def enabled_source_ids(sources: list[dict], domains: list[str]) -> list[str]:
    """IDs of the Acts whose domain is switched on (see ENABLED_DOMAINS in app/config.py)."""
    return [source["id"] for source in sources if source["domain"] in domains]


def build_retrievers() -> dict:
    """Load the Acts of the enabled domains from sources.json and build the search methods."""
    from app import config

    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    sections = load_sections(PROCESSED_DIR, enabled_source_ids(sources, config.ENABLED_DOMAINS))

    keyword = BM25Retriever(sections)
    meaning = EmbeddingRetriever(sections, cache_path=EMBEDDINGS_CACHE)
    return {
        "bm25": keyword,
        "embeddings": meaning,
        "hybrid": HybridRetriever(keyword, meaning),
    }


def build_assistant():
    """Build the full answer pipeline (search + OpenAI) from the settings in .env.

    Used by the API server, scripts.ask and scripts.evaluate_answers.
    """
    import openai

    from app import config
    from app.services.assistant import NyayaAssistant, load_known_issues
    from app.services.query_rewriter import QueryRewriter, QueryRewritingRetriever

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    retriever = build_retrievers()["hybrid"]
    if config.USE_QUERY_REWRITE:
        retriever = QueryRewritingRetriever(retriever, QueryRewriter(client, config.QUERY_REWRITE_MODEL))

    return NyayaAssistant(
        retriever=retriever,
        client=client,
        model=config.OPENAI_MODEL,
        known_issues=load_known_issues(SOURCES_FILE),
        context_sections=config.ANSWER_CONTEXT_SECTIONS,
    )


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m scripts.search "your question"')
        return

    question = " ".join(sys.argv[1:])
    retriever = build_retrievers()["hybrid"]

    print(f"Question: {question}\n")
    for rank, result in enumerate(retriever.search(question, top_k=5), start=1):
        s = result.section
        print(f"{rank}. {s.citation} - {s.heading} (page {s.page_start})")


if __name__ == "__main__":
    main()
