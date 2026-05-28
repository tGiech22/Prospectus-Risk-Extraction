# Evaluation and heuristic baseline reporting

This guide explains **how to measure** your current rule-based pipeline (`prospectus-analyze` / `analyzer.py`) against gold labels, and **how to present** those numbers in a README, report, or interview.

It assumes you have (or will have) labels created per [annotation_guidelines.md](annotation_guidelines.md). No automated eval code is required to follow this document—you can score runs manually or in a spreadsheet first.

---

## What is the “heuristic baseline”?

The **heuristic baseline** is the performance of your **existing, non-learned** pipeline:

1. Parse PDF layout (spans → lines → paragraphs).
2. Find the Risk Factors section (regex + typography scoring).
3. Segment risks (3-pass cascade: font → indent → text patterns).
4. Output `(title, body, word_count)` per risk.

It has **no trained weights**. Every improvement you report later (classifier, transformer, etc.) should be compared against this baseline on the **same labeled test split**.

Always name the tool and version in your write-up, e.g. “Baseline: `prospectus-analyze` v0.1.0, commit `abc123`, evaluated on `data/labels/test/` (N=12 PDFs).”

---

## Evaluation tasks and metrics

Split evaluation into **section** and **segmentation**. Report both; segmentation is usually the headline.

### Task A — Section localization

**Gold:** `section.start_line`, `section.end_line` (or equivalent page/heading anchors).  
**Prediction:** from analyzer debug output or re-derived via `find_risk_section(lines)`.

| Metric | Formula / rule | Interpretation |
|--------|----------------|----------------|
| **Section found rate** | % of docs where prediction returns a section (not `FAILED-NO-SECTION`) | Coverage |
| **Start error (lines)** | `abs(pred_start - gold_start)` | Off-by-one heading detection |
| **End error (lines)** | `abs(pred_end - gold_end)` | Wrong next-section boundary |
| **Section IoU** | `len(range intersection) / len(range union)` on line indices | Single number for overlap; 1.0 = perfect |
| **Section exact match** | start error ≤ 1 **and** end error ≤ 1 (tune tolerance) | Strict doc-level check |

Example: gold lines 100–500, pred 105–490 → intersection 385, union 400 → IoU = 0.9625.

If you only labeled **heading text** (no line numbers), you can still score **found / not found** and manually check whether the predicted section contains all gold risks.

### Task B — Risk segmentation (primary)

**Gold:** ordered list `[(title_i, body_i)]`.  
**Prediction:** `risk_factors` from JSON output or `*_detailed.csv`.

#### B1. Risk count

| Metric | Formula |
|--------|---------|
| **Exact count accuracy** | % docs where `pred_count == gold_count` |
| **Count MAE** | `mean(|pred_count - gold_count|)` over docs |
| **Count bias** | `mean(pred_count - gold_count)` — positive = over-splitting |

Your `test_fixtures/expected_counts.txt` implements only **exact count per file**—useful but insufficient alone.

#### B2. Title matching

Normalize titles before compare:

- lowercase
- collapse whitespace
- strip trailing punctuation

| Metric | Definition |
|--------|------------|
| **Title exact match rate** | % of gold titles with an exact normalized match in predictions |
| **Title recall@1 (fuzzy)** | % of gold titles whose best pred title has similarity ≥ 0.85 (e.g. `difflib.SequenceMatcher`) |

#### B3. Risk-level boundary F1 (recommended headline metric)

A **predicted risk** is a true positive if:

1. It matches **at most one** gold risk (one-to-one matching), and  
2. **Title similarity** ≥ 0.85 (normalized fuzzy or exact), and  
3. **Body overlap** ≥ 0.80 token IoU (or character-level Jaccard on `body`).

Unmatched predictions → **false positives**. Unmatched gold → **false negatives**.

```
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2 * precision * recall / (precision + recall)
```

Compute **per document**, then macro-average across docs (treat each PDF equally).

#### B4. Word count (secondary)

For matched risk pairs only:

| Metric | Formula |
|--------|---------|
| **Word count MAE** | `mean(|pred_word_count - gold_word_count|)` |
| **Word count MAPE** | mean absolute % error vs gold (skip very short bodies) |

This reflects your original product goal (length analytics) but should not replace boundary F1.

### Task C — End-to-end doc success (optional summary)

A document **passes** if:

- Section IoU ≥ 0.95 (or section found and all gold titles appear in pred section), **and**
- Segmentation macro-F1 ≥ 0.80 (choose threshold and stick to it).

Report **doc success rate** = passes / N. Easy for non-technical readers.

---

## Data splits

Keep a simple split list before scoring:

```text
data/labels/splits/
  train.txt    # doc_ids — for future model training only
  val.txt      # tune rules / thresholds
  test.txt     # never used until final baseline table
```

**Rule:** the baseline number you put on your resume comes from **`test.txt` only**, after you stop changing heuristics.

---

## How to produce predictions for scoring

### 1. Run the analyzer on labeled PDFs only

Put labeled PDFs in one folder (or symlink). Run:

```bash
prospectus-analyze data/labeled_pdfs -o artifacts/reports/eval_run.csv
```

Outputs (under `artifacts/`):

| File | Use for evaluation |
|------|-------------------|
| `eval_run_summary.csv` | Per-doc count, method, warnings |
| `eval_run_detailed.csv` | Predicted titles and word counts |
| `eval_run_full.json` | Full `risk_factors` list per file |

### 2. Align gold and prediction by `doc_id`

Use the **filename** as key: `1A. Aegerion Pharmaceuticals.pdf`.

Gold: `data/labels/1A. Aegerion Pharmaceuticals.pdf.json`  
Pred: entry in `eval_run_full.json` where `filename` matches.

---

## Manual baseline workflow (spreadsheet)

Best for your first 5–10 labeled PDFs before any eval script exists.

### Sheet 1 — `per_document`

| doc_id | split | gold_count | pred_count | count_match | section_ok | notes |
|--------|-------|------------|------------|-------------|------------|-------|
| foo.pdf | test | 42 | 40 | 0 | 1 | under-split |

Formulas:

- `count_match` = `(gold_count = pred_count)`
- `section_ok` = manual 0/1 after checking PDF

Aggregate:

- Count exact accuracy = `AVERAGE(count_match)`
- Count MAE = `AVERAGE(ABS(pred_count - gold_count))`

### Sheet 2 — `per_risk` (long format)

| doc_id | source | rf_id | title |
|--------|--------|-------|-------|
| foo.pdf | gold | 1 | We have incurred... |
| foo.pdf | pred | 1 | We have incurred... |

1. Paste all gold titles and all pred titles.  
2. Manually mark matches (color / `match_id` column).  
3. Count TP, FP, FN per doc → precision, recall, F1.

### Sheet 3 — `errors` (for portfolio narrative)

| doc_id | error_type | gold_excerpt | pred_excerpt |
|--------|------------|--------------|--------------|
| bar.pdf | over_split | single risk X | split into 2 |

Typical `error_type` values: `over_split`, `under_split`, `wrong_section`, `intro_as_risk`, `missed_heading`, `toc_false_positive`.

This sheet becomes your “error analysis” section—very strong in interviews.

---

## Worked example (one document)

**Gold (3 risks):**

1. Title: `We have no revenues` — body: 120 words  
2. Title: `Clinical trials may fail` — body: 200 words  
3. Title: `We rely on third parties` — body: 150 words  

**Prediction (3 risks):**

1. `We have no revenues` — 115 words → **TP** (title match, body IoU high)  
2. `Clinical trials may fail` — 95 words → **TP** (title match, body slightly short but IoU may still pass)  
3. `Investing in our stock involves risk` — 80 words → **FP** (intro; no gold match)  
4. *(missing)* `We rely on third parties` → **FN**

TP=2, FP=1, FN=1 → precision = 2/3, recall = 2/3, F1 ≈ 0.67.

Count MAE for this doc = |3 - 3| = 0 (misleadingly good because intro was counted as a risk).

**Lesson:** always report **boundary F1**, not count alone.

---

## Reporting template (README or report section)

Use a fixed structure so results are comparable over time.

### 1. Dataset

```markdown
## Evaluation set

- **Source:** biotech IPO / prospectus PDFs
- **Size:** 22 documents (train 12 / val 5 / test 5)
- **Annotation:** full risk title + body; section boundaries on 18/22
- **Guidelines:** docs/annotation_guidelines.md
```

### 2. Baseline system

```markdown
## Baseline (heuristic)

- **System:** layout-aware 3-pass cascade (`prospectus-analyze`)
- **Dependencies:** PyMuPDF, rule-based section detection and segmentation
- **No training data used**
```

### 3. Results table (test split only)

```markdown
| Metric | Test (n=5) |
|--------|------------|
| Section found rate | 100% |
| Mean section IoU | 0.94 |
| Risk count exact accuracy | 60% |
| Risk count MAE | 2.4 |
| Macro segmentation F1 | 0.78 |
| Matched risk word-count MAE | 18 words |
```

### 4. Breakdown by extraction method

From `eval_run_summary.csv`, group test docs by `Method` column:

```markdown
| Method | n | Macro F1 |
|--------|---|----------|
| font-standalone-merged | 3 | 0.91 |
| indent-paragraph | 1 | 0.62 |
| text-paragraph | 1 | 0.55 |
```

Shows **where** the heuristic fails—excellent for interviews.

### 5. Error analysis (3–5 bullets)

```markdown
- **Over-splitting** on plain-text PDFs without bold headings (2 docs).
- **Intro paragraph** classified as first risk when font detection is weak (1 doc).
- **Section end** early on one filing where “Management’s Discussion” was not detected as heading styled.
```

### 6. Reproducibility

```markdown
## Reproduce

git checkout <commit>
pip install -e .
prospectus-analyze data/labeled_pdfs -o artifacts/reports/eval_run.csv
# Compare to data/labels/ using docs/evaluation_and_baseline_reporting.md
```

---

## Turning baseline numbers into a future ML goal

Once baseline is measured on `test`:

| Baseline (heuristic) | Target (learned v1) | How you might get there |
|--------------------|---------------------|-------------------------|
| Macro F1 0.78 | F1 ≥ 0.85 | Line-level heading classifier using layout features |
| Count MAE 2.4 | MAE ≤ 1.0 | Better heading vs body discrimination |
| Section IoU 0.94 | IoU ≥ 0.98 | Section boundary classifier or CRF on lines |

Train only on `train`, tune on `val`, report once on `test`. The heuristic baseline number should **not** change when you train a model—it is the reference line on the same test set.

---

## Common mistakes when reporting

1. **Reporting count accuracy only** — hides merged/split errors.  
2. **Tuning rules on test** — optimistic bias; use `val` for rule changes.  
3. **Mixing PDF parsers** — gold labeled from viewer text but scored against `analyzer` output (different tokenization). Score against `prospectus-analyze` output only.  
4. **Including failed docs without marking them** — separate “section not found” from segmentation F1.  
5. **No error taxonomy** — recruiters want 2–3 concrete failure modes, not just one F1 number.

---

## Checklist: “I have a credible baseline report”

- [ ] ≥ 15 labeled PDFs with full title/body (not just counts)  
- [ ] Held-out `test` split defined and untouched during rule tuning  
- [ ] Predictions generated via `prospectus-analyze` on all labeled PDFs  
- [ ] Reported: section metrics + macro segmentation F1 + count MAE  
- [ ] Breakdown by `extraction_method` from summary CSV  
- [ ] 3–5 error examples with doc names and short explanation  
- [ ] Repro commands and commit hash documented  

---

## Related docs

- [annotation_guidelines.md](annotation_guidelines.md) — how to create gold labels  
- [README.md](README.md) — doc index  

When you are ready to automate scoring, you can implement `eval/metrics.py` and `eval/run_eval.py` following the definitions in this file—the formulas above are the specification.
