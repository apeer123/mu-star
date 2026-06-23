"""
prep_coords.py — Extracts coordinates from WTP and WWTP shapefiles.
"""
import geopandas as gpd
import pandas as pd
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Extracts coordinates from shapefiles.")
    parser.add_argument("--wtp_shp", required=True, help="Path to Water Treatment shapefile")
    parser.add_argument("--wwtp_shp", required=True, help="Path to Wastewater Treatment shapefile")
    parser.add_argument("--output_dir", required=True, help="Directory to save CSV outputs")
    args = parser.parse_args()

    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    wtp = gpd.read_file(args.wtp_shp).to_crs(epsg=4326)
    wtp["lon"] = wtp.geometry.x
    wtp["lat"] = wtp.geometry.y
    wtp_out = wtp.drop(columns="geometry")[["OID_","Name","lon","lat","Snippet","PopupInfo"]]
    wtp_out.to_csv(os.path.join(out_dir, "wtp_with_coords.csv"), index=False)
    print("WTP:"); print(wtp_out.to_string())

    wwtp = gpd.read_file(args.wwtp_shp).to_crs(epsg=4326)
    wwtp["lon"] = wwtp.geometry.x
    wwtp["lat"] = wwtp.geometry.y
    wwtp_out = wwtp.drop(columns="geometry")[["OID_","Name","lon","lat","Snippet","PopupInfo"]]
    wwtp_out.to_csv(os.path.join(out_dir, "wwtp_with_coords.csv"), index=False)
    print("WWTP:"); print(wwtp_out.to_string())

    # UdM rivers OSM assignments
    rivers_csv = os.path.join(out_dir, "udm_rivers_attributes.csv")
    if os.path.exists(rivers_csv):
        rivers = pd.read_csv(rivers_csv)
        rivers_clean = rivers[rivers["name_sourc"] == "OSM"][["Name","assigned_n","name_sourc"]].drop_duplicates().sort_values("Name")
        rivers_clean.to_csv(os.path.join(out_dir, "udm_rivers_osm_assigned.csv"), index=False)
        print("UdM rivers direct OSM match:", len(rivers_clean), "unique segments")
    else:
        print(f"UdM rivers attributes file not found: {rivers_csv} (Skipping UdM assignments)")

if __name__ == "__main__":
    main()
