"""Follow-up questions: add the user's earlier questions so "what about the old one?" makes sense."""

PREVIOUS_TURNS_USED = 4  # earlier user messages added as context for follow-up questions


def question_with_context(messages: list[dict], new_question: str) -> str:
    """Add the user's last few questions (not NyayaAI's answers) to the new question.

    The instruction travels WITH the message (not in the system prompts), so the evaluated
    prompts stay unchanged. It stops an old topic (e.g. harassment) leaking into a new one.
    """
    earlier = [m["content"] for m in messages if m["role"] == "user"][-PREVIOUS_TURNS_USED:]
    if not earlier:
        return new_question
    context = "\n".join(f"- {text}" for text in earlier)
    return (f"Earlier in this conversation the user said (oldest first). Use these ONLY if the current "
            f"question refers back to them; if the current question is about a different topic, "
            f"ignore them:\n{context}\n\nCurrent question: {new_question}")
