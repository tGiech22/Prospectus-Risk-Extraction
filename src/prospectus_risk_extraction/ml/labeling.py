"""Per-line features and (weak) labels for the line-classification task.

We reuse the analyzer's PDF parsing (spans -> lines -> document style) so the
features here describe *exactly* the same ``Line`` objects the heuristic sees.
Two things are produced for each line inside the Risk Factors section:

* :func:`line_features` - a flat dict of numeric + text features for the model.
* :func:`weak_label`    - the label the heuristic's Pass-1 logic would assign.

``weak_label`` mirrors ``segment_risk_factors`` Pass-1 in ``analyzer.py`` line
for line, so a classifier trained on these labels has the heuristic as its
ceiling. Replace this function (or pass your own labels) once you hand-annotate
real gold lines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..analyzer import (
    SUBCAT_PAT,
    build_lines,
    extract_spans,
    find_risk_section,
    learn_style,
)

LABELS = ["heading", "body", "subheading", "skip"]

_SKIP_RE = re.compile(r"^(table of contents|page\s+\d|\d+\s*$)", re.IGNORECASE)


def weak_label(line, style) -> str:
    """Label one line the way ``analyzer.segment_risk_factors`` Pass-1 would.

    Kept deliberately identical to that block so the distilled dataset matches
    the baseline system's internal decisions.
    """
    t = line.text.strip()
    wc = len(t.split())
    if wc < 2:
        return "skip"
    if _SKIP_RE.match(t):
        return "skip"
    if SUBCAT_PAT.match(t) and wc < 20 and (line.is_bold or line.is_italic or line.is_all_caps):
        return "subheading"
    if line.char_count <= 600 and wc >= 3 and (
        (line.is_bold and not style.body_is_bold)
        or line.is_italic
        or (line.is_all_caps and wc <= 40)
        or line.font_size > style.body_font_size + 0.5
    ):
        return "heading"
    return "body"


def line_features(line, style) -> dict:
    """Flat feature dict for one line.

    Numeric features describe typography and geometry *relative to the document's
    own body style* (so the model is not tied to one PDF's absolute font sizes).
    The raw ``text`` is kept for a TF-IDF representation in the model pipeline.
    """
    t = line.text.strip()
    wc = len(t.split())
    body_size = style.body_font_size or 1.0
    avg_gap = style.avg_line_gap or 1.0
    gap = line.gap_before if 0 <= line.gap_before < 100 else 0.0
    first_x = line.spans[0].x_pos if line.spans else 0.0
    return {
        "text": t,
        "font_size": line.font_size,
        "font_size_delta": line.font_size - body_size,
        "font_size_ratio": line.font_size / body_size,
        "is_bold": int(line.is_bold),
        "is_italic": int(line.is_italic),
        "is_all_caps": int(line.is_all_caps),
        "is_bold_vs_body": int(line.is_bold and not style.body_is_bold),
        "gap_before": gap,
        "gap_ratio": gap / avg_gap,
        "x_pos": first_x,
        "word_count": wc,
        "char_count": line.char_count,
        "ends_period": int(t.endswith(".")),
        "starts_upper": int(bool(t) and t[0].isupper()),
    }


NUMERIC_FEATURES = [
    "font_size",
    "font_size_delta",
    "font_size_ratio",
    "is_bold",
    "is_italic",
    "is_all_caps",
    "is_bold_vs_body",
    "gap_before",
    "gap_ratio",
    "x_pos",
    "word_count",
    "char_count",
    "ends_period",
    "starts_upper",
]
TEXT_FEATURE = "text"


@dataclass
class DocLines:
    """Section lines of one document, with the learned document style."""

    doc_id: str
    lines: list
    style: object
    section: tuple | None


def load_section_lines(pdf_path: str, doc_id: str | None = None) -> DocLines:
    """Parse a PDF and return only the lines inside its Risk Factors section."""
    import os

    doc_id = doc_id or os.path.basename(pdf_path)
    _, spans = extract_spans(pdf_path)
    lines = build_lines(spans)
    if not lines:
        return DocLines(doc_id, [], None, None)
    style = learn_style(lines)
    section = find_risk_section(lines)
    if section is None:
        return DocLines(doc_id, [], style, None)
    si, ei = section
    return DocLines(doc_id, lines[si:ei], style, section)
