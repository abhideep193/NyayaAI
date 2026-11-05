from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="NyayaAI",
    description="An AI-powered Indian legal assistant, starting with Intellectual Property Rights (IPR) and designed to expand into other legal domains.",    version="1.0.0"
)

@app.get("/")
def home():
    return {
        "message": "Welcome to NyayaAI!",
        "status": "Application is running successfully"
    }

class LegalQuestion(BaseModel):
    question: str = Field(
        min_length=5,
        max_length=2000,
        description="Describe your legal problem in detail"
    )


@app.post("/ask")
def ask_legal_question(data: LegalQuestion):
    return {
        "received_question": data.question,
        "message": "Your legal question has been received!"
    }
