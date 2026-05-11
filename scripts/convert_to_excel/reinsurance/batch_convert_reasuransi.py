"""Batch convert all reinsurance company PDFs to Excel for a given period.

Usage:
    python scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py [--period 2026-03]

Processes all 7 companies in parallel where possible, generating Excel files in:
    data/{period}/converted_excel/reasuransi/{company}/{company}_{period}.xlsx

Summary statistics are printed upon completion showing success/failure counts.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# List of all 7 reinsurance companies
COMPANIES = [
    "nasre",
    "tugure",
    "indonesiare",
    "orionre",
    "inare",
    "marein",
    "maipark",
]


def convert_company(company_id: str, period: str, script_dir: Path) -> tuple[str, bool, str]:
    """Convert a single company. Returns (company_id, success, message)."""
    converter_script = script_dir / f"convert_{company_id}.py"

    if not converter_script.exists():
        return company_id, False, f"Script not found: {converter_script.name}"

    try:
        result = subprocess.run(
            [sys.executable, str(converter_script), "--period", period],
            cwd=str(script_dir.parent.parent.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            if "Wrote" in result.stdout:
                return company_id, True, result.stdout.strip().split('\n')[-1]
            else:
                return company_id, False, "Conversion completed but no output file found"
        else:
            error_msg = result.stderr or result.stdout
            return company_id, False, error_msg.split('\n')[0][:80]

    except subprocess.TimeoutExpired:
        return company_id, False, "Timeout (60s)"
    except Exception as e:
        return company_id, False, str(e)[:80]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch convert all reinsurance company PDFs to Excel"
    )
    parser.add_argument(
        "--period",
        help="Report period, e.g. 2026-03 (default: current_period from config)",
        default=None,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    period = args.period

    # If no period specified, load from config
    if not period:
        try:
            import yaml
            config_periods = yaml.safe_load(
                (script_dir.parent.parent.parent / "config" / "report_periods.yml").read_text()
            )
            period = config_periods["current_period"]
        except Exception:
            print("Error: Could not determine period. Please specify with --period")
            sys.exit(1)

    print("=" * 90)
    print(f"{'BATCH CONVERT: REINSURANCE REASURANSI':^90}")
    print("=" * 90)
    print(f"Period: {period}")
    print(f"Companies: {len(COMPANIES)}")
    print(f"Workers: {args.workers}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(convert_company, company, period, script_dir): company
            for company in COMPANIES
        }

        for i, future in enumerate(as_completed(futures), 1):
            company_id, success, message = future.result()
            status = "✓" if success else "✗"
            print(f"[{i:2d}/{len(COMPANIES)}] {status} {company_id:50s}", end="")
            if not success:
                print(f" {message}")
            else:
                print()
            results.append((company_id, success, message))

    # Summary
    successful = sum(1 for _, success, _ in results if success)
    failed = len(results) - successful

    print("=" * 90)
    print(f"{'SUMMARY':^90}")
    print("=" * 90)
    print(f"Successful: {successful}/{len(COMPANIES)}")
    print(f"Failed:     {failed}/{len(COMPANIES)}")
    print(f"End time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if failed > 0:
        print(f"\n{'FAILURES':^90}")
        print("-" * 90)
        for company_id, success, message in results:
            if not success:
                print(f"  {company_id:50s} {message}")

    print("=" * 90)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
