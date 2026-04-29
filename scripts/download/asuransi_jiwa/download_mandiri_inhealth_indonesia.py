"""Download financial reports for PT Asuransi Jiwa Mandiri Inhealth Indonesia."""
import argparse
import logging
import re
import sys
from pathlib import Path

from _downloader_base import (
    build_session, download_pdf, write_manifest, write_debug_html,
    fetch_html_static, current_timestamp, MONTH_NAMES
)

LOGGER = logging.getLogger("download_mandiri_inhealth_indonesia")
SOURCE_URL = "https://www.inhealth.co.id/id/gcg"
PDF_BASE = "https://www.inhealth.co.id/api/cms/preview/"
COMPANY_ID = "mandiri_inhealth_indonesia"
COMPANY_NAME = "PT Asuransi Jiwa Mandiri Inhealth Indonesia"
CATEGORY = "asuransi_jiwa"


def find_pdf_filename(html, year, month):
    """Extract PDF filename from Next.js SSR data embedded in page."""
    month_terms = MONTH_NAMES[month]
    year_str = str(year)

    # All laporan_keuangan PDF filenames are embedded in Next.js __next_f push data
    filenames = re.findall(r'laporan_keuangan[^"\'<>\s\\]+\.pdf', html)
    for fname in filenames:
        fname_lower = fname.lower()
        year_hit = year_str in fname_lower
        month_hit = any(term in fname_lower for term in month_terms)
        if year_hit and month_hit:
            return fname
    return None


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

    LOGGER.info(f"Fetching page source from {SOURCE_URL}")
    try:
        html, _ = fetch_html_static(session, SOURCE_URL, args.timeout)
    except Exception as e:
        reason = f"failed to fetch: {e}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, "", reason)
        return 1

    filename = find_pdf_filename(html, args.year, args.month)
    if not filename:
        reason = f"no PDFs found for {period}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, html, reason)
        return 1

    pdf_url = PDF_BASE + filename
    LOGGER.info(f"Found: {filename}")
    LOGGER.info(f"URL: {pdf_url}")

    if args.dry_run:
        LOGGER.info("Dry-run complete - no download")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": SOURCE_URL,
            "pdf_url": pdf_url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "dry_run",
            "reason": "dry-run requested", "discovery_method": "nextjs_ssr",
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
            "source_page_url": SOURCE_URL, "discovered_page_url": SOURCE_URL,
            "pdf_url": pdf_url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "downloaded" if status else "skipped_exists",
            "reason": "downloaded" if status else "existing file kept",
            "discovery_method": "nextjs_ssr",
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
