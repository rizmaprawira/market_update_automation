"""Convert PT AJB Bumiputera 1912 monthly PDF to Excel.

Layout: 1 page, 4 tables.
- Table 1 (13 rows x 4 cols): Indikator Kesehatan Keuangan summary
- Table 2 (10 rows x 8 cols): Laporan Posisi Keuangan (balance sheet)
  cols: ASET label | num idx | 2026 | 2025 | LIAB label | num idx | 2026 | 2025
- Table 3 (15 rows x 4 cols): Laporan Laba Rugi
  cols: num idx | label | 2026 | 2025
- Table 4 (6 rows x 4 cols): PAYDI (Produk Asuransi Dikaitkan Investasi)

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_ajb.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_ajb_bumiputera_1912/pt_ajb_bumiputera_1912_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_ajb_bumiputera_1912/pt_ajb_bumiputera_1912_2026-03.xlsx"

DATE_2026 = "31 Mar 2026"
DATE_2025 = "31 Mar 2025"


def clean_num(val):
    """Parse Indonesian number string to float."""
    if val is None:
        return None
    s = re.sub(r"\s+", "", str(val)).strip()
    if s in ("", "-", "—", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    # AJB uses period as thousands sep and comma for decimals — detect by last separator
    # e.g. "168,915.86" => period is decimal; OR "168.915,86" => comma is decimal
    if "." in s and "," in s:
        if s.index(".") < s.index(","):
            # European: 168.915,86
            s = s.replace(".", "").replace(",", ".")
        else:
            # US/Indonesian: 168,915.86
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        # Could be thousands or decimal — if >2 digits after comma, thousands
        parts = s.split(",")
        if len(parts[-1]) > 2:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def expand_packed_cell(cell):
    """Split a newline-packed cell into a list of stripped strings."""
    if cell is None:
        return []
    return [x.strip() for x in str(cell).split("\n") if x.strip()]


def style_sheet(ws):
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for col in ws.columns:
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 55)


def parse_balance_sheet(table):
    """
    Table 2: balance sheet. The rows pack index numbers and labels together in
    newline-separated cells. Columns: [ASET_idx, ASET_label, 2026, 2025, LIAB_idx, LIAB_label, 2026, 2025]
    Special structure: first row is header, subsequent rows interleave numeric totals.
    """
    aset_rows = []
    liab_rows = []

    for row in table:
        if len(row) < 8:
            row = list(row) + [None] * (8 - len(row))

        # Aset side: cols 0 (index), 1 (label), 2 (2026), 3 (2025)
        idx_items = expand_packed_cell(row[0])
        lbl_items = expand_packed_cell(row[1])
        v26_items = expand_packed_cell(row[2])
        v25_items = expand_packed_cell(row[3])

        length = max(len(idx_items), len(lbl_items), len(v26_items), len(v25_items))
        for i in range(length):
            idx = idx_items[i] if i < len(idx_items) else ""
            lbl = lbl_items[i] if i < len(lbl_items) else ""
            v26 = clean_num(v26_items[i]) if i < len(v26_items) else None
            v25 = clean_num(v25_items[i]) if i < len(v25_items) else None
            label = f"{idx} {lbl}".strip() if idx else lbl
            if label or v26 is not None or v25 is not None:
                aset_rows.append({"Uraian": label, DATE_2026: v26, DATE_2025: v25})

        # Liabilitas side: cols 4 (index), 5 (label), 6 (2026), 7 (2025)
        idx_items = expand_packed_cell(row[4])
        lbl_items = expand_packed_cell(row[5])
        v26_items = expand_packed_cell(row[6])
        v25_items = expand_packed_cell(row[7])

        length = max(len(idx_items), len(lbl_items), len(v26_items), len(v25_items))
        for i in range(length):
            idx = idx_items[i] if i < len(idx_items) else ""
            lbl = lbl_items[i] if i < len(lbl_items) else ""
            v26 = clean_num(v26_items[i]) if i < len(v26_items) else None
            v25 = clean_num(v25_items[i]) if i < len(v25_items) else None
            label = f"{idx} {lbl}".strip() if idx else lbl
            if label or v26 is not None or v25 is not None:
                liab_rows.append({"Uraian": label, DATE_2026: v26, DATE_2025: v25})

    df_aset = pd.DataFrame(aset_rows)
    df_liab = pd.DataFrame(liab_rows)
    # Remove pure header rows
    for df in [df_aset, df_liab]:
        df.drop(df[df["Uraian"].isin(["ASET", "LIABILITAS DAN EKUITAS", "LIABILITAS & EKUITAS",
                                       DATE_2026, DATE_2025, ""])].index, inplace=True)
    return df_aset.reset_index(drop=True), df_liab.reset_index(drop=True)


def parse_plr(table):
    """Table 3: P&L. Cols: [index, label, 2026, 2025]"""
    rows = []
    for row in table:
        if len(row) < 4:
            row = list(row) + [None] * (4 - len(row))
        idx_items = expand_packed_cell(row[0])
        lbl_items = expand_packed_cell(row[1])
        v26_items = expand_packed_cell(row[2])
        v25_items = expand_packed_cell(row[3])
        length = max(len(idx_items), len(lbl_items), len(v26_items), len(v25_items))
        for i in range(length):
            idx = idx_items[i] if i < len(idx_items) else ""
            lbl = lbl_items[i] if i < len(lbl_items) else ""
            v26 = clean_num(v26_items[i]) if i < len(v26_items) else None
            v25 = clean_num(v25_items[i]) if i < len(v25_items) else None
            label = f"{idx} {lbl}".strip() if idx else lbl
            if label or v26 is not None or v25 is not None:
                rows.append({"Uraian": label, DATE_2026: v26, DATE_2025: v25})
    df = pd.DataFrame(rows)
    # Remove header rows
    df = df[~df["Uraian"].isin(["Uraian", DATE_2026, DATE_2025, ""])].reset_index(drop=True)
    return df


def parse_paydi(table):
    """Table 4: PAYDI data. Cols: [label, None, 2026, 2025]"""
    rows = []
    for row in table:
        if len(row) < 4:
            row = list(row) + [None] * (4 - len(row))
        lbl_items = expand_packed_cell(row[0])
        v26_items = expand_packed_cell(row[2])
        v25_items = expand_packed_cell(row[3])
        length = max(len(lbl_items), len(v26_items), len(v25_items))
        for i in range(length):
            lbl = lbl_items[i] if i < len(lbl_items) else ""
            v26 = clean_num(v26_items[i]) if i < len(v26_items) else None
            v25 = clean_num(v25_items[i]) if i < len(v25_items) else None
            if lbl or v26 is not None or v25 is not None:
                rows.append({"Uraian": lbl, DATE_2026: v26, DATE_2025: v25})
    df = pd.DataFrame(rows)
    df = df[~df["Uraian"].isin(["Laporan Keuangan (PAYDI)", DATE_2026, DATE_2025, ""])].reset_index(drop=True)
    return df


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(PDF_PATH) as pdf:
        tables = pdf.pages[0].extract_tables()

    # Table 0: indikator kesehatan (we skip — absorbed into balance sheet)
    # Table 1: balance sheet
    # Table 2: P&L
    # Table 3: PAYDI
    df_aset, df_liab = parse_balance_sheet(tables[1])
    df_plr = parse_plr(tables[2])
    df_paydi = parse_paydi(tables[3])

    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        df_aset.to_excel(writer, sheet_name="Posisi Keuangan - Aset", index=False)
        df_liab.to_excel(writer, sheet_name="Posisi Keuangan - Liabilitas", index=False)
        df_plr.to_excel(writer, sheet_name="Laba Rugi", index=False)
        df_paydi.to_excel(writer, sheet_name="PAYDI", index=False)
        for ws in writer.sheets.values():
            style_sheet(ws)

    print(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
