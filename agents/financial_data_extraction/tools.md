# Financial Data Extraction - Tools and Access Rules

## Allowed Input Folders

```text
data/YYYY-MM/raw_pdf/asuransi_umum/
data/YYYY-MM/raw_pdf/asuransi_jiwa/
data/YYYY-MM/raw_pdf/reasuransi/
```

## Allowed Script Folders

```text
scripts/convert_to_excel/
scripts/extraction/
```

## Allowed Output Folders

```text
data/YYYY-MM/converted_excel/asuransi_umum/
data/YYYY-MM/converted_excel/asuransi_jiwa/
data/YYYY-MM/converted_excel/reasuransi/
data/YYYY-MM/extracted_table/
data/YYYY-MM/logs/
```

## Allowed Reference Folders

```text
knowledge/
schemas/
```

## Allowed Actions

You may:

- Run PDF conversion scripts.
- Create or modify extraction scripts.
- Create converted Excel/CSV/TSV outputs.
- Create combined extracted tables.
- Create extraction logs.
- Create missing item logs.
- Create manual-review logs.
- Inspect raw PDFs for extraction purposes.

## Forbidden Actions

You must not:

- Download missing PDFs.
- Delete raw PDFs.
- Modify download logs except to reference them in extraction status.
- Write market analysis.
- Modify final report files.
- Fill missing values with guesses.
- Change source financial values for presentation purposes.

## Safe Output Rule

If an extracted table already exists:

- Do not overwrite silently.
- Create a versioned output or confirm update behavior with the Director.
- Keep previous outputs unless explicitly instructed otherwise.

## Traceability Rule

Where practical, extracted values should be traceable to:

```text
source_pdf
source_page_or_sheet
source_table_or_cell
```

If exact traceability is unavailable, mark the row or field for manual review.
