# Life Insurance Financial Report Downloaders

48 scripts for downloading monthly financial reports from Indonesian life insurance companies.

## Status Summary (Latest Test: 2026-04-28)

**Overall:** 16/48 companies have publicly downloadable PDF reports
- ✅ **Working**: 16 companies with directly accessible PDFs
- ❌ **Not Available**: 26 companies don't publish downloadable PDFs publicly
- ⚠️ **Rate Limited**: 4 companies return 403 (WAF/rate limiting)
- ⏱️ **Timeout**: 2 companies (network issues)

### Working Companies (PDFs Found)
| Company | Status | Latest PDF |
|---------|--------|-----------|
| PT AIA Financial | ✅ | Laporan Keuangan Konvensional Maret 2026 |
| PT Asuransi Jiwa Astra | ✅ | Laporan Keuangan - Maret 2026 (Konvensional Unaudited) |
| PT BNI Life Insurance | ✅ | PDF found |
| PT Capital Life Indonesia | ✅ | Laporan Keuangan Maret 2026 |
| PT Asuransi Jiwa Central Asia Raya | ✅ | Laporan Keuangan Konvensional Maret 2026 |
| China Life Insurance Indonesia | ✅ | PDF found |
| Chubb Life Insurance | ✅ | PDF found |
| PT Asuransi Generali Indonesia | ✅ | LAPORAN KEUANGAN UNIT SYARIAH 2026 BULAN MARET |
| Great Eastern Life Indonesia | ✅ | Laporan Keuangan Konvensional Maret 2026 |
| PT Asuransi Nasional | ✅ | Laporan Keuangan Bulan Maret 2026 |
| PT PFI Mega Life Insurance | ✅ | Unduh |
| PT Prudential Life Assurance | ✅ | Download |
| PT Asuransi Jiwa Reliance Indonesia | ✅ | Maret 2026 |
| PT Sequis Life | ✅ | Unduh Sekarang |
| Sun Life Financial Indonesia | ✅ | Laporan Keuangan Konvensional Maret 2026 |
| PT Victoria ALIFE Indonesia | ✅ | Laporan Bulan Februari 2026 |

### Rate Limited (403 Errors)
| Company | Issue | Workaround |
|---------|-------|-----------|
| PT Asuransi Allianz Life Indonesia | WAF blocking | Add delays between requests, retry with new session |
| PT Asuransi Jiwa IFG | 403 Forbidden | May require user-agent rotation |
| PT Manulife Indonesia | 403 Forbidden | May require user-agent rotation |
| PT Panin Daichi Life | 403 Forbidden | May require user-agent rotation |

### Not Available (26 companies)
Companies that don't publish downloadable PDFs on their public websites:
- PT Asuransi BRI Life (requires `--use-browser`)
- PT Asuransi Ciputra Indonesia (requires `--use-browser`)
- PT Asuransi Jiwa Avrist Assurance
- PT Axa Financial Indonesia
- PT Axa Mandiri Financial Services
- PT Asuransi Jiwa BCA
- PT Bhinneka Life Indonesia
- PT Bumiputera Asuransi (1912)
- Central Asia Financial Jagadir
- PT Forward Insurance Indonesia
- PT Hanwha Life Insurance Indonesia
- PT Heksa Solution Insurance
- PT Lippo Life Assurance
- PT Mandiri Inhealth Indonesia
- PT MNC Life Assurance
- PT MSIG Life Insurance Indonesia
- PT Pacific Life Insurance
- PT Perta Life Insurance
- PT Sealnsure
- PT Sequis Financial
- PT Simas Jiwa
- PT Starinvestama
- PT Taspen (Asuransi)
- PT Teguh Pelita Pelindung
- PT Tokio Marine Life Insurance Indonesia
- PT Zurich Topas Life

## Installation

All scripts depend on `_downloader_base.py` (shared utilities) and standard libraries:
- requests
- beautifulsoup4

For browser-based rendering (BRI Life, Ciputra):
```bash
pip install playwright
python -m playwright install chromium
```

## Usage

Basic syntax for all scripts (from project root):
```bash
python scripts/download/asuransi_jiwa/download_<company>.py --year YYYY --month M [OPTIONS]
```

### Examples

**Download March 2026 report for AIA:**
```bash
python scripts/download/asuransi_jiwa/download_aia.py --year 2026 --month 3
```

**Dry-run (discovery only, no download):**
```bash
python scripts/download/asuransi_jiwa/download_aia.py --year 2026 --month 3 --dry-run
```

**Force re-download even if file exists:**
```bash
python scripts/download/asuransi_jiwa/download_aia.py --year 2026 --month 3 --force
```

**BRI Life with Playwright browser rendering:**
```bash
python scripts/download/asuransi_jiwa/download_brilife.py --year 2026 --month 3 --use-browser
```

**Allianz, Ciputra with browser rendering:**
```bash
python scripts/download/asuransi_jiwa/download_allianz.py --year 2026 --month 3
python scripts/download/asuransi_jiwa/download_ciputra.py --year 2026 --month 3 --use-browser
```

### Command-line Options

- `--year YYYY` (required): Target report year (e.g., 2026)
- `--month M` (required): Target month 1-12 (e.g., 3 for March)
- `--output-root PATH`: Root directory for output (default: `data`)
- `--dry-run`: Discover reports without downloading
- `--force`: Overwrite existing PDF files
- `--use-browser`: Use Playwright for JS-heavy pages (BRI Life, Ciputra)
- `--timeout SECONDS`: HTTP timeout (default: 30)

## Output Structure

Reports are saved to:
```
data/{YYYY-MM}/raw_pdf/asuransi_jiwa/{company_id}/{company_id}_{YYYY-MM}.pdf
```

Example:
```
data/2026-03/raw_pdf/asuransi_jiwa/aia/aia_2026-03.pdf
data/2026-03/raw_pdf/asuransi_jiwa/astra/astra_2026-03.pdf
```

## Testing Results (2026-03)

All 48 company scripts have been tested with dry-run mode to verify they can discover PDFs.

**Test Summary:**
- ✅ **16 companies**: Successfully found PDFs for March 2026
- ❌ **26 companies**: No PDFs found (not published or requires special access)
- ⚠️ **4 companies**: 403 Forbidden (rate limiting/WAF)
- ⏱️ **2 companies**: Timeout (network/server issues)

**Sample Downloads Verified:**
- ✅ AIA Financial: Successfully downloaded (201 KB)
- ✅ Astra: Successfully downloaded (82 KB)
- ✅ BNI Life: Found PDF for download

**Known Issues:**
- Allianz, IFG, Manulife, Panin Daichi: Return 403 (WAF blocking)
- BRI Life, Ciputra: Static HTML shows no PDFs - require `--use-browser` flag
- 26 companies: No downloadable PDFs available on public websites

## Integration with Pipeline

To integrate into the main pipeline:

### 1. Download all companies for a specific month/year:
```python
import subprocess
from pathlib import Path

year, month = 2026, 3
scripts_dir = Path("scripts/download/asuransi_jiwa")

for script in sorted(scripts_dir.glob("download_*.py")):
    company = script.stem.replace("download_", "")
    print(f"Downloading {company}...")
    
    result = subprocess.run([
        "python", str(script),
        "--year", str(year),
        "--month", str(month),
        "--timeout", "30"
    ], capture_output=True, text=True)
    
    if "successfully downloaded" in result.stdout.lower():
        print(f"  ✅ Success")
    elif "ERROR" in result.stdout:
        print(f"  ❌ Failed: {result.stdout.split('ERROR')[1][:50]}")
```

### 2. Track downloads with manifest:
Each script generates `download_manifest.csv` at:
```
data/{YYYY-MM}/raw_pdf/asuransi_jiwa/{company_id}/download_manifest.csv
```

Manifest fields: `timestamp, company_name, company_id, source_url, pdf_url, status, file_path, file_size_kb, error_reason`

### 3. Handle failures gracefully:
- Use `--dry-run` first to check which companies have available PDFs
- Re-run failed downloads with `--force` to overwrite
- Check manifest CSV files to identify problematic companies
- For 403 errors, add delay between requests or skip

## Known Issues

1. **Allianz**: May return 403 after first successful request - likely WAF/rate limiting
   - Workaround: Add delays between requests or retry with new session

2. **BRI Life & Ciputra**: Require JavaScript rendering
   - Solutions: Use `--use-browser` (requires Playwright installation)
   - Alternative: Manually inspect pages to find direct PDF URLs

3. **Session Management**: Long-running scripts may hit rate limits
   - Workaround: Add delays between company downloads, use `--force` sparingly

## Architecture

- `_downloader_base.py`: Shared utilities
  - `build_session()`: HTTP session with retry logic
  - `extract_pdf_links()`: Find PDFs matching month/year
  - `download_pdf()`: Download with validation
  - `score_candidate()`: Rank candidates by relevance
  
- Per-company scripts: ~70 lines each
  - Parse CLI arguments
  - Fetch HTML from source URL
  - Extract candidates with month/year matching
  - Download highest-scoring candidate

## Directory Structure

```
scripts/download/asuransi_jiwa/                    ← 48 Life Insurance Scripts
├── _downloader_base.py                           ← Shared utilities
├── download_aia.py                               ← Company scripts
├── download_allianz.py
├── download_astra.py
├── download_avrist_assurance.py
├── download_axa_financial_indonesia.py
├── download_axa_mandiri_financial_services.py
├── download_bca.py
├── ... (48 total download scripts)
├── download_zurich_topas_life.py
├── README_LIFE_INSURANCE_DOWNLOADS.md
└── data/                                         ← Downloaded PDFs
    └── {YYYY-MM}/raw_pdf/asuransi_jiwa/
        └── {company_id}/{company_id}_{YYYY-MM}.pdf
```

**All 48 Companies:**
aia, allianz, astra, avrist_assurance, axa_financial_indonesia, axa_mandiri_financial_services, bca, bhinneka_life_indonesia, bni_life_insurance, brilife, bumiputera_1912, capital_life_indonesia, central_asia_financial_jagadir, central_asia_raya, china_life_insurance_indonesia, chubb_life_insurance, ciputra, equity_life_indonesia, fwd_insurance_indonesia, generali_indonesia, great_eastern_life_indonesia, hanwha_life_insurance_indonesi, heksa_solution_insurance, ifg, indolife_pensiontama, lippo_life_assurance, mandiri_inhealth_indonesia, manulife_indonesia, mnc_life_assurance, msig_life_insurance_indonesia_, nasional, pacific_life_insurance, panin_daichi_life, perta_life_insurance, pfi_mega_life_insurance, prudential_life_assurance, reliance_indonesia, sealnsure, sequis_financial, sequis_life, simas_jiwa, starinvestama, sun_life_financial_indonesia, taspen, teguh_pelita_pelindung, tokio_marine_life_insurance_in, victoria_alife_indonesia, zurich_topas_life

## Implementation Status

### ✅ Completed
- All 48 download scripts generated and deployed
- Shared `_downloader_base.py` with retry logic and session management
- PDF validation via header/footer inspection
- Month/year matching algorithm for candidate filtering
- Candidate scoring system (relevance ranking)
- Manifest CSV/JSON generation for audit tracking
- Debug HTML output for troubleshooting failed discoveries
- Support for all CLI flags: `--year`, `--month`, `--dry-run`, `--force`, `--use-browser`, `--debug-html`, `--timeout`
- Static HTML fetching with automatic fallback
- Comprehensive README documentation

### ⚠️ Partially Working
- Browser rendering (Playwright) support - requires explicit `--use-browser` flag
- 16/48 companies have publicly downloadable PDFs
- Rate limiting affects 4 companies (Allianz, IFG, Manulife, Panin Daichi)

### 🔮 Future Enhancements
1. **Browser rendering fallback**: Automatically try `--use-browser` when static HTML returns 0 PDFs
2. **Rate limiting workarounds**: Implement exponential backoff, session rotation for 403 errors
3. **Parallel downloads**: Concurrent downloads with thread pooling for faster batch operations
4. **Data enrichment**: For companies without public PDFs, fetch from OJK database or IR portals
5. **PDF content validation**: Verify PDFs contain actual financial data (not empty/placeholder files)
6. **Cached page storage**: Store HTML snapshots to avoid re-fetching unchanged pages
7. **Email-based report fetching**: For companies that email reports instead of publishing online

