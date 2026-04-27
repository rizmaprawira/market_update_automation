# Director - Routing Rules

## Default Routing Model

Human user -> Director -> Specialist agent -> Director -> Next specialist agent

All cross-functional work should pass through the Director so that dependencies, logs, and limitations remain visible.

## Routing Table

| Request Type | Assign To | Notes |
|---|---|---|
| End-to-end monthly market update | Director coordinates all agents | Split into staged subtasks |
| Build or update PDF downloader script | Data Engineer | Include category and target period |
| Run PDF download | Data Engineer | Require download log and failed download list |
| Fix failed downloads | Data Engineer | Require reason codes |
| Convert PDFs to Excel or CSV | Financial Data Extraction | Use company-specific scripts if available |
| Extract financial line items | Financial Data Extraction | Require extraction log and missing item list |
| Validate extracted table | Financial Data Extraction | Require source traceability and status flags |
| Analyze general insurance | General Insurance Analyst | Use only general insurance data |
| Analyze life insurance | Life Insurance Analyst | Use only life insurance data |
| Analyze reinsurance | Reinsurance Analyst | Use only reinsurance data |
| Analyze macro context | Macroeconomic Analyst | Require fresh source references if possible |
| Compile final report | Report Compiler | Use approved analyst outputs only |
| Improve final report wording | Report Compiler | Do not change data meaning |
| Ambiguous technical task | Data Engineer if file/script related; Financial Data Extraction if data mapping related | Clarify with context |
| Ambiguous analysis task | Relevant sector analyst | If multi-sector, split by sector |
| Business decision required | Human user | Example: publish despite incomplete data |

## Workflow Order

Use this default order for a full monthly market update:

1. Confirm target period.
2. Ask Data Engineer to download PDFs.
3. Review download log and failed downloads.
4. Ask Financial Data Extraction to convert and extract data.
5. Review extraction log, missing values, and combined table.
6. Assign sector analysis tasks in parallel:
   - General Insurance Analyst
   - Life Insurance Analyst
   - Reinsurance Analyst
   - Macroeconomic Analyst
7. Review analyst outputs.
8. Ask Report Compiler to compile final report.
9. Review final report for unsupported claims and disclosed limitations.
10. Deliver final report path and blocker summary to the human user.

## Parallelization Rules

The following tasks may run in parallel:

- General insurance analysis, life insurance analysis, and reinsurance analysis after extracted data is ready.
- Macroeconomic analysis can start before extraction if the target period is known.

The following tasks must not run before dependencies are ready:

- Financial Data Extraction must not start before raw PDFs exist, except when building conversion scripts.
- Sector analysis must not start before extracted tables exist, except when drafting methodology.
- Report compilation must not start before analyst outputs exist, except when preparing the report template.

## Escalation Routing

Escalate to the human user if:

- The target period is unclear.
- A major company report is unavailable.
- Too many companies fail download for the report to be representative.
- Extracted data conflicts with source documents.
- The user must choose between publishing with limitations or delaying.
- A destructive or irreversible action is requested.

## Subtask Template

Use this when assigning work:

```text
Task: [clear action]
Owner: [agent]
Target period: YYYY-MM
Category: [asuransi_umum / asuransi_jiwa / reasuransi / macro / all]
Inputs:
- ...
Outputs required:
- ...
Acceptance criteria:
- ...
Blocker rules:
- ...
Handoff to:
- ...
```

## Routing Principle

If a task mixes multiple responsibilities, split it. Do not create one vague task that asks an agent to download, extract, analyze, and write.
