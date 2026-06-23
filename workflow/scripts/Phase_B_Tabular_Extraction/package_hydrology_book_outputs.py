"""
Package Mauritius Hydrology Data Book outputs into both:
  1. standardized separate deliverables
  2. consolidated merged deliverables

This script does not alter existing extraction outputs. It reads the canonical CSVs
already produced by the extraction scripts and writes a named export package under:

    <hydrology-output-root>/named_exports/
            separate/
            consolidated/

It also writes an inventory CSV describing all packaged files.
"""

import sys
from pathlib import Path

import pandas as pd


BASE_DIR = Path(
    "."
)
SEPARATE_DIR = BASE_DIR / "named_exports" / "separate"
CONSOLIDATED_DIR = BASE_DIR / "named_exports" / "consolidated"
INVENTORY_PATH = BASE_DIR / "named_exports" / "mauritius_hydrology_book__packaging_inventory.csv"

PREFIX = "mauritius_hydrology_book"

FLOW_DIRS = {
    "2006-2010": Path("."),
    "2000-2005": Path("."),
}

STATIC_DATASETS = [
    {
        "theme": "rainfall",
        "source": BASE_DIR / "extracted_rainfall" / "precipitation_monthly.csv",
        "separate_name": f"{PREFIX}__rainfall__precipitation_monthly.csv",
        "consolidated_name": f"{PREFIX}__rainfall__precipitation_monthly_all_books.csv",
    },
    {
        "theme": "rainfall",
        "source": BASE_DIR / "extracted_rainfall" / "rainfall_longterm_means.csv",
        "separate_name": f"{PREFIX}__rainfall__long_term_means.csv",
        "consolidated_name": f"{PREFIX}__rainfall__long_term_means_all_books.csv",
    },
    {
        "theme": "reservoir",
        "source": BASE_DIR / "extracted_reservoir" / "reservoir_salient_features.csv",
        "separate_name": f"{PREFIX}__reservoir__salient_features.csv",
        "consolidated_name": f"{PREFIX}__reservoir__salient_features_all_books.csv",
    },
    {
        "theme": "reservoir",
        "source": BASE_DIR / "extracted_reservoir" / "reservoir_feeder_canals.csv",
        "separate_name": f"{PREFIX}__reservoir__feeder_canals.csv",
        "consolidated_name": f"{PREFIX}__reservoir__feeder_canals_all_books.csv",
    },
    {
        "theme": "groundwater",
        "source": BASE_DIR / "extracted_groundwater" / "well_characteristics.csv",
        "separate_name": f"{PREFIX}__groundwater__well_characteristics.csv",
        "consolidated_name": f"{PREFIX}__groundwater__well_characteristics_all_books.csv",
    },
    {
        "theme": "groundwater",
        "source": BASE_DIR / "extracted_groundwater" / "small_well_characteristics.csv",
        "separate_name": f"{PREFIX}__groundwater__small_well_characteristics.csv",
        "consolidated_name": f"{PREFIX}__groundwater__small_well_characteristics_all_books.csv",
    },
    {
        "theme": "groundwater",
        "source": BASE_DIR / "extracted_groundwater" / "all_wells.csv",
        "separate_name": f"{PREFIX}__groundwater__all_wells.csv",
        "consolidated_name": f"{PREFIX}__groundwater__all_wells_all_books.csv",
    },
    {
        "theme": "river_gauging",
        "source": BASE_DIR / "extracted_river_gauging" / "river_gauging_stations_index.csv",
        "separate_name": f"{PREFIX}__river_gauging__station_index.csv",
        "consolidated_name": f"{PREFIX}__river_gauging__station_index_all_books.csv",
    },
    {
        "theme": "water_quality",
        "source": BASE_DIR / "extracted_water_quality" / "river_sampling_points.csv",
        "separate_name": f"{PREFIX}__water_quality__river_sampling_points.csv",
        "consolidated_name": f"{PREFIX}__water_quality__river_sampling_points_all_books.csv",
    },
    {
        "theme": "water_quality",
        "source": BASE_DIR / "extracted_water_quality" / "groundwater_sampling_points.csv",
        "separate_name": f"{PREFIX}__water_quality__groundwater_sampling_points.csv",
        "consolidated_name": f"{PREFIX}__water_quality__groundwater_sampling_points_all_books.csv",
    },
    {
        "theme": "water_quality",
        "source": BASE_DIR / "extracted_water_quality" / "water_quality_parameter_ranges.csv",
        "separate_name": f"{PREFIX}__water_quality__parameter_ranges.csv",
        "consolidated_name": f"{PREFIX}__water_quality__parameter_ranges_all_books.csv",
    },
    {
        "theme": "visual",
        "source": BASE_DIR / "extracted_visual" / "isohyetal_contours.csv",
        "separate_name": f"{PREFIX}__visual__isohyetal_contours.csv",
        "consolidated_name": f"{PREFIX}__visual__isohyetal_contours_all_books.csv",
    },
    {
        "theme": "visual",
        "source": BASE_DIR / "extracted_visual" / "schematic_topology.csv",
        "separate_name": f"{PREFIX}__visual__schematic_topology.csv",
        "consolidated_name": f"{PREFIX}__visual__schematic_topology_all_books.csv",
    },
    {
        "theme": "visual",
        "source": BASE_DIR / "extracted_visual" / "storage_chart_scale.csv",
        "separate_name": f"{PREFIX}__visual__storage_chart_scale.csv",
        "consolidated_name": f"{PREFIX}__visual__storage_chart_scale_all_books.csv",
    },
    {
        "theme": "visual",
        "source": BASE_DIR / "extracted_visual" / "storage_chart_monthly.csv",
        "separate_name": f"{PREFIX}__visual__storage_chart_monthly.csv",
        "consolidated_name": f"{PREFIX}__visual__storage_chart_monthly_all_books.csv",
    },
]


def ensure_dirs():
    SEPARATE_DIR.mkdir(parents=True, exist_ok=True)
    CONSOLIDATED_DIR.mkdir(parents=True, exist_ok=True)


def write_csv(df, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def add_inventory_row(inventory_rows, tier, theme, dataset_key, output_path, row_count, source_path, notes=None):
    inventory_rows.append({
        "tier": tier,
        "theme": theme,
        "dataset_key": dataset_key,
        "file_name": output_path.name,
        "output_path": str(output_path),
        "row_count": row_count,
        "source_path": source_path,
        "notes": notes,
    })


def package_static_datasets(inventory_rows):
    for spec in STATIC_DATASETS:
        src = spec["source"]
        if not src.exists():
            print(f"SKIP missing source: {src}")
            continue

        df = pd.read_csv(src)

        separate_path = SEPARATE_DIR / spec["theme"] / spec["separate_name"]
        consolidated_path = CONSOLIDATED_DIR / spec["consolidated_name"]

        write_csv(df, separate_path)
        write_csv(df, consolidated_path)

        dataset_key = spec["separate_name"].replace(f"{PREFIX}__", "").replace(".csv", "")
        add_inventory_row(inventory_rows, "separate", spec["theme"], dataset_key, separate_path, len(df), str(src))
        add_inventory_row(
            inventory_rows,
            "consolidated",
            spec["theme"],
            dataset_key + "_all_books",
            consolidated_path,
            len(df),
            str(src),
            notes="Source file already spans both books." if "all_books" in consolidated_path.name else None,
        )


def package_flow_datasets(inventory_rows):
    flow_frames = []

    for book_label, flow_dir in FLOW_DIRS.items():
        if not flow_dir.exists():
            print(f"SKIP missing flow dir: {flow_dir}")
            continue

        book_slug = book_label.replace("-", "_")
        for csv_path in sorted(flow_dir.glob("*_flows.csv")):
            df = pd.read_csv(csv_path)
            df.insert(0, "book", book_label)
            station_code = csv_path.stem.replace("_flows", "").lower()

            separate_name = f"{PREFIX}__flows__book_{book_slug}__{station_code}_monthly.csv"
            separate_path = SEPARATE_DIR / "flows" / separate_name
            write_csv(df, separate_path)
            add_inventory_row(
                inventory_rows,
                "separate",
                "flows",
                f"flows__{book_slug}__{station_code}",
                separate_path,
                len(df),
                str(csv_path),
            )
            flow_frames.append(df)

    if flow_frames:
        df_all_flows = pd.concat(flow_frames, ignore_index=True)
        consolidated_path = CONSOLIDATED_DIR / f"{PREFIX}__flows__monthly_all_stations_all_books.csv"
        write_csv(df_all_flows, consolidated_path)
        add_inventory_row(
            inventory_rows,
            "consolidated",
            "flows",
            "flows__all_stations_all_books",
            consolidated_path,
            len(df_all_flows),
            "; ".join(str(path) for path in FLOW_DIRS.values()),
            notes="Merged from per-station flow CSVs for both books.",
        )


def package_sampling_sites_consolidated(inventory_rows):
    river_path = BASE_DIR / "extracted_water_quality" / "river_sampling_points.csv"
    groundwater_path = BASE_DIR / "extracted_water_quality" / "groundwater_sampling_points.csv"
    if not river_path.exists() or not groundwater_path.exists():
        return

    river_df = pd.read_csv(river_path)
    groundwater_df = pd.read_csv(groundwater_path)

    river_sites = pd.DataFrame({
        "book": river_df["book"],
        "page_num": river_df["page_num"],
        "site_type": "river_sampling_point",
        "site_name": river_df["sampling_point"],
        "parent_feature": river_df["river"],
        "region": None,
        "code_raw": None,
    })
    groundwater_sites = pd.DataFrame({
        "book": groundwater_df["book"],
        "page_num": groundwater_df["page_num"],
        "site_type": "groundwater_borehole",
        "site_name": groundwater_df["name"],
        "parent_feature": None,
        "region": groundwater_df["region"],
        "code_raw": groundwater_df["borehole_no_raw"],
    })

    combined = pd.concat([river_sites, groundwater_sites], ignore_index=True)
    out_path = CONSOLIDATED_DIR / f"{PREFIX}__water_quality__sampling_sites_all_books.csv"
    write_csv(combined, out_path)
    add_inventory_row(
        inventory_rows,
        "consolidated",
        "water_quality",
        "water_quality__sampling_sites_all_books",
        out_path,
        len(combined),
        f"{river_path}; {groundwater_path}",
        notes="Merged river and groundwater sampling locations into one site inventory.",
    )


def main():
    ensure_dirs()
    inventory_rows = []

    package_static_datasets(inventory_rows)
    package_flow_datasets(inventory_rows)
    package_sampling_sites_consolidated(inventory_rows)

    df_inventory = pd.DataFrame(inventory_rows).sort_values(["tier", "theme", "file_name"])
    write_csv(df_inventory, INVENTORY_PATH)
    print(f"Saved: {INVENTORY_PATH} ({len(df_inventory)} rows)")
    print(f"Separate outputs: {SEPARATE_DIR}")
    print(f"Consolidated outputs: {CONSOLIDATED_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())