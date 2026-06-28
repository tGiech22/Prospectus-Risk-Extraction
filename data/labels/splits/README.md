# Data splits

Document-level splits for evaluation. **Each entry is a whole PDF (`doc_id`)** —
never split the lines of one document across files. This keeps both the
per-document metrics (section IoU, segmentation F1) and the per-line classifier
honest (no line from a training doc leaks into its own test fold).

The IDs match the `doc_id` field inside `data/labels/*.json`. Note these use the
underscore form (`1A__Aegerion_Pharmaceuticals.pdf`); the actual PDF on disk is
`data/sample_pdfs/1A. Aegerion Pharmaceuticals.pdf`, so any code that maps an ID
to a PDF must normalize (`. ` / spaces -> `_`).

| split | n | purpose |
|-------|---|---------|
| `train.txt` | 9 | line-classifier training only |
| `val.txt`   | 3 | tune heuristic rules + classifier thresholds |
| `test.txt`  | 3 | the final number — touch ONCE, after rules are frozen |

## Caveats at this size

- A 3-doc test is statistically thin; report it as `n=3` and treat it as a range.
- For the **line classifier**, prefer document-grouped k-fold CV over all 15 docs
  (see `src/prospectus_risk_extraction/ml/train.py`, which already does GroupKFold)
  rather than relying on this single small test split.
- Aim for ~20–25 labeled docs to support a solid fixed held-out test *and* CV.
