# Data Engineer - Tools and Access Rules

## Allowed Input Files

```text
assets/link_asuransi_umum.xlsx
assets/link_asuransi_jiwa.xlsx
assets/link_reasuransi.xlsx
```

## Allowed Script Folders

```text
scripts/download/
```

Preferred script names:

```text
scripts/download/download_general_insurance.py
scripts/download/download_life_insurance.py
scripts/download/download_reinsurance.py
```

## Allowed Data Output Folders

```text
data/YYYY-MM/raw_pdf/asuransi_umum/
data/YYYY-MM/raw_pdf/asuransi_jiwa/
data/YYYY-MM/raw_pdf/reasuransi/
data/YYYY-MM/logs/
```

## Allowed Actions

You may:

- Create downloader scripts.
- Modify downloader scripts.
- Run downloader scripts.
- Create raw PDF folders.
- Download PDFs.
- Create download logs.
- Create failed download logs.
- Inspect links and pages for report URLs.
- Retry failed downloads when appropriate.
- Modifying scripts need boards approval

## Forbidden Actions

You must not:

- Modify files in `data/YYYY-MM/extracted_table/`.
- Modify analyst outputs.
- Modify final reports.
- Delete raw PDFs unless explicitly requested.
- Download syariah reports into conventional folders.
- Create fake placeholder PDFs.
- Mark a company as successful without a valid downloaded file.

## Safe Rerun Rule

If a file already exists:

- Do not overwrite silently.
- Either skip and log `already_exists`, or save a versioned filename.
- The behavior must be visible in `download_log.csv`.

## Minimum Command Interface

Downloader scripts should support a pattern similar to:

```text
python scripts/download/download_reinsurance.py --period YYYY-MM --input assets/link_reasuransi.xlsx --output data/YYYY-MM/raw_pdf/reasuransi
```

Use equivalent flags if the existing project uses different names.
