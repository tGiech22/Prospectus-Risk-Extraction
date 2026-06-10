"""Regression test for the PDF word counter.

Uses the small fixture PDFs in ``test_fixtures/`` and their known-good counts
in ``test_fixtures/expected_counts.txt`` so that changes to the tokenizer or
extraction logic can't silently change the numbers.
"""
from pathlib import Path

import pytest

from prospectus_risk_extraction.count_pdf_words import count_words_in_pdf

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "test_fixtures"


def _load_expected():
    """Parse 'filename<TAB>count' lines from expected_counts.txt."""
    cases = []
    for line in (FIXTURE_DIR / "expected_counts.txt").read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        name, count = line.split("\t")
        cases.append((name, int(count)))
    return cases


@pytest.mark.parametrize("filename,expected", _load_expected())
def test_word_count_matches_expected(filename, expected):
    assert count_words_in_pdf(FIXTURE_DIR / filename) == expected
