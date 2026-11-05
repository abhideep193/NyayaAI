"""Combine keyword search (BM25) and meaning search (embeddings) into one ranking.

BM25 is good at exact legal terms ("compulsory licence", "Section 52").
Embeddings are good at meaning ("software" ~ "computer programme").
Hybrid search uses both.
"""

from app.services.retriever import SearchResult

# Standard value from the original RRF paper; it stops the #1 result of a
# single list from dominating everything else.
RRF_K = 60


def reciprocal_rank_fusion(result_lists: list[list[SearchResult]], k: int = RRF_K) -> list[SearchResult]:
    """Merge several rankings: each section earns 1 / (k + rank) from every list it appears in.

    We combine RANKS rather than raw scores because BM25 scores (e.g. 12.4) and
    cosine similarities (e.g. 0.63) are on completely different scales.
    A section ranked well by BOTH searches ends up at the top.
    """
    fused_scores: dict[tuple[str, str], float] = {}
    sections = {}
    for results in result_lists:
        for rank, result in enumerate(results, start=1):
            key = (result.section.source_id, result.section.section)
            fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (k + rank)
            sections[key] = result.section

    ranked_keys = sorted(fused_scores, key=fused_scores.get, reverse=True)
    return [SearchResult(section=sections[key], score=fused_scores[key]) for key in ranked_keys]


class HybridRetriever:
    """Runs keyword and meaning search, then fuses their rankings."""

    def __init__(self, keyword_retriever, embedding_retriever, candidates: int = 30):
        # candidates: how many results to take from EACH search before fusing.
        self.keyword_retriever = keyword_retriever
        self.embedding_retriever = embedding_retriever
        self.candidates = candidates

    def search(self, question: str, top_k: int = 5) -> list[SearchResult]:
        keyword_results = self.keyword_retriever.search(question, top_k=self.candidates)
        meaning_results = self.embedding_retriever.search(question, top_k=self.candidates)
        return reciprocal_rank_fusion([keyword_results, meaning_results])[:top_k]
