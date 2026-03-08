#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter

import pdfplumber

START_RE = re.compile(r"^\s*RISK\s+FACTORS\s*$", re.I)
END_RE = re.compile(
    r"^\s*(USE\s+OF\s+PROCEEDS|MANAGEMENT|BUSINESS|DESCRIPTION\s+OF\s+SECURITIES)\s*$",
    re.I,
)
WORD_RE = re.compile(r"\b[0-9A-Za-z']+\b")


def is_page_number(text):
    return text.strip().isdigit()


def group_lines(words, y_tol=1.5):
    lines = []
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        if not lines or abs(lines[-1]["top"] - w["top"]) > y_tol:
            lines.append({"top": w["top"], "words": [w]})
        else:
            lines[-1]["words"].append(w)
    for line in lines:
        line["words"].sort(key=lambda x: x["x0"])
        line["text"] = " ".join(w["text"] for w in line["words"]).strip()
        line["fonts"] = Counter(w["fontname"] for w in line["words"])
        sizes = [w.get("size", 0) for w in line["words"]]
        line["size"] = sum(sizes) / len(sizes) if sizes else 0
    return lines


def line_style(line):
    fonts = line["fonts"]
    total = sum(fonts.values()) or 1
    bold_italic = sum(v for k, v in fonts.items() if "BoldItalic" in k) / total
    bold = sum(v for k, v in fonts.items() if "Bold" in k and "Italic" not in k) / total
    return {
        "bold_italic": bold_italic >= 0.6,
        "bold": bold >= 0.6,
    }


def extract_risk_section_lines(pdf_path):
    in_section = False
    section_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not in_section:
                for line in text.splitlines():
                    if START_RE.match(line.strip()):
                        in_section = True
                        break
                if not in_section:
                    continue
            words = page.extract_words(extra_attrs=["fontname", "size"])
            for line in group_lines(words):
                txt = line["text"]
                if not txt or is_page_number(txt):
                    continue
                if START_RE.match(txt):
                    continue
                if END_RE.match(txt):
                    return section_lines
                section_lines.append(line)
    return section_lines


def looks_like_title(text, line_size, body_size):
    if not text or is_page_number(text):
        return False
    if text.lower().startswith("table of contents"):
        return False
    if re.match(r"^\s*Risks\s+Related\s+to\b", text, re.I):
        return False
    if text.endswith(":"):
        return False
    if text[0].islower():
        return False
    words = text.split()
    if len(words) < 6 or len(words) > 40:
        return False
    if text.isupper() and len(words) <= 15:
        return True
    # Slight preference for larger font sizes if present
    if line_size > 0 and body_size > 0 and line_size >= body_size + 0.2:
        return True
    # Title-case-ish line (not all caps) as a last resort
    return any(w[0].isupper() for w in words) and any(c.islower() for c in text)


def split_risks(section_lines):
    body_sizes = [l.get("size", 0) for l in section_lines if l.get("size", 0) > 0]
    body_size = sorted(body_sizes)[len(body_sizes) // 2] if body_sizes else 0
    has_bold_italic = any(line_style(l)["bold_italic"] for l in section_lines)

    risks = []
    current = None

    for line in section_lines:
        txt = line["text"]
        style = line_style(line)

        if style["bold_italic"]:
            if current and not current["body"]:
                current["title"] = f"{current['title']} {txt}"
            else:
                if current:
                    risks.append(current)
                current = {"title": txt, "body": []}
            continue

        if style["bold"] and has_bold_italic:
            if current:
                risks.append(current)
                current = None
            continue

        if not has_bold_italic:
            if style["bold"] or looks_like_title(txt, line.get("size", 0), body_size):
                if current:
                    risks.append(current)
                current = {"title": txt, "body": []}
                continue

        if current:
            current["body"].append(txt)

    if current:
        risks.append(current)
    return risks


def count_words(text):
    return len(WORD_RE.findall(text))


def analyze(pdf_path):
    section_lines = extract_risk_section_lines(pdf_path)
    risks = split_risks(section_lines)
    result = []
    for r in risks:
        body = " ".join(r["body"]).strip()
        result.append(
            {
                "title": r["title"],
                "word_count": count_words(body),
            }
        )
    return {
        "risk_count": len(result),
        "risks": result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = analyze(args.pdf_path)
    if args.json:
        print(json.dumps(data, indent=2))
        return

    print(f"Risk count: {data['risk_count']}")
    for i, r in enumerate(data["risks"], 1):
        print(f"{i}. {r['title']}")
        print(f"   words: {r['word_count']}")


if __name__ == "__main__":
    main()
