"""
The text-embedding model (all-MiniLM-L6-v2), loaded once and shared.

Before: the library, personal documents, and every document you added each
loaded their own copy (slower start, more memory), and each one checked
Hugging Face online first. Now:
  - one copy for the whole app
  - once it's saved in memory/model_cache, it loads offline — no network,
    no "unauthenticated requests to the HF Hub" warning
"""

import os
from pathlib import Path

MODEL_NAME = "all-MiniLM-L6-v2"
CACHE_DIR = Path("memory/model_cache")

_model = None


def use_offline_cache_if_present():
    """
    Tell Hugging Face libraries to stay offline when the model is already
    downloaded. Must run before they're imported (they read this at import).
    """
    if CACHE_DIR.exists() and any(CACHE_DIR.rglob("config.json")):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def get_embedder():
    """The shared model. Raises ImportError if sentence-transformers is missing."""
    global _model
    if _model is None:
        use_offline_cache_if_present()
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME, cache_folder=str(CACHE_DIR))
    return _model
