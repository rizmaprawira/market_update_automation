"""Convert PT Asuransi Jiwa Nasional monthly PDF to Excel.

Layout: 1 page, 4 tables.
- Table 0 (1 rows x 2 cols): Section headers only (skip)
- Table 1 (26 rows x 10 cols): Balance sheet + P&L side by side
  Cols 0-2   : Aset (label, Jan 2024, Jan 2025)
  Cols 3-5   : Liabilitas & Ekuitas (label, None/skip, Jan 2024, Jan 2025)  [Note: cols 3,5,6]
  Cols 7-9   : P&L (label, Jan 2024, Jan 2025)
- Table 2 (19 rows x 3 cols): Tingkat Solvabilitas
- Table 3 (4 rows x 1 col) : Komisaris & Direksi (skip)

Note: Nasional uses "31 Januari 2024" / "31 Januari 2025" as period labels
(unusual — this appears to be a data filing issue from OJK side, but we preserve the labels).

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_nasional.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_jiwa_nasional/pt_asuransi_jiwa_nasional_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_jiwa_nasional/pt_asuransi_jiwa_nasional_2026-03.xlsx"

SKIP_STRS = {
    "LAPORAN POSISI KEUANGAN", "LAPORAN LABA (RUGI) KOMPREHENSIF",
    "ASET", "LIABILITAS DAN EKUITAS", "URAIAN", "U R A I A N",
    "31 Januari 2024", "31 Januari 2025", "(dalam jutaan rupiah)",
    "PEMENUHAN TINGKAT SOLVABILITAS",
}
DATE_A = "31 Januari 2024"
DATE_B = "31 Januari 2025"


def clean_num(val):
    if val is None:
        return None
    s = re.sub(r"\s+", "", str(val)).strip()
    if s in ("", "-", "—", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    # Nasional uses period as thousands and comma as decimal: "65.077,65"
    if "." in s and "," in s:
        if s.index(".") < s.index(","):
            # European format: 65.077,65 → 65077.65
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        # comma-separated thousands: remove comma
        s = s.replace(",", "")
    elif "." in s and "," not in s:
        parts = s.split(".")
        if len(parts) == 2 and len(parts[-1]) == 3:
            s = s.replace(".", "")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def expand(cell):
    if cell is None:
        return []
    return [x.strip() for x in str(cell).split("\n") if x.strip()]


def zip_lbl(lbl_cell, va_cell, vb_cell):
    lbls = expand(lbl_cell)
    vas = expand(va_cell)
    vbs = expand(vb_cell)
    length = max(len(lbls), len(vas), len(vbs))
    rows = []
    for i in range(length):
        lbl = lbls[i] if i < len(lbls) else ""
        va = clean_num(vas[i]) if i < len(vas) else None
        vb = clean_num(vbs[i]) if i < len(vbs) else None
        if lbl or va is not None or vb is not None:
            rows.append({"Uraian": lbl, DATE_A: va, DATE_B: vb})
    return rows


def to_df(rows):
    df = pd.DataFrame(rows, columns=["Uraian", DATE_A, DATE_B])
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

    tbl = tables[1]  # 26 rows x 10 cols

    aset_rows, liab_rows, plr_rows = [], [], []

    for row in tbl:
        while len(row) < 10:
            row = list(row) + [None]

        first = str(row[0] or "").strip()
        if first.upper() in {s.upper() for s in SKIP_STRS}:
            continue

        # Aset: col 0 (label), col 1 (date A), col 2 (date B)
        aset_rows.extend(zip_lbl(row[0], row[1], row[2]))
        # Liabilitas: col 3 (label), col 5 (date A), col 6 (date B)
        liab_rows.extend(zip_lbl(row[3], row[5], row[6]))
        # P&L: col 7 (label), col 8 (date A), col 9 (date B)
        plr_rows.extend(zip_lbl(row[7], row[8], row[9]))

    df_aset = to_df(aset_rows)
    df_liab = to_df(liab_rows)
    df_plr = to_df(plr_rows)

    # Solvabilitas from table 2
    tbl2 = tables[2]
    tkk_rows = []
    for row in tbl2:
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
