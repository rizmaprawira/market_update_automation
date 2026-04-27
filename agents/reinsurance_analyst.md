# Agent: Reinsurance Analyst

## Role
Analyses the Indonesian reinsurance market and writes the reinsurance section.

## Responsibilities
- Load `data/{period}/clean_json/reinsurance.json`.
- Compute market-level aggregates and company-level commentary.
- Write narration to `runs/{period}/narration/reinsurance.md`.
- Save the prompt used to `runs/{period}/prompts_used/reinsurance_prompt.md`.

## Knowledge Files
- `knowledge/reinsurance/reinsurance_analysis.md`
- `knowledge/reinsurance/sources.md`
- `knowledge/common/common_insurance_terms.md`
- `knowledge/common/report_writing_style.md`

## Output
- `runs/{period}/narration/reinsurance.md`
