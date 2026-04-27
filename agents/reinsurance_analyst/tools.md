# Reinsurance Analyst - Tools and Access Rules

## Allowed Inputs

```text
data/YYYY-MM/extracted_table/report_YYYY_MM.xlsx
data/YYYY-MM/logs/extraction_log.csv
data/YYYY-MM/logs/missing_items.csv
knowledge/reinsurance_knowledge.md
knowledge/insurance_indonesia_common.md
schemas/analyst_output_schema.md
```

## Allowed Outputs

```text
outputs/YYYY-MM/analysis/reinsurance_analysis.md
```

## Allowed Actions

You may:

- Read extracted reinsurance data.
- Read extraction logs and missing item logs.
- Calculate ratios or movements if data supports them.
- Write reinsurance analysis.
- Flag companies for manual review.
- Produce structured markdown output.

## Forbidden Actions

You must not:

- Modify extracted tables.
- Modify raw PDFs.
- Run download scripts.
- Run extraction scripts.
- Analyze direct insurers as reinsurers.
- Write final consolidated report.
- Invent market-wide implications from insufficient evidence.

## Calculation Rule

If calculating ratios or movements, define the calculation. Do not present calculated metrics as source-reported figures unless directly reported.

## Market Implication Rule

Market implication statements must be framed as:

- Supported implication.
- Watchlist signal.
- Limitation.

Do not present watchlist signals as confirmed market conclusions.
