# Prospectus Risk Extraction

**Turning unstructured biotech IPO prospectuses into structured risk-factor data — with a rule-based baseline, a learned line classifier, and an honest evaluation harness.**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Status](https://img.shields.io/badge/tests-pytest-green)

SEC prospectuses bury a company's risk profile in a long, inconsistently formatted "Risk Factors" section — dozens of individually-titled risks, rendered differently in every filing (bold headings in one, ALL-CAPS noun phrases in another, plain wrapped sentences in a third). This project parses those PDFs and extracts each risk factor as structured `(title, body, word_count)`, then **measures how well it does** against hand-labeled gold data.

---

## Why this project is interesting

- **Real, messy data.** 15 biotech IPO prospectuses spanning ~20 years of filing conventions — no two formatted the same way.
- **A baseline *and* a learned model.** A transparent rule-based pipeline sets the bar; a scikit-learn line classifier is trained to beat it, distilling the heuristic and then learning from hand-annotated gold labels.
- **Evaluation done right.** Document-grouped cross-validation (no line from a training filing leaks into its own test fold), a frozen held-out split, and metrics that report the document-level number the product actually cares about — not just line accuracy.
- **End-to-end and reproducible.** PDF in → structured risks out → CSV / Excel / JSON reports, all from `pip install -e .` and a single CLI command.

## Results

Line-level classification (heading / body / subheading / skip), evaluated with **5-fold document-grouped cross-validation** over 15 filings (~13.7k labeled lines):

| Metric | Score |
|--------|-------|
| Overall accuracy | **0.97** |
| Heading F1 | **0.91** |
| Macro F1 | 0.83 |

Risk-factor segmentation (reconstructing whole risks from predicted lines, scored against gold):

| Metric | Score |
|--------|-------|
| Mean title recall@1 (fuzzy ≥ 0.85) | **96%** |
| Risk-count MAE | 2.4 risks / doc |
| Risk-count bias | +2.1 (slight over-splitting) |

The honest take: heading detection generalizes well, and titles are recovered almost perfectly; the remaining gap is a handful of over-split risks on the hardest plain-text filings — analyzed per-document in [docs/evaluation_and_baseline_reporting.md](docs/evaluation_and_baseline_reporting.md).

## How it works

```
PDF ──▶ layout parsing ──▶ locate "Risk Factors" ──▶ segment risks ──▶ structured output
        (spans→lines→        (regex + typography      ┌─ heuristic: 3-pass cascade
         paragraphs,          scoring)                 └─ learned:   line classifier
         font/gap features)                                          (layout + TF-IDF → LogReg)
```

**1. Layout-aware parsing** ([analyzer.py](src/prospectus_risk_extraction/analyzer.py)) — extracts text spans with font, weight, size, and position via PyMuPDF, then groups them into lines and paragraphs and *learns each document's own body style* so detection isn't tied to absolute font sizes.

**2. Section localization** — finds the Risk Factors heading and the next major section using regex patterns scored by typography (bold, caps, font size) and table-of-contents disambiguation.

**3a. Heuristic segmentation (baseline)** — a three-pass cascade that adapts to a document's formatting: font-style headings → indentation levels → text-pattern fallback, so it degrades gracefully from cleanly-formatted to plain-text PDFs.

**3b. Learned segmentation** ([ml/](src/prospectus_risk_extraction/ml/)) — a scikit-learn pipeline (standardized layout features + TF-IDF over line text → balanced logistic regression) classifies each line, then risks are reconstructed by collapsing consecutive `heading` runs and attaching their following `body`. Trainable on weak heuristic-distilled labels *or* hand-annotated gold.

## Quickstart

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[ml]"        # omit [ml] for just the heuristic pipeline
```

**Heuristic pipeline** — extract risks and generate CSV/Excel/JSON reports:

```bash
# Single PDF → printed risks
prospectus-extract-risks "data/sample_pdfs/1A. Aegerion Pharmaceuticals.pdf"

# Whole folder → summary + detailed + JSON + Excel reports
prospectus-analyze data/sample_pdfs -o artifacts/reports/results.csv
```

**Learned pipeline** — build a dataset, train + evaluate, predict on new filings:

```bash
prospectus-ml-train   data/sample_pdfs --labels gold   # grouped-CV eval + saves model
prospectus-ml-predict data/sample_pdfs --eval          # score segmentation vs gold
prospectus-ml-predict "data/sample_pdfs/Aduro Biotech.pdf"   # predict on one PDF → JSON
```

Run the tests with `pytest`.

## Repository layout

| Path | Contents |
|------|----------|
| [src/prospectus_risk_extraction/](src/prospectus_risk_extraction/) | Core package: `analyzer.py`, `extract_risks.py`, and the `ml/` training/eval/predict pipeline |
| [data/sample_pdfs/](data/sample_pdfs/) | 15 biotech IPO prospectus PDFs |
| [data/labels/](data/labels/) | Hand-annotated gold risk factors + train/val/test splits |
| [docs/](docs/) | [Annotation guidelines](docs/annotation_guidelines.md) and [evaluation methodology](docs/evaluation_and_baseline_reporting.md) |
| [tests/](tests/) | pytest suite (feature/label consistency, word counting, imports) |
| [artifacts/](artifacts/) | Generated reports, models, and datasets |

## Tech stack

Python · PyMuPDF · pdfplumber · scikit-learn · pandas / NumPy · openpyxl · pytest
</content>
</invoke>
