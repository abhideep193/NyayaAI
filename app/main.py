import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Literal

import openai
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app import config
from app.services.answer_generator import ModelRefusedError
from app.services.assistant import NyayaAssistant

logger = logging.getLogger("nyayaai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs ONCE when the server starts (before `yield`) and once when it stops (after).

    Loading the search models takes ~20 seconds, so we do it here instead of
    on every request. The ready assistant is stored on app.state.
    """
    # Imported here so that importing app.main (e.g. in tests) stays fast.
    from scripts.search import build_assistant

    app.state.assistant = None
    if not config.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set: /ask will return 503 until it is added to .env")
    else:
        app.state.assistant = build_assistant()
        logger.info("NyayaAI assistant ready (model: %s)", config.OPENAI_MODEL)
    yield


app = FastAPI(
    title="NyayaAI",
    description="An AI-powered Indian legal assistant, starting with Intellectual Property Rights (IPR) and designed to expand into other legal domains.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def home():
    return {
        "message": "Welcome to NyayaAI!",
        "status": "Application is running successfully"
    }


# ---------------------------------------------------------------------------
# Request and response shapes (they also appear in /docs)
# ---------------------------------------------------------------------------


class LegalQuestion(BaseModel):
    question: str = Field(
        min_length=5,
        max_length=2000,
        description="Describe your legal problem in detail"
    )


class CitationOut(BaseModel):
    section_id: str = Field(description="e.g. copyright_act_1957:52")
    citation: str | None = Field(description="e.g. Section 52, The Copyright Act, 1957")
    page: int | None = Field(description="Page of the official India Code PDF")
    quote: str = Field(description="Exact words quoted from the section")
    supports: str = Field(description="The statement in the answer this quote supports")
    verified: bool = Field(description="True only if the quote was found in a retrieved section")
    reason: str


class SafetyNoteOut(BaseModel):
    kind: Literal["helpline", "old_law"]
    text: str = Field(description="Fixed text added by NyayaAI's code, not by the model")
    source: str = Field(description="Official source of the information")


class AskResponse(BaseModel):
    question: str
    answer: str
    confidence: Literal["high", "medium", "low", "insufficient"] = Field(
        description="After citation checks (can be lower than the model's own confidence)"
    )
    model_confidence: Literal["high", "medium", "low", "insufficient"]
    citations: list[CitationOut]
    next_steps: list[str]
    disclaimer: str
    sources_considered: list[str] = Field(description="Every section the model was given")
    model: str
    input_tokens: int
    output_tokens: int
    safety_notes: list[SafetyNoteOut] = Field(description="Checked helplines / old-law notice")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def get_assistant(request: Request) -> NyayaAssistant:
    """FastAPI dependency: hands the ready assistant to the endpoint.

    Tests replace this function with one that returns a fake assistant.
    """
    assistant = getattr(request.app.state, "assistant", None)
    if assistant is None:
        raise HTTPException(status_code=503, detail="The AI service is not configured on this server.")
    return assistant


@app.post("/ask", response_model=AskResponse)
def ask_legal_question(data: LegalQuestion, assistant: NyayaAssistant = Depends(get_assistant)):
    try:
        response = assistant.ask(data.question)
    except ModelRefusedError:
        raise HTTPException(status_code=502, detail="The AI model did not return a usable answer. Please try again.")
    except openai.APIError:
        logger.exception("OpenAI request failed")
        raise HTTPException(status_code=502, detail="The AI service could not be reached. Please try again later.")

    return asdict(response)
