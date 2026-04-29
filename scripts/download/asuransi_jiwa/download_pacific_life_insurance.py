"""Download financial reports for PT Pacific Life Insurance via HTML select interaction."""
import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin

from _downloader_base import (
    build_session, download_pdf, write_manifest, write_debug_html,
    current_timestamp, MONTH_LABELS
)

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import Error as PlaywrightError
except ImportError:
    sync_playwright = None
    PlaywrightTimeoutError = TimeoutError
    PlaywrightError = Exception

LOGGER = logging.getLogger("download_pacific_life_insurance")
SOURCE_URL = "https://www.pacificlife.co.id/laporan-keuangan"
COMPANY_ID = "pacific_life_insurance"
COMPANY_NAME = "PT Pacific Life Insurance"
CATEGORY = "asuransi_jiwa"


def find_pdf_via_selects(year, month, timeout):
    """Use Playwright to interact with the HTML selects and extract the PDF file path."""
    if sync_playwright is None:
        raise RuntimeError("Playwright not installed")

    month_label = MONTH_LABELS[month]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.goto(SOURCE_URL, wait_until="commit", timeout=timeout * 1000)
            page.wait_for_timeout(4000)

            page.select_option("#financial_reports_type_selector", "Laporan Keuangan")
            page.wait_for_timeout(1000)
            page.select_option("#financial_reports_year_selector", str(year))
            page.wait_for_timeout(4000)

            options = page.evaluate(
                "() => Array.from(document.querySelector('#financial_report_detail_types').options)"
                ".map(o => ({value: o.value, text: o.text}))"
            )
            # Find option matching target month
            for opt in options:
                if month_label.lower() in opt["text"].lower() and opt["value"] not in ("", "-- Pilih File --"):
                    file_path = opt["value"].lstrip("/")
                    pdf_url = urljoin(SOURCE_URL.rsplit("/", 1)[0] + "/", file_path)
                    return pdf_url, opt["text"]
            return None, None
        except PlaywrightTimeoutError as e:
            raise RuntimeError(f"browser timeout: {e}") from e
        except PlaywrightError as e:
            raise RuntimeError(f"browser error: {e}") from e
        finally:
            browser.close()


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

    LOGGER.info(f"Fetching from {SOURCE_URL} via browser select interaction")
    try:
        pdf_url, title = find_pdf_via_selects(args.year, args.month, args.timeout)
    except Exception as e:
        reason = f"browser interaction failed: {e}"
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
            "source_page_url": SOURCE_URL, "discovered_page_url": SOURCE_URL,
            "pdf_url": pdf_url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "dry_run",
            "reason": "dry-run requested", "discovery_method": "playwright_select",
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
            "discovery_method": "playwright_select",
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
