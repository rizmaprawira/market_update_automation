from __future__ import annotations

"""Download conventional general-insurance financial report PDFs.

Usage examples:
    python scripts/download/download_general_insurance.py \
        --year 2026 --month 4 \
        --input assets/link_asuransi_umum.xlsx \
        --output-root data

    python scripts/download/download_general_insurance.py \
        --year 2026 --month 4 \
        --input assets/link_asuransi_umum.xlsx \
        --output-root data \
        --dry-run --use-browser

The script downloads only conventional reports, writes one PDF per company into:
    data/{YYYY}-{MM}/raw_pdf/asuransi_umum/{safe_company_name}/

It also writes:
    download_manifest.csv
    download_manifest.json
"""

import argparse
from contextlib import suppress
import hashlib
import json
import logging
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4 import FeatureNotFound

try:  # pragma: no cover - tqdm is a convenience dependency.
    from tqdm import tqdm
except ImportError:  # pragma: no cover - keep the script usable without a progress bar.
    def tqdm(iterable, *args, **kwargs):  # type: ignore[override]
        return iterable

try:  # pragma: no cover - optional dependency.
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - browser fallback is optional.
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


LOGGER = logging.getLogger("download_general_insurance")
CATEGORY = "asuransi_umum"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_WORKERS = 4
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
MAX_DISCOVERY_DEPTH = 2
MAX_LINKS_PER_PAGE = 80

MONTH_ALIASES = {
    1: ("januari", "january", "jan"),
    2: ("februari", "february", "feb"),
    3: ("maret", "march", "mar"),
    4: ("april", "apr"),
    5: ("mei", "may"),
    6: ("juni", "june", "jun"),
    7: ("juli", "july", "jul"),
    8: ("agustus", "august", "aug"),
    9: ("september", "sep", "sept"),
    10: ("oktober", "october", "oct"),
    11: ("november", "nov"),
    12: ("desember", "december", "dec"),
}

REPORT_POSITIVE_PHRASES = (
    "laporan keuangan konvensional",
    "laporan keuangan perusahaan",
    "publikasi laporan keuangan",
    "laporan keuangan",
    "financial report",
    "financial statement",
    "published report",
    "monthly report",
    "laporan bulanan",
    "financial highlight",
    "report",
)

STRONG_REPORT_PHRASES = (
    "laporan keuangan konvensional",
    "laporan keuangan perusahaan",
    "publikasi laporan keuangan",
    "laporan keuangan",
    "financial report",
    "financial statement",
)

SYARIAH_TERMS = (
    "unit syariah",
    "usaha syariah",
    "syariah",
    "shariah",
    "sharia",
    "uus",
    "islamic",
)

NEGATIVE_TERMS = (
    "sustainability",
    "keberlanjutan",
    "corporate governance",
    "tata kelola",
    "integrated report",
    "annual report",
    "laporan tahunan",
    "tahunan",
    "quarterly report",
)

QUARTER_TERMS = ("triwulan", "triwulanan", "quarter", "quarterly", "kuartal")
MONTHLY_TERMS = ("laporan bulanan", "monthly report")
CONVENTIONAL_TERMS = ("konvensional", "conventional", "general insurance", "asuransi umum")
RELEVANT_PAGE_TERMS = (
    "laporan keuangan",
    "financial report",
    "financial statement",
    "laporan publikasi",
    "publikasi laporan keuangan",
    "laporan bulanan",
    "monthly report",
    "report",
    "investor",
    "tata kelola",
    "keterbukaan informasi",
)
UNRELATED_TERMS = (
    "annual report",
    "sustainability",
    "esg",
    "governance",
    "gcg",
    "rbc",
    "klaim",
    "claim form",
    "formulir",
    "polis",
    "policy wording",
    "product brochure",
    "company profile",
    "press release",
    "marketing",
)


class DiscoveryError(RuntimeError):
    """Raised when source-page discovery fails after all fallbacks."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download conventional financial report PDFs for Indonesian general insurers."
    )
    parser.add_argument("--year", type=int, required=True, help="Target report year, for example 2026.")
    parser.add_argument("--month", type=int, required=True, help="Target report month, 1-12.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("link_asuransi_umum.xlsx"),
        help="Excel workbook with columns: no | nama perusahaan | link.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data"),
        help="Root output directory. The script writes into data/{YYYY}-{MM}/raw_pdf/asuransi_umum/.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Discover candidates without writing PDFs.")
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Discover and score candidate PDFs but do not download them.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing PDFs.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds for page fetch and PDF download requests.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Number of worker threads used to process companies.",
    )
    parser.add_argument(
        "--use-browser",
        action="store_true",
        help="Use Playwright to render pages when HTML parsing is insufficient.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum same-domain crawl depth from the source page.",
    )
    parser.add_argument(
        "--debug-html",
        action="store_true",
        help="Save fetched and rendered HTML snapshots for failed companies under _debug_html.",
    )
    return parser.parse_args(argv)


def ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_search_text(value: Any) -> str:
    return ascii_fold(clean_text(value)).lower()


def _make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def normalize_month_terms(month: int) -> list[str]:
    aliases = MONTH_ALIASES.get(month)
    if aliases is None:
        raise ValueError("month must be in the range 1-12")
    terms: list[str] = []
    for term in aliases:
        if term not in terms:
            terms.append(term)
    numeric_terms = (str(month), f"{month:02d}")
    for term in numeric_terms:
        if term not in terms:
            terms.append(term)
    return terms


def normalize_target_period(year: int, month: int) -> tuple[int, int, str]:
    if year < 1900:
        raise ValueError("year must be a realistic four-digit year")
    if not 1 <= month <= 12:
        raise ValueError("month must be in the range 1-12")
    return year, month, f"{year:04d}-{month:02d}"


def sanitize_filename(text: str) -> str:
    value = ascii_fold(clean_text(text)).lower()
    value = re.sub(r"\bpt\.?\b", " ", value)
    value = re.sub(r"\bpersero\b", " ", value)
    value = re.sub(r"\btbk\b", " ", value)
    value = re.sub(r"[^\w\s-]", " ", value)
    value = re.sub(r"[-\s]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "company"


def is_syariah_candidate(text: str) -> bool:
    normalized = normalize_search_text(text)
    if not normalized:
        return False
    if re.search(r"\bunit\s+usaha\s+syariah\b", normalized):
        return True
    if re.search(r"\bunit\s+syariah\b", normalized):
        return True
    if re.search(r"\busaha\s+syariah\b", normalized):
        return True
    if re.search(r"\buus\b", normalized):
        return True
    for term in ("syariah", "shariah", "sharia", "islamic"):
        if re.search(rf"\b{re.escape(term)}\b", normalized):
            return True
    return False


def _contains_token(text: str, token: str) -> bool:
    if token.isdigit():
        return re.search(rf"(?<!\d){re.escape(token)}(?!\d)", text) is not None
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


def _contains_any(text: str, tokens: tuple[str, ...] | list[str]) -> bool:
    return any(_contains_token(text, token) for token in tokens)


def _contains_exact_period(text: str, year: int, month: int) -> bool:
    month2 = f"{month:02d}"
    patterns = (
        rf"(?<!\d){year}[-_/\.]{month2}(?!\d)",
        rf"(?<!\d){year}[-_/\.]{month}(?!\d)",
        rf"(?<!\d){month2}[-_/\.]{year}(?!\d)",
        rf"(?<!\d){month}[-_/\.]{year}(?!\d)",
        rf"(?<!\d){year}{month2}(?!\d)",
        rf"(?<!\d){month2}{year}(?!\d)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _contains_month_reference(text: str, year: int, month: int) -> bool:
    if _contains_exact_period(text, year, month):
        return True
    month_terms = normalize_month_terms(month)
    month_words = [term for term in month_terms if not term.isdigit()]
    if not _contains_token(text, str(year)):
        return False
    return any(_contains_token(text, term) for term in month_words) or any(
        _contains_token(text, term) for term in month_terms if term.isdigit()
    )


def _contains_mismatched_month_reference(text: str, year: int, month: int) -> bool:
    for other_month in range(1, 13):
        if other_month == month:
            continue
        if _contains_exact_period(text, year, other_month):
            return True
        other_terms = normalize_month_terms(other_month)
        other_words = [term for term in other_terms if not term.isdigit()]
        if _contains_token(text, str(year)) and any(_contains_token(text, term) for term in other_words):
            return True
    return False


def _quarter_month(month: int) -> bool:
    return month in {3, 6, 9, 12}


def _quarter_number(month: int) -> int | None:
    mapping = {3: 1, 6: 2, 9: 3, 12: 4}
    return mapping.get(month)


def _quarter_terms(month: int) -> tuple[str, ...]:
    quarter = _quarter_number(month)
    if quarter is None:
        return ()
    roman = {1: "i", 2: "ii", 3: "iii", 4: "iv"}[quarter]
    return (
        f"q{quarter}",
        f"quarter {quarter}",
        f"quarter {roman}",
        f"triwulan {roman}",
        f"triwulan {quarter}",
        f"tw {roman}",
        f"tw {quarter}",
    )


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("anchor_text", ""),
        candidate.get("title", ""),
        candidate.get("button_text", ""),
        candidate.get("page_title", ""),
        candidate.get("pdf_url", ""),
        candidate.get("discovered_on_url", ""),
    ]
    return normalize_search_text(" ".join(str(part) for part in parts if part))


def _period_kind(text: str, year: int, month: int) -> str:
    if _contains_exact_period(text, year, month) or _contains_month_reference(text, year, month):
        return "monthly"
    if _quarter_month(month) and _contains_any(text, QUARTER_TERMS) and _contains_token(text, str(year)):
        return "quarterly"
    if _contains_any(text, ("annual report", "laporan tahunan", "tahunan")):
        if _contains_token(text, str(year)) or _contains_exact_period(text, year, month):
            return "annual"
    return "unknown"


def _is_strong_report(candidate_text: str) -> bool:
    return _contains_any(candidate_text, STRONG_REPORT_PHRASES)


def is_unrelated_report(text: str) -> bool:
    normalized = normalize_search_text(text)
    if not normalized:
        return False
    if is_syariah_candidate(normalized):
        return False

    strong = _contains_any(normalized, STRONG_REPORT_PHRASES) or _contains_any(
        normalized, CONVENTIONAL_TERMS
    )
    if _contains_any(normalized, UNRELATED_TERMS):
        return not strong
    if "annual report" in normalized or "laporan tahunan" in normalized:
        return not strong
    if "tata kelola" in normalized and not strong:
        return True
    if "claim" in normalized or "klaim" in normalized:
        return not strong
    return False


def is_relevant_financial_report(text: str, year: int, month: int) -> bool:
    normalized = normalize_search_text(text)
    if not normalized or is_syariah_candidate(normalized):
        return False
    if not _contains_token(normalized, str(year)) and not _contains_exact_period(normalized, year, month):
        return False
    if _contains_mismatched_month_reference(normalized, year, month):
        return False

    if _contains_exact_period(normalized, year, month):
        return True

    if _contains_any(normalized, STRONG_REPORT_PHRASES) and _contains_month_reference(normalized, year, month):
        return True

    if _contains_any(normalized, MONTHLY_TERMS) and _contains_month_reference(normalized, year, month):
        return True

    if _quarter_month(month) and (
        _contains_any(normalized, QUARTER_TERMS) or _contains_any(normalized, _quarter_terms(month))
    ):
        if _contains_any(normalized, REPORT_POSITIVE_PHRASES) or _contains_any(normalized, CONVENTIONAL_TERMS):
            return True

    if _contains_any(normalized, CONVENTIONAL_TERMS) and _contains_month_reference(normalized, year, month):
        return True

    if _contains_any(normalized, ("published report", "publikasi")) and _contains_month_reference(normalized, year, month):
        return True

    return False


def _should_follow_html_link(text: str, href: str, year: int, month: int) -> bool:
    normalized = normalize_search_text(f"{text} {href}")
    if not normalized or is_syariah_candidate(normalized):
        return False
    if href.lower().endswith(".pdf"):
        return False
    if _contains_any(normalized, RELEVANT_PAGE_TERMS) or _contains_any(normalized, CONVENTIONAL_TERMS):
        return True
    return _contains_month_reference(normalized, year, month)


def _extract_pdf_urls(value: str) -> list[str]:
    if not value:
        return []
    candidates = re.findall(
        r"""(?i)(?:https?://|//|/|\.{1,2}/)[^"'<>]+?\.pdf(?:\?[^"'<>]*)?""",
        value,
    )
    cleaned: list[str] = []
    for candidate in candidates:
        candidate = candidate.replace("\\/", "/").strip().rstrip(".,;)")
        if candidate and candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned


def _canonicalize_url(url: str) -> str:
    parsed = urlparse(clean_text(url))
    return parsed._replace(fragment="").geturl()


def _same_host(left: str, right: str) -> bool:
    left_host = urlparse(left).netloc.lower().removeprefix("www.")
    right_host = urlparse(right).netloc.lower().removeprefix("www.")
    return left_host == right_host


def _html_digest(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def _debug_html_path(debug_dir: Path, company_name: str, stage: str, url: str, suffix: str = "html") -> Path:
    company_folder = sanitize_filename(company_name)
    debug_dir = debug_dir / company_folder
    debug_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{stage}_{_html_digest(url)}.{suffix}"
    return debug_dir / filename


def _save_debug_html(
    debug_dir: Path | None,
    company_name: str,
    stage: str,
    url: str,
    html: str,
) -> None:
    if debug_dir is None:
        return
    path = _debug_html_path(debug_dir, company_name, stage, url)
    path.write_text(html, encoding="utf-8")


def _collect_context_text(element: Any) -> str:
    for selector in ("tr", "li", "article", "section", "div", "td", "main"):
        parent = element.find_parent(selector)
        if parent is not None:
            text = clean_text(parent.get_text(" ", strip=True))
            if text:
                return text[:800]
    return ""


def _make_candidate(
    *,
    source_page_url: str,
    discovered_on_url: str,
    pdf_url: str,
    anchor_text: str = "",
    title: str = "",
    context_text: str = "",
    page_title: str = "",
    discovery_mode: str,
    http_status: int | None,
) -> dict[str, Any]:
    candidate = {
        "category": CATEGORY,
        "source_page_url": source_page_url,
        "discovered_page_url": discovered_on_url,
        "discovered_on_url": discovered_on_url,
        "pdf_url": _canonicalize_url(pdf_url),
        "anchor_text": clean_text(anchor_text),
        "title": clean_text(title),
        "context_text": clean_text(context_text),
        "page_title": clean_text(page_title),
        "discovery_mode": discovery_mode,
        "http_status": http_status,
        "page_text": "",
    }
    candidate_text = _candidate_text(candidate)
    candidate["candidate_text"] = candidate_text
    candidate["is_syariah"] = is_syariah_candidate(candidate_text)
    candidate["period_kind"] = "unknown"
    return candidate


def _score_candidate(candidate: dict[str, Any], year: int, month: int) -> int:
    candidate_text = _candidate_text(candidate)
    url_text = normalize_search_text(candidate.get("pdf_url", ""))
    score = 0

    if candidate.get("is_syariah"):
        return -10_000
    if candidate.get("is_unrelated") or is_unrelated_report(candidate_text):
        score -= 250

    period_kind = _period_kind(candidate_text, year, month)
    candidate["period_kind"] = period_kind
    if period_kind == "monthly":
        score += 500
    elif period_kind == "quarterly":
        score += 350
    elif period_kind == "annual":
        score += 120

    if _contains_any(candidate_text, STRONG_REPORT_PHRASES):
        score += 140
    elif _contains_any(candidate_text, REPORT_POSITIVE_PHRASES):
        score += 80

    if _contains_any(candidate_text, ("konvensional", "conventional")):
        score += 80
    if _contains_any(candidate_text, ("perusahaan", "company", "general insurance", "asuransi umum")):
        score += 20

    if _contains_token(candidate_text, str(year)):
        score += 50
    if _contains_month_reference(candidate_text, year, month):
        score += 60
    if _contains_exact_period(candidate_text, year, month):
        score += 90

    if normalize_search_text(candidate.get("pdf_url", "")).endswith(".pdf"):
        score += 30

    if _contains_any(candidate_text, NEGATIVE_TERMS):
        score -= 120

    if _contains_any(candidate_text, ("financial highlight", "financialhigh", "financial-higlight")):
        score += 10

    if "download" in candidate_text and not _contains_any(candidate_text, STRONG_REPORT_PHRASES):
        score -= 10

    if "report" in candidate_text and not _contains_any(candidate_text, STRONG_REPORT_PHRASES):
        score += 5

    if _contains_month_reference(url_text, year, month):
        score += 35

    if _contains_any(url_text, ("laporan-keuangan", "financialreport", "financial_statement")):
        score += 20

    if _contains_any(candidate_text, RELEVANT_PAGE_TERMS):
        score += 15

    if candidate.get("discovery_mode") == "browser":
        score += 5

    return score


def score_candidate(candidate: dict[str, Any], year: int, month: int) -> int:
    return _score_candidate(candidate, year, month)


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_url: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        pdf_url = candidate.get("pdf_url", "")
        if not pdf_url:
            continue
        key = _canonicalize_url(pdf_url).lower()
        current = best_by_url.get(key)
        if current is None:
            best_by_url[key] = candidate
            continue
        current_score = current.get("score", 0)
        new_score = candidate.get("score", 0)
        if new_score > current_score:
            best_by_url[key] = candidate
            continue
        current_text = _candidate_text(current)
        new_text = _candidate_text(candidate)
        if new_score == current_score and len(new_text) > len(current_text):
            best_by_url[key] = candidate
    return list(best_by_url.values())


def _fetch_html(session: requests.Session, url: str, timeout: int) -> requests.Response:
    response = session.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": url,
        },
    )
    response.raise_for_status()
    return response


def _is_pdf_response(final_url: str, content_type: str, content: bytes) -> bool:
    lowered_content_type = normalize_search_text(content_type)
    if "application/pdf" in lowered_content_type or "pdf" in lowered_content_type:
        return True
    if final_url.lower().endswith(".pdf"):
        return True
    return content.startswith(b"%PDF")


def is_valid_pdf_response(response: Any, content_bytes: bytes) -> bool:
    headers = getattr(response, "headers", {}) or {}
    content_type = ""
    if isinstance(headers, dict):
        content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
    final_url = getattr(response, "url", "")
    return _is_pdf_response(final_url, content_type, content_bytes)


def _parse_html_for_candidates(
    html: str,
    *,
    source_page_url: str,
    discovered_on_url: str,
    year: int,
    month: int,
    discovery_mode: str,
    http_status: int | None,
    page_title: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    soup = _make_soup(html)
    page_text = clean_text(soup.get_text(" ", strip=True))
    discovered_candidates: list[dict[str, Any]] = []
    nested_html_links: list[str] = []
    seen_urls: set[str] = set()

    def add_candidate(pdf_url: str, anchor_text: str = "", title: str = "", context_text: str = "") -> None:
        resolved = _canonicalize_url(urljoin(discovered_on_url, pdf_url))
        if not resolved:
            return
        key = resolved.lower()
        if key in seen_urls:
            return
        candidate = _make_candidate(
            source_page_url=source_page_url,
            discovered_on_url=discovered_on_url,
            pdf_url=resolved,
            anchor_text=anchor_text,
            title=title,
            context_text=context_text,
            page_title=page_title,
            discovery_mode=discovery_mode,
            http_status=http_status,
        )
        candidate["page_text"] = page_text[:4000]
        discovered_candidates.append(candidate)
        seen_urls.add(key)

    for element in soup.find_all(["a", "button", "summary", "iframe", "embed", "object", "source", "meta"]):
        if element.name == "meta":
            http_equiv = normalize_search_text(element.get("http-equiv", ""))
            content = clean_text(element.get("content", ""))
            if "refresh" in http_equiv:
                match = re.search(r"url\s*=\s*(.+)$", content, flags=re.I)
                if match:
                    resolved = _canonicalize_url(urljoin(discovered_on_url, match.group(1).strip()))
                    if resolved.lower().endswith(".pdf"):
                        add_candidate(resolved, title="meta refresh", context_text="meta refresh")
            continue

        href = element.get("href") or element.get("src") or element.get("data") or ""
        if not href:
            href = clean_text(element.get("onclick") or element.get("data-href") or element.get("data-url") or "")
        button_text = clean_text(element.get_text(" ", strip=True))

        title = clean_text(element.get("title") or element.get("aria-label") or element.get("alt") or "")
        context_text = _collect_context_text(element)
        attributes = " ".join(
            clean_text(value)
            for key, value in element.attrs.items()
            if key not in {"href", "src", "data"} and value
        )
        raw_strings = [href, button_text, title, context_text, attributes, page_text]
        pdf_urls: list[str] = []
        for raw in raw_strings:
            pdf_urls.extend(_extract_pdf_urls(raw))

        if pdf_urls:
            for pdf_url in pdf_urls:
                add_candidate(pdf_url, anchor_text=button_text, title=title, context_text=context_text)
            continue

        resolved_href = _canonicalize_url(urljoin(discovered_on_url, href))
        if resolved_href.lower().endswith(".pdf"):
            add_candidate(resolved_href, anchor_text=button_text, title=title, context_text=context_text)
            continue

        if len(nested_html_links) < MAX_LINKS_PER_PAGE and _should_follow_html_link(button_text + " " + title + " " + context_text, href, year, month):
            nested_html_links.append(resolved_href)

    for raw_url in _extract_pdf_urls(html):
        add_candidate(raw_url, anchor_text="raw_pdf_url", title=page_title, context_text=page_title)

    for script in soup.find_all("script"):
        script_text = clean_text(script.get_text(" ", strip=True))
        for raw_url in _extract_pdf_urls(script_text):
            add_candidate(raw_url, anchor_text="script", title=page_title, context_text=script_text)

    for candidate in discovered_candidates:
        text = _candidate_text(candidate)
        candidate["is_syariah"] = is_syariah_candidate(text)
        candidate["is_unrelated"] = is_unrelated_report(text)
        candidate["is_relevant"] = is_relevant_financial_report(text, year, month)
        candidate["score"] = score_candidate(candidate, year, month)

    return discovered_candidates, nested_html_links


def _discover_with_browser(source_url: str, timeout: int) -> tuple[str, str, int, str]:
    if sync_playwright is None:
        raise DiscoveryError("playwright is not installed")

    browser = None
    context = None
    page = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=DEFAULT_USER_AGENT, accept_downloads=True)
        context.set_default_timeout(timeout * 1000)
        page = context.new_page()
        response = page.goto(source_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        if response is None:
            raise DiscoveryError(f"browser did not return a response for {source_url}")
        with suppress(PlaywrightTimeoutError):
            page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 8000))
        return page.content(), page.url, response.status if response else 0, response.headers.get("content-type", "")
    except Exception as exc:  # noqa: BLE001
        raise DiscoveryError(str(exc)) from exc
    finally:
        with suppress(Exception):
            if page is not None:
                page.close()
        with suppress(Exception):
            if context is not None:
                context.close()
        with suppress(Exception):
            if browser is not None:
                browser.close()


def _extract_candidates_from_html(
    html: str,
    *,
    source_page_url: str,
    discovered_on_url: str,
    year: int,
    month: int,
    discovery_mode: str,
    http_status: int | None,
    page_title: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    return _parse_html_for_candidates(
        html,
        source_page_url=source_page_url,
        discovered_on_url=discovered_on_url,
        year=year,
        month=month,
        discovery_mode=discovery_mode,
        http_status=http_status,
        page_title=page_title,
    )


def extract_candidates_static(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    debug_snapshots: list[tuple[str, str, str]] | None = None,
    discovery_method: str = "static",
) -> list[dict[str, Any]]:
    timeout = getattr(session, "_download_timeout", DEFAULT_TIMEOUT)
    response = _fetch_html(session, source_url, timeout)
    final_url = response.url
    http_status = response.status_code
    content_type = response.headers.get("Content-Type", "")
    if is_valid_pdf_response(response, response.content):
        candidate = _make_candidate(
            source_page_url=source_url,
            discovered_on_url=final_url,
            pdf_url=final_url,
            anchor_text="direct_pdf",
            title="direct_pdf",
            context_text="direct_pdf",
            page_title="",
            discovery_mode=discovery_method,
            http_status=http_status,
        )
        candidate["page_text"] = ""
        candidate["is_syariah"] = is_syariah_candidate(_candidate_text(candidate))
        candidate["is_unrelated"] = is_unrelated_report(_candidate_text(candidate))
        candidate["is_relevant"] = is_relevant_financial_report(_candidate_text(candidate), year, month)
        candidate["score"] = score_candidate(candidate, year, month)
        if debug_snapshots is not None:
            debug_snapshots.append((f"{discovery_method}:pdf", final_url, f"PDF response: {final_url}"))
        return [candidate]

    html = response.text
    if debug_snapshots is not None:
        debug_snapshots.append((f"{discovery_method}:page", final_url, html))
    soup = _make_soup(html)
    page_title = clean_text(soup.title.get_text(strip=True)) if soup.title else ""
    candidates, _ = _extract_candidates_from_html(
        html,
        source_page_url=source_url,
        discovered_on_url=final_url,
        year=year,
        month=month,
        discovery_mode=discovery_method,
        http_status=http_status,
        page_title=page_title,
    )
    return candidates


def extract_candidates_browser(
    source_url: str,
    year: int,
    month: int,
    debug_snapshots: list[tuple[str, str, str]] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    discovery_method: str = "browser",
) -> list[dict[str, Any]]:
    snapshots = _browser_page_snapshots(source_url, year, month, timeout)
    candidates: list[dict[str, Any]] = []
    for stage, page_url, html in snapshots:
        if debug_snapshots is not None:
            debug_snapshots.append((f"{discovery_method}:{stage}", page_url, html))
        soup = _make_soup(html)
        page_title = clean_text(soup.title.get_text(strip=True)) if soup.title else ""
        snapshot_candidates, _ = _extract_candidates_from_html(
            html,
            source_page_url=source_url,
            discovered_on_url=page_url,
            year=year,
            month=month,
            discovery_mode=discovery_method,
            http_status=None,
            page_title=page_title,
        )
        candidates.extend(snapshot_candidates)

    final_candidates: list[dict[str, Any]] = []
    for candidate in _dedupe_candidates(candidates):
        text = _candidate_text(candidate)
        candidate["is_syariah"] = is_syariah_candidate(text)
        candidate["is_unrelated"] = is_unrelated_report(text)
        candidate["is_relevant"] = is_relevant_financial_report(text, year, month)
        candidate["score"] = score_candidate(candidate, year, month)
        final_candidates.append(candidate)
    return final_candidates


def _browser_month_tokens(year: int, month: int) -> list[str]:
    tokens = [str(year), f"{year:04d}-{month:02d}", f"{year:04d}_{month:02d}", f"{month:02d}-{year}", f"{month:02d}_{year}"]
    tokens.extend(normalize_month_terms(month))
    tokens.extend(list(_quarter_terms(month)))
    return [token.lower() for token in tokens if token]


def _capture_page_snapshot(
    page: Any,
    *,
    stage: str,
    snapshots: list[tuple[str, str, str]],
) -> None:
    html = page.content()
    snapshots.append((stage, page.url, html))


def _browser_interact_page(page: Any, year: int, month: int) -> list[tuple[str, str, str]]:
    snapshots: list[tuple[str, str, str]] = []
    tokens = _browser_month_tokens(year, month)
    relevant_texts = list(RELEVANT_PAGE_TERMS) + list(CONVENTIONAL_TERMS) + list(_quarter_terms(month))

    def visible_text(locator: Any) -> str:
        try:
            return clean_text(locator.inner_text(timeout=1_000))
        except Exception:  # noqa: BLE001
            return ""

    with suppress(Exception):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(750)
        _capture_page_snapshot(page, stage="scrolled", snapshots=snapshots)

    cookie_texts = ("accept", "agree", "setuju", "oke", "ok", "got it")
    for selector in ("button", "[role='button']", "a"):
        locator = page.locator(selector)
        count = min(locator.count(), 20)
        for index in range(count):
            item = locator.nth(index)
            text = visible_text(item).lower()
            if not text:
                continue
            if any(token in text for token in cookie_texts):
                with suppress(Exception):
                    item.click(timeout=1_500)
                    page.wait_for_timeout(500)
                    _capture_page_snapshot(page, stage=f"dismiss_{selector}_{index}", snapshots=snapshots)
                continue
            if not any(token in text for token in relevant_texts):
                continue
            with suppress(Exception):
                item.click(timeout=2_000)
                page.wait_for_timeout(750)
                _capture_page_snapshot(page, stage=f"click_{selector}_{index}", snapshots=snapshots)

    for selector in ("select",):
        locator = page.locator(selector)
        count = min(locator.count(), 8)
        for index in range(count):
            item = locator.nth(index)
            options: list[tuple[str, str]] = []
            with suppress(Exception):
                option_locator = item.locator("option")
                option_count = min(option_locator.count(), 20)
                for option_index in range(option_count):
                    option = option_locator.nth(option_index)
                    label = clean_text(option.inner_text(timeout=1_000))
                    value = clean_text(option.get_attribute("value"))
                    if label or value:
                        options.append((label, value))
            chosen_value: str | None = None
            for label, value in options:
                label_lower = label.lower()
                value_lower = value.lower()
                if any(token in label_lower or token in value_lower for token in tokens):
                    chosen_value = value or label
                    break
            if chosen_value:
                with suppress(Exception):
                    item.select_option(value=chosen_value)
                    page.wait_for_timeout(750)
                    _capture_page_snapshot(page, stage=f"select_{index}", snapshots=snapshots)

    for selector in ("summary", "[role='tab']", "[data-toggle='tab']", ".tab", ".accordion-button"):
        locator = page.locator(selector)
        count = min(locator.count(), 16)
        for index in range(count):
            item = locator.nth(index)
            text = visible_text(item).lower()
            if not text or not any(token in text for token in relevant_texts):
                continue
            with suppress(Exception):
                item.click(timeout=2_000)
                page.wait_for_timeout(750)
                _capture_page_snapshot(page, stage=f"expand_{selector}_{index}", snapshots=snapshots)

    with suppress(Exception):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(750)
        _capture_page_snapshot(page, stage="final_scroll", snapshots=snapshots)

    return snapshots


def _browser_page_snapshots(source_url: str, year: int, month: int, timeout: int) -> list[tuple[str, str, str]]:
    if sync_playwright is None:
        raise DiscoveryError("playwright is not installed")

    playwright = None
    browser = None
    context = None
    page = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=DEFAULT_USER_AGENT, accept_downloads=True)
        context.set_default_timeout(timeout * 1000)
        page = context.new_page()
        response = page.goto(source_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        if response is None:
            raise DiscoveryError(f"browser did not return a response for {source_url}")
        with suppress(PlaywrightTimeoutError):
            page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 8_000))
        snapshots: list[tuple[str, str, str]] = []
        snapshots.append(("initial", page.url, page.content()))
        snapshots.extend(_browser_interact_page(page, year, month))
        snapshots.append(("final", page.url, page.content()))
        return snapshots
    except Exception as exc:  # noqa: BLE001
        raise DiscoveryError(str(exc)) from exc
    finally:
        with suppress(Exception):
            if page is not None:
                page.close()
        with suppress(Exception):
            if context is not None:
                context.close()
        with suppress(Exception):
            if browser is not None:
                browser.close()
        with suppress(Exception):
            if playwright is not None:
                playwright.stop()


def _crawl_page(
    session: requests.Session,
    source_url: str,
    root_source_url: str,
    year: int,
    month: int,
    *,
    timeout: int,
    use_browser: bool,
    max_depth: int,
    debug_snapshots: list[tuple[str, str, str]] | None = None,
    depth: int = 0,
    visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    if visited is None:
        visited = set()

    canonical_source_url = _canonicalize_url(source_url)
    if not canonical_source_url or canonical_source_url.lower() in visited:
        return []
    visited.add(canonical_source_url.lower())

    try:
        response = _fetch_html(session, canonical_source_url, timeout)
        final_url = response.url
        status_code = response.status_code
        content_type = response.headers.get("Content-Type", "")
        if _is_pdf_response(final_url, content_type, response.content):
            candidate = _make_candidate(
                source_page_url=root_source_url,
                discovered_on_url=final_url,
                pdf_url=final_url,
                anchor_text="direct_pdf",
                title="direct_pdf",
                context_text="direct_pdf",
                page_title="",
                discovery_mode="http",
                http_status=status_code,
            )
            candidate["is_syariah"] = is_syariah_candidate(_candidate_text(candidate))
            candidate["is_unrelated"] = is_unrelated_report(_candidate_text(candidate))
            candidate["is_relevant"] = is_relevant_financial_report(_candidate_text(candidate), year, month)
            candidate["score"] = score_candidate(candidate, year, month)
            return [candidate]
        html = response.text
    except Exception as exc:  # noqa: BLE001
        if depth == 0:
            try:
                html, final_url, status_code, content_type = _discover_with_browser(canonical_source_url, timeout)
            except Exception as browser_exc:  # noqa: BLE001
                raise DiscoveryError(f"{canonical_source_url}: {exc}; browser: {browser_exc}") from browser_exc
        else:
            return []

    soup_title = ""
    soup = _make_soup(html)
    if soup.title and soup.title.get_text(strip=True):
        soup_title = clean_text(soup.title.get_text(strip=True))

    candidates, nested_html_links = _parse_html_for_candidates(
        html,
        source_page_url=root_source_url,
        discovered_on_url=final_url,
        year=year,
        month=month,
        discovery_mode="static" if depth == 0 else "crawled_static",
        http_status=status_code,
        page_title=soup_title,
    )

    if debug_snapshots is not None:
        debug_snapshots.append((f"static:{depth}", final_url, html))

    has_conventional = any(
        candidate.get("is_relevant") and not candidate.get("is_syariah") and not candidate.get("is_unrelated")
        for candidate in candidates
    )
    browser_required = use_browser or (depth == 0 and not has_conventional)

    if browser_required:
        try:
            browser_snapshots = _browser_page_snapshots(canonical_source_url, year, month, timeout)
            for stage, browser_final_url, browser_html in browser_snapshots:
                if debug_snapshots is not None:
                    debug_snapshots.append((f"browser:{depth}:{stage}", browser_final_url, browser_html))
                browser_soup = _make_soup(browser_html)
                browser_title = ""
                if browser_soup.title and browser_soup.title.get_text(strip=True):
                    browser_title = clean_text(browser_soup.title.get_text(strip=True))
                browser_candidates, browser_nested_links = _parse_html_for_candidates(
                    browser_html,
                    source_page_url=root_source_url,
                    discovered_on_url=browser_final_url,
                    year=year,
                    month=month,
                    discovery_mode="browser" if depth == 0 else "crawled_browser",
                    http_status=None,
                    page_title=browser_title,
                )
                candidates.extend(browser_candidates)
                nested_html_links.extend(browser_nested_links)
        except DiscoveryError:
            pass

    if depth < max_depth:
        for nested_url in nested_html_links:
            if not _same_host(canonical_source_url, nested_url):
                continue
            try:
                nested_candidates = _crawl_page(
                    session,
                    nested_url,
                    root_source_url,
                    year,
                    month,
                    timeout=timeout,
                    use_browser=use_browser,
                    max_depth=max_depth,
                    debug_snapshots=debug_snapshots,
                    depth=depth + 1,
                    visited=visited,
                )
            except DiscoveryError:
                continue
            candidates.extend(nested_candidates)

    return _dedupe_candidates(candidates)


def crawl_related_pages(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    max_depth: int = 2,
    use_browser: bool = False,
    debug_snapshots: list[tuple[str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    timeout = getattr(session, "_download_timeout", DEFAULT_TIMEOUT)
    return _crawl_page(
        session,
        source_url,
        source_url,
        year,
        month,
        timeout=timeout,
        use_browser=use_browser,
        max_depth=max_depth,
        debug_snapshots=debug_snapshots,
    )


def extract_pdf_candidates(
    session: requests.Session,
    source_url: str,
    year: int,
    month: int,
    use_browser: bool = False,
) -> list[dict[str, Any]]:
    candidates = crawl_related_pages(session, source_url, year, month, use_browser=use_browser)
    final_candidates = []
    for candidate in _dedupe_candidates(candidates):
        candidate_text = _candidate_text(candidate)
        candidate["is_syariah"] = is_syariah_candidate(candidate_text)
        candidate["is_unrelated"] = is_unrelated_report(candidate_text)
        candidate["is_relevant"] = is_relevant_financial_report(candidate_text, year, month)
        candidate["score"] = score_candidate(candidate, year, month)
        final_candidates.append(candidate)
    return final_candidates


def choose_best_candidate(candidates: list[dict[str, Any]], year: int, month: int) -> dict[str, Any] | None:
    if not candidates:
        return None

    annotated = []
    for candidate in candidates:
        candidate_text = _candidate_text(candidate)
        candidate["is_syariah"] = is_syariah_candidate(candidate_text)
        candidate["is_relevant"] = is_relevant_financial_report(candidate_text, year, month)
        candidate["period_kind"] = _period_kind(candidate_text, year, month)
        candidate["is_unrelated"] = is_unrelated_report(candidate_text)
        candidate["score"] = score_candidate(candidate, year, month)
        annotated.append(candidate)

    non_syariah = [
        candidate
        for candidate in annotated
        if not candidate["is_syariah"] and not candidate.get("is_unrelated")
    ]
    relevant = [candidate for candidate in non_syariah if candidate["is_relevant"]]
    if relevant:
        monthly = [candidate for candidate in relevant if candidate["period_kind"] == "monthly"]
        if monthly:
            return max(monthly, key=lambda candidate: (candidate["score"], len(_candidate_text(candidate))))

        quarterly = [candidate for candidate in relevant if candidate["period_kind"] == "quarterly"]
        if quarterly and _quarter_month(month):
            return max(quarterly, key=lambda candidate: (candidate["score"], len(_candidate_text(candidate))))

        annual = [candidate for candidate in relevant if candidate["period_kind"] == "annual"]
        if annual:
            return max(annual, key=lambda candidate: (candidate["score"], len(_candidate_text(candidate))))

        return max(relevant, key=lambda candidate: (candidate["score"], len(_candidate_text(candidate))))

    return None


def _build_output_path(output_base: Path, company_name: str, year: int, month: int) -> Path:
    company_folder = sanitize_filename(company_name)
    filename = f"{company_folder}_{year:04d}-{month:02d}.pdf"
    return output_base / company_folder / filename


def _response_indicates_pdf(content_type: str, pdf_url: str, first_chunk: bytes) -> bool:
    content_type = normalize_search_text(content_type)
    if "application/pdf" in content_type:
        return True
    if pdf_url.lower().endswith(".pdf"):
        return True
    return first_chunk[:4] == b"%PDF"


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
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    temp_path = output_path.with_suffix(output_path.suffix + ".part")
    try:
        with session.get(
            pdf_url,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
            headers={
                "Accept": "application/pdf,*/*;q=0.8",
                "Referer": pdf_url,
            },
        ) as response:
            response.raise_for_status()
            chunk_iter = response.iter_content(chunk_size=8192)
            first_chunk = b""
            written = 0
            with temp_path.open("wb") as handle:
                for chunk in chunk_iter:
                    if not chunk:
                        continue
                    if not first_chunk:
                        first_chunk = chunk
                    handle.write(chunk)
                    written += len(chunk)

            if written == 0:
                raise ValueError(f"empty response for PDF: {pdf_url}")
            if not is_valid_pdf_response(response, first_chunk):
                raise ValueError(f"response did not look like a PDF: {pdf_url}")

        temp_path.replace(output_path)
        return {
            "status": "downloaded",
            "reason": "download complete",
            "http_status": response.status_code,
            "file_size_bytes": output_path.stat().st_size,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    except Exception as exc:  # noqa: BLE001
        temp_path.unlink(missing_ok=True)
        raise


def _resolve_input_path(path: Path) -> Path:
    if path.exists():
        return path
    assets_path = Path("assets") / path.name
    if assets_path.exists():
        return assets_path
    return path


def _normalise_workbook(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {column: str(column).strip().lower() for column in df.columns}
    df = df.rename(columns=renamed)
    required = {"no", "nama perusahaan", "link"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    return df


def _candidate_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidate_count": len(candidates),
        "rejected_syariah_count": sum(1 for candidate in candidates if candidate.get("is_syariah")),
        "rejected_unrelated_count": sum(
            1 for candidate in candidates if candidate.get("is_unrelated") and not candidate.get("is_syariah")
        ),
    }


def _save_debug_snapshots(
    debug_dir: Path,
    company_name: str,
    snapshots: list[tuple[str, str, str]],
) -> None:
    if not snapshots:
        return
    for index, (stage, url, html) in enumerate(snapshots, start=1):
        safe_stage = re.sub(r"[^a-zA-Z0-9_.-]+", "_", stage).strip("_") or "snapshot"
        path = _debug_html_path(debug_dir, company_name, f"{index:02d}_{safe_stage}", url)
        path.write_text(html, encoding="utf-8")


def process_company(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    company_name = clean_text(row.get("nama perusahaan"))
    source_page_url = clean_text(row.get("link"))
    target_year, target_month, period = normalize_target_period(int(args.year), int(args.month))
    output_root = Path(args.output_root) / period / "raw_pdf" / CATEGORY
    output_path = _build_output_path(output_root, company_name, target_year, target_month)
    debug_dir = output_root / "_debug_html"
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    result: dict[str, Any] = {
        "category": CATEGORY,
        "company_name": company_name,
        "source_page_url": source_page_url,
        "discovered_page_url": "",
        "pdf_url": "",
        "target_year": target_year,
        "target_month": target_month,
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
        "timestamp": timestamp,
    }
    debug_snapshots: list[tuple[str, str, str]] = []

    if not company_name or not source_page_url:
        result["reason"] = "missing company name or source page URL"
        return result

    fallback_url = COMPANY_FALLBACK_URLS.get(company_name.lower())
    if fallback_url:
        source_page_url = fallback_url
        result["source_page_url"] = source_page_url

    LOGGER.info("[%s] processing %s", sanitize_filename(company_name), company_name)

    try:
        with requests.Session() as session:
            session.headers.update(
                {
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Connection": "keep-alive",
                }
            )
            session._download_timeout = int(args.timeout)  # type: ignore[attr-defined]

            candidates = crawl_related_pages(
                session,
                source_page_url,
                target_year,
                target_month,
                max_depth=int(args.max_depth),
                use_browser=bool(args.use_browser),
                debug_snapshots=debug_snapshots,
            )

            if fallback_url and fallback_url != source_page_url:
                fallback_candidates = crawl_related_pages(
                    session,
                    fallback_url,
                    target_year,
                    target_month,
                    max_depth=int(args.max_depth),
                    use_browser=bool(args.use_browser),
                    debug_snapshots=debug_snapshots,
                )
                for candidate in fallback_candidates:
                    candidate["discovery_mode"] = "manual_fallback"
                candidates.extend(fallback_candidates)

            candidates = _dedupe_candidates(candidates)
            for candidate in candidates:
                text = _candidate_text(candidate)
                candidate["is_syariah"] = is_syariah_candidate(text)
                candidate["is_unrelated"] = is_unrelated_report(text)
                candidate["is_relevant"] = is_relevant_financial_report(text, target_year, target_month)
                candidate["score"] = score_candidate(candidate, target_year, target_month)

            counts = _candidate_counts(candidates)
            result.update(counts)

            best_candidate = choose_best_candidate(candidates, target_year, target_month)
            if best_candidate is None:
                if candidates:
                    if counts["rejected_syariah_count"] > 0 and counts["candidate_count"] == counts["rejected_syariah_count"]:
                        result["reason"] = "only syariah/sharia candidates were discovered after full crawl"
                    elif counts["rejected_unrelated_count"] > 0 and counts["candidate_count"] == counts["rejected_unrelated_count"]:
                        result["reason"] = "only unrelated report candidates were discovered after full crawl"
                    else:
                        result["reason"] = "no conventional March 2026 financial report candidate matched after full crawl"
                else:
                    result["reason"] = "no candidate PDF found after static, browser, and crawl attempts"
                result["status"] = "no_match"
                if args.debug_html:
                    _save_debug_snapshots(debug_dir, company_name, debug_snapshots)
                return result

            result["pdf_url"] = best_candidate.get("pdf_url", "")
            result["discovered_page_url"] = best_candidate.get("discovered_page_url", best_candidate.get("discovered_on_url", ""))
            result["discovery_method"] = best_candidate.get("discovery_mode", "")
            result["score"] = int(best_candidate.get("score", 0))
            result["http_status"] = best_candidate.get("http_status")

            if args.discover_only or args.dry_run:
                result["status"] = "discover_only"
                result["reason"] = "candidate discovered; download skipped by flag"
                if args.debug_html:
                    _save_debug_snapshots(debug_dir, company_name, debug_snapshots)
                return result

            if output_path.exists() and not args.force:
                result["status"] = "skipped_existing"
                result["reason"] = "file already exists"
                result["file_size_bytes"] = output_path.stat().st_size
                if args.debug_html:
                    _save_debug_snapshots(debug_dir, company_name, debug_snapshots)
                return result

            download_result = download_pdf(
                session,
                best_candidate["pdf_url"],
                output_path,
                timeout=int(args.timeout),
                force=bool(args.force),
            )
            result["status"] = download_result["status"]
            result["reason"] = download_result["reason"]
            result["http_status"] = download_result["http_status"]
            result["file_size_bytes"] = download_result["file_size_bytes"]
            if args.debug_html and result["status"] in {"failed", "no_match"}:
                _save_debug_snapshots(debug_dir, company_name, debug_snapshots)
            return result
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["reason"] = str(exc).splitlines()[0]
        if hasattr(exc, "response") and getattr(exc.response, "status_code", None) is not None:  # type: ignore[attr-defined]
            result["http_status"] = exc.response.status_code  # type: ignore[attr-defined]
        if args.debug_html:
            _save_debug_snapshots(debug_dir, company_name, debug_snapshots)
        return result


def write_manifest(records: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "download_manifest.csv"
    json_path = output_dir / "download_manifest.json"
    columns = [
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
    frame = pd.DataFrame(records).reindex(columns=columns)
    frame.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def _configure_logging() -> None:
    LOGGER.handlers.clear()
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)


def _summarise_records(records: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for record in records:
        status = record.get("status", "unknown")
        summary[status] = summary.get(status, 0) + 1
    return summary


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    try:
        args = parse_args(argv)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("argument parsing failed: %s", exc)
        return 2

    try:
        target_year, target_month, period = normalize_target_period(int(args.year), int(args.month))
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("invalid target period: %s", exc)
        return 2

    input_path = _resolve_input_path(Path(args.input))
    if not input_path.exists():
        LOGGER.error("input workbook not found: %s", input_path)
        return 2

    output_base = Path(args.output_root) / period / "raw_pdf" / CATEGORY
    output_base.mkdir(parents=True, exist_ok=True)

    LOGGER.info("reading workbook: %s", input_path)
    try:
        frame = pd.read_excel(input_path, engine="openpyxl")
        frame = _normalise_workbook(frame)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("failed to read workbook: %s", exc)
        return 2

    rows = frame.to_dict(orient="records")
    for index, row in enumerate(rows, start=1):
        row["__index"] = index

    total = len(rows)
    LOGGER.info(
        "starting download run: companies=%d year=%04d month=%02d dry_run=%s discover_only=%s force=%s max_workers=%d use_browser=%s max_depth=%d debug_html=%s",
        total,
        target_year,
        target_month,
        bool(args.dry_run),
        bool(args.discover_only),
        bool(args.force),
        int(args.max_workers),
        bool(args.use_browser),
        int(args.max_depth),
        bool(args.debug_html),
    )

    records: list[dict[str, Any]] = [dict() for _ in rows]
    with ThreadPoolExecutor(max_workers=max(1, int(args.max_workers))) as executor:
        future_map = {executor.submit(process_company, row, args): row["__index"] - 1 for row in rows}
        for future in tqdm(as_completed(future_map), total=total, desc="companies", unit="company"):
            index = future_map[future]
            row = rows[index]
            try:
                records[index] = future.result()
            except Exception as exc:  # noqa: BLE001
                records[index] = {
                    "category": CATEGORY,
                    "company_name": clean_text(row.get("nama perusahaan")),
                    "source_page_url": clean_text(row.get("link")),
                    "discovered_page_url": "",
                    "pdf_url": "",
                    "target_year": target_year,
                    "target_month": target_month,
                    "output_path": str(_build_output_path(output_base, clean_text(row.get("nama perusahaan")), target_year, target_month)),
                    "status": "failed",
                    "reason": str(exc).splitlines()[0],
                    "discovery_method": "",
                    "score": 0,
                    "rejected_syariah_count": 0,
                    "rejected_unrelated_count": 0,
                    "candidate_count": 0,
                    "http_status": None,
                    "file_size_bytes": None,
                    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
            status = records[index].get("status", "unknown")
            company_name = records[index].get("company_name", "")
            LOGGER.info("[%d/%d] %s -> %s", index + 1, total, company_name, status)

    csv_path, json_path = write_manifest(records, output_base)
    summary = _summarise_records(records)
    LOGGER.info("manifest written: %s", csv_path)
    LOGGER.info("manifest written: %s", json_path)
    LOGGER.info("summary: %s", ", ".join(f"{key}={value}" for key, value in sorted(summary.items())))
    return 0


COMPANY_FALLBACK_URLS: dict[str, str] = {}


if __name__ == "__main__":
    raise SystemExit(main())
