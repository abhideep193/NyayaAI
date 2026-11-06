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
# Comma-separated, e.g. "ipr". Criminal law switched on 2026-11-06 after evaluation (outputs/answer_experiments.md).
ENABLED_DOMAINS = [d.strip() for d in os.getenv("ENABLED_DOMAINS", "ipr,criminal").split(",") if d.strip()]

# --- Public demo ---
# If set (e.g. as a secret on Hugging Face), the chat page asks for this code before answering,
# so a public link cannot spend the owner's OpenAI credit. Empty = no code needed (local use).
APP_ACCESS_CODE = os.getenv("APP_ACCESS_CODE", "")
