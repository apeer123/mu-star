"""
Extract monthly precipitation data from Chapter 2 PDFs of BOTH Hydrology Data Books.

Source PDFs (same structure, different year ranges):
  2006-2010: precipitation data.pdf  (lowercase p)
  2000-2005: Precipitation data.pdf  (capital P)

PDF table structure per station (one table per station per page):
  Row 0 : 'PRECIPITATION RECORD\\nStation Location : X  Station Coordinates : E , N'
  Row 1 : ['PERIOD', 'JAN', 'FEB', ..., 'DEC', 'YEAR']
  Row 2 : All years and values stacked with \\n within each cell

Also extracts long-term mean rainfall from Rainfall data.pdf (both books).

Outputs (written to extracted_rainfall/):
  precipitation_monthly.csv  — station, year, month, rainfall_mm, book
  rainfall_longterm_means.csv — period, annual_mean_mm, book
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

# ---------------------------------------------------------------------------
# Book definitions
# ---------------------------------------------------------------------------
BOOKS = {
    "2006-2010": {
        "base": Path(Path("../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book").resolve()),
        "precip_file": "Chapter 2/precipitation data.pdf",
        "rainfall_file": "Chapter 2/Rainfall data.pdf",
    },
    "2000-2005": {
        "base": Path("."),
        "precip_file": "Chapter 2/Precipitation data.pdf",
        "rainfall_file": "Chapter 2/Rainfall data.pdf",
    },
}

OUT_DIR = Path(".")
OUT_DIR.mkdir(parents=True, exist_ok=True)

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_station_header(cell_text):
    """Extract station name and coordinates from the header cell of a precipitation table.
    Always returns a 3-tuple (station_name, easting, northing).
    """
    if not cell_text:
        return "", None, None
    # Station name between 'Station Location' and 'Station Coordinates'
    name_match = re.search(r"Station Location\s*:\s*([A-Z0-9 _'()/.-]+?)(?:\s+Station Coordinates|$)", cell_text, re.I)
    coord_match = re.search(r"Coordinates\s*:\s*([\d]+)\s*E\s*,\s*([\d]+)\s*N", cell_text, re.I)
    station_name = name_match.group(1).strip() if name_match else ""
    easting = int(coord_match.group(1)) if coord_match else None
    northing = int(coord_match.group(2)) if coord_match else None
    return station_name, easting, northing


def split_stacked_cell(cell_text):
    """Split a stacked cell (years or values separated by \\n) into a list."""
    if not cell_text:
        return []
    parts = str(cell_text).strip().split("\n")
    return [p.strip() for p in parts if p.strip()]


def extract_precip_from_table(table):
    """
    Parse one precipitation table (one station, one period) into rows.
    Returns list of dicts: {station, easting, northing, year, month, rainfall_mm}
    """
    if not table or len(table) < 3:
        return [], ""

    # Row 0: header with station info
    header_cell = table[0][0] or ""
    station_name, easting, northing = parse_station_header(header_cell)

    # Skip tables that don't look like precipitation tables
    if not station_name and "precipitation record" not in header_cell.lower():
        return [], ""

    # Row 1: column names — find indices of months
    col_row = table[1]
    # Safe: strip whitespace from each cell label
    col_labels = [str(c).strip().upper() if c else "" for c in col_row]

    # Map month name -> column index
    month_col = {}
    period_col = None
    year_col = None
    for idx, label in enumerate(col_labels):
        if label == "PERIOD":
            period_col = idx
        elif label in MONTH_NUM:
            month_col[label] = idx
        elif label == "YEAR":
            year_col = idx

    if period_col is None or not month_col:
        return [], station_name

    # Row 2+ (usually just row 2): data with stacked values
    records = []
    for data_row in table[2:]:
        if not data_row or data_row[period_col] is None:
            continue
        years = split_stacked_cell(data_row[period_col])
        if not years:
            continue

        # For each month, get the stacked values
        month_values = {}
        for m, idx in month_col.items():
            vals = split_stacked_cell(data_row[idx]) if idx < len(data_row) else []
            month_values[m] = vals

        # Zip years with month values
        for yr_i, yr_str in enumerate(years):
            try:
                year = int(yr_str)
            except ValueError:
                continue
            for month, vals in month_values.items():
                if yr_i < len(vals):
                    val_str = vals[yr_i]
                    try:
                        val = float(val_str)
                    except ValueError:
                        val = None
                    records.append({
                        "station": station_name,
                        "easting": easting,
                        "northing": northing,
                        "year": year,
                        "month": MONTH_NUM[month],
                        "month_abbr": month,
                        "rainfall_mm": val,
                    })
    return records, station_name


def extract_longterm_means(pdf_path, book_label):
    """Extract long-term mean rainfall from Rainfall data.pdf."""
    rows = []
    if not pdf_path.exists():
        print(f"  MISSING: {pdf_path.name}")
        return rows
    with pdfplumber.open(pdf_path) as doc:
        for pg in doc.pages:
            tables = pg.extract_tables()
            for tbl in tables:
                for row in tbl:
                    if not row or not row[0]:
                        continue
                    period_str = str(row[0]).strip()
                    # Expect period like '1931-1960' or '1961-1990'
                    if re.match(r"\d{4}-\d{4}", period_str):
                        try:
                            annual_mean = float(str(row[1]).strip())
                        except (ValueError, IndexError):
                            annual_mean = None
                        rows.append({"period": period_str, "annual_mean_mm": annual_mean, "book": book_label})
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    all_precip = []
    all_longterm = []

    for book_label, book_info in BOOKS.items():
        base = book_info["base"]
        precip_path = base / book_info["precip_file"]
        rainfall_path = base / book_info["rainfall_file"]

        # --- Precipitation monthly data
        if not precip_path.exists():
            print(f"MISSING {book_label}: {precip_path}")
        else:
            print(f"\nProcessing {book_label}: {precip_path.name}")
            with pdfplumber.open(precip_path) as doc:
                for pg_i, pg in enumerate(doc.pages):
                    tables = pg.extract_tables()
                    for tbl_i, tbl in enumerate(tables):
                        records, station_name = extract_precip_from_table(tbl)
                        for rec in records:
                            rec["book"] = book_label
                            all_precip.append(rec)
                        if records:
                            print(f"  Page {pg_i+1} Table {tbl_i+1}: {station_name} -> {len(records)} rows")
                        elif station_name:
                            print(f"  Page {pg_i+1} Table {tbl_i+1}: {station_name} -> 0 rows (check format)")

        # --- Long-term mean rainfall
        lt = extract_longterm_means(rainfall_path, book_label)
        all_longterm.extend(lt)
        print(f"  Long-term means: {len(lt)} rows")

    # --- Save precipitation monthly
    if all_precip:
        df = pd.DataFrame(all_precip)
        # Sort
        df = df.sort_values(["book", "station", "year", "month"]).reset_index(drop=True)
        out_p = OUT_DIR / "precipitation_monthly.csv"
        df.to_csv(out_p, index=False)
        print(f"\nSaved: {out_p}")
        print(f"  Rows: {len(df)}, Stations: {df.station.nunique()}, "
              f"Years: {df.year.min()}-{df.year.max()}")
        print(df.groupby(["book", "station"])["rainfall_mm"].count().to_string())
    else:
        print("WARNING: No precipitation records extracted")

    # --- Save long-term means
    if all_longterm:
        df_lt = pd.DataFrame(all_longterm)
        out_lt = OUT_DIR / "rainfall_longterm_means.csv"
        df_lt.to_csv(out_lt, index=False)
        print(f"\nSaved: {out_lt}")
        print(df_lt.to_string(index=False))
    else:
        print("WARNING: No long-term means found")


if __name__ == "__main__":
    main()
