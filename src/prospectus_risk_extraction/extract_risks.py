#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter

import pdfplumber

# Section boundary detection.
START_RE = re.compile(r"^\s*RISK\s+FACTORS\s*$", re.I)
END_RE = re.compile(
    r"^\s*(USE\s+OF\s+PROCEEDS|MANAGEMENT|BUSINESS|DESCRIPTION\s+OF\s+SECURITIES|FORWARD-LOOKING\s+STATEMENTS?|NOTE\s+REGARDING\s+FORWARD-LOOKING\s+STATEMENTS)\s*$",
    re.I,
)

# Basic word tokenizer for risk body word counts.
WORD_RE = re.compile(r"\b[0-9A-Za-z']+\b")


def is_page_number(text):
    """Return True for lines that are just a page number."""
    return text.strip().isdigit()


def group_lines(words, y_tol=1.5):
    """
    Group PDF words into lines based on their vertical position and enrich
    each line with text, font usage, and average font size.
    """
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
        line["x0"] = min((w["x0"] for w in line["words"]), default=0)
    return lines


def line_style(line):
    """Classify line styling as bold, bold-italic, or italic based on font names."""
    fonts = line["fonts"]
    total = sum(fonts.values()) or 1
    bold_italic = sum(v for k, v in fonts.items() if "BoldItalic" in k) / total
    bold = sum(v for k, v in fonts.items() if "Bold" in k and "Italic" not in k) / total
    italic = sum(v for k, v in fonts.items() if "Italic" in k and "Bold" not in k) / total
    return {
        "bold_italic": bold_italic >= 0.6,
        "bold": bold >= 0.6,
        "italic": italic >= 0.6,
    }


def extract_risk_section_lines(pdf_path):
    """
    Extract all lines in the Risk Factors section by scanning pages
    between the 'RISK FACTORS' heading and the next major section.
    """
    with pdfplumber.open(pdf_path) as pdf:
        candidates = []
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not any(START_RE.match(l.strip()) for l in text.splitlines()):
                continue

            lines = [l.strip() for l in text.splitlines() if l.strip()]
            toc_like = 0
            for l in lines:
                words = l.split()
                if (
                    l.isupper()
                    and 2 <= len(words) <= 8
                    and re.search(r"[A-Z]", l)
                    and not l.isdigit()
                ):
                    toc_like += 1

            score = 0
            if re.search(r"TABLE\\s+OF\\s+CONTENTS", text, re.I):
                score -= 2
            if toc_like >= 5:
                score -= 2
            if re.search(r"Risks\\s+Related\\s+to", text, re.I):
                score += 1
            if re.search(r"(Investing in our common stock|An investment in our)", text, re.I):
                score += 2

            candidates.append((score, i))

        if not candidates:
            return []

        max_score = max(score for score, _ in candidates)
        start_page = min(i for score, i in candidates if score == max_score)
        section_lines = []
        for page_index, page in enumerate(pdf.pages[start_page:], start=start_page):
            words = page.extract_words(extra_attrs=["fontname", "size"])
            started = page_index != start_page
            for line in group_lines(words):
                txt = line["text"]
                if not txt or is_page_number(txt):
                    continue
                if not started:
                    if START_RE.match(txt):
                        started = True
                    continue
                if re.sub(r"\\s+", " ", txt.strip()).lower() == "table of contents":
                    continue
                if START_RE.match(txt):
                    continue
                if END_RE.match(txt):
                    return section_lines
                section_lines.append(line)
    return section_lines


def looks_like_title(text, line_size, body_size, line_x0, body_x0, is_italic):
    """
    Heuristic title detection for PDFs that don't use bold-italic headings.
    Uses capitalization, length, and relative font size.
    """
    if not text or is_page_number(text):
        return False
    if text.lower().startswith("table of contents"):
        return False
    if re.match(r"^\s*Risks\s+Related\s+to\b", text, re.I):
        return False
    if text.endswith(":"):
        return False
    if is_italic:
        return False
    if text.lstrip().startswith(("•", "", "-", "–", "—")):
        return False
    if text[0].islower():
        return False
    words = text.split()
    if len(words) < 4 or len(words) > 40:
        return False
    if text.isupper() and len(words) <= 15:
        return True
    if (
        line_size > 0
        and body_size > 0
        and line_size >= body_size + 0.2
        and line_x0 <= body_x0 + 2
    ):
        return True
    return False


def looks_like_italic_title(text):
    """Looser heuristic for italic-only titles after a category header."""
    if not text or is_page_number(text):
        return False
    if text.endswith(":"):
        return False
    if text.lstrip().startswith(("•", "", "-", "–", "—")):
        return False
    if text[0].islower():
        return False
    words = text.split()
    if len(words) < 6 or len(words) > 40:
        return False
    return True


def looks_like_plain_title(text, next_text):
    """Fallback heuristic for plain-text titles with no font styling."""
    if not text or is_page_number(text):
        return False
    if text.endswith(":"):
        return False
    if text.lstrip().startswith(("•", "", "-", "–", "—")):
        return False
    if text[0].islower():
        return False
    words = text.split()
    if len(words) < 4 or len(words) > 30:
        return False
    if len(text) < 20 or len(text) > 200:
        return False
    return True


def looks_like_plain_title_start(text):
    """Detect the first line of a wrapped plain-text title."""
    if not text or is_page_number(text):
        return False
    if text.endswith(":") or text.endswith("."):
        return False
    if text.lstrip().startswith(("•", "", "-", "–", "—")):
        return False
    if text[0].islower():
        return False
    words = text.split()
    if len(words) < 4 or len(words) > 16:
        return False
    if len(text) < 25 or len(text) > 90:
        return False
    return True


def split_risks(section_lines):
    """
    Split the Risk Factors section into individual risks.
    Priority order:
    1) bold-italic headings (most reliable for this sample),
    2) bold headings,
    3) heuristic title lines (fallback for other prospectuses).
    """
    body_sizes = [l.get("size", 0) for l in section_lines if l.get("size", 0) > 0]
    body_xs = [l.get("x0", 0) for l in section_lines if l.get("x0", 0) > 0]
    body_size = sorted(body_sizes)[len(body_sizes) // 2] if body_sizes else 0
    body_x0 = sorted(body_xs)[len(body_xs) // 2] if body_xs else 0
    has_bold_italic = any(line_style(l)["bold_italic"] for l in section_lines)

    risks = []
    current = None
    seen_category = False

    for idx, line in enumerate(section_lines):
        txt = line["text"]
        style = line_style(line)

        if re.match(r"^\s*Risks\s+Relat(ed|ing)\s+to\b", txt, re.I):
            if current and current["body"]:
                risks.append(current)
            current = None
            seen_category = True
            continue

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
            if style["bold"]:
                if current and not current["body"]:
                    current["title"] = f"{current['title']} {txt}"
                else:
                    if current:
                        risks.append(current)
                    current = {"title": txt, "body": []}
                continue
            if style["italic"] and seen_category and looks_like_italic_title(txt):
                if current and not current["body"]:
                    current["title"] = f"{current['title']} {txt}"
                else:
                    if current:
                        risks.append(current)
                    current = {"title": txt, "body": []}
                continue
            if looks_like_title(
                txt, line.get("size", 0), body_size, line.get("x0", 0), body_x0, style["italic"]
            ):
                if current:
                    risks.append(current)
                current = {"title": txt, "body": []}
                continue

        if current:
            current["body"].append(txt)

    if current:
        risks.append(current)

    if risks:
        return risks

    # Plain-text fallback: detect short title sentences followed by longer bodies.
    risks = []
    current = None
    seen_category = False
    title_buf = None
    x0s = [l.get("x0", 0) for l in section_lines if l.get("x0", 0) > 0]
    base_x0 = sorted(x0s)[max(0, len(x0s) // 10)] if x0s else 0
    x0_tol = 3
    for i, line in enumerate(section_lines):
        txt = line["text"].strip()
        left_aligned = line.get("x0", 0) <= base_x0 + x0_tol if base_x0 else True
        if re.match(r"^\s*Risks\s+Relat(ed|ing)\s+to\b", txt, re.I):
            if current and current["body"]:
                risks.append(current)
            current = None
            seen_category = True
            title_buf = None
            continue
        if not seen_category:
            continue
        next_txt = section_lines[i + 1]["text"].strip() if i + 1 < len(section_lines) else ""
        next_left = (
            section_lines[i + 1].get("x0", 0) <= base_x0 + x0_tol if i + 1 < len(section_lines) else False
        )
        if title_buf:
            combined = f"{title_buf} {txt}".strip()
            if (
                combined.endswith(".")
                and len(combined) <= 200
                and len(combined.split()) <= 30
                and left_aligned
                and looks_like_plain_title(combined, next_txt)
            ):
                if current:
                    risks.append(current)
                current = {"title": combined, "body": []}
                title_buf = None
                continue
            if combined.endswith("."):
                if current:
                    current["body"].append(combined)
                title_buf = None
            # If we're in the middle of a title, keep buffering if it's still short.
            if (
                not combined.endswith(".")
                and left_aligned
                and len(combined) <= 220
                and len(combined.split()) <= 32
            ):
                title_buf = combined
            else:
                if current and title_buf:
                    current["body"].append(title_buf)
                title_buf = None
            continue
        if left_aligned and txt.endswith(".") and looks_like_plain_title(txt, next_txt):
            if current:
                risks.append(current)
            current = {"title": txt, "body": []}
            continue
        if left_aligned and looks_like_plain_title_start(txt) and next_left:
            title_buf = txt
            continue
        if current:
            current["body"].append(txt)
    if current:
        risks.append(current)
    return risks


def count_words(text):
    """Count word-like tokens in a string."""
    return len(WORD_RE.findall(text))


def analyze(pdf_path):
    """End-to-end extraction and counting for a single PDF."""
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
    """CLI entrypoint."""
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
