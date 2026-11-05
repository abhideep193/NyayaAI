"""Tests for the basic NyayaAI API endpoints in app/main.py."""

from fastapi.testclient import TestClient

from app.main import app

# One fake "browser" that all tests below use to call the app
client = TestClient(app)


def test_home_returns_welcome_message():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to NyayaAI!"


def test_ask_accepts_valid_question():
    question = "Can I use a song in my YouTube video?"

    response = client.post("/ask", json={"question": question})

    assert response.status_code == 200
    assert response.json()["received_question"] == question


def test_ask_rejects_too_short_question():
    # "Hi" has 2 characters; the minimum is 5
    response = client.post("/ask", json={"question": "Hi"})

    assert response.status_code == 422


def test_ask_rejects_too_long_question():
    # 2001 characters; the maximum is 2000
    response = client.post("/ask", json={"question": "a" * 2001})

    assert response.status_code == 422


def test_ask_rejects_missing_question():
    # Empty JSON body: the required "question" field is missing
    response = client.post("/ask", json={})

    assert response.status_code == 422
