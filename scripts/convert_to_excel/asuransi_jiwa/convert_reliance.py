"""Convert PT Asuransi Jiwa Reliance Indonesia monthly PDF to Excel.

Layout: 1 page (A4 landscape 841.89 x 595.276).
The PDF has a 4-section wide layout with overlapping columns that pdfplumber's
table extractor does not cleanly separate. We use word-level extraction instead.

Section x-boundaries (approximate):
  Aset labels   : x 0-100
  Aset 2026     : x 100-160
  Aset 2025     : x 160-195
  Liab labels   : x 190-350
  Liab 2026     : x 345-420
  P&L labels    : x 430-540
  P&L 2026      : x 548-620
  P&L 2025      : x 598-660 (partial overlap)
  TKK labels    : x 640-770
  TKK 2026      : x 765-840

We group words by y-coordinate and assign them to columns by x-position.

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_reliance.py
"""
from pathlib import Path
from collections import defaultdict
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_jiwa_reliance_indonesia/pt_asuransi_jiwa_reliance_indonesia_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_jiwa_reliance_indonesia/pt_asuransi_jiwa_reliance_indonesia_2026-03.xlsx"

# Column x-boundaries calibrated from actual word x-positions in the PDF
# Header row (y=93): ASET@43 | 2026@115 | 2025@159 | LIAB@228 | 2026@346 | 2025@390 |
#                    URAIAN@473 | 2026@554 | 2025@598 | URAIAN@682 | 2026@763 | 2025@807
COL_BOUNDS = {
    "aset_lbl":  (0,   114),
    "aset_26":   (114, 159),
    "aset_25":   (159, 191),
    "liab_lbl":  (191, 346),
    "liab_26":   (346, 393),
    "liab_25":   (393, 432),
    "plr_lbl":   (432, 554),
    "plr_26":    (554, 600),
    "plr_25":    (600, 640),
    "tkk_lbl":   (640, 763),
    "tkk_26":    (763, 808),
    "tkk_25":    (808, 842),
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


def assign_col(x):
    """Assign a word to a logical column based on x-coordinate."""
    for col_name, (x0, x1) in COL_BOUNDS.items():
        if x0 <= x < x1:
            return col_name
    return None


def group_lines(words, y_tol=3):
    """Group words into lines by y-coordinate."""
    lines = defaultdict(list)
    for w in words:
        y_key = round(w["top"] / y_tol) * y_tol
        lines[y_key].append(w)
    return {y: sorted(ws, key=lambda w: w["x0"]) for y, ws in lines.items()}


def build_section(lines, lbl_col, val_col, val2_col=None, min_y=90, max_y=600):
    """
    Build a section DataFrame from grouped lines.
    Labels accumulate across multiple lines; values are standalone.
    """
    rows = []
    current_label = []
    current_26 = []
    current_25 = []

    def flush():
        lbl = " ".join(current_label).strip()
        v26_str = " ".join(current_26).strip()
        v25_str = " ".join(current_25).strip() if val2_col else None
        if lbl or v26_str:
            rows.append({
                "Uraian": lbl,
                "2026": clean_num(v26_str),
                "2025": clean_num(v25_str),
            })

    for y in sorted(lines.keys()):
        if y < min_y or y > max_y:
            continue
        line_words = lines[y]
        col_data = defaultdict(list)
        for w in line_words:
            col = assign_col(w["x0"])
            if col:
                col_data[col].append(w["text"])

        lbl_text = " ".join(col_data.get(lbl_col, [])).strip()
        v26_text = " ".join(col_data.get(val_col, [])).strip()
        v25_text = " ".join(col_data.get(val2_col, [])).strip() if val2_col else ""

        if lbl_text or v26_text or v25_text:
            # If new label starts (contains letter), flush previous and start fresh
            if lbl_text:
                if current_label or current_26:
                    flush()
                    current_label.clear()
                    current_26.clear()
                    current_25.clear()
                current_label.append(lbl_text)
            if v26_text:
                current_26.append(v26_text)
            if v25_text:
                current_25.append(v25_text)

    if current_label or current_26:
        flush()

    df = pd.DataFrame(rows, columns=["Uraian", "2026", "2025"])
    # Remove header/noise rows
    noise = {"ASET", "LIABILITAS DAN EKUITAS", "URAIAN", "2026", "2025",
             "LAPORAN POSISI KEUANGAN", "LAPORAN LABA (RUGI) KOMPREHENSIF",
             "INDIKATOR KESEHATAN KEUANGAN", "(dalam jutaan rupiah)",
             "PEMENUHAN TINGKAT SOLVABILITAS", "RASIO SELAIN TINGKAT SOLVABILITAS",
             "PT ASURANSI JIWA RELIANCE INDONESIA", ""}
    df = df[df["Uraian"].apply(lambda x: str(x).upper() not in {n.upper() for n in noise})]
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
        page = pdf.pages[0]
        words = page.extract_words(x_tolerance=4, y_tolerance=2)

    lines = group_lines(words, y_tol=3)

    df_aset = build_section(lines, "aset_lbl", "aset_26", "aset_25", min_y=100)
    df_liab = build_section(lines, "liab_lbl", "liab_26", "liab_25", min_y=100)
    df_plr = build_section(lines, "plr_lbl", "plr_26", "plr_25", min_y=100)
    df_tkk = build_section(lines, "tkk_lbl", "tkk_26", "tkk_25", min_y=100)

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
