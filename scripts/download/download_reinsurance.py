from __future__ import annotations

"""
Download conventional financial report PDFs for Indonesian reinsurance companies.

Usage examples:
  python scripts/download/download_reinsurance.py \
    --year 2026 --month 3 \
    --input link_reasuransi.xlsx \
    --output-root data \
    --dry-run

  python scripts/download/download_reinsurance.py \
    --year 2026 --month 3 \
    --input assets/link_reasuransi.xlsx \
    --output-root data \
    --max-workers 4 \
    --use-browser

The dry-run mode discovers candidates and writes the manifest, but skips file writes.
"""

import argparse
import csv
import json
import logging
import re
import sys
import unicodedata
from collections import deque
from contextlib import suppress
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional dependency.
    def tqdm(iterable=None, *args, **kwargs):  # type: ignore[override]
        return iterable if iterable is not None else []

try:  # Optional browser fallback for JavaScript-rendered pages.
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency.
    PlaywrightError = Exception  # type: ignore[assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


LOGGER = logging.getLogger("download_reinsurance")
CATEGORY = "reasuransi"
OUTPUT_SUBDIR = "raw_pdf"
MANIFEST_FIELDS = [
    "category",
    "company_name",
    "source_page_url",
    "discovered_page_url",
    "pdf_url",
    "target_year",
    "target_month",
    "output_path",
    "status",
    "reason",
    "discovery_method",
    "score",
    "rejected_syariah_count",
    "rejected_unrelated_count",
    "candidate_count",
    "http_status",
    "file_size_bytes",
    "timestamp",
]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MANIFEST_TIMEZONE = ZoneInfo("Asia/Jakarta")
REQUEST_TIMEOUT_DEFAULT = 30

MONTH_TERMS: dict[int, list[str]] = {
    1: ["januari", "january", "jan"],
    2: ["februari", "february", "feb"],
    3: ["maret", "march", "mar"],
    4: ["april", "apr"],
    5: ["mei", "may"],
    6: ["juni", "june", "jun"],
    7: ["juli", "july", "jul"],
    8: ["agustus", "august", "aug"],
    9: ["september", "sep", "sept"],
    10: ["oktober", "october", "oct", "okt"],
    11: ["november", "nov"],
    12: ["desember", "december", "dec", "des"],
}
QUARTER_ROMAN = {1: "i", 2: "ii", 3: "iii", 4: "iv"}
REPORT_TERMS_STRONG = (
    "laporan keuangan konvensional",
    "laporan keuangan perusahaan",
    "laporan keuangan",
    "financial report",
    "financial statement",
    "laporan bulanan",
    "monthly report",
    "published report",
    "publikasi laporan keuangan",
)
REPORT_TERMS_WEAK = (
    "publikasi",
    "publication",
    "report",
    "laporan",
    "financial",
    "bulanan",
    "monthly",
    "statement",
)
DOCUMENT_URL_HINTS = (
    ".pdf",
    "download",
    "unduh",
    "file",
    "attachment",
    "document",
    "report",
    "laporan",
    "publikasi",
)
SYARIAH_TERMS = (
    "syariah",
    "sharia",
    "shariah",
    "unit syariah",
    "usaha syariah",
    "uus",
    "islamic",
)
UNRELATED_REPORT_TERMS = (
    "annual report",
    "laporan tahunan",
    "sustainability report",
    "sustainability",
    "integrated report",
    "good corporate governance",
    "corporate governance",
    "tata kelola",
    "gcg",
    "csr",
    "esg",
    "news",
    "press release",
    "brochure",
    "product brochure",
    "company profile",
    "profile company",
    "presentation",
    "slide",
    "ppt",
    "award",
    "awards",
)
FOLLOW_LINK_HINTS = (
    "laporan keuangan",
    "financial report",
    "financial statement",
    "laporan bulanan",
    "monthly report",
    "publikasi",
    "published report",
    "report",
    "investor",
    "keterbukaan informasi",
    "information disclosure",
    "public disclosure",
    "financial",
    "reasuransi",
    "reinsurance",
)
BAD_FILENAME_TOKENS = {"download", "file", "report", "document", "pdf", "index"}
MAX_LINKS_PER_PAGE = 40
COMPANY_SLUG_ALIASES = {
    "pt indoperkasa suksesjaya reasuransi": "indoperkasa",
    "pt maskapai reasuransi indonesia tbk": "marein",
    "pt orion reasuransi indonesia": "orionre",
    "pt reasuransi indonesia utama persero": "indonesia_re",
    "pt reasuransi maipark indonesia": "maipark",
    "pt reasuransi nasional indonesia": "nasre",
    "pt reasuransi nusantara makmur": "nusantarare",
    "pt tugu reasuransi indonesia": "tugure",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download conventional financial report PDFs for Indonesian reinsurance companies.",
    )
    parser.add_argument("--year", type=int, required=True, help="Target report year, e.g. 2026.")
    parser.add_argument("--month", type=int, required=True, help="Target report month, 1-12.")
    parser.add_argument(
        "--input",
        default="assets/link_reasuransi.xlsx",
        help="Input Excel workbook containing company names and report-page links.",
    )
    parser.add_argument(
        "--output-root",
        default="data",
        help="Root output directory that will contain data/{YYYY-MM}/raw_pdf/reasuransi/.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Discover candidates without writing PDFs.")
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Stop after discovery and write manifest rows with status=discover_only.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing PDF files.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=REQUEST_TIMEOUT_DEFAULT,
        help="HTTP timeout in seconds for page fetches and PDF downloads.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of concurrent companies to process.",
    )
    parser.add_argument(
        "--use-browser",
        action="store_true",
        help="Use Playwright fallback for JavaScript-rendered pages.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum crawl depth within the same domain from the source page.",
    )
    parser.add_argument(
        "--debug-html",
        action="store_true",
        help="Save fetched/rendered HTML snapshots for failed companies.",
    )
    args = parser.parse_args()

    if not 1 <= args.month <= 12:
        parser.error("--month must be between 1 and 12")
    if args.year < 1900:
        parser.error("--year must be a sensible calendar year")
    if args.max_workers < 1:
        parser.error("--max-workers must be at least 1")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1 second")
    if args.max_depth < 0:
        parser.error("--max-depth must be zero or greater")

    return args


def ascii_fold(value: str | Any) -> str:
    normalized = unicodedata.normalize("NFKD", str("" if value is None else value))
    return normalized.encode("ascii", "ignore").decode("ascii")


def collapse_spaces(value: str | Any) -> str:
    return re.sub(r"\s+", " ", str("" if value is None else value)).strip()


def normalize_text(value: str | Any) -> str:
    text = ascii_fold(clean_cell(value)).lower()
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    text = collapse_spaces(text)
    return text


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        pieces: list[str] = []
        for item in value:
            cleaned = clean_cell(item)
            if cleaned:
                pieces.append(cleaned)
        return collapse_spaces(" ".join(pieces))
    try:
        missing = pd.isna(value)
    except Exception:
        missing = False
    else:
        try:
            if bool(missing):
                return ""
        except Exception:
            try:
                if missing.all():
                    return ""
            except Exception:
                pass
    text = str(value)
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return collapse_spaces(text)


def normalize_month_terms(month: int) -> list[str]:
    if month not in MONTH_TERMS:
        raise ValueError("month must be between 1 and 12")
    return list(dict.fromkeys(MONTH_TERMS[month]))


def normalize_target_period(year: int, month: int) -> dict[str, Any]:
    quarter = quarter_for_month(month)
    quarter_roman = QUARTER_ROMAN[quarter]
    month_terms = normalize_month_terms(month)
    numeric_terms = [f"{month:02d}", str(month)]
    month_patterns = [
        f"{year:04d}-{month:02d}",
        f"{year:04d}_{month:02d}",
        f"{year:04d}{month:02d}",
        f"{month:02d}-{year:04d}",
        f"{month:02d}_{year:04d}",
        f"{year:04d} {month:02d}",
        f"{month:02d} {year:04d}",
    ]
    month_patterns.extend(f"{term} {year:04d}" for term in month_terms)
    month_patterns.extend(f"{year:04d} {term}" for term in month_terms)
    quarter_patterns = [
        f"triwulan {quarter_roman} {year:04d}",
        f"triwulan {quarter} {year:04d}",
        f"q{quarter} {year:04d}",
        f"quarter {quarter} {year:04d}",
        f"{year:04d} triwulan {quarter_roman}",
        f"{year:04d} q{quarter}",
        f"{year:04d} quarter {quarter}",
    ]
    return {
        "year": year,
        "month": month,
        "quarter": quarter,
        "month_terms": month_terms,
        "numeric_terms": numeric_terms,
        "month_patterns": list(dict.fromkeys(month_patterns)),
        "quarter_patterns": list(dict.fromkeys(quarter_patterns)),
        "all_variants": list(dict.fromkeys(month_patterns + quarter_patterns)),
    }


def sanitize_filename(text: str) -> str:
    alias_key = collapse_spaces(re.sub(r"[^a-z0-9]+", " ", ascii_fold(text).lower()))
    if alias_key in COMPANY_SLUG_ALIASES:
        return COMPANY_SLUG_ALIASES[alias_key]

    value = ascii_fold(text).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\bpt\b\.?", "", value)
    value = re.sub(r"\b(persero|tbk|perseroan terbatas)\b\.?", "", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "company"


def is_syariah_candidate(text: str) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False

    if "unit syariah" in blob or "usaha syariah" in blob:
        return True
    if re.search(r"\buus\b", blob):
        return True
    for term in ("syariah", "shariah", "sharia", "islamic"):
        if re.search(rf"\b{re.escape(term)}\b", blob) or term in blob:
            return True
    return False


def is_unrelated_report(text: str) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False
    for term in UNRELATED_REPORT_TERMS:
        if term in blob:
            return True
    return bool(re.search(r"\bnews\b", blob) or re.search(r"\bpress\s+release\b", blob))


def quarter_for_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def looks_like_document_url(url: str) -> bool:
    blob = normalize_text(url)
    return any(token in blob for token in DOCUMENT_URL_HINTS)


def looks_like_report_text(text: str) -> bool:
    blob = normalize_text(text)
    return any(term in blob for term in REPORT_TERMS_STRONG + REPORT_TERMS_WEAK)


def extract_years(text: str) -> list[int]:
    years = sorted({int(match) for match in re.findall(r"20\d{2}", ascii_fold(text))})
    return years


def canonicalize_url(url: str) -> str:
    cleaned = collapse_spaces(url)
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    return parsed._replace(fragment="").geturl()


def summarize_exception(exc: Exception | str, limit: int = 240) -> str:
    text = str(exc) if str(exc) else str(exc)
    for marker in ("\n", "Browser logs:", "Call log:", "Traceback (most recent call last):"):
        text = text.split(marker)[0]
    text = collapse_spaces(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def build_candidate_blob(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("pdf_url", ""),
        candidate.get("anchor_text", ""),
        candidate.get("title_text", ""),
        candidate.get("context_text", ""),
        candidate.get("page_title", ""),
        candidate.get("visible_text", ""),
    ]
    return " ".join(clean_cell(part) for part in parts if clean_cell(part))


def extract_pdf_urls(text: str) -> list[str]:
    if not text:
        return []
    pattern = re.compile(
        r"""(?i)(?:https?://|//|/|\.{1,2}/)[^"'<>\\\s]+?\.pdf(?:\?[^"'<>\\\s]*)?""",
    )
    return [candidate.rstrip(".,;)]}") for candidate in pattern.findall(text)]


def build_context_text(tag: Any, page_title: str) -> str:
    pieces: list[str] = []
    for attr in ("title", "aria-label", "data-title", "download"):
        value = tag.get(attr)
        if value:
            pieces.append(clean_cell(value))

    anchor_text = clean_cell(tag.get_text(" ", strip=True))
    if anchor_text:
        pieces.append(anchor_text)

    parent = getattr(tag, "parent", None)
    depth = 0
    while parent is not None and depth < 2:
        name = getattr(parent, "name", None)
        if name in {"li", "article", "div", "p", "td", "tr", "section", "main"}:
            parent_text = clean_cell(parent.get_text(" ", strip=True))
            if parent_text and len(parent_text) <= 500:
                pieces.append(parent_text)
                break
        parent = getattr(parent, "parent", None)
        depth += 1

    if page_title:
        pieces.append(page_title)

    return collapse_spaces(" ".join(pieces))


def build_candidate_analysis(candidate: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    blob = build_candidate_blob(candidate)
    raw_blob = ascii_fold(blob).lower()
    token_blob = normalize_text(blob)
    period = normalize_target_period(year, month)

    years_found = extract_years(raw_blob)
    target_year_present = year in years_found
    other_years = [value for value in years_found if value != year]
    month_terms = period["month_terms"]
    quarter = period["quarter"]
    month_term_hits = [term for term in month_terms if re.search(rf"\b{re.escape(term)}\b", token_blob)]
    month_name_match = bool(month_term_hits)
    numeric_month_pattern = re.compile(
        rf"(?<!\d){year}[-_/.\s]?{month:02d}(?!\d)|(?<!\d){month:02d}[-_/.\s]?{year}(?!\d)|(?<!\d){year}{month:02d}(?!\d)",
    )
    numeric_month_match = bool(numeric_month_pattern.search(raw_blob))
    qroman = QUARTER_ROMAN[quarter]
    quarter_patterns = period["quarter_patterns"] + [
        rf"\bq{quarter}\b",
        rf"\bquarter\s*{quarter}\b",
        rf"\bkuartal\s*{quarter}\b",
        rf"\btriwulan\s*{quarter}\b",
        rf"\btriwulan\s*{qroman}\b",
    ]
    quarter_match = any(re.search(pattern, token_blob) for pattern in quarter_patterns)
    strong_report = [term for term in REPORT_TERMS_STRONG if term in token_blob]
    weak_report = [term for term in REPORT_TERMS_WEAK if term in token_blob]
    unrelated_report = [term for term in UNRELATED_REPORT_TERMS if term in token_blob]
    url_hint = looks_like_document_url(candidate.get("pdf_url", ""))
    report_signal = bool(strong_report or weak_report or url_hint)
    syariah = is_syariah_candidate(blob)
    unrelated = bool(unrelated_report or is_unrelated_report(blob))
    pdf_url_lower = normalize_text(candidate.get("pdf_url", "")).split("?")[0]
    is_pdf_link = pdf_url_lower.endswith(".pdf")
    is_image_link = bool(re.search(r"\.(png|jpg|jpeg|gif|webp)$", pdf_url_lower))

    period_group = "other"
    if target_year_present and (numeric_month_match or month_name_match):
        period_group = "month"
        period_rank = 0
    elif target_year_present and quarter_match:
        period_group = "quarter"
        period_rank = 1
    elif target_year_present and report_signal:
        period_group = "year"
        period_rank = 2
    else:
        period_rank = 4

    topic_rank = 0 if strong_report else 1 if weak_report else 2
    url_rank = 0 if numeric_month_match or month_name_match else 1 if url_hint else 2
    year_penalty = len(other_years) * 5
    score = period_rank * 100 + topic_rank * 10 + url_rank + year_penalty
    if syariah:
        score -= 10_000
    if unrelated:
        score -= 250
    if "konvensional" in token_blob or "conventional" in token_blob:
        score += 120
    if "reasuransi" in token_blob or "reinsurance" in token_blob:
        score += 40
    if "perusahaan" in token_blob or "company" in token_blob:
        score += 20
    if target_year_present:
        score += 50
    if month_name_match:
        score += 80
    if numeric_month_match:
        score += 100
    if quarter_match:
        score += 35
    if looks_like_report_text(blob):
        score += 30
    if "publikasi laporan keuangan" in token_blob:
        score += 80
    if is_pdf_link:
        score += 150
    if is_image_link:
        score -= 400

    match_reasons: list[str] = []
    if numeric_month_match:
        match_reasons.append("numeric month-year match")
    if month_name_match:
        match_reasons.append(f"month term match: {', '.join(month_term_hits)}")
    if quarter_match:
        match_reasons.append(f"quarter match: Q{quarter}")
    if strong_report:
        match_reasons.append(f"report term: {', '.join(strong_report[:2])}")
    elif weak_report:
        match_reasons.append(f"report hint: {', '.join(weak_report[:2])}")
    if url_hint:
        match_reasons.append("document-url hint")
    if target_year_present:
        match_reasons.append(f"year {year}")
    if other_years:
        match_reasons.append(f"other years: {', '.join(str(value) for value in other_years)}")
    if syariah:
        match_reasons.append("syariah term detected")
    if unrelated:
        match_reasons.append("unrelated report term detected")
    if is_pdf_link:
        match_reasons.append("pdf link")
    if is_image_link:
        match_reasons.append("image preview link")

    relevant = bool(
        target_year_present
        and not syariah
        and not unrelated
        and (numeric_month_match or month_name_match or quarter_match or report_signal)
    )

    return {
        "blob": blob,
        "years_found": years_found,
        "target_year_present": target_year_present,
        "other_years": other_years,
        "month_term_hits": month_term_hits,
        "numeric_month_match": numeric_month_match,
        "month_name_match": month_name_match,
        "quarter_match": quarter_match,
        "report_signal": report_signal,
        "strong_report_terms": strong_report,
        "weak_report_terms": weak_report,
        "url_hint": url_hint,
        "syariah": syariah,
        "unrelated": unrelated,
        "relevant": relevant,
        "period_group": period_group,
        "period_rank": period_rank,
        "topic_rank": topic_rank,
        "url_rank": url_rank,
        "year_penalty": year_penalty,
        "score": score,
        "match_reason": "; ".join(match_reasons) if match_reasons else "no matching report signal",
    }


def score_candidate(candidate: dict[str, Any], year: int, month: int) -> int:
    analysis = candidate.get("analysis")
    if not isinstance(analysis, dict):
        analysis = build_candidate_analysis(candidate, year, month)
        candidate["analysis"] = analysis
    return int(analysis.get("score", 0))


def is_relevant_financial_report(text: str, year: int, month: int) -> bool:
    candidate = {
        "pdf_url": "",
        "anchor_text": text,
        "title_text": "",
        "context_text": "",
        "page_title": "",
    }
    analysis = build_candidate_analysis(candidate, year, month)
    return bool(analysis["relevant"])


def is_valid_pdf_response(response: Any, content_bytes: bytes) -> bool:
    headers = getattr(response, "headers", {}) or {}
    content_type = clean_cell(headers.get("Content-Type", headers.get("content-type", ""))).lower()
    content_disposition = clean_cell(
        headers.get("Content-Disposition", headers.get("content-disposition", "")),
    ).lower()
    final_url = clean_cell(getattr(response, "url", "")).lower().split("?")[0]
    return (
        content_bytes.startswith(b"%PDF")
        or "application/pdf" in content_type
        or final_url.endswith(".pdf")
        or "pdf" in content_disposition
    )


def add_raw_candidate(
    candidates: dict[str, dict[str, Any]],
    *,
    url: str,
    source_page_url: str,
    discovered_page_url: str,
    anchor_text: str,
    title_text: str,
    context_text: str,
    page_title: str,
    discovery_mode: str,
    year: int,
    month: int,
) -> None:
    resolved = canonicalize_url(url)
    if not resolved:
        return

    candidate = {
        "pdf_url": resolved,
        "source_page_url": source_page_url,
        "discovered_page_url": discovered_page_url or source_page_url,
        "anchor_text": anchor_text,
        "title_text": title_text,
        "context_text": context_text,
        "page_title": page_title,
        "discovery_mode": discovery_mode,
    }
    analysis = build_candidate_analysis(candidate, year, month)
    candidate["analysis"] = analysis

    if not (analysis["relevant"] or analysis["syariah"] or analysis["unrelated"] or analysis["report_signal"]):
        return

    key = resolved.lower()
    if key in candidates:
        existing = candidates[key]
        for field in ("anchor_text", "title_text", "context_text", "page_title", "discovered_page_url"):
            existing_value = clean_cell(existing.get(field, ""))
            new_value = clean_cell(candidate.get(field, ""))
            if new_value and new_value not in existing_value:
                existing[field] = f"{existing_value} | {new_value}" if existing_value else new_value
        existing["discovery_mode"] = existing.get("discovery_mode") or discovery_mode
        existing["analysis"] = build_candidate_analysis(existing, year, month)
        return

    candidates[key] = candidate


def parse_candidates_from_html(
    html: str,
    *,
    base_url: str,
    source_page_url: str,
    discovered_page_url: str,
    page_title: str,
    year: int,
    month: int,
    discovery_mode: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    if not page_title:
        title_tag = soup.title.string if soup.title and soup.title.string else ""
        page_title = clean_cell(title_tag)

    discovered: dict[str, dict[str, Any]] = {}

    for tag in soup.find_all(True):
        tag_name = getattr(tag, "name", "").lower()
        urls: list[str] = []

        if tag_name == "a":
            href = clean_cell(tag.get("href"))
            if href:
                urls.append(href)
        for attr in ("src", "data", "href"):
            if tag_name == "a" and attr == "href":
                continue
            value = clean_cell(tag.get(attr))
            if value:
                urls.append(value)

        for attr_value in tag.attrs.values():
            if isinstance(attr_value, (list, tuple)):
                values = [clean_cell(item) for item in attr_value if clean_cell(item)]
            else:
                values = [clean_cell(attr_value)] if clean_cell(attr_value) else []
            for value in values:
                for extracted in extract_pdf_urls(value):
                    urls.append(extracted)

        if tag_name == "meta" and "refresh" in clean_cell(tag.get("http-equiv")).lower():
            content = clean_cell(tag.get("content"))
            match = re.search(r"url\s*=\s*(.+)$", content, flags=re.I)
            if match:
                urls.append(match.group(1).strip())

        if not urls:
            continue

        context_text = build_context_text(tag, page_title)
        title_text = clean_cell(tag.get("title") or tag.get("aria-label") or tag.get("data-title") or "")
        anchor_text = clean_cell(tag.get_text(" ", strip=True)) or title_text

        candidate_blob = normalize_text(" ".join([anchor_text, title_text, context_text, page_title]))
        if not candidate_blob:
            continue

        for raw_url in urls:
            resolved = canonicalize_url(urljoin(base_url, raw_url))
            if not resolved:
                continue
            resolved_blob = normalize_text(f"{resolved} {candidate_blob}")
            if is_syariah_candidate(resolved_blob):
                add_raw_candidate(
                    discovered,
                    url=resolved,
                    source_page_url=source_page_url,
                    discovered_page_url=discovered_page_url,
                    anchor_text=anchor_text,
                    title_text=title_text,
                    context_text=context_text,
                    page_title=page_title,
                    discovery_mode=discovery_mode,
                    year=year,
                    month=month,
                )
                continue
            if looks_like_document_url(resolved) and is_relevant_financial_report(resolved_blob, year, month):
                add_raw_candidate(
                    discovered,
                    url=resolved,
                    source_page_url=source_page_url,
                    discovered_page_url=discovered_page_url,
                    anchor_text=anchor_text,
                    title_text=title_text,
                    context_text=context_text,
                    page_title=page_title,
                    discovery_mode=discovery_mode,
                    year=year,
                    month=month,
                )
                continue
            if looks_like_document_url(resolved) and looks_like_report_text(candidate_blob):
                add_raw_candidate(
                    discovered,
                    url=resolved,
                    source_page_url=source_page_url,
                    discovered_page_url=discovered_page_url,
                    anchor_text=anchor_text,
                    title_text=title_text,
                    context_text=context_text,
                    page_title=page_title,
                    discovery_mode=discovery_mode,
                    year=year,
                    month=month,
                )

    for raw_url in extract_pdf_urls(html):
        resolved = canonicalize_url(urljoin(base_url, raw_url))
        if not resolved:
            continue
        add_raw_candidate(
            discovered,
            url=resolved,
            source_page_url=source_page_url,
            discovered_page_url=discovered_page_url,
            anchor_text="raw-html-url",
            title_text="",
            context_text="",
            page_title=page_title,
            discovery_mode=discovery_mode,
            year=year,
            month=month,
        )

    candidates = list(discovered.values())
    candidates.sort(key=lambda item: (-item["analysis"]["score"], item["pdf_url"]))
    return candidates


def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _normalized_host(url: str) -> str:
    host = urlparse(canonicalize_url(url)).netloc.lower()
    return host.removeprefix("www.")


def _same_host(left: str, right: str) -> bool:
    left_host = _normalized_host(left)
    right_host = _normalized_host(right)
    return bool(left_host and right_host and left_host == right_host)


def _extract_nested_html_links(
    html: str,
    *,
    base_url: str,
    source_page_url: str,
    year: int,
    month: int,
    current_depth: int,
    max_depth: int,
) -> list[str]:
    if current_depth >= max_depth:
        return []

    soup = _make_soup(html)
    target = normalize_target_period(year, month)
    period_terms = [normalize_text(term) for term in target["all_variants"]]
    nested: list[str] = []
    seen: set[str] = set()

    for tag in soup.find_all(["a", "button", "summary", "div", "span", "li"]):
        if len(nested) >= MAX_LINKS_PER_PAGE:
            break
        href = clean_cell(tag.get("href") or tag.get("data-href") or tag.get("data-url") or "")
        if not href:
            continue
        if href.startswith(("mailto:", "tel:", "javascript:")) or href.startswith("#"):
            continue

        resolved = canonicalize_url(urljoin(base_url, href))
        if not resolved or resolved.lower().endswith(".pdf"):
            continue
        if not _same_host(source_page_url, resolved):
            continue

        text = collapse_spaces(
            " ".join(
                part
                for part in [
                    clean_cell(tag.get_text(" ", strip=True)),
                    clean_cell(tag.get("title")),
                    clean_cell(tag.get("aria-label")),
                    clean_cell(tag.get("data-title")),
                    clean_cell(tag.get("data-text")),
                    clean_cell(tag.get("class")),
                    clean_cell(tag.get("id")),
                ]
                if part
            ),
        )
        blob = normalize_text(f"{text} {resolved}")
        if not any(term in blob for term in FOLLOW_LINK_HINTS) and not re.search(rf"\b{year}\b", blob):
            if not any(term in blob for term in period_terms):
                continue
        key = resolved.lower()
        if key in seen:
            continue
        seen.add(key)
        nested.append(resolved)

    return nested


def _expand_browser_page(page: Any, year: int, month: int) -> None:
    target = normalize_target_period(year, month)
    click_keywords = {
        *FOLLOW_LINK_HINTS,
        *target["month_terms"],
        *target["quarter_patterns"],
        "accordion",
        "tab",
        "year",
        "month",
        "filter",
        "more",
    }

    selectors = [
        "button",
        "[role='button']",
        "summary",
        "a",
        "[data-bs-toggle]",
        "[data-toggle]",
        "[aria-expanded='false']",
        ".accordion-button",
        ".tab",
        ".tabs button",
        "select",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            continue

        for index in range(min(count, 30)):
            element = locator.nth(index)
            try:
                text = collapse_spaces(
                    " ".join(
                        clean_cell(part)
                        for part in [
                            element.inner_text(timeout=500),
                            element.get_attribute("aria-label"),
                            element.get_attribute("title"),
                            element.get_attribute("data-title"),
                        ]
                        if clean_cell(part)
                    ),
                )
            except Exception:
                text = ""
            blob = normalize_text(text)
            if selector == "select":
                try:
                    options = element.locator("option").all()
                except Exception:
                    options = []
                matched = False
                for option in options[:12]:
                    try:
                        option_text = collapse_spaces(
                            " ".join(
                                clean_cell(part)
                                for part in [
                                    option.inner_text(timeout=300),
                                    option.get_attribute("value"),
                                    option.get_attribute("label"),
                                ]
                                if clean_cell(part)
                            ),
                        )
                        option_blob = normalize_text(option_text)
                        if any(term in option_blob for term in click_keywords):
                            value = option.get_attribute("value") or option_text
                            with suppress(Exception):
                                element.select_option(value=value)
                            matched = True
                            break
                    except Exception:
                        continue
                if matched:
                    with suppress(Exception):
                        page.wait_for_timeout(750)
                continue

            if not blob or not any(term in blob for term in click_keywords):
                continue
            with suppress(Exception):
                element.scroll_into_view_if_needed(timeout=500)
            try:
                element.click(timeout=1000, force=True)
                page.wait_for_timeout(500)
            except Exception:
                continue


def _render_html_with_browser(source_url: str, timeout: int, year: int, month: int) -> tuple[str, str, str, int, str]:
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed")

    timeout_ms = max(timeout, 1) * 1000
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            accept_downloads=True,
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 1800},
        )
        page = context.new_page()
        try:
            response = page.goto(source_url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response is None:
                raise RuntimeError(f"browser did not return a response for {source_url}")
            with suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
            _expand_browser_page(page, year, month)
            with suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
            html = page.content()
            final_url = page.url
            title = clean_cell(page.title())
            status_code = response.status
            content_type = response.headers.get("content-type", "")
            return html, final_url, title, status_code, content_type
        finally:
            with suppress(Exception):
                page.close()
            with suppress(Exception):
                context.close()
            with suppress(Exception):
                browser.close()


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.trust_env = True
    return session


def fetch_html_with_requests(session: requests.Session, source_url: str, timeout: int) -> requests.Response:
    response = session.get(
        source_url,
        timeout=timeout,
        allow_redirects=True,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    response.raise_for_status()
    return response


def fetch_html_with_browser(
    source_url: str,
    timeout: int,
    year: int = 1970,
    month: int = 1,
) -> tuple[str, str, str]:
    html, final_url, title, _status_code, _content_type = _render_html_with_browser(source_url, timeout, year, month)
    return html, final_url, title


def _make_direct_pdf_candidate(
    *,
    pdf_url: str,
    source_page_url: str,
    discovered_page_url: str,
    discovery_mode: str,
    year: int,
    month: int,
    http_status: int | None = None,
) -> dict[str, Any]:
    candidate = {
        "pdf_url": canonicalize_url(pdf_url),
        "source_page_url": source_page_url,
        "discovered_page_url": discovered_page_url or source_page_url,
        "anchor_text": "direct_pdf",
        "title_text": "direct_pdf",
        "context_text": "direct_pdf",
        "page_title": "",
        "visible_text": "direct_pdf",
        "discovery_mode": discovery_mode,
        "http_status": http_status,
    }
    candidate["analysis"] = build_candidate_analysis(candidate, year, month)
    return candidate


def _dedupe_candidates(candidates: list[dict[str, Any]], year: int, month: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        pdf_url = canonicalize_url(candidate.get("pdf_url", ""))
        if not pdf_url:
            continue
        candidate["pdf_url"] = pdf_url
        analysis = candidate.get("analysis")
        if not isinstance(analysis, dict):
            analysis = build_candidate_analysis(candidate, year, month)
            candidate["analysis"] = analysis
        key = pdf_url.lower()
        if key not in merged:
            merged[key] = candidate
            continue
        existing = merged[key]
        for field in ("anchor_text", "title_text", "context_text", "page_title", "visible_text", "discovered_page_url"):
            existing_value = clean_cell(existing.get(field, ""))
            new_value = clean_cell(candidate.get(field, ""))
            if new_value and new_value not in existing_value:
                existing[field] = f"{existing_value} | {new_value}" if existing_value else new_value
        if candidate.get("discovery_mode") == "browser" and existing.get("discovery_mode") != "browser":
            existing["discovery_mode"] = candidate["discovery_mode"]
        if candidate.get("discovery_mode", "").startswith("crawled_") and not str(existing.get("discovery_mode", "")).startswith("crawled_"):
            existing["discovery_mode"] = candidate["discovery_mode"]
        existing["analysis"] = build_candidate_analysis(existing, year, month)
    candidates = list(merged.values())
    candidates.sort(key=lambda item: (-item["analysis"]["score"], item["pdf_url"]))
    return candidates


def extract_candidates_static(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    debug_pages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return crawl_related_pages(
        session,
        source_url,
        year,
        month,
        max_depth=0,
        use_browser=False,
        debug_pages=debug_pages,
    )


def extract_candidates_browser(
    source_url: str,
    year: int,
    month: int,
    debug_pages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    session = create_session()
    try:
        return crawl_related_pages(
            session,
            source_url,
            year,
            month,
            max_depth=0,
            use_browser=True,
            debug_pages=debug_pages,
        )
    finally:
        session.close()


def _record_debug_page(
    debug_pages: list[dict[str, Any]] | None,
    *,
    company_slug: str,
    depth: int,
    method: str,
    source_page_url: str,
    discovered_page_url: str,
    html: str,
    status_code: int | None,
    content_type: str,
    title: str,
) -> None:
    if debug_pages is None:
        return
    debug_pages.append(
        {
            "company_slug": company_slug,
            "depth": depth,
            "method": method,
            "source_page_url": source_page_url,
            "discovered_page_url": discovered_page_url,
            "html": html,
            "status_code": status_code,
            "content_type": content_type,
            "title": title,
        },
    )


def _discover_page(
    session: requests.Session,
    source_url: str,
    root_source_url: str,
    year: int,
    month: int,
    *,
    timeout: int,
    use_browser: bool,
    depth: int,
    max_depth: int,
    debug_pages: list[dict[str, Any]] | None,
    company_slug: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    canonical_source_url = canonicalize_url(source_url)
    if not canonical_source_url:
        return [], []

    if canonical_source_url.lower().endswith(".pdf"):
        candidate = _make_direct_pdf_candidate(
            pdf_url=canonical_source_url,
            source_page_url=root_source_url,
            discovered_page_url=canonical_source_url,
            discovery_mode="browser" if use_browser else "static",
            year=year,
            month=month,
            http_status=None,
        )
        return [candidate], []

    html = ""
    final_url = canonical_source_url
    title = ""
    status_code: int | None = None
    content_type = ""
    used_browser = False

    browser_error: Exception | None = None
    request_error: Exception | None = None

    if use_browser:
        try:
            html, final_url, title, status_code, content_type = _render_html_with_browser(
                canonical_source_url,
                timeout,
                year,
                month,
            )
            used_browser = True
        except Exception as exc:  # noqa: BLE001
            browser_error = exc

    if not html:
        try:
            response = fetch_html_with_requests(session, canonical_source_url, timeout)
            status_code = response.status_code
            content_type = response.headers.get("Content-Type", "")
            final_url = response.url or canonical_source_url
            if is_valid_pdf_response(response, response.content):
                candidate = _make_direct_pdf_candidate(
                    pdf_url=final_url,
                    source_page_url=root_source_url,
                    discovered_page_url=final_url,
                    discovery_mode="browser" if use_browser else "static",
                    year=year,
                    month=month,
                    http_status=status_code,
                )
                _record_debug_page(
                    debug_pages,
                    company_slug=company_slug,
                    depth=depth,
                    method="browser" if used_browser else "static",
                    source_page_url=root_source_url,
                    discovered_page_url=final_url,
                    html="",
                    status_code=status_code,
                    content_type=content_type,
                    title=title,
                )
                return [candidate], []
            html = response.text
            soup = _make_soup(html)
            title = clean_cell(soup.title.get_text(strip=True)) if soup.title else ""
        except Exception as exc:  # noqa: BLE001
            request_error = exc

    if not html:
        if browser_error is not None and request_error is not None:
            LOGGER.debug(
                "[%s] both browser and static fetch failed for %s: %s / %s",
                company_slug,
                canonical_source_url,
                summarize_exception(browser_error),
                summarize_exception(request_error),
            )
        return [], []

    base_method = "browser" if used_browser else "static"
    discovery_mode = base_method if depth == 0 else f"crawled_{base_method}"
    candidates = parse_candidates_from_html(
        html,
        base_url=final_url,
        source_page_url=root_source_url,
        discovered_page_url=final_url,
        page_title=title,
        year=year,
        month=month,
        discovery_mode=discovery_mode,
    )
    nested_links = _extract_nested_html_links(
        html,
        base_url=final_url,
        source_page_url=root_source_url,
        year=year,
        month=month,
        current_depth=depth,
        max_depth=max_depth,
    )
    _record_debug_page(
        debug_pages,
        company_slug=company_slug,
        depth=depth,
        method=discovery_mode,
        source_page_url=root_source_url,
        discovered_page_url=final_url,
        html=html,
        status_code=status_code,
        content_type=content_type,
        title=title,
    )
    return candidates, nested_links


def crawl_related_pages(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    max_depth: int = 2,
    use_browser: bool = False,
    debug_pages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    timeout = getattr(session, "_download_timeout", REQUEST_TIMEOUT_DEFAULT)
    company_slug = sanitize_filename(source_url)
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(source_url, 0)])
    collected: list[dict[str, Any]] = []

    while queue:
        page_url, depth = queue.popleft()
        canonical_url = canonicalize_url(page_url)
        if not canonical_url:
            continue
        key = canonical_url.lower()
        if key in visited:
            continue
        visited.add(key)

        candidates, nested_links = _discover_page(
            session,
            canonical_url,
            source_url,
            year,
            month,
            timeout=timeout,
            use_browser=use_browser,
            depth=depth,
            max_depth=max_depth,
            debug_pages=debug_pages,
            company_slug=company_slug,
        )
        collected.extend(candidates)

        if depth >= max_depth:
            continue
        for nested_url in nested_links:
            if not _same_host(source_url, nested_url):
                continue
            queue.append((nested_url, depth + 1))

    return _dedupe_candidates(collected, year, month)


def extract_pdf_candidates(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    use_browser: bool = False,
    timeout: int = REQUEST_TIMEOUT_DEFAULT,
) -> list[dict[str, Any]]:
    session._download_timeout = timeout  # type: ignore[attr-defined]
    candidates = crawl_related_pages(
        session,
        source_url,
        year,
        month,
        max_depth=2,
        use_browser=use_browser,
    )
    return candidates


def choose_best_candidate(candidates: list[dict[str, Any]], year: int, month: int) -> dict[str, Any] | None:
    if not candidates:
        return None

    conventional = [
        candidate
        for candidate in candidates
        if candidate["analysis"]["relevant"]
    ]
    if not conventional:
        return None

    target_month_group = [
        candidate for candidate in conventional if candidate["analysis"]["period_group"] == "month"
    ]
    quarter_group = [
        candidate for candidate in conventional if candidate["analysis"]["period_group"] == "quarter"
    ]
    year_group = [candidate for candidate in conventional if candidate["analysis"]["period_group"] == "year"]
    preferred_groups = [target_month_group, quarter_group, year_group, conventional]
    for group in preferred_groups:
        if group:
            return max(group, key=lambda item: (item["analysis"]["score"], item["pdf_url"]))

    return None


def candidate_filename(pdf_url: str, company_slug: str, year: int, month: int) -> str:
    parsed = urlparse(pdf_url)
    name = clean_cell(unquote(Path(parsed.path).name))
    stem = sanitize_filename(Path(name).stem) if name else ""
    if stem and stem not in BAD_FILENAME_TOKENS and len(stem) > 3:
        filename = f"{stem}.pdf"
    else:
        filename = f"{company_slug}_{year:04d}-{month:02d}.pdf"
    return filename


def download_pdf(
    session: requests.Session,
    pdf_url: str,
    output_path: Path,
    timeout: int,
    force: bool = False,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        return {
            "status": "skipped_existing",
            "reason": "file already exists",
            "http_status": None,
            "file_size_bytes": output_path.stat().st_size,
        }

    tmp_path = output_path.with_suffix(output_path.suffix + ".part")
    try:
        with session.get(
            pdf_url,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
            headers={"Accept": "application/pdf,*/*;q=0.8"},
        ) as response:
            http_status = response.status_code
            response.raise_for_status()
            first_bytes = b""
            bytes_written = 0
            with tmp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(first_bytes) < 8:
                        first_bytes += bytes(chunk[: 8 - len(first_bytes)])
                    handle.write(chunk)
                    bytes_written += len(chunk)
        final_url = response.url or pdf_url
        if bytes_written == 0:
            raise ValueError(f"empty response for PDF: {pdf_url}")
        if not is_valid_pdf_response(response, first_bytes):
            raise ValueError(f"{pdf_url} did not look like a PDF after download")

        tmp_path.replace(output_path)
        return {
            "status": "downloaded",
            "reason": "downloaded successfully",
            "http_status": http_status,
            "file_size_bytes": bytes_written,
        }
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        return {
            "status": "failed",
            "reason": summarize_exception(exc),
            "http_status": getattr(exc, "response", None).status_code if getattr(exc, "response", None) else None,
            "file_size_bytes": None,
        }


def timestamp_now() -> str:
    return datetime.now(MANIFEST_TIMEZONE).isoformat(timespec="seconds")


def choose_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.output_root) / f"{args.year:04d}-{args.month:02d}" / OUTPUT_SUBDIR / CATEGORY


def resolve_input_path(input_arg: str) -> Path:
    candidate = Path(input_arg)
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        for fallback in (Path("assets") / candidate, Path("assets") / candidate.name):
            if fallback.exists():
                return fallback
    raise FileNotFoundError(f"Input workbook not found: {input_arg}")


def _debug_html_dir(output_root: Path, year: int, month: int, company_slug: str) -> Path:
    return output_root / f"{year:04d}-{month:02d}" / OUTPUT_SUBDIR / CATEGORY / "_debug_html" / company_slug


def _write_debug_html(
    debug_pages: list[dict[str, Any]],
    *,
    output_root: Path,
    year: int,
    month: int,
    company_slug: str,
    company_name: str,
) -> None:
    if not debug_pages:
        return

    debug_dir = _debug_html_dir(output_root, year, month, company_slug)
    debug_dir.mkdir(parents=True, exist_ok=True)
    summary_path = debug_dir / "summary.json"
    summary: list[dict[str, Any]] = []

    for index, page in enumerate(debug_pages):
        html_path = debug_dir / f"{index:02d}_{sanitize_filename(page.get('method', 'page'))}.html"
        html = clean_cell(page.get("html"))
        html_path.write_text(
            "\n".join(
                [
                    "<html><head><meta charset='utf-8'>",
                    f"<title>{html_escape(company_name)} - {html_escape(clean_cell(page.get('method')))}</title>",
                    "</head><body>",
                    "<pre>",
                    html_escape(
                        "\n".join(
                            [
                                f"company_name: {company_name}",
                                f"company_slug: {company_slug}",
                                f"depth: {page.get('depth')}",
                                f"method: {page.get('method')}",
                                f"source_page_url: {page.get('source_page_url')}",
                                f"discovered_page_url: {page.get('discovered_page_url')}",
                                f"status_code: {page.get('status_code')}",
                                f"content_type: {page.get('content_type')}",
                                f"title: {page.get('title')}",
                                "",
                                html,
                            ],
                        ),
                    ),
                    "</pre>",
                    "</body></html>",
                ],
            ),
            encoding="utf-8",
        )
        summary.append(
            {
                "index": index,
                "method": page.get("method"),
                "depth": page.get("depth"),
                "source_page_url": page.get("source_page_url"),
                "discovered_page_url": page.get("discovered_page_url"),
                "status_code": page.get("status_code"),
                "content_type": page.get("content_type"),
                "title": page.get("title"),
                "html_file": str(html_path),
            },
        )

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _candidate_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        pdf_url = canonicalize_url(candidate.get("pdf_url", ""))
        if not pdf_url:
            continue
        key = pdf_url.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    syariah = sum(1 for candidate in unique if candidate["analysis"]["syariah"])
    unrelated = sum(
        1 for candidate in unique if not candidate["analysis"]["syariah"] and candidate["analysis"]["unrelated"]
    )
    return {
        "candidate_count": len(unique),
        "rejected_syariah_count": syariah,
        "rejected_unrelated_count": unrelated,
    }


def _best_candidate_for_evidence(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["analysis"]["score"], item["pdf_url"]))


def _build_no_match_reason(
    candidates: list[dict[str, Any]],
    static_candidates: list[dict[str, Any]],
    browser_candidates: list[dict[str, Any]],
) -> str:
    if not candidates:
        static_count = len(static_candidates)
        browser_count = len(browser_candidates)
        return f"no candidate PDF links discovered after static ({static_count}) and browser ({browser_count}) crawl"

    syariah_count = sum(1 for candidate in candidates if candidate["analysis"]["syariah"])
    unrelated_count = sum(
        1 for candidate in candidates if not candidate["analysis"]["syariah"] and candidate["analysis"]["unrelated"]
    )
    conventional = [candidate for candidate in candidates if candidate["analysis"]["relevant"]]
    if syariah_count and not conventional:
        return f"only syariah candidates discovered ({syariah_count}); conventional report not found after static and browser crawl"
    if unrelated_count and not conventional:
        return f"only unrelated report candidates discovered ({unrelated_count}); conventional financial report not found"

    best = _best_candidate_for_evidence(candidates)
    if best is None:
        return "no candidate PDF links discovered"
    return f"no conventional March 2026 report matched; best candidate: {best['analysis']['match_reason']}"


def _merge_candidate_lists(*candidate_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate_list in candidate_lists:
        for candidate in candidate_list:
            pdf_url = canonicalize_url(candidate.get("pdf_url", ""))
            if not pdf_url:
                continue
            key = pdf_url.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
    return merged


def load_input_rows(input_path: Path) -> list[dict[str, Any]]:
    df = pd.read_excel(input_path, engine="openpyxl")
    column_map = {normalize_text(column): column for column in df.columns}

    def pick_column(*aliases: str) -> str | None:
        for alias in aliases:
            column = column_map.get(normalize_text(alias))
            if column is not None:
                return column
        return None

    no_column = pick_column("no", "nomor")
    company_column = pick_column("nama perusahaan", "nama_perusahaan", "company", "company name", "nama")
    link_column = pick_column("link", "url", "source_url", "source url")
    if company_column is None or link_column is None:
        raise ValueError("Workbook must contain at least 'nama perusahaan' and 'link' columns")

    rows: list[dict[str, Any]] = []
    for excel_index, row in df.iterrows():
        company_name = clean_cell(row[company_column])
        source_page_url = clean_cell(row[link_column])
        row_no = clean_cell(row[no_column]) if no_column is not None else str(excel_index + 1)
        if not company_name and not source_page_url:
            continue
        rows.append(
            {
                "excel_row": excel_index + 2,
                "row_no": row_no,
                "company_name": company_name,
                "source_page_url": source_page_url,
            },
        )
    return rows


def format_reason_from_candidates(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "no candidates discovered"
    best = max(candidates, key=lambda item: (item["analysis"]["score"], item["pdf_url"]))
    return best["analysis"]["match_reason"]


def process_company(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    company_name = clean_cell(row.get("company_name"))
    source_page_url = clean_cell(row.get("source_page_url"))
    company_slug = sanitize_filename(company_name)
    output_dir = choose_output_dir(args) / company_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{company_slug}_{args.year:04d}-{args.month:02d}.pdf"
    debug_pages: list[dict[str, Any]] = []

    base_record: dict[str, Any] = {
        "category": CATEGORY,
        "company_name": company_name,
        "source_page_url": source_page_url,
        "discovered_page_url": "",
        "pdf_url": "",
        "target_year": args.year,
        "target_month": args.month,
        "output_path": str(output_path),
        "status": "failed",
        "reason": "",
        "discovery_method": "",
        "score": 0,
        "rejected_syariah_count": 0,
        "rejected_unrelated_count": 0,
        "candidate_count": 0,
        "http_status": None,
        "file_size_bytes": None,
        "timestamp": timestamp_now(),
    }

    if not source_page_url:
        base_record["reason"] = "missing source page url"
        return base_record

    session = create_session()
    session._download_timeout = args.timeout  # type: ignore[attr-defined]
    try:
        LOGGER.info("[%s] discovering report links from %s", company_name or company_slug, source_page_url)
        static_candidates = crawl_related_pages(
            session,
            source_page_url,
            args.year,
            args.month,
            max_depth=args.max_depth,
            use_browser=False,
            debug_pages=debug_pages,
        )
        candidates = static_candidates
        browser_candidates: list[dict[str, Any]] = []
        best_conventional = choose_best_candidate(candidates, args.year, args.month)

        if best_conventional is None and args.use_browser:
            browser_max_depth = 0 if len(static_candidates) > 80 else args.max_depth
            browser_candidates = crawl_related_pages(
                session,
                source_page_url,
                args.year,
                args.month,
                max_depth=browser_max_depth,
                use_browser=True,
                debug_pages=debug_pages,
            )
            candidates = _merge_candidate_lists(static_candidates, browser_candidates)
            candidates = _dedupe_candidates(candidates, args.year, args.month)
            best_conventional = choose_best_candidate(candidates, args.year, args.month)

        LOGGER.info(
            "[%s] discovered %d candidate(s)",
            company_name or company_slug,
            len(candidates),
        )

        counts = _candidate_counts(candidates)
        base_record["candidate_count"] = counts["candidate_count"]
        base_record["rejected_syariah_count"] = counts["rejected_syariah_count"]
        base_record["rejected_unrelated_count"] = counts["rejected_unrelated_count"]

        evidence_candidate = _best_candidate_for_evidence(candidates)
        if evidence_candidate is not None:
            base_record["pdf_url"] = evidence_candidate.get("pdf_url", "")
            base_record["discovered_page_url"] = clean_cell(evidence_candidate.get("discovered_page_url"))
            base_record["discovery_method"] = clean_cell(evidence_candidate.get("discovery_mode"))
            base_record["score"] = int(evidence_candidate["analysis"]["score"])
            base_record["http_status"] = evidence_candidate.get("http_status")

        if best_conventional is None:
            base_record["status"] = "no_match"
            base_record["reason"] = _build_no_match_reason(candidates, static_candidates, browser_candidates)
            if args.debug_html:
                _write_debug_html(
                    debug_pages,
                    output_root=Path(args.output_root),
                    year=args.year,
                    month=args.month,
                    company_slug=company_slug,
                    company_name=company_name,
                )
            return base_record

        output_path = output_dir / candidate_filename(
            pdf_url=best_conventional["pdf_url"],
            company_slug=company_slug,
            year=args.year,
            month=args.month,
        )
        base_record["output_path"] = str(output_path)
        base_record["pdf_url"] = best_conventional["pdf_url"]
        base_record["discovered_page_url"] = clean_cell(best_conventional.get("discovered_page_url"))
        base_record["discovery_method"] = clean_cell(best_conventional.get("discovery_mode"))
        base_record["score"] = int(best_conventional["analysis"]["score"])
        base_record["http_status"] = best_conventional.get("http_status")
        base_record["reason"] = best_conventional["analysis"]["match_reason"]

        if args.dry_run or args.discover_only:
            base_record.update(
                {
                    "status": "discover_only",
                    "reason": (
                        f"{'dry-run' if args.dry_run else 'discover-only'}: "
                        f"{best_conventional['analysis']['match_reason']}"
                    ),
                    "http_status": None,
                    "file_size_bytes": None,
                },
            )
            if args.debug_html and base_record["status"] in {"no_match", "failed"}:
                _write_debug_html(
                    debug_pages,
                    output_root=Path(args.output_root),
                    year=args.year,
                    month=args.month,
                    company_slug=company_slug,
                    company_name=company_name,
                )
            return base_record

        download_result = download_pdf(
            session,
            best_conventional["pdf_url"],
            output_path,
            timeout=args.timeout,
            force=args.force,
        )
        base_record.update(download_result)
        if base_record["status"] == "failed":
            base_record["reason"] = f"{best_conventional['analysis']['match_reason']}; {download_result['reason']}"
        else:
            base_record["reason"] = best_conventional["analysis"]["match_reason"]
        if base_record["status"] == "skipped_existing":
            base_record["file_size_bytes"] = output_path.stat().st_size if output_path.exists() else None
        if base_record["status"] in {"failed", "no_match"} and args.debug_html:
            _write_debug_html(
                debug_pages,
                output_root=Path(args.output_root),
                year=args.year,
                month=args.month,
                company_slug=company_slug,
                company_name=company_name,
            )
        return base_record
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("[%s] failed: %s", company_name or company_slug, summarize_exception(exc))
        base_record.update(
            {
                "status": "failed",
                "reason": summarize_exception(exc),
            },
        )
        if args.debug_html:
            _write_debug_html(
                debug_pages,
                output_root=Path(args.output_root),
                year=args.year,
                month=args.month,
                company_slug=company_slug,
                company_name=company_name,
            )
        return base_record
    finally:
        session.close()


def write_manifest(records: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "download_manifest.csv"
    json_path = output_dir / "download_manifest.json"

    ordered_records = sorted(records, key=lambda item: item.get("_row_index", 0))
    stripped_records: list[dict[str, Any]] = []
    for record in ordered_records:
        stripped = {field: record.get(field) for field in MANIFEST_FIELDS}
        stripped_records.append(stripped)

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(stripped_records)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(stripped_records, handle, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    input_path = resolve_input_path(args.input)
    output_dir = choose_output_dir(args)
    rows = load_input_rows(input_path)

    LOGGER.info(
        "Starting reinsurance download run for %04d-%02d from %s",
        args.year,
        args.month,
        input_path,
    )
    LOGGER.info("Discovered %d company row(s)", len(rows))
    if args.dry_run or args.discover_only:
        LOGGER.info("Discovery-only mode enabled: PDFs will not be written")

    records: list[dict[str, Any]] = []
    if not rows:
        LOGGER.warning("No company rows found in %s", input_path)
        write_manifest(records, output_dir)
        return 0

    if args.max_workers == 1:
        iterator = rows
        for index, row in enumerate(iterator, start=1):
            result = process_company(row, args)
            result["_row_index"] = index
            records.append(result)
            LOGGER.info(
                "[%s] status=%s reason=%s",
                clean_cell(result.get("company_name")) or f"row-{index}",
                result.get("status"),
                result.get("reason"),
            )
    else:
        futures: dict[Any, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            for index, row in enumerate(rows, start=1):
                future = executor.submit(process_company, row, args)
                futures[future] = {"row_index": index, "row": row}

            for future in tqdm(as_completed(futures), total=len(futures), desc="Companies", file=sys.stderr):
                meta = futures[future]
                result = future.result()
                result["_row_index"] = meta["row_index"]
                records.append(result)
                LOGGER.info(
                    "[%s] status=%s reason=%s",
                    clean_cell(result.get("company_name")) or f"row-{meta['row_index']}",
                    result.get("status"),
                    result.get("reason"),
                )

    write_manifest(records, output_dir)
    status_counts: dict[str, int] = {}
    company_lists: dict[str, list[str]] = {"downloaded": [], "discover_only": [], "skipped_existing": [], "no_match": [], "failed": []}
    for record in records:
        status = clean_cell(record.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status in company_lists:
            company_lists[status].append(clean_cell(record.get("company_name")))

    LOGGER.info("Wrote manifest to %s", output_dir)
    LOGGER.info(
        "Summary: %s",
        ", ".join(f"{status}={count}" for status, count in sorted(status_counts.items())),
    )
    for status, names in company_lists.items():
        if names:
            LOGGER.info("%s companies: %s", status, ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
