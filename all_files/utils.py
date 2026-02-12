# lib/utils.py
"""Shared utility functions with memoization."""

import re
from functools import lru_cache


@lru_cache(maxsize=4096)
def normalize_japanese(text: str) -> str:
    """Remove brackets, spaces, normalize Japanese text. Memoized."""
    if not text:
        return ""
    return re.sub(r'[「」『』（）\(\)\s\u3000]', '', text).strip()


# Full-width to half-width digit translation table
_FULL2HALF = str.maketrans("０１２３４５６７８９", "0123456789")


@lru_cache(maxsize=4096)
def norm_for_alignment(text: str) -> str:
    """Normalize text for alignment: remove brackets, spaces, convert digits."""
    return normalize_japanese(text).translate(_FULL2HALF)
