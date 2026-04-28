# General Insurance Financial Report Downloaders

71 scripts for downloading monthly financial reports from Indonesian general insurance companies.

## Status Summary

**Overall:** All 71 companies have scripts deployed and ready for testing
- ✅ **Scripts Generated**: 71 companies with download automation
- **Pending**: Initial test run to categorize which companies have publicly downloadable PDF reports

## Installation

All scripts depend on `_downloader_base.py` (shared utilities) and standard libraries:
- requests
- beautifulsoup4

For browser-based rendering (JavaScript-heavy sites):
```bash
pip install playwright
python -m playwright install chromium
```

## Usage

Basic syntax for all scripts (from project root):
```bash
python scripts/download/asuransi_umum/download_<company_id>.py --year YYYY --month M [OPTIONS]
```

### Examples

**Download March 2026 report for AIG Insurance:**
```bash
python scripts/download/asuransi_umum/download_pt_aig_insurance_indonesia.py --year 2026 --month 3
```

**Dry-run (discovery only, no download):**
```bash
python scripts/download/asuransi_umum/download_pt_aig_insurance_indonesia.py --year 2026 --month 3 --dry-run
```

**Force re-download even if file exists:**
```bash
python scripts/download/asuransi_umum/download_pt_aig_insurance_indonesia.py --year 2026 --month 3 --force
```

**With browser rendering for JavaScript-heavy pages:**
```bash
python scripts/download/asuransi_umum/download_pt_brilife.py --year 2026 --month 3 --use-browser
```

### Command-line Options

- `--year YYYY` (required): Target report year (e.g., 2026)
- `--month M` (required): Target month 1-12 (e.g., 3 for March)
- `--output-root PATH`: Root directory for output (default: `data`)
- `--dry-run`: Discover reports without downloading
- `--force`: Overwrite existing PDF files
- `--use-browser`: Use Playwright for JS-heavy pages
- `--timeout SECONDS`: HTTP timeout (default: 30)
- `--debug-html`: Save HTML for troubleshooting when PDF discovery fails

## Output Structure

Reports are saved to:
```
data/{YYYY-MM}/raw_pdf/asuransi_umum/{company_id}/{company_id}_{YYYY-MM}.pdf
```

Example:
```
data/2026-03/raw_pdf/asuransi_umum/pt_aig_insurance_indonesia/pt_aig_insurance_indonesia_2026-03.pdf
data/2026-03/raw_pdf/asuransi_umum/pt_asuransi_astra_buana/pt_asuransi_astra_buana_2026-03.pdf
```

## All 71 Companies

PT AIG Insurance Indonesia, PT Arthagraha General Insurance, PT Asuransi Allianz Utama Indonesia, PT Asuransi Artarindo, PT Asuransi Asei Indonesia, PT Asuransi Astra Buana, PT Asuransi Bangun Askrida, PT Asuransi Bhakti Bhayangkara, PT Asuransi Bina Dana Arta Tbk. (OONA Ins.), PT Asuransi Binagriya Upakara, PT Asuransi Bintang Tbk., PT Asuransi Buana Independent, PT Asuransi Cakrawala Proteksi Indonesia, PT Asuransi Candi Utama, PT Asuransi Central Asia, PT Asuransi Dayin Mitra Tbk., PT Asuransi Digital Bersama Tbk., PT Asuransi Eka Lloyd Jaya, PT Asuransi Etiqa Internasional Indonesia, PT Asuransi FPG Indonesia, PT Asuransi Harta Aman Pratama Tbk., PT Asuransi Intra Asia, PT Asuransi Jasa Indonesia, PT Asuransi Jasa Tania Tbk., PT Asuransi Jasaraharja Putera, PT Asuransi Kerugian Jasa Raharja, PT Asuransi Kredit Indonesia, PT Asuransi Maximus Graha Persada Tbk., PT Asuransi Mitra Pelindung Mustika, PT Asuransi MSIG Indonesia, PT Asuransi Multi Artha Guna Tbk., PT Asuransi Perisai Listrik Nasional, PT Asuransi Raksa Pratikara, PT Asuransi Rama Satria Wibawa, PT Asuransi Ramayana Tbk., PT Asuransi Reliance Indonesia, PT Asuransi Sahabat Artha Proteksi, PT Asuransi Samsung Tugu, PT Asuransi Simas Insurtech, PT Asuransi Sinar Mas, PT Asuransi Staco Mandiri, PT Asuransi Sumit Oto, PT Asuransi Tokio Marine Indonesia, PT Asuransi Total Bersama, PT Asuransi Tri Pakarta, PT Asuransi Tugu Pratama Indonesia Tbk., PT Asuransi Umum BCA, PT Asuransi Umum Bumiputera Muda 1967, PT Asuransi Umum Mega, PT Asuransi Umum Seainsure, PT Asuransi Umum Videi, PT Asuransi Untuk Semua, PT Asuransi Wahana Tata, PT Avrist General Insurance, PT AXA Insurance Indonesia, PT Bosowa Asuransi, PT BRI Asuransi Indonesia, PT China Taiping Insurance Indonesia, PT Chubb General Insurance Indonesia, PT Citra International Underwriters, PT Great Eastern General Insurance Indonesia, PT Kookmin Best Insurance Indonesia, PT Lippo General Insurance Tbk., PT Malacca Trust Wuwungan Insurance Tbk., PT Meritz Korindo Insurance, PT MNC Asuransi Indonesia, PT Pan Pacific Insurance, PT Sompo Insurance Indonesia, PT Sunday Insurance Indonesia, PT Victoria Insurance Tbk., PT Zurich Asuransi Indonesia Tbk.

## Integration with Pipeline

To integrate into the main pipeline:

### 1. Download all companies for a specific month/year:
```python
import subprocess
from pathlib import Path

year, month = 2026, 3
scripts_dir = Path("scripts/download/asuransi_umum")

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
data/{YYYY-MM}/raw_pdf/asuransi_umum/{company_id}/download_manifest.csv
```

Manifest fields: `timestamp, category, company_id, company_name, source_page_url, discovered_page_url, pdf_url, target_year, target_month, output_path, status, reason`

### 3. Handle failures gracefully:
- Use `--dry-run` first to check which companies have available PDFs
- Re-run failed downloads with `--force` to overwrite
- Check manifest CSV files to identify problematic companies
- Use `--use-browser` for JavaScript-heavy sites that fail with static HTML
- Add delays between requests to avoid rate limiting

## Architecture

- `_downloader_base.py`: Shared utilities
  - `build_session()`: HTTP session with retry logic
  - `extract_pdf_links()`: Find PDFs matching month/year
  - `download_pdf()`: Download with validation
  - `score_candidate()`: Rank candidates by relevance
  - `fetch_html_static()`: Static HTML fetching
  - `fetch_html_browser()`: Playwright-based rendering for JS content
  
- Per-company scripts: ~65 lines each
  - Parse CLI arguments
  - Fetch HTML from source URL (static or browser-rendered)
  - Extract candidates with month/year matching
  - Download highest-scoring candidate

## Directory Structure

```
scripts/download/asuransi_umum/                    ← 71 General Insurance Scripts
├── _downloader_base.py                           ← Shared utilities
├── download_pt_aig_insurance_indonesia.py         ← Company scripts
├── download_pt_arthagraha_general_insurance.py
├── download_pt_asuransi_allianz_utama_indonesia.py
├── ... (71 total download scripts)
├── download_pt_zurich_asuransi_indonesia_tbk.py
├── README_GENERAL_INSURANCE_DOWNLOADS.md
└── data/                                         ← Downloaded PDFs (auto-created)
    └── {YYYY-MM}/raw_pdf/asuransi_umum/
        └── {company_id}/{company_id}_{YYYY-MM}.pdf
```

## Implementation Status

### ✅ Completed
- All 71 download scripts generated and deployed
- Shared `_downloader_base.py` with retry logic and session management
- PDF validation via header/footer inspection
- Month/year matching algorithm for candidate filtering
- Candidate scoring system (relevance ranking)
- Manifest CSV/JSON generation for audit tracking
- Debug HTML output for troubleshooting failed discoveries
- Support for all CLI flags: `--year`, `--month`, `--dry-run`, `--force`, `--use-browser`, `--debug-html`, `--timeout`
- Static HTML fetching with automatic fallback
- Comprehensive README documentation

### ⏳ Pending
- Initial test run to verify which companies have publicly downloadable PDFs
- Documentation of working vs problematic companies
- Identification of rate-limited or timeout-prone sites
- Browser rendering investigation for sites with dynamic content

### 🔮 Future Enhancements
1. **Browser rendering fallback**: Automatically try `--use-browser` when static HTML returns 0 PDFs
2. **Rate limiting workarounds**: Implement exponential backoff, session rotation for 403 errors
3. **Parallel downloads**: Concurrent downloads with thread pooling for faster batch operations
4. **Data enrichment**: For companies without public PDFs, fetch from OJK database or IR portals
5. **PDF content validation**: Verify PDFs contain actual financial data (not empty/placeholder files)
6. **Cached page storage**: Store HTML snapshots to avoid re-fetching unchanged pages
7. **Email-based report fetching**: For companies that email reports instead of publishing online
8. **API endpoint discovery**: Detect and use direct API endpoints for PDF retrieval

## Next Steps

1. Run initial test with dry-run mode on all 71 companies
2. Categorize results (working, rate-limited, timeout, no PDF available)
3. For problematic sites: investigate with `--use-browser` flag
4. For 403 errors: implement workarounds (delays, session rotation)
5. For no-PDF sites: explore alternative sources (OJK, IR portals)
6. Integrate tested scripts into main data pipeline
7. Set up monthly batch download automation

## Known Issues (to be confirmed with testing)

- Some companies may require JavaScript rendering for PDF discovery
- Potential rate limiting on highly trafficked sites
- Network timeouts on slow or distant servers
- Some companies may not publish downloadable PDFs publicly

