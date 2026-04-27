# CLAUDE.md — Indonesia Re Market Update

Guidance for Claude Code agents working in this repository.

## Project Purpose

Quarterly automated pipeline producing the Indonesia Re Market Update report, covering Indonesian reinsurance, general insurance, life insurance, and macroeconomic context.

## Active Period

Defined in `config/report_periods.yml` → `current_period`. Always use this value to resolve data paths; never hardcode a period.

## Path Convention

All paths are templated in `config/paths.yml`. Resolve with:
```python
path.format(period=current_period, segment="reinsurance", company="indore")
```

## Data Flow

```
data/{period}/raw_pdf/
  → data/{period}/converted_excel/
    → data/{period}/extracted_table/
      → data/{period}/clean_json/          ← validated against schemas/
        → runs/{period}/narration/         ← written by analyst agents
          → reports/{period}/              ← compiled by Report Compiler
```

## Quality Checks

Before writing any narration, verify:
1. `data/{period}/quality_checks/extraction_status.csv` — all rows show `status=success`.
2. `data/{period}/quality_checks/missing_data_report.md` — no critical KPIs flagged.

If gaps exist, note them explicitly in the narration rather than omitting or estimating.

## Writing Style

Always follow `knowledge/common/report_writing_style.md`. Key rules:
- Formal, third-person, analytical tone.
- Numbers: IDR in billions, ratios to one decimal place.
- Always state the comparison direction and period (e.g., "increased 12.3% YoY").

## Agent Roles

Each agent's responsibilities are defined in `agents/`. Agents should read their own `.md` file before starting work.

- Do not exceed your agent's defined scope.
- Save the exact prompt used to `runs/{period}/prompts_used/{segment}_prompt.md`.

## Schema Validation

All JSON written to `data/{period}/clean_json/` must validate against the corresponding schema in `schemas/`. Use Pydantic models defined in `src/marketupdate/extractors/validation.py`.

## No Fabrication

If a data point is unavailable, use `null` in JSON and flag it in the missing data report. Never invent or estimate a KPI value.

## Adding a New Company

1. Add entry to `config/companies.yml` under the correct segment.
2. Create a converter script in `scripts/convert_to_excel/{segment}/convert_{id}.py`.
3. Add the company's KPI aliases to `config/kpi_mapping.yml`.
4. Update `schemas/{segment}_schema.json` if new KPI fields are introduced.

## Adding a New Period

1. Add entry to `config/report_periods.yml`.
2. Update `current_period`.
3. The pipeline scripts will create the required `data/{period}/` and `runs/{period}/` subdirectories automatically.
