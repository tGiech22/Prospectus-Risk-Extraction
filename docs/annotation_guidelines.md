# Annotation guidelines: labeling prospectus PDFs

This guide explains how to create **gold-standard labels** for your evaluation set. Labels are what you compare the heuristic pipeline (`prospectus-analyze`) against when you report a baseline.

You are not training a model in this step—you are defining **what correct output looks like** for each PDF.

---

## What you are labeling

The pipeline solves two problems. Label both when you can; at minimum label **risk segmentation**.

### Task A — Risk Factors section boundaries

Where the formal **Risk Factors** section begins and ends in the document.

- **Start:** the line immediately after the `RISK FACTORS` heading (not the heading itself).
- **End:** the line before the next major section (e.g. *Use of Proceeds*, *Management’s Discussion*, *Forward-Looking Statements*).

Your analyzer already does this in `find_risk_section()` and prints it when `DEBUG` is on, e.g. `Risk Factors: ~12,400 words (lines 842-2103)`.

### Task B — Individual risk factors (required)

An ordered list of risks inside that section. Each risk has:

| Field | Meaning |
|-------|---------|
| **title** | The heading or first sentence that names the risk |
| **body** | All explanatory paragraphs until the next risk starts |

**One risk = one distinct disclosure item** an investor would count separately in the prospectus—not every bold line, and not section intros like “Risks Related to Our Business” unless you deliberately choose to treat those as risks (this project does **not**; see rules below).

---

## What “correct” means for this project

Use these rules so labels stay consistent across annotators and PDF layouts.

### Include as a risk factor

- A standalone risk with its own title/heading and following paragraphs.
- Multi-line titles (merge into one `title` string).
- Risks introduced by a sentence-style title (e.g. *We may not be able to…*) when the prospectus clearly treats it as its own item.

### Do **not** label as separate risks

- **Section intro / boilerplate** before the first real risk, e.g. “Investing in our common stock involves a high degree of risk…”, “You should carefully consider…”
- **Category subheadings only**, e.g. *Risks Related to Our Business*, *General Risks*, unless the filing uses that heading as the **only** title for a single long block you still want to count as one risk (rare; note in `metadata.notes`).
- **Table of contents** lines, page numbers, headers/footers.
- **Bullet sub-points** that belong under the same risk title (keep them in `body`).
- **Duplicate** headings caused by PDF extraction glitches (one logical risk).

### Title vs body

- **Title:** shortest text that uniquely identifies the risk at its start (often bold, bold-italic, ALL CAPS, or the first sentence).
- **Body:** everything after the title until the next risk’s title begins.
- If the “title” is really the first sentence of a paragraph and the rest continues in normal body font, still put that first sentence in `title` and the remainder in `body`—match how the SEC filing reads to a human.

### When two annotators might disagree

Write a decision in `metadata.notes` and prefer:

1. **Investor-facing granularity** — how many distinct risks would appear in a table of contents for the Risk Factors section?
2. **Visual structure** — new bold/italic heading or clear new paragraph with a new topic → new risk.
3. **When unsure** — merge rather than split (under-splitting is easier to catch in review than 2× over-splitting).

---

## Recommended label format

Store one JSON file per PDF under `data/labels/` (create the folder when you start). Example:

```json
{
  "doc_id": "1A. Aegerion Pharmaceuticals.pdf",
  "section": {
    "start_line": 842,
    "end_line": 2103,
    "start_heading_text": "RISK FACTORS",
    "end_heading_text": "USE OF PROCEEDS"
  },
  "risk_factors": [
    {
      "id": 1,
      "title": "We have incurred significant losses since inception...",
      "body": "We have incurred significant losses... [full body text]",
      "body_word_count": 412
    }
  ],
  "metadata": {
    "annotator": "your_name",
    "date": "2026-05-27",
    "layout_type": "bold_italic_headings",
    "time_minutes": 45,
    "notes": ""
  }
}
```

### Line indices vs full text

| Approach | Pros | Cons |
|----------|------|------|
| **Full `title` + `body` text** | Easy in a spreadsheet; no tooling; good for title/body F1 later | Harder to compute span IoU without alignment |
| **`start_line` / `end_line` per risk** | Matches `analyzer.py` internals; precise boundary metrics | You need a line listing export (see below) |

**Practical recommendation:** label **full text** first for 10–20 PDFs. Add line numbers for section boundaries and optionally per risk once you are comfortable.

---

## Step-by-step labeling workflow

### 1. Choose documents deliberately

Do not label 100 random PDFs first. Build a **stratified** set:

| Bucket | Why | Target count (first pass) |
|--------|-----|---------------------------|
| Heuristic works well | `extraction_method` = `font-standalone-merged`, few warnings | 8–10 |
| Indent / text fallback | `indent-paragraph` or `text-paragraph` | 8–10 |
| Heuristic warnings | low/high risk count, odd median words | 5 |
| Known hard cases | TOC-heavy, plain text, very short section | 5 |

Keep a manifest file `data/labels/manifest.csv`:

```csv
doc_id,split,layout_notes,priority
1A. Aegerion Pharmaceuticals.pdf,train,bold_italic,1
```

Use splits `train` / `val` / `test` now—even before ML—so you never tune rules on the same PDFs you report as “final” baseline.

### 2. Run the heuristic to get a draft

```bash
. .venv/bin/activate
pip install -e .
prospectus-analyze path/to/your/pdfs -o artifacts/reports/baseline_run.csv
```

Open:

- `artifacts/reports/baseline_run_detailed.csv` — predicted titles and word counts per risk
- `artifacts/json/baseline_run_full.json` — full structured output per file

Treat these as **pre-labels**: copy, correct, don’t annotate from a blank PDF unless the run failed completely.

### 3. Open the PDF side by side

Use any PDF viewer. Scroll only the **Risk Factors** section.

For each predicted risk in the CSV:

1. Find the same text in the PDF.
2. If boundaries match → keep.
3. If merged/split wrong → fix in your gold JSON (add/remove risks, adjust title/body).
4. If the section start/end is wrong → fix `section` in gold (compare to next major heading in PDF).

### 4. Record gold labels

**Option A — Spreadsheet (fastest to start)**

Columns:

```text
doc_id | rf_id | title | body | notes
```

One row per risk. Export to JSON later or keep CSV as gold for v1.

**Option B — JSON files (better long-term)**

One file per `doc_id` in `data/labels/` as in the schema above.

### 5. Optional: line numbers aligned with the analyzer

The analyzer builds a `Line` list in order through the PDF. When `DEBUG = True` in `analyzer.py`, a run prints section line range and sample titles.

To label with line indices without changing the package yet, you can run a **one-off** snippet in a Python REPL after installing the package:

```python
from pathlib import Path
from prospectus_risk_extraction.analyzer import extract_spans, build_lines, find_risk_section

pdf = Path("data/sample_pdfs/1A. Aegerion Pharmaceuticals.pdf")
_, spans = extract_spans(str(pdf))
lines = build_lines(spans)
for i, ln in enumerate(lines[840:860]):
    print(f"{840+i}\t{ln.text[:120]}")
```

Use printed indices in your gold JSON `section.start_line` / `end_line` and optionally per-risk `title_line` / `body_end_line`.

### 6. Quality checks before you “freeze” a label file

- [ ] Risk count is plausible (often roughly 15–80 for biotech prospectuses; extremes need a `notes` explanation).
- [ ] No empty bodies (except intentional edge cases you document).
- [ ] First item is not pure intro boilerplate.
- [ ] Titles are not duplicated back-to-back with nearly identical bodies.
- [ ] Sum of body word counts is roughly consistent with section size (order-of-magnitude).

### 7. (Later) Double annotation

Have someone else label 5 PDFs independently. Compare risk **counts** and title lists. If agreement is low, tighten these guidelines before labeling more.

---

## Using your existing test fixtures

`test_fixtures/expected_counts.txt` only stores **risk counts** per small PDF:

```text
simple1.pdf	14
```

That is useful for smoke tests, not for segmentation quality. For fixtures:

1. Open `test_fixtures/simple1.pdf` in a viewer.
2. Manually list 14 risk titles (or confirm the heuristic’s 14 titles are all correct).
3. Save full gold in `data/labels/simple1.pdf.json`.

Promote a fixture to “gold” only when you have titles, not just a count.

---

## Time and scale expectations

| Experience | Time per PDF (full segmentation) |
|------------|----------------------------------|
| First 3 docs | 60–90 min (learning the section) |
| After 10 docs | 20–40 min |
| Simple / short fixtures | 5–15 min |

A credible first benchmark: **15–25 fully labeled PDFs** plus your 4–5 fixtures. That is enough to report a baseline and show error patterns in a README or interview.

---

## What not to do yet

- Do not label only risk **counts** (you already have that weak signal).
- Do not tune heuristic rules on the same PDFs you will call `test` in your final table.
- Do not mix `extract_risks.py` and `analyzer.py` outputs in one gold set—pick **`analyzer.py`** (`prospectus-analyze`) as the official baseline system.

Next: [evaluation_and_baseline_reporting.md](evaluation_and_baseline_reporting.md) — how to score labels against heuristic output and write up results.
