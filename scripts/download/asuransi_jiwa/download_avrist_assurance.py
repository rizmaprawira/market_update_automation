"""Download financial reports for PT Avrist Assurance."""
import argparse
import logging
import sys
from pathlib import Path
from urllib.parse import quote

import urllib3

from _downloader_base import (
    build_session, discover_download_candidate, download_pdf, write_manifest, write_debug_html,
    fetch_html_static, fetch_html_browser, current_timestamp, validate_pdf
)

LOGGER = logging.getLogger("download_avrist_assurance")
SOURCE_URL = "https://www.avrist.com/tentang-avrist-life/tentang-avrist-life?tab=Laporan+Perusahaan"
COMPANY_ID = "avrist_assurance"
COMPANY_NAME = "PT Avrist Assurance"
CATEGORY = "asuransi_jiwa"
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def try_avrist_pdf_variants(session, year, month, timeout):
    month_names = {
        1: ("Jan", "Januari"),
        2: ("Feb", "Februari"),
        3: ("Mar", "Maret"),
        4: ("Apr", "April"),
        5: ("Mei", "Mei"),
        6: ("Jun", "Juni"),
        7: ("Jul", "Juli"),
        8: ("Agu", "Agustus"),
        9: ("Sep", "September"),
        10: ("Okt", "Oktober"),
        11: ("Nov", "November"),
        12: ("Des", "Desember"),
    }
    month_abbrev, month_full = month_names[month]
    year_str = str(year)
    base_urls = [
        f"https://avrist.com/PDF/Financial%20Report/{year_str}/",
        f"https://assets.avrist.com/PDF/Financial%20Report/{year_str}/",
    ]
    patterns = [
        f"Web Published_Lap Keu {month_abbrev} {year_str}_Syariah.pdf",
        f"Web Published_Lap Keu {month_abbrev} {year_str}_Konvensional.pdf",
        f"Laporan Keuangan Syariah {month_full} {year_str}.pdf",
        f"Laporan Keuangan Konvensional {month_full} {year_str}.pdf",
        f"Laporan Keuangan PT Avrist Assurance {year_str} Q{(month - 1) // 3 + 1}.pdf",
        f"Laporan Keuangan PT Avrist Assurance {year_str} Q{(month - 1) // 3 + 1} - konvensional - syariah-.pdf",
    ]
    for base_url in base_urls:
        for pattern in patterns:
            candidate_url = base_url + quote(pattern)
            try:
                response = session.get(candidate_url, timeout=timeout, stream=True, verify=False)
                if response.status_code != 200:
                    continue
                content = response.content
                if validate_pdf(content):
                    return candidate_url
            except Exception:
                continue
    return None


def download_avrist_pdf(session, url, output_path, timeout, force=False):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not force:
        existing = output_path.read_bytes()
        if validate_pdf(existing):
            return None, len(existing)

    with session.get(url, timeout=timeout, stream=True, verify=False) as response:
        status = response.status_code
        response.raise_for_status()
        with output_path.with_suffix(".part").open("wb") as tmp:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)

    data = output_path.with_suffix(".part").read_bytes()
    if not validate_pdf(data):
        output_path.with_suffix(".part").unlink(missing_ok=True)
        raise RuntimeError(f"Invalid PDF from {url}")

    output_path.with_suffix(".part").replace(output_path)
    return status, len(data)

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
        return 1
    
    try:
        best = discover_download_candidate(session, html, discovered_url, args.year, args.month, timeout=args.timeout)
        LOGGER.info(f"Selected: {best.text}")
        LOGGER.info(f"URL: {best.url}")
    except Exception:
        fallback_url = try_avrist_pdf_variants(session, args.year, args.month, args.timeout)
        if fallback_url is None:
            reason = f"no PDFs found for {period}"
            LOGGER.error(reason)
            if args.debug_html:
                write_debug_html(debug_dir, html, reason)
            return 1
        best = type("Best", (), {
            "url": fallback_url,
            "text": f"Avrist PDF {period}",
            "score": 100,
            "discovered_url": discovered_url,
        })()
        LOGGER.info(f"Selected: {best.text}")
        LOGGER.info(f"URL: {best.url}")
    
    if args.dry_run:
        LOGGER.info("Dry-run complete - no download")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": best.discovered_url,
            "pdf_url": best.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "dry_run",
            "reason": "dry-run requested", "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": best.score, "candidate_count": 1,
            "http_status": None, "file_size_bytes": None, "timestamp": current_timestamp()
        }])
        return 0
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if "avrist.com" in best.url or "assets.avrist.com" in best.url:
            status, size = download_avrist_pdf(session, best.url, output_pdf, timeout=args.timeout, force=args.force)
        else:
            status, size = download_pdf(session, best.url, output_pdf, timeout=args.timeout, force=args.force)
        LOGGER.info(f"Downloaded: {output_pdf} ({size} bytes)")
        write_manifest(output_dir, [{
            "category": CATEGORY, "company_id": COMPANY_ID, "company_name": COMPANY_NAME,
            "source_page_url": SOURCE_URL, "discovered_page_url": best.discovered_url,
            "pdf_url": best.url, "target_year": args.year, "target_month": args.month,
            "output_path": str(output_pdf), "status": "downloaded" if status else "skipped_exists",
            "reason": "downloaded" if status else "existing file kept",
            "discovery_method": "playwright" if args.use_browser else "static_html",
            "score": best.score, "candidate_count": 1,
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
