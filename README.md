# Indonesia Re — Market Update Pipeline

Automated pipeline that downloads, converts, extracts, analyses, and reports on the Indonesian insurance and reinsurance market every quarter.

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
