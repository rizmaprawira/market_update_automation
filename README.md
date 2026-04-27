# Indonesia Re — Market Update Pipeline

Automated quarterly pipeline for downloading, processing, analyzing, and reporting on the Indonesian insurance and reinsurance market.

## Repository Layout

```
market_update/
├── config/          # YAML configuration (companies, periods, paths, KPI mappings)
├── data/{period}/   # Raw PDFs → Excel → extracted KPIs → clean JSON + QC files
├── scripts/         # Entry-point scripts for each pipeline stage
├── src/marketupdate/# Shared Python library (downloaders, converters, extractors, charts)
├── knowledge/       # Context documents consumed by analyst agents
├── agents/          # Agent role definitions (Director, Analysts, Compiler)
├── schemas/         # JSON Schema definitions for all clean_json outputs
├── templates/       # Report and chart style templates
├── runs/{period}/   # Per-run outputs: charts, narrations, prompts used
├── reports/{period}/# Final compiled report (md, docx, pdf)
└── logs/{period}/   # Pipeline execution logs
```

## Pipeline Stages

```
Download PDFs  →  Convert to Excel  →  Extract KPIs  →  Validate JSON
      ↓
Generate Charts  →  Analyst Narrations  →  Compile Report  →  Export PDF
```

## Quick Start

```bash
# 1. Install dependencies
pip install -e .

# 2. Configure companies and source URLs
vim config/companies.yml

# 3. Run full pipeline for current period
python scripts/download/download_all.py
python scripts/convert_to_excel/convert_all.py
python scripts/extract_market_kpi/extract_all.py
python scripts/charts/generate_all_charts.py
python scripts/report/build_report_docx.py
python scripts/report/export_pdf.py
```

## General Insurance Download

Download conventional financial report PDFs for the general insurance list in `link_asuransi_umum.xlsx`:

```bash
python scripts/download/download_general_insurance.py \
  --year 2026 \
  --month 4 \
  --input assets/link_asuransi_umum.xlsx \
  --output-root data \
  --max-workers 4
```

For pages that only render links in JavaScript, add `--use-browser`. Use `--dry-run` to inspect the selected target paths without writing PDFs.

## Life Insurance Download

Download conventional financial report PDFs for the life insurance list in `link_asuransi_jiwa.xlsx`:

```bash
python scripts/download/download_life_insurance.py \
  --year 2026 \
  --month 4 \
  --input link_asuransi_jiwa.xlsx \
  --output-root data \
  --max-workers 4
```

The script also resolves the workbook from `assets/` when you pass only the file name. Add `--dry-run`
to preview matches and `--use-browser` when the target site requires Playwright to reveal PDF links.

## Reinsurance Download

Download conventional reinsurance financial report PDFs from the official report-page workbook:

```bash
XDG_CACHE_HOME=/tmp mamba run -n market_update python scripts/download/download_reinsurance.py \
  --year 2026 \
  --month 3 \
  --input input/link_reasuransi.xlsx \
  --output-root data \
  --use-browser \
  --debug-html
```

For a future month, change only `--year` and `--month`. For example, April 2026 becomes:

```bash
XDG_CACHE_HOME=/tmp mamba run -n market_update python scripts/download/download_reinsurance.py \
  --year 2026 \
  --month 4 \
  --input input/link_reasuransi.xlsx \
  --output-root data \
  --use-browser \
  --debug-html
```

Useful flags:

- `--discover-only` writes the manifest without downloading PDFs.
- `--dry-run` is an alias for discovery-only style runs.
- `--force` overwrites existing PDFs.
- `--max-depth 2` controls same-domain crawling depth.
- `--debug-html` saves fetched/rendered HTML under `data/{YYYY}-{MM}/raw_pdf/reasuransi/_debug_html/`.

Outputs are written to:

- `data/{YYYY}-{MM}/raw_pdf/reasuransi/{safe_company_name}/`
- `data/{YYYY}-{MM}/raw_pdf/reasuransi/download_manifest.csv`
- `data/{YYYY}-{MM}/raw_pdf/reasuransi/download_manifest.json`

## Configuration

| File | Purpose |
|---|---|
| `config/companies.yml` | Company registry, source URLs, converter assignments |
| `config/report_periods.yml` | Active period and period history |
| `config/paths.yml` | Path templates for all data directories |
| `config/kpi_mapping.yml` | Column-name aliases for KPI normalisation |

## Agents

Eight Claude Code and Open Code agents orchestrate the analytical layer. See `agents/` for role definitions:

- **Director** — orchestrates the full run
- **Data Engineer** — runs the data pipeline
- **Financial Data Analyst** — cross-segment quantitative analysis
- **Macroeconomic Analyst** — macro section
- **Reinsurance Analyst** — reinsurance section
- **General Insurance Analyst** — general insurance section
- **Life Insurance Analyst** — life insurance section
- **Report Compiler** — assembles the final report

## Period Data

Each quarter's data is isolated under `data/{period}/` and `runs/{period}/`. The active period is set in `config/report_periods.yml`.

## Testing

```bash
pytest tests/
```

## Credits

Author: Rizma Prawira (`rizmaprawira17@gmail.com`)

Funding support: Industry Research Department, Indonesia Re Institute Division
