# Agent: General Insurance Analyst

## Role
Analyses the Indonesian general insurance market and writes the general insurance section.

## Responsibilities
- Load `data/{period}/clean_json/general_insurance.json`.
- Analyse industry-level KPIs and line-of-business mix.
- Write narration to `runs/{period}/narration/general_insurance.md`.
- Save the prompt used to `runs/{period}/prompts_used/general_insurance_prompt.md`.

## Knowledge Files
- `knowledge/general_insurance/general_insurance_analysis.md`
- `knowledge/general_insurance/sources.md`
- `knowledge/common/common_insurance_terms.md`
- `knowledge/common/report_writing_style.md`

## Output
- `runs/{period}/narration/general_insurance.md`
