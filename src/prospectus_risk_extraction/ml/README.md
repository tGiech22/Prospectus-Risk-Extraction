# ML: line classification

This subpackage reframes risk-factor segmentation as a **supervised line-classification**
problem and gives you the full scikit-learn workflow on data you already have.

## The task

Every line inside a Risk Factors section is one example, labeled:

| label | meaning |
|-------|---------|
| `heading` | starts a new risk factor (the title line) |
| `body` | explanatory text under a heading |
| `subheading` | a category like *Risks Related to Our Business* |
| `skip` | page numbers, table-of-contents lines, noise |

Grouping consecutive `heading` runs then gives the risk **count** the product cares about.

## Where the labels come from (read this)

Labels are currently **distilled from the heuristic** (`analyzer.py` Pass-1), in
[labeling.py](labeling.py) `weak_label()`. So a model trained here learns to *reproduce
the rule system* — the heuristic is its ceiling. That is intentional: it lets you practice
the entire pipeline (features → train → cross-validate → confusion matrix → risk count)
before doing any hand-labeling. When you hand-label real gold lines, replace `weak_label`
(or supply your own `label` column) and nothing else changes.

## Data reality

The `test_fixtures/*.pdf` are one-sentence smoke tests for the word counter (e.g.
`"Hello world."`) — **not** risk-factor data. The real prospectuses live in
`data/sample_pdfs/` (15 at last count), with hand-annotated gold in `data/labels/`.
With ≥ 3 documents `train.py` automatically uses document-grouped cross-validation
(no line from a training doc leaks into its own test fold); with < 3 it falls back
to an optimistic line-level split and prints a loud warning.

## Weak vs gold labels

```bash
prospectus-ml-train data/sample_pdfs                 # --labels weak (default)
prospectus-ml-train data/sample_pdfs --labels gold   # hand annotations in data/labels/
```

`--labels gold` builds the dataset from `data/labels/*.json` instead of `weak_label`.
Gold titles are clean prose that may wrap across several physical lines, so
`gold_line_labels()` (in `labeling.py`) aligns each title to a run of consecutive
lines and marks them `heading`. The builder prints a **per-doc alignment check** —
`heading-runs` should equal `gold-risks`; a `MISMATCH` flag means the matcher needs
tuning for that document. PDFs without a gold file are skipped.

The gold section window is anchored on the gold titles (`gold_section_window()`),
not the heuristic `find_risk_section` — the heuristic can start a few dozen lines
late and clip the first risk(s), so we scan a short lookback before its boundary
to recover them.

## Evaluation: grouped CV + a fixed held-out split

`train.py` always reports document-grouped cross-validation (every doc gets a turn
as test). If `--splits-dir` (default `data/labels/splits/`) has `train.txt` and
`test.txt`, it *also* fits on the train docs and reports once on the held-out test
docs — the frozen number for a baseline table. `val.txt` is left out of both.

> At n=15 the 3-doc test is noisy: which docs land in it dominates the number.
> Treat the **grouped-CV** figure as the headline and the fixed test as a
> secondary stress check until there are ~20–25 labeled docs.

## Usage

```bash
pip install -e ".[ml]"

# 1. Dump the dataset to inspect by hand (recommended first step)
prospectus-ml-dataset data/sample_pdfs -o artifacts/ml/line_dataset.csv

# 2. Train + evaluate + save the model
prospectus-ml-train data/sample_pdfs

# 3. Run the saved model on new PDFs (reconstructs title/body/word_count per risk)
prospectus-ml-predict "data/sample_pdfs/1A. Aegerion Pharmaceuticals.pdf"

# 4. Close the loop: score the model's segmentation against gold
prospectus-ml-predict data/sample_pdfs --eval
```

`prospectus-ml-predict` loads `artifacts/models/line_classifier.joblib`, classifies
each Risk Factors line, then segments predicted `heading` runs back into
`(title, body, word_count)` risks — the same shape `analyzer` emits, so the two are
directly comparable. `--eval` reports the Task-B metrics from
`docs/evaluation_and_baseline_reporting.md` (exact-count accuracy, count MAE/bias,
fuzzy title recall@1) for every PDF that has a gold file.

## Files

| file | role |
|------|------|
| [labeling.py](labeling.py) | per-line features + weak label (reuses analyzer parsing) |
| [dataset.py](dataset.py) | build a `pandas` DataFrame / CSV across PDFs |
| [train.py](train.py) | sklearn pipeline (layout features + TF-IDF → logistic regression), grouped CV, report, risk-count check |
| [predict.py](predict.py) | load the saved model, classify a new PDF, reconstruct risks, score segmentation vs gold |

## Next steps (the learning path)

1. **Hand-label** a few real prospectuses → swap weak labels for gold; re-run.
2. **More PDFs** → grouped CV gives a real generalization number to beat the heuristic.
3. **Better model** → try gradient boosting on numeric features, then a transformer
   (DistilBERT on line text, or LayoutLM to fuse text + geometry) using the same dataset.
4. ~~**Close the loop** → feed predicted `heading` lines back into segmentation and score
   with the metrics in `docs/evaluation_and_baseline_reporting.md`.~~ **Done** —
   see `prospectus-ml-predict --eval` ([predict.py](predict.py)). Compare its numbers
   against the heuristic baseline on the same `data/labels/splits/test.txt` docs.
