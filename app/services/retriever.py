"""Find the sections of law most relevant to a question, using BM25 keyword search.

BM25 gives every section a score for a question. For each word in the question:
  - sections that use the word more often score higher (with diminishing returns),
  - rare words (e.g. "cinematograph") count much more than common ones (e.g. "act"),
  - long sections are penalised a little, so they do not win just by being long.
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import snowballstemmer

from app.services.section_splitter import Section

# Reduces words to a common root: "infringed", "infringement" -> "infring".
STEMMER = snowballstemmer.stemmer("english")

# Very common words that say nothing about the topic of a question.
STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "has", "have", "i", "if", "in", "into", "is", "it", "its", "me", "my", "of",
    "on", "or", "our", "shall", "so", "such", "that", "the", "their", "them", "there",
    "this", "to", "under", "was", "we", "what", "when", "where", "which", "who", "will",
    "with", "you", "your",
}


def tokenize(text: str) -> list[str]:
    """Turn text into a list of lowercase word stems, without stopwords.

    "Can I use a song?"           -> ["use", "song"]
    "infringed registered marks"  -> ["infring", "regist", "mark"]
    """
    text = text.lower()

    # People write "trademark" or "trade-mark"; the Acts write "trade mark".
    text = re.sub(r"\btrade-?mark", "trade mark", text)

    words = re.findall(r"[a-z0-9]+", text)
    words = [word for word in words if word not in STOPWORDS]
    return STEMMER.stemWords(words)


@dataclass
class SearchResult:
    """One search hit: a section and how well it matched."""

    section: Section
    score: float


class BM25Retriever:
    """Keyword search over a list of sections."""

    def __init__(
        self,
        sections: list[Section],
        k1: float = 1.5,
        b: float = 0.75,
        heading_weight: int = 5,
    ):
        # k1: how quickly repeating a word stops adding to the score.
        # b:  how strongly long sections are penalised (0 = not at all, 1 = fully).
        # heading_weight: how many EXTRA times the heading's words are counted.
        #   Headings summarise a section ("Term of patent"), so their words matter more.
        self.k1 = k1
        self.b = b

        # Omitted (repealed) sections are not current law, so we never return them.
        self.sections = [s for s in sections if s.status != "omitted"]

        # For each section, count how often each word appears in it.
        # (The text already starts with the heading, so it is counted once there.)
        self.word_counts = [
            Counter(tokenize(s.text) + tokenize(s.heading) * heading_weight)
            for s in self.sections
        ]
        self.lengths = [sum(counts.values()) for counts in self.word_counts]
        self.average_length = sum(self.lengths) / len(self.lengths)

        # For each word, in how many sections does it appear at least once?
        sections_containing = Counter()
        for counts in self.word_counts:
            sections_containing.update(counts.keys())

        # IDF ("inverse document frequency"): high for rare words, low for common ones.
        n = len(self.sections)
        self.idf = {
            word: math.log((n - count + 0.5) / (count + 0.5) + 1)
            for word, count in sections_containing.items()
        }

    def score(self, query_words: list[str], index: int) -> float:
        """BM25 score of section number `index` for the query words."""
        counts = self.word_counts[index]
        length_ratio = self.lengths[index] / self.average_length
        total = 0.0
        for word in query_words:
            frequency = counts.get(word, 0)
            if frequency == 0:
                continue
            saturation = frequency * (self.k1 + 1) / (
                frequency + self.k1 * (1 - self.b + self.b * length_ratio)
            )
            total += self.idf[word] * saturation
        return total

    def search(self, question: str, top_k: int = 5) -> list[SearchResult]:
        """Return the top_k best-matching sections, best first."""
        query_words = tokenize(question)
        results = [
            SearchResult(section=section, score=self.score(query_words, index))
            for index, section in enumerate(self.sections)
        ]
        results = [r for r in results if r.score > 0]  # drop sections with no matching word
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


def load_sections(processed_dir: Path, source_ids: list[str]) -> list[Section]:
    """Load the <id>_sections.json files produced by scripts.split_sections."""
    sections = []
    for source_id in source_ids:
        path = processed_dir / f"{source_id}_sections.json"
        for item in json.loads(path.read_text(encoding="utf-8")):
            sections.append(Section(**item))
    return sections
