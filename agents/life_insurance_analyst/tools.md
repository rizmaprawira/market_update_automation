# Life Insurance Analyst - Tools and Access Rules

## Allowed Inputs

```text
data/YYYY-MM/extracted_table/report_YYYY_MM.xlsx
data/YYYY-MM/logs/extraction_log.csv
data/YYYY-MM/logs/missing_items.csv
knowledge/life_insurance_knowledge.md
knowledge/insurance_indonesia_common.md
schemas/analyst_output_schema.md
```

## Allowed Outputs

```text
outputs/YYYY-MM/analysis/life_insurance_analysis.md
```

## Allowed Actions

You may:

- Read extracted life insurance data.
- Read extraction logs and missing item logs.
- Calculate ratios or movements if data supports them.
- Write life insurance analysis.
- Flag companies for manual review.
- Produce structured markdown output.

## Forbidden Actions

You must not:

- Modify extracted tables.
- Modify raw PDFs.
- Run download scripts.
- Run extraction scripts.
- Analyze general insurance data.
- Analyze reinsurance data.
- Write final consolidated report.
- Invent product-level explanations.

## Calculation Rule

If calculating ratios or movements, define the calculation. Do not present calculated metrics as source-reported figures unless directly reported.

## Reserve Data Rule

If reserve or insurance liability data is unavailable, disclose the limitation before making conclusions about life insurance profitability or liability pressure.
