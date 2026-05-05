"""Convert PT Asuransi BRI Life monthly PDF to Excel.

Layout: 1 page, 1 large table (55 rows x 19 cols).
The table spans 3 report sections side by side:
  Cols 1-3   : Laporan Posisi Keuangan - Aset (label, 2025, 2026)
  Cols 5-8   : Laporan Posisi Keuangan - Liabilitas & Ekuitas (label, None, 2025, 2026)
  Cols 10-13 : Laporan Laba Rugi (label, None, 2025, 2026)
  Cols 15-18 : Indikator Kesehatan Keuangan (label, 2025, 2026, None)

Note: BRI Life uses 2025 before 2026 in most columns.

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_bri_life.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_bri_life/pt_asuransi_bri_life_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_bri_life/pt_asuransi_bri_life_2026-03.xlsx"

SKIP_STRS = {
    "LAPORAN POSISI KEUANGAN", "LAPORAN LABA (RUGI) KOMPREHENSIF",
    "INDIKATOR KESEHATAN KEUANGAN", "(dalam jutaan rupiah)",
    "A S E T", "ASET", "LIABILITAS DAN EKUITAS", "U R A I A N", "URAIAN",
    "KOMISARIS DAN DIREKSI", "PEMILIK PERUSAHAAN", "REASURADUR UTAMA",
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


def zip_section(lbl_cell, v25_cell, v26_cell):
    """Zip label + value cells (both packed) into rows."""
    lbls = expand(lbl_cell)
    v25s = expand(v25_cell)
    v26s = expand(v26_cell)
    length = max(len(lbls), len(v25s), len(v26s))
    rows = []
    for i in range(length):
        lbl = lbls[i] if i < len(lbls) else ""
        v25 = clean_num(v25s[i]) if i < len(v25s) else None
        v26 = clean_num(v26s[i]) if i < len(v26s) else None
        if lbl or v25 is not None or v26 is not None:
            rows.append({"Uraian": lbl, "2025": v25, "2026": v26})
    return rows


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

    tbl = tables[0]  # 55 rows x 19 cols

    aset_rows, liab_rows, plr_rows, tkk_rows = [], [], [], []

    for row in tbl:
        while len(row) < 19:
            row = list(row) + [None]

        # Skip header rows
        lbl_aset = row[1]
        if lbl_aset and str(lbl_aset).strip().upper() in {s.upper() for s in SKIP_STRS}:
            continue

        # Aset: cols 1 (label), 2 (2025), 3 (2026)
        aset_rows.extend(zip_section(row[1], row[2], row[3]))
        # Liabilitas: cols 5 (label), 7 (2025), 8 (2026)
        liab_rows.extend(zip_section(row[5], row[7], row[8]))
        # P&L: cols 10 (label), 12 (2025), 13 (2026)
        plr_rows.extend(zip_section(row[10], row[12], row[13]))
        # TKK: cols 15 (label), 16 (2025), 17 (2026)
        tkk_rows.extend(zip_section(row[15], row[16], row[17]))

    def to_df(rows):
        df = pd.DataFrame(rows, columns=["Uraian", "2025", "2026"])
        df = df[~df["Uraian"].isin(["", "None"] + list(SKIP_STRS))].reset_index(drop=True)
        return df

    df_aset = to_df(aset_rows)
    df_liab = to_df(liab_rows)
    df_plr = to_df(plr_rows)
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
