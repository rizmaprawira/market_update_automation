# Reinsurance Analyst - Heartbeat Checklist

Run this checklist every time you receive or resume a task.

## 1. Confirm Task Ownership

This task belongs to you only if it involves reinsurance analysis.

If the task involves downloading, extraction, general insurance, life insurance, macro analysis, or final compilation, escalate to Director.

## 2. Confirm Inputs

Check that you have:

```text
Target period: YYYY-MM
Extracted table path
Category: reasuransi
```

If the extracted table is missing, report blocker.

## 3. Filter Correct Data

Use only reinsurance rows.

Do not include:

- General insurance companies.
- Life insurance companies.
- Syariah-only entities unless explicitly requested.
- Failed extraction rows without disclosure.

## 4. Check Data Quality

Before analysis, check:

- How many reinsurers are complete?
- How many are partial?
- Are premium, claims, underwriting result, investment income, equity, and profit/loss fields available?
- Are retrocession or capital indicators available?
- Are prior-period comparisons available?

## 5. Analyze Material Movements

Review:

- Reinsurance premium.
- Claims burden.
- Underwriting result.
- Retrocession-related items if available.
- Investment income.
- Assets, liabilities, and equity.
- Profit/loss.

## 6. Write Output

Use this structure:

```text
# Reinsurance Analysis - YYYY-MM

## Executive Summary
## Reinsurance Sector Overview
## Key Financial Movements
## Company Highlights
## Market Implication Notes
## Risk and Watchlist Items
## Data Limitations
## Manual Review Items
```

## 7. Final Check

Before handoff:

- Remove unsupported market-wide claims.
- Mark partial data clearly.
- Confirm the analysis uses reinsurance logic.
- Confirm output is ready for Report Compiler.

## 8. Handoff

Report to Director using the format in `agent.md`.
