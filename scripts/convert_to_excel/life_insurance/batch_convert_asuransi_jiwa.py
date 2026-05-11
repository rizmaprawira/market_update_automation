"""Batch convert all life insurance (asuransi jiwa) company PDFs to Excel.

Usage:
    python scripts/convert_to_excel/life_insurance/batch_convert_asuransi_jiwa.py [--period 2026-03] [--workers 4]

Converts all companies with available PDFs and configuration files.
Progress is displayed in real-time with summary statistics.
"""

import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.path_utils import load_current_period, resolve_path
from common.pdf_extractor import extract_pdf_rows
from common.template_filler import fill_template

SEGMENT = "asuransi_jiwa"
CONFIG_DIR = Path(__file__).parent / "configs"


def convert_company(company_id: str, period: str) -> tuple[str, bool, str]:
    """Convert a single company's PDF. Returns (company_id, success, message)."""
    try:
        config_path = CONFIG_DIR / f"{company_id}.yml"
        if not config_path.exists():
            return company_id, False, "Config not found"

        config = yaml.safe_load(config_path.read_text())

        # Resolve paths
        pdf_dir = resolve_path("raw_pdf", period, SEGMENT, company_id)
        out_dir = resolve_path("converted_excel", period, SEGMENT, company_id)

        sep = config.get("pdf_period_sep", "-")
        period_file = period.replace("-", sep)

        pdf_path = pdf_dir / f"{company_id}_{period_file}.pdf"
        out_path = out_dir / f"{company_id}_{period}.xlsx"

        if not pdf_path.exists():
            return company_id, False, "PDF not found"

        # Extract rows
        rows = extract_pdf_rows(pdf_path, config)

        # Fill template
        fill_template(rows, config, period, out_path)

        return company_id, True, f"Converted {len(rows)} rows"

    except Exception as e:
        return company_id, False, f"Error: {str(e)[:50]}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch convert all life insurance PDFs to Excel"
    )
    parser.add_argument(
        "--period", help="Report period (default: current_period from config)"
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Number of parallel workers (default: 4)"
    )
    args = parser.parse_args()

    period = args.period or load_current_period()

    # Find all company configs
    company_ids = sorted([
        p.stem.replace("pt_", "").replace(".yml", "")
        for p in CONFIG_DIR.glob("pt_*.yml")
    ])

    # Add back the pt_ prefix for the actual file/ID
    company_ids = [f"pt_{cid}" for cid in company_ids]

    print(f"🔄 Life Insurance Batch Converter")
    print(f"   Period: {period}")
    print(f"   Companies: {len(company_ids)}")
    print(f"   Workers: {args.workers}")
    print()

    start_time = datetime.now()
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(convert_company, cid, period): cid for cid in company_ids
        }

        completed = 0
        for future in as_completed(futures):
            company_id, success, message = future.result()
            results.append((company_id, success, message))
            completed += 1

            status = "✓" if success else "✗"
            print(f"[{completed:2d}/{len(company_ids)}] {status} {company_id:45s} {message}")

    elapsed = (datetime.now() - start_time).total_seconds()

    # Summary
    successful = sum(1 for _, success, _ in results if success)
    failed = len(results) - successful

    print()
    print("=" * 75)
    print(f"📊 Summary: {successful} successful, {failed} failed in {elapsed:.1f}s")
    print("=" * 75)

    if failed > 0:
        print("\n⚠️  Failed conversions:")
        for company_id, success, message in results:
            if not success:
                print(f"   {company_id:45s} {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
