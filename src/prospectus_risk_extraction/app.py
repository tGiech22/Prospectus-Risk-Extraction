"""Streamlit UI for the Prospectus Risk Extraction model.

Upload a prospectus PDF, click a button, and the trained line classifier runs
and displays the reconstructed risk factors — the same output as
``prospectus-ml-predict``, but in the browser.

Run it with::

    prospectus-ui            # console script (see pyproject.toml)
    # or
    streamlit run src/prospectus_risk_extraction/app.py

Install the UI extra first::

    pip install -e ".[ml,ui]"
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

from prospectus_risk_extraction.ml.predict import DEFAULT_MODEL, predict_risks


@st.cache_resource
def load_model(model_path: str):
    """Load (and cache) the trained classifier so it isn't reloaded per click."""
    return joblib.load(model_path)


def main() -> None:
    st.set_page_config(page_title="Prospectus Risk Extraction", layout="wide")
    st.title("📄 Prospectus Risk Extraction")
    st.caption(
        "Upload a biotech IPO prospectus PDF and extract each risk factor as "
        "structured `(title, body, word_count)`."
    )

    model_path = st.sidebar.text_input("Model path", value=DEFAULT_MODEL)
    if not Path(model_path).exists():
        st.error(
            f"No model found at `{model_path}`. Train one first:\n\n"
            "`prospectus-ml-train data/sample_pdfs --labels gold`"
        )
        return

    uploaded = st.file_uploader("Choose a prospectus PDF", type="pdf")
    run = st.button("Extract risks", type="primary", disabled=uploaded is None)

    if not run or uploaded is None:
        return

    # predict_risks reads from a path, so persist the upload to a temp file.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    with st.spinner("Running the model…"):
        model = load_model(model_path)
        risks = predict_risks(tmp_path, model, doc_id=uploaded.name)
    Path(tmp_path).unlink(missing_ok=True)

    if not risks:
        st.warning("No risk factors were found in this PDF.")
        return

    rows = [asdict(r) for r in risks]
    st.success(f"Found **{len(risks)}** risk factor(s) in `{uploaded.name}`.")

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    col1.download_button(
        "Download CSV",
        df.to_csv(index=False).encode(),
        file_name=f"{Path(uploaded.name).stem}_risks.csv",
        mime="text/csv",
    )
    col2.download_button(
        "Download JSON",
        json.dumps(rows, indent=2).encode(),
        file_name=f"{Path(uploaded.name).stem}_risks.json",
        mime="application/json",
    )

    for i, r in enumerate(risks, 1):
        with st.expander(f"{i}. {r.title}  ·  {r.word_count} words"):
            st.write(r.body)


def run() -> None:
    """Console-script entry point: launch this file under ``streamlit run``."""
    import sys

    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", __file__, *sys.argv[1:]]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
