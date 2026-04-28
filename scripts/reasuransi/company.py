from __future__ import annotations

"""Download the conventional financial report PDF for Indonesia Re.

The script starts from:
    https://www.indonesiare.co.id/id/investor-relations/financial-report

It discovers the requested year/month report, excludes syariah/sharia/UUS/
islamic documents, validates the PDF bytes, writes the PDF into the same
company folder as the manifest files, and saves debug HTML if no match is found.
"""

import argparse
import csv
import json
import logging
import re
import sys
import tempfile
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from bs4 import FeatureNotFound
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:  # pragma: no cover - optional dependency.
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - browser fallback is optional.
    PlaywrightError = Exception  # type: ignore[assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


LOGGER = logging.getLogger("download_indonesiare_report")

SOURCE_URL = "https://www.indonesiare.co.id/id/investor-relations/financial-report"
COMPANY_ID = "indonesiare"
COMPANY_NAME = "Indonesia Re"
CATEGORY = "reasuransi"
OUTPUT_SUBDIR = "raw_pdf"
DEBUG_HTML_DIRNAME = "_debug_html"

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_PAGES = 24
DEFAULT_MAX_LINKS_PER_PAGE = 80
MAX_RUNTIME_SECONDS = 180
MANIFEST_TIMEZONE = ZoneInfo("Asia/Jakarta")

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
    10: ["oktober", "october", "oct"],
    11: ["november", "nov"],
    12: ["desember", "december", "dec"],
}

SYARIAH_TERMS = ("syariah", "shariah", "sharia", "uus", "islamic")
UNRELATED_TERMS = (
    "annual report",
    "laporan tahunan",
    "sustainability",
    "keberlanjutan",
    "integrated report",
    "corporate governance",
    "tata kelola",
)
REPORT_TERMS = (
    "laporan keuangan",
    "laporan keuangan bulanan",
    "financial report",
    "financial statement",
    "laporan bulanan",
    "monthly report",
    "monthly financial report",
    "publikasi laporan keuangan",
    "report",
)

MANIFEST_FIELDS = [
    "category",
    "company_id",
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
    "candidate_count",
    "rejected_syariah_count",
    "rejected_unrelated_count",
    "http_status",
    "file_size_bytes",
    "timestamp",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@dataclass(frozen=True)
class Candidate:
    page_url: str
    discovered_page_url: str
    pdf_url: str
    title: str
    context: str
    discovery_method: str
    score: int
    is_syariah: bool
    is_unrelated: bool
    target_match: bool

    def to_manifest(
        self,
        *,
        year: int,
        month: int,
        output_path: Path,
        status: str,
        reason: str,
        http_status: int | None,
        file_size_bytes: int | None,
        candidate_count: int,
        rejected_syariah_count: int,
        rejected_unrelated_count: int,
    ) -> dict[str, Any]:
        return {
            "category": CATEGORY,
            "company_id": COMPANY_ID,
            "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL,
            "discovered_page_url": self.discovered_page_url,
            "pdf_url": self.pdf_url,
            "target_year": year,
            "target_month": month,
            "output_path": str(output_path),
            "status": status,
            "reason": reason,
            "discovery_method": self.discovery_method,
            "score": self.score,
            "candidate_count": candidate_count,
            "rejected_syariah_count": rejected_syariah_count,
            "rejected_unrelated_count": rejected_unrelated_count,
            "http_status": http_status,
            "file_size_bytes": file_size_bytes,
            "timestamp": current_timestamp(),
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the conventional financial report PDF for Indonesia Re.",
    )
    parser.add_argument("--year", type=positive_int, required=True, help="Target report year.")
    parser.add_argument("--month", type=month_int, required=True, help="Target report month (1-12).")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data"),
        help="Root output directory.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Discover the report without writing the PDF.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing PDF.")
    parser.add_argument(
        "--debug-html",
        action="store_true",
        help="Save HTML snapshots when the target PDF cannot be found.",
    )
    parser.add_argument(
        "--use-browser",
        action="store_true",
        help="Use Playwright to render the page when static HTML is insufficient.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds for page fetch and PDF download requests.",
    )
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def month_int(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 12:
        raise argparse.ArgumentTypeError("month must be between 1 and 12")
    return parsed


def ascii_fold(value: str | Any) -> str:
    normalized = unicodedata.normalize("NFKD", str("" if value is None else value))
    return normalized.encode("ascii", "ignore").decode("ascii")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", ascii_fold(clean_text(value))).strip().lower()


def make_soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def current_timestamp() -> str:
    return datetime.now(MANIFEST_TIMEZONE).isoformat(timespec="seconds")


def month_terms(month: int) -> list[str]:
    terms = list(MONTH_NAMES[month])
    terms.extend([f"{month:02d}", str(month)])
    return list(dict.fromkeys(terms))


def target_period_tokens(year: int, month: int) -> list[str]:
    values = [
        f"{year}{month:02d}",
        f"{year}-{month:02d}",
        f"{year}_{month:02d}",
        f"{month:02d}-{year}",
        f"{month:02d}_{year}",
        f"{month:02d}{year}",
    ]
    values.extend(f"{term} {year}" for term in month_terms(month) if not term.isdigit())
    values.extend(f"{year} {term}" for term in month_terms(month) if not term.isdigit())
    return list(dict.fromkeys(values))


def is_syariah_candidate(text: str) -> bool:
    blob = normalize_text(text)
    return bool(blob) and any(re.search(rf"\b{re.escape(term)}\b", blob) for term in SYARIAH_TERMS)


def is_unrelated_candidate(text: str) -> bool:
    blob = normalize_text(text)
    return bool(blob) and any(term in blob for term in UNRELATED_TERMS)


def is_reportish(text: str) -> bool:
    blob = normalize_text(text)
    return bool(blob) and any(term in blob for term in REPORT_TERMS)


def matches_target_period(text: str, year: int, month: int) -> bool:
    blob = normalize_text(text)
    if not blob:
        return False
    month_hit = any(re.search(rf"\b{re.escape(term)}\b", blob) for term in month_terms(month))
    year_hit = re.search(rf"\b{year}\b", blob) is not None
    numeric_hit = any(token in blob for token in target_period_tokens(year, month))
    return (month_hit and year_hit) or numeric_hit


def score_candidate(text: str, year: int, month: int) -> int:
    blob = normalize_text(text)
    score = 0
    if matches_target_period(blob, year, month):
        score += 50
    if is_reportish(blob):
        score += 25
    if "laporan keuangan konvensional" in blob or "laporan keuangan perusahaan" in blob:
        score += 30
    if blob.endswith(".pdf"):
        score += 10
    if "/uploads/" in blob or "/pdf/" in blob:
        score += 5
    return score


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session


def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return parsed._replace(fragment="").geturl()


def summarize_exception(exc: Exception | str) -> str:
    text = str(exc)
    text = text.split("\n", 1)[0]
    return re.sub(r"\s+", " ", text).strip()


def fetch_source_html(session: requests.Session, url: str, timeout: int) -> tuple[str, str, str]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    html = response.text
    content_type = response.headers.get("Content-Type", "")
    if not html.strip():
        raise RuntimeError("source page response was empty")
    return html, canonical_url(response.url), content_type


def render_source_html_with_browser(url: str, timeout: int) -> tuple[str, str]:
    if sync_playwright is None:  # pragma: no cover - optional dependency.
        raise RuntimeError("Playwright is not installed; cannot use --use-browser")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"], viewport={"width": 1440, "height": 2200})
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            page.wait_for_timeout(500)
            return page.content(), canonical_url(page.url)
        except PlaywrightTimeoutError as exc:  # pragma: no cover - browser timing varies.
            raise RuntimeError(f"browser timeout while loading {url}: {exc}") from exc
        except PlaywrightError as exc:  # pragma: no cover - browser timing varies.
            raise RuntimeError(f"browser error while loading {url}: {exc}") from exc
        finally:
            browser.close()


def extract_links(html: str, base_url: str) -> list[dict[str, str]]:
    soup = make_soup(html)
    links: list[dict[str, str]] = []
    for tag in soup.find_all("a"):
        href = clean_text(tag.get("href"))
        if not href:
            continue
        absolute_url = canonical_url(urljoin(base_url, href))
        text_parts = [
            clean_text(tag.get_text(" ", strip=True)),
            clean_text(tag.get("title")),
            clean_text(tag.get("aria-label")),
            clean_text(tag.get("download")),
        ]
        parent = tag.parent
        if parent is not None:
            parent_text = clean_text(parent.get_text(" ", strip=True))
            if parent_text and len(parent_text) <= 300:
                text_parts.append(parent_text)
        context = clean_text(" ".join(piece for piece in text_parts if piece))
        links.append({"url": absolute_url, "text": context, "raw_href": href})
    return links[:DEFAULT_MAX_LINKS_PER_PAGE]


def is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def should_follow_link(link: dict[str, str], source_url: str) -> bool:
    url = link["url"]
    if is_pdf_url(url):
        return False
    parsed = urlparse(url)
    source_parsed = urlparse(source_url)
    if parsed.netloc.lower() != source_parsed.netloc.lower():
        return False
    if parsed.path != source_parsed.path:
        return False
    return bool(re.search(r"(?:^|&)page=\d+", parsed.query))


def build_candidate(
    *,
    page_url: str,
    discovered_page_url: str,
    url: str,
    text: str,
    year: int,
    month: int,
    discovery_method: str,
) -> Candidate | None:
    blob = f"{text} {url}"
    is_syariah = is_syariah_candidate(blob)
    is_unrelated = is_unrelated_candidate(blob)
    target_match = matches_target_period(blob, year, month)
    if is_syariah or is_unrelated or not target_match:
        return None
    return Candidate(
        page_url=page_url,
        discovered_page_url=discovered_page_url,
        pdf_url=canonical_url(url),
        title=text,
        context=text,
        discovery_method=discovery_method,
        score=score_candidate(blob, year, month),
        is_syariah=is_syariah,
        is_unrelated=is_unrelated,
        target_match=target_match,
    )


def extract_candidates_from_html(
    html: str,
    base_url: str,
    year: int,
    month: int,
    discovery_method: str,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for link in extract_links(html, base_url):
        pdf_url = link["url"]
        if not is_pdf_url(pdf_url):
            continue
        candidate = build_candidate(
            page_url=SOURCE_URL,
            discovered_page_url=base_url,
            url=pdf_url,
            text=link["text"] or pdf_url,
            year=year,
            month=month,
            discovery_method=discovery_method,
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def discover_candidates(
    session: requests.Session,
    year: int,
    month: int,
    *,
    use_browser: bool,
    timeout: int,
    max_pages: int,
    max_depth: int | None = None,
    deadline: float,
) -> tuple[list[Candidate], list[dict[str, str]], str, str, str]:
    queue: deque[tuple[str, int, str]] = deque([(SOURCE_URL, 0, "static_html")])
    visited: set[str] = set()
    candidates: list[Candidate] = []
    snapshots: list[dict[str, str]] = []
    source_html = ""
    rendered_html = ""
    discovered_url = SOURCE_URL
    depth_limit = max_pages if max_depth is None else max_depth

    while queue and len(visited) < max_pages and time.monotonic() < deadline:
        current_url, depth, discovery_method = queue.popleft()
        current_url = canonical_url(current_url)
        if current_url in visited:
            continue
        visited.add(current_url)

        html = ""
        final_url = current_url
        content_type = ""
        fetch_error: str | None = None

        try:
            html, final_url, content_type = fetch_source_html(session, current_url, timeout)
        except Exception as exc:
            fetch_error = summarize_exception(exc)
            if use_browser:
                try:
                    html, final_url = render_source_html_with_browser(current_url, timeout)
                    discovery_method = "playwright"
                except Exception as browser_exc:  # noqa: BLE001
                    fetch_error = f"{fetch_error}; browser fallback failed: {summarize_exception(browser_exc)}"
                    html = ""
                    final_url = current_url
            else:
                raise

        if not source_html and final_url == canonical_url(SOURCE_URL):
            source_html = html
        if discovery_method == "playwright" and html and not rendered_html:
            rendered_html = html
        if html and not discovered_url:
            discovered_url = final_url
        if html:
            title = clean_text(make_soup(html).title.get_text(" ", strip=True) if make_soup(html).title else "")
            snapshots.append(
                {
                    "url": final_url,
                    "title": title,
                    "content_type": content_type,
                    "method": discovery_method,
                    "error": fetch_error or "",
                }
            )

        for link in extract_links(html, final_url):
            link_url = link["url"]
            link_text = link["text"]
            if not link_url:
                continue
            if is_pdf_url(link_url):
                candidate = build_candidate(
                    page_url=current_url,
                    discovered_page_url=final_url,
                    url=link_url,
                    text=link_text,
                    year=year,
                    month=month,
                    discovery_method=discovery_method,
                )
                if candidate is not None:
                    candidates.append(candidate)
                continue
            if depth < depth_limit and should_follow_link(link, SOURCE_URL):
                queue.append((link_url, depth + 1, discovery_method))

    if use_browser and not candidates and not rendered_html:
        try:
            rendered_html, rendered_url = render_source_html_with_browser(SOURCE_URL, timeout)
        except Exception as exc:  # noqa: BLE001
            LOGGER.info("browser fallback after static crawl found no candidates: %s", summarize_exception(exc))
        else:
            if rendered_html:
                source_html = rendered_html if not source_html else source_html
                discovered_url = rendered_url
                candidates = extract_candidates_from_html(rendered_html, rendered_url, year, month, "playwright")
                if rendered_html and not snapshots:
                    snapshots.append(
                        {
                            "url": rendered_url,
                            "title": clean_text(make_soup(rendered_html).title.get_text(" ", strip=True) if make_soup(rendered_html).title else ""),
                            "content_type": "text/html",
                            "method": "playwright",
                            "error": "",
                        }
                    )

    if use_browser and not rendered_html and source_html:
        rendered_html = source_html

    return candidates, snapshots, source_html, rendered_html, discovered_url


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    best_by_url: dict[str, Candidate] = {}
    for candidate in candidates:
        current = best_by_url.get(candidate.pdf_url)
        if current is None or candidate.score > current.score:
            best_by_url[candidate.pdf_url] = candidate
    return sorted(best_by_url.values(), key=lambda item: item.score, reverse=True)


def choose_candidate(candidates: list[Candidate]) -> Candidate | None:
    filtered = dedupe_candidates(candidates)
    return filtered[0] if filtered else None


def validate_pdf_bytes(data: bytes) -> bool:
    if len(data) < 16:
        return False
    if not data.startswith(b"%PDF-"):
        return False
    tail = data[-2048:] if len(data) > 2048 else data
    return b"%%EOF" in tail


def download_pdf(
    session: requests.Session,
    pdf_url: str,
    output_path: Path,
    *,
    timeout: int,
    force: bool,
) -> tuple[int | None, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        existing = output_path.read_bytes()
        if validate_pdf_bytes(existing):
            return None, len(existing)

    with session.get(pdf_url, timeout=timeout, stream=True) as response:
        status = response.status_code
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        with tempfile.NamedTemporaryFile(delete=False, dir=str(output_path.parent), suffix=".part") as tmp:
            temp_path = Path(tmp.name)
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp.write(chunk)
            finally:
                tmp.flush()

    data = temp_path.read_bytes()
    if "pdf" not in content_type and not validate_pdf_bytes(data):
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded file from {pdf_url} is not a valid PDF")
    if not validate_pdf_bytes(data):
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded file from {pdf_url} failed PDF validation")

    temp_path.replace(output_path)
    return status, len(data)


def write_manifest(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "download_manifest.csv"
    json_path = output_dir / "download_manifest.json"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
    LOGGER.info("wrote manifest: %s", csv_path)
    LOGGER.info("wrote manifest: %s", json_path)


def write_debug_html(debug_dir: Path, source_html: str, rendered_html: str, reason: str, snapshots: list[dict[str, str]]) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    if source_html:
        (debug_dir / "source_page.html").write_text(source_html, encoding="utf-8")
    if rendered_html and rendered_html != source_html:
        (debug_dir / "rendered_page.html").write_text(rendered_html, encoding="utf-8")
    (debug_dir / "reason.txt").write_text(reason + "\n", encoding="utf-8")
    (debug_dir / "snapshots.json").write_text(json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8")


def build_no_pdf_reason(
    *,
    year: int,
    month: int,
    source_url: str,
    snapshots: list[dict[str, str]],
    candidates: list[Candidate],
) -> str:
    if not candidates:
        if snapshots:
            available = ", ".join(snapshot["url"] for snapshot in snapshots[:3])
            return (
                f"no conventional monthly financial report PDF for {year}-{month:02d} was found on {source_url}; "
                f"the page was fetched successfully, but no link matched the requested month/year "
                f"after excluding syariah/sharia/UUS/islamic and unrelated report categories. "
                f"Visited pages: {available}"
            )
        return (
            f"no conventional monthly financial report PDF for {year}-{month:02d} was found on {source_url}; "
            "the page could not be rendered into any candidate links."
        )

    syariah_count = sum(1 for item in candidates if item.is_syariah)
    unrelated_count = sum(1 for item in candidates if item.is_unrelated)
    return (
        f"only rejected candidates were discovered for {year}-{month:02d}; "
        f"syariah/sharia/UUS/islamic matches: {syariah_count}; unrelated matches: {unrelated_count}."
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    period = f"{args.year:04d}-{args.month:02d}"
    output_dir = args.output_root / period / OUTPUT_SUBDIR / CATEGORY / COMPANY_ID
    output_pdf = output_dir / f"{COMPANY_ID}_{period}.pdf"
    debug_dir = output_dir / DEBUG_HTML_DIRNAME
    deadline = time.monotonic() + MAX_RUNTIME_SECONDS

    session = build_session()
    LOGGER.info("starting discovery from %s", SOURCE_URL)

    candidates: list[Candidate] = []
    snapshots: list[dict[str, str]] = []
    source_html = ""
    rendered_html = ""
    discovered_url = SOURCE_URL

    try:
        candidates, snapshots, source_html, rendered_html, discovered_url = discover_candidates(
            session,
            args.year,
            args.month,
            use_browser=args.use_browser,
            timeout=args.timeout,
            max_pages=DEFAULT_MAX_PAGES,
            deadline=deadline,
        )
    except Exception as exc:  # noqa: BLE001
        reason = summarize_exception(exc)
        write_debug_html(debug_dir, source_html, rendered_html, reason, snapshots)
        write_manifest(
            output_dir,
            [
                {
                    "category": CATEGORY,
                    "company_id": COMPANY_ID,
                    "company_name": COMPANY_NAME,
                    "source_page_url": SOURCE_URL,
                    "discovered_page_url": discovered_url,
                    "pdf_url": "",
                    "target_year": args.year,
                    "target_month": args.month,
                    "output_path": str(output_pdf),
                    "status": "failed",
                    "reason": reason,
                    "discovery_method": "playwright" if args.use_browser else "static_html",
                    "score": 0,
                    "candidate_count": 0,
                    "rejected_syariah_count": 0,
                    "rejected_unrelated_count": 0,
                    "http_status": None,
                    "file_size_bytes": None,
                    "timestamp": current_timestamp(),
                }
            ],
        )
        LOGGER.error("discovery failed: %s", reason)
        return 1

    best = choose_candidate(candidates)
    if best is None:
        reason = build_no_pdf_reason(
            year=args.year,
            month=args.month,
            source_url=SOURCE_URL,
            snapshots=snapshots,
            candidates=candidates,
        )
        write_debug_html(debug_dir, source_html, rendered_html, reason, snapshots)
        write_manifest(
            output_dir,
            [
                {
                    "category": CATEGORY,
                    "company_id": COMPANY_ID,
                    "company_name": COMPANY_NAME,
                    "source_page_url": SOURCE_URL,
                    "discovered_page_url": discovered_url,
                    "pdf_url": "",
                    "target_year": args.year,
                    "target_month": args.month,
                    "output_path": str(output_pdf),
                    "status": "not_found",
                    "reason": reason,
                    "discovery_method": "playwright" if args.use_browser else "static_html",
                    "score": 0,
                    "candidate_count": len(candidates),
                    "rejected_syariah_count": sum(1 for item in candidates if item.is_syariah),
                    "rejected_unrelated_count": sum(1 for item in candidates if item.is_unrelated),
                    "http_status": None,
                    "file_size_bytes": None,
                    "timestamp": current_timestamp(),
                }
            ],
        )
        LOGGER.error(reason)
        return 1

    if args.dry_run:
        reason = "dry-run requested; PDF discovery completed without writing the file"
        write_manifest(
            output_dir,
            [
                best.to_manifest(
                    year=args.year,
                    month=args.month,
                    output_path=output_pdf,
                    status="dry_run",
                    reason=reason,
                    http_status=None,
                    file_size_bytes=None,
                    candidate_count=len(candidates),
                    rejected_syariah_count=sum(1 for item in candidates if item.is_syariah),
                    rejected_unrelated_count=sum(1 for item in candidates if item.is_unrelated),
                )
            ],
        )
        LOGGER.info("%s", reason)
        return 0

    try:
        http_status, file_size = download_pdf(
            session,
            best.pdf_url,
            output_pdf,
            timeout=args.timeout,
            force=args.force,
        )
    except Exception as exc:  # noqa: BLE001
        reason = f"failed to download PDF: {summarize_exception(exc)}"
        write_debug_html(debug_dir, source_html, rendered_html, reason, snapshots)
        write_manifest(
            output_dir,
            [
                best.to_manifest(
                    year=args.year,
                    month=args.month,
                    output_path=output_pdf,
                    status="error",
                    reason=reason,
                    http_status=None,
                    file_size_bytes=None,
                    candidate_count=len(candidates),
                    rejected_syariah_count=sum(1 for item in candidates if item.is_syariah),
                    rejected_unrelated_count=sum(1 for item in candidates if item.is_unrelated),
                )
            ],
        )
        LOGGER.error(reason)
        return 1
    finally:
        session.close()

    write_manifest(
        output_dir,
        [
            best.to_manifest(
                year=args.year,
                month=args.month,
                output_path=output_pdf,
                status="downloaded" if http_status is not None else "skipped_exists",
                reason=(
                    "downloaded conventional financial report PDF"
                    if http_status is not None
                    else "existing valid PDF was kept"
                ),
                http_status=http_status,
                file_size_bytes=file_size,
                candidate_count=len(candidates),
                rejected_syariah_count=sum(1 for item in candidates if item.is_syariah),
                rejected_unrelated_count=sum(1 for item in candidates if item.is_unrelated),
            )
        ],
    )

    if args.debug_html:
        write_debug_html(debug_dir, source_html, rendered_html, "download completed", snapshots)

    LOGGER.info("wrote %s", output_pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
