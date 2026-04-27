# General Insurance Analyst - Heartbeat Checklist

Run this checklist every time you receive or resume a task.

## 1. Confirm Task Ownership

This task belongs to you only if it involves general insurance analysis.

If the task involves downloading, extraction, life insurance, reinsurance, macro analysis, or final compilation, escalate to Director.

## 2. Confirm Inputs

Check that you have:

```text
Target period: YYYY-MM
Extracted table path
Category: asuransi_umum
```

If the extracted table is missing, report blocker.

## 3. Filter Correct Data

Use only general insurance rows.

Do not include:

- Life insurance companies.
- Reinsurance companies.
- Syariah-only entities unless explicitly requested.
- Rows marked missing or failed without disclosure.

## 4. Check Data Quality

Before analysis, check:

- How many companies are complete?
- How many are partial?
- Which key values are missing?
- Are there extreme values needing manual review?
- Are prior-period comparisons available?

## 5. Analyze Material Movements

Review:

- Premiums.
- Claims.
- Underwriting result.
- Investment income.
- Profit/loss.
- Assets, liabilities, and equity.

## 6. Write Output

Use this structure:

```text
# General Insurance Analysis - YYYY-MM

## Executive Summary
## Sector Overview
## Key Financial Movements
## Company Highlights
## Risk and Watchlist Items
## Data Limitations
## Manual Review Items
```

## 7. Final Check

Before handoff:

- Remove unsupported causal explanations.
- Mark uncertainty clearly.
- Confirm all comments are based on data.
- Confirm output is ready for Report Compiler.

## 8. Handoff

Report to Director using the format in `agent.md`.
