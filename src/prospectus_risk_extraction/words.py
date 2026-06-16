"""Shared word tokenization.

All three CLIs report word counts (total document, risk-factors section, and
per-risk-factor bodies). Importing the same ``count_words`` everywhere keeps
those numbers comparable no matter which command produced them.
"""
from __future__ import annotations

import re

# A word is a run of letters/digits, optionally containing apostrophes (the
# ASCII apostrophe plus the common Unicode variants) or a backtick standing in
# for one. Kept identical to the original ``count_pdf_words`` regex so existing
# fixture counts remain valid.
WORD_RE = re.compile(r"\b[0-9A-Za-z'’‛`]+\b")


def count_words(text: str) -> int:
    """Count word-like tokens in ``text``."""
    return len(WORD_RE.findall(text))
