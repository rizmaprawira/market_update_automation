"""Convert PT Asuransi Jiwa Central Asia Raya monthly PDF to Excel.

Layout: 1 page, 3 tables.
- Table 0 (35 rows x 15 cols): Main financial data, 3 sections side by side:
  Cols 0-1  : Aset (number index, label) + Cols 2-3 (2026, 2025)
  Cols 4-5  : Liabilitas & Ekuitas (number index, label) + Cols 6-7 (2026, 2025)
  Cols 8-11 : Laporan Laba Rugi (no., label, 2026, 2025)
  Cols 12-14: Indikator Kesehatan Keuangan (label, 2026, 2025)
- Table 1 (5 rows x 7 cols): Komisaris/PAYDI/Reinsurers (skip)
- Table 2 (2 rows x 1 col) : Pemilik perusahaan (skip)

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_central_asia.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_jiwa_central_asia_raya/pt_asuransi_jiwa_central_asia_raya_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_jiwa_central_asia_raya/pt_asuransi_jiwa_central_asia_raya_2026-03.xlsx"

SKIP_STRS = {
    "A S E T", "ASET", "LIABILITAS DAN EKUITAS", "U R A I A N", "URAIAN",
    "No.", "2026", "2025", "(Dalam jutaan rupiah)",
    "LAPORAN KEUANGAN KONVENSIONAL", "LAPORAN LABA RUGI KOMPREHENSIF",
    "INDIKATOR KESEHATAN KEUANGAN",
}


def clean_num(val):
    if val is None:
        return None
    s = re.sub(r"\s+", "", str(val)).strip()
    if s in ("", "-", "—", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    # Central Asia uses period as thousands separator (e.g. "211.561")
    if "." in s and "," not in s:
        # Check if decimal or thousands: if digits after dot < 3, it's decimal
        parts = s.split(".")
        if len(parts) == 2 and len(parts[-1]) <= 2:
            pass  # it's a decimal dot, keep as is
        else:
            s = s.replace(".", "")  # thousands dot
    elif "." in s and "," in s:
        if s.index(".") < s.index(","):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
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


def zip_idx_lbl(idx_cell, lbl_cell, v26_cell, v25_cell):
    """Combine numeric index + label columns, paired with values."""
    idxs = expand(idx_cell)
    lbls = expand(lbl_cell)
    v26s = expand(v26_cell)
    v25s = expand(v25_cell)
    length = max(len(idxs), len(lbls), len(v26s), len(v25s))
    rows = []
    for i in range(length):
        idx = idxs[i] if i < len(idxs) else ""
        lbl = lbls[i] if i < len(lbls) else ""
        v26 = clean_num(v26s[i]) if i < len(v26s) else None
        v25 = clean_num(v25s[i]) if i < len(v25s) else None
        label = f"{idx} {lbl}".strip() if idx else lbl
        if label or v26 is not None or v25 is not None:
            rows.append({"Uraian": label, "2026": v26, "2025": v25})
    return rows


def zip_lbl(lbl_cell, v26_cell, v25_cell):
    """Simple label + 2026 + 2025."""
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

    tbl = tables[0]  # 35 rows x 15 cols

    aset_rows, liab_rows, plr_rows, tkk_rows = [], [], [], []

    for row in tbl:
        while len(row) < 15:
            row = list(row) + [None]

        # Skip pure section header rows
        first = str(row[0] or "").strip()
        if first.upper() in {s.upper() for s in SKIP_STRS}:
            continue
        if first.startswith("LAPORAN") or first.startswith("PER 31"):
            continue

        # Aset: col 0 (index), col 1 (label), col 2 (2026), col 3 (2025)
        aset_rows.extend(zip_idx_lbl(row[0], row[1], row[2], row[3]))
        # Liabilitas: col 4 (index), col 5 (label), col 6 (2026), col 7 (2025)
        liab_rows.extend(zip_idx_lbl(row[4], row[5], row[6], row[7]))
        # P&L: col 8 (no), col 9 (label), col 10 (2026), col 11 (2025)
        plr_rows.extend(zip_idx_lbl(row[8], row[9], row[10], row[11]))
        # TKK: col 12 (label), col 13 (2026), col 14 (2025)
        tkk_rows.extend(zip_lbl(row[12], row[13], row[14]))

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
