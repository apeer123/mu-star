"""
Extract salient features and feeder canal data from Chapter 5 reservoir PDFs.

Structure of each reservoir PDF (La Ferme, Mare Aux Vacoas, etc.):
  Page 1:
    - Feeder canals table (name, length km, river, design capacity m3/s)
    - Embedded schematic diagram image (cannot be parsed as text)
    - Salient features block (key:value text, not a table):
        Year of Construction, Catchment Area, Mean Annual Rainfall,
        Annual Regulated Yield, Reservoir Capacity, Dead Storage,
        Full Reservoir Level, Type of Dam, Maximum height of dam,
        Length of Dam, Type of spillway, Width of Spillway, Purpose
  Page 2+:
    - Daily storage variation charts per year (graphical - extracted as images by render_visual_pdfs.py)

Sources: Both books (2006-2010 and 2000-2005)

Outputs written to extracted_reservoir/:
  reservoir_salient_features.csv  - key technical parameters per reservoir
  reservoir_feeder_canals.csv     - feeder canal inventory per reservoir
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

# ---------------------------------------------------------------------------
# Book definitions
# ---------------------------------------------------------------------------
BOOKS = {
    "2006-2010": Path(Path("../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book").resolve()),
    "2000-2005": Path("."),
}

RESERVOIR_NAMES = [
    "La Ferme",
    "Mare Aux Vacoas",
    "Mare Longue",
    "Midlands",
    "Nicoliere",
    "Piton Du Milieu",
]

OUT_DIR = Path(".")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Salient features parser (text-based, not table)
# ---------------------------------------------------------------------------
FEATURE_PATTERNS = {
    "location":                 r"Location\s*:\s*([^\n]+)",
    "year_constructed":         r"Year of Construction\s*:\s*(\d{4})",
    "catchment_area_km2":       r"Catchment Area\s*:\s*([\d.]+)\s*km",
    "mean_annual_rainfall_mm":  r"Mean Annual Rainfall\s*:\s*([\d.]+)\s*mm",
    "annual_regulated_yield_Mm3": r"Annual Regulated Yield\s*:\s*([\d.]+)\s*Mm",
    "reservoir_capacity_Mm3":   r"Reservoir Capacity\s*:\s*([\d.]+)\s*Mm",
    "dead_storage_Mm3":         r"Dead Storage\s*:\s*([\d.]+)\s*Mm",
    "full_reservoir_level_masl": r"Full Reservoir Level\s*:\s*([\d.]+)\s*m",
    "type_of_dam":              r"Type of Dam\s*:\s*([^\n]+)",
    "dam_height_ground_m":      r"above ground level[^\d]*([\d.]+)\s*m",
    "dam_length_m":             r"Length of Dam\s*:\s*([\d.,]+)\s*m",
    "type_of_spillway":         r"Type of spillway\s*:\s*([^\n]+)",
    "spillway_width_m":         r"Width of Spillway\s*:\s*([\d.]+)\s*m",
    "purpose":                  r"Purpose\s*:\s*([^\n]+)",
}


def parse_salient_features(page_text, reservoir_name):
    """Extract key:value pairs from reservoir salient features text block."""
    features = {"reservoir": reservoir_name}
    for key, pattern in FEATURE_PATTERNS.items():
        m = re.search(pattern, page_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().rstrip(".")
            # Try to convert numeric values
            if key in ("year_constructed", "catchment_area_km2", "mean_annual_rainfall_mm",
                       "annual_regulated_yield_Mm3", "reservoir_capacity_Mm3",
                       "dead_storage_Mm3", "full_reservoir_level_masl",
                       "dam_height_ground_m", "dam_length_m", "spillway_width_m"):
                try:
                    val = float(val.replace(",", ""))
                except ValueError:
                    pass
            features[key] = val
    return features


def parse_feeder_canals(page_tables, reservoir_name):
    """Extract feeder canal rows from the first page table.
    Handles both one-feeder-per-row and stacked-feeders-within-one-row formats.
    """
    canals = []
    for tbl in page_tables:
        if not tbl:
            continue
        header_found = False
        for row in tbl:
            if not row or not row[0]:
                continue
            cell0 = str(row[0]).strip().upper()
            # Detect header row (FEEDER CANALS or FEEDERS CANALS or FEEDER CANAL)
            if re.search(r"FEEDER[S]?\s+CANAL", cell0):
                header_found = True
                # The header row itself may contain a feeder name below the column label
                # e.g. ['FEEDER CANALS/ RIVER DIVERSIONS\nL.N.F.C', 'LENGTH\n(Km)\n27', ...]
                # Split each cell on \n and take parts after the first (the label)
                def after_label(cell, skip=1):
                    if not cell:
                        return []
                    parts = str(cell).split("\n")
                    return [p.strip() for p in parts[skip:] if p.strip()]

                names = after_label(row[0], skip=1)  # skip "FEEDER CANALS/..." label
                lengths = after_label(row[1], skip=2) if len(row) > 1 else []  # skip "LENGTH\n(Km)"
                rivers = after_label(row[2], skip=1) if len(row) > 2 else []
                caps = after_label(row[3], skip=2) if len(row) > 3 else []  # skip "DESIGN\nCAPACITY"
                for i, name in enumerate(names):
                    if not name or name.startswith("*"):
                        continue
                    length_km = None
                    river = rivers[i] if i < len(rivers) else None
                    cap = None
                    try:
                        length_km = float(lengths[i]) if i < len(lengths) else None
                    except (ValueError, TypeError):
                        pass
                    try:
                        cap = float(caps[i]) if i < len(caps) else None
                    except (ValueError, TypeError):
                        pass
                    canals.append({
                        "reservoir": reservoir_name,
                        "feeder_canal": name,
                        "length_km": length_km,
                        "river": river,
                        "design_capacity_m3s": cap,
                    })
                continue

            if not header_found:
                continue

            # Skip non-data rows
            if cell0 in ("FEEDERS CANALS", "FEEDER", "LENGTH", "DESIGN",
                         "FEEDER CANAL", "FEEDER CANALS"):
                continue
            if "NATURAL STREAMS" in cell0 or cell0 == "FEEDERS":
                continue
            # Skip footnote rows
            if cell0.startswith("*"):
                continue

            # Split stacked cells on \n
            names = [p.strip() for p in str(row[0]).split("\n") if p.strip() and not p.strip().startswith("*")]
            lengths_raw = str(row[1]).split("\n") if len(row) > 1 and row[1] else []
            rivers_raw = str(row[2]).split("\n") if len(row) > 2 and row[2] else []
            caps_raw = str(row[3]).split("\n") if len(row) > 3 and row[3] else []

            for i, name in enumerate(names):
                if not name:
                    continue
                length_km = None
                river = rivers_raw[i].strip() if i < len(rivers_raw) else None
                cap = None
                try:
                    length_km = float(lengths_raw[i].strip()) if i < len(lengths_raw) else None
                except (ValueError, TypeError):
                    pass
                try:
                    cap = float(caps_raw[i].strip()) if i < len(caps_raw) else None
                except (ValueError, TypeError):
                    pass
                canals.append({
                    "reservoir": reservoir_name,
                    "feeder_canal": name,
                    "length_km": length_km,
                    "river": river,
                    "design_capacity_m3s": cap,
                })
    return canals


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    all_features = []
    all_canals = []

    for book_label, base_dir in BOOKS.items():
        res_dir = base_dir / "Chapter 5" / "Salient Features, Storage variation"
        if not res_dir.exists():
            print(f"MISSING dir: {res_dir}")
            continue

        print(f"\n=== Book {book_label} ===")
        for res_name in RESERVOIR_NAMES:
            pdf_path = res_dir / f"{res_name}.pdf"
            if not pdf_path.exists():
                print(f"  MISSING: {res_name}.pdf")
                continue

            with pdfplumber.open(pdf_path) as doc:
                page_count = len(doc.pages)
                page1 = doc.pages[0]
                page1_text = page1.extract_text() or ""
                page1_tables = page1.extract_tables()

            # Salient features from text
            features = parse_salient_features(page1_text, res_name)
            features["book"] = book_label
            features["page_count"] = page_count
            all_features.append(features)

            # Feeder canals from tables
            canals = parse_feeder_canals(page1_tables, res_name)
            for c in canals:
                c["book"] = book_label
            all_canals.extend(canals)

            has_capacity = "reservoir_capacity_Mm3" in features
            has_area = "catchment_area_km2" in features
            print(f"  {res_name}: {len(canals)} feeders, "
                  f"capacity={'%.2f Mm3' % features.get('reservoir_capacity_Mm3', 0) if has_capacity else '?'}, "
                  f"area={features.get('catchment_area_km2','?')} km2, "
                  f"purpose={features.get('purpose','?')}")

    # --- Save salient features
    if all_features:
        df = pd.DataFrame(all_features)
        # Order columns sensibly
        first_cols = ["reservoir", "book", "location", "year_constructed", "catchment_area_km2",
                      "mean_annual_rainfall_mm", "annual_regulated_yield_Mm3",
                      "reservoir_capacity_Mm3", "dead_storage_Mm3",
                      "full_reservoir_level_masl", "type_of_dam", "dam_height_ground_m",
                      "dam_length_m", "type_of_spillway", "spillway_width_m", "purpose"]
        existing = [c for c in first_cols if c in df.columns]
        extra = [c for c in df.columns if c not in first_cols]
        df = df[existing + extra]
        out = OUT_DIR / "reservoir_salient_features.csv"
        df.to_csv(out, index=False)
        print(f"\nSaved: {out}  ({len(df)} rows)")

    # --- Save feeder canals
    if all_canals:
        df_c = pd.DataFrame(all_canals)
        out_c = OUT_DIR / "reservoir_feeder_canals.csv"
        df_c.to_csv(out_c, index=False)
        print(f"Saved: {out_c}  ({len(df_c)} rows)")

    if not all_features:
        print("WARNING: No reservoir features extracted")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
