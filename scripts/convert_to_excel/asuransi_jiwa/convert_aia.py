"""Convert PT AIA Financial monthly PDF to Excel.

Layout: 1 page, 3 tables. Main table (13 cols) packs multiple financial items
per cell with newline separators. We split each multi-line cell into individual rows.

Columns in main table:
  0-2  : Laporan Posisi Keuangan - Aset (label, 2026, 2025)
  3-5  : Laporan Posisi Keuangan - Liabilitas & Ekuitas (label, 2026, 2025)
  6-8  : Laporan Laba Rugi (label, 2026, 2025)
  10-12: Tingkat Kesehatan Keuangan (label, 2026, 2025)

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_aia.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_aia_financial/pt_aia_financial_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_aia_financial/pt_aia_financial_2026-03.xlsx"

# Headers to skip
SKIP_LABELS = {
    "LAPORAN POSISI KEUANGAN", "(dalam jutaan rupiah)", "ASET",
    "LIABILITAS DAN EKUITAS", "LAPORAN LABA (RUGI) KOMPREHENSIF",
    "U R A I A N", "URAIAN", "TINGKAT KESEHATAN KEUANGAN",
    "KOMISARIS DAN DIREKSI", "PEMILIK PERUSAHAAN", "REASURADUR UTAMA",
    "NAMA REASURADUR", "%",
}


def clean_num(val):
    """Parse Indonesian number string to float. Returns None for blanks/dashes."""
    if val is None:
        return None
    s = re.sub(r"\s+", "", str(val)).strip()
    if s in ("", "-", "—", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace(",", "")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def expand_cell_pair(label_cell, val26_cell, val25_cell):
    """
    Expand newline-packed cells into list of (label, 2026_val, 2025_val) tuples.
    """
    lbls = [l.strip() for l in str(label_cell or "").split("\n") if l.strip()]
    v26s = [v.strip() for v in str(val26_cell or "").split("\n") if v.strip()]
    v25s = [v.strip() for v in str(val25_cell or "").split("\n") if v.strip()]
    length = max(len(lbls), len(v26s), len(v25s))
    rows = []
    for i in range(length):
        lbl = lbls[i] if i < len(lbls) else ""
        v26 = clean_num(v26s[i]) if i < len(v26s) else None
        v25 = clean_num(v25s[i]) if i < len(v25s) else None
        if lbl or v26 is not None or v25 is not None:
            rows.append({"Uraian": lbl, "2026": v26, "2025": v25})
    return rows


def parse_section(table, lbl_col, col26, col25, skip=None):
    """Extract rows from specific columns of the raw table."""
    skip = skip or SKIP_LABELS
    rows = []
    for row in table:
        # Pad row if needed
        while len(row) <= max(lbl_col, col26, col25):
            row = row + [None]
        lbl = row[lbl_col]
        v26 = row[col26]
        v25 = row[col25]
        if lbl and str(lbl).strip().upper() in {s.upper() for s in skip}:
            continue
        rows.extend(expand_cell_pair(lbl, v26, v25))
    # Remove rows that are purely empty
    rows = [r for r in rows if r["Uraian"] or r["2026"] is not None or r["2025"] is not None]
    return pd.DataFrame(rows, columns=["Uraian", "2026", "2025"])


def style_sheet(ws):
    """Apply bold to header row and auto-fit column widths."""
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for col in ws.columns:
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 55)


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(PDF_PATH) as pdf:
        tables = pdf.pages[0].extract_tables()

    main_tbl = tables[0]  # 40 rows x 13 cols

    df_aset = parse_section(main_tbl, lbl_col=0, col26=1, col25=2)
    df_liab = parse_section(main_tbl, lbl_col=3, col26=4, col25=5)
    df_plr = parse_section(main_tbl, lbl_col=6, col26=7, col25=8)
    df_tkk = parse_section(main_tbl, lbl_col=10, col26=11, col25=12)

    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        df_aset.to_excel(writer, sheet_name="Posisi Keuangan - Aset", index=False)
        df_liab.to_excel(writer, sheet_name="Posisi Keuangan - Liabilitas", index=False)
        df_plr.to_excel(writer, sheet_name="Laba Rugi", index=False)
        df_tkk.to_excel(writer, sheet_name="Tingkat Kesehatan", index=False)
        for ws in writer.sheets.values():
            style_sheet(ws)

    print(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
