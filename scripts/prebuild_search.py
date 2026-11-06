"""Download the embedding model and build the search indexes ahead of time.

Run while building the deployment image (see Dockerfile), so the live app starts quickly
instead of embedding ~2,300 sections (several minutes) on its first visitor.
Writes data/processed/embeddings_cache*.npz for every enabled area of law.

    python -m scripts.prebuild_search
"""

from app import config
from scripts.search import build_domain_retrievers


def main() -> None:
    retrievers = build_domain_retrievers()
    print(f"search indexes ready for: {', '.join(retrievers)} (areas enabled: {config.ENABLED_DOMAINS})")


if __name__ == "__main__":
    main()
