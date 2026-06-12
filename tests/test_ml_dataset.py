"""Tests for the ML line-classification feature/label extraction.

These don't need scikit-learn or a trained model - they check that features and
weak labels are produced consistently for the real sample prospectus. Skipped
automatically if pandas or the sample PDF are unavailable.
"""
from pathlib import Path

import pytest

pytest.importorskip("pandas")

from prospectus_risk_extraction.ml.dataset import build_dataframe
from prospectus_risk_extraction.ml.labeling import LABELS, NUMERIC_FEATURES, TEXT_FEATURE

SAMPLE_PDF = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "sample_pdfs"
    / "1A. Aegerion Pharmaceuticals.pdf"
)


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="sample prospectus not present")
def test_dataframe_schema_and_labels():
    df = build_dataframe([str(SAMPLE_PDF)])
    assert not df.empty
    # Every feature column the model expects must be present.
    for col in NUMERIC_FEATURES + [TEXT_FEATURE, "label", "doc_id"]:
        assert col in df.columns
    # Labels are always drawn from the known label set.
    assert set(df["label"]).issubset(set(LABELS))
    # The section should contain headings and body, not be one homogeneous blob.
    assert df["label"].nunique() >= 2
    assert (df["label"] == "heading").sum() > 0
