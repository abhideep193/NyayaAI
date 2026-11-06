"""Meaning-based search over sections using an embedding model.

An embedding model turns text into a list of numbers (a "vector") that represents
its meaning. Texts with similar meanings get vectors that point in similar
directions, even when they share no words ("software" vs "computer programme").
"""

import hashlib
import os
from pathlib import Path

import numpy as np

from app.services.retriever import SearchResult
from app.services.section_splitter import Section

# Hide a harmless Windows warning about file shortcuts in the model cache.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

MODEL_NAME = "BAAI/bge-small-en-v1.5"

# This model was trained to expect this prefix on questions (not on documents).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# The model reads at most 512 tokens (~2,000 characters); longer text is cut off.
# Chunks of ~1,200 characters plus a header stay safely inside that limit.
CHUNK_CHARS = 1200


def chunk_text(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    """Split text into chunks of about max_chars, only breaking between lines."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        if current and len(current) + 1 + len(line) > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def chunk_section(section: Section) -> list[str]:
    """Chunk a section, starting every chunk with the Act, section number and heading.

    The header tells the model which law each chunk belongs to, even for the
    3rd chunk of a long section that no longer contains the heading.
    """
    header = f"{section.act_title}, Section {section.section}: {section.heading}"
    return [f"{header}\n{chunk}" for chunk in chunk_text(section.text)]


class EmbeddingRetriever:
    """Search sections by meaning instead of by exact words."""

    def __init__(self, sections: list[Section], cache_path: Path | None = None, model_name: str = MODEL_NAME,
                 model=None):
        # model: an already-loaded SentenceTransformer to share between several indexes (saves memory).
        if model is None:
            # Imported here because loading the library takes several seconds.
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
        self.model = model

        # Like BM25: omitted (repealed) sections are never returned.
        self.sections = [s for s in sections if s.status != "omitted"]

        # Build all chunks, remembering which section each chunk came from.
        chunks: list[str] = []
        owners: list[int] = []
        for index, section in enumerate(self.sections):
            for chunk in chunk_section(section):
                chunks.append(chunk)
                owners.append(index)
        self.chunk_owner = np.array(owners)

        self.chunk_vectors = self._load_or_build_vectors(chunks, model_name, cache_path)

    def _load_or_build_vectors(self, chunks: list[str], model_name: str, cache_path: Path | None) -> np.ndarray:
        """Embed every chunk, or load the saved vectors if nothing has changed.

        Embedding all chunks takes a minute or two, so the result is saved to a
        cache file together with a fingerprint of the model name and chunk text.
        If the sections or the model change, the fingerprint changes and the
        vectors are rebuilt automatically.
        """
        fingerprint = hashlib.sha256("\x00".join([model_name, *chunks]).encode("utf-8")).hexdigest()

        if cache_path is not None and cache_path.exists():
            cached = np.load(cache_path)
            if str(cached["fingerprint"]) == fingerprint:
                return cached["vectors"]

        # normalize_embeddings=True makes every vector length 1, so a simple
        # dot product between two vectors equals their cosine similarity.
        vectors = self.model.encode(chunks, normalize_embeddings=True, show_progress_bar=True)

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(cache_path, vectors=vectors, fingerprint=fingerprint)
        return vectors

    def search(self, question: str, top_k: int = 5) -> list[SearchResult]:
        """Return the top_k sections whose best chunk is closest in meaning to the question."""
        question_vector = self.model.encode([QUERY_PREFIX + question], normalize_embeddings=True)[0]

        # Cosine similarity of the question with every chunk at once (matrix x vector).
        chunk_scores = self.chunk_vectors @ question_vector

        # A section's score is the score of its best-matching chunk.
        best_per_section: dict[int, float] = {}
        for owner, score in zip(self.chunk_owner, chunk_scores):
            if score > best_per_section.get(owner, -1.0):
                best_per_section[owner] = float(score)

        ranked = sorted(best_per_section.items(), key=lambda item: item[1], reverse=True)
        return [SearchResult(section=self.sections[i], score=score) for i, score in ranked[:top_k]]
