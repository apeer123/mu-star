"""
write_plant_named_csvs.py
Combines Manual-Review plant name assignments with OSM-confirmed localities
to produce final A4/A5 deliverable CSVs.
"""
import csv
import argparse
from pathlib import Path

def read_rows(csv_path):
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Type cast known numerics, let missing be empty string
            if 'id' in row and row['id']: row['id'] = int(row['id'])
            if 'lon' in row and row['lon']: row['lon'] = float(row['lon'])
            if 'lat' in row and row['lat']: row['lat'] = float(row['lat'])
            if 'capacity_m3d' in row and row['capacity_m3d']: row['capacity_m3d'] = int(row['capacity_m3d'])
            rows.append(row)
    return rows

def main():
    parser = argparse.ArgumentParser(description="Combines manual plant names with OSM-confirmed localities")
    parser.add_argument("--input_dir", required=True, help="Directory containing wtp_manual_assignments.csv and wwtp_manual_assignments.csv")
    parser.add_argument("--output_dir", required=True, help="Directory to save the named CSVs")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wtp_rows = read_rows(input_dir / "wtp_manual_assignments.csv")
    wwtp_rows = read_rows(input_dir / "wwtp_manual_assignments.csv")

    WTP_SCHEMA = ["id", "lon", "lat", "plant_name", "water_source", "service_area",
                  "osm_locality", "confidence", "name_basis"]
    WWTP_SCHEMA = ["id", "lon", "lat", "plant_name", "capacity_m3d", "discharge_to",
                   "osm_locality", "confidence", "name_basis"]

    for fname, rows, schema in [
        ("wtp_named.csv",  wtp_rows,  WTP_SCHEMA),
        ("wwtp_named.csv", wwtp_rows, WWTP_SCHEMA),
    ]:
        p = out_dir / fname
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=schema, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"Written: {p}  ({len(rows)} rows)")

if __name__ == "__main__":
    main()
