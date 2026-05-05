"""Convert PT Asuransi Jiwa SealNsure monthly PDF to Excel.

Layout: 1 page, 5 tables.
- Table 0 (1 rows x 2 cols): Section title headers (skip)
- Table 1 (27 rows x 9 cols): Balance sheet + P&L side by side
  Cols 0-2  : Aset (label, 2026, 2025)
  Cols 3-5  : Liabilitas & Ekuitas (label, 2026, 2025)
  Cols 6-8  : P&L (label, 2026, 2025)
- Table 2 (19 rows x 3 cols): Tingkat Solvabilitas (label, 2026, 2025)
- Table 3 (4 rows x 1 col) : Komisaris & Direksi (skip)
- Table 4 (3 rows x 2 cols): Reinsurers (skip)

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_sealnsure.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_jiwa_sealnsure/pt_asuransi_jiwa_sealnsure_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_jiwa_sealnsure/pt_asuransi_jiwa_sealnsure_2026-03.xlsx"

SKIP_STRS = {
    "ASET", "LIABILITAS DAN EKUITAS", "URAIAN", "2026", "2025",
    "(dalam jutaan rupiah)", "PEMENUHAN TINGKAT SOLVABILITAS",
    "LAPORAN POSISI KEUANGAN", "LAPORAN LABA (RUGI) KOMPREHENSIF",
    "1 PENDAPATAN",
}


def clean_num(val):
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


def expand(cell):
    if cell is None:
        return []
    return [x.strip() for x in str(cell).split("\n") if x.strip()]


def zip_lbl(lbl_cell, v26_cell, v25_cell):
    lbls = expand(lbl_cell)
    v26s = expand(v26_cell)
    v25s = expand(v25_cell)
    length = max(len(lbls), len(v26s), len(v25s))
    rows = []
    for i in range(length):
        lbl = lbls[i] if i < len(lbls) else ""
        v26 = clean_num(v26s[i]) if i < len(v26s) else None
        v25 = clean_num(v25s[i]) if i < len(v25s) else None
        if lbl or v26 is not None or v25 is not None:
            rows.append({"Uraian": lbl, "2026": v26, "2025": v25})
    return rows


def to_df(rows):
    df = pd.DataFrame(rows, columns=["Uraian", "2026", "2025"])
    df = df[df["Uraian"].apply(lambda x: str(x).upper() not in {s.upper() for s in SKIP_STRS})].reset_index(drop=True)
    df = df[df["Uraian"] != ""].reset_index(drop=True)
    return df


def style_sheet(ws):
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for col in ws.columns:
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 55)


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(PDF_PATH) as pdf:
        tables = pdf.pages[0].extract_tables()

    # Table 1: main financial data (27 rows x 9 cols)
    tbl = tables[1]

    aset_rows, liab_rows, plr_rows = [], [], []

    for row in tbl:
        while len(row) < 9:
            row = list(row) + [None]
        first = str(row[0] or "").strip()
        if first.upper() in {s.upper() for s in SKIP_STRS}:
            continue

        aset_rows.extend(zip_lbl(row[0], row[1], row[2]))
        liab_rows.extend(zip_lbl(row[3], row[4], row[5]))
        plr_rows.extend(zip_lbl(row[6], row[7], row[8]))

    df_aset = to_df(aset_rows)
    df_liab = to_df(liab_rows)
    df_plr = to_df(plr_rows)

    # Table 2: Tingkat Solvabilitas
    tkk_rows = []
    for row in tables[2]:
        while len(row) < 3:
            row = list(row) + [None]
        tkk_rows.extend(zip_lbl(row[0], row[1], row[2]))
    df_tkk = to_df(tkk_rows)

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
