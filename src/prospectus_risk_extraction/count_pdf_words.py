#!/usr/bin/env python3
import argparse
from pathlib import Path

import pdfplumber
from openpyxl import Workbook

from .words import count_words


def count_words_in_pdf(pdf_path):
    total = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            total += count_words(text)
    return total


def write_counts_to_excel(rows, output_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Word Counts"
    sheet.append(["File", "Word Count"])

    for pdf_path, count in rows:
        sheet.append([Path(pdf_path).name, count])

    workbook.save(output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o",
        "--output",
        default="word_counts.xlsx",
        help="Path to the output Excel file",
    )
    parser.add_argument("pdf_paths", nargs="+")
    args = parser.parse_args()

    rows = []
    for path in args.pdf_paths:
        count = count_words_in_pdf(path)
        rows.append((path, count))
        print(f"{path}\t{count}")

    output_path = Path(args.output)
    write_counts_to_excel(rows, output_path)
    print(f"Wrote Excel file to {output_path.resolve()}")


if __name__ == "__main__":
    main()
