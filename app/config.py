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
