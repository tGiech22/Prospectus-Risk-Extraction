"""Train a line classifier (heading / body / subheading / skip) and evaluate it.

The model is a scikit-learn pipeline: numeric layout features (standardized) +
TF-IDF over the line text -> logistic regression. Evaluation is honest about the
data you have:

* >= 3 documents -> document-grouped cross-validation (no line from a training
  doc leaks into its own test fold). This is the only setup that estimates
  generalization to *new* prospectuses.
* < 3 documents  -> a stratified line-level split, with a loud warning that the
  score is optimistic (lines from the same document are highly correlated).

    python -m prospectus_risk_extraction.ml.train data/sample_pdfs

Add more real PDFs to the folder and the evaluation automatically upgrades to
grouped CV - no code change.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import GroupKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .dataset import build_dataframe, build_gold_dataframe, find_pdfs
from .labeling import DEFAULT_LABELS_DIR, LABELS, NUMERIC_FEATURES, TEXT_FEATURE


def build_model() -> Pipeline:
    """Numeric layout features + TF-IDF text -> balanced logistic regression."""
    features = ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
            (
                "text",
                TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=2),
                TEXT_FEATURE,
            ),
        ]
    )
    return Pipeline(
        [
            ("features", features),
            (
                "clf",
                LogisticRegression(max_iter=2000, class_weight="balanced"),
            ),
        ]
    )


def evaluate(df: pd.DataFrame, model: Pipeline) -> np.ndarray:
    """Cross-validated predictions, grouped by document when possible."""
    X = df[NUMERIC_FEATURES + [TEXT_FEATURE]]
    y = df["label"].to_numpy()
    n_docs = df["doc_id"].nunique()

    if n_docs >= 3:
        n_splits = min(5, n_docs)
        print(f"Evaluation: {n_splits}-fold document-grouped CV over {n_docs} docs.")
        cv = GroupKFold(n_splits=n_splits)
        return cross_val_predict(model, X, y, groups=df["doc_id"], cv=cv)

    print(
        f"WARNING: only {n_docs} document(s). Using a stratified line split, but the\n"
        "         score is OPTIMISTIC - lines from one prospectus are correlated, so\n"
        "         this does NOT estimate accuracy on a new document. Add more PDFs to\n"
        "         get document-grouped cross-validation."
    )
    idx = np.arange(len(df))
    train_idx, test_idx = train_test_split(
        idx, test_size=0.25, random_state=0, stratify=y
    )
    model.fit(X.iloc[train_idx], y[train_idx])
    preds = np.empty(len(df), dtype=object)
    preds[test_idx] = model.predict(X.iloc[test_idx])
    preds[train_idx] = y[train_idx]  # not scored; only test_idx is reported below
    # Restrict the report to held-out rows.
    mask = np.zeros(len(df), dtype=bool)
    mask[test_idx] = True
    df.attrs["eval_mask"] = mask
    return preds


def report(df: pd.DataFrame, preds: np.ndarray) -> None:
    """Print a classification report and confusion matrix on evaluated rows."""
    y = df["label"].to_numpy()
    mask = df.attrs.get("eval_mask")
    if mask is not None:
        y, preds = y[mask], preds[mask]
    present = [l for l in LABELS if l in set(y) | set(preds)]
    print("\n=== Classification report ===")
    print(classification_report(y, preds, labels=present, zero_division=0))
    print("Confusion matrix (rows = true, cols = predicted):")
    cm = confusion_matrix(y, preds, labels=present)
    header = "        " + "".join(f"{l[:6]:>8}" for l in present)
    print(header)
    for label, row in zip(present, cm):
        print(f"{label[:6]:>6}  " + "".join(f"{v:>8}" for v in row))


def segmentation_check(df: pd.DataFrame, preds: np.ndarray) -> None:
    """Compare risk counts from predicted vs heuristic headings, per document.

    A "risk" is a run of consecutive ``heading`` lines followed by body. This is
    the payoff: it shows how line-level accuracy turns into the document-level
    number the product cares about.
    """

    def count_risks(labels: list[str]) -> int:
        risks, prev_heading = 0, False
        for lab in labels:
            if lab == "heading":
                if not prev_heading:
                    risks += 1
                prev_heading = True
            else:
                prev_heading = False
        return risks

    print("\n=== Risk count: true labels vs model predictions (per doc) ===")
    df = df.assign(pred=preds)
    for doc_id, g in df.groupby("doc_id"):
        true = count_risks(g["label"].tolist())
        pred = count_risks(g["pred"].tolist())
        print(f"  {doc_id:<45} true={true:>4}  model={pred:>4}  diff={pred - true:+d}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="PDF file or folder of training PDFs")
    parser.add_argument(
        "-m", "--model-out", default="artifacts/models/line_classifier.joblib"
    )
    parser.add_argument(
        "--labels",
        choices=["weak", "gold"],
        default="weak",
        help="weak = heuristic-distilled (default); gold = hand annotations in --labels-dir",
    )
    parser.add_argument("--labels-dir", default=DEFAULT_LABELS_DIR)
    args = parser.parse_args()

    pdfs = find_pdfs(args.pdf_path)
    if not pdfs:
        print(f"No PDFs found under {args.pdf_path!r}")
        return
    print(f"Building dataset from {len(pdfs)} PDF(s) [labels={args.labels}]...")
    if args.labels == "gold":
        df = build_gold_dataframe(pdfs, args.labels_dir)
    else:
        df = build_dataframe(pdfs)
    if df.empty or df["label"].nunique() < 2:
        print("Not enough labeled data to train (need >= 2 classes).")
        return
    print(f"\n{len(df)} lines | {df['doc_id'].nunique()} doc(s) | label counts:")
    print(df["label"].value_counts().to_string())

    model = build_model()
    preds = evaluate(df, model)
    report(df, preds)
    segmentation_check(df, preds)

    # Fit a final model on ALL data for downstream use / inference.
    model.fit(df[NUMERIC_FEATURES + [TEXT_FEATURE]], df["label"])
    out = Path(args.model_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out)
    print(f"\nSaved model trained on all {len(df)} lines to {out}")


if __name__ == "__main__":
    main()
