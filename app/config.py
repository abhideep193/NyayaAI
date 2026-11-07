"""Central settings for NyayaAI. Change behaviour here instead of inside the code."""

import os

from dotenv import load_dotenv

# Read KEY=value lines from the .env file into environment variables.
# Real environment variables take priority over .env.
load_dotenv()

# --- LLM ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6.1-terra")

# --- Retrieval ---
# How many sections are given to the LLM for each question.
# 15 chosen after comparing 8 vs 15 (see outputs/answer_experiments.md).
# Can be overridden in .env, e.g. ANSWER_CONTEXT_SECTIONS=8
ANSWER_CONTEXT_SECTIONS = int(os.getenv("ANSWER_CONTEXT_SECTIONS", "15"))

# Rewrite each question into the Acts' vocabulary (and into English) before searching.
# Accepted after measurement (see outputs/retrieval_experiments.md). Set to "false" to switch off.
USE_QUERY_REWRITE = os.getenv("USE_QUERY_REWRITE", "true").lower() == "true"
QUERY_REWRITE_MODEL = os.getenv("QUERY_REWRITE_MODEL", "gpt-6-luna")

# --- Areas of law ---
# Which domains (the "domain" field in data/legal_sources/sources.json) the app searches.
# Comma-separated, e.g. "ipr". Criminal law switched on 2026-11-06, property and consumer law 2026-11-08, each after
# evaluation against rules fixed in advance (outputs/answer_experiments.md).
ENABLED_DOMAINS = [d.strip() for d in os.getenv("ENABLED_DOMAINS", "ipr,criminal,property,consumer").split(",") if d.strip()]

# --- Documents and voice (added 2026-11-07) ---
# Model that reads the text in a PHOTO of a document (must accept images).
VISION_MODEL = os.getenv("VISION_MODEL") or OPENAI_MODEL  # an empty line in .env also means "default"
# Speech-to-text for voice questions (the text is shown to the user to check before sending).
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL") or "gpt-4o-transcribe"

# --- Public demo ---
# If set (e.g. as a secret on Hugging Face), the chat page asks for this code before answering,
# so a public link cannot spend the owner's OpenAI credit. Empty = no code needed (local use).
APP_ACCESS_CODE = os.getenv("APP_ACCESS_CODE", "")
