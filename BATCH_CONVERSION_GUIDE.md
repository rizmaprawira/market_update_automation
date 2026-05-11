# Batch PDF-to-Excel Conversion Guide

Quick reference for converting financial reports from PDFs to Excel for the Indonesia Re Market Update project.

## Overview

Two batch conversion scripts are available:
- **Reinsurance** (7 companies) → `scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py`
- **General Insurance** (41 companies) → `scripts/convert_to_excel/general_insurance/batch_convert_asuransi_umum.py`

Both scripts:
- Process companies in parallel (configurable worker count)
- Load period from config if not specified
- Generate Excel files in standardized template format
- Display real-time progress and summary statistics

---

## Reinsurance Batch Conversion

### Basic Usage

```bash
# Convert current period (from config/report_periods.yml)
python3 scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py

# Convert specific period
python3 scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py --period 2025-12

# Convert with custom worker count
python3 scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py --period 2026-03 --workers 2
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--period` | config value | Report period (e.g., `2026-03`) |
| `--workers` | 4 | Number of parallel conversion workers |

### Output

```
==========================================================================================
                          BATCH CONVERT: REINSURANCE REASURANSI                           
==========================================================================================
Period: 2026-03
Companies: 7
Workers: 4
Start time: 2026-05-11 12:48:23
==========================================================================================
[ 1/7] ✓ orionre                                           
[ 2/7] ✓ tugure                                            
[ 3/7] ✓ nasre                                             
[ 4/7] ✓ indonesiare                                       
[ 5/7] ✓ inare                                             
[ 6/7] ✓ marein                                            
[ 7/7] ✓ maipark                                           
==========================================================================================
Successful: 7/7
Failed:     0/7
End time:   2026-05-11 12:48:29
==========================================================================================
```

### Companies Included

1. **nasre** - PT Reasuransi Nasional Indonesia
2. **tugure** - PT Asuransi Tugure Indonesia
3. **indonesiare** - PT Reasuransi Indonesia Utama
4. **orionre** - PT Orion Reinsurance Company
5. **inare** - PT Indoperkasa Suksesjaya Reasuransi
6. **marein** - PT Maskapai Reasuransi Indonesia Tbk
7. **maipark** - PT Multiperkasa Insurance

---

## General Insurance Batch Conversion

### Basic Usage

```bash
# Convert current period
python3 scripts/convert_to_excel/general_insurance/batch_convert_asuransi_umum.py

# Convert specific period
python3 scripts/convert_to_excel/general_insurance/batch_convert_asuransi_umum.py --period 2025-12

# Fast conversion with more workers
python3 scripts/convert_to_excel/general_insurance/batch_convert_asuransi_umum.py --period 2026-03 --workers 8
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--period` | config value | Report period (e.g., `2026-03`) |
| `--workers` | 4 | Number of parallel conversion workers |

### Output Example

```
==========================================================================================
                      BATCH CONVERT: GENERAL INSURANCE ASURANSI_UMUM                      
==========================================================================================
Period: 2026-03
Companies: 41
Workers: 8
Start time: 2026-05-11 12:47:34
==========================================================================================
[ 1/41] ✓ pt_asuransi_asei_indonesia                        
[ 2/41] ✓ pt_asuransi_binagriya_upakara                     
[ 3/41] ✓ pt_asuransi_allianz_utama_indonesia               
...
[40/41] ✓ pt_victoria_insurance_tbk                         
[41/41] ✓ pt_malacca_trust_wuwungan_insurance_tbk           
==========================================================================================
Successful: 41/41
Failed:     0/41
End time:   2026-05-11 12:47:43
==========================================================================================
```

### Companies Included (41 total)

**Major Companies:**
- PT AIG Insurance Indonesia
- PT Asuransi Allianz Utama Indonesia
- PT Asuransi MSIG Indonesia
- PT Sompo Insurance Indonesia
- PT Chubb General Insurance Indonesia
- PT AXA Insurance Indonesia
- PT China Taiping Insurance Indonesia

**Plus 34 additional Indonesian and international general insurance carriers**

---

## Output Locations

### Reinsurance Excel Files
```
data/{period}/converted_excel/reasuransi/
├── nasre/nasre_{period}.xlsx
├── tugure/tugure_{period}.xlsx
├── indonesiare/indonesiare_{period}.xlsx
├── orionre/orionre_{period}.xlsx
├── inare/inare_{period}.xlsx
├── marein/marein_{period}.xlsx
└── maipark/maipark_{period}.xlsx
```

### General Insurance Excel Files
```
data/{period}/converted_excel/asuransi_umum/
├── pt_aig_insurance_indonesia/pt_aig_insurance_indonesia_{period}.xlsx
├── pt_asuransi_allianz_utama_indonesia/pt_asuransi_allianz_utama_indonesia_{period}.xlsx
├── ... (41 companies total)
└── pt_victoria_insurance_tbk/pt_victoria_insurance_tbk_{period}.xlsx
```

---

## Performance & Parallelization

### Worker Recommendations

| Scenario | Workers | Rationale |
|----------|---------|-----------|
| Single-core system | 1-2 | Avoid CPU overload |
| 4-core laptop | 4 | Default, good balance |
| 8-core workstation | 6-8 | Max parallelism |
| Server/CI environment | 8+ | System dependent |

### Timing Examples

**Reinsurance (7 companies):**
- 1 worker: ~15 seconds total
- 4 workers: ~5 seconds total (parallel execution)

**General Insurance (41 companies):**
- 4 workers: ~10 seconds total
- 8 workers: ~6 seconds total

---

## Troubleshooting

### Missing PDF
```
✗ pt_asuransi_xxx_xxx  Script not found or PDF missing
```
**Fix:** Check that the PDF exists at `data/{period}/raw_pdf/asuransi_umum/{company}/{company}_{period}.pdf`

### Conversion Timeout
```
✗ company_name  Timeout (60s)
```
**Fix:** Increase timeout or reduce parallel workers to free system resources

### Unmatched Labels (Warnings)
```
[WARN] company: 5 unmatched label(s):
```
This is normal - the converter extracted data but couldn't match all labels to the template. The main financial data is still filled in. See [Converter Configuration Guide](scripts/convert_to_excel/README.md) for fine-tuning.

---

## Adding a New Company

### For Reinsurance:
1. Add company to `COMPANIES` list in `batch_convert_reasuransi.py`
2. Create `scripts/convert_to_excel/reinsurance/convert_{company_id}.py`
3. Create `scripts/convert_to_excel/reinsurance/configs/{company_id}.yml`
4. Run batch script to test

### For General Insurance:
1. Add company to `COMPANIES` list in `batch_convert_asuransi_umum.py`
2. Create `scripts/convert_to_excel/general_insurance/convert_{company_id}.py`
3. Create `scripts/convert_to_excel/general_insurance/configs/{company_id}.yml`
4. Run batch script to test

---

## Integration with Data Pipeline

These batch scripts fit into the full Indonesia Re Market Update pipeline:

```
Raw PDFs
   ↓
[Batch Conversion Scripts] ← YOU ARE HERE
   ↓
Excel Files (intermediate format)
   ↓
Extraction & Validation
   ↓
Clean JSON Data
   ↓
Analyst Narration
   ↓
Final Market Update Report
```

---

## Advanced Usage

### Run only if PDFs exist
```bash
# Check for PDFs first, then convert
if [ -f "data/2026-03/raw_pdf/reinsurance/nasre/*.pdf" ]; then
  python3 scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py --period 2026-03
fi
```

### Chain both batch conversions
```bash
# Convert both reinsurance and general insurance in sequence
python3 scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py --period 2026-03 && \
python3 scripts/convert_to_excel/general_insurance/batch_convert_asuransi_umum.py --period 2026-03
```

### Monitor with custom wrapper
```bash
#!/bin/bash
PERIOD=${1:-$(grep current_period config/report_periods.yml | cut -d' ' -f2)}
echo "Converting period: $PERIOD"
python3 scripts/convert_to_excel/reinsurance/batch_convert_reasuransi.py --period $PERIOD --workers 4
python3 scripts/convert_to_excel/general_insurance/batch_convert_asuransi_umum.py --period $PERIOD --workers 8
echo "Conversion complete!"
```

---

## Related Documentation

- [Reinsurance Converter Details](scripts/convert_to_excel/reinsurance/README.md)
- [General Insurance Converter Details](scripts/convert_to_excel/general_insurance/README.md)
- [Template Structure Guide](docs/TEMPLATE_STRUCTURE.md)
- [CLAUDE.md](CLAUDE.md) - Project setup and conventions
