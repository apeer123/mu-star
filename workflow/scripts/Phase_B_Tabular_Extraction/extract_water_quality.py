"""
Extract Chapter 6 water-quality sampling sites and summary parameter ranges.

Outputs written to extracted_water_quality/:
  river_sampling_points.csv
  groundwater_sampling_points.csv
  water_quality_parameter_ranges.csv
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


def parse_range(value):
    raw = clean_cell(value)
    if not raw or raw == "-":
        return raw or None, None, None, None

    qualifier = None
    if raw.startswith("<"):
        qualifier = "<"
    compact = raw.replace(" ", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", compact)
    if len(numbers) >= 2:
        return raw, qualifier, float(numbers[0]), float(numbers[1])
    if len(numbers) == 1:
        number = float(numbers[0])
        return raw, qualifier, number, number
    return raw, qualifier, None, None


def extract_river_sampling_points(tables, book_label, page_num, current_river):
    rows = []
    for table in tables:
        header = [clean_cell(cell).upper() for cell in table[0]] if table else []
        if header[:2] != ["RIVER", "SAMPLING POINT"]:
            continue

        for raw_row in table[1:]:
            river = clean_cell(raw_row[0]) if len(raw_row) > 0 else ""
            sampling_point = clean_cell(raw_row[1]) if len(raw_row) > 1 else ""
            if river:
                current_river = river
            if not sampling_point:
                continue
            rows.append({
                "book": book_label,
                "page_num": page_num,
                "river": current_river,
                "sampling_point": sampling_point,
            })

    return rows, current_river


def extract_groundwater_sampling_points(tables, book_label, page_num, current_region):
    rows = []
    for table in tables:
        if not table:
            continue
        header = [clean_cell(cell).upper() for cell in table[0]]
        is_three_col = header[:3] == ["REGION", "BH NO", "NAME"]
        is_two_col = header[:2] == ["BH NO.", "NAME"]
        is_continuation = len(table[0]) >= 3 and clean_cell(table[0][0]) == "" and clean_cell(table[0][1]) and clean_cell(table[0][2])

        if not (is_three_col or is_two_col or is_continuation):
            continue

        start_index = 0 if is_continuation else 1
        for raw_row in table[start_index:]:
            cells = [clean_cell(cell) for cell in raw_row]
            if not any(cells):
                continue

            if is_three_col or is_continuation:
                region = cells[0] if len(cells) > 0 else ""
                borehole_no = cells[1] if len(cells) > 1 else ""
                name = cells[2] if len(cells) > 2 else ""
                if region:
                    current_region = region
            else:
                borehole_no = cells[0] if len(cells) > 0 else ""
                name = cells[1] if len(cells) > 1 else ""

            if not borehole_no or not name:
                continue

            rows.append({
                "book": book_label,
                "page_num": page_num,
                "region": current_region,
                "borehole_no_raw": borehole_no,
                "name": name,
            })

    return rows, current_region


def extract_parameter_ranges(tables, book_label, page_num):
    rows = []
    for table in tables:
        if not table:
            continue
        header = [clean_cell(cell) for cell in table[0]]
        if len(header) < 3 or header[0].upper() != "PARAMETER":
            continue

        water_source = header[1].strip().lower().replace(" ", "_")
        for raw_row in table[1:]:
            if len(raw_row) < 3:
                continue
            parameter = clean_cell(raw_row[0])
            observed = clean_cell(raw_row[1])
            who_standard = clean_cell(raw_row[2])
            if not parameter:
                continue

            observed_raw, observed_qualifier, observed_min, observed_max = parse_range(observed)
            who_raw, who_qualifier, who_min, who_max = parse_range(who_standard)
            rows.append({
                "book": book_label,
                "page_num": page_num,
                "water_source": water_source,
                "parameter": parameter,
                "observed_range_raw": observed_raw,
                "observed_qualifier": observed_qualifier,
                "observed_min": observed_min,
                "observed_max": observed_max,
                "who_standard_raw": who_raw,
                "who_qualifier": who_qualifier,
                "who_min": who_min,
                "who_max": who_max,
            })

    return rows


def main():
    river_rows = []
    groundwater_rows = []
    parameter_rows = []

    for book_label, base_dir in BOOKS.items():
        pdf_name = "water quality.pdf" if (base_dir / "Chapter 6" / "water quality.pdf").exists() else "Water quality.pdf"
        pdf_path = base_dir / "Chapter 6" / pdf_name
        if not pdf_path.exists():
            print(f"MISSING: {pdf_path}")
            continue

        with pdfplumber.open(pdf_path) as pdf:
            current_river = None
            current_region = None
            for page_num in range(3, len(pdf.pages) + 1):
                tables = pdf.pages[page_num - 1].extract_tables() or []
                new_river_rows, current_river = extract_river_sampling_points(tables, book_label, page_num, current_river)
                new_groundwater_rows, current_region = extract_groundwater_sampling_points(
                    tables, book_label, page_num, current_region
                )
                river_rows.extend(new_river_rows)
                groundwater_rows.extend(new_groundwater_rows)
                parameter_rows.extend(extract_parameter_ranges(tables, book_label, page_num))

    df_river = pd.DataFrame(river_rows).sort_values(["book", "river", "sampling_point"])
    df_groundwater = pd.DataFrame(groundwater_rows).sort_values(["book", "region", "name"])
    df_params = pd.DataFrame(parameter_rows).sort_values(["book", "water_source", "parameter"])

    out_river = OUT_DIR / "river_sampling_points.csv"
    out_groundwater = OUT_DIR / "groundwater_sampling_points.csv"
    out_params = OUT_DIR / "water_quality_parameter_ranges.csv"

    df_river.to_csv(out_river, index=False)
    df_groundwater.to_csv(out_groundwater, index=False)
    df_params.to_csv(out_params, index=False)

    print(f"Saved: {out_river} ({len(df_river)} rows)")
    print(f"Saved: {out_groundwater} ({len(df_groundwater)} rows)")
    print(f"Saved: {out_params} ({len(df_params)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())