"""Voice questions: turn a recording into text with OpenAI speech-to-text.

The text is always SHOWN to the person to check and correct before it is sent, because a
misheard word ("bail" / "jail") changes a legal question.
"""

# A hint about the vocabulary we expect; it does not change what was said.
TRANSCRIBE_PROMPT = ("A person in India asking a legal question, in English, Hindi or Hinglish. "
                     "Words like FIR, police, copyright, trade mark, notice, Section, Act.")


def transcribe(audio_bytes: bytes, filename: str, client, model: str) -> str:
    """Return the words in the recording ("" if nothing was heard)."""
    result = client.audio.transcriptions.create(
        model=model,
        file=(filename or "question.wav", audio_bytes),
        prompt=TRANSCRIBE_PROMPT,
    )
    return (getattr(result, "text", "") or "").strip()
