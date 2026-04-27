# Financial Data Extraction - Heartbeat Checklist

Run this checklist every time you receive or resume a task.

## 1. Confirm Task Ownership

This task belongs to you only if it involves:

- PDF conversion.
- Excel or CSV creation from PDFs.
- Financial line-item extraction.
- Data mapping.
- Combined extracted tables.
- Extraction logs.
- Data validation.

If the task asks for downloading, sector analysis, macro commentary, or final report writing, escalate to the Director.

## 2. Confirm Target Period and Category

Check:

```text
Target period: YYYY-MM
Category: asuransi_umum / asuransi_jiwa / reasuransi / all
```

## 3. Confirm Input Availability

For each category, check that the raw PDF folder exists:

```text
data/YYYY-MM/raw_pdf/asuransi_umum/
data/YYYY-MM/raw_pdf/asuransi_jiwa/
data/YYYY-MM/raw_pdf/reasuransi/
```

If raw PDFs are missing, report blocker to Director.

## 4. Confirm Output Folders

Prepare:

```text
data/YYYY-MM/converted_excel/[category]/
data/YYYY-MM/extracted_table/
data/YYYY-MM/logs/
```

## 5. Choose Conversion Method

For each company/PDF:

1. Use existing company-specific script if available.
2. Use category-level fallback converter if appropriate.
3. If conversion fails, log failure and continue to next company.
4. Do not silently skip files.

## 6. Extract Required Fields

For each converted report:

- Identify company name.
- Identify reporting period.
- Identify category.
- Extract required financial line items.
- Preserve sign and unit.
- Map labels to standardized schema fields.
- Record source location if possible.

## 7. Validate Numbers

Check:

- Numeric fields parse correctly.
- Missing fields are marked missing.
- Negative values are intentionally negative.
- Values are not copied into the wrong company row.
- Obvious OCR or parsing artifacts are marked for review.

## 8. Write Logs

Update:

```text
extraction_log.csv
missing_items.csv
manual_review_items.csv
```

## 9. Handoff

Report to the Director with:

- Output paths.
- Counts.
- Failures.
- Missing values.
- Manual-review items.
- Recommendation on whether analysis can begin.
