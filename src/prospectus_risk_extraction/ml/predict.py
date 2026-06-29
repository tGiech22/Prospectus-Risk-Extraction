"""Run the trained line classifier on new PDFs and reconstruct risk factors.

This closes the loop: :mod:`.train` produces ``line_classifier.joblib`` (a model
that labels each section line ``heading`` / ``body`` / ``subheading`` / ``skip``);
here we load that model, classify a fresh prospectus, and *segment* the predicted
labels back into ``(title, body, word_count)`` risk factors - the same output the
heuristic ``analyzer`` produces, so the two are directly comparable.

    # predict risks for one PDF (or a folder) and print JSON
    prospectus-ml-predict data/sample_pdfs/1A.\\ Aegerion\\ Pharmaceuticals.pdf

    # score the model's segmentation against gold (the metrics that matter)
    prospectus-ml-predict data/sample_pdfs --eval

The reconstruction mirrors ``count_risks`` in :mod:`.train`: a maximal run of
consecutive ``heading`` lines is one risk; the ``body`` lines that follow (until
the next heading) are its body. ``subheading`` / ``skip`` lines break a heading
run but contribute no text.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

import joblib
import pandas as pd

from .dataset import find_pdfs
from .labeling import (
    DEFAULT_LABELS_DIR,
    NUMERIC_FEATURES,
    TEXT_FEATURE,
    _norm_text,
    line_features,
    load_gold,
    load_section_lines,
)

DEFAULT_MODEL = "artifacts/models/line_classifier.joblib"

# Title-match threshold for the segmentation score (see
# docs/evaluation_and_baseline_reporting.md, Task B2 "Title recall@1 (fuzzy)").
TITLE_SIM_THRESHOLD = 0.85


@dataclass
class PredictedRisk:
    """One reconstructed risk factor: a heading run plus its following body."""

    title: str
    body: str
    word_count: int


def reconstruct_risks(lines: list, labels: list[str]) -> list[PredictedRisk]:
    """Group predicted per-line ``labels`` into risk factors.

    A risk opens on the first ``heading`` line; consecutive ``heading`` lines
    extend its title (titles wrap across physical lines). ``body`` lines after
    the title become the body until the next heading opens the following risk.
    Lines before the first heading, and ``skip`` / ``subheading`` lines, add no
    text but do close any open heading run.
    """
    risks: list[PredictedRisk] = []
    title_parts: list[str] = []
    body_parts: list[str] = []
    in_heading = False

    def flush() -> None:
        if title_parts:
            body = " ".join(body_parts).strip()
            risks.append(
                PredictedRisk(
                    title=" ".join(title_parts).strip(),
                    body=body,
                    word_count=len(body.split()),
                )
            )

    for line, label in zip(lines, labels):
        text = line.text.strip()
        if label == "heading":
            if not in_heading:  # a new heading run starts the next risk
                flush()
                title_parts, body_parts = [], []
            title_parts.append(text)
            in_heading = True
        else:
            in_heading = False
            if label == "body" and title_parts:
                body_parts.append(text)
    flush()
    return risks


def predict_risks(
    pdf_path: str, model, doc_id: str | None = None
) -> list[PredictedRisk]:
    """Classify a PDF's Risk Factors lines and reconstruct its risk factors."""
    doc = load_section_lines(pdf_path, doc_id)
    if not doc.lines:
        return []
    feats = [line_features(line, doc.style) for line in doc.lines]
    X = pd.DataFrame(feats)[NUMERIC_FEATURES + [TEXT_FEATURE]]
    labels = list(model.predict(X))
    return reconstruct_risks(doc.lines, labels)


# ---------------------------------------------------------------------------
# Evaluation against gold (segmentation metrics)
# ---------------------------------------------------------------------------
def _title_recall(pred_titles: list[str], gold_titles: list[str]) -> float:
    """Fraction of gold titles with a fuzzy match (>= threshold) in predictions."""
    if not gold_titles:
        return 0.0
    preds = [_norm_text(t) for t in pred_titles]
    hits = 0
    for gold in (_norm_text(t) for t in gold_titles):
        best = max(
            (SequenceMatcher(None, gold, p).ratio() for p in preds), default=0.0
        )
        if best >= TITLE_SIM_THRESHOLD:
            hits += 1
    return hits / len(gold_titles)


def evaluate(pdfs: list[str], model, labels_dir: str) -> None:
    """Score predicted segmentation against gold (count + title recall, per doc).

    Reports the Task-B metrics from ``docs/evaluation_and_baseline_reporting.md``:
    exact count accuracy, count MAE, count bias, and mean fuzzy title recall@1.
    PDFs without a gold file are skipped (their truth is unknown).
    """
    print("\n=== Segmentation vs gold (model predictions) ===")
    print(f"{'doc':<45}{'gold':>6}{'pred':>6}{'diff':>6}{'title_rec':>11}")
    diffs, recalls, exact = [], [], 0
    for path in pdfs:
        doc_id = Path(path).name
        gold = load_gold(doc_id, labels_dir)
        if gold is None:
            continue
        gold_risks = gold.get("risk_factors", [])
        gold_titles = [rf.get("title", "") for rf in gold_risks]
        preds = predict_risks(path, model, doc_id)
        diff = len(preds) - len(gold_risks)
        recall = _title_recall([p.title for p in preds], gold_titles)
        diffs.append(diff)
        recalls.append(recall)
        exact += diff == 0
        print(
            f"{doc_id:<45}{len(gold_risks):>6}{len(preds):>6}{diff:>+6}{recall:>11.2f}"
        )

    n = len(diffs)
    if n == 0:
        print(f"(No gold files matched the loaded PDFs in {labels_dir})")
        return
    mae = sum(abs(d) for d in diffs) / n
    bias = sum(diffs) / n
    print(
        f"\nDocs scored: {n}  |  exact-count acc: {exact / n:.0%}  |  "
        f"count MAE: {mae:.2f}  |  count bias: {bias:+.2f}  |  "
        f"mean title recall@1: {sum(recalls) / n:.0%}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="PDF file or folder to run the model on")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help="trained .joblib")
    parser.add_argument(
        "--eval",
        action="store_true",
        help="score predictions against gold in --labels-dir instead of dumping risks",
    )
    parser.add_argument("--labels-dir", default=DEFAULT_LABELS_DIR)
    parser.add_argument(
        "-o", "--output", help="write predicted risks as JSON to this path"
    )
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        print(f"No model at {model_path}. Train one first: prospectus-ml-train ...")
        return
    model = joblib.load(model_path)

    pdfs = find_pdfs(args.pdf_path)
    if not pdfs:
        print(f"No PDFs found under {args.pdf_path!r}")
        return

    if args.eval:
        evaluate(pdfs, model, args.labels_dir)
        return

    out = {}
    for path in pdfs:
        doc_id = Path(path).name
        risks = predict_risks(path, model, doc_id)
        out[doc_id] = [asdict(r) for r in risks]
        print(f"{doc_id}: {len(risks)} risk(s)")

    if args.output:
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=2))
        print(f"\nWrote predictions for {len(out)} doc(s) to {dest}")
    elif len(out) == 1:
        print(json.dumps(next(iter(out.values())), indent=2))


if __name__ == "__main__":
    main()
