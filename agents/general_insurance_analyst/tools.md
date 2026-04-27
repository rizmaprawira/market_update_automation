# General Insurance Analyst - Tools and Access Rules

## Allowed Inputs

```text
data/YYYY-MM/extracted_table/report_YYYY_MM.xlsx
data/YYYY-MM/logs/extraction_log.csv
data/YYYY-MM/logs/missing_items.csv
knowledge/general_insurance_knowledge.md
knowledge/insurance_indonesia_common.md
schemas/analyst_output_schema.md
```

## Allowed Outputs

```text
outputs/YYYY-MM/analysis/general_insurance_analysis.md
```

## Allowed Actions

You may:

- Read extracted general insurance data.
- Read extraction logs and missing item logs.
- Calculate ratios or movements if data supports them.
- Write general insurance analysis.
- Flag companies for manual review.
- Produce structured markdown output.

## Forbidden Actions

You must not:

- Modify extracted tables.
- Modify raw PDFs.
- Run download scripts.
- Run extraction scripts.
- Analyze life insurance data.
- Analyze reinsurance data as direct insurance data.
- Write final consolidated report.
- Invent causes not supported by data.

## Calculation Rule

If calculating ratios or growth rates, define the formula in the analysis or notes. Do not present calculated metrics as source-reported figures unless they are directly reported.

## Data Limitation Rule

If more than a small number of companies are missing critical values, disclose this prominently in the analysis.
