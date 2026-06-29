"""Build a line-classification dataset from one or more prospectus PDFs.

Each row is one line inside a Risk Factors section: layout/text features plus a
(weak) label and the source ``doc_id`` (used later for document-grouped
cross-validation). Run as a CLI to dump a CSV you can open and inspect - reading
the dataset by hand is the fastest way to understand what the model sees.

    python -m prospectus_risk_extraction.ml.dataset data/sample_pdfs -o artifacts/ml/lines.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .labeling import (
    DEFAULT_LABELS_DIR,
    gold_line_labels,
    line_features,
    load_gold,
    load_gold_section_lines,
    load_section_lines,
    weak_label,
)


def build_dataframe(pdf_paths: list[str]) -> pd.DataFrame:
    """Extract features + weak labels for every section line across PDFs."""
    rows = []
    for path in pdf_paths:
        doc = load_section_lines(path)
        if not doc.lines:
            print(f"  skip {doc.doc_id}: no Risk Factors section / no text")
            continue
        for line in doc.lines:
            feats = line_features(line, doc.style)
            feats["label"] = weak_label(line, doc.style)
            feats["doc_id"] = doc.doc_id
            rows.append(feats)
        print(f"  {doc.doc_id}: {len(doc.lines)} section lines")
    return pd.DataFrame(rows)


def build_gold_dataframe(
    pdf_paths: list[str], labels_dir: str = DEFAULT_LABELS_DIR
) -> pd.DataFrame:
    """Like :func:`build_dataframe` but labels come from hand-annotated gold.

    PDFs without a matching gold file under ``labels_dir`` are skipped (their
    truth is unknown). For each labeled doc we also print the heading-run count
    vs the gold risk count - the alignment sanity check: they should match.
    """
    rows = []
    for path in pdf_paths:
        doc_id = Path(path).name
        gold = load_gold(doc_id, labels_dir)
        if gold is None:
            print(f"  skip {doc_id}: no gold file in {labels_dir}")
            continue
        doc = load_gold_section_lines(path, gold, doc_id)
        if not doc.lines:
            print(f"  skip {doc.doc_id}: no Risk Factors section / no text")
            continue
        labels = gold_line_labels(doc.lines, gold, doc.style)
        for line, label in zip(doc.lines, labels):
            feats = line_features(line, doc.style)
            feats["label"] = label
            feats["doc_id"] = doc.doc_id
            rows.append(feats)
        runs = _count_heading_runs(labels)
        gold_n = len(gold.get("risk_factors", []))
        flag = "" if runs == gold_n else "  <-- MISMATCH (tune matcher)"
        print(
            f"  {doc.doc_id}: {len(doc.lines)} lines | "
            f"heading-runs={runs} gold-risks={gold_n}{flag}"
        )
    return pd.DataFrame(rows)


def _count_heading_runs(labels: list[str]) -> int:
    """Number of maximal consecutive ``heading`` runs (== number of risks)."""
    runs, prev = 0, False
    for lab in labels:
        if lab == "heading" and not prev:
            runs += 1
        prev = lab == "heading"
    return runs


def find_pdfs(root: str) -> list[str]:
    """Return all PDFs under ``root`` (file or directory)."""
    p = Path(root).expanduser()
    if p.is_file() and p.suffix.lower() == ".pdf":
        return [str(p)]
    return sorted(str(x) for x in p.rglob("*.pdf"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="PDF file or folder to scan recursively")
    parser.add_argument("-o", "--output", default="artifacts/ml/line_dataset.csv")
    args = parser.parse_args()

    pdfs = find_pdfs(args.pdf_path)
    if not pdfs:
        print(f"No PDFs found under {args.pdf_path!r}")
        return
    print(f"Building dataset from {len(pdfs)} PDF(s)...")
    df = build_dataframe(pdfs)
    if df.empty:
        print("No usable lines extracted.")
        return

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nWrote {len(df)} rows from {df['doc_id'].nunique()} doc(s) to {out}")
    print("\nLabel distribution:")
    print(df["label"].value_counts().to_string())


if __name__ == "__main__":
    main()
