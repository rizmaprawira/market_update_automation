# Asuransi Umum (General Insurance) Download System - Deployment Summary

**Date Deployed:** 2026-04-28  
**Total Companies:** 71  
**Status:** Ready for testing  

## What Was Built

### 1. Download Scripts (71 files)
One automated script for each Indonesian general insurance company:
```
download_pt_aig_insurance_indonesia.py
download_pt_arthagraha_general_insurance.py
download_pt_asuransi_allianz_utama_indonesia.py
... (71 total)
```

Each script:
- Accepts `--year` and `--month` parameters for targeting specific reports
- Fetches company's report page and searches for PDF links
- Intelligently matches PDFs by month/year to ensure correct file
- Downloads and validates PDF integrity
- Tracks results in a manifest CSV file
- Supports dry-run, browser rendering, timeouts, and debugging

### 2. Shared Base Module
**File:** `_downloader_base.py` (13 KB)

Core functionality used by all 71 scripts:
- PDF discovery algorithm with month/year matching
- Candidate scoring to select the best PDF match
- HTTP session management with retry logic
- Static HTML fetching and Playwright browser rendering
- PDF validation (checking headers for %PDF marker)
- Download with error handling and resumption
- Manifest generation for audit tracking
- Debug HTML output for troubleshooting

### 3. Documentation
- **README_GENERAL_INSURANCE_DOWNLOADS.md** - Complete reference guide with usage examples, integration patterns, and future enhancements
- **QUICKSTART.md** - Fast start guide for testing and batch downloads
- **DEPLOYMENT_SUMMARY.md** - This file, showing what was delivered

## Key Features

✅ **Month/Year Matching** - Automatically finds PDFs for the target month and year  
✅ **Candidate Ranking** - Scores candidates by relevance (exact matches score highest)  
✅ **PDF Validation** - Verifies downloaded files are valid PDFs, not empty stubs  
✅ **Dry-Run Mode** - Test PDF discovery without downloading  
✅ **Browser Rendering** - Optional Playwright support for JavaScript-heavy pages  
✅ **Error Tracking** - Manifest files record success/failure with reasons  
✅ **Timeout Control** - Configurable HTTP timeouts for slow/problematic sites  
✅ **Force Re-download** - Overwrite existing PDFs with `--force` flag  
✅ **Consistent Output** - All PDFs saved to structured directory tree: `data/{YYYY-MM}/raw_pdf/asuransi_umum/{company_id}/`

## Getting Started (Next Steps)

### 1. Quick Test (2 minutes)
```bash
# Test one company with dry-run
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3 --dry-run

# Actually download it
python scripts/download/asuransi_umum/download_pt_asuransi_astra_buana.py --year 2026 --month 3
```

### 2. Batch Test All 71 Companies (5-10 minutes)
```bash
# Discover PDFs for all companies (no downloads)
for script in scripts/download/asuransi_umum/download_*.py; do
  python "$script" --year 2026 --month 3 --dry-run 2>&1 | grep -E "(Selected|no PDF)" &
done
wait
```

### 3. Document Results
After testing, categorize which companies:
- ✅ Have publicly downloadable PDFs
- ❌ Don't publish PDFs publicly
- ⚠️ Return rate limiting errors (403)
- ⏱️ Timeout or have network issues
- 🔧 Need `--use-browser` flag (JavaScript required)

### 4. Improve Problem Companies (Optional)
Once we know which companies have issues, we can:
- Add company-specific handlers (like the Mandiri Inhealth dropdown fix you mentioned)
- Implement retry logic with exponential backoff for rate-limited sites
- Increase timeouts for slow servers
- Use browser automation for JavaScript-rendered content

### 5. Integrate Into Pipeline
Once validated:
```python
# Monthly batch download automation
import subprocess
from pathlib import Path

year, month = 2026, 4  # Next month
scripts_dir = Path("scripts/download/asuransi_umum")

for script in sorted(scripts_dir.glob("download_*.py")):
    subprocess.run([
        "python", str(script),
        "--year", str(year),
        "--month", str(month)
    ])
```

## Comparison with Asuransi Jiwa (Life Insurance)

**Asuransi Jiwa System (Deployed 2026-04-28):**
- 48 companies
- 16 working (33%)
- 26 with no public PDFs (54%)
- 4 rate-limited (8%)
- 2 timeouts (4%)

**Asuransi Umum System (This Build):**
- 71 companies
- Ready for testing - results TBD

The exact same codebase and architecture was used, so we expect similar distribution of working/problematic companies.

## Important Notes

### Data Quality
- Only downloads PDFs that match the target month/year
- Validates PDF format before confirming success
- No estimated or fabricated data
- All failures are tracked with reasons in manifest files

### Rate Limiting
Some sites may block or throttle automated access:
- Consider adding 1-5 second delays between company downloads
- Use `--use-browser` flag for JavaScript-based rate limiting detection
- Implement session rotation if needed

### Alternative Sources
For companies without public PDFs, consider:
- OJK (Otoritas Jasa Keuangan) database
- Company investor relations (IR) portals
- Direct email requests to CFO/IR departments

## Files Overview

| File | Size | Purpose |
|------|------|---------|
| `download_pt_*.py` × 71 | 5-6 KB each | Individual company downloader scripts |
| `_downloader_base.py` | 13 KB | Shared utility module |
| `README_GENERAL_INSURANCE_DOWNLOADS.md` | 10 KB | Complete reference documentation |
| `QUICKSTART.md` | 4 KB | Fast start guide |
| `DEPLOYMENT_SUMMARY.md` | This file | What was delivered & next steps |

## Support & Troubleshooting

See **QUICKSTART.md** for common issues and solutions.

For company-specific issues:
1. Run with `--debug-html` to save the page HTML
2. Check if the website has JavaScript-rendered content (try `--use-browser`)
3. Verify the source URL in the script matches the Excel file
4. Check the manifest CSV for error details

## Ready to Test?

Start with: `python scripts/download/asuransi_umum/QUICKSTART.md`

Then run the batch test to see how many companies have accessible PDFs!
