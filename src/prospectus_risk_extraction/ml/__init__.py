"""Machine-learning components for the prospectus risk-factor pipeline.

This subpackage turns the hand-tuned heuristic in :mod:`prospectus_risk_extraction.analyzer`
into a *learnable* task. The unit of learning is a **single line** inside the Risk
Factors section, classified as ``heading`` / ``body`` / ``subheading`` / ``skip``.

The current labels are *distilled* from the heuristic (see :mod:`.labeling`), so a
model trained on them learns to reproduce the rule system. That is a deliberate
first step: it gives you the full ML workflow (features -> train -> cross-validate
-> confusion matrix -> plug back into segmentation) on data you already have. The
moment you hand-label real gold lines, you swap the label source and the rest of
the pipeline is unchanged.
"""
