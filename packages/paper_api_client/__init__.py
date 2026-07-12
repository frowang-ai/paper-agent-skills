"""Deprecated compatibility names backed by the Paper Agent runtime."""
from .client import (
    DEFAULT_BASE_URL,
    PaperClient,
    load_api_key,
    load_base_url,
)

__all__ = ["DEFAULT_BASE_URL", "PaperClient", "load_api_key", "load_base_url"]
