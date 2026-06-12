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

from .labeling import line_features, load_section_lines, weak_label


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
