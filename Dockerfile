# NyayaAI chat page as a container (used for the Hugging Face Space demo).
# Secrets (OPENAI_API_KEY, APP_ACCESS_CODE) are NOT in this image: the host passes them in
# as environment variables at run time.

FROM python:3.14-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.model_cache \
    ENABLED_DOMAINS=ipr,criminal

# Hugging Face Spaces run the app as user 1000
RUN useradd -m -u 1000 user
WORKDIR /app

# CPU-only PyTorch first (the default download includes GPU libraries we do not need, ~2 GB more)
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 \
 && pip install -r requirements.txt

COPY --chown=user . .
RUN mkdir -p /app/.model_cache && chown -R user /app
USER user

# Download the embedding model and build the search indexes now, not on the first visit
RUN python -m scripts.prebuild_search

EXPOSE 7860
CMD ["streamlit", "run", "streamlit_app.py", "--server.port", "7860", "--server.address", "0.0.0.0", "--server.headless", "true"]
