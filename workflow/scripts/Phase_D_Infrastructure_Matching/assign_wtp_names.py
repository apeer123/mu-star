"""
Assign names and enrich metadata for Water Treatment Plant (WTP) and
Wastewater Treatment Plant (WWTP) shapefiles.

The current shapefiles have placeholder names ("PDM" for WTPs, "MJ" for WWTPs).
This script:
  1. Loads WTP and WWTP shapefiles.
  2. Cross-references plant locations against a known reference table
     (derived from CWA website, NAO 2025 report, and Hydrology Data Book).
  3. Assigns names by nearest-point matching to the reference coordinates.
  4. Adds available metadata: served_area, capacity_m3day, source_type,
     supply_zone (WSZ), data_source.
  5. Saves enriched shapefiles and a combined summary CSV.

Usage:
    python assign_wtp_names.py
    python assign_wtp_names.py --wtp PATH --wwtp PATH --out-dir PATH

Tom's instruction: script the data extraction where possible.
"""

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Point

# ---------------------------------------------------------------------------
# Reference tables — compiled from:
#   - CWA website (7 WTPs, capacity, WSZ)
#   - NAO December 2025 report (production volumes, WSZ)
#   - Hydrology Data Book (abstraction point locations)
#   - Statistics Mauritius Digest 2024
#
# Coordinates are in EPSG:4326 (WGS84 lon/lat).
# ---------------------------------------------------------------------------

WTP_REFERENCE = [
    # name, lon, lat, capacity_m3day, supply_zone, source_type, notes
    ("La Nicolière WTP",      57.5264, -20.0968, 120_000, "North",      "surface", "Abstraction: La Nicolière reservoir"),
    ("Pamplemousses WTP",     57.5742, -20.1167,  70_000, "North",      "surface", "Abstraction: Rivière du Tombeau"),
    ("Piton du Milieu WTP",   57.6497, -20.2367,  80_000, "East",       "surface", "Abstraction: Piton du Milieu reservoir"),
    ("Camp Levieux WTP",      57.5014, -20.3811,  60_000, "South",      "surface", "Abstraction: Mare Longue / La Ferme"),
    ("St. Martin WTP",        57.5042, -20.2789, 100_000, "Upper MAV",  "surface", "Abstraction: Midlands reservoir"),
    ("Mare aux Vacoas WTP",   57.4939, -20.2739,  55_000, "Lower MAV",  "surface", "Abstraction: Mare aux Vacoas"),
    ("Bagatelle WTP",         57.4811, -20.2433,  24_000, "Port Louis", "surface", "Abstraction: Bagatelle reservoir (2017)"),
]

WWTP_REFERENCE = [
    # name, lon, lat, capacity_m3day, service_area, notes
    ("Montagne Jacquot WWTP",   57.5064, -20.2689,  35_000, "Plaines Wilhems", "CWA / WMA"),
    ("Riche Terre WWTP",        57.5522, -20.1608,  18_000, "Port Louis North","CWA / WMA"),
    ("Baie du Tombeau WWTP",    57.5303, -20.1333,  12_000, "Port Louis",      "CWA / WMA"),
    ("Pointe aux Sables WWTP",  57.4397, -20.2111,  10_000, "Port Louis West", "CWA / WMA"),
    ("St. Martin WWTP",         57.4994, -20.3006,  20_000, "Quatre Bornes",   "CWA / WMA"),
    ("Plaine Magnien WWTP",     57.7278, -20.4228,  15_000, "South East",      "CWA / WMA"),
    ("Bambous WWTP",            57.4017, -20.2950,   8_000, "West",            "CWA / WMA"),
    ("Rivière des Anguilles WWTP", 57.5511, -20.4728, 12_000, "South",        "CWA / WMA"),
    ("Poste de Flacq WWTP",     57.7117, -20.2003,   9_000, "East",           "CWA / WMA"),
    ("Triolet WWTP",            57.5494, -20.0611,   7_000, "North",          "CWA / WMA"),
]


def reference_to_gdf(ref_list: list, columns: list) -> gpd.GeoDataFrame:
    """Convert a reference list to a GeoDataFrame in EPSG:4326."""
    df = pd.DataFrame(ref_list, columns=columns)
    geometry = [Point(row["lon"], row["lat"]) for _, row in df.iterrows()]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    return gdf.drop(columns=["lon", "lat"])


def assign_names_by_nearest(
    plants: gpd.GeoDataFrame,
    reference: gpd.GeoDataFrame,
    max_dist_m: float = 20000.0,
    ref_name_col: str = "name",
) -> gpd.GeoDataFrame:
    """
    Match each plant point to the best reference point using the Hungarian
    algorithm (globally optimal 1-to-1 assignment), then filter out pairs
    whose distance exceeds max_dist_m.
    """
    # Project to Mauritius projected CRS for accurate distance calculation
    target_crs = "EPSG:3337"
    plants_proj = plants.to_crs(target_crs).copy()
    ref_proj = reference.to_crs(target_crs).copy()

    ref_cols = [c for c in reference.columns if c != "geometry"]
    for col in ref_cols:
        plants_proj[col] = None

    plants_proj["match_dist_m"] = None
    plants_proj["match_status"] = "unmatched"

    # Build full distance matrix (n_plants x n_refs)
    n_plants = len(plants_proj)
    n_refs = len(ref_proj)
    dist_matrix = np.full((n_plants, n_refs), fill_value=1e9)

    plant_geoms = list(plants_proj.geometry)
    ref_geoms = list(ref_proj.geometry)

    for i, pg in enumerate(plant_geoms):
        if pg is None or pg.is_empty:
            continue
        for j, rg in enumerate(ref_geoms):
            if rg is None or rg.is_empty:
                continue
            dist_matrix[i, j] = pg.distance(rg)

    # Hungarian algorithm for optimal 1:1 assignment
    row_ind, col_ind = linear_sum_assignment(dist_matrix)

    plant_idx_list = list(plants_proj.index)
    ref_idx_list = list(ref_proj.index)

    for i, j in zip(row_ind, col_ind):
        dist = dist_matrix[i, j]
        pidx = plant_idx_list[i]
        ridx = ref_idx_list[j]
        if dist <= max_dist_m:
            for col in ref_cols:
                plants_proj.at[pidx, col] = ref_proj.at[ridx, col]
            plants_proj.at[pidx, "match_dist_m"] = round(float(dist), 1)
            plants_proj.at[pidx, "match_status"] = "matched"

    matched = (plants_proj["match_status"] == "matched").sum()
    print(f"  Matched {matched}/{n_plants} plants (Hungarian algorithm, max {max_dist_m/1000:.0f} km)")

    # Convert back to original CRS
    result = plants_proj.to_crs(plants.crs)
    return result


def find_shapefile_in(directory: Path, keyword: str) -> Path | None:
    """Return first .shp file under directory whose path contains keyword."""
    for p in sorted(directory.rglob("*.shp")):
        if keyword.lower() in str(p).lower():
            return p
    return None


def main():
    base = Path(".")

    parser = argparse.ArgumentParser(description="Assign names and metadata to WTP/WWTP shapefiles")
    parser.add_argument("--wtp",  default=None, help="Path to WTP shapefile")
    parser.add_argument("--wwtp", default=None, help="Path to WWTP shapefile")
    parser.add_argument("--out-dir", default=str(base), help="Output directory")
    parser.add_argument("--max-dist", type=float, default=30000.0,
                        help="Max matching distance in metres (default 30000 m; use large value for imprecise reference coords)")
    args = parser.parse_args()

    # --- Locate shapefiles ---
    # Search for "Water Treatment" but exclude "Wastewater" matches
    if args.wtp:
        wtp_path = Path(args.wtp)
    else:
        wtp_path = None
        for p in sorted(base.rglob("*.shp")):
            pstr = str(p).lower()
            if "water treatment" in pstr and "wastewater" not in pstr:
                wtp_path = p
                break
    wwtp_path = Path(args.wwtp) if args.wwtp else find_shapefile_in(base, "Wastewater")

    if wtp_path is None or not wtp_path.exists():
        print(f"ERROR: WTP shapefile not found under {base}. Use --wtp to specify.")
        return
    if wwtp_path is None or not wwtp_path.exists():
        print(f"ERROR: WWTP shapefile not found under {base}. Use --wwtp to specify.")
        return

    print(f"WTP  shapefile: {wtp_path}")
    print(f"WWTP shapefile: {wwtp_path}")

    # --- Build reference GeoDataFrames ---
    wtp_ref = reference_to_gdf(
        WTP_REFERENCE,
        ["name", "lon", "lat", "capacity_m3day", "supply_zone", "source_type", "notes"],
    )
    wwtp_ref = reference_to_gdf(
        WWTP_REFERENCE,
        ["name", "lon", "lat", "capacity_m3day", "service_area", "notes"],
    )

    # --- Load plant shapefiles ---
    wtp  = gpd.read_file(wtp_path)
    wwtp = gpd.read_file(wwtp_path)
    print(f"  WTP:  {len(wtp)} features, CRS={wtp.crs}, cols={list(wtp.columns)}")
    print(f"  WWTP: {len(wwtp)} features, CRS={wwtp.crs}, cols={list(wwtp.columns)}")

    # --- Assign names ---
    wtp_named  = assign_names_by_nearest(wtp,  wtp_ref,  max_dist_m=args.max_dist)
    wwtp_named = assign_names_by_nearest(wwtp, wwtp_ref, max_dist_m=args.max_dist)

    # --- Report ---
    wtp_ok  = (wtp_named["match_status"]  == "matched").sum()
    wwtp_ok = (wwtp_named["match_status"] == "matched").sum()
    print(f"\nWTP  matched: {wtp_ok}/{len(wtp_named)}")
    print(f"WWTP matched: {wwtp_ok}/{len(wwtp_named)}")

    unmatched_wtp  = wtp_named[wtp_named["match_status"] == "unmatched"]
    unmatched_wwtp = wwtp_named[wwtp_named["match_status"] == "unmatched"]
    if not unmatched_wtp.empty:
        print(f"  Unmatched WTPs (check coordinates manually): {len(unmatched_wtp)} plants")
    if not unmatched_wwtp.empty:
        print(f"  Unmatched WWTPs: {len(unmatched_wwtp)} plants")

    # --- Save outputs ---
    out_dir = Path(args.out_dir)

    wtp_out  = wtp_path.parent  / "WaterTreatment_named.shp"
    wwtp_out = wwtp_path.parent / "WWTreatmentP_named.shp"

    wtp_named.to_file(wtp_out)
    wwtp_named.to_file(wwtp_out)
    print(f"Saved WTP  -> {wtp_out}")
    print(f"Saved WWTP -> {wwtp_out}")

    # Combined summary CSV
    wtp_csv  = wtp_out.with_suffix(".csv")
    wwtp_csv = wwtp_out.with_suffix(".csv")
    wtp_named.drop(columns="geometry").to_csv(wtp_csv, index=False)
    wwtp_named.drop(columns="geometry").to_csv(wwtp_csv, index=False)
    print(f"Summary CSV (WTP)  -> {wtp_csv}")
    print(f"Summary CSV (WWTP) -> {wwtp_csv}")

    print("\nNOTE: Reference coordinates are approximate (derived from public sources).")
    print("match_dist_m shows the matching distance. Distances >5000 m need manual")
    print("verification against CWA records or satellite imagery.")
    print("For 7 WTPs on a 60x45 km island, all points should match within 20 km.")


if __name__ == "__main__":
    main()
