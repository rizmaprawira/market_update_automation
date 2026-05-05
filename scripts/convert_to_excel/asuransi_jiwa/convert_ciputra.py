"""Convert PT Asuransi Ciputra Indonesia monthly PDF to Excel.

Layout: 1 page, 5 tables.
- Table 0 (32 rows x 13 cols): Main financial data in 3 side-by-side sections
  Cols 0-2  : Laporan Posisi Keuangan - Aset (label, 2026, 2025)
  Cols 3-5  : Laporan Posisi Keuangan - Liabilitas (label, 2026, 2025)
  Cols 6-9  : Laporan Laba Rugi (no., label, 2026, 2025)
  Cols 10-12: Indikator Kesehatan Keuangan (label, 2026, 2025)
- Tables 1-4: Notes, directors info, reinsurers — not needed for financial data

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_ciputra.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_ciputra_indonesia/pt_asuransi_ciputra_indonesia_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_ciputra_indonesia/pt_asuransi_ciputra_indonesia_2026-03.xlsx"

SKIP_STRS = {
    "LAPORAN POSISI KEUANGAN", "LAPORAN LABA (RUGI) KOMPREHENSIF",
    "INDIKATOR KESEHATAN KEUANGAN", "(dalam jutaan rupiah)", "ASET",
    "LIABILITAS DAN EKUITAS", "No.", "URAIAN", "KETERANGAN",
    "PER 31 MARET 2026 DAN 2025", "2026", "2025",
}


def clean_num(val):
    if val is None:
        return None
    s = re.sub(r"\s+", "", str(val)).strip()
    if s in ("", "-", "—", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    # Handle both dot-thousands-comma-decimal (European) and comma-thousands (US)
    if "." in s and "," in s:
        if s.index(".") < s.index(","):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        # Thousands dot: if >1 dot or last segment has 3 digits
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[-1]) == 3):
            s = s.replace(".", "")
    else:
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


def zip_section(lbl_cell, v26_cell, v25_cell):
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


def zip_plr(no_cell, lbl_cell, v26_cell, v25_cell):
    """P&L has extra number-index column."""
    nos = expand(no_cell)
    lbls = expand(lbl_cell)
    v26s = expand(v26_cell)
    v25s = expand(v25_cell)
    length = max(len(nos), len(lbls), len(v26s), len(v25s))
    rows = []
    for i in range(length):
        no = nos[i] if i < len(nos) else ""
        lbl = lbls[i] if i < len(lbls) else ""
        v26 = clean_num(v26s[i]) if i < len(v26s) else None
        v25 = clean_num(v25s[i]) if i < len(v25s) else None
        label = f"{no} {lbl}".strip() if no else lbl
        if label or v26 is not None or v25 is not None:
            rows.append({"Uraian": label, "2026": v26, "2025": v25})
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

    tbl = tables[0]  # 32 rows x 13 cols

    aset_rows, liab_rows, plr_rows, tkk_rows = [], [], [], []

    for row in tbl:
        while len(row) < 13:
            row = list(row) + [None]

        # Skip pure header rows based on col 0 label
        lbl0 = str(row[0] or "").strip()
        if lbl0.upper() in {s.upper() for s in SKIP_STRS}:
            continue
        if lbl0.startswith("LAPORAN POSISI") or lbl0.startswith("UNTUK PERIODE"):
            continue

        aset_rows.extend(zip_section(row[0], row[1], row[2]))
        liab_rows.extend(zip_section(row[3], row[4], row[5]))
        plr_rows.extend(zip_plr(row[6], row[7], row[8], row[9]))
        tkk_rows.extend(zip_section(row[10], row[11], row[12]))

    def to_df(rows):
        df = pd.DataFrame(rows, columns=["Uraian", "2026", "2025"])
        df = df[df["Uraian"].apply(lambda x: str(x).upper() not in {s.upper() for s in SKIP_STRS})].reset_index(drop=True)
        df = df[df["Uraian"] != ""].reset_index(drop=True)
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
