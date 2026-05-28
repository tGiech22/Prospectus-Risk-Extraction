# Prospectus-Risk-Extraction

This project extracts and analyzes risk factors from biotech prospectus PDFs using
layout-aware heuristics and text processing.

## Project Structure

- `src/prospectus_risk_extraction/`: main Python package
- `data/sample_pdfs/`: sample PDF inputs
- `test_fixtures/`: small fixture PDFs for regression tests
- `artifacts/`: generated reports and outputs from runs
- `docs/`: labeling guidelines and baseline evaluation guide

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

## CLI Commands

```bash
prospectus-extract-risks "data/sample_pdfs/1A. Aegerion Pharmaceuticals.pdf"
prospectus-count-words -o artifacts/spreadsheets/word_counts.xlsx "data/sample_pdfs/1A. Aegerion Pharmaceuticals.pdf"
prospectus-analyze data/sample_pdfs -o artifacts/reports/results.csv
```
