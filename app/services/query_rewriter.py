"""Rewrite a user's question into the vocabulary of the Acts before searching.

People say "transfer my copyright"; the Act says "assignment". People may also write
in Hindi or Hinglish, while our search index is English. A small, cheap model turns
the question into an English search query that uses the Acts' own words. We then
search with BOTH the original question and the rewrite and merge the two rankings.

The rewrite only changes WHICH sections are found. The answer still uses only the
retrieved law, and every citation is still checked by citation_verifier.
Measured in outputs/retrieval_experiments.md.
"""

import logging

from pydantic import BaseModel, Field

from app.services.hybrid import reciprocal_rank_fusion
from app.services.retriever import SearchResult

logger = logging.getLogger("nyayaai")

# The {blanks} are filled in by app/domains.py from the enabled areas of law and their Acts.
REWRITE_PROMPT_TEMPLATE = """Rewrite the user's question so it can be used to SEARCH the text of {count} Indian Acts: \
{acts}.
Use the words these Acts themselves use (for example {words}) and name the Act that is most relevant.
Do NOT answer the question. Do NOT mention section numbers. Return one or two sentences.
Always write the search query in English, even if the question is in Hindi, Hinglish or another language.
If the question is not about {rewrite_scope}, just restate it in plain English."""


class SearchQuery(BaseModel):
    legal_query: str = Field(description="The question rewritten in statutory language, in English")


class QueryRewriter:
    """Calls a small model to rewrite questions. `client` is an openai.OpenAI() object.

    `prompt` is built by app.domains.build_rewrite_prompt() from the enabled Acts.
    """

    def __init__(self, client, model: str, prompt: str):
        self.client = client
        self.model = model
        self.prompt = prompt

    def rewrite(self, question: str) -> str | None:
        """Return the rewritten query, or None if the call fails (search then uses the original only)."""
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=self.prompt,
                input=question,
                text_format=SearchQuery,
                store=False,
            )
        except Exception:  # never let the optional rewrite step break answering
            logger.exception("Query rewrite failed; searching with the original question only")
            return None
        return response.output_parsed.legal_query if response.output_parsed else None


class QueryRewritingRetriever:
    """Wraps a retriever: search with the original AND the rewritten question, then fuse."""

    def __init__(self, base_retriever, rewriter: QueryRewriter, candidates: int = 30):
        self.base_retriever = base_retriever
        self.rewriter = rewriter
        self.candidates = candidates

    def search(self, question: str, top_k: int = 5) -> list[SearchResult]:
        rewritten = self.rewriter.rewrite(question)
        if not rewritten:
            return self.base_retriever.search(question, top_k=top_k)
        original_results = self.base_retriever.search(question, top_k=self.candidates)
        rewritten_results = self.base_retriever.search(rewritten, top_k=self.candidates)
        return reciprocal_rank_fusion([original_results, rewritten_results])[:top_k]


# ---------------------------------------------------------------------------
# Domain routing: used only when more than one area of law is enabled.
# The same rewrite call also says which area(s) the question is about, and we
# search only those areas' Acts, so e.g. criminal sections cannot crowd out
# the right copyright section. Measured in outputs/retrieval_experiments.md.
# ---------------------------------------------------------------------------


class RoutedSearchQuery(BaseModel):
    legal_query: str = Field(description="The question rewritten in statutory language, in English")
    areas: list[str] = Field(description="IDs of the areas of law the question is about; empty if none applies")


class RoutingQueryRewriter(QueryRewriter):
    """Rewrites the question AND chooses the area(s) of law. `prompt` includes the list of area IDs."""

    def route(self, question: str) -> tuple[str | None, list[str]]:
        """Return (rewritten query, area IDs). On any failure: (None, [])."""
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=self.prompt,
                input=question,
                text_format=RoutedSearchQuery,
                store=False,
            )
        except Exception:
            logger.exception("Query rewrite/routing failed; searching all areas with the original question")
            return None, []
        parsed = response.output_parsed
        return (parsed.legal_query, parsed.areas) if parsed else (None, [])


class DomainRoutedRetriever:
    """Search only the area(s) of law chosen by the rewriter, each with its own index.

    retrievers: {"ipr": HybridRetriever(IPR Acts only), "criminal": HybridRetriever(criminal Acts only)}
    With one area chosen this is exactly QueryRewritingRetriever on that area's index.
    If no known area is chosen (or the rewrite fails), every area is searched and merged.
    """

    def __init__(self, retrievers: dict, rewriter: RoutingQueryRewriter, candidates: int = 30):
        self.retrievers = retrievers
        self.rewriter = rewriter
        self.candidates = candidates

    def search(self, question: str, top_k: int = 5) -> list[SearchResult]:
        rewritten, areas = self.rewriter.route(question)
        chosen = [a for a in dict.fromkeys(areas) if a in self.retrievers] or list(self.retrievers)

        per_area = []
        for area in chosen:
            retriever = self.retrievers[area]
            if rewritten:
                per_area.append(reciprocal_rank_fusion([
                    retriever.search(question, top_k=self.candidates),
                    retriever.search(rewritten, top_k=self.candidates),
                ]))
            else:
                per_area.append(retriever.search(question, top_k=self.candidates))

        merged = per_area[0] if len(per_area) == 1 else reciprocal_rank_fusion(per_area)
        return merged[:top_k]
