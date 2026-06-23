"""
Assign river names to the UdM river shapefile using OSM rivers as a reference.

Strategy:
  1. Load the UdM rivers shapefile (geometry present, no/blank names).
  2. Load the OSM rivers shapefile (geometry + name attribute).
  3. For each UdM segment, find the OSM segment with the highest spatial overlap
     (measured by length of intersection after buffering the UdM line by a small
     tolerance). Assign the OSM name.
  4. For any remaining unnamed UdM segments, attempt a nearest-neighbour name
     assignment up to a maximum snap distance.
  5. Write the enriched shapefile.

Inputs (auto-detected from the local Downloads folder):
  UdM rivers:  ...Natural/Rivers/RiversStreams*.shp
  OSM rivers:  ...Natural/Hydrology/OSM rivers.../*.shp   (select the line layer)

Usage:
    python assign_river_names.py
    python assign_river_names.py --udm-rivers PATH --osm-rivers PATH --out PATH

Tom's instruction: script the data extraction where possible.
"""

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import nearest_points

# ---------------------------------------------------------------------------
# Known river names from the Hydrology Data Book — fallback lookup by
# catchment letter code.  Source: Chapter 3 station descriptions.
# ---------------------------------------------------------------------------
CATCHMENT_RIVER_NAMES = {
    "A": "Rivière du Rempart",
    "B": "Rivière du Tombeau",
    "D": "Rivière Terre Rouge",
    "E": "Rivière des Anguilles",       # East / South area rivers
    "G": "Rivière la Chaux",
    "H": "Rivière Creuse",
    "J": "Rivière la Chaux / Rivière Cascade Vacoas",
    "L": "Rivière St. Martin",
    "M": "Rivière Moka",
    "N": "Rivière Noire",
    "P": "Petite Rivière",
    "Q": "Rivière Citron",
    "R": "Rivière Savanne",
    "S": "Rivière Souillac",
    "T": "Rivière du Poste",
    "U": "Rivière Bois Chéri",
    "W": "Grande Rivière Sud Est",
    "Y": "Rivière Mapou",
    "Z": "Rodrigues River",
}


def find_shapefile(search_dir: Path, keyword: str) -> Path | None:
    """Return the first .shp file whose path contains keyword (case-insensitive)."""
    for p in sorted(search_dir.rglob("*.shp")):
        if keyword.lower() in p.parts[-2].lower() or keyword.lower() in p.stem.lower():
            return p
    return None


def load_rivers(path: Path, label: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    print(f"  {label}: {len(gdf)} features, CRS={gdf.crs}, cols={list(gdf.columns)}")
    # Keep only LINE geometries (drop points/polygons if mixed)
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    return gdf


def detect_name_column(gdf: gpd.GeoDataFrame) -> str | None:
    """Heuristically find the column most likely to contain river names."""
    candidates = [c for c in gdf.columns if c.lower() in ("name", "name_", "rivname", "river", "label")]
    if candidates:
        return candidates[0]
    # Try any column with mostly non-null string values
    for col in gdf.select_dtypes(include="object").columns:
        if gdf[col].notna().mean() > 0.5:
            return col
    return None


def assign_names_by_overlap(
    udm: gpd.GeoDataFrame,
    osm: gpd.GeoDataFrame,
    osm_name_col: str,
    buffer_m: float = 30.0,
) -> gpd.GeoDataFrame:
    """
    For each UdM segment, find the OSM segment whose buffered geometry
    has the largest intersection length with the UdM segment.
    """
    udm = udm.copy()
    udm["assigned_name"] = None
    udm["name_source"] = None

    # CRS alignment is done in main() before calling this function

    # Build spatial index on OSM for fast candidate lookup
    osm_sindex = osm.sindex

    for idx, row in udm.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        # Buffer the UdM segment to catch nearby OSM lines
        buffered = geom.buffer(buffer_m)
        candidate_indices = list(osm_sindex.intersection(buffered.bounds))
        if not candidate_indices:
            continue

        candidates = osm.iloc[candidate_indices]
        best_name = None
        best_overlap = 0.0

        for _, osm_row in candidates.iterrows():
            try:
                intersection = buffered.intersection(osm_row.geometry)
                overlap = intersection.length
            except Exception:
                continue
            if overlap > best_overlap:
                best_overlap = overlap
                best_name = osm_row.get(osm_name_col)

        if best_name and str(best_name).strip() not in ("", "nan", "None"):
            udm.at[idx, "assigned_name"] = str(best_name).strip()
            udm.at[idx, "name_source"] = "OSM"

    named = udm["assigned_name"].notna().sum()
    print(f"  OSM overlap match: {named}/{len(udm)} segments named")
    return udm


def assign_names_by_nearest(
    udm: gpd.GeoDataFrame,
    osm: gpd.GeoDataFrame,
    osm_name_col: str,
    max_dist_m: float = 100.0,
) -> gpd.GeoDataFrame:
    """Nearest-neighbour fallback for still-unnamed UdM segments."""
    unnamed_mask = udm["assigned_name"].isna()
    unnamed = udm[unnamed_mask].copy()
    print(f"  Nearest-neighbour fallback for {unnamed_mask.sum()} unnamed segments (max {max_dist_m} m) ...")

    for idx, row in unnamed.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pt = geom.centroid
        nearest_osm_idx = osm.geometry.distance(pt).idxmin()
        dist = osm.geometry[nearest_osm_idx].distance(pt)
        if dist <= max_dist_m:
            name = osm.at[nearest_osm_idx, osm_name_col]
            if name and str(name).strip() not in ("", "nan", "None"):
                udm.at[idx, "assigned_name"] = str(name).strip()
                udm.at[idx, "name_source"] = f"OSM_nearest_{dist:.0f}m"

    named_after = udm["assigned_name"].notna().sum()
    print(f"  After nearest-neighbour: {named_after}/{len(udm)} segments named")
    return udm


def main():
    base = Path(Path("../Incoming Data").resolve())

    parser = argparse.ArgumentParser(description="Assign river names to UdM shapefile from OSM")
    parser.add_argument("--udm-rivers", default=None, help="Path to UdM rivers shapefile")
    parser.add_argument("--osm-rivers", default=None, help="Path to OSM rivers (line) shapefile")
    parser.add_argument(
        "--out",
        default=str(base / "Natural" / "Rivers" / "RiversStreams_named.shp"),
        help="Output shapefile path",
    )
    parser.add_argument("--buffer", type=float, default=30.0, help="Buffer distance (m) for overlap match")
    parser.add_argument("--max-dist", type=float, default=100.0, help="Max snap distance (m) for nearest-neighbour")
    args = parser.parse_args()

    # --- Auto-detect input files ---
    if args.udm_rivers:
        udm_path = Path(args.udm_rivers)
    else:
        udm_path = find_shapefile(base / "Natural" / "Rivers", "River")
        if udm_path is None:
            udm_path = next((base / "Natural" / "Rivers").rglob("*.shp"), None)
    if udm_path is None or not udm_path.exists():
        print(f"ERROR: UdM rivers shapefile not found. Use --udm-rivers to specify.")
        return

    if args.osm_rivers:
        osm_path = Path(args.osm_rivers)
    else:
        # OSM rivers directory has two shapefiles — pick the one with 'line' or larger count
        osm_dir = base / "Natural" / "Hydrology"
        osm_candidates = list(osm_dir.rglob("*.shp"))
        osm_candidates = [p for p in osm_candidates if "osm" in p.parts[-2].lower()]
        if not osm_candidates:
            osm_candidates = list(osm_dir.rglob("*.shp"))
        # Prefer the file whose name contains 'line' or 'river'
        preferred = [p for p in osm_candidates if "line" in p.stem.lower() or "river" in p.stem.lower()]
        osm_path = preferred[0] if preferred else osm_candidates[0]
    if osm_path is None or not osm_path.exists():
        print(f"ERROR: OSM rivers shapefile not found. Use --osm-rivers to specify.")
        return

    print(f"UdM rivers: {udm_path}")
    print(f"OSM rivers: {osm_path}")

    udm = load_rivers(udm_path, "UdM rivers")
    osm = load_rivers(osm_path, "OSM rivers")

    osm_name_col = detect_name_column(osm)
    if osm_name_col is None:
        print("ERROR: Cannot detect name column in OSM shapefile.")
        return
    print(f"  OSM name column detected: '{osm_name_col}'")

    # Reproject OSM to match UdM's CRS so all spatial ops are in the same system
    if udm.crs != osm.crs:
        osm = osm.to_crs(udm.crs)
        print(f"  OSM reprojected to UdM CRS: {udm.crs.to_string()[:60]}")

    # --- Step 1: Overlap-based name assignment ---
    udm = assign_names_by_overlap(udm, osm, osm_name_col, buffer_m=args.buffer)

    # --- Step 2: Nearest-neighbour fallback ---
    udm = assign_names_by_nearest(udm, osm, osm_name_col, max_dist_m=args.max_dist)

    # --- Step 3: Summary and write ---
    named_total = udm["assigned_name"].notna().sum()
    print(f"\nFinal: {named_total}/{len(udm)} segments have names ({named_total/len(udm)*100:.1f}%)")

    unnamed_count = len(udm) - named_total
    if unnamed_count > 0:
        print(f"  {unnamed_count} segments remain unnamed - check geometry alignment with OSM.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    udm.to_file(out_path)
    print(f"  Saved -> {out_path}")

    # Also save a summary CSV
    summary_csv = out_path.with_suffix(".csv")
    udm[["assigned_name", "name_source"]].to_csv(summary_csv, index=True)
    print(f"  Summary CSV -> {summary_csv}")


if __name__ == "__main__":
    main()
