"""
Extract groundwater well inventories from Chapter 4 of both Hydrology Data Books.

This script normalizes the two Chapter 4 table types:
  - Well characteristics
  - Small well characteristics

Outputs written to extracted_groundwater/:
  well_characteristics.csv
  small_well_characteristics.csv
  all_wells.csv
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber


BOOKS = {
    "2006-2010": Path(Path("../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book").resolve()),
    "2000-2005": Path("."),
}

OUT_DIR = Path(
    "."
)
OUT_DIR.mkdir(parents=True, exist_ok=True)


def clean_cell(value):
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def parse_float(value):
    text = clean_cell(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        match = re.search(r"\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None


def parse_int(value):
    text = clean_cell(value)
    if not text:
        return None
    match = re.search(r"\d{1,3}(?:,\d{3})+", text)
    if match:
        number = int(match.group(0).replace(",", ""))
        return number if 900000 <= number <= 1100000 else None
    text = text.replace(",", "")
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_range(value):
    raw = clean_cell(value)
    if not raw:
        return raw, None, None
    compact = raw.replace(" ", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", compact)
    if len(numbers) >= 2:
        return raw, float(numbers[0]), float(numbers[1])
    if len(numbers) == 1:
        number = float(numbers[0])
        return raw, number, number
    return raw, None, None


def looks_coord(value):
    return bool(re.fullmatch(r"\d{1,3}(?:,\d{3})+", clean_cell(value)))


def looks_float(value):
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", clean_cell(value)))


def looks_well_type(value):
    return bool(re.fullmatch(r"[A-Z/]{1,5}", clean_cell(value)))


def is_header_row(row):
    joined = " ".join(clean_cell(cell).upper() for cell in row if clean_cell(cell))
    if not joined:
        return True
    header_terms = [
        "CODE",
        "LOCATION",
        "TYPE OF WELL",
        "L.C.O",
        "EASTING",
        "NORTHING",
        "DEPTH",
        "VARIATION OF WATER LEVEL",
        "BELOW COLLAR",
        "REMARKS",
        "TABLE 4.",
        "WELL CHARACTERISTICS",
        "SMALL WELL CHARACTERISTICS",
        "NOV 1980",
        "NOV 1992",
        "NOV 1999",
        "NOV 2005",
    ]
    return any(term in joined for term in header_terms)


def is_code_like(text):
    return bool(re.fullmatch(r"[A-Za-z0-9]+(?:[A-Za-z]|/[A-Za-z])?", clean_cell(text)))


def normalize_large_row(row):
    cells = [clean_cell(cell) for cell in row]
    cells += [""] * max(0, 10 - len(cells))
    cells = cells[:10]

    # Some rows shift when the location cell contains an extra numeric token.
    if not looks_well_type(cells[2]) and looks_float(cells[2]) and looks_well_type(cells[3]):
        cells[1] = (cells[1] + " " + cells[2]).strip()
        cells[2:] = cells[3:] + [""]

    return cells


def normalize_small_row(row):
    cells = [clean_cell(cell) for cell in row]
    cells += [""] * max(0, 8 - len(cells))
    match = re.search(r"^(.*?)(\d{1,3}(?:,\d{3})+.*)$", cells[2])
    if match:
        prefix = match.group(1).strip()
        if prefix and (len(prefix) > 1 or ")" in prefix):
            cells[1] = (cells[1] + prefix).strip()
        cells[2] = match.group(2).strip()
    return cells[:8]


def extract_large_wells(pdf_path, book_label):
    rows = []
    period_1_label = None
    period_2_label = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                for header_row in table[:3]:
                    cells = normalize_large_row(header_row)
                    if cells[7] and "NOV" in cells[7].upper():
                        period_1_label = cells[7]
                    if cells[8] and "NOV" in cells[8].upper():
                        period_2_label = cells[8]

                for raw_row in table:
                    cells = normalize_large_row(raw_row)
                    code = cells[0]
                    if not code or is_header_row(cells) or not is_code_like(code):
                        continue

                    raw_1, min_1, max_1 = parse_range(cells[7])
                    raw_2, min_2, max_2 = parse_range(cells[8])
                    rows.append({
                        "book": book_label,
                        "source_pdf": pdf_path.stem,
                        "page_num": page_num,
                        "well_class": "well_characteristics",
                        "code": code,
                        "location": cells[1] or None,
                        "well_type": cells[2] or None,
                        "elevation_amsl_m": parse_float(cells[3]),
                        "easting": parse_int(cells[4]),
                        "northing": parse_int(cells[5]),
                        "depth_m": parse_float(cells[6]),
                        "period_1_label": period_1_label,
                        "period_1_range_raw": raw_1 or None,
                        "period_1_min_below_collar_m": min_1,
                        "period_1_max_below_collar_m": max_1,
                        "period_2_label": period_2_label,
                        "period_2_range_raw": raw_2 or None,
                        "period_2_min_below_collar_m": min_2,
                        "period_2_max_below_collar_m": max_2,
                        "remarks": cells[9] or None,
                    })

    return rows


def extract_small_wells(pdf_path, book_label):
    rows = []
    period_1_label = None
    period_2_label = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                for header_row in table[:4]:
                    cells = normalize_small_row(header_row)
                    if cells[5] and "NOV" in cells[5].upper():
                        period_1_label = cells[5]
                    if cells[6] and "NOV" in cells[6].upper():
                        period_2_label = cells[6]

                for raw_row in table:
                    cells = normalize_small_row(raw_row)
                    code = cells[0]
                    if not code or is_header_row(cells) or not is_code_like(code):
                        continue

                    raw_1, min_1, max_1 = parse_range(cells[5])
                    raw_2, min_2, max_2 = parse_range(cells[6])
                    rows.append({
                        "book": book_label,
                        "source_pdf": pdf_path.stem,
                        "page_num": page_num,
                        "well_class": "small_well_characteristics",
                        "code": code,
                        "location": cells[1] or None,
                        "well_type": None,
                        "elevation_amsl_m": None,
                        "easting": parse_int(cells[2]),
                        "northing": parse_int(cells[3]),
                        "depth_m": parse_float(cells[4]),
                        "period_1_label": period_1_label,
                        "period_1_range_raw": raw_1 or None,
                        "period_1_min_below_collar_m": min_1,
                        "period_1_max_below_collar_m": max_1,
                        "period_2_label": period_2_label,
                        "period_2_range_raw": raw_2 or None,
                        "period_2_min_below_collar_m": min_2,
                        "period_2_max_below_collar_m": max_2,
                        "remarks": cells[7] or None,
                    })

    return rows


def main():
    large_rows = []
    small_rows = []

    for book_label, base_dir in BOOKS.items():
        chapter_dir = base_dir / "Chapter 4"
        large_name = "well characteristics.pdf" if (chapter_dir / "well characteristics.pdf").exists() else "Well characteristics.pdf"
        small_name = "Small well characteristics.pdf"

        large_path = chapter_dir / large_name
        small_path = chapter_dir / small_name

        if large_path.exists():
            large_rows.extend(extract_large_wells(large_path, book_label))
        else:
            print(f"MISSING: {large_path}")

        if small_path.exists():
            small_rows.extend(extract_small_wells(small_path, book_label))
        else:
            print(f"MISSING: {small_path}")

    df_large = pd.DataFrame(large_rows).sort_values(["book", "code", "page_num"])
    df_small = pd.DataFrame(small_rows).sort_values(["book", "code", "page_num"])
    frames = [df for df in (df_large, df_small) if not df.empty]
    if frames:
        all_columns = []
        for frame in frames:
            for column in frame.columns:
                if column not in all_columns:
                    all_columns.append(column)
        frames = [frame.reindex(columns=all_columns).astype(object) for frame in frames]
        df_all = pd.concat(frames, ignore_index=True).sort_values(["book", "well_class", "code"])
    else:
        df_all = pd.DataFrame()

    out_large = OUT_DIR / "well_characteristics.csv"
    out_small = OUT_DIR / "small_well_characteristics.csv"
    out_all = OUT_DIR / "all_wells.csv"

    df_large.to_csv(out_large, index=False)
    df_small.to_csv(out_small, index=False)
    df_all.to_csv(out_all, index=False)

    print(f"Saved: {out_large} ({len(df_large)} rows)")
    print(f"Saved: {out_small} ({len(df_small)} rows)")
    print(f"Saved: {out_all} ({len(df_all)} rows)")

    return 0


if __name__ == "__main__":
    sys.exit(main())