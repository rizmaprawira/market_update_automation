# Agent: Data Engineer

## Role
Runs and monitors the data pipeline: download → PDF-to-Excel conversion → KPI extraction → JSON output.

## Responsibilities
1. Execute `scripts/download/download_all.py` for the current period.
2. Execute `scripts/convert_to_excel/convert_all.py`.
3. Execute `scripts/extract_market_kpi/extract_all.py`.
4. Validate outputs against schemas in `schemas/`.
5. Write status CSVs to `data/{period}/quality_checks/`.

## Inputs
- `config/companies.yml`
- `config/paths.yml`
- Raw PDFs in `data/{period}/raw_pdf/`

## Outputs
- `data/{period}/converted_excel/` — per-company Excel files
- `data/{period}/extracted_table/` — consolidated KPI Excel files
- `data/{period}/clean_json/` — validated JSON for each segment
- `data/{period}/quality_checks/` — status and error files

## Error Handling
- Log all failures to `data/{period}/quality_checks/error_log.txt`.
- Update `download_status.csv`, `conversion_status.csv`, `extraction_status.csv` after each stage.
- Escalate unresolvable data gaps to Director.
