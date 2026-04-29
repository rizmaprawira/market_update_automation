"""Download financial reports for PT Asuransi Dayin Mitra Tbk.."""
import argparse
import logging
import sys
import time
from pathlib import Path

from _downloader_base import (
    build_session, extract_pdf_links, download_pdf, write_manifest, write_debug_html,
    fetch_html_static, fetch_html_browser, fetch_html_browser_domready,
    fetch_html_with_smart_fallback, current_timestamp, MONTH_NAMES
)

LOGGER = logging.getLogger("download_pt_asuransi_dayin_mitra_tbk")
SOURCE_URL = "https://asuransidayinmitra.com/?page_id=1481"
COMPANY_ID = "pt_asuransi_dayin_mitra_tbk"
COMPANY_NAME = "PT Asuransi Dayin Mitra Tbk."
CATEGORY = "asuransi_umum"

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
        browser_timeout = max(args.timeout, 60)
        LOGGER.info(f"Using browser with domcontentloaded (timeout={browser_timeout}s)")
        html, discovered_url = fetch_html_browser_domready(SOURCE_URL, browser_timeout, extra_wait_ms=3000)
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
            "timestamp": current_timestamp()
        }])
        return 1
    
    candidates = extract_pdf_links(html, discovered_url, args.year, args.month)
    
    if not candidates:
        reason = "no PDF candidates found"
        LOGGER.warning(reason)
        if args.debug_html:
            write_debug_html(debug_dir, html, reason)
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": discovered_url,
            "pdf_url": "", "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "no_pdf_found", "reason": reason,
            "timestamp": current_timestamp()
        }])
        return 0
    
    # Prefer candidate whose link text explicitly names the target month
    month_variants = MONTH_NAMES[args.month]
    text_matched = [c for c in candidates if any(m in c.text.lower() for m in month_variants)]
    selected_candidate = text_matched[0] if text_matched else candidates[0]
    LOGGER.info(f"Selected: {selected_candidate.text[:60]}")
    
    if args.dry_run:
        LOGGER.info(f"Dry-run: would download from {selected_candidate.url}")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": discovered_url,
            "pdf_url": selected_candidate.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "dry_run", "reason": "dry-run mode",
            "timestamp": current_timestamp()
        }])
        return 0
    
    if output_pdf.exists() and not args.force:
        LOGGER.info(f"PDF already exists at {output_pdf}")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": discovered_url,
            "pdf_url": selected_candidate.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "already_exists", "reason": "file exists",
            "timestamp": current_timestamp()
        }])
        return 0
    
    success, reason = download_pdf(
        session, selected_candidate.url, output_pdf, timeout=args.timeout
    )
    
    write_manifest(output_dir, [{
        "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
        "source_page_url": SOURCE_URL, "discovered_page_url": discovered_url,
        "pdf_url": selected_candidate.url, "target_year": args.year, "target_month": args.month,
        "output_path": str(output_pdf), "status": "success" if success else "failed",
        "reason": reason, "timestamp": current_timestamp()
    }])
    
    if success:
        LOGGER.info(f"Successfully downloaded to {output_pdf}")
    else:
        LOGGER.error(f"Failed to download: {reason}")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
