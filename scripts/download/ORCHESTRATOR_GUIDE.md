# Batch Download Orchestrators - Complete Guide

Two main orchestrator scripts that run all companies in one command:

- **`scripts/download/asuransi_jiwa/download_asuransi_jiwa.py`** — All 48 life insurance companies
- **`scripts/download/asuransi_umum/download_asuransi_umum.py`** — All 71 general insurance companies

## Quick Start

### Download all companies for a specific month

```bash
# Life Insurance - March 2026
python scripts/download/asuransi_jiwa/download_asuransi_jiwa.py --year 2026 --month 3

# General Insurance - March 2026
python scripts/download/asuransi_umum/download_asuransi_umum.py --year 2026 --month 3
```

### Dry-run (find PDFs without downloading)

```bash
python scripts/download/asuransi_jiwa/download_asuransi_jiwa.py --year 2026 --month 3 --dry-run
python scripts/download/asuransi_umum/download_asuransi_umum.py --year 2026 --month 3 --dry-run
```

### Speed up with parallel workers

```bash
# Use 5 parallel workers (10x faster!)
python scripts/download/asuransi_umum/download_asuransi_umum.py \
  --year 2026 --month 3 --dry-run --parallel 5
```

## Command-line Options

### Required Arguments
- `--year YYYY` — Target report year (e.g., 2026)
- `--month M` — Target month 1-12 (e.g., 3 for March)

### Optional Arguments
- `--dry-run` — Discover PDFs without downloading (default: false)
- `--parallel N` — Number of parallel workers (default: 1)
  - `--parallel 1` — Sequential (safe, shows progress)
  - `--parallel 5` — 5 concurrent downloads (5-10x faster)
  - `--parallel 10` — 10 concurrent (fastest, may trigger rate limits)
- `--timeout SECONDS` — HTTP timeout per script (default: 30)
- `--use-browser` — Enable browser rendering for JavaScript-heavy sites (default: false)
- `--output-root PATH` — Output directory (default: `data`)

## Usage Examples

### Example 1: Quick discovery (all companies, no download)

```bash
# Check which companies have PDFs for March 2026 (fast with parallel)
python scripts/download/asuransi_umum/download_asuransi_umum.py \
  --year 2026 --month 3 --dry-run --parallel 10

# Takes ~20 seconds instead of ~120 seconds
```

### Example 2: Full download with sequential processing

```bash
# Download all PDFs for March 2026 (shows each company)
python scripts/download/asuransi_jiwa/download_asuransi_jiwa.py \
  --year 2026 --month 3

# Good for monitoring progress, takes ~75 seconds
```

### Example 3: Full download with parallel processing

```bash
# Download all PDFs using 5 workers (5x faster)
python scripts/download/asuransi_umum/download_asuransi_umum.py \
  --year 2026 --month 3 --parallel 5

# Takes ~20-30 seconds instead of ~100-120 seconds
```

### Example 4: Next month (just change the parameters)

```bash
# April 2026
python scripts/download/asuransi_umum/download_asuransi_umum.py \
  --year 2026 --month 4 --parallel 5

# May 2026
python scripts/download/asuransi_umum/download_asuransi_umum.py \
  --year 2026 --month 5 --parallel 5
```

## Output & Results

### Real-time Progress

```
================================================================================
ASURANSI UMUM BATCH DOWNLOADER - 2026-03
================================================================================
Total companies: 71
Mode: DRY-RUN
Parallel workers: 1
Timeout per script: 30s
================================================================================

[1/71] pt_aig_insurance_indonesia... ✓ Dry-run (PDF found)
[2/71] pt_arthagraha_general_insurance... ✓ Dry-run (PDF found)
[3/71] pt_asuransi_allianz_utama_indonesia... ✓ Dry-run (PDF found)
...
```

### Status Indicators

- ✅ **Downloaded** — PDF successfully downloaded
- ✓ **Dry-run (PDF found)** — PDF found but not downloaded (dry-run mode)
- ❌ **No PDF found** — Company doesn't publish downloadable reports
- ⚠️ **Rate limited** — Server returned 403 (WAF/rate limiting)
- 📦 **Already exists** — PDF already downloaded, not overwriting
- ⏱️ **Timeout** — Connection timed out
- ❓ **Error** — Other error (check logs)

### Summary Report

```
================================================================================
SUMMARY
================================================================================
✓ Found (dry-run)        :  32 ( 45.1%)
❌ No PDF found           :  32 ( 45.1%)
⚠️  Rate limited         :   3 (  4.2%)
❓ Error                  :   4 (  5.6%)

Total time: 19.2s (0.3s per company)
================================================================================

Detailed report saved to: data/2026-03/raw_pdf/asuransi_umum/batch_report.csv

Breakdown:
  Working companies:  32
  No public PDFs:     32
  Rate limited:       3
  Timeouts:           0
  Errors:             4
```

### Detailed CSV Report

Each batch run generates a detailed CSV at:
```
data/{YYYY-MM}/raw_pdf/{segment}/batch_report.csv
```

Contents:
```csv
company_id,status,reason,returncode
pt_aig_insurance_indonesia,dry_run,Dry-run (PDF found),0
pt_arthagraha_general_insurance,dry_run,Dry-run (PDF found),0
pt_asuransi_allianz_utama_indonesia,dry_run,Dry-run (PDF found),0
pt_asuransi_artarindo,no_pdf,No PDF found,0
...
```

## Performance

### Timing Comparison

| Scenario | Sequential (--parallel 1) | Parallel 5 (--parallel 5) | Speedup |
|----------|---------------------------|--------------------------|---------|
| Asuransi Umum (71 cos) | ~110s | ~20s | 5.5x |
| Asuransi Jiwa (48 cos) | ~75s | ~15s | 5x |

### When to use each mode

- **Sequential (`--parallel 1`)** — Safe, shows real-time progress, good for monitoring
- **Parallel 3-5 (`--parallel 3-5`)** — Good balance, 4-5x faster, minimal rate limit risk
- **Parallel 10+ (`--parallel 10+`)** — Very fast, but may trigger rate limiting on sensitive sites

## Automation Examples

### Monthly batch in a shell script

```bash
#!/bin/bash
# download_monthly.sh

YEAR=2026
MONTH=3

echo "Downloading asuransi_jiwa for ${YEAR}-${MONTH}..."
python scripts/download/asuransi_jiwa/download_asuransi_jiwa.py \
  --year $YEAR --month $MONTH --parallel 5

echo "Downloading asuransi_umum for ${YEAR}-${MONTH}..."
python scripts/download/asuransi_umum/download_asuransi_umum.py \
  --year $YEAR --month $MONTH --parallel 5

echo "Done!"
```

### Monthly batch in Python

```python
import subprocess
from pathlib import Path

year, month = 2026, 3

for segment, script in [
    ("asuransi_jiwa", "scripts/download/asuransi_jiwa/download_asuransi_jiwa.py"),
    ("asuransi_umum", "scripts/download/asuransi_umum/download_asuransi_umum.py"),
]:
    print(f"Downloading {segment} for {year}-{month:02d}...")
    result = subprocess.run([
        "python", script,
        "--year", str(year),
        "--month", str(month),
        "--parallel", "5"
    ])
    if result.returncode != 0:
        print(f"❌ Failed: {segment}")
    else:
        print(f"✅ Completed: {segment}")
```

### Cron job (runs monthly on the 1st)

```bash
# /etc/cron.d/insurance_reports
# Run at 2 AM on the 1st of each month
0 2 1 * * cd /home/user/IndonesiaRe/market_update && \
  python scripts/download/asuransi_jiwa/download_asuransi_jiwa.py \
    --year $(date +\%Y) --month $(date +\%m) --parallel 5 >> \
    logs/download_$(date +\%Y\%m).log 2>&1
```

## Troubleshooting

### Q: Some companies are showing errors
**A:** This is normal. Check the batch_report.csv to see which companies failed. Then:
1. Try with `--use-browser` flag to handle JavaScript-rendered content
2. Check individual company scripts: `python scripts/download/{segment}/download_{company_id}.py --year 2026 --month 3 --debug-html`
3. Increase `--timeout` if you see timeout errors

### Q: Rate limiting is blocking downloads (too many 403 errors)
**A:** Reduce parallel workers or add delays:
```bash
# Use only 2 parallel workers instead of 5
python scripts/download/asuransi_umum/download_asuransi_umum.py \
  --year 2026 --month 3 --parallel 2
```

### Q: How do I download specific companies only?
**A:** Run individual scripts instead:
```bash
# Download just 3 companies
python scripts/download/asuransi_umum/download_pt_aig_insurance_indonesia.py --year 2026 --month 3
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3
python scripts/download/asuransi_umum/download_pt_chubb_general_insurance_indonesia.py --year 2026 --month 3
```

### Q: Can I resume a partial batch?
**A:** Yes! Just re-run the command. Existing files won't be re-downloaded. To force re-download:
```bash
# This would need to be done per-company, e.g.:
python scripts/download/asuransi_umum/download_pt_aig_insurance_indonesia.py \
  --year 2026 --month 3 --force
```

## Expected Results

### Asuransi Jiwa (Life Insurance)
- **Working:** ~20-25 companies (40-50%)
- **No public PDFs:** ~15-20 companies (30-40%)
- **Rate limited:** ~2-4 companies (4-8%)
- **Other issues:** ~5-10 companies (10-20%)

### Asuransi Umum (General Insurance)
- **Working:** ~30-35 companies (42-50%)
- **No public PDFs:** ~30-35 companies (42-50%)
- **Rate limited:** ~2-4 companies (3-5%)
- **Other issues:** ~3-5 companies (4-7%)

## Next Steps

1. **Run both batch downloads** with `--dry-run` to discover PDFs
2. **Review the batch_report.csv** to see which companies work
3. **Document problematic companies** (no PDF, rate limited, etc.)
4. **Implement company-specific fixes** for high-priority companies
5. **Set up monthly automation** with cron or scheduler
6. **Integrate into main pipeline** for regular processing

