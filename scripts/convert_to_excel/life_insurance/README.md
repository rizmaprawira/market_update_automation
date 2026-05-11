# Life Insurance (Asuransi Jiwa) PDF-to-Excel Converter System

## Overview

This system converts monthly financial reports from Indonesian life insurance companies (asuransi jiwa) from PDF format to standardized Excel templates. It follows the same architecture as the reinsurance converter system but handles the different PDF layout (4 horizontal sections instead of a single vertical layout).

## What's Included

### Core Infrastructure

- **`common/pdf_extractor.py`** - Extracts text and structure from PDFs using pdftotext bbox-layout
- **`common/template_filler.py`** - Fills OJK standard template with extracted financial data
- **`common/path_utils.py`** - Path resolution utilities for data directories
- **`laporan_keuangan_template_asuransi_jiwa.xlsx`** - Base template for all companies

### Working Converters

1. **PT AIA Financial** (`convert_pt_aia_financial.py`)
   - Status: ✓ Working (with some unmatched labels in income/health sections)
   - Config: `configs/pt_aia_financial.yml`

2. **PT AJB Bumiputera 1912** (`convert_pt_ajb_bumiputera_1912.py`)
   - Status: ✓ Working (minimal unmatched labels)
   - Config: `configs/pt_ajb_bumiputera_1912.yml`

### Templates for Building New Converters

- **`convert_pt_TEMPLATE.py`** - Template converter script (copy and customize)
- **`configs/TEMPLATE_CONFIG.yml`** - Template configuration with extensive comments
- **`LIFE_INSURANCE_CONVERTER_GUIDE.md`** - Detailed guide for creating new converters

## Available Companies

The following 33 life insurance companies have PDFs in `data/2026-03/raw_pdf/asuransi_jiwa/`:

### Existing Converters (2)
- ✓ pt_aia_financial
- ✓ pt_ajb_bumiputera_1912

### Pending Converters (31)
1. pt_asuransi_allianz_life_indonesia
2. pt_asuransi_bri_life
3. pt_asuransi_ciputra_indonesia
4. pt_asuransi_jiwa_astra
5. pt_asuransi_jiwa_central_asia_raya
6. pt_asuransi_jiwa_generali_indonesia
7. pt_asuransi_jiwa_nasional
8. pt_asuransi_jiwa_reliance_indonesia
9. pt_asuransi_jiwa_sealnsure
10. pt_asuransi_jiwa_sequis_financial
11. pt_asuransi_jiwa_sequis_life
12. pt_asuransi_jiwa_starinvestama
13. pt_asuransi_jiwa_taspen
14. pt_asuransi_jiwa_teguh_pelita_pelindung
15. pt_asuransi_simas_jiwa
16. pt_axa_financial_indonesia
17. pt_axa_mandiri_financial_services
18. pt_bni_life_insurance
19. pt_capital_life_indonesia
20. pt_china_life_insurance_indonesia
21. pt_chubb_life_insurance
22. pt_fwd_insurance_indonesia
23. pt_great_eastern_life_indonesia
24. pt_indolife_pensiontama
25. pt_msig_life_insurance_indonesia_tbk
26. pt_perta_life_insurance
27. pt_pfi_mega_life_insurance
28. pt_prudential_life_assurance
29. pt_tokio_marine_life_insurance_indonesia
30. pt_victoria_alife_indonesia
31. pt_zurich_topas_life

## Quick Start

### Run a Working Converter

```bash
# Convert AIA Financial for current period
python scripts/convert_to_excel/life_insurance/convert_pt_aia_financial.py

# Convert AJB for specific period
python scripts/convert_to_excel/life_insurance/convert_pt_ajb_bumiputera_1912.py --period 2026-03
```

### Build a New Converter

1. **Copy templates**
   ```bash
   cp scripts/convert_to_excel/life_insurance/configs/TEMPLATE_CONFIG.yml \
      scripts/convert_to_excel/life_insurance/configs/pt_new_company.yml
   cp scripts/convert_to_excel/life_insurance/convert_pt_TEMPLATE.py \
      scripts/convert_to_excel/life_insurance/convert_pt_new_company.py
   ```

2. **Analyze the company's PDF** to find column positions
   ```bash
   pdftotext -bbox-layout \
     data/2026-03/raw_pdf/asuransi_jiwa/pt_new_company/pt_new_company_2026-03.pdf - | \
     grep -E "[0-9],[0-9]{3}" | head -30
   ```

3. **Edit the config** with company-specific:
   - Company name and ID
   - PDF column position thresholds (x_thresholds)
   - Content start position (content_start_y)
   - Skip labels for non-financial data

4. **Edit the converter script** to use the new company ID

5. **Test the converter**
   ```bash
   python scripts/convert_to_excel/life_insurance/convert_pt_new_company.py --period 2026-03
   ```

6. **Validate** the output Excel file

See `LIFE_INSURANCE_CONVERTER_GUIDE.md` for detailed instructions.

## Architecture Comparison

### Reinsurance PDFs (reference)
```
Single vertical column layout:
┌─────────────────────┐
│ Assets (B, C, D)    │
│ Liabilities (F, G) │
│ Income (J, K)       │
│ Health (N, O)       │
└─────────────────────┘
```

### Life Insurance PDFs
```
Four horizontal sections:
┌──────────┬──────────┬──────────┬──────────┐
│ Assets   │ Liab     │ Income   │ Health   │
│ B,C,D    │ F,G,H    │ J,K,L    │ N,O,P    │
│ 2026/25  │ 2026/25  │ 2026/25  │ 2026/25  │
└──────────┴──────────┴──────────┴──────────┘
```

The horizontal layout requires careful tuning of `x_thresholds` to separate sections.

## Configuration Deep Dive

### Key Parameters

**`content_start_y`**: Y-coordinate where content starts (skip PDF header)
- Typical range: 60-100
- Find by examining bbox output

**`x_thresholds`**: Boundaries between column sections
- List of 9 numbers defining 12 columns
- Critical for correct data extraction
- Must be adjusted per company

**`thousands_sep`**: Number format in PDF
- "," for US format (most life insurance)
- "." for Indonesian format

**`skip_labels`**: Non-financial text to ignore
- Reinsurer names
- Commissioner/Director names
- Section headers
- Footer text

## Common Issues & Solutions

### Many Unmatched Labels
- Adjust `x_thresholds` to better separate columns
- Add more items to `skip_labels`
- Check if PDF has unusual layout

### No Values in Output
- Verify `thousands_sep` matches PDF format
- Check `x_thresholds` are assigning values to correct columns
- Ensure `content_start_y` isn't cutting off data

### Template File Not Found
- Run converter from project root:
  ```bash
  cd /Users/rizzie/Work/IndonesiaRe/market_update
  python scripts/convert_to_excel/life_insurance/convert_pt_company.py
  ```

### Mixed Section Data
- PDF sections are too compressed
- Try adjusting `row_cluster_tol`
- May need to use AIA config as starting point

## Testing Methodology

For each new converter:

1. **Run the converter**
   ```bash
   python scripts/convert_to_excel/life_insurance/convert_pt_company.py --period 2026-03 2>&1 | tee conversion.log
   ```

2. **Check output file was created**
   ```bash
   ls -lh data/2026-03/converted_excel/asuransi_jiwa/pt_company/
   ```

3. **Verify Excel structure**
   - Open file in Excel or Python
   - Check headers (rows 1-3) are filled
   - Verify at least Assets column has values
   - Check for data in Liabilities/Income/Health

4. **Review unmatched labels**
   - Fewer than 10 is good
   - If > 20, may need x_threshold adjustment

5. **Compare with original PDF**
   - Spot-check a few values
   - Verify amounts match PDF

## Development Notes

### Key Learnings from AIA & AJB

**AIA Financial**
- More complex layout with mixed sections
- Requires aggressive skip_labels
- ~15-20 unmatched labels acceptable

**AJB Bumiputera**
- Cleaner layout, easier extraction
- Only 5 unmatched labels
- Good model for simpler PDFs

### Why Per-Company Config?

Each company's PDF has:
- Unique horizontal layout
- Different column spacing
- Different section overlaps
- Different thousands separator
- Different header heights

A single config would fail for most companies. Per-company config is necessary.

## Next Steps

### Immediate (Quick Wins)
1. Test remaining 31 companies with baseline config
2. Identify which ones work without modification
3. Group companies by layout similarity
4. Build 5-10 more converters for high-similarity groups

### Medium Term
1. Automate x_threshold detection
2. Create batch converter for all working converters
3. Document which companies need manual entry
4. Build validation dashboard

### Long Term
1. Integrate with data extraction pipeline
2. Automate template filling
3. Add missing data detection
4. Create audit reports

## File Structure

```
scripts/convert_to_excel/life_insurance/
├── README.md                                    # This file
├── LIFE_INSURANCE_CONVERTER_GUIDE.md            # Detailed guide
├── laporan_keuangan_template_asuransi_jiwa.xlsx # Base template
│
├── common/
│   ├── __init__.py
│   ├── path_utils.py
│   ├── pdf_extractor.py
│   └── template_filler.py
│
├── configs/
│   ├── TEMPLATE_CONFIG.yml              # Copy to create new configs
│   ├── pt_aia_financial.yml             # ✓ Working
│   └── pt_ajb_bumiputera_1912.yml       # ✓ Working
│
├── convert_pt_TEMPLATE.py               # Copy to create new converters
├── convert_pt_aia_financial.py          # ✓ Working
└── convert_pt_ajb_bumiputera_1912.py    # ✓ Working
```

## References

- Parent reinsurance converter: `scripts/convert_to_excel/reinsurance/`
- Template: `scripts/convert_to_excel/life_insurance/laporan_keuangan_template_asuransi_jiwa.xlsx`
- Data paths: `config/paths.yml`
- Periods: `config/report_periods.yml`

## Support

For questions about:
- **Converter logic**: See reinsurance system (`scripts/convert_to_excel/reinsurance/`)
- **Creating new converters**: See `LIFE_INSURANCE_CONVERTER_GUIDE.md`
- **PDF analysis**: Use pdftotext bbox-layout and examine coordinate values
- **Configuration tuning**: Review working configs (AIA, AJB) as examples

---

**Last Updated**: 2026-05-11  
**Status**: 2/33 converters working, framework complete for building remaining 31
