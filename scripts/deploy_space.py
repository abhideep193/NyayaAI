"""Publish the NyayaAI chat page to a Hugging Face Space (Docker).

Only the files listed in ALLOW are uploaded - never .env, the virtual environment, the PDFs
or evaluation outputs. Before uploading, every file is scanned for anything that looks like
an OpenAI key; if one is found, nothing is uploaded.

Secrets are NOT uploaded: set OPENAI_API_KEY and APP_ACCESS_CODE in the Space's
Settings -> Variables and secrets.

First log in once in your own terminal (the token is stored by huggingface_hub, not here):
    hf auth login
Then:
    python -m scripts.deploy_space --repo YOUR_HF_USERNAME/nyayaai --dry-run   # list files only
    python -m scripts.deploy_space --repo YOUR_HF_USERNAME/nyayaai             # upload
"""

import argparse
import fnmatch
import re
from pathlib import Path

ALLOW = [
    "Dockerfile",
    "requirements.txt",
    "streamlit_app.py",
    ".streamlit/config.toml",
    "app/*.py",
    "app/services/*.py",
    "scripts/*.py",
    "data/legal_sources/*.json",
    "data/processed/*_sections.json",
    "assets/sphere_cut.png",
    "assets/sphere_avatar.png",
    "assets/lady_justice_icon.png",
    "assets/sphere_component.html",
]
NEVER = [".env", ".env.*", "*.npz", "*.pdf", ".venv/*", "**/__pycache__/*", "*.pyc"]
KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")  # what an OpenAI secret key looks like


def files_to_upload(root: Path) -> list[Path]:
    chosen = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and any(fnmatch.fnmatch(rel, p) for p in ALLOW) \
                and not any(fnmatch.fnmatch(rel, p) for p in NEVER):
            chosen.append(path)
    return chosen


def find_secrets(paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        if path.suffix in {".png"}:
            continue
        if KEY_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")):
            problems.append(str(path))
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="e.g. yourname/nyayaai")
    parser.add_argument("--dry-run", action="store_true", help="only list what would be uploaded")
    args = parser.parse_args()

    root = Path(".")
    paths = files_to_upload(root)
    size = sum(p.stat().st_size for p in paths) / 1e6
    print(f"{len(paths)} files, {size:.1f} MB:")
    for p in paths:
        print("  ", p.as_posix())

    leaks = find_secrets(paths)
    if leaks:
        raise SystemExit(f"STOPPED: something that looks like an API key is in {leaks}. Nothing uploaded.")
    print("secret scan: no API keys found")
    if args.dry_run:
        return

    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(args.repo, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(folder_path=".", repo_id=args.repo, repo_type="space",
                      allow_patterns=[p.as_posix() for p in paths],
                      commit_message="Deploy NyayaAI chat page")
    api.upload_file(path_or_fileobj="deploy/space_README.md", path_in_repo="README.md",
                    repo_id=args.repo, repo_type="space", commit_message="Space description")
    print(f"\nUploaded. Build log and app: https://huggingface.co/spaces/{args.repo}")


if __name__ == "__main__":
    main()
