#!/usr/bin/env python3
import argparse
import re

import pdfplumber

# Include ASCII apostrophe and common Unicode apostrophes.
WORD_RE = re.compile(r"\b[0-9A-Za-z'’‛`]+\b")


def count_words_in_pdf(pdf_path):
    total = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            total += len(WORD_RE.findall(text))
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_paths", nargs="+")
    args = parser.parse_args()

    for path in args.pdf_paths:
        count = count_words_in_pdf(path)
        print(f"{path}\t{count}")


if __name__ == "__main__":
    main()
