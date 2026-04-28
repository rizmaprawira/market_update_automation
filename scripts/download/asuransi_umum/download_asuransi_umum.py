"""Orchestrate downloads for all 71 general insurance companies."""
import argparse
import csv
import logging
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from collections import defaultdict

LOGGER = logging.getLogger("download_asuransi_umum")
SCRIPT_DIR = Path(__file__).parent
CATEGORY = "asuransi_umum"


def get_all_company_scripts():
    """Return sorted list of all download_*.py scripts."""
    scripts = sorted(SCRIPT_DIR.glob("download_pt_*.py"))
    return [s for s in scripts if s.is_file()]


def run_single_company(script_path, year, month, dry_run=False, timeout=30, use_browser=False):
    """Run a single company's download script and return results."""
    company_id = script_path.stem.replace("download_", "")

    cmd = [
        "python", str(script_path),
        "--year", str(year),
        "--month", str(month),
        "--timeout", str(timeout)
    ]

    if dry_run:
        cmd.append("--dry-run")

    if use_browser:
        cmd.append("--use-browser")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 10
        )

        output = result.stdout + result.stderr

        # Determine status from output
        if "Successfully downloaded" in output:
            status = "success"
            reason = "Downloaded"
        elif "Dry-run complete" in output or "Dry-run:" in output:
            status = "dry_run"
            reason = "Dry-run (PDF found)"
        elif "no PDF candidates found" in output:
            status = "no_pdf"
            reason = "No PDF found"
        elif "403" in output or "Forbidden" in output:
            status = "rate_limited"
            reason = "Rate limited (403)"
        elif "already exists" in output or "already_exists" in output:
            status = "already_exists"
            reason = "Already downloaded"
        elif "timeout" in output.lower() or result.returncode == 124:
            status = "timeout"
            reason = "Connection timeout"
        elif "wrote manifest" in output and result.returncode == 0:
            status = "dry_run"
            reason = "Dry-run (PDF found)"
        elif result.returncode != 0:
            status = "error"
            reason = f"Error (exit code {result.returncode})"
        else:
            status = "unknown"
            reason = "Unknown status"

        return {
            "company_id": company_id,
            "status": status,
            "reason": reason,
            "returncode": result.returncode,
            "output_snippet": output.split('\n')[-3:-1]
        }

    except subprocess.TimeoutExpired:
        return {
            "company_id": company_id,
            "status": "timeout",
            "reason": "Script timeout",
            "returncode": 124,
            "output_snippet": []
        }
    except Exception as e:
        return {
            "company_id": company_id,
            "status": "error",
            "reason": f"Exception: {str(e)[:50]}",
            "returncode": -1,
            "output_snippet": []
        }


def main():
    parser = argparse.ArgumentParser(
        description="Download financial reports for all 71 general insurance companies"
    )
    parser.add_argument("--year", type=int, required=True, help="Target year")
    parser.add_argument("--month", type=int, required=True, help="Target month (1-12)")
    parser.add_argument("--dry-run", action="store_true", help="Discovery only, no download")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel workers (default: 1)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per script in seconds")
    parser.add_argument("--use-browser", action="store_true", help="Use browser rendering")
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    args = parser.parse_args()

    if not 1 <= args.month <= 12:
        print("Error: Month must be 1-12")
        return 1

    if args.parallel < 1:
        print("Error: Parallel workers must be >= 1")
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    period = f"{args.year:04d}-{args.month:02d}"
    scripts = get_all_company_scripts()

    print("\n" + "="*80)
    print(f"ASURANSI UMUM BATCH DOWNLOADER - {period}")
    print("="*80)
    print(f"Total companies: {len(scripts)}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'DOWNLOAD'}")
    print(f"Parallel workers: {args.parallel}")
    print(f"Timeout per script: {args.timeout}s")
    if args.use_browser:
        print(f"Browser rendering: ENABLED")
    print("="*80 + "\n")

    # Run downloads
    results = []
    start_time = time.time()

    if args.parallel == 1:
        # Sequential execution
        for idx, script in enumerate(scripts, 1):
            company_id = script.stem.replace("download_", "")
            print(f"[{idx:2d}/{len(scripts)}] {company_id}...", end=" ", flush=True)

            result = run_single_company(
                script, args.year, args.month,
                dry_run=args.dry_run,
                timeout=args.timeout,
                use_browser=args.use_browser
            )
            results.append(result)

            # Status indicator
            if result["status"] == "success":
                print(f"✅ {result['reason']}")
            elif result["status"] == "dry_run":
                print(f"✓ {result['reason']}")
            elif result["status"] == "no_pdf":
                print(f"❌ {result['reason']}")
            elif result["status"] == "rate_limited":
                print(f"⚠️  {result['reason']}")
            elif result["status"] == "timeout":
                print(f"⏱️  {result['reason']}")
            elif result["status"] == "already_exists":
                print(f"📦 {result['reason']}")
            else:
                print(f"❓ {result['reason']}")
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(
                    run_single_company, script, args.year, args.month,
                    args.dry_run, args.timeout, args.use_browser
                ): script for script in scripts
            }

            completed = 0
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                results.append(result)

                company_id = result["company_id"]
                status_icon = {
                    "success": "✅",
                    "dry_run": "✓",
                    "no_pdf": "❌",
                    "rate_limited": "⚠️ ",
                    "timeout": "⏱️ ",
                    "already_exists": "📦",
                    "error": "❓"
                }.get(result["status"], "?")

                print(f"[{completed:2d}/{len(scripts)}] {status_icon} {company_id}: {result['reason']}")

    elapsed = time.time() - start_time

    # Aggregate results
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    summary = defaultdict(int)
    for result in results:
        summary[result["status"]] += 1

    status_labels = {
        "success": "✅ Downloaded",
        "dry_run": "✓ Found (dry-run)",
        "no_pdf": "❌ No PDF found",
        "rate_limited": "⚠️  Rate limited",
        "timeout": "⏱️  Timeout",
        "already_exists": "📦 Already exists",
        "error": "❓ Error"
    }

    for status, label in status_labels.items():
        count = summary[status]
        if count > 0:
            pct = (count / len(results)) * 100
            print(f"{label:25s}: {count:3d} ({pct:5.1f}%)")

    print(f"\nTotal time: {elapsed:.1f}s ({elapsed/len(results):.1f}s per company)")
    print("="*80)

    # Save detailed report
    report_path = args.output_root / period / "raw_pdf" / CATEGORY / "batch_report.csv"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["company_id", "status", "reason", "returncode"])
        writer.writeheader()
        for result in results:
            writer.writerow({
                "company_id": result["company_id"],
                "status": result["status"],
                "reason": result["reason"],
                "returncode": result["returncode"]
            })

    print(f"\nDetailed report saved to: {report_path}")

    # Summary by status
    print(f"\nBreakdown:")
    print(f"  Working companies:  {summary['success'] + summary['dry_run']}")
    print(f"  No public PDFs:     {summary['no_pdf']}")
    print(f"  Rate limited:       {summary['rate_limited']}")
    print(f"  Timeouts:           {summary['timeout']}")
    print(f"  Errors:             {summary['error'] + summary.get('unknown', 0)}")

    # Determine exit code
    total_success = summary['success'] + summary['dry_run'] + summary['already_exists']
    if total_success == len(results):
        print(f"\n✅ All {len(results)} companies processed successfully!")
        return 0
    elif total_success >= len(results) * 0.7:
        print(f"\n✓ {total_success}/{len(results)} companies successful")
        return 0
    else:
        print(f"\n⚠️  Only {total_success}/{len(results)} companies successful")
        return 1


if __name__ == "__main__":
    sys.exit(main())
