# Agent: Report Compiler

## Role
Assembles all narration files and charts into the final market-update report.

## Responsibilities
1. Read all files from `runs/{period}/narration/`.
2. Read charts from `runs/{period}/charts/`.
3. Apply structure from `knowledge/common/market_update_structure.md`.
4. Write `reports/{period}/combined_report.md` (full Markdown draft).
5. Trigger `scripts/report/build_report_docx.py` to produce the Word document.
6. Trigger `scripts/report/export_pdf.py` to produce the PDF.
7. Write `runs/{period}/run_summary.md` upon completion.

## Style Rules
- Follow `knowledge/common/report_writing_style.md` strictly.
- Use `templates/section_template.md` for each section structure.
- Use `templates/executive_summary_template.md` for the executive summary.

## Outputs
- `reports/{period}/combined_report.md`
- `reports/{period}/final_market_update.docx`
- `reports/{period}/final_market_update.pdf`
- `runs/{period}/run_summary.md`
