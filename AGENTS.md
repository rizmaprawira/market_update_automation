# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Python pipeline for the Indonesia Re market update. Core library code lives under `src/marketupdate/`, grouped by responsibility: `downloaders/`, `converters/`, `extractors/`, `charts/`, `report/`, and `utils/`. Script entry points are in `scripts/`, organized by stage such as `scripts/download/`, `scripts/convert_to_excel/`, and `scripts/report/`. Configuration and schemas are in `config/` and `schemas/`. Generated outputs are written to period-based folders like `data/{period}/`, `runs/{period}/`, `reports/{period}/`, and `logs/{period}/`; avoid editing committed outputs by hand.

## Build, Test, and Development Commands

- `pip install -e .` installs the package in editable mode for local development.
- `python scripts/download/download_all.py` runs the full PDF download stage.
- `python scripts/convert_to_excel/convert_all.py` converts downloaded PDFs into spreadsheets.
- `python scripts/extract_market_kpi/extract_all.py` extracts KPI tables and validates outputs.
- `python scripts/charts/generate_all_charts.py` builds charts for the current period.
- `python scripts/report/build_report_docx.py` compiles the report document.
- `python scripts/report/export_pdf.py` exports the final PDF report.
- `pytest tests/` runs the test suite. `pyproject.toml` already configures `pytest` to look in `tests/`.
- `ruff check .` is the expected lint command; line length is 100 and the project targets Python 3.11.

## Coding Style & Naming Conventions

Use Python 3.11, 4-space indentation, and `ruff`-compatible imports and formatting. Keep functions and modules small and descriptive. Use snake_case for files, functions, and variables, and reserve PascalCase for classes. Follow existing naming patterns such as `convert_<company>.py`, `extract_<segment>.py`, and `generate_<segment>_charts.py`.

## Testing Guidelines

Add tests under `tests/` using filenames like `test_<module>.py`. Mirror the package layout where practical, for example `tests/test_utils/` for `src/marketupdate/utils/`. Prefer focused unit tests for extractors, converters, and utilities, and keep fixtures small and deterministic. Run `pytest tests/` before opening a pull request.

## Commit & Pull Request Guidelines

No git history is visible in this checkout, so follow a short imperative style for commits, for example `fix KPI mapping` or `add reinsurance chart export`. Pull requests should include a concise summary, the affected period or pipeline stage, and any relevant sample output or screenshots when report rendering changes.

## Agent-Specific Instructions

Read `CLAUDE.md` before changing pipeline logic. Respect `config/report_periods.yml` for the active period, and do not hardcode dates or paths that already exist in `config/paths.yml`. If you generate data, keep it inside the appropriate period folder.
