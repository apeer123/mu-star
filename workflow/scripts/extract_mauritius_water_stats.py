"""
Extract water production and sales statistics from Mauritius Statistics
"Digest of Energy and Water Statistics" workbooks (2005-2020).

Source: Statistics Mauritius — Energy_Water_YrXX.xls (16 annual files)
        Issued by: Statistics Mauritius (statsmauritius.govmu.org)
        Provided by: Silvia Colombo, Oxford / MSTAR project

Each workbook covers two calendar years (current and previous, e.g. 2019-2020).
The relevant sheets are:
  - 'wat prod' / 'TAB15'  : Average monthly potable water production by supply zone
  - 'Wat sale ' / 'TAB16' : Water sales by tariff type
  - 'rainfall' / 'TAB13'  : Mean monthly rainfall (bonus)

Outputs (in --out-dir):
  mauritius_water_production.csv   — monthly production by zone (Mm3), 2004-2020
  mauritius_water_sales.csv        — annual sales by tariff type, 2004-2020
  mauritius_rainfall.csv           — mean annual/monthly rainfall by region, 2004-2020

Column schema (water production):
  year, month, supply_zone, surface_Mm3, borehole_Mm3, total_Mm3

Column schema (water sales):
  year, tariff_type, subscribers, volume_m3_thousand, amount_rs000

Tom Russell's instruction: script the data extraction where possible.
Usage:
    python extract_mauritius_water_stats.py
    python extract_mauritius_water_stats.py --stats-dir PATH --out-dir PATH
"""

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEFAULT_STATS_DIR = (
    "."
)
DEFAULT_OUT_DIR = (
    "."
    r"\extracted"
)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Mapping from month abbreviation to month number
MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}

# ---------------------------------------------------------------------------
# Canonical zone names (normalise spelling variants across workbook editions)
# ---------------------------------------------------------------------------
ZONE_CANONICAL = {
    # Mare Aux Vacoas Upper
    "mare aux vacoas (upper)":           "Mare Aux Vacoas (Upper)",
    "mare aux vacoas (upper maw)":       "Mare Aux Vacoas (Upper)",
    "mare aux vacoas  (upper maw)":      "Mare Aux Vacoas (Upper)",
    # Mare Aux Vacoas Lower
    "mare aux vacoas (lower)":           "Mare Aux Vacoas (Lower)",
    "mare aux vacoas (lower maw)":       "Mare Aux Vacoas (Lower)",
    "mare aux vacoas  (lower maw)":      "Mare Aux Vacoas (Lower)",
    # Port Louis
    "port -louis":                       "Port Louis",
    "port-louis":                        "Port Louis",
    "port louis":                        "Port Louis",
    # DWS North
    "district water supply - north":     "DWS North",
    "district water supply - north":     "DWS North",
    "district water supply  (dws north)": "DWS North",
    "dws north":                         "DWS North",
    # DWS South
    "district water supply - south":     "DWS South",
    "district water supply  (dws south)": "DWS South",
    "dws south":                         "DWS South",
    # DWS East
    "district water supply - east":      "DWS East",
    "district water supply  (dws east)": "DWS East",
    "dws east":                          "DWS East",
}


def normalise_zone(name: str) -> str:
    """Map spelling variants to a canonical supply zone name."""
    return ZONE_CANONICAL.get(name.lower().strip(), name.strip())


# ---------------------------------------------------------------------------
# Helper: find the right sheet by keyword
# ---------------------------------------------------------------------------
def find_sheet(xl: pd.ExcelFile, keywords: list[str]) -> str | None:
    """Return first sheet name that contains any keyword (case-insensitive)."""
    for sh in xl.sheet_names:
        sh_lower = sh.strip().lower()
        for kw in keywords:
            if kw.lower() in sh_lower:
                return sh
    return None


# ---------------------------------------------------------------------------
# Parse years from title cell (row 0, col 0)
# ---------------------------------------------------------------------------
def parse_years(title_str: str) -> tuple[int, int] | None:
    """Extract two years from title e.g. '2004-2005' or '2019 and 2020'."""
    years = re.findall(r"\b(20\d{2}|199\d)\b", str(title_str))
    if len(years) >= 2:
        return int(years[0]), int(years[1])
    if len(years) == 1:
        return int(years[0]), int(years[0])
    return None


# ---------------------------------------------------------------------------
# Parse water production sheet
# ---------------------------------------------------------------------------
def parse_water_production(df: pd.DataFrame, year1: int, year2: int) -> pd.DataFrame:
    """
    Extract monthly water production by supply zone from the raw sheet DataFrame.

    Sheet layout (0-indexed rows):
      Row 0 : Table title
      Row 1 : blank
      Row 2 : Zone-level column headers (forward-filled)
      Row 3 : Source-level headers: Surface, Borehole, Total
      Row 4 : Units (Mm3)
      Row 5 : Year1 annual total  (col 0 = year e.g. 2004)
      Rows 6-17  : Jan-Dec for Year1
      Row 18: Year2 annual total  (col 0 = year e.g. 2005)
      Rows 19-30 : Jan-Dec for Year2
    """
    records = []

    # Build column labels from rows 2 and 3
    zone_row   = df.iloc[2]   # zone names (some cells NaN due to merging)
    source_row = df.iloc[3]   # Surface / Borehole / Total

    # Forward-fill zone names across merged cells
    zone_ffill = []
    current_zone = ""
    for v in zone_row:
        v_str = str(v).strip() if pd.notna(v) else ""
        if v_str and v_str.lower() not in ("nan", "month", ""):
            current_zone = v_str
        zone_ffill.append(current_zone)

    # Combine zone + source into column labels
    col_labels = []
    for zone, src in zip(zone_ffill, source_row):
        src_str = str(src).strip() if pd.notna(src) else ""
        col_labels.append((zone, src_str))

    # Find year-block start rows: rows where col-0 value is a 4-digit year
    year_rows = {}
    for i in range(5, len(df)):
        val = str(df.iloc[i, 0]).strip()
        m = re.match(r"^(20\d{2}|199\d)$", val)
        if m:
            year_rows[int(m.group(1))] = i

    # Identify supply zones: zones that have a 'Total' column (exclude "Month", "Total production" etc.)
    total_col_positions = []
    for col_idx, (zone, src) in enumerate(col_labels):
        if src.lower() == "total" and zone.lower() not in ("", "month"):
            # Also skip the grand-total zone
            if "total" not in zone.lower():
                total_col_positions.append((col_idx, zone))

    # For each year block, extract monthly data
    for year, start_row in sorted(year_rows.items()):
        if year not in (year1, year2):
            continue
        # Monthly rows: 12 rows after the annual-total row
        for offset in range(1, 13):
            row_idx = start_row + offset
            if row_idx >= len(df):
                break
            month_val = str(df.iloc[row_idx, 0]).strip()
            if month_val not in MONTH_NUM:
                # Some files use full month names or numbers
                # Try to match partial
                matched = None
                for abbr in MONTHS:
                    if month_val.startswith(abbr):
                        matched = abbr
                        break
                if matched is None:
                    continue
                month_val = matched
            month_num = MONTH_NUM[month_val]

            for col_idx, zone in total_col_positions:
                # The 'Total' column is at col_idx
                # Surface is 2 columns before (col_idx-2), Borehole 1 before (col_idx-1)
                surf_idx = col_idx - 2
                bore_idx = col_idx - 1
                total_idx = col_idx

                def safe_float(df_local, ridx, cidx):
                    try:
                        v = df_local.iloc[ridx, cidx]
                        v = pd.to_numeric(v, errors="coerce")
                        return float(v) if pd.notna(v) else np.nan
                    except (IndexError, TypeError):
                        return np.nan

                records.append({
                    "year":        year,
                    "month":       month_num,
                    "supply_zone": normalise_zone(zone.replace("\n", " ").strip()),
                    "surface_Mm3": safe_float(df, row_idx, surf_idx),
                    "borehole_Mm3": safe_float(df, row_idx, bore_idx),
                    "total_Mm3":   safe_float(df, row_idx, total_idx),
                })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Parse water sales sheet
# ---------------------------------------------------------------------------
def parse_water_sales(df: pd.DataFrame, year1: int, year2: int) -> pd.DataFrame:
    """
    Extract annual water sales totals by tariff type.

    Layout (both old 'Wat sale' and new 'TAB16'):
      - One row contains year values (as integers or strings) in later columns.
      - Pattern per year: base_col = subscribers, base_col+2 = volume, base_col+4 = amount.
      - Tariff name is always in col 1 (col 0 is either blank or the zone label).
    """
    records = []

    # Find the header row: first row that has two 4-digit year values >= 2000
    header_row = None
    year_col_map = {}  # year_int -> base column index
    for i in range(min(8, len(df))):
        row = df.iloc[i]
        found_years = {}
        for c, val in enumerate(row):
            m = re.match(r"^(20\d{2}|199\d)$", str(val).strip())
            if m:
                found_years[int(m.group(1))] = c
        if len(found_years) >= 1:
            header_row = i
            year_col_map = found_years
            break

    if header_row is None or not year_col_map:
        return pd.DataFrame()

    # Find first data row: first row after header_row+2 where col 1 has a tariff name
    tariff_keywords = ["domestic", "government", "public", "business", "commercial",
                       "hotel", "industrial", "agriculture", "religious",
                       "total potable", "total non", "grand total", "acquired",
                       "livestock"]
    data_start = header_row + 2
    while data_start < len(df):
        v1 = str(df.iloc[data_start, 1]).strip().lower()
        if any(kw in v1 for kw in tariff_keywords):
            break
        data_start += 1

    # Parse data rows
    for i in range(data_start, len(df)):
        tariff = str(df.iloc[i, 1]).strip()
        if not tariff or tariff.lower() == "nan":
            continue
        # Skip source / notes rows
        if tariff.lower().startswith("source"):
            break

        for year_int, base_col in year_col_map.items():
            if year_int not in (year1, year2):
                continue
            try:
                subs_val   = pd.to_numeric(df.iloc[i, base_col],     errors="coerce")
                vol_val    = pd.to_numeric(df.iloc[i, base_col + 2], errors="coerce")
                amount_val = pd.to_numeric(df.iloc[i, base_col + 4], errors="coerce")
                records.append({
                    "year":               year_int,
                    "tariff_type":        tariff,
                    "subscribers_no":     float(subs_val)   if pd.notna(subs_val)   else np.nan,
                    "volume_m3_thousand": float(vol_val)    if pd.notna(vol_val)    else np.nan,
                    "amount_rs000":       float(amount_val) if pd.notna(amount_val) else np.nan,
                })
            except (IndexError, TypeError):
                continue

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Parse rainfall sheet (bonus)
# ---------------------------------------------------------------------------
def parse_rainfall(df: pd.DataFrame, year1: int, year2: int) -> pd.DataFrame:
    """Extract mean annual rainfall by region and year."""
    records = []
    # Find the row where "Year" appears in col 0 (annual total row)
    # Also look for rows with month abbreviations
    for i in range(len(df)):
        row0 = str(df.iloc[i, 0]).strip()
        if row0 == "Year":
            # This row contains annual totals; look at neighbouring columns for year values
            # The typical structure: col 0 = period label, col 1 = long-term mean, col 2 = year1_mean, col 4 = year2_mean
            region_label = ""
            # Walk back to find the last non-empty region label
            for j in range(i - 1, max(0, i - 5), -1):
                v = str(df.iloc[j, 0]).strip()
                if v and v.lower() not in ("nan", "", "north", "south", "east", "west",
                                            "island of mauritius", "period"):
                    region_label = v
                    break
            for year_offset, col_offset in [(year1, 2), (year2, 4)]:
                try:
                    val = pd.to_numeric(df.iloc[i, col_offset], errors="coerce")
                    if pd.notna(val):
                        records.append({
                            "year":    year_offset,
                            "month":   0,  # 0 = annual
                            "region":  region_label,
                            "rainfall_mm": float(val),
                        })
                except IndexError:
                    pass
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Process one workbook
# ---------------------------------------------------------------------------
def process_workbook(path: Path, min_year1: int = 9999) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (production_df, sales_df, rainfall_df) for one workbook."""
    xl = pd.ExcelFile(path)

    # Detect production sheet: 'wat prod', 'TAB15', or numbered 'Table 14/15'
    prod_sheet = find_sheet(xl, ["TAB15", "wat prod"])
    if prod_sheet is None:
        # Yr11 uses numbered names; Table 14 = production, Table 15 = sales
        t14 = find_sheet(xl, ["Table 14"])
        if t14:
            df_test = xl.parse(t14, header=None)
            title_test = str(df_test.iloc[0, 0]).lower()
            if "potable water production" in title_test or "monthly" in title_test:
                prod_sheet = t14
    sales_sheet = find_sheet(xl, ["TAB16", "Wat sale"])
    if sales_sheet is None:
        t15 = find_sheet(xl, ["Table 15"])
        if t15:
            df_test = xl.parse(t15, header=None)
            title_test = str(df_test.iloc[0, 0]).lower()
            if "water sales" in title_test or "tariff" in title_test:
                sales_sheet = t15
    rain_sheet = find_sheet(xl, ["TAB13", "rainfall"])

    if prod_sheet is None:
        print(f"    WARNING: no water production sheet found in {path.name}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Parse production
    df_prod_raw = xl.parse(prod_sheet, header=None)
    years = parse_years(str(df_prod_raw.iloc[0, 0]))
    if years is None:
        print(f"    WARNING: could not parse years from {path.name}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    year1, year2 = years

    # Only extract year2 (the current/latest year per workbook) to avoid
    # zone-name overlap when the same calendar year appears in two workbooks.
    # Exception: the first workbook (earliest year pair) also provides year1.
    extract_year1 = (year1 == min_year1)
    prod = parse_water_production(df_prod_raw,
                                  year1 if extract_year1 else year2,
                                  year2)

    # Parse sales (same year-selection logic)
    sales = pd.DataFrame()
    if sales_sheet:
        df_sales_raw = xl.parse(sales_sheet, header=None)
        try:
            sales = parse_water_sales(df_sales_raw,
                                      year1 if extract_year1 else year2,
                                      year2)
        except Exception as e:
            print(f"    WARNING: sales parse error in {path.name}: {e}")

    # Parse rainfall (same year-selection logic)
    rain = pd.DataFrame()
    if rain_sheet:
        df_rain_raw = xl.parse(rain_sheet, header=None)
        try:
            rain = parse_rainfall(df_rain_raw,
                                  year1 if extract_year1 else year2,
                                  year2)
        except Exception as e:
            print(f"    WARNING: rainfall parse error in {path.name}: {e}")

    return prod, sales, rain


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Extract water stats from Mauritius Statistics Energy+Water digests")
    parser.add_argument("--stats-dir", default=DEFAULT_STATS_DIR,
                        help="Directory containing Energy_Water_Yr*.xls files")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="Output directory for extracted CSVs")
    args = parser.parse_args()

    stats_dir = Path(args.stats_dir)
    out_dir   = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Find all workbooks (case-insensitive extension)
    workbooks = sorted(
        p for p in stats_dir.iterdir()
        if re.search(r"Energy_Water_Yr\d+\.(xls|XLS)$", p.name, re.IGNORECASE)
    )

    if not workbooks:
        print(f"No Energy_Water_Yr*.xls files found in {stats_dir}")
        return

    print(f"Found {len(workbooks)} workbooks in {stats_dir}\n")

    # Pre-scan to find the earliest year1 so we include that year too
    min_year1 = 9999
    for path in workbooks:
        try:
            xl = pd.ExcelFile(path)
            prod_sh = find_sheet(xl, ["TAB15", "wat prod", "Table 14"])
            if prod_sh:
                df_tmp = xl.parse(prod_sh, header=None)
                yrs = parse_years(str(df_tmp.iloc[0, 0]))
                if yrs and yrs[0] < min_year1:
                    min_year1 = yrs[0]
        except Exception:
            pass

    all_prod   = []
    all_sales  = []
    all_rain   = []

    for path in workbooks:
        print(f"  {path.name} ...", end=" ")
        try:
            prod, sales, rain = process_workbook(path, min_year1=min_year1)
            n_prod  = len(prod)
            n_sales = len(sales)
            n_rain  = len(rain)
            print(f"prod={n_prod} rows, sales={n_sales} rows, rain={n_rain} rows")
            if not prod.empty:
                all_prod.append(prod)
            if not sales.empty:
                all_sales.append(sales)
            if not rain.empty:
                all_rain.append(rain)
        except Exception as e:
            print(f"ERROR: {e}")

    def write_dedup(frames: list[pd.DataFrame], key_cols: list[str], out_path: Path, label: str):
        if not frames:
            print(f"\nNo {label} data extracted.")
            return
        combined = pd.concat(frames, ignore_index=True)
        # Deduplicate: keep last occurrence (latest workbook has most accurate data for shared years)
        combined = combined.drop_duplicates(subset=key_cols, keep="last")
        combined = combined.sort_values(key_cols).reset_index(drop=True)
        combined.to_csv(out_path, index=False)
        years = sorted(combined["year"].unique())
        print(f"\n{label}: {len(combined)} rows, years {years[0]}-{years[-1]} -> {out_path}")
        return combined

    prod_path  = out_dir / "mauritius_water_production.csv"
    sales_path = out_dir / "mauritius_water_sales.csv"
    rain_path  = out_dir / "mauritius_rainfall.csv"

    combined_prod = write_dedup(all_prod, ["year", "month", "supply_zone"],
                                prod_path, "Water production")

    write_dedup(all_sales, ["year", "tariff_type"], sales_path, "Water sales")
    write_dedup(all_rain,  ["year", "month", "region"], rain_path, "Rainfall")

    # Production summary table
    if combined_prod is not None and not combined_prod.empty:
        print("\nAnnual water production totals (Mm3):")
        annual = (
            combined_prod[combined_prod["supply_zone"].str.lower().str.contains("total", na=False)]
            .groupby("year")["total_Mm3"]
            .sum()
            .reset_index()
        )
        # Fallback: compute from all zones
        if annual.empty:
            annual = (
                combined_prod.groupby(["year", "supply_zone"])["total_Mm3"]
                .sum()
                .reset_index()
                .groupby("year")["total_Mm3"]
                .sum()
                .reset_index()
            )
        print(f"  {'Year':>6}  {'Total Mm3':>12}")
        for _, row in annual.iterrows():
            val = row["total_Mm3"]
            val_str = f"{val:.1f}" if pd.notna(val) else "N/A"
            print(f"  {int(row['year']):>6}  {val_str:>12}")


if __name__ == "__main__":
    main()
