"""Convert PT Asuransi Jiwa Generali Indonesia monthly PDF to Excel.

This is a SYARIAH (Islamic insurance) company with a unique multi-fund layout.
Layout: 1 page, 3 pdfplumber tables plus additional text-based sections.

Table 0 (54 rows x 18 cols): Balance sheet per fund (Dana Perusahaan, Dana Tabarru,
Dana Investasi Peserta). Structured with labels in col 0, multiple fund columns.

The "Laporan Kinerja Keuangan" (P&L equivalent) section is in the right portion
of the page using word-level extraction because its label column is not cleanly
captured by pdfplumber's table extractor.

Table 1 (24 rows x 3 cols): Tingkat Solvabilitas summary.

Usage:
    conda run -n market_update python scripts/convert_to_excel/asuransi_jiwa/convert_generali.py
"""
from pathlib import Path
import re
import pdfplumber
import pandas as pd
from openpyxl.styles import Font

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_PATH = PROJECT_ROOT / "data/2026-03/raw_pdf/asuransi_jiwa/pt_asuransi_jiwa_generali_indonesia/pt_asuransi_jiwa_generali_indonesia_2026-03.pdf"
OUT_PATH = PROJECT_ROOT / "data/2026-03/raw_excel/asuransi_jiwa/pt_asuransi_jiwa_generali_indonesia/pt_asuransi_jiwa_generali_indonesia_2026-03.xlsx"


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


def parse_balance_sheet(tbl):
    """
    Table 0: Balance sheet per fund. 54 rows x 18 cols.
    Col 0: label, Cols 1-8: fund columns (SAK/SAP per fund).
    """
    headers = [
        "Uraian",
        "Dana Perusahaan SAK",
        "Dana Perusahaan SAP",
        "Dana Tabarru SAK DT",
        "Dana Tabarru SAK DTH",
        "Dana Tabarru SAP",
        "Dana Investasi SAK",
        "Dana Investasi SAP",
        "Dana Investasi Penyesuaian",
    ]
    rows_out = []
    for row in tbl[2:]:  # Skip header rows
        while len(row) < 9:
            row = list(row) + [None]
        lbl = str(row[0] or "").strip()
        if not lbl:
            continue
        lbl = lbl.replace("(cid:9)", "").replace("nJaIlW#A", "").strip()
        if lbl.upper() in {"ASET", "LIABILITAS DAN EKUITAS", "LIABILITAS",
                            "EKUITAS DANA", "BUKAN INVESTASI", "INVESTASI"}:
            continue
        row_data = {
            "Uraian": lbl,
            "Dana Perusahaan SAK": clean_num(row[1]),
            "Dana Perusahaan SAP": clean_num(row[2]),
            "Dana Tabarru SAK DT": clean_num(row[3]),
            "Dana Tabarru SAK DTH": clean_num(row[4]),
            "Dana Tabarru SAP": clean_num(row[5]),
            "Dana Investasi SAK": clean_num(row[6]),
            "Dana Investasi SAP": clean_num(row[7]),
            "Dana Investasi Penyesuaian": clean_num(row[8]),
        }
        if any(v is not None for k, v in row_data.items() if k != "Uraian"):
            rows_out.append(row_data)
    return pd.DataFrame(rows_out, columns=headers)


def parse_kinerja_keuangan(page):
    """
    Extract Laporan Kinerja Keuangan (P&L equivalent) by grouping words by y-coordinate.
    Labels: x 428-530; Values Dana Perusahaan: x ~548-570; Dana Tabarru: x ~580-600; Dana Investasi: x ~610-630.
    """
    words = page.extract_words(x_tolerance=5, y_tolerance=2)
    # Only process words in the P&L section (y > 60, x 395-640)
    section_words = [w for w in words if w["top"] > 60 and 395 <= w["x0"] <= 640]

    # Group words by y-coordinate band (tolerance 3px)
    lines = {}
    for w in section_words:
        y_key = round(w["top"] / 4) * 4  # round to nearest 4px
        if y_key not in lines:
            lines[y_key] = []
        lines[y_key].append(w)

    rows = []
    for y_key in sorted(lines.keys()):
        line_words = sorted(lines[y_key], key=lambda w: w["x0"])
        # Separate labels (x < 530) and values (x >= 530)
        label_parts = [w["text"] for w in line_words if w["x0"] < 530]
        val_parts = sorted(
            [(w["x0"], w["text"]) for w in line_words if w["x0"] >= 530],
            key=lambda x: x[0]
        )
        label = " ".join(label_parts).strip()
        if not label:
            continue

        # Skip header rows
        if label.upper() in {"URAIAN", "DANA PERUSAHAAN", "DANA TABARRU'", "DANA TANAHUD",
                              "DANA INVESTASI PESERTA", "LAPORAN KINERJA KEUANGAN",
                              "RINGKASAN LAPORAN KEUANGAN", "UNIT SYARIAH"}:
            continue
        if "Ringkasan" in label or "GENERALI" in label or "nJaIlW" in label:
            continue
        if "RASIO KEUANGAN" in label.upper():
            break  # Stop at rasio section

        # Assign values to fund columns based on x position
        dp_val, dt_val, dip_val = None, None, None
        for x, text in val_parts:
            if 530 <= x < 575:
                dp_val = clean_num(text)
            elif 575 <= x < 610:
                dt_val = clean_num(text)
            elif 610 <= x < 650:
                dip_val = clean_num(text)

        if label or dp_val is not None or dt_val is not None or dip_val is not None:
            rows.append({
                "Uraian": label,
                "Dana Perusahaan": dp_val,
                "Dana Tabarru dan Dana Tanahud": dt_val,
                "Dana Investasi Peserta": dip_val,
            })

    return pd.DataFrame(rows, columns=["Uraian", "Dana Perusahaan",
                                        "Dana Tabarru dan Dana Tanahud",
                                        "Dana Investasi Peserta"])


def parse_solvabilitas(tbl):
    """Table 1: Tingkat Solvabilitas (3 cols)."""
    rows = []
    for row in tbl:
        while len(row) < 3:
            row = list(row) + [None]
        lbls = expand(row[0])
        v1s = expand(row[1])
        v2s = expand(row[2])
        length = max(len(lbls), len(v1s), len(v2s))
        for i in range(length):
            lbl = lbls[i] if i < len(lbls) else ""
            v1 = clean_num(v1s[i]) if i < len(v1s) else None
            v2 = clean_num(v2s[i]) if i < len(v2s) else None
            if lbl or v1 is not None or v2 is not None:
                rows.append({"Uraian": lbl, "Dana Tabarru / Dana Tanahud": v1, "Dana Perusahaan": v2})
    df = pd.DataFrame(rows)
    df = df[df["Uraian"] != ""].reset_index(drop=True)
    return df


def style_sheet(ws):
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for col in ws.columns:
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()

        df_balance = parse_balance_sheet(tables[0])
        df_kinerja = parse_kinerja_keuangan(page)
        df_solvabilitas = parse_solvabilitas(tables[1])

    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        df_balance.to_excel(writer, sheet_name="Posisi Keuangan", index=False)
        df_kinerja.to_excel(writer, sheet_name="Kinerja Keuangan", index=False)
        df_solvabilitas.to_excel(writer, sheet_name="Tingkat Solvabilitas", index=False)
        for ws in writer.sheets.values():
            style_sheet(ws)

    print(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
