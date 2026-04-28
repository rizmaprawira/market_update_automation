# General Insurance Downloads - Quick Start Guide

## What's Been Built

✅ **71 download scripts** for all Indonesian general insurance companies  
✅ **Shared base module** with PDF discovery, validation, and download logic  
✅ **Ready to test** with a simple command  

## Test One Company (2 mins)

```bash
# Discover PDF without downloading (recommended first step)
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3 --dry-run

# Actually download the PDF
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3
```

## Batch Test All 71 Companies (5-10 mins)

```bash
# Dry-run on all companies to see which have available PDFs
for script in scripts/download/asuransi_umum/download_*.py; do
  python "$script" --year 2026 --month 3 --dry-run 2>&1 | grep -E "(Fetching|Selected|no PDF|ERROR)" &
done
wait
```

## Download Month-by-Month

```bash
# March 2026
for script in scripts/download/asuransi_umum/download_*.py; do
  company=$(basename "$script" | sed 's/download_//;s/.py//')
  echo "Downloading $company..."
  python "$script" --year 2026 --month 3 &
done
wait

# April 2026 (just change the month)
for script in scripts/download/asuransi_umum/download_*.py; do
  python "$script" --year 2026 --month 4 &
done
wait
```

## Check Results

Manifest files are created at:
```
data/2026-03/raw_pdf/asuransi_umum/{company_id}/download_manifest.csv
```

Summary script to see what worked and what didn't:

```bash
echo "SUMMARY OF DOWNLOADS FOR 2026-03"
echo "============================="
echo "Success:"
find data/2026-03/raw_pdf/asuransi_umum -name "download_manifest.csv" | xargs grep "success" | wc -l

echo "Failed:"
find data/2026-03/raw_pdf/asuransi_umum -name "download_manifest.csv" | xargs grep "failed\|no_pdf" | wc -l

echo "Already exists:"
find data/2026-03/raw_pdf/asuransi_umum -name "download_manifest.csv" | xargs grep "already_exists" | wc -l
```

## If a Company Fails

Common reasons:
- **No PDF found** → Check if the website publishes downloadable reports
- **403 Forbidden** → Rate limiting (try `--use-browser` flag)
- **Timeout** → Network/server issue (try increasing `--timeout 60`)
- **JavaScript required** → Use `--use-browser` flag (requires Playwright)

```bash
# Try with browser rendering
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3 --use-browser

# Try with increased timeout
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3 --timeout 60

# Save debug HTML to investigate failure
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3 --debug-html
```

## All Available Flags

- `--year YYYY` *(required)* - Report year
- `--month M` *(required)* - Report month (1-12)
- `--dry-run` - Find PDFs without downloading
- `--force` - Overwrite existing downloads
- `--use-browser` - Use browser rendering for JS content
- `--timeout SECONDS` - HTTP timeout (default 30)
- `--debug-html` - Save HTML for debugging failures
- `--output-root PATH` - Custom output directory (default: `data`)

## Expected Results After First Test

Based on similar systems:
- **60-70%** of companies should have downloadable PDFs ✅
- **20-30%** may have no public PDFs ❌
- **5-10%** may be rate-limited (403 errors) ⚠️
- **5-10%** may have PDFs hidden in dropdowns/scrolling (solvable with `--use-browser`) 🔧

Once you've tested and documented which companies work, we can:
1. Improve problematic ones with company-specific handlers
2. Set up automated monthly downloads
3. Integrate into the main pipeline
