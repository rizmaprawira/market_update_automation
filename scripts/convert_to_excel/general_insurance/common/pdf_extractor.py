"""Shared PDF text extraction for text-layer (non-scanned) general insurance PDFs."""
from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


def _parse_words(pdf_path: Path) -> list[dict]:
    xml = subprocess.check_output(
        ["pdftotext", "-bbox-layout", str(pdf_path), "-"], text=True
    )
    root = ET.fromstring(xml)
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    lines = []
    for line in root.findall(".//x:line", ns):
        words = []
        for w in line.findall("x:word", ns):
            text = (w.text or "").strip()
            if text:
                words.append({"x": float(w.attrib["xMin"]), "text": text})
        if words:
            words.sort(key=lambda ww: ww["x"])
            lines.append({"y": float(line.attrib["yMin"]), "words": words})
    lines.sort(key=lambda ll: (ll["y"], ll["words"][0]["x"]))
    return lines


def _clean(text: str) -> str:
    return " ".join(text.split())


def _assign_col(x: float, x_thresholds: tuple, body_cols: tuple) -> str:
    for thresh, col in zip(x_thresholds, body_cols[:-1]):
        if x < thresh:
            return col
    return body_cols[-1]


def _row_flags(texts: list[str], bold_tokens: tuple, center_tokens: tuple) -> dict:
    joined = " | ".join(texts).upper()
    return {
        "bold": any(t in joined for t in bold_tokens)
                or joined.lstrip().startswith(("I.", "II.", "III.", "IV.")),
        "center": any(t in joined for t in center_tokens),
    }


def extract_pdf_rows(pdf_path: Path, config: dict) -> list[dict]:
    """Extract and cluster rows from a text-layer PDF using pdftotext -bbox-layout.

    Returns a list of row dicts. Each dict maps column letter → text,
    plus ``_flags`` (bold/center) and ``_gap`` (row height hint in PDF units).
    """
    lines = _parse_words(pdf_path)

    content_start_y = config["content_start_y"]
    row_cluster_tol = config["row_cluster_tol"]
    x_thresholds = tuple(config["x_thresholds"])
    body_cols = tuple(config["body_cols"])
    bold_tokens = tuple(config.get("bold_tokens", []))
    center_tokens = tuple(config.get("center_tokens", []))

    content = [ln for ln in lines if ln["y"] >= content_start_y]
    clusters: list[dict] = []
    for ln in content:
        if not clusters or abs(ln["y"] - clusters[-1]["min_y"]) > row_cluster_tol:
            clusters.append({"lines": [ln], "min_y": ln["y"], "max_y": ln["y"]})
        else:
            clusters[-1]["lines"].append(ln)
            clusters[-1]["min_y"] = min(clusters[-1]["min_y"], ln["y"])
            clusters[-1]["max_y"] = max(clusters[-1]["max_y"], ln["y"])

    rows = []
    for idx, grp in enumerate(clusters):
        gap = (clusters[idx + 1]["min_y"] - grp["min_y"]) if idx < len(clusters) - 1 else 8.0

        parts: dict[str, list[str]] = defaultdict(list)
        for ln in grp["lines"]:
            for w in ln["words"]:
                col = _assign_col(w["x"], x_thresholds, body_cols)
                parts[col].append(w["text"])

        row = {col: _clean(" ".join(words)) for col, words in parts.items() if words}
        row["_flags"] = _row_flags(list(row.values()), bold_tokens, center_tokens)
        row["_gap"] = gap
        rows.append(row)

    return rows
