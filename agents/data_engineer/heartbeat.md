# Data Engineer - Heartbeat Checklist

Run this checklist every time you receive or resume a task.

## 1. Confirm Task Ownership

This task belongs to you only if it involves:

- Downloader scripts.
- Raw PDF downloading.
- Link Excel files.
- Download logs.
- Failed download troubleshooting.
- Raw PDF folder organization.

If the task asks for extraction, analysis, or report writing, escalate to the Director.

## 2. Confirm Target Period

Check that the task includes:

```text
Target period: YYYY-MM
```

If missing, ask the Director for the period before running downloads.

## 3. Confirm Category

Identify the category:

```text
asuransi_umum
asuransi_jiwa
reasuransi
```

If category is `all`, handle each category separately and produce category-specific logs.

## 4. Confirm Inputs

Check the correct Excel input:

```text
asuransi_umum -> link_asuransi_umum.xlsx
asuransi_jiwa -> link_asuransi_jiwa.xlsx
reasuransi -> link_reasuransi.xlsx
```

Confirm the required columns:

```text
no | nama perusahaan | link
```

## 5. Confirm Outputs

Use the correct output path:

```text
data/YYYY-MM/raw_pdf/asuransi_umum/
data/YYYY-MM/raw_pdf/asuransi_jiwa/
data/YYYY-MM/raw_pdf/reasuransi/
data/YYYY-MM/logs/
```

## 6. Before Running or Building Scripts

Check:

- Does the relevant downloader script already exist?
- Does it accept `--period` or equivalent?
- Does it avoid syariah reports?
- Does it write logs?
- Does it support reruns without destructive overwrites?

## 7. During Download

For each company:

- Read the source link.
- Locate the relevant period report.
- Confirm the report is conventional.
- Download the PDF.
- Save with a safe filename.
- Log status.

## 8. After Download

Validate:

- Every company is represented in logs.
- Downloaded files exist.
- File sizes are plausible.
- Failed downloads have reason codes.
- Suspicious files are marked for manual review.

## 9. Handoff

Report to the Director using the required handoff format in `agent.md`.

Do not simply say the task is done. Include counts, paths, and blockers.
