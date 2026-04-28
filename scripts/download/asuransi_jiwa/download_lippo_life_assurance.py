"""Download financial reports for PT Lippo Life Assurance."""
import argparse
import logging
import sys
from pathlib import Path

from _downloader_base import (
    build_session, extract_pdf_links, download_pdf, write_manifest, write_debug_html,
    fetch_html_static, fetch_html_browser, current_timestamp
)

LOGGER = logging.getLogger("download_lippo_life_assurance")
SOURCE_URL = "https://lippolife.co.id/company/non-audited/monthly-report"
COMPANY_ID = "lippo_life_assurance"
COMPANY_NAME = "PT Lippo Life Assurance"
CATEGORY = "asuransi_jiwa"

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
    
    LOGGER.info(f"Fetching from {SOURCE_URL}")
    
    html = None
    discovered_url = None

    try:
        if args.use_browser:
            LOGGER.info("Using Playwright browser rendering")
            html, discovered_url = fetch_html_browser(SOURCE_URL, args.timeout)
        else:
            try:
                html, discovered_url = fetch_html_static(session, SOURCE_URL, args.timeout)
                candidates = extract_pdf_links(html, discovered_url, args.year, args.month)
                if not candidates:
                    LOGGER.info("No PDFs found in static HTML, falling back to Playwright browser rendering")
                    html, discovered_url = fetch_html_browser(SOURCE_URL, args.timeout)
            except Exception as static_error:
                LOGGER.info("Static fetch failed, falling back to Playwright browser rendering")
                html, discovered_url = fetch_html_browser(SOURCE_URL, args.timeout)
    except Exception as e:
        reason = f"failed to fetch: {e}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, "", reason)
        return 1

    candidates = extract_pdf_links(html, discovered_url, args.year, args.month)
    LOGGER.info(f"Found {len(candidates)} PDF candidates for {period}")
    
    if not candidates:
        reason = f"no PDFs found for {period}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, html, reason)
        return 1
    
    best = candidates[0]
    LOGGER.info(f"Selected: {best.text}")
    
    if args.dry_run:
        LOGGER.info("Dry-run complete - no download")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": best.discovered_url,
            "pdf_url": best.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "dry_run",
            "reason": "dry-run requested", "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": best.score, "candidate_count": len(candidates),
            "http_status": None, "file_size_bytes": None, "timestamp": current_timestamp()
        }])
        return 0
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        status, size = download_pdf(session, best.url, output_pdf, timeout=args.timeout, force=args.force)
        LOGGER.info(f"Downloaded: {output_pdf} ({size} bytes)")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": best.discovered_url,
            "pdf_url": best.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "downloaded" if status else "skipped_exists",
            "reason": "downloaded" if status else "existing file kept",
            "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": best.score, "candidate_count": len(candidates),
            "http_status": status, "file_size_bytes": size, "timestamp": current_timestamp()
        }])
        return 0
    except Exception as e:
        reason = f"download failed: {e}"
        LOGGER.error(reason)
        if args.debug_html:
            write_debug_html(debug_dir, html, reason)
        return 1

if __name__ == "__main__":
    sys.exit(main())
