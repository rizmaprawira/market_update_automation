"""Convert PT Asuransi Allianz Life Indonesia monthly PDF to Excel.

Usage:
    python scripts/convert_to_excel/life_insurance/convert_pt_asuransi_allianz_life_indonesia.py [--period 2026-03]

Input:  data/{period}/raw_pdf/asuransi_jiwa/pt_asuransi_allianz_life_indonesia/pt_asuransi_allianz_life_indonesia_{period}.pdf
Output: data/{period}/converted_excel/asuransi_jiwa/pt_asuransi_allianz_life_indonesia/pt_asuransi_allianz_life_indonesia_{period}.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.path_utils import load_current_period, resolve_path
from common.pdf_extractor import extract_pdf_rows
from common.template_filler import fill_template

COMPANY_ID = "pt_asuransi_allianz_life_indonesia"
SEGMENT    = "asuransi_jiwa"
_CONFIG    = yaml.safe_load((Path(__file__).parent / "configs" / f"{COMPANY_ID}.yml").read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Convert {COMPANY_ID} financial PDF to Excel")
    parser.add_argument("--period", help="Report period, e.g. 2026-03 (default: current_period)")
    args = parser.parse_args()

    period = args.period or load_current_period()
    sep = _CONFIG.get("pdf_period_sep", "-")
    period_file = period.replace("-", sep)

    pdf_dir  = resolve_path("raw_pdf",         period, SEGMENT, COMPANY_ID)
    out_dir  = resolve_path("converted_excel", period, SEGMENT, COMPANY_ID)
    pdf_path = pdf_dir  / f"{COMPANY_ID}_{period_file}.pdf"
    out_path = out_dir  / f"{COMPANY_ID}_{period}.xlsx"

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"Extracting from {pdf_path.name}...")
    rows = extract_pdf_rows(pdf_path, _CONFIG)
    print(f"Extracted {len(rows)} rows")

    print(f"Filling template...")
    fill_template(rows, _CONFIG, period, out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
