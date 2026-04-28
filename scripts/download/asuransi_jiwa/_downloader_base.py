"""Base downloader for life insurance company financial reports."""
import csv
import json
import logging
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightError = Exception
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None

LOGGER = logging.getLogger("downloader_base")

MONTH_NAMES = {
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}

MANIFEST_TIMEZONE = ZoneInfo("Asia/Jakarta")
MANIFEST_FIELDS = [
    "category", "company_id", "company_name", "source_page_url", 
    "discovered_page_url", "pdf_url", "target_year", "target_month",
    "output_path", "status", "reason", "discovery_method", "score",
    "candidate_count", "http_status", "file_size_bytes", "timestamp"
]

@dataclass(frozen=True)
class PDFCandidate:
    url: str
    text: str
    score: int
    discovered_url: str

def current_timestamp():
    return datetime.now(MANIFEST_TIMEZONE).isoformat(timespec="seconds")

def build_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.3,
                  status_forcelist=(429, 500, 502, 503, 504))
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def normalize_text(text):
    text = str(text).lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def month_terms(month):
    terms = list(MONTH_NAMES[month])
    terms.extend([f"{month:02d}", str(month)])
    return list(dict.fromkeys(terms))

def matches_target_period(text, year, month):
    blob = normalize_text(text)
    if not blob:
        return False
    month_hit = any(term in blob for term in month_terms(month))
    year_hit = str(year) in blob
    return month_hit and year_hit

def score_candidate(text, year, month):
    blob = normalize_text(text)
    score = 0
    if matches_target_period(blob, year, month):
        score += 50
    if "laporan" in blob and "keuangan" in blob:
        score += 30
    if "bulanan" in blob or "monthly" in blob:
        score += 20
    if blob.endswith("pdf"):
        score += 10
    return score

def extract_pdf_links(html, base_url, year, month):
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []
    
    for link in soup.find_all('a'):
        href = link.get('href', '').strip()
        if not href or not href.lower().endswith('.pdf'):
            continue
        
        text = link.get_text(strip=True)
        url = urljoin(base_url, href)
        
        if matches_target_period(text + " " + url, year, month):
            score = score_candidate(text + " " + url, year, month)
            candidates.append(PDFCandidate(url=url, text=text, score=score, discovered_url=base_url))
    
    return sorted(candidates, key=lambda x: x.score, reverse=True)

def validate_pdf(data):
    if len(data) < 16:
        return False
    if not data.startswith(b"%PDF-"):
        return False
    return b"%%EOF" in data[-2048:] if len(data) > 2048 else True

def fetch_html_static(session, url, timeout):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text, url

def fetch_html_browser(url, timeout):
    if sync_playwright is None:
        raise RuntimeError("Playwright not installed; pip install playwright && playwright install chromium")
    
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"], viewport={"width": 1440, "height": 2200})
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            page.wait_for_timeout(500)
            html = page.content()
            final_url = page.url
            return html, final_url
        except PlaywrightTimeoutError as e:
            raise RuntimeError(f"browser timeout: {e}") from e
        except PlaywrightError as e:
            raise RuntimeError(f"browser error: {e}") from e
        finally:
            browser.close()

def download_pdf(session, url, output_path, timeout=30, force=False):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if output_path.exists() and not force:
        existing = output_path.read_bytes()
        if validate_pdf(existing):
            return None, len(existing)
    
    with session.get(url, timeout=timeout, stream=True) as response:
        status = response.status_code
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, dir=str(output_path.parent), suffix=".part") as tmp:
            temp_path = Path(tmp.name)
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)
            tmp.flush()
    
    data = temp_path.read_bytes()
    if not validate_pdf(data):
        temp_path.unlink()
        raise RuntimeError(f"Invalid PDF from {url}")
    
    temp_path.replace(output_path)
    return status, len(data)

def write_manifest(output_dir, rows):
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "download_manifest.csv"
    json_path = output_dir / "download_manifest.json"
    
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    
    LOGGER.info(f"wrote manifest: {csv_path}")

def write_debug_html(debug_dir, html, reason):
    debug_dir.mkdir(parents=True, exist_ok=True)
    if html:
        (debug_dir / "page.html").write_text(html, encoding="utf-8")
    (debug_dir / "reason.txt").write_text(reason + "\n", encoding="utf-8")
    LOGGER.info(f"wrote debug html: {debug_dir}")
