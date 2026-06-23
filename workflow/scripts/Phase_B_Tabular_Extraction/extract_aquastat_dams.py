"""
Extract Aquastat dam/reservoir inventory for Mauritius.

Source: FAO Aquastat Global Dam and Reservoir Database
        File: MUS-dams_eng.xlsx (provided by Silvia Colombo, Oxford / MSTAR project)
        URL:  https://www.fao.org/aquastat/en/databases/dams

Cleans the raw Excel into a flat CSV with consistent column names, numeric
types, and boolean purpose flags.

Outputs (to same directory as input .xlsx, or --out-dir if supplied):
  mauritius_dams.csv
  mauritius_dams.geojson   (only for dams with lat/lon)

Tom Russell's instruction: script the data extraction where possible.
Usage:
    python extract_aquastat_dams.py
    python extract_aquastat_dams.py --xlsx PATH --out-dir PATH
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEFAULT_XLSX = (
    "."
    r"\MUS-dams_eng.xlsx"
)
DEFAULT_OUT_DIR = None  # if None, written beside the input .xlsx


# ---------------------------------------------------------------------------
# Column mapping: raw Excel col positions → clean names
# The 'Dams' sheet row 1 is the header (0-indexed)
# ---------------------------------------------------------------------------
COL_MAP = {
    "Country":                          "country",
    "Name of dam":                      "dam_name",
    "Alternate dam name":               "alt_name",
    "ISO alpha- 3":                     "iso3",
    "Administrative\nUnit":             "admin_unit",
    "Nearest city":                     "nearest_city",
    "River":                            "river",
    "Major basin":                      "major_basin",
    "Sub-basin":                        "sub_basin",
    "Completed /operational since":     "year_operational",
    "Dam height (m)":                   "height_m",
    "Reservoir capacity (million m3)":  "capacity_Mm3",
    "Reservoir area (km2)":             "area_km2",
    "Sedimen-tation \n(latest known) \n(%)": "sedimentation_pct",
    "Irrigation":                       "purpose_irrigation",
    "Water supply":                     "purpose_water_supply",
    "Flood control":                    "purpose_flood_control",
    "Hydroelectricity (MW)":            "purpose_hydropower",
    "Navigation":                       "purpose_navigation",
    "Recreation":                       "purpose_recreation",
    "Pollution control":                "purpose_pollution_control",
    "Livestock rearing":                "purpose_livestock",
    "Other":                            "purpose_other",
    "Decimal degree latitude":          "lat",
    "Decimal degree longitude":         "lon",
    "National reference(s)":            "ref_national",
    "Other reference(s)":               "ref_other",
    "Comments":                         "comments",
}

PURPOSE_COLS = [
    "purpose_irrigation", "purpose_water_supply", "purpose_flood_control",
    "purpose_hydropower", "purpose_navigation", "purpose_recreation",
    "purpose_pollution_control", "purpose_livestock", "purpose_other",
]


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------
def extract_dams(xlsx_path: Path) -> pd.DataFrame:
    """Read the 'Dams' sheet and return a clean DataFrame."""
    df = pd.read_excel(xlsx_path, sheet_name="Dams", header=1, engine="openpyxl")

    # Rename columns using the map (ignore columns not in map)
    # Strip whitespace from column names first (Excel often has trailing spaces)
    df.columns = [str(c).strip() if not isinstance(c, int) else c for c in df.columns]
    rename = {k: v for k, v in COL_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Drop rows where dam_name is missing (truly empty rows)
    if "dam_name" in df.columns:
        df = df[df["dam_name"].notna()].copy()
    else:
        # Fall back to raw positional read
        print("  WARNING: 'Name of dam' column not found; using positional read")
        df = pd.read_excel(xlsx_path, sheet_name="Dams", header=None,
                           engine="openpyxl")
        df.columns = range(len(df.columns))

    # --- Numeric columns ---
    for col in ["year_operational", "height_m", "capacity_Mm3", "area_km2",
                "sedimentation_pct", "lat", "lon"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # year_operational: coerce to int where not NaN
    if "year_operational" in df.columns:
        df["year_operational"] = df["year_operational"].astype("Int64")

    # --- Purpose flags: 'x' or 'X' → True, everything else → False ---
    for col in PURPOSE_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.lower() == "x"

    # --- Keep only columns present ---
    keep = [c for c in COL_MAP.values() if c in df.columns]
    df = df[keep].reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Write GeoJSON (dams with valid lat/lon)
# ---------------------------------------------------------------------------
def to_geojson(df: pd.DataFrame, out_path: Path) -> None:
    spatial = df.dropna(subset=["lat", "lon"])
    features = []
    for _, row in spatial.iterrows():
        props = {}
        for k, v in row.items():
            if k in ("lat", "lon"):
                continue
            # Convert pandas NA / bool to JSON-safe types
            if pd.isna(v):
                props[k] = None
            elif isinstance(v, (np.bool_, bool)):
                props[k] = bool(v)
            elif isinstance(v, (np.integer,)):
                props[k] = int(v)
            elif isinstance(v, (np.floating,)):
                props[k] = float(v)
            else:
                props[k] = str(v) if not isinstance(v, str) else v
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row["lon"]), float(row["lat"])],
            },
            "properties": props,
        })
    fc = {"type": "FeatureCollection", "features": features}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Extract Aquastat dam inventory for Mauritius")
    parser.add_argument("--xlsx",    default=DEFAULT_XLSX,
                        help="Path to MUS-dams_eng.xlsx")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="Output directory (default: same as input .xlsx)")
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f"ERROR: file not found: {xlsx_path}")
        return

    out_dir = Path(args.out_dir) if args.out_dir else xlsx_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {xlsx_path.name} ...")
    df = extract_dams(xlsx_path)
    print(f"  Extracted {len(df)} dams/reservoirs")

    # Print summary
    print("\nDam inventory:")
    print(f"  {'Dam name':<35} {'River':<30} {'Year':>6} {'Cap Mm3':>8} {'Height m':>9}")
    for _, row in df.iterrows():
        yr  = int(row["year_operational"]) if pd.notna(row.get("year_operational")) else ""
        cap = f"{row['capacity_Mm3']:.2f}" if pd.notna(row.get("capacity_Mm3")) else ""
        ht  = f"{row['height_m']:.0f}" if pd.notna(row.get("height_m")) else ""
        print(f"  {str(row.get('dam_name','')):<35} {str(row.get('river','')):<30} {str(yr):>6} {cap:>8} {ht:>9}")

    # Purpose overview
    print("\nPurpose flags:")
    for col in PURPOSE_COLS:
        if col in df.columns:
            count = int(df[col].sum())
            label = col.replace("purpose_", "")
            print(f"  {label:<25} {count} dam(s)")

    # CSV output
    csv_path = out_dir / "mauritius_dams.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nCSV  -> {csv_path}")

    # GeoJSON output
    n_spatial = df.dropna(subset=["lat", "lon"]).shape[0]
    if n_spatial > 0:
        geojson_path = out_dir / "mauritius_dams.geojson"
        to_geojson(df, geojson_path)
        print(f"GeoJSON ({n_spatial} dams with coordinates) -> {geojson_path}")
    else:
        print("No dams with valid lat/lon - GeoJSON not created.")


if __name__ == "__main__":
    main()
