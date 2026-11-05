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
