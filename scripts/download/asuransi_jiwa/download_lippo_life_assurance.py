"""Download financial reports for PT Lippo Life Assurance via Strapi API."""
import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin

from _downloader_base import (
    build_session, download_pdf, write_manifest, write_debug_html,
    current_timestamp, MONTH_NAMES
)

LOGGER = logging.getLogger("download_lippo_life_assurance")
SOURCE_URL = "https://lippolife.co.id/company/non-audited/monthly-report"
STRAPI_API = "https://strapi-rqqq74ig4a-et.a.run.app/monthly-report-page"
STRAPI_BASE = "https://strapi-rqqq74ig4a-et.a.run.app"
COMPANY_ID = "lippo_life_assurance"
COMPANY_NAME = "PT Lippo Life Assurance"
CATEGORY = "asuransi_jiwa"


def find_pdf_url(session, year, month, timeout):
    month_terms = MONTH_NAMES[month]
    resp = session.get(STRAPI_API, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    statements = data.get("financialStatements", [])
    for stmt in statements:
        title = stmt.get("title", "").lower()
        year_hit = str(year) in title
        month_hit = any(term in title for term in month_terms)
        if year_hit and month_hit:
            image_detail = stmt.get("imageDetail", {})
            pdf_path = image_detail.get("url", "")
            if pdf_path and pdf_path.endswith(".pdf"):
                return urljoin(STRAPI_BASE, pdf_path), stmt.get("title", "")
    return None, None


def main():
    parser = argparse.ArgumentParser(description=f"Download {COMPANY_NAME} financial reports")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--use-browser", action="store_true")
    parser.add_argument("--debug-html", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if not 1 <= args.month <= 12:
        return 1

    session = build_session()
    period = f"{args.year:04d}-{args.month:02d}"
    output_dir = args.output_root / period / "raw_pdf" / CATEGORY / COMPANY_ID
    output_pdf = output_dir / f"{COMPANY_ID}_{period}.pdf"
    debug_dir = output_dir / "_debug_html"

    LOGGER.info(f"Querying Strapi API for {period}")
    try:
        pdf_url, title = find_pdf_url(session, args.year, args.month, args.timeout)
    except Exception as e:
        reason = f"Strapi API failed: {e}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, "", reason)
        return 1

    if not pdf_url:
        reason = f"no PDFs found for {period}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, "", reason)
        return 1

    LOGGER.info(f"Found: {title}")
    LOGGER.info(f"URL: {pdf_url}")

    if args.dry_run:
        LOGGER.info("Dry-run complete - no download")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": STRAPI_API,
            "pdf_url": pdf_url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "dry_run",
            "reason": "dry-run requested", "discovery_method": "strapi_api",
            "score": 100, "candidate_count": 1,
            "http_status": None, "file_size_bytes": None, "timestamp": current_timestamp()
        }])
        return 0

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        status, size = download_pdf(session, pdf_url, output_pdf, timeout=args.timeout, force=args.force)
        LOGGER.info(f"Downloaded: {output_pdf} ({size} bytes)")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": STRAPI_API,
            "pdf_url": pdf_url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "downloaded" if status else "skipped_exists",
            "reason": "downloaded" if status else "existing file kept",
            "discovery_method": "strapi_api",
            "score": 100, "candidate_count": 1,
            "http_status": status, "file_size_bytes": size, "timestamp": current_timestamp()
        }])
        return 0
    except Exception as e:
        reason = f"download failed: {e}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, "", reason)
        return 1


if __name__ == "__main__":
    sys.exit(main())
