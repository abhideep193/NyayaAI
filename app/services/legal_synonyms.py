"""Everyday words -> the words Indian IPR Acts use for the same idea.

Used to EXPAND a question before searching: the original words are kept and the
legal terms are added. "Can I use a song?" also searches "musical work sound recording".

Rules for this list:
  - Only general IPR vocabulary, not phrases written to pass specific eval questions.
  - Every legal term on the right must actually appear in the Acts.
"""

import re

SYNONYMS: dict[str, str] = {
    # --- kinds of work (Copyright Act) ---
    "song": "musical work sound recording",
    "music": "musical work sound recording",
    "movie": "cinematograph film",
    "video": "cinematograph film",
    "book": "literary work",
    "article": "literary work",
    "software": "computer programme",
    "app": "computer programme",
    "photo": "artistic work photograph",
    "painting": "artistic work",
    # --- brands (Trade Marks Act) ---
    "brand": "trade mark",
    "logo": "trade mark device",
    "fake": "false trade mark",
    "counterfeit": "false trade mark",
    # --- wrongs and remedies ---
    "copy": "infringement reproduction",
    "copied": "infringement reproduction",
    "piracy": "infringement",
    "sue": "suit infringement",
    "legal action": "suit remedies",
    "jail": "imprisonment offence",
    "punishment": "penalty imprisonment",
    # --- procedure and time ---
    "how long": "term duration",
    "last": "term duration",
    "expire": "term expiry",
    "rejected": "refusal",
    "challenge": "opposition",
    "oppose": "opposition",
    "permission": "licence consent",
    "license": "licence",
    "abroad": "outside India",
}

# One pattern per entry: whole word or phrase, optionally followed by a plural/past ending.
_PATTERNS = {
    phrase: re.compile(r"\b" + re.escape(phrase) + r"(s|es|d|ed)?\b") for phrase in SYNONYMS
}


def expand_query(question: str) -> str:
    """Return the question with legal terms appended for any everyday words found.

    "How long does a patent last?" -> "How long does a patent last? term duration term duration"
    """
    lowered = question.lower()
    additions = [SYNONYMS[phrase] for phrase, pattern in _PATTERNS.items() if pattern.search(lowered)]
    return " ".join([question] + additions)
