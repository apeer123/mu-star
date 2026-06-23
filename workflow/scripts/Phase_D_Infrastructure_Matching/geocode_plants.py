"""
geocode_plants.py
Reverse-geocodes WTP and WWTP coordinates via Nominatim OSM API.
Writes:
  wtp_geocoded.csv
  wwtp_geocoded.csv
in the specified output directory.
"""
import time
import csv
import argparse
import requests
from pathlib import Path

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
HEADERS = {"User-Agent": "MSTAR-Mauritius-Research/1.0"}

def read_coords(csv_path):
    coords = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            coords.append((int(row['num']), float(row['lon']), float(row['lat'])))
    return coords

def reverse_geocode(lon: float, lat: float) -> dict:
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "zoom": 16,
        "addressdetails": 1,
    }
    try:
        r = requests.get(NOMINATIM, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def extract_fields(result: dict) -> dict:
    addr = result.get("address", {})
    return {
        "osm_name":       result.get("name") or result.get("display_name", "")[:80],
        "display_name":   result.get("display_name", "")[:120],
        "osm_type":       result.get("osm_type", ""),
        "osm_category":   result.get("category", ""),
        "road":           addr.get("road", ""),
        "suburb":         addr.get("suburb", ""),
        "village":        addr.get("village", "") or addr.get("town", "") or addr.get("city", ""),
        "district":       addr.get("state_district", "") or addr.get("county", ""),
        "postcode":       addr.get("postcode", ""),
    }

def geocode_list(coords, label):
    rows = []
    for num, lon, lat in coords:
        print(f"  {label} #{num}  ({lon}, {lat})", end=" ... ")
        result = reverse_geocode(lon, lat)
        fields = extract_fields(result)
        row = {"num": num, "lon": lon, "lat": lat}
        row.update(fields)
        rows.append(row)
        print(fields["village"] or fields["suburb"] or fields["road"] or "?")
        time.sleep(1.1)  # Nominatim rate limit: 1 req/sec
    return rows

def main():
    parser = argparse.ArgumentParser(description="Reverse geocodes plant coordinates.")
    parser.add_argument("--input_dir", required=True, help="Directory containing wtp_seed_coords.csv and wwtp_seed_coords.csv")
    parser.add_argument("--output_dir", required=True, help="Directory to save geocoded CSVs")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wtp_coords = read_coords(input_dir / "wtp_seed_coords.csv")
    wwtp_coords = read_coords(input_dir / "wwtp_seed_coords.csv")

    print("=== WTP reverse-geocode ===")
    wtp_rows = geocode_list(wtp_coords, "WTP")

    print("\n=== WWTP reverse-geocode ===")
    wwtp_rows = geocode_list(wwtp_coords, "WWTP")

    SCHEMA = ["num", "lon", "lat", "osm_name", "village", "suburb", "road",
              "district", "postcode", "osm_type", "osm_category", "display_name"]

    for fname, rows in [("wtp_geocoded.csv", wtp_rows), ("wwtp_geocoded.csv", wwtp_rows)]:
        p = out_dir / fname
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SCHEMA, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"\nWritten: {p}")

if __name__ == "__main__":
    main()
