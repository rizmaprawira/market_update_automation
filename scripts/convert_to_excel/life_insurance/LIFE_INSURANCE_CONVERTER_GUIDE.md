# Life Insurance (Asuransi Jiwa) PDF-to-Excel Converter Guide

## Architecture Overview

The life insurance converter system mirrors the reinsurance architecture but handles a fundamentally different PDF layout:

### Key Difference from Reinsurance
- **Reinsurance**: Single vertical column layout (Assets → Liabilities → Income → Health)
- **Life Insurance**: Four horizontal parallel sections (Assets | Liabilities | Income | Health)

This horizontal layout makes column position extraction critical.

### Component Stack

1. **`common/pdf_extractor.py`**: Extracts text using pdftotext bbox-layout
2. **`common/template_filler.py`**: Fills the OJK template with extracted data
3. **`common/path_utils.py`**: Resolves data paths using config files
4. **`configs/{company_id}.yml`**: Company-specific layout parameters
5. **`convert_{company_id}.py`**: Main converter script (same pattern for all companies)

## PDF Extraction Strategy

### Step 1: Identify Column Positions

Each company's PDF has a unique horizontal layout. Use pdftotext to find x-coordinates:

```bash
pdftotext -bbox-layout data/2026-03/raw_pdf/asuransi_jiwa/pt_company/pt_company_2026-03.pdf - | \
  grep -E "2026|2025|[0-9]{1,3},[0-9]{3}" | head -30
```

Look for patterns in x-coordinates:
- Assets 2026 values: typically x=155-180
- Assets 2025 values: typically x=185-210
- Liabilities 2026 values: typically x=375-410
- Liabilities 2025 values: typically x=415-450
- Income 2026 values: typically x=530-570
- Income 2025 values: typically x=570-610
- Health 2026 values: typically x=690-730
- Health 2025 values: typically x=730+

### Step 2: Configure x_thresholds

The `x_thresholds` in the config file divides the horizontal space into columns:

```yaml
x_thresholds: [140, 180, 220, 370, 420, 530, 570, 690, 730]
body_cols: [B, C, D, F, G, H, J, K, L, N, O, P]
```

These thresholds map:
- x < 140 → Column B (labels)
- 140 ≤ x < 180 → Column C (Assets 2026)
- 180 ≤ x < 220 → Column D (Assets 2025)
- 220 ≤ x < 370 → Column F (Liabilities labels)
- 370 ≤ x < 420 → Column G (Liabilities 2026)
- 420 ≤ x < 530 → Column H (Liabilities 2025)
- 530 ≤ x < 570 → Column J (Income labels)
- 570 ≤ x < 690 → Column K (Income 2026)
- 690 ≤ x < 730 → Column L (Income 2025)
- 730 ≤ x → Columns N, O, P (Health section)

**IMPORTANT**: These values must be adjusted for each company's specific PDF layout.

### Step 3: Identify content_start_y

The `content_start_y` parameter skips the PDF header. Find the y-coordinate where actual data begins:

```bash
pdftotext -bbox-layout data/2026-03/raw_pdf/asuransi_jiwa/pt_company/pt_company_2026-03.pdf - | \
  grep -E 'yMin="[0-9]{2}' | head -5
```

Typical values: 60-100 (depends on company header size)

### Step 4: Adjust row_cluster_tol

This tolerance groups words on the same horizontal line into a single row. Typical values: 0.75-1.0

## Creating a New Converter

### 1. Create Config File

Copy and customize `configs/pt_aia_financial.yml`:

```bash
cp scripts/convert_to_excel/life_insurance/configs/pt_aia_financial.yml \
   scripts/convert_to_excel/life_insurance/configs/pt_new_company.yml
```

Edit the new config to match the company's PDF:
- Update `company_id`, `sheet_name`
- Adjust `content_start_y`, `row_cluster_tol`, `x_thresholds`
- Add any company-specific `skip_labels` (reinsurer names, mixed content)
- Update header text with company name
- Verify `thousands_sep` (usually "," for life insurance companies)

### 2. Create Converter Script

Copy and customize the converter template:

```bash
cp scripts/convert_to_excel/life_insurance/convert_pt_aia_financial.py \
   scripts/convert_to_excel/life_insurance/convert_pt_new_company.py
```

Edit to match the new company ID:
```python
COMPANY_ID = "pt_new_company"  # Change this
_CONFIG = yaml.safe_load((Path(__file__).parent / "configs" / f"{COMPANY_ID}.yml").read_text())
```

### 3. Test the Converter

```bash
python scripts/convert_to_excel/life_insurance/convert_pt_new_company.py --period 2026-03
```

### 4. Validate Output

- Check if file created: `data/2026-03/converted_excel/asuransi_jiwa/pt_new_company/`
- Open Excel file and verify:
  - Headers are correctly filled
  - Asset values appear in columns C & D
  - Liabilities values appear in columns G & H
  - Income values appear in columns K & L
  - Health values appear in columns O & P

### 5. Iteratively Refine

If many labels show "UNMATCHED" warnings:

1. **Check x_thresholds**: Print extracted rows to verify columns
   ```bash
   python3 << 'EOF'
   import sys
   sys.path.insert(0, 'scripts/convert_to_excel/life_insurance')
   from common.pdf_extractor import extract_pdf_rows
   import yaml
   config = yaml.safe_load(...)
   rows = extract_pdf_rows(pdf_path, config)
   for row in rows[:20]:
       print(row)
   EOF
   ```

2. **Add skip_labels**: Identify unmatched items that aren't real financial labels
   - Reinsurer names that appear in liability columns
   - Commissioner/Director names
   - Footer text
   - Section headers from other parts of the PDF

3. **Check label normalization**: Verify that partial labels are being matched
   - Template has "Utang Klaim" but PDF has "Klaim" + values split across lines
   - The `_norm()` function in template_filler.py handles this
   - Add to `skip_labels` if a label can't be fixed

## Common Issues and Solutions

### Issue: "Many unmatched labels"

**Cause**: Columns are misaligned
**Solution**: 
1. Adjust x_thresholds first
2. Check content_start_y isn't cutting off data
3. Print extracted rows to verify column assignments

### Issue: "No values appearing in template"

**Cause**: Values aren't being parsed correctly
**Solution**:
1. Check `thousands_sep` matches the PDF (usually "," for life insurance)
2. Verify numeric values are being assigned to correct columns
3. Check if template has the label row (may need label_map override)

### Issue: "Mixed sections (Income rows appearing in Liabilities)"

**Cause**: PDF layout is too compressed, x_thresholds overlap
**Solution**:
1. Use different company as baseline if this one is too complex
2. Focus on Assets & Liabilities first (often most critical)
3. Document that Income/Health sections need manual entry for this company

### Issue: "Template file not found"

**Cause**: Converter is looking in wrong path
**Solution**: Ensure you're running converter from project root:
```bash
cd /Users/rizzie/Work/IndonesiaRe/market_update
python scripts/convert_to_excel/life_insurance/convert_pt_company.py
```

## Template Structure

The template file (`laporan_keuangan_template_asuransi_jiwa.xlsx`) has:

- **Rows 1-6**: Header section (company name, date, period)
- **Rows 7-11**: Section bars and column headers
- **Rows 12-61**: Data rows for financial metrics
- **Rows 62+**: Commissioner/Director section (if needed)

The filler populates:
- Asset labels in column B, values in C (2026) & D (2025)
- Liability labels in column F, values in G (2026) & H (2025)
- Income labels in column J, values in K (2026) & L (2025)
- Health labels in column N, values in O (2026) & P (2025)

## Batch Processing

Once you have converters for multiple companies, run batch:

```bash
python scripts/convert_to_excel/life_insurance/batch_convert_asuransi_jiwa.py --period 2026-03 --workers 4
```

(Requires creating batch_convert_asuransi_jiwa.py following the reinsurance pattern)

## Per-Company Notes

### Companies with Simple Layouts (START HERE)
- These likely need minimal x_threshold adjustment
- Start with these when learning the system

### Companies with Complex Layouts (ADVANCED)
- May have unusual column widths or spacing
- May require additional skip_labels
- May be better to focus on Assets/Liabilities only

## Validation Checklist

For each converter:

- [ ] Config file created with company_id matching PDF directory name
- [ ] Converter script created and imports correct config
- [ ] Test run produces Excel file without errors
- [ ] Excel file has headers filled (check row 3)
- [ ] At least Assets section has values in columns C & D
- [ ] Unmatched labels list is < 20 items
- [ ] All unmatched items are either skip_labels or known limitations
- [ ] File opens in Excel without corruption
- [ ] Sample values match original PDF

## Next Steps

1. Pick a simple company PDF to start
2. Follow the "Creating a New Converter" steps
3. Test and refine the x_thresholds until columns align
4. Document any peculiarities in the company's layout
5. Move to next company

## Support Resources

- Reinsurance converter examples: `scripts/convert_to_excel/reinsurance/`
- Template file: `scripts/convert_to_excel/life_insurance/laporan_keuangan_template_asuransi_jiwa.xlsx`
- Common utilities: `scripts/convert_to_excel/life_insurance/common/`
