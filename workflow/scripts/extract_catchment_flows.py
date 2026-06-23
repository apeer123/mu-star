"""
Extract annual discharge tables from the Mauritius Hydrology Data Book catchment PDFs.

TWO PDF FORMATS exist in Chapter 3 / Schematic Diagrams and Flow Data:

  SUMMARY FORMAT (e.g. A03.pdf, B01.pdf):
    - Page 1: Station description (river name, code, location, catchment area)
    - Page 2: Five annual tables, one per hydrological year 2005/06-2009/10
              Columns: NOV DEC JAN FEB MAR APR MAY JUN JUL AUG SEP OCT [YEAR total]
              Rows:    Volume (Mm3), Mean (m3/s), Max (m3/s), Min (m3/s)

  DAILY FORMAT (e.g. J01.pdf, E008a.pdf, W03.pdf):
    - Page 1: Station schematic / map
    - Page 2: Station description (may cover multiple stations)
    - Pages 3+: One data page per hydrological year
                Title: "ANNUAL DISCHARGE RECORD RIVER <name> : <station_code>"
                Columns: Day | NOV | DEC | JAN | FEB | MAR | APR | MAY | JUN | JUL | AUG | SEP | OCT
                Rows:    1-31 daily discharge values in m3/s

For daily format, monthly statistics are aggregated from the daily data:
  - Mean (m3/s)   = mean of valid daily values
  - Max  (m3/s)   = maximum daily value
  - Min  (m3/s)   = minimum positive daily value
  - Volume (Mm3)  = sum(Q_day * 86400) / 1_000_000

The Mauritius hydrological year runs November (start_year) to October (end_year).
  e.g. "2005/06" -> Nov 2005, Dec 2005, Jan-Oct 2006

Output: one CSV per station (named <STATION_CODE>_flows.csv) with columns:
    station_code, station_name, river, catchment_code, catchment_area_km2,
    hydro_year, year, month, volume_Mm3, mean_m3s, max_m3s, min_m3s

Usage:
    python extract_catchment_flows.py \
        --indir  "processed_data/Hydrology_Data_Book/Chapter 3/Schematic Diagrams and Flow Data" \
        --outdir "processed_data/Hydrology_Data_Book/extracted_flows"
"""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HYDRO_MONTHS = ["NOV", "DEC", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT"]

MONTH_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Months that belong to the START year of the hydrological year
FIRST_HALF_MONTHS = {"NOV", "DEC"}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def parse_year_label(cell_text):
    """
    Extract the hydrological year from a pdfplumber table cell.

    The year label is rotated 90 degrees so pdfplumber returns it
    character-by-character separated by newlines; we reverse and reconstruct.

    Examples:
        '6\n0\n/\n5\n0\n0\n2\n:\nR\nA\nE\nY'  -> 'YEAR:2005/06' -> '2005/06'
        '6\n0\n0\n2\n/\n5\n0\n0\n2\nR\nA\nE\nY' -> 'YEAR2005/2006' -> '2005/06'
    """
    if not cell_text:
        return None
    chars = cell_text.split("\n")
    chars_reversed = list(reversed(chars))
    raw_str = "".join(chars_reversed)
    year_str = re.sub(r'[^\d/]', '', raw_str)
    
    if "/" in year_str and len(year_str) == 7:
        return year_str
    if "/" in year_str and len(year_str) == 9:
        parts = year_str.split("/")
        return f"{parts[0]}/{parts[1][2:]}"
    if len(year_str) == 6 and "/" not in year_str:
        return f"{year_str[:4]}/{year_str[4:]}"
    # Fallback aggressive matching within the string just in case it got munged
    m = re.search(r"(\d{4})\s*[/|-]?\s*(\d{2,4})", year_str)
    if m:
        y1, y2 = m.groups()
        if len(y2) == 4:
            y2 = y2[2:]
        return f"{y1}/{y2}"
    return year_str if year_str else None


def hydro_year_to_calendar(hydro_year, month_abbr):
    """Convert hydrological year + month to (calendar_year, calendar_month_int)."""
    try:
        start_year = int(hydro_year.split("/")[0])
    except (ValueError, IndexError):
        start_year = 0
    end_year = start_year + 1
    cal_year = start_year if month_abbr in FIRST_HALF_MONTHS else end_year
    return cal_year, MONTH_NUM[month_abbr]


def parse_station_metadata(page_text):
    """Extract station code, river name, location etc. from a description page."""
    meta = {}
    patterns = {
        "river":                     r"RIVER(?:/CANAL)?\s*:\s*([^\n]+)",
        "catchment_code":            r"CATCHMENT CODE\s*:\s*([A-Z]+)",
        "station_code":              r"STATION CODE\s*:\s*([A-Z0-9]+)",
        "location":                  r"LOCATION\s*:\s*([^\n]+)",
        "catchment_area_at_station": r"(?:At Station|Catchment Area \(Km2\)|Area at Station)\s*[:=]?\s*([\d.]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, page_text, re.IGNORECASE)
        if m:
            meta[key] = m.group(1).strip()
    return meta


# ---------------------------------------------------------------------------
# Summary-format parser
# ---------------------------------------------------------------------------

def _extract_all_metric_values(text, metric_pattern):
    """Find all metric lines on the page and extract their monthly floats."""
    pattern = (
        rf"{re.escape(metric_pattern)}"
        r"[^\d]+((?:[\d.]+[ \t]+){11}[\d.]+(?:[ \t]+[\d.]+)?)"
    )
    matches = re.findall(pattern, text)
    return [[float(v) for v in m.split()[:13]] for m in matches]

def _extract_metric_values(text, metric_pattern):
    res = _extract_all_metric_values(text, metric_pattern)
    return res[0] if res else None


def _parse_summary_page(page_text, tables, pdf_name, meta):
    """Parse one summary-format data page. Returns monthly row dicts."""
    rows = []

    year_labels = []
    for tbl in tables:
        if len(tbl) >= 2 and tbl[1]:
            year_labels.append(parse_year_label(tbl[1][0] or ""))
        else:
            year_labels.append(None)

    year_blocks = re.split(
        r"NOV\s+DEC\s+JAN\s+FEB\s+MAR\s+APR\s+MAY\s+JUN\s+JUL\s+AUG\s+SEP\s+OCT\s+YEAR",
        page_text,
    )
    data_blocks = year_blocks[1:]

    for idx, block in enumerate(data_blocks):
        hydro_year = year_labels[idx] if idx < len(year_labels) else None
        if not hydro_year:
            ym = re.search(r"(\d{4}/\d{2})", block)
            hydro_year = ym.group(1) if ym else f"unknown_{idx}"

        volumes = _extract_metric_values(block, "Volume (Mm3")
        means   = _extract_metric_values(block, "Mean (m3/s)")
        maxs    = _extract_metric_values(block, "Max (m3/s)")
        mins    = _extract_metric_values(block, "Min (m3/s)")

        if not volumes:
            print(f"  [WARN] {pdf_name}: could not parse Volume row for {hydro_year}")
            continue

        for m_idx, month_abbr in enumerate(HYDRO_MONTHS):
            cal_year, cal_month = hydro_year_to_calendar(hydro_year, month_abbr)
            
            mean_q = means[m_idx] if means and m_idx < len(means) else None
            max_q  = maxs[m_idx] if maxs and m_idx < len(maxs) else None
            min_q  = mins[m_idx] if mins and m_idx < len(mins) else None
            
            # Validation checks (Fix 2/4/5 swaps)
            if min_q is not None and mean_q is not None and min_q > mean_q:
                min_q, mean_q = mean_q, min_q
            if mean_q is not None and max_q is not None and mean_q > max_q:
                mean_q, max_q = max_q, mean_q
                
            rows.append({
                "station_code":        meta.get("station_code", ""),
                "station_name":        meta.get("station_name", ""),
                "river":               meta.get("river", ""),
                "catchment_code":      meta.get("catchment_code", ""),
                "catchment_area_km2":  meta.get("catchment_area_at_station", ""),
                "hydro_year":          hydro_year,
                "year":                cal_year,
                "month":               cal_month,
                "volume_Mm3":  volumes[m_idx] if m_idx < len(volumes) else None,
                "mean_m3s":    mean_q,
                "max_m3s":     max_q,
                "min_m3s":     min_q,
            })
    return rows


# ---------------------------------------------------------------------------
# Daily-format parser
# ---------------------------------------------------------------------------

def _parse_daily_page(page_text, tables, pdf_name, meta):
    """
    Parse one daily-format data page and aggregate to monthly stats.
    Splits the page text by "Day Nov Dec..." headers to isolate multi-year blocks.
    """
    rows = []

    # Station code from page title (overrides PDF-level metadata for multi-station PDFs)
    title_m = re.search(r"ANNUAL DISCHARGE RECORD.*?:\s*([A-Z][A-Z0-9]+)\s*$", page_text, re.MULTILINE)
    station_code = title_m.group(1) if title_m else meta.get("station_code", "")

    river = meta.get("river", "")
    if title_m:
        river_m = re.search(
            r"ANNUAL DISCHARGE RECORD\s+RIVER\s+(.*?)\s*:\s*[A-Z][A-Z0-9]+\s*$",
            page_text, re.MULTILINE,
        )
        if river_m:
            raw = river_m.group(1).strip()
            # Collapse spaced-out chars: 'C i t r o n' -> 'Citron'
            river = re.sub(r"(?<=\w) (?=\w)", "", raw)
    station_name = f"{river} at {meta.get('location', '')}".strip(" at")

    # Fix 3: Extract all summaries at the page level to prevent cross-block pollution
    page_mean_overrides = _extract_all_metric_values(page_text, "Mean (m3/s)")
    page_vol_overrides  = _extract_all_metric_values(page_text, "Volume (Mm3")
    
    # Split page by "Day Nov Dec Jan"
    blocks = re.split(r"(?i)\bDay\s+Nov\s+Dec", page_text)
    
    # Extract year labels from table cells
    year_labels = []
    for tbl in tables:
        if len(tbl) >= 2 and tbl[1]:
            hydro_year = parse_year_label(tbl[1][0] or "")
            if hydro_year:
                year_labels.append(hydro_year)

    # Fallback to Regex if table borders missed the year cell
    if not year_labels:
        yms = re.findall(r"(\d{4}/\d{2})", page_text)
        year_labels = yms if yms else ["unknown"]

    # Parse each year block separately
    for idx, block in enumerate(blocks[1:]):
        hydro_year = year_labels[idx] if idx < len(year_labels) else year_labels[-1]
        
        daily_data = defaultdict(list)
        for line in block.split("\n"):
            # Strip rotated column headers like '0 11 0.105' -> '11 0.105'
            clean_line = re.sub(r'^[A-Za-z0-9/]\s+(?=\d{1,2}\s+\d+\.\d+)', '', line)
            parts = clean_line.split()
            if not parts or not parts[0].isdigit():
                continue
            day = int(parts[0])
            if not (1 <= day <= 31):
                continue
            for col_idx, v in enumerate(parts[1:]):
                if col_idx >= len(HYDRO_MONTHS):
                    break
                try:
                    daily_data[col_idx].append(float(v))
                except ValueError:
                    break

        if not daily_data:
            print(f"  [WARN] {pdf_name}: no daily rows found for {hydro_year} station {station_code}")
            continue

        mean_override = page_mean_overrides[idx] if idx < len(page_mean_overrides) else None
        vol_override  = page_vol_overrides[idx] if idx < len(page_vol_overrides) else None

        for m_idx, month_abbr in enumerate(HYDRO_MONTHS):
            vals = daily_data.get(m_idx, [])
            if not vals:
                continue
            positive_vals = [v for v in vals if v > 0]
            
            mean_q  = mean_override[m_idx] if mean_override and m_idx < len(mean_override) else sum(vals) / len(vals)
            volume  = vol_override[m_idx] if vol_override and m_idx < len(vol_override) else sum(v * 86400 for v in vals) / 1_000_000
            
            max_q   = max(vals)
            min_q   = min(positive_vals) if positive_vals else 0.0
            
            # Validation checks (Fix 2/4/5 swaps)
            if min_q > mean_q:
                min_q, mean_q = mean_q, min_q
            if mean_q > max_q:
                mean_q, max_q = max_q, mean_q

            cal_year, cal_month = hydro_year_to_calendar(hydro_year, month_abbr)
            rows.append({
                "station_code":        station_code,
                "station_name":        station_name,
                "river":               river,
                "catchment_code":      meta.get("catchment_code", ""),
                "catchment_area_km2":  meta.get("catchment_area_at_station", ""),
                "hydro_year":          hydro_year,
                "year":                cal_year,
                "month":               cal_month,
                "volume_Mm3":  round(volume, 4),
                "mean_m3s":    round(mean_q, 4),
                "max_m3s":     round(max_q, 4),
                "min_m3s":     round(min_q, 4),
            })
    return rows


def _is_daily_format(page_text):
    """Return True if this page uses daily-discharge format (Day | Nov | Dec ...)."""
    return bool(re.search(r"\bDay\s+Nov\s+Dec\s+Jan\b", page_text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Main per-PDF extraction
# ---------------------------------------------------------------------------

def extract_catchment_pdf(pdf_path):
    """
    Extract all monthly flow rows from one catchment PDF.

    Returns dict: station_code -> list of row dicts.
    (Most PDFs have one station; some daily-format PDFs embed multiple stations,
    each identified by its "ANNUAL DISCHARGE RECORD ... : STATION" title.)
    """
    station_rows = defaultdict(list)

    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) < 2:
            print(f"  [WARN] {pdf_path.name}: only {len(pdf.pages)} page(s) - skipping")
            return {}

        # Find station metadata from the first description page
        meta = {}
        for pg_idx in range(min(2, len(pdf.pages))):
            text = pdf.pages[pg_idx].extract_text() or ""
            if "STATION CODE" in text or "RIVER" in text:
                meta = parse_station_metadata(text)
                if meta.get("station_code"):
                    break
        station_code_default = meta.get("station_code", pdf_path.stem.upper())
        location = meta.get("location", "")
        river_default = meta.get("river", "")
        meta["station_name"] = f"{river_default} at {location}".strip(" at")
        meta["station_code"] = station_code_default

        for page in pdf.pages[1:]:
            page_text = page.extract_text() or ""
            tables = page.extract_tables()

            if not page_text:
                continue
            has_discharge = (
                "ANNUAL DISCHARGE RECORD" in page_text
                or bool(re.search(r"NOV\s+DEC\s+JAN", page_text))
            )
            if not has_discharge:
                continue

            if _is_daily_format(page_text):
                new_rows = _parse_daily_page(page_text, tables, pdf_path.name, meta)
            else:
                new_rows = _parse_summary_page(page_text, tables, pdf_path.name, meta)

            for row in new_rows:
                sc = row.get("station_code") or station_code_default
                station_rows[sc].append(row)

    return dict(station_rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract discharge tables from Hydrology Data Book PDFs")
    parser.add_argument(
        "--indir",
        required=True,
        help="Directory containing catchment PDFs",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Directory for output CSVs",
    )
    args = parser.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(indir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {indir}")
        return

    print(f"Processing {len(pdf_files)} catchment PDFs -> {outdir}")

    FIELDNAMES = [
        "station_code", "station_name", "river", "catchment_code",
        "catchment_area_km2", "hydro_year", "year", "month",
        "volume_Mm3", "mean_m3s", "max_m3s", "min_m3s",
    ]

    total_rows = 0
    total_stations = 0
    failed = []

    for pdf_path in pdf_files:
        print(f"  Extracting {pdf_path.name} ...", end=" ")
        try:
            station_data = extract_catchment_pdf(pdf_path)
        except Exception as exc:
            print(f"ERROR: {exc}")
            failed.append(pdf_path.name)
            continue

        if not station_data:
            print("0 rows (skipped)")
            failed.append(pdf_path.name)
            continue

        for station_code, rows in station_data.items():
            out_csv = outdir / f"{station_code}_flows.csv"
            file_exists = out_csv.exists()
            with open(out_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(rows)
            total_rows += len(rows)
            total_stations += 1
            print(f"{len(rows)} rows -> {out_csv.name}", end="  ")
        print()

    print(f"\nDone. {total_rows} monthly rows written across {total_stations} station-files.")
    if failed:
        print(f"Skipped (no data / 1-page schematics): {failed}")


if __name__ == "__main__":
    main()
