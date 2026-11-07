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
DOMAINS_FILE = Path("data/legal_sources/domains.json")
SAFETY_FILE = Path("data/legal_sources/safety.json")


def enabled_source_ids(sources: list[dict], domains: list[str]) -> list[str]:
    """IDs of the Acts whose domain is switched on (see ENABLED_DOMAINS in app/config.py)."""
    return [source["id"] for source in sources if source["domain"] in domains]


def embeddings_cache_for(domains: list[str]) -> Path:
    """One cache file per set of domains, so switching domains on/off doesn't recompute everything."""
    if domains == ["ipr"]:
        return EMBEDDINGS_CACHE  # the original file name
    return PROCESSED_DIR / f"embeddings_cache_{'_'.join(domains)}.npz"


def build_retrievers() -> dict:
    """Load the Acts of the enabled domains from sources.json and build the search methods."""
    from app import config

    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    sections = load_sections(PROCESSED_DIR, enabled_source_ids(sources, config.ENABLED_DOMAINS))

    keyword = BM25Retriever(sections)
    meaning = EmbeddingRetriever(sections, cache_path=embeddings_cache_for(config.ENABLED_DOMAINS))
    return {
        "bm25": keyword,
        "embeddings": meaning,
        "hybrid": HybridRetriever(keyword, meaning),
    }


def build_domain_retrievers() -> dict:
    """One hybrid index per enabled area of law, e.g. {"ipr": ..., "criminal": ...}.

    Each area is searched on its own, exactly as if it were the only area enabled
    (same sections, same keyword statistics, same embedding cache file).
    """
    from sentence_transformers import SentenceTransformer

    from app import config
    from app.services.embeddings import MODEL_NAME

    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    shared_model = SentenceTransformer(MODEL_NAME)  # load once, share between the indexes
    retrievers = {}
    for domain in config.ENABLED_DOMAINS:
        sections = load_sections(PROCESSED_DIR, enabled_source_ids(sources, [domain]))
        keyword = BM25Retriever(sections)
        meaning = EmbeddingRetriever(sections, cache_path=embeddings_cache_for([domain]), model=shared_model)
        retrievers[domain] = HybridRetriever(keyword, meaning)
    return retrievers


def build_rewriting_retriever(retriever, client=None):
    """Wrap a retriever with LLM query rewriting, using the prompt for the enabled domains."""
    import openai

    from app import config
    from app.domains import build_rewrite_prompt, load_domains
    from app.services.query_rewriter import QueryRewriter, QueryRewritingRetriever

    client = client or openai.OpenAI(api_key=config.OPENAI_API_KEY)
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    prompt = build_rewrite_prompt(load_domains(DOMAINS_FILE), config.ENABLED_DOMAINS, sources)
    return QueryRewritingRetriever(retriever, QueryRewriter(client, config.QUERY_REWRITE_MODEL, prompt))


def build_routed_retriever(client=None):
    """Rewrite + choose area(s) of law, then search only those areas' indexes (2+ areas enabled)."""
    import openai

    from app import config
    from app.domains import build_routing_prompt, load_domains
    from app.services.query_rewriter import DomainRoutedRetriever, RoutingQueryRewriter

    client = client or openai.OpenAI(api_key=config.OPENAI_API_KEY)
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    prompt = build_routing_prompt(load_domains(DOMAINS_FILE), config.ENABLED_DOMAINS, sources)
    rewriter = RoutingQueryRewriter(client, config.QUERY_REWRITE_MODEL, prompt)
    return DomainRoutedRetriever(build_domain_retrievers(), rewriter)


def build_assistant():
    """Build the full answer pipeline (search + OpenAI) from the settings in .env.

    Used by the API server, scripts.ask and scripts.evaluate_answers.
    """
    import openai

    from app import config
    from app.domains import build_system_prompt, load_domains
    from app.safety import load_safety
    from app.services.assistant import NyayaAssistant, load_known_issues

    domains = load_domains(DOMAINS_FILE)
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    if config.USE_QUERY_REWRITE and len(config.ENABLED_DOMAINS) > 1:
        # 2+ areas of law: rewrite + choose the area, search only its Acts (accepted 2026-11-06)
        retriever = build_routed_retriever(client)
    elif config.USE_QUERY_REWRITE:
        retriever = build_rewriting_retriever(build_retrievers()["hybrid"], client)
    else:
        retriever = build_retrievers()["hybrid"]

    return NyayaAssistant(
        retriever=retriever,
        client=client,
        model=config.OPENAI_MODEL,
        known_issues=load_known_issues(SOURCES_FILE),
        system_prompt=build_system_prompt(domains, config.ENABLED_DOMAINS),
        context_sections=config.ANSWER_CONTEXT_SECTIONS,
        safety=load_safety(SAFETY_FILE),
        domain_of={source["id"]: source["domain"] for source in sources},
    )


def build_document_explainer(retriever=None, client=None):
    """'Explain my document': all enabled Acts (to look up the sections a document names) + search.

    Pass the chat assistant's retriever to share it; otherwise the same routed search is built.
    """
    import openai

    from app import config
    from app.services.document_explainer import DocumentExplainer

    client = client or openai.OpenAI(api_key=config.OPENAI_API_KEY)
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    enabled = [s for s in sources if s["domain"] in config.ENABLED_DOMAINS]
    sections = load_sections(PROCESSED_DIR, [s["id"] for s in enabled])
    if retriever is None:
        retriever = build_assistant().retriever
    return DocumentExplainer(client, config.OPENAI_MODEL, enabled, sections, retriever=retriever,
                             vision_model=config.VISION_MODEL)


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
