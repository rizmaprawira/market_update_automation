from __future__ import annotations

"""Download conventional life-insurance financial report PDFs.

Usage examples:

    python scripts/download/download_life_insurance.py \
        --year 2026 --month 4 \
        --input link_asuransi_jiwa.xlsx \
        --output-root data

    python scripts/download/download_life_insurance.py \
        --year 2026 --month 4 \
        --input assets/link_asuransi_jiwa.xlsx \
        --output-root data \
        --dry-run --use-browser

If you plan to use the browser fallback, install Chromium once:

    playwright install chromium
"""

import argparse
import csv
import json
import logging
import shutil
import re
import sys
import unicodedata
from collections import Counter, deque
from contextlib import suppress
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4 import FeatureNotFound
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LOGGER = logging.getLogger("download_life_insurance")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATEGORY = "asuransi_jiwa"
DEFAULT_INPUT = "link_asuransi_jiwa.xlsx"
MANIFEST_TIMEZONE = ZoneInfo("Asia/Jakarta")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_DEPTH = 2
MAX_LINKS_PER_PAGE = 24
MAX_CRAWL_PAGES = 40
DEBUG_HTML_DIRNAME = "_debug_html"

MONTH_NAMES: dict[int, list[str]] = {
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

SYARIAH_PATTERNS = (
    r"\bsyariah\b",
    r"\bshariah\b",
    r"\bsharia\b",
    r"\bunit\s+syariah\b",
    r"\busaha\s+syariah\b",
    r"\buus\b",
    r"\bislamic\b",
)

CONVENTIONAL_OVERRIDE_PATTERNS = (
    r"\blaporan\s+keuangan\s+konvensional\b",
    r"\blaporan\s+keuangan\s+perusahaan\b",
    r"\bfinancial\s+statement\b",
    r"\bfinancial\s+report\b",
    r"\bmonthly\s+financial\s+statement\b",
    r"\bpublikasi\s+laporan\s+keuangan\b",
)

FUND_AND_INVESTMENT_PATTERNS = (
    r"\bfund\s+fact\s*sheet\b",
    r"\bfund\s+factsheet\b",
    r"\bfund\s+performance\b",
    r"\bunit[- ]?linked\b",
    r"\bunit\s+link\b",
    r"\binvestment\s+report\b",
    r"\blaporan\s+investasi\b",
    r"\bkinerja\s+dana\b",
    r"\bharga\s+unit\b",
    r"\bnab\b",
    r"\bnet\s+asset\s+value\b",
)

NON_TARGET_REPORT_PATTERNS = (
    r"\bsustainability\b",
    r"\bkeberlanjutan\b",
    r"\besg\b",
    r"\bgov(?:ernance)?\b",
    r"\bintegrated\s+report\b",
    r"\bannual\s+report\b",
    r"\blaporan\s+tahunan\b",
    r"\byearly\s+report\b",
    r"\bcsr\b",
    r"\bgcg\b",
)

UNRELATED_REPORT_PATTERNS = (
    r"\bannual\s+report\b",
    r"\blaporan\s+tahunan\b",
    r"\bsustainability\b",
    r"\bkeberlanjutan\b",
    r"\besg\b",
    r"\bgcg\b",
    r"\bcorporate\s+governance\b",
    r"\btata\s+kelola\b",
    r"\bproduct\s+brochure\b",
    r"\bbrochure\b",
    r"\bcompany\s+profile\b",
    r"\bpress\s+release\b",
    r"\bclaim\s+form\b",
    r"\bformulir\s+klaim\b",
    r"\bpolicy\s+wording\b",
    r"\bpolis\b",
    r"\bbancassurance\b",
)

FUND_REPORT_PATTERNS = FUND_AND_INVESTMENT_PATTERNS + (
    r"\bfund\b",
    r"\bdana\s+investasi\b",
    r"\bproduk\b",
    r"\bproduct\b",
)

REPORT_HINT_PATTERNS = (
    r"\blaporan\s+keuangan\b",
    r"\bfinancial\s+statement\b",
    r"\bfinancial\s+report\b",
    r"\bmonthly\s+financial\s+statement\b",
    r"\bmonthly\s+report\b",
    r"\blaporan\s+bulanan\b",
    r"\bpublikasi\b",
    r"\bpublished\s+report\b",
    r"\breport\b",
    r"\bstatement\b",
    r"\bdownload\b",
    r"\bunduh\b",
)

REPORTISH_PATTERNS = REPORT_HINT_PATTERNS + (
    r"\bpdf\b",
    r"\bfinancial\b",
    r"\blaporan\b",
)

STOPWORDS = {
    "asuransi",
    "insurance",
    "jiwa",
    "pt",
    "persero",
    "tbk",
    "the",
    "and",
    "co",
    "corp",
    "corporation",
    "company",
    "insurance",
    "asuransi",
    "jiwa",
}

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
    "rejected_fund_report_count",
    "candidate_count",
    "http_status",
    "file_size_bytes",
    "timestamp",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download conventional financial report PDFs for Indonesian life insurance companies."
    )
    parser.add_argument("--year", type=positive_int, required=True, help="Target report year.")
    parser.add_argument("--month", type=month_int, required=True, help="Target report month (1-12).")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(DEFAULT_INPUT),
        help="Excel workbook with columns: no | nama perusahaan | link.",
    )
    parser.add_argument("--output-root", type=Path, default=Path("data"), help="Root output folder.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect candidates without writing PDFs.")
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Discover and score candidates without downloading PDFs.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output PDF.")
    parser.add_argument("--timeout", type=positive_int, default=DEFAULT_TIMEOUT, help="Timeout in seconds.")
    parser.add_argument(
        "--max-workers",
        type=positive_int,
        default=DEFAULT_MAX_WORKERS,
        help="Concurrent company workers.",
    )
    parser.add_argument(
        "--max-depth",
        type=positive_int,
        default=DEFAULT_MAX_DEPTH,
        help="Maximum same-domain crawl depth from the provided report page.",
    )
    parser.add_argument(
        "--use-browser",
        action="store_true",
        help="Enable Playwright fallback when HTML parsing is insufficient.",
    )
    parser.add_argument(
        "--debug-html",
        action="store_true",
        help="Save fetched/rendered HTML snapshots for failed companies.",
    )
    args = parser.parse_args(argv)
    if args.discover_only and args.dry_run:
        LOGGER.debug("both --dry-run and --discover-only were supplied; treating as discover-only")
    return args


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - argparse handles invalid input.
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def month_int(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 12:
        raise argparse.ArgumentTypeError("month must be between 1 and 12")
    return parsed


def ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:  # pragma: no cover - defensive.
        pass
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", ascii_fold(clean_text(value))).strip().lower()


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = clean_text(value).lower()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def normalize_month_terms(month: int) -> list[str]:
    terms = list(MONTH_NAMES[month])
    terms.extend([f"{month:02d}", str(month)])
    return unique_preserve_order(terms)


def normalize_target_period(year: int, month: int) -> dict[str, Any]:
    quarter = ((month - 1) // 3) + 1
    quarter_roman = _quarter_roman(quarter)
    month_terms = normalize_month_terms(month)
    exact_terms = [
        f"{month:02d}-{year}",
        f"{month:02d}_{year}",
        f"{year}-{month:02d}",
        f"{year}_{month:02d}",
        f"{year}{month:02d}",
        f"{month:02d}{year}",
        f"{month_terms[0]} {year}",
        f"{year} {month_terms[0]}",
        f"q{quarter} {year}",
        f"quarter {quarter} {year}",
        f"triwulan {quarter_roman} {year}",
    ]
    exact_terms.extend([f"{term} {year}" for term in month_terms if not term.isdigit()])
    exact_terms.extend([f"{year} {term}" for term in month_terms if not term.isdigit()])
    quarter_terms = [
        f"q{quarter}",
        f"quarter {quarter}",
        f"triwulan {quarter}",
        f"triwulan {quarter_roman}",
        f"kuartal {quarter}",
        f"kuartal {quarter_roman}",
    ]
    return {
        "year": year,
        "month": month,
        "month_terms": month_terms,
        "quarter": quarter,
        "quarter_roman": quarter_roman,
        "quarter_terms": unique_preserve_order(quarter_terms),
        "exact_terms": unique_preserve_order(exact_terms),
        "numeric_terms": unique_preserve_order([f"{year}{month:02d}", f"{year}-{month:02d}", f"{month:02d}-{year}"]),
    }


def sanitize_filename(text: str) -> str:
    value = ascii_fold(clean_text(text)).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in STOPWORDS]
    safe = re.sub(r"_+", "_", "_".join(tokens)).strip("_")
    if len(safe) > 120:
        safe = safe[:120].rstrip("_")
    return safe or "company"


def is_syariah_candidate(text: str) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False
    return any(re.search(pattern, blob) for pattern in SYARIAH_PATTERNS)


def is_life_investment_or_fund_report(text: str) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False
    return any(re.search(pattern, blob) for pattern in FUND_REPORT_PATTERNS)


def is_unrelated_report(text: str) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False
    return any(re.search(pattern, blob) for pattern in UNRELATED_REPORT_PATTERNS)


def is_non_company_financial_report(text: str) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False
    return is_life_investment_or_fund_report(blob) or is_unrelated_report(blob)


def _has_report_hint(blob: str) -> bool:
    return any(re.search(pattern, blob) for pattern in REPORT_HINT_PATTERNS)


def _quarter_roman(quarter: int) -> str:
    return {1: "i", 2: "ii", 3: "iii", 4: "iv"}[quarter]


def _quarter_month_ranges(month: int) -> list[tuple[str, str]]:
    return {
        1: [("januari", "maret"), ("january", "march"), ("jan", "mar")],
        2: [("april", "juni"), ("april", "june"), ("apr", "jun")],
        3: [("juli", "september"), ("july", "september"), ("jul", "sep")],
        4: [("oktober", "desember"), ("october", "december"), ("oct", "dec"), ("okt", "des")],
    }[month]


def _period_kind(blob: str, year: int, month: int) -> str:
    period = normalize_target_period(year, month)
    year_text = str(year)
    month_text = f"{month:02d}"
    month_plain = str(month)

    exact_patterns = [
        rf"\b{year_text}\s*[-_/\. ]\s*0?{month_plain}\b",
        rf"\b0?{month_plain}\s*[-_/\. ]\s*{year_text}\b",
        rf"\b{year_text}{month_text}\b",
        rf"\b{month_text}{year_text}\b",
        rf"\b{year_text}[./_-]?{month_text}\b",
        rf"\b{month_text}[./_-]?{year_text}\b",
    ]
    if any(re.search(pattern, blob) for pattern in exact_patterns):
        return "exact_month"

    for term in period["month_terms"]:
        if term.isdigit():
            continue
        if re.search(rf"\b{re.escape(term)}\b", blob) and re.search(rf"\b{year_text}\b", blob):
            return "exact_month"

    if re.search(rf"\b{year_text}\b", blob) and _quarter_match(blob, month):
        return "quarter"

    return "none"


def is_relevant_financial_report(text: str, year: int, month: int) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False
    if is_syariah_candidate(blob):
        return False
    period_kind = _period_kind(blob, year, month)
    strong_conventional = any(
        phrase in blob
        for phrase in (
            "laporan keuangan konvensional",
            "laporan keuangan perusahaan",
            "financial statement",
            "financial report",
            "monthly financial statement",
            "publikasi laporan keuangan",
        )
    )
    if is_life_investment_or_fund_report(blob) or is_unrelated_report(blob):
        if strong_conventional and period_kind == "exact_month":
            return True
        return False
    if not _has_report_hint(blob):
        return False
    if re.search(r"\bannual\s+report\b", blob) or re.search(r"\blaporan\s+tahunan\b", blob):
        return False
    return period_kind in {"exact_month", "quarter"}


def _quarter_match(blob: str, month: int) -> bool:
    quarter = ((month - 1) // 3) + 1
    roman = _quarter_roman(quarter)
    patterns = (
        rf"\bq\s*{quarter}\b",
        rf"\bquarter\s*{quarter}\b",
        rf"\bquarter\s*{roman}\b",
        rf"\btriwulan\s*{quarter}\b",
        rf"\btriwulan\s*{roman}\b",
        rf"\bkuartal\s*{quarter}\b",
        rf"\bkuartal\s*{roman}\b",
    )
    if any(re.search(pattern, blob) for pattern in patterns):
        return True

    for start, end in _quarter_month_ranges(month):
        if re.search(rf"\b{re.escape(start)}\b", blob) and re.search(rf"\b{re.escape(end)}\b", blob):
            return True

    return False


def _candidate_blob(candidate: dict[str, Any], *, include_page_title: bool = True) -> str:
    parts = [
        candidate.get("pdf_url", ""),
        candidate.get("text", ""),
        candidate.get("title", ""),
        candidate.get("context", ""),
    ]
    if include_page_title:
        parts.append(candidate.get("page_title", ""))
    return normalize_text(" ".join(clean_text(part) for part in parts if clean_text(part)))


def _candidate_core_blob(candidate: dict[str, Any]) -> str:
    return _candidate_blob(candidate, include_page_title=False)


def _candidate_is_reportish(blob: str) -> bool:
    return any(re.search(pattern, blob) for pattern in REPORTISH_PATTERNS)


def _element_context(element: Any, own_text: str) -> str:
    for ancestor in element.parents:
        tag_name = getattr(ancestor, "name", None)
        if tag_name not in {"tr", "li", "article", "section", "div", "td", "p"}:
            continue
        try:
            anchor_count = len(ancestor.find_all("a"))
        except Exception:  # pragma: no cover - defensive for malformed markup.
            anchor_count = 0
        if anchor_count > 1:
            continue
        context = clean_text(ancestor.get_text(" ", strip=True))
        if not context:
            continue
        if own_text and context == own_text:
            continue
        return context[:500]
    return ""


def _extract_pdf_urls(value: str) -> list[str]:
    if not value:
        return []
    matches = re.findall(
        r"""(?i)(?:https?://|//|/|\.{1,2}/)[^"'<>\s]+?\.pdf(?:\?[^\s"'<>]*)?""",
        value,
    )
    cleaned: list[str] = []
    for match in matches:
        candidate = unquote(match.replace("\\/", "/").strip().rstrip(".,;)"))
        if candidate:
            cleaned.append(candidate)
    return cleaned


def _canonicalize_url(url: str) -> str:
    parsed = urlparse(clean_text(url))
    if not parsed.scheme and not parsed.netloc and not parsed.path:
        return ""
    return parsed._replace(fragment="").geturl()


def _normalize_netloc(url: str) -> str:
    netloc = urlparse(clean_text(url)).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _same_domain(url_a: str, url_b: str) -> bool:
    netloc_a = _normalize_netloc(url_a)
    netloc_b = _normalize_netloc(url_b)
    return bool(netloc_a and netloc_b and netloc_a == netloc_b)


def _make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def _page_text_excerpt(soup: BeautifulSoup, limit: int = 8000) -> str:
    text = clean_text(soup.get_text(" ", strip=True))
    if len(text) > limit:
        return text[:limit]
    return text


def _normalize_blob(*parts: Any) -> str:
    return normalize_text(" ".join(clean_text(part) for part in parts if clean_text(part)))


def _add_candidate(
    candidates: list[dict[str, Any]],
    seen: set[str],
    *,
    pdf_url: str,
    text: str,
    title: str,
    context: str,
    page_title: str,
    page_text: str,
    source_page_url: str,
    discovered_page_url: str,
    source_http_status: int | None,
    discovery_mode: str,
) -> None:
    resolved = _canonicalize_url(urljoin(source_page_url, pdf_url))
    if not resolved:
        return
    key = resolved.lower()
    if key in seen:
        return

    candidate = {
        "pdf_url": resolved,
        "text": clean_text(text),
        "title": clean_text(title),
        "context": clean_text(context),
        "page_title": clean_text(page_title),
        "page_text": clean_text(page_text),
        "source_page_url": source_page_url,
        "discovered_page_url": discovered_page_url,
        "source_http_status": source_http_status,
        "discovery_mode": discovery_mode,
    }
    blob = _candidate_blob(candidate)
    if not _candidate_is_reportish(blob):
        return

    candidates.append(candidate)
    seen.add(key)


def _collect_candidates_from_html(
    html: str,
    source_page_url: str,
    *,
    source_http_status: int | None,
    discovery_mode: str,
    page_title: str = "",
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - parser fallback.
        soup = BeautifulSoup(html, "html.parser")

    if not page_title:
        page_title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    page_text = clean_text(soup.get_text(" ", strip=True))
    if len(page_text) > 8000:
        page_text = page_text[:8000]

    selectors = (
        "a[href], iframe[src], embed[src], object[data], source[src], "
        "button, [role='button'], summary, [onclick], [data-href], [data-url], [data-link]"
    )
    for element in soup.select(selectors):
        href = clean_text(
            element.get("href")
            or element.get("src")
            or element.get("data")
            or element.get("xlink:href")
            or element.get("data-href")
            or element.get("data-url")
            or element.get("data-link")
            or ""
        )
        if not href:
            attr_values = " ".join(clean_text(value) for value in element.attrs.values() if value)
            extracted_urls = _extract_pdf_urls(attr_values)
            href = extracted_urls[0] if extracted_urls else ""
        if not href or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue

        text = clean_text(element.get_text(" ", strip=True))
        title = clean_text(
            element.get("title")
            or element.get("aria-label")
            or element.get("download")
            or element.get("alt")
            or element.get("value")
        )
        context = _element_context(element, text)
        _add_candidate(
            candidates,
            seen,
            pdf_url=href,
            text=text,
            title=title,
            context=context,
            page_title=page_title,
            page_text=page_text,
            source_page_url=source_page_url,
            discovered_page_url=source_page_url,
            source_http_status=source_http_status,
            discovery_mode=discovery_mode,
        )

        for attr_value in element.attrs.values():
            if not attr_value:
                continue
            if isinstance(attr_value, list):
                attr_value = " ".join(map(str, attr_value))
            for extracted in _extract_pdf_urls(str(attr_value)):
                _add_candidate(
                    candidates,
                    seen,
                    pdf_url=extracted,
                    text=text,
                    title=title,
                    context=context,
                    page_title=page_title,
                    page_text=page_text,
                    source_page_url=source_page_url,
                    discovered_page_url=source_page_url,
                    source_http_status=source_http_status,
                    discovery_mode=discovery_mode,
                )

    for raw_url in _extract_pdf_urls(html):
        _add_candidate(
            candidates,
            seen,
            pdf_url=raw_url,
            text="raw_html",
            title="",
            context="",
            page_title=page_title,
            page_text=page_text,
            source_page_url=source_page_url,
            discovered_page_url=source_page_url,
            source_http_status=source_http_status,
            discovery_mode=discovery_mode,
        )

    return candidates


def _node_binary() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    fallback = Path(sys.executable).resolve().parents[1] / "bin" / "node"
    return str(fallback) if fallback.exists() else None


def _node_modules_root() -> Path | None:
    root = Path(sys.executable).resolve().parents[1] / "lib" / "node_modules"
    return root if root.exists() else None


def _browser_terms(year: int, month: int) -> list[str]:
    period = normalize_target_period(year, month)
    terms = [
        "laporan keuangan",
        "laporan keuangan konvensional",
        "laporan keuangan perusahaan",
        "financial report",
        "financial statement",
        "monthly report",
        "monthly financial statement",
        "laporan bulanan",
        "publikasi",
        "published report",
        "report",
        "investor",
        "keterbukaan informasi",
        "conventional",
        "konvensional",
        "perusahaan",
        "asuransi jiwa",
        "life insurance",
    ]
    terms.extend(period["month_terms"])
    terms.extend(period["exact_terms"])
    terms.extend(period["quarter_terms"])
    return unique_preserve_order(terms)


def _run_playwright_snapshot(source_page_url: str, year: int, month: int, timeout: int) -> dict[str, Any]:
    node = _node_binary()
    if node is None:
        raise RuntimeError("node binary not found for Playwright fallback")

    module_root = _node_modules_root()
    if module_root is None:
        raise RuntimeError("Playwright node modules were not found")

    payload = {
        "url": source_page_url,
        "timeoutMs": timeout * 1000,
        "year": year,
        "month": month,
        "terms": _browser_terms(year, month),
        "userAgent": DEFAULT_USER_AGENT,
        "maxClicks": 20,
    }
    js_script = r"""
const payload = JSON.parse(process.argv[1]);
const { chromium } = require('playwright');

function normalize(value) {
  return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

function visible(element) {
  if (!element) {
    return false;
  }
  const style = window.getComputedStyle(element);
  if (!style || style.visibility === 'hidden' || style.display === 'none') {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function blobFor(element) {
  const parts = [];
  for (const attr of ['innerText', 'textContent']) {
    if (element[attr]) {
      parts.push(element[attr]);
    }
  }
  for (const attr of ['title', 'aria-label', 'href', 'data-href', 'data-url', 'data-link', 'download', 'value']) {
    const value = element.getAttribute && element.getAttribute(attr);
    if (value) {
      parts.push(value);
    }
  }
  return normalize(parts.join(' '));
}

function matches(blob, terms) {
  if (!blob) {
    return false;
  }
  return terms.some((term) => blob.includes(normalize(term)));
}

async function collectSnapshot(page, label) {
  const html = await page.content();
  const title = await page.title().catch(() => '');
  return {
    label,
    url: page.url(),
    title,
    html,
  };
}

async function selectRelevantOptions(page, terms) {
  let changed = false;
  const selects = await page.$$('select');
  for (const select of selects) {
    const options = await select.$$('option');
    let chosenIndex = -1;
    let fallbackIndex = -1;
    for (let index = 0; index < options.length; index += 1) {
      const option = options[index];
      const label = normalize(
        await option.innerText().catch(() => '')
          || await option.getAttribute('label').catch(() => '')
          || await option.getAttribute('value').catch(() => '')
      );
      if (!label) {
        continue;
      }
      if (matches(label, terms)) {
        chosenIndex = index;
        break;
      }
      if (fallbackIndex < 0 && (
        label.includes(payload.year.toString()) ||
        label.includes(payload.year.toString().slice(2)) ||
        label.includes('q1') ||
        label.includes('quarter 1') ||
        label.includes('triwulan i')
      )) {
        fallbackIndex = index;
      }
    }
    const indexToChoose = chosenIndex >= 0 ? chosenIndex : fallbackIndex;
    if (indexToChoose >= 0) {
      try {
        await select.selectOption({ index: indexToChoose });
        await select.dispatchEvent('change').catch(() => {});
        await select.dispatchEvent('input').catch(() => {});
        await page.waitForTimeout(500);
        changed = true;
      } catch (error) {
        // Ignore select failures and continue with other controls.
      }
    }
  }
  return changed;
}

async function clickRelevantControls(page, terms, maxClicks) {
  let clicked = 0;
  let changed = false;
  const elements = await page.$$('button, a[href], [role="button"], summary, [aria-expanded], [data-href], [data-url], [data-link]');
  for (const element of elements) {
    if (clicked >= maxClicks) {
      break;
    }
    try {
      if (!(await element.isVisible())) {
        continue;
      }
    } catch (error) {
      continue;
    }
    const blob = normalize(
      await element.evaluate((node) => {
        const parts = [];
        if (node.innerText) {
          parts.push(node.innerText);
        }
        if (node.textContent) {
          parts.push(node.textContent);
        }
        for (const attr of ['title', 'aria-label', 'href', 'data-href', 'data-url', 'data-link', 'download', 'value']) {
          const value = node.getAttribute ? node.getAttribute(attr) : '';
          if (value) {
            parts.push(value);
          }
        }
        return parts.join(' ');
      }).catch(() => '')
    );
    if (!matches(blob, terms)) {
      continue;
    }
    try {
      await element.click({ timeout: Math.min(payload.timeoutMs, 3000) });
      clicked += 1;
      changed = true;
      await page.waitForTimeout(700);
    } catch (error) {
      continue;
    }
  }
  return changed;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: payload.userAgent,
    acceptDownloads: false,
    ignoreHTTPSErrors: true,
  });
  context.setDefaultTimeout(payload.timeoutMs);
  const page = await context.newPage();
  const snapshots = [];
  try {
    await page.goto(payload.url, { waitUntil: 'domcontentloaded', timeout: payload.timeoutMs });
    await page.waitForLoadState('networkidle', { timeout: Math.min(payload.timeoutMs, 10_000) }).catch(() => {});
    snapshots.push(await collectSnapshot(page, 'initial'));

    for (let round = 0; round < 3; round += 1) {
      let changed = false;
      changed = await selectRelevantOptions(page, payload.terms) || changed;
      changed = await clickRelevantControls(page, payload.terms, payload.maxClicks) || changed;
      if (!changed) {
        break;
      }
      await page.waitForTimeout(800);
      await page.waitForLoadState('networkidle', { timeout: Math.min(payload.timeoutMs, 10_000) }).catch(() => {});
      snapshots.push(await collectSnapshot(page, `round-${round + 1}`));
    }

    snapshots.push(await collectSnapshot(page, 'final'));
    process.stdout.write(JSON.stringify({
      ok: true,
      final_url: page.url(),
      title: await page.title().catch(() => ''),
      snapshots,
    }));
  } finally {
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }
})().catch((error) => {
  process.stderr.write(String(error && error.stack ? error.stack : error));
  process.exit(1);
});
"""

    env = os.environ.copy()
    current_node_path = env.get("NODE_PATH", "")
    node_module_str = str(module_root)
    env["NODE_PATH"] = node_module_str if not current_node_path else f"{node_module_str}:{current_node_path}"
    result = subprocess.run(
        [node, "-e", js_script, json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=max(60, timeout * 3),
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Playwright browser render failed for {source_page_url}: {summarize_exception(result.stderr or result.stdout)}"
        )
    data = json.loads(result.stdout)
    snapshots = data.get("snapshots") or []
    return {
        "final_url": clean_text(data.get("final_url", source_page_url)) or source_page_url,
        "title": clean_text(data.get("title", "")),
        "snapshots": snapshots,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _browser_candidates(source_page_url: str, timeout: int) -> list[dict[str, Any]]:
    raise RuntimeError("_browser_candidates is deprecated; use extract_candidates_browser(source_url, year, month)")


def _link_relevance_score(blob: str, year: int, month: int) -> int:
    if not blob:
        return 0

    score = 0
    period_kind = _period_kind(blob, year, month)

    strong_terms = (
        "laporan keuangan konvensional",
        "laporan keuangan perusahaan",
        "financial report",
        "financial statement",
        "laporan keuangan",
        "publikasi laporan keuangan",
        "monthly financial statement",
        "monthly report",
        "laporan bulanan",
    )
    soft_terms = (
        "publikasi",
        "report",
        "statement",
        "financial",
        "investor",
        "keterbukaan informasi",
        "financial report",
        "financial statement",
        "financial reports",
    )
    follow_terms = (
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
        "financial",
        "statement",
        "download",
        "unduh",
        "reporting",
    )

    if any(term in blob for term in strong_terms):
        score += 60
    if any(term in blob for term in soft_terms):
        score += 20
    if any(term in blob for term in follow_terms):
        score += 10
    if period_kind == "exact_month":
        score += 40
    elif period_kind == "quarter":
        score += 20
    if re.search(r"\b20\d{2}\b", blob):
        score += 5
    if any(term in blob for term in ("pdf", "download", "unduh")):
        score += 5
    if is_syariah_candidate(blob):
        score -= 200
    if is_life_investment_or_fund_report(blob) and not any(term in blob for term in strong_terms):
        score -= 80
    if is_unrelated_report(blob):
        score -= 40
    return score


def _extract_related_links_from_html(
    html: str,
    source_page_url: str,
    year: int,
    month: int,
    *,
    source_http_status: int | None,
    discovery_mode: str,
    page_title: str = "",
) -> list[dict[str, Any]]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - parser fallback.
        soup = BeautifulSoup(html, "html.parser")

    page_text = _page_text_excerpt(soup)
    if not page_title:
        page_title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")

    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    selectors = "a[href], button, [role='button'], summary, [onclick], [data-href], [data-url], [data-link]"
    for element in soup.select(selectors):
        href = clean_text(
            element.get("href")
            or element.get("data-href")
            or element.get("data-url")
            or element.get("data-link")
            or element.get("xlink:href")
            or ""
        )
        if not href:
            attr_values = " ".join(clean_text(value) for value in element.attrs.values() if value)
            pdf_urls = _extract_pdf_urls(attr_values)
            href = pdf_urls[0] if pdf_urls else ""
        if not href:
            continue
        if href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue

        resolved = _canonicalize_url(urljoin(source_page_url, href))
        if not resolved or not _same_domain(resolved, source_page_url) or _looks_like_pdf_source(resolved):
            continue

        text = clean_text(element.get_text(" ", strip=True))
        title = clean_text(
            element.get("title")
            or element.get("aria-label")
            or element.get("download")
            or element.get("alt")
            or element.get("value")
        )
        context = _element_context(element, text)
        blob = _normalize_blob(resolved, text, title, context, page_title, page_text)
        score = _link_relevance_score(blob, year, month)
        if score <= 0:
            continue

        key = resolved.lower()
        if key in seen:
            continue
        seen.add(key)
        links.append(
            {
                "url": resolved,
                "text": text,
                "title": title,
                "context": context,
                "page_title": page_title,
                "page_text": page_text,
                "source_page_url": source_page_url,
                "source_http_status": source_http_status,
                "discovery_mode": discovery_mode,
                "score": score,
            }
        )

    links.sort(key=lambda item: (-int(item.get("score") or 0), clean_text(item.get("url", "")).lower()))
    return links[:MAX_LINKS_PER_PAGE]


def extract_candidates_static(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    timeout = int(getattr(session, "_timeout", DEFAULT_TIMEOUT))
    response = _request_page(session, source_url, timeout)
    page_url = clean_text(response.url or source_url)
    content_bytes = response.content[:8] if response.content else b""
    if is_valid_pdf_response(response, content_bytes) or _looks_like_pdf_source(page_url):
        return [
            {
                "pdf_url": _canonicalize_url(page_url or source_url),
                "text": "",
                "title": "",
                "context": "",
                "page_title": "",
                "page_text": "",
                "source_page_url": page_url or source_url,
                "discovered_page_url": page_url or source_url,
                "source_http_status": response.status_code,
                "discovery_mode": "static",
            }
        ]

    page_title = ""
    try:
        soup = _make_soup(response.text)
        page_title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    except Exception:
        page_title = ""

    return _collect_candidates_from_html(
        response.text,
        page_url or source_url,
        source_http_status=response.status_code,
        discovery_mode="static",
        page_title=page_title,
    )


def _browser_candidates_with_snapshots(
    source_url: str,
    year: int,
    month: int,
    timeout: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rendered = _run_playwright_snapshot(source_url, year, month, timeout)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for snapshot in rendered.get("snapshots", []):
        html = clean_text(snapshot.get("html", ""))
        if not html:
            continue
        page_url = clean_text(snapshot.get("url") or rendered.get("final_url") or source_url) or source_url
        page_title = clean_text(snapshot.get("title") or rendered.get("title") or "")
        snapshot_candidates = _collect_candidates_from_html(
            html,
            page_url,
            source_http_status=200,
            discovery_mode="browser",
            page_title=page_title,
        )
        for candidate in snapshot_candidates:
            key = clean_text(candidate.get("pdf_url", "")).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    return candidates, rendered.get("snapshots", [])


def extract_candidates_browser(source_url: str, year: int, month: int) -> list[dict[str, Any]]:
    try:
        candidates, _ = _browser_candidates_with_snapshots(source_url, year, month, DEFAULT_TIMEOUT)
        return candidates
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("browser extraction failed for %s: %s", source_url, summarize_exception(exc))
        return []


def crawl_related_pages(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    max_depth: int = 2,
) -> list[dict[str, Any]]:
    timeout = int(getattr(session, "_timeout", DEFAULT_TIMEOUT))
    use_browser = bool(getattr(session, "_use_browser", False))
    source_page_url = _canonicalize_url(source_url) or clean_text(source_url)

    state: dict[str, Any] = {
        "source_page_url": source_page_url,
        "pages": [],
        "visited_pages": [],
        "candidates": [],
        "candidate_urls_seen": set(),
        "candidate_count": 0,
        "browser_attempted": False,
        "browser_used": False,
        "browser_errors": [],
        "static_errors": [],
        "depth_limit": max_depth,
        "discovery_methods": [],
    }

    queue: deque[tuple[str, int]] = deque([(source_page_url, 0)])
    visited: set[str] = set()
    combined_candidates: list[dict[str, Any]] = []
    combined_seen: set[str] = set()

    while queue and len(visited) < MAX_CRAWL_PAGES:
        page_url, depth = queue.popleft()
        if not page_url:
            continue
        normalized_page_url = _canonicalize_url(page_url) or page_url
        if normalized_page_url in visited:
            continue
        visited.add(normalized_page_url)
        page_record: dict[str, Any] = {
            "page_url": normalized_page_url,
            "depth": depth,
            "static_status": None,
            "browser_status": None,
            "static_candidates": 0,
            "browser_candidates": 0,
            "related_links": [],
            "html_static": "",
            "html_browser": "",
            "page_title": "",
            "page_text": "",
            "error": "",
        }

        static_html = ""
        static_status = None
        static_title = ""
        static_candidates: list[dict[str, Any]] = []
        static_links: list[dict[str, Any]] = []
        static_error: Exception | None = None

        try:
            response = _request_page(session, normalized_page_url, timeout)
            static_status = response.status_code
            static_html = response.text or ""
            soup = _make_soup(static_html)
            static_title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
            page_record["page_text"] = _page_text_excerpt(soup)
            static_candidates = _collect_candidates_from_html(
                static_html,
                normalized_page_url,
                source_http_status=static_status,
                discovery_mode="static" if depth == 0 else "crawled_static",
                page_title=static_title,
            )
            static_links = _extract_related_links_from_html(
                static_html,
                normalized_page_url,
                year,
                month,
                source_http_status=static_status,
                discovery_mode="static" if depth == 0 else "crawled_static",
                page_title=static_title,
            )
            page_record["static_status"] = static_status
            page_record["html_static"] = static_html
            page_record["page_title"] = static_title
        except Exception as exc:  # noqa: BLE001
            static_error = exc
            page_record["error"] = summarize_exception(exc)
            state["static_errors"].append(
                {
                    "page_url": normalized_page_url,
                    "depth": depth,
                    "error": page_record["error"],
                }
            )

        page_candidates: list[dict[str, Any]] = list(static_candidates)
        page_links: list[dict[str, Any]] = list(static_links)
        browser_candidates: list[dict[str, Any]] = []
        has_exact_static = any(
            is_relevant_financial_report(_candidate_core_blob(candidate), year, month)
            and _period_kind(_candidate_core_blob(candidate), year, month) == "exact_month"
            for candidate in static_candidates
        )
        needs_browser = use_browser and (
            not static_candidates
            or not any(is_relevant_financial_report(_candidate_blob(candidate), year, month) for candidate in static_candidates)
            or static_error is not None
        )

        if needs_browser:
            state["browser_attempted"] = True
            try:
                browser_candidates, snapshots = _browser_candidates_with_snapshots(normalized_page_url, year, month, timeout)
                state["browser_used"] = True
                page_record["browser_status"] = 200
                page_record["browser_candidates"] = len(browser_candidates)
                for snapshot in snapshots:
                    snapshot_html = clean_text(snapshot.get("html", ""))
                    if not snapshot_html:
                        continue
                    snapshot_url = clean_text(snapshot.get("url") or normalized_page_url) or normalized_page_url
                    snapshot_title = clean_text(snapshot.get("title") or "")
                    snapshot_links = _extract_related_links_from_html(
                        snapshot_html,
                        snapshot_url,
                        year,
                        month,
                        source_http_status=200,
                        discovery_mode="browser" if depth == 0 else "crawled_browser",
                        page_title=snapshot_title,
                    )
                    page_links.extend(snapshot_links)
                    if not page_record["html_browser"]:
                        page_record["html_browser"] = snapshot_html
            except Exception as exc:  # noqa: BLE001
                state["browser_errors"].append(
                    {
                        "page_url": normalized_page_url,
                        "depth": depth,
                        "error": summarize_exception(exc),
                    }
                )
                page_record["error"] = summarize_exception(exc)
                browser_candidates = []

            adjusted_browser_candidates: list[dict[str, Any]] = []
            for candidate in browser_candidates:
                candidate = dict(candidate)
                candidate["discovery_mode"] = "browser" if depth == 0 else "crawled_browser"
                candidate["discovered_page_url"] = normalized_page_url
                adjusted_browser_candidates.append(candidate)
            page_candidates.extend(adjusted_browser_candidates)

        unique_candidates_for_page: list[dict[str, Any]] = []
        for candidate in page_candidates:
            candidate = dict(candidate)
            candidate.setdefault("source_page_url", source_page_url)
            candidate["discovered_page_url"] = normalized_page_url
            key = clean_text(candidate.get("pdf_url", "")).lower()
            if not key or key in combined_seen:
                continue
            combined_seen.add(key)
            unique_candidates_for_page.append(candidate)
            combined_candidates.append(candidate)

        page_record["static_candidates"] = len(static_candidates)
        page_record["candidate_count"] = len(unique_candidates_for_page)
        page_record["related_links"] = page_links
        page_record["browser_snapshots"] = len(page_links)
        page_record["candidate_urls"] = [candidate.get("pdf_url", "") for candidate in unique_candidates_for_page]
        state["pages"].append(page_record)
        state["visited_pages"].append(normalized_page_url)
        state["candidate_count"] = len(combined_candidates)
        state["candidates"] = combined_candidates
        state["candidate_urls_seen"] = combined_seen

        if depth < max_depth:
            follow_links = sorted(
                page_links,
                key=lambda item: (-int(item.get("score") or 0), clean_text(item.get("url", "")).lower()),
            )
            for link in follow_links[:MAX_LINKS_PER_PAGE]:
                next_url = clean_text(link.get("url", ""))
                if not next_url or next_url in visited:
                    continue
                queue.append((next_url, depth + 1))

    session._discovery_state = state  # type: ignore[attr-defined]
    return combined_candidates


def _looks_like_pdf_source(url: str) -> bool:
    lowered = normalize_text(url)
    return lowered.endswith(".pdf") or ".pdf?" in lowered or ".pdf#" in lowered


def is_valid_pdf_response(response: requests.Response, content_bytes: bytes) -> bool:
    content_type = clean_text(response.headers.get("Content-Type", "")).lower()
    disposition = clean_text(response.headers.get("Content-Disposition", "")).lower()
    final_url = clean_text(response.url).lower()
    return (
        "application/pdf" in content_type
        or "pdf" in disposition
        or final_url.endswith(".pdf")
        or ".pdf?" in final_url
        or content_bytes.startswith(b"%PDF")
    )


def _request_page(session: requests.Session, source_url: str, timeout: int) -> requests.Response:
    response = session.get(
        source_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout=timeout,
    )
    return response


def _first_non_none(values: list[Any]) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _exception_http_status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
    return None


def extract_pdf_candidates(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    use_browser: bool = False,
) -> list[dict[str, Any]]:
    session._use_browser = use_browser  # type: ignore[attr-defined]
    session._timeout = int(getattr(session, "_timeout", DEFAULT_TIMEOUT))  # type: ignore[attr-defined]
    return crawl_related_pages(session, source_url, year, month, max_depth=1)


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = clean_text(candidate.get("pdf_url", "")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _topic_rank(blob: str) -> int:
    strong = (
        "laporan keuangan konvensional",
        "laporan keuangan perusahaan",
        "financial report",
        "financial statement",
        "monthly financial statement",
        "publikasi laporan keuangan",
    )
    medium = (
        "laporan keuangan",
        "financial report",
        "financial statement",
        "monthly report",
        "laporan bulanan",
        "published report",
        "report",
        "statement",
        "publikasi",
    )
    if any(term in blob for term in strong):
        return 0
    if any(term in blob for term in medium):
        return 1
    return 2


def _url_rank(pdf_url: str, year: int, month: int) -> int:
    url_blob = normalize_text(unquote(pdf_url))
    period = _period_kind(url_blob, year, month)
    if period == "exact_month":
        return 0
    if period == "quarter":
        return 1
    if any(keyword in url_blob for keyword in ("report", "laporan", "financial", "statement", "publikasi")):
        return 2
    return 3


def score_candidate(candidate: dict[str, Any], year: int, month: int) -> int:
    blob = _candidate_core_blob(candidate)
    if not blob:
        return -1000
    if is_syariah_candidate(blob):
        return -10_000

    period_kind = _period_kind(blob, year, month)
    exact_month = period_kind == "exact_month"
    quarter = period_kind == "quarter"
    strong = _topic_rank(blob) == 0
    url = clean_text(candidate.get("pdf_url", ""))
    url_blob = normalize_text(unquote(url))
    has_period_url = _url_rank(url, year, month) == 0
    has_year = str(year) in blob or str(year) in url_blob
    has_month_terms = any(term in blob or term in url_blob for term in normalize_month_terms(month))

    score = 0
    if exact_month:
        score += 220
    elif quarter:
        score += 120
    else:
        score += 20

    if strong:
        score += 80
    elif _has_report_hint(blob):
        score += 35

    if has_period_url:
        score += 45
    elif has_year:
        score += 15

    if has_month_terms:
        score += 20

    discovery_mode = clean_text(candidate.get("discovery_mode", "")).lower()
    if discovery_mode in {"static", "browser", "manual_fallback"}:
        score += 12
    elif discovery_mode.startswith("crawled_"):
        score += 6

    if candidate.get("discovered_page_url") and clean_text(candidate.get("discovered_page_url", "")) != clean_text(
        candidate.get("source_page_url", "")
    ):
        score += 8

    if is_life_investment_or_fund_report(blob):
        if strong and exact_month:
            score -= 10
        else:
            score -= 120
    if is_unrelated_report(blob):
        if strong and exact_month:
            score -= 8
        else:
            score -= 90

    if "annual report" in blob or "laporan tahunan" in blob:
        score -= 100

    return score


def _selection_reason(candidate: dict[str, Any], year: int, month: int) -> str:
    blob = _candidate_core_blob(candidate)
    parts: list[str] = []
    period = _period_kind(blob, year, month)
    if period == "exact_month":
        parts.append("exact month match")
    elif period == "quarter":
        parts.append("quarter fallback")
    if _topic_rank(blob) == 0:
        parts.append("strong conventional financial report wording")
    elif _has_report_hint(blob):
        parts.append("report wording")
    if _url_rank(clean_text(candidate.get("pdf_url", "")), year, month) == 0:
        parts.append("url matches period")
    discovery_mode = clean_text(candidate.get("discovery_mode", ""))
    if discovery_mode:
        parts.append(f"{discovery_mode} discovery")
    return ", ".join(parts)


def choose_best_candidate(candidates: list[dict[str, Any]], year: int, month: int) -> dict[str, Any] | None:
    ranked: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for candidate in candidates:
        if not is_relevant_financial_report(_candidate_core_blob(candidate), year, month):
            continue
        score = score_candidate(candidate, year, month)
        selected = dict(candidate)
        selected["score"] = score
        selected["selection_reason"] = _selection_reason(candidate, year, month)
        period_rank = 0 if _period_kind(_candidate_core_blob(candidate), year, month) == "exact_month" else 1
        discovery_rank = 0 if clean_text(candidate.get("discovery_mode", "")).lower() in {"static", "browser", "manual_fallback"} else 1
        ranked.append(
            (
                -score,
                period_rank,
                discovery_rank,
                clean_text(candidate.get("pdf_url", "")).lower(),
                selected,
            )
        )

    if not ranked:
        return None

    _, _, _, _, best = min(ranked)
    return best


def _candidate_rejection_bucket(candidate: dict[str, Any], year: int, month: int) -> str:
    blob = _candidate_core_blob(candidate)
    if is_syariah_candidate(blob):
        return "syariah"
    if is_life_investment_or_fund_report(blob):
        if _topic_rank(blob) == 0 and _period_kind(blob, year, month) == "exact_month":
            return "keep"
        return "fund"
    if is_unrelated_report(blob):
        if _topic_rank(blob) == 0 and _period_kind(blob, year, month) == "exact_month":
            return "keep"
        return "unrelated"
    if is_relevant_financial_report(blob, year, month):
        return "keep"
    return "other"


def _build_output_path(output_root: Path, year: int, month: int, company_name: str) -> Path:
    safe_company_name = sanitize_filename(company_name)
    return (
        output_root
        / f"{year:04d}-{month:02d}"
        / "raw_pdf"
        / CATEGORY
        / safe_company_name
        / f"{safe_company_name}_{year:04d}_{month:02d}.pdf"
    )


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
            "reason": "output file already exists",
            "http_status": None,
            "file_size_bytes": output_path.stat().st_size,
            "pdf_url": pdf_url,
            "output_path": str(output_path),
        }

    tmp_path = output_path.with_suffix(output_path.suffix + ".part")
    first_bytes = b""
    response: requests.Response | None = None

    try:
        response = session.get(
            pdf_url,
            headers={
                "Accept": "application/pdf,*/*;q=0.8",
            },
            timeout=timeout,
            stream=True,
        )
        response.raise_for_status()

        buffered = bytearray()
        with tmp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                if not first_bytes:
                    first_bytes = chunk[:8]
                if len(buffered) < 4096:
                    buffered.extend(chunk[:4096 - len(buffered)])
                handle.write(chunk)

        if not is_valid_pdf_response(response, bytes(buffered or first_bytes)) and not first_bytes.startswith(b"%PDF"):
            raise ValueError(f"response did not look like a PDF: {pdf_url}")

        tmp_path.replace(output_path)
        return {
            "status": "downloaded",
            "reason": "downloaded",
            "http_status": response.status_code,
            "file_size_bytes": output_path.stat().st_size,
            "pdf_url": pdf_url,
            "output_path": str(output_path),
        }
    except Exception:
        with suppress(Exception):
            tmp_path.unlink(missing_ok=True)
        raise
    finally:
        if response is not None:
            response.close()


def _resolve_input_path(input_path: Path) -> Path:
    candidates = [input_path.expanduser()]
    if not input_path.is_absolute():
        candidates.append(PROJECT_ROOT / input_path)
        candidates.append(PROJECT_ROOT / "assets" / input_path.name)
        candidates.append(PROJECT_ROOT / "assets" / input_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return input_path


def _load_workbook_rows(input_path: Path) -> list[dict[str, Any]]:
    frame = pd.read_excel(input_path, engine="openpyxl")
    normalized_columns = {str(column).strip().lower(): column for column in frame.columns}
    required = {"nama perusahaan", "link"}
    missing = required - set(normalized_columns)
    if missing:
        raise ValueError(f"missing required columns in workbook: {', '.join(sorted(missing))}")

    rows: list[dict[str, Any]] = []
    for index, record in frame.iterrows():
        company_name = clean_text(record[normalized_columns["nama perusahaan"]])
        source_page_url = clean_text(record[normalized_columns["link"]])
        if not company_name and not source_page_url:
            continue
        rows.append(
            {
                "row_index": int(index) + 2,
                "company_name": company_name,
                "source_page_url": source_page_url,
            }
        )
    return rows


def _manifest_row(record: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in MANIFEST_FIELDS:
        value = record.get(field, "")
        row[field] = "" if value is None else value
    return row


def write_manifest(records: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "download_manifest.csv"
    json_path = output_dir / "download_manifest.json"

    manifest_rows = [_manifest_row(record) for record in records]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest_rows, handle, ensure_ascii=False, indent=2)

    LOGGER.info("wrote manifest: %s", csv_path)
    LOGGER.info("wrote manifest: %s", json_path)


def summarize_exception(exc: Exception | str, limit: int = 240) -> str:
    text = clean_text(str(exc).splitlines()[0] if str(exc) else exc)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _build_session(timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.5,
        allowed_methods=frozenset({"GET", "HEAD"}),
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session._timeout = timeout  # type: ignore[attr-defined]
    return session


def _manifest_timestamp() -> str:
    return datetime.now(MANIFEST_TIMEZONE).isoformat(timespec="seconds")


def _candidate_count_summary(candidates: list[dict[str, Any]], year: int, month: int) -> Counter[str]:
    summary: Counter[str] = Counter()
    for candidate in candidates:
        bucket = _candidate_rejection_bucket(candidate, year, month)
        summary[bucket] += 1
    return summary


def _best_discovery_method(candidates: list[dict[str, Any]], state: dict[str, Any] | None = None) -> str:
    methods = [clean_text(candidate.get("discovery_mode", "")).lower() for candidate in candidates if candidate.get("discovery_mode")]
    for preferred in ("manual_fallback", "crawled_browser", "browser", "crawled_static", "static"):
        if preferred in methods:
            return preferred
    if state:
        if state.get("browser_used"):
            return "crawled_browser" if any(page.get("depth", 0) > 0 for page in state.get("pages", [])) else "browser"
        if any(page.get("depth", 0) > 0 for page in state.get("pages", [])):
            return "crawled_static"
    return "static"


def _save_debug_html(
    debug_dir: Path,
    company_slug: str,
    source_page_url: str,
    selected_url: str,
    candidates: list[dict[str, Any]],
    discovery_state: dict[str, Any] | None,
    reason: str,
) -> None:
    if discovery_state is None:
        return
    company_dir = debug_dir / company_slug
    company_dir.mkdir(parents=True, exist_ok=True)
    summary_path = company_dir / "summary.json"
    summary_payload = {
        "source_page_url": source_page_url,
        "selected_url": selected_url,
        "reason": reason,
        "candidate_count": len(candidates),
        "pages": [
            {
                "page_url": page.get("page_url"),
                "depth": page.get("depth"),
                "static_status": page.get("static_status"),
                "browser_status": page.get("browser_status"),
                "candidate_count": page.get("candidate_count"),
                "related_links": [link.get("url") for link in page.get("related_links", [])],
                "error": page.get("error"),
            }
            for page in discovery_state.get("pages", [])
        ],
    }
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, ensure_ascii=False, indent=2)

    for index, page in enumerate(discovery_state.get("pages", []), start=1):
        depth = page.get("depth", 0)
        page_slug = f"{index:02d}_depth{depth}_{sanitize_filename(page.get('page_url', f'page_{index}'))}"
        static_html = clean_text(page.get("html_static", ""))
        if static_html:
            (company_dir / f"{page_slug}_static.html").write_text(static_html, encoding="utf-8")
        browser_html = clean_text(page.get("html_browser", ""))
        if browser_html:
            (company_dir / f"{page_slug}_browser.html").write_text(browser_html, encoding="utf-8")


def _process_company_impl(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    company_name = clean_text(row.get("company_name"))
    source_page_url = clean_text(row.get("source_page_url"))
    output_path = _build_output_path(args.output_root, args.year, args.month, company_name or f"row_{row['row_index']}")
    timestamp = _manifest_timestamp()

    base_record = {
        "row_index": row.get("row_index"),
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
        "score": None,
        "rejected_syariah_count": 0,
        "rejected_unrelated_count": 0,
        "rejected_fund_report_count": 0,
        "candidate_count": 0,
        "http_status": None,
        "file_size_bytes": None,
        "timestamp": timestamp,
    }

    if not company_name:
        base_record["reason"] = "missing company name"
        return base_record
    if not source_page_url:
        base_record["reason"] = "missing source page URL"
        return base_record
    if not source_page_url.lower().startswith(("http://", "https://")):
        base_record["reason"] = "source page URL must start with http:// or https://"
        return base_record

    if output_path.exists() and not args.force and not (args.discover_only or args.dry_run):
        base_record["status"] = "skipped_existing"
        base_record["reason"] = "output file already exists"
        base_record["file_size_bytes"] = output_path.stat().st_size
        LOGGER.info("[%s] %s -> skipped_existing", row.get("row_index"), company_name)
        return base_record

    LOGGER.info("[%s] starting %s", row.get("row_index"), company_name)
    try:
        with _build_session(args.timeout) as session:
            session._use_browser = args.use_browser  # type: ignore[attr-defined]
            session._debug_html = args.debug_html  # type: ignore[attr-defined]
            session._output_root = args.output_root  # type: ignore[attr-defined]

            candidates = crawl_related_pages(session, source_page_url, args.year, args.month, max_depth=args.max_depth)
            discovery_state = getattr(session, "_discovery_state", {})
            base_record["candidate_count"] = len(candidates)
            counts = _candidate_count_summary(candidates, args.year, args.month)
            base_record["rejected_syariah_count"] = counts.get("syariah", 0)
            base_record["rejected_unrelated_count"] = counts.get("unrelated", 0)
            base_record["rejected_fund_report_count"] = counts.get("fund", 0)
            base_record["http_status"] = _first_non_none(
                [candidate.get("source_http_status") for candidate in candidates] + [page.get("static_status") for page in discovery_state.get("pages", [])]
            )

            if not candidates:
                base_record["status"] = "no_match"
                base_record["reason"] = "no candidate PDFs were discovered after static, browser, and crawl attempts"
                base_record["discovery_method"] = _best_discovery_method(candidates, discovery_state)
                if args.debug_html:
                    debug_dir = args.output_root / f"{args.year:04d}-{args.month:02d}" / "raw_pdf" / CATEGORY / DEBUG_HTML_DIRNAME
                    _save_debug_html(debug_dir, sanitize_filename(company_name), source_page_url, "", candidates, discovery_state, base_record["reason"])
                return base_record

            selected = choose_best_candidate(candidates, args.year, args.month)
            if selected is None:
                counts_reason = []
                if counts.get("syariah", 0):
                    counts_reason.append("syariah/sharia/UUS")
                if counts.get("fund", 0):
                    counts_reason.append("fund/unit-link/investment")
                if counts.get("unrelated", 0):
                    counts_reason.append("unrelated reports")
                if counts_reason:
                    reason = "only " + ", ".join(counts_reason) + " candidates were discovered"
                else:
                    reason = "no conventional financial report matched the requested period"
                base_record["status"] = "no_match"
                base_record["reason"] = reason
                base_record["discovery_method"] = _best_discovery_method(candidates, discovery_state)
                if args.debug_html:
                    debug_dir = args.output_root / f"{args.year:04d}-{args.month:02d}" / "raw_pdf" / CATEGORY / DEBUG_HTML_DIRNAME
                    _save_debug_html(debug_dir, sanitize_filename(company_name), source_page_url, "", candidates, discovery_state, reason)
                return base_record

            base_record["discovered_page_url"] = clean_text(selected.get("discovered_page_url") or selected.get("source_page_url"))
            base_record["pdf_url"] = clean_text(selected.get("pdf_url", ""))
            base_record["score"] = selected.get("score")
            base_record["discovery_method"] = clean_text(selected.get("discovery_mode", "")) or _best_discovery_method(candidates, discovery_state)
            selected_reason = selected.get("selection_reason", "selected candidate")

            if args.discover_only or args.dry_run:
                base_record["status"] = "discover_only"
                base_record["reason"] = f"discover-only: {selected_reason}"
                if args.debug_html:
                    debug_dir = args.output_root / f"{args.year:04d}-{args.month:02d}" / "raw_pdf" / CATEGORY / DEBUG_HTML_DIRNAME
                    _save_debug_html(
                        debug_dir,
                        sanitize_filename(company_name),
                        source_page_url,
                        base_record["discovered_page_url"],
                        candidates,
                        discovery_state,
                        base_record["reason"],
                    )
                LOGGER.info("[%s] discover-only selected %s", row.get("row_index"), base_record["pdf_url"])
                return base_record

            session.headers["Referer"] = source_page_url
            ranked_candidates = sorted(
                [
                    candidate
                    for candidate in candidates
                    if is_relevant_financial_report(_candidate_core_blob(candidate), args.year, args.month)
                ],
                key=lambda candidate: (-score_candidate(candidate, args.year, args.month), clean_text(candidate.get("pdf_url", "")).lower()),
            )
            last_error: Exception | None = None
            for candidate in ranked_candidates:
                try:
                    download_result = download_pdf(
                        session,
                        candidate["pdf_url"],
                        output_path,
                        args.timeout,
                        force=args.force,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    LOGGER.warning(
                        "[%s] candidate failed for %s: %s",
                        row.get("row_index"),
                        candidate.get("pdf_url"),
                        summarize_exception(exc),
                    )
                    continue

                base_record["status"] = download_result.get("status", "downloaded")
                base_record["reason"] = candidate.get("selection_reason", selected_reason)
                base_record["pdf_url"] = candidate.get("pdf_url", "")
                base_record["discovered_page_url"] = clean_text(candidate.get("discovered_page_url") or candidate.get("source_page_url"))
                base_record["score"] = score_candidate(candidate, args.year, args.month)
                base_record["discovery_method"] = clean_text(candidate.get("discovery_mode", "")) or base_record["discovery_method"]
                base_record["http_status"] = download_result.get("http_status", candidate.get("source_http_status"))
                base_record["file_size_bytes"] = download_result.get("file_size_bytes")
                LOGGER.info("[%s] %s -> %s", row.get("row_index"), company_name, base_record["status"])
                if args.debug_html and base_record["status"] in {"failed", "no_match"}:
                    debug_dir = args.output_root / f"{args.year:04d}-{args.month:02d}" / "raw_pdf" / CATEGORY / DEBUG_HTML_DIRNAME
                    _save_debug_html(
                        debug_dir,
                        sanitize_filename(company_name),
                        source_page_url,
                        base_record["discovered_page_url"],
                        candidates,
                        discovery_state,
                        base_record["reason"],
                    )
                return base_record

            base_record["status"] = "failed"
            base_record["reason"] = (
                f"all candidate downloads failed: {summarize_exception(last_error)}"
                if last_error is not None
                else "all candidate downloads failed"
            )
            base_record["discovery_method"] = _best_discovery_method(candidates, discovery_state)
            if args.debug_html:
                debug_dir = args.output_root / f"{args.year:04d}-{args.month:02d}" / "raw_pdf" / CATEGORY / DEBUG_HTML_DIRNAME
                _save_debug_html(
                    debug_dir,
                    sanitize_filename(company_name),
                    source_page_url,
                    base_record["discovered_page_url"],
                    candidates,
                    discovery_state,
                    base_record["reason"],
                )
            base_record["http_status"] = _first_non_none(
                [candidate.get("source_http_status") for candidate in candidates]
                + [page.get("static_status") for page in discovery_state.get("pages", [])]
            )
            return base_record
    except Exception as exc:  # noqa: BLE001
        base_record["status"] = "failed"
        base_record["reason"] = summarize_exception(exc)
        base_record["http_status"] = _exception_http_status(exc)
        LOGGER.warning("[%s] %s failed: %s", row.get("row_index"), company_name, base_record["reason"])
        return base_record


def process_company(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return _process_company_impl(row, args)


def _configure_logging() -> None:
    LOGGER.handlers.clear()
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)
    LOGGER.addHandler(stream_handler)


def run() -> int:
    args = parse_args()
    _configure_logging()

    input_path = _resolve_input_path(args.input)
    if not input_path.exists():
        LOGGER.error("input workbook not found: %s", input_path)
        return 2

    rows = _load_workbook_rows(input_path)
    if not rows:
        LOGGER.warning("no company rows found in %s", input_path)

    period_root = args.output_root / f"{args.year:04d}-{args.month:02d}" / "raw_pdf" / CATEGORY
    period_root.mkdir(parents=True, exist_ok=True)
    args.total_companies = len(rows)  # type: ignore[attr-defined]

    LOGGER.info(
        "target period %04d-%02d | companies=%d | dry_run=%s | force=%s | browser=%s | workers=%d",
        args.year,
        args.month,
        len(rows),
        args.dry_run,
        args.force,
        args.use_browser,
        args.max_workers,
    )
    LOGGER.info("input workbook: %s", input_path)
    LOGGER.info("output root: %s", args.output_root)
    LOGGER.info("manifest folder: %s", period_root)

    results: list[dict[str, Any]] = []
    if args.max_workers == 1 or len(rows) <= 1:
        for row in rows:
            results.append(process_company(row, args))
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = [executor.submit(process_company, row, args) for row in rows]
            for future in as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda record: int(record.get("row_index") or 0))
    write_manifest(results, period_root)

    summary = Counter(record.get("status", "failed") for record in results)
    LOGGER.info(
        "finished | total=%d | downloaded=%d | skipped_existing=%d | discover_only=%d | no_match=%d | failed=%d",
        len(results),
        summary.get("downloaded", 0),
        summary.get("skipped_existing", 0),
        summary.get("discover_only", 0),
        summary.get("no_match", 0),
        summary.get("failed", 0),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
