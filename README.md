# Prospectus-Risk-Extraction

`extract_risks.py` reads a prospectus PDF, isolates the Risk Factors section, splits it into individual risk items, and reports the total risk count plus the word count of each risk’s description.

How it works (high level):
1. Detects the `RISK FACTORS` section by scanning for the heading and the next major section header.
2. Reconstructs page text into lines and inspects font styling and size.
3. Splits risks by bold‑italic headings when present, or falls back to bold/heuristic title detection for other prospectuses.
4. Counts word tokens in each risk’s body text.

Usage:
```bash
. .venv/bin/activate
python extract_risks.py "1A. Aegerion Pharmaceuticals.pdf"
```
