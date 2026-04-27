# Life Insurance Analyst - Heartbeat Checklist

Run this checklist every time you receive or resume a task.

## 1. Confirm Task Ownership

This task belongs to you only if it involves life insurance analysis.

If the task involves downloading, extraction, general insurance, reinsurance, macro analysis, or final compilation, escalate to Director.

## 2. Confirm Inputs

Check that you have:

```text
Target period: YYYY-MM
Extracted table path
Category: asuransi_jiwa
```

If the extracted table is missing, report blocker.

## 3. Filter Correct Data

Use only life insurance rows.

Do not include:

- General insurance companies.
- Reinsurance companies.
- Syariah-only entities unless explicitly requested.
- Failed extraction rows without disclosure.

## 4. Check Data Quality

Before analysis, check:

- How many companies are complete?
- How many are partial?
- Are premium, claims/benefits, investment income, assets, liabilities, equity, and profit/loss fields available?
- Is reserve or insurance liability data available?
- Are prior-period comparisons available?

## 5. Analyze Material Movements

Review:

- Premium income.
- Claims and benefits.
- Investment income.
- Technical reserves or insurance liabilities if available.
- Assets, liabilities, and equity.
- Profit/loss.

## 6. Write Output

Use this structure:

```text
# Life Insurance Analysis - YYYY-MM

## Executive Summary
## Sector Overview
## Key Financial Movements
## Investment and Liability Context
## Company Highlights
## Risk and Watchlist Items
## Data Limitations
## Manual Review Items
```

## 7. Final Check

Before handoff:

- Remove unsupported product-level claims.
- Mark missing reserve data if relevant.
- Confirm analysis uses life insurance logic.
- Confirm output is ready for Report Compiler.

## 8. Handoff

Report to Director using the format in `agent.md`.
