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

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from ..analyzer import (
    SUBCAT_PAT,
    build_lines,
    extract_spans,
    find_risk_section,
    learn_style,
)

LABELS = ["heading", "body", "subheading", "skip"]

_SKIP_RE = re.compile(r"^(table of contents|page\s+\d|\d+\s*$)", re.IGNORECASE)

DEFAULT_LABELS_DIR = "data/labels"


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


# ---------------------------------------------------------------------------
# Gold labels (replace the weak/heuristic labels with hand-annotated truth)
# ---------------------------------------------------------------------------
def _canon(name: str) -> str:
    """Canonical key for a doc id / filename: lowercase alphanumerics only.

    Reconciles the two naming conventions in the repo: gold ``doc_id`` uses
    underscores (``1A__Aegerion_Pharmaceuticals.pdf``) while the PDF on disk
    uses dots/spaces (``1A. Aegerion Pharmaceuticals.pdf``). Both collapse to
    the same key.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _norm_text(s: str) -> str:
    """Lowercase, collapse whitespace - for matching line text to gold titles."""
    return re.sub(r"\s+", " ", s.strip().lower())


_GOLD_INDEX: dict | None = None


def _gold_index(labels_dir: str) -> dict:
    """Map canonical doc key -> gold json path, scanning ``labels_dir`` once."""
    global _GOLD_INDEX
    if _GOLD_INDEX is not None:
        return _GOLD_INDEX
    index = {}
    for path in Path(labels_dir).glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        doc_id = data.get("doc_id") or path.stem
        index[_canon(doc_id)] = str(path)
    _GOLD_INDEX = index
    return index


def load_gold(doc_id: str, labels_dir: str = DEFAULT_LABELS_DIR) -> dict | None:
    """Return the gold annotation dict for ``doc_id``, or None if not labeled."""
    path = _gold_index(labels_dir).get(_canon(doc_id))
    if path is None:
        return None
    return json.loads(Path(path).read_text())


def gold_line_labels(lines: list, gold: dict, style) -> list[str]:
    """Align analyzer-parsed section lines to gold risk titles -> per-line labels.

    A gold title is clean prose that may wrap across several physical ``Line``
    objects. We walk the lines in order and, at each position, try to reconstruct
    an unconsumed gold title from a run of consecutive lines. Every line in a
    matched run is labeled ``heading`` (so ``count_risks`` collapses the run to
    exactly one risk); the rest are ``skip`` (noise), ``subheading`` (category),
    or ``body``.
    """
    titles = [_norm_text(rf.get("title", "")) for rf in gold.get("risk_factors", [])]
    titles = [t for t in titles if t]
    used = [False] * len(titles)
    norm_lines = [_norm_text(ln.text) for ln in lines]

    def match_run(i: int) -> tuple[int, int]:
        """Best (title_idx, n_lines) for a title starting at line ``i``, else (-1, 0)."""
        best = (-1, 0)
        for ti, title in enumerate(titles):
            if used[ti] or not norm_lines[i] or not title.startswith(norm_lines[i][:8]):
                continue
            acc, k = "", 0
            while i + k < len(norm_lines) and len(acc) < len(title) + 5:
                cand = (acc + " " + norm_lines[i + k]).strip()
                head = title[: len(cand)]
                if title.startswith(cand) or SequenceMatcher(None, cand, head).ratio() >= 0.9:
                    acc, k = cand, k + 1
                    if len(acc) >= len(title) * 0.95:
                        break
                else:
                    break
            # Accept a full reconstruction, or a confident partial (wrapped title).
            covered = len(acc) >= min(40, len(title) * 0.6)
            if k > 0 and covered and k > best[1]:
                best = (ti, k)
        return best

    out = ["body"] * len(lines)
    i = 0
    while i < len(lines):
        ti, k = match_run(i)
        if ti >= 0:
            used[ti] = True
            for j in range(i, i + k):
                out[j] = "heading"
            i += k
            continue
        t = norm_lines[i]
        wc = len(t.split())
        if wc < 2 or _SKIP_RE.match(t):
            out[i] = "skip"
        elif SUBCAT_PAT.match(lines[i].text.strip()) and wc < 20 and (
            lines[i].is_bold or lines[i].is_italic or lines[i].is_all_caps
        ):
            out[i] = "subheading"
        i += 1
    return out
