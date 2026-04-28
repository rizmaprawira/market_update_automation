"""Download financial reports for PT AIA Financial."""
import argparse
import logging
import sys
import time
from pathlib import Path

from _downloader_base import (
    build_session, extract_pdf_links, download_pdf, write_manifest, write_debug_html,
    fetch_html_static, fetch_html_browser, current_timestamp
)

LOGGER = logging.getLogger("download_aia")
SOURCE_URL = "https://www.aia-financial.co.id/id/about-aia/laporan-penting/report-financial"
COMPANY_ID = "aia"
COMPANY_NAME = "PT AIA Financial"
CATEGORY = "asuransi_jiwa"

def main():
    parser = argparse.ArgumentParser(description=f"Download {COMPANY_NAME} financial reports")
    parser.add_argument("--year", type=int, required=True, help="Target year")
    parser.add_argument("--month", type=int, required=True, help="Target month (1-12)")
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    parser.add_argument("--dry-run", action="store_true", help="Discovery only, no download")
    parser.add_argument("--force", action="store_true", help="Overwrite existing PDF")
    parser.add_argument("--use-browser", action="store_true", help="Use Playwright browser rendering")
    parser.add_argument("--debug-html", action="store_true", help="Save debug HTML on failure")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    
    if not 1 <= args.month <= 12:
        LOGGER.error("Month must be 1-12")
        return 1
    
    session = build_session()
    period = f"{args.year:04d}-{args.month:02d}"
    output_dir = args.output_root / period / "raw_pdf" / CATEGORY / COMPANY_ID
    output_pdf = output_dir / f"{COMPANY_ID}_{period}.pdf"
    debug_dir = output_dir / "_debug_html"
    
    LOGGER.info(f"Fetching from {SOURCE_URL}")
    
    try:
        if args.use_browser:
            LOGGER.info("Using Playwright browser rendering")
            html, discovered_url = fetch_html_browser(SOURCE_URL, args.timeout)
        else:
            html, discovered_url = fetch_html_static(session, SOURCE_URL, args.timeout)
    except Exception as e:
        reason = f"failed to fetch: {e}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, "", reason)
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": SOURCE_URL,
            "pdf_url": "", "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "failed", "reason": reason,
            "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": 0, "candidate_count": 0, "http_status": None,
            "file_size_bytes": None, "timestamp": current_timestamp()
        }])
        return 1
    
    candidates = extract_pdf_links(html, discovered_url, args.year, args.month)
    LOGGER.info(f"Found {len(candidates)} PDF candidates for {period}")
    
    if not candidates:
        reason = f"no PDFs found for {period}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, html, reason)
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": discovered_url,
            "pdf_url": "", "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "not_found", "reason": reason,
            "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": 0, "candidate_count": 0, "http_status": None,
            "file_size_bytes": None, "timestamp": current_timestamp()
        }])
        return 1
    
    best = candidates[0]
    LOGGER.info(f"Selected: {best.text}")
    LOGGER.info(f"URL: {best.url}")
    
    if args.dry_run:
        LOGGER.info("Dry-run complete - no download")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": best.discovered_url,
            "pdf_url": best.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "dry_run",
            "reason": "dry-run requested",
            "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": best.score, "candidate_count": len(candidates),
            "http_status": None, "file_size_bytes": None,
            "timestamp": current_timestamp()
        }])
        return 0
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        status, size = download_pdf(session, best.url, output_pdf, timeout=args.timeout, force=args.force)
        
        if status is None:
            LOGGER.info(f"File already exists: {output_pdf} ({size} bytes)")
            status_str = "skipped_exists"
        else:
            LOGGER.info(f"Downloaded: {output_pdf} ({size} bytes, HTTP {status})")
            status_str = "downloaded"
        
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": best.discovered_url,
            "pdf_url": best.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": status_str,
            "reason": "downloaded" if status else "existing file kept",
            "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": best.score, "candidate_count": len(candidates),
            "http_status": status, "file_size_bytes": size,
            "timestamp": current_timestamp()
        }])
        
        if args.debug_html:
            write_debug_html(debug_dir, html, "download completed")
        
        return 0
    except Exception as e:
        reason = f"download failed: {e}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, html, reason)
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": best.discovered_url,
            "pdf_url": best.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "error", "reason": reason,
            "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": best.score, "candidate_count": len(candidates),
            "http_status": None, "file_size_bytes": None,
            "timestamp": current_timestamp()
        }])
        return 1

if __name__ == "__main__":
    sys.exit(main())
