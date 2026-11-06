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

REWRITE_PROMPT = """Rewrite the user's question so it can be used to SEARCH the text of three Indian Acts: \
the Copyright Act, 1957, the Trade Marks Act, 1999 and the Patents Act, 1970.
Use the words these Acts themselves use (for example "infringement", "assignment", "invention", \
"registration", "licence") and name the Act that is most relevant.
Do NOT answer the question. Do NOT mention section numbers. Return one or two sentences.
Always write the search query in English, even if the question is in Hindi, Hinglish or another language.
If the question is not about copyright, trade marks or patents, just restate it in plain English."""


class SearchQuery(BaseModel):
    legal_query: str = Field(description="The question rewritten in statutory language, in English")


class QueryRewriter:
    """Calls a small model to rewrite questions. `client` is an openai.OpenAI() object."""

    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    def rewrite(self, question: str) -> str | None:
        """Return the rewritten query, or None if the call fails (search then uses the original only)."""
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=REWRITE_PROMPT,
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
