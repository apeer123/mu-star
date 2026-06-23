"""
Extract GRDC daily discharge data → monthly flow statistics per station.

Source: Global Runoff Data Centre (GRDC), Station IDs 1689100-1689600
        Mauritius — Water Resources Unit, Ministry of Energy and Public Utilities
        Data owner: GRDC, Koblenz, Germany (https://www.bafg.de/GRDC)

Each GRDC file is a semicolon-delimited CSV with a '#'-prefixed header block
containing station metadata, followed by daily discharge values (m³/s).
Missing values are coded as -999.

Outputs (to <out_dir>):
  grdc_stations.csv         — station metadata (one row per station)
  grdc_monthly_flows.csv    — monthly statistics (all stations combined)
  <GRDC_NO>_monthly.csv     — per-station monthly file (mirrors catchment format)

Column schema (monthly):
  grdc_no, river, station_name, lat, lon, catchment_area_km2,
  year, month, mean_m3s, max_m3s, min_m3s, volume_Mm3, n_days_valid

Tom Russell's instruction: script the data extraction where possible.
Usage:
    python extract_grdc_flows.py
    python extract_grdc_flows.py --grdc-dir PATH --out-dir PATH
"""

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEFAULT_GRDC_DIR = (
    "."
)
DEFAULT_OUT_DIR = (
    "."
)


# ---------------------------------------------------------------------------
# Parse GRDC file header
# ---------------------------------------------------------------------------
def _parse_grdc_header(lines: list[str]) -> dict:
    """Extract metadata fields from the '#' comment lines at the top of a GRDC file."""
    meta = {}
    patterns = {
        "grdc_no":           r"GRDC-No\.\s*:\s*(\d+)",
        "river":             r"River\s*:\s*(.+)",
        "station_name":      r"Station\s*:\s*(.+)",
        "country":           r"Country\s*:\s*(.+)",
        "lat":               r"Latitude \(DD\)\s*:\s*([+-]?\d+\.\d+)",
        "lon":               r"Longitude \(DD\)\s*:\s*([+-]?\d+\.\d+)",
        "catchment_area_km2": r"Catchment area \(km",
        "altitude_m":        r"Altitude \(m ASL\)\s*:\s*([+-]?\d+\.?\d*)",
        "time_series":       r"Time series\s*:\s*(.+)",
        "n_years":           r"No\. of years\s*:\s*(\d+)",
    }
    for line in lines:
        line = line.lstrip("#").strip()
        m = re.search(r"GRDC-No\.\s*:\s*(\d+)", line)
        if m:
            meta["grdc_no"] = int(m.group(1))
        m = re.search(r"River\s*:\s*(.+)", line)
        if m and "river" not in meta:
            meta["river"] = m.group(1).strip()
        m = re.search(r"Station\s*:\s*(.+)", line)
        if m and "station_name" not in meta:
            meta["station_name"] = m.group(1).strip()
        m = re.search(r"Country\s*:\s*(.+)", line)
        if m and "country" not in meta:
            meta["country"] = m.group(1).strip()
        m = re.search(r"Latitude \(DD\)\s*:\s*([+-]?\d+\.\d+)", line)
        if m:
            meta["lat"] = float(m.group(1))
        m = re.search(r"Longitude \(DD\)\s*:\s*([+-]?\d+\.\d+)", line)
        if m:
            meta["lon"] = float(m.group(1))
        m = re.search(r"Catchment area \(km.*?\)\s*:\s*([+-]?\d+\.?\d*)", line)
        if m:
            meta["catchment_area_km2"] = float(m.group(1))
        m = re.search(r"Altitude \(m ASL\)\s*:\s*([+-]?\d+\.?\d*)", line)
        if m:
            meta["altitude_m"] = float(m.group(1))
        m = re.search(r"Time series\s*:\s*(.+)", line)
        if m:
            meta["time_series"] = m.group(1).strip()
        m = re.search(r"No\. of years\s*:\s*(\d+)", line)
        if m:
            meta["n_years"] = int(m.group(1))
    return meta


# ---------------------------------------------------------------------------
# Read one GRDC file → daily DataFrame
# ---------------------------------------------------------------------------
def read_grdc_daily(path: Path) -> tuple[dict, pd.DataFrame]:
    """
    Returns (metadata_dict, daily_df).
    daily_df has columns: date (datetime), q_m3s (float, NaN for missing).
    """
    header_lines = []
    data_start = 0
    with open(path, "r", encoding="latin-1") as f:
        for i, line in enumerate(f):
            if line.startswith("#"):
                header_lines.append(line)
                data_start = i + 1
            else:
                break  # first non-comment line = column header row

    meta = _parse_grdc_header(header_lines)

    # Read the data portion (skip the header block + the column-header row)
    # Column header row looks like: "YYYY-MM-DD;hh:mm; Value"
    df = pd.read_csv(
        path,
        skiprows=data_start,
        sep=";",
        names=["date_str", "time_str", "value"],
        skip_blank_lines=True,
        dtype=str,
        encoding="latin-1",
    )

    # Strip whitespace and parse
    df["date_str"] = df["date_str"].str.strip()
    df["value"] = pd.to_numeric(df["value"].str.strip(), errors="coerce")

    # Drop the header row if it was read as data
    df = df[df["date_str"].str.match(r"\d{4}-\d{2}-\d{2}")]

    df["date"] = pd.to_datetime(df["date_str"], format="%Y-%m-%d", errors="coerce")
    df = df.dropna(subset=["date"])

    # Replace GRDC missing-value code with NaN
    df.loc[df["value"] <= -999, "value"] = np.nan
    df = df.rename(columns={"value": "q_m3s"})[["date", "q_m3s"]].copy()
    df = df.sort_values("date").reset_index(drop=True)

    return meta, df


# ---------------------------------------------------------------------------
# Aggregate daily → monthly statistics
# ---------------------------------------------------------------------------
def daily_to_monthly(meta: dict, daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily discharge to monthly mean/max/min/volume."""
    if daily.empty:
        return pd.DataFrame()

    daily = daily.copy()
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month

    def agg_month(grp):
        valid = grp["q_m3s"].dropna()
        if valid.empty:
            return pd.Series({
                "mean_m3s": np.nan, "max_m3s": np.nan,
                "min_m3s": np.nan, "volume_Mm3": np.nan, "n_days_valid": 0,
            })
        # Approximate monthly volume: sum(Q_day * 86400 s) / 1e6 Mm³
        volume = float((valid * 86400).sum() / 1e6)
        return pd.Series({
            "mean_m3s":    round(float(valid.mean()), 6),
            "max_m3s":     round(float(valid.max()),  6),
            "min_m3s":     round(float(valid.min()),  6),
            "volume_Mm3":  round(volume, 6),
            "n_days_valid": int(valid.count()),
        })

    monthly = daily.groupby(["year", "month"]).apply(agg_month).reset_index()
    monthly.insert(0, "grdc_no",           meta.get("grdc_no", ""))
    monthly.insert(1, "river",             meta.get("river", ""))
    monthly.insert(2, "station_name",      meta.get("station_name", ""))
    monthly.insert(3, "lat",               meta.get("lat", np.nan))
    monthly.insert(4, "lon",               meta.get("lon", np.nan))
    monthly.insert(5, "catchment_area_km2", meta.get("catchment_area_km2", np.nan))
    return monthly


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Extract GRDC flows to monthly CSVs")
    parser.add_argument("--grdc-dir", default=DEFAULT_GRDC_DIR,
                        help="Directory containing GRDC *_Q_Day.csv files")
    parser.add_argument("--out-dir",  default=DEFAULT_OUT_DIR,
                        help="Output directory for extracted CSVs")
    args = parser.parse_args()

    grdc_dir = Path(args.grdc_dir)
    out_dir  = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(grdc_dir.glob("*_Q_Day.csv"))
    if not csv_files:
        print(f"No *_Q_Day.csv files found in {grdc_dir}")
        return

    print(f"Found {len(csv_files)} GRDC station files in {grdc_dir}")

    all_meta    = []
    all_monthly = []

    for path in csv_files:
        print(f"  Processing {path.name} ...", end=" ")
        try:
            meta, daily = read_grdc_daily(path)
            monthly = daily_to_monthly(meta, daily)

            # Per-station output
            grdc_no = meta.get("grdc_no", path.stem.split("_")[0])
            station_csv = out_dir / f"{grdc_no}_monthly.csv"
            monthly.to_csv(station_csv, index=False)

            n_rows = len(monthly)
            n_valid = (monthly["n_days_valid"] > 20).sum()
            print(f"{n_rows} monthly rows ({n_valid} with >20 valid days)")

            all_monthly.append(monthly)
            all_meta.append({
                "grdc_no":           meta.get("grdc_no"),
                "river":             meta.get("river"),
                "station_name":      meta.get("station_name"),
                "country":           meta.get("country"),
                "lat":               meta.get("lat"),
                "lon":               meta.get("lon"),
                "catchment_area_km2": meta.get("catchment_area_km2"),
                "altitude_m":        meta.get("altitude_m"),
                "time_series":       meta.get("time_series"),
                "n_years":           meta.get("n_years"),
            })
        except Exception as e:
            print(f"ERROR: {e}")

    if not all_monthly:
        print("No data extracted.")
        return

    # Combined output
    combined = pd.concat(all_monthly, ignore_index=True)
    combined_path = out_dir / "grdc_monthly_flows.csv"
    combined.to_csv(combined_path, index=False)
    print(f"\nCombined monthly flows: {len(combined)} rows -> {combined_path}")

    meta_df = pd.DataFrame(all_meta)
    meta_path = out_dir / "grdc_stations.csv"
    meta_df.to_csv(meta_path, index=False)
    print(f"Station metadata:       {len(meta_df)} stations -> {meta_path}")

    # Summary
    print("\nStation summary:")
    print(f"  {'GRDC-No':>10}  {'River':<35} {'Station':<30} {'Rows':>6} {'Years':>6}")
    for row in all_meta:
        n = len([m for m in all_monthly if str(m['grdc_no'].iloc[0]) == str(row['grdc_no'])])
        grdc_no = row['grdc_no']
        sub = combined[combined['grdc_no'] == grdc_no]
        years = sub['year'].nunique() if not sub.empty else 0
        rows  = len(sub)
        print(f"  {grdc_no:>10}  {str(row.get('river','')):<35} {str(row.get('station_name','')):<30} {rows:>6} {years:>6}")


if __name__ == "__main__":
    main()
