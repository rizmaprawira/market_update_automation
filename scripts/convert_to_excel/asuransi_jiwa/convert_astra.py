"""Convert PT Asuransi Jiwa Astra monthly PDF to Excel.

Layout: 1 page, 6 tables.
- Table 0 (8 rows x 3 cols)  : Laporan Posisi Keuangan - Aset only (label, 2026, 2025)
- Table 1 (12 rows x 3 cols) : Laporan Posisi Keuangan - Liabilitas & Ekuitas (label, 2026, 2025)
- Table 2 (21 rows x 3 cols) : Laporan Laba Rugi (label, 2026, 2025)
- Table 3 (4 rows x 3 cols)  : Pemenuhan Tingkat Solvabilitas (label, 2026, 2025)
- Table 4 (1 rows x 3 cols)  : Rasio Selain Tingkat Solvabilitas
- Table 5 (4 rows x 1 col)   : Komisaris & Direksi (skip)

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_astra.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_jiwa_astra/pt_asuransi_jiwa_astra_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_jiwa_astra/pt_asuransi_jiwa_astra_2026-03.xlsx"

SKIP_STRS = {
    "ASET", "LIABILITAS DAN EKUITAS", "URAIAN", "2026", "2025",
    "(dalam jutaan rupiah)", "PEMENUHAN TINGKAT SOLVABILITAS",
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


def parse_3col_table(table, col_lbl=0, col_26=1, col_25=2):
    """Parse a 3-column table: label | 2026 | 2025."""
    rows = []
    for row in table:
        while len(row) <= max(col_lbl, col_26, col_25):
            row = list(row) + [None]
        lbls = expand(row[col_lbl])
        v26s = expand(row[col_26])
        v25s = expand(row[col_25])
        length = max(len(lbls), len(v26s), len(v25s))
        for i in range(length):
            lbl = lbls[i] if i < len(lbls) else ""
            v26 = clean_num(v26s[i]) if i < len(v26s) else None
            v25 = clean_num(v25s[i]) if i < len(v25s) else None
            if lbl or v26 is not None or v25 is not None:
                rows.append({"Uraian": lbl, "2026": v26, "2025": v25})
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

    df_aset = parse_3col_table(tables[0])
    df_liab = parse_3col_table(tables[1])
    df_plr = parse_3col_table(tables[2])
    df_tkk = parse_3col_table(tables[3])
    df_rasio = parse_3col_table(tables[4])

    # Combine tingkat solvabilitas + rasio
    df_kesehatan = pd.concat([df_tkk, df_rasio], ignore_index=True)

    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        df_aset.to_excel(writer, sheet_name="Posisi Keuangan - Aset", index=False)
        df_liab.to_excel(writer, sheet_name="Posisi Keuangan - Liabilitas", index=False)
        df_plr.to_excel(writer, sheet_name="Laba Rugi", index=False)
        df_kesehatan.to_excel(writer, sheet_name="Tingkat Kesehatan", index=False)
        for ws in writer.sheets.values():
            style_sheet(ws)

    print(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
