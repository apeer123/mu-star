"""
Render all visual PDFs from both Hydrology Data Books to high-resolution PNG images.

For each PDF page this script:
  1. Renders to PNG at 300 DPI using PyMuPDF
  2. Extracts ALL text elements with bounding-box positions
  3. Classifies the page content type (schematic / isohyetal_map / drainage_map /
     storage_chart / geological_map / table / text)
  4. Saves a JSON manifest alongside the PNG

Output structure:
  rendered_images/
    <book_label>/
      <chapter>/<pdf_stem>/
        page_01.png
        page_01.json     <- text elements + metadata

A master index file rendered_images/manifest_index.csv lists every image with its
visual type, enabling downstream AI/CV processing.

Usage:
    python render_visual_pdfs.py               # process both books
    python render_visual_pdfs.py --book 2006-2010  # one book only
    python render_visual_pdfs.py --dpi 150     # lower DPI for faster runs
"""

import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

# ---------------------------------------------------------------------------
# Book definitions
# ---------------------------------------------------------------------------
BOOKS = {
    "2006-2010": Path(Path("../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book").resolve()),
    "2000-2005": Path("."),
}

BASE_OUT = Path(Path("../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book/Images").resolve())

# ---------------------------------------------------------------------------
# Visual page classification
#
# Each entry: (regex pattern matching the pdf stem, page_index 0-based or None=all, type_label)
# Page index None means "apply this type to all pages"
# ---------------------------------------------------------------------------

# PDFs that are purely visual maps — ALL pages are visual
VISUAL_ALL_PAGES = [
    (r"(?i)isohyetal.map",          "isohyetal_map"),
    (r"(?i)map.drainage.area",       "drainage_area_map"),
    (r"(?i)drainage.areas.rodrigues", "drainage_area_map"),
    (r"(?i)geological.map.rodrigues", "geological_map"),
]

# Per-PDF page overrides
# (pdf_stem_regex, page_0based, type_label)
PAGE_TYPE_OVERRIDES = [
    # Schematic + flow data PDFs: page 0 is schematic, pages 1+ are tables
    (r"(?i)^(A|B|D|E|G|H|J|L|M|N|P|Q|R|S|T|U|W|Y|Z)[0-9]", 0, "schematic_diagram"),
    (r"(?i)^totgrse$",                                         0, "schematic_diagram"),
    # Reservoir PDFs: page 0 is salient features (table+embedded schematic), page 1+ are storage charts
    (r"(?i)^(la.ferme|mare.aux.vacoas|mare.longue|midlands|nicoliere|piton.du.milieu)$",
     0, "reservoir_features"),
    (r"(?i)^(la.ferme|mare.aux.vacoas|mare.longue|midlands|nicoliere|piton.du.milieu)$",
     1, "storage_variation_chart"),
]

DEFAULT_TYPES = {
    "precipitation data":      "table",
    "Precipitation data":      "table",
    "Rainfall data":           "table",
    "Rainfall Stations":       "map_reference",
    "River Gauging Stations":  "table",
    "Stations data provided":  "table",
    "Stations on Diversions":  "table",
    "Flow Data on Rivers and Canals": "table",
    "descriptive notes on hydrology": "text",
    "Brief Description groundwater":  "text",
    "well characteristics":    "table",
    "Small well characteristics": "table",
    "Well characteristics":    "table",
    "water quality":           "table",
    "Water quality":           "table",
    "Brief Description Reservoirs": "text",
    "INTRODUCTION":            "text",
    "Glossary":                "text",
    "Staff List":              "text",
    "table of contents":       "text",
    "minister message+foreword": "text",
    "Agalega":                 "table",
    "Brief Description Rod&Aga": "text",
    "Rodrigues well characteristics": "table",
}


def classify_page(pdf_stem, page_idx):
    """Return a content type string for a given PDF stem + page index."""
    # Check all-visual-pages list
    for pat, label in VISUAL_ALL_PAGES:
        if re.search(pat, pdf_stem):
            return label
    # Check per-page overrides
    for pat, pg, label in PAGE_TYPE_OVERRIDES:
        if re.search(pat, pdf_stem) and (pg is None or pg == page_idx):
            return label
    # Fall back to table for remaining schematic pages (page 1+)
    for pat, pg, label in PAGE_TYPE_OVERRIDES:
        if re.search(pat, pdf_stem) and pg == 0 and page_idx > 0:
            return "table"
    # Look up default by stem
    for key, label in DEFAULT_TYPES.items():
        if key.lower() in pdf_stem.lower():
            return label
    return "unknown"


# ---------------------------------------------------------------------------
# Text element extraction
# ---------------------------------------------------------------------------

def extract_text_elements(page):
    """
    Extract all text spans from a PyMuPDF page with their bounding boxes.
    Returns a list of dicts: {text, x0, y0, x1, y1, fontsize, fontname}
    """
    elements = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:  # skip image blocks
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                bbox = span.get("bbox", [0, 0, 0, 0])
                elements.append({
                    "text": text,
                    "x0": round(bbox[0], 1),
                    "y0": round(bbox[1], 1),
                    "x1": round(bbox[2], 1),
                    "y1": round(bbox[3], 1),
                    "fontsize": round(span.get("size", 0), 1),
                    "fontname": span.get("font", ""),
                })
    return elements


def build_schematic_topology(text_elements, station_code):
    """
    Attempt to reconstruct schematic topology from positioned text.
    Identifies:
      - Station codes (known pattern: letter+digits)
      - River/canal names
      - Infrastructure labels (WEIR, DAM, RESERVOIR, WTP, etc.)
      - Flow values / catchment area labels
    Returns a topology dict for inclusion in the JSON manifest.
    """
    station_pat = re.compile(r"^[A-Z]\d{2,4}[a-z]?$")
    infra_keywords = {"WEIR", "DAM", "RESERVOIR", "WTP", "WWTP", "POWER", "DIVERSION",
                      "INTAKE", "CANAL", "FEEDER", "SPILLWAY", "PUMP", "GAUGE"}

    stations_found = []
    infrastructure = []
    labels = []

    for el in text_elements:
        t = el["text"].strip()
        t_upper = t.upper()
        if station_pat.match(t_upper):
            stations_found.append({
                "code": t_upper,
                "x": round((el["x0"] + el["x1"]) / 2, 1),
                "y": round((el["y0"] + el["y1"]) / 2, 1),
            })
        elif any(kw in t_upper for kw in infra_keywords):
            infrastructure.append({
                "label": t,
                "x": round((el["x0"] + el["x1"]) / 2, 1),
                "y": round((el["y0"] + el["y1"]) / 2, 1),
            })
        elif len(t) > 3 and not re.match(r"^[\d.,\-/]+$", t):
            labels.append({
                "text": t,
                "x": round((el["x0"] + el["x1"]) / 2, 1),
                "y": round((el["y0"] + el["y1"]) / 2, 1),
            })

    # Sort stations top-to-bottom (smaller y = higher on page = upstream typically)
    stations_found.sort(key=lambda s: s["y"])

    # Build simple chain: each station lists the next one below it
    chain = []
    for i, st in enumerate(stations_found):
        entry = {"code": st["code"], "position_x": st["x"], "position_y": st["y"]}
        if i + 1 < len(stations_found):
            entry["downstream_candidate"] = stations_found[i + 1]["code"]
        chain.append(entry)

    return {
        "primary_station": station_code,
        "stations_detected": [s["code"] for s in stations_found],
        "station_chain": chain,
        "infrastructure": infrastructure,
        "other_labels": labels[:20],  # cap to avoid huge manifests
    }


# ---------------------------------------------------------------------------
# AI vision prompt generator
# ---------------------------------------------------------------------------

PROMPTS = {
    "schematic_diagram": (
        "This is a schematic diagram of a river catchment in Mauritius. "
        "Please identify: (1) All station codes visible (format: letter + digits, e.g. A03, W03). "
        "(2) The flow direction (upstream to downstream connections). "
        "(3) Any diversions, reservoirs, dams, weirs or water treatment plants shown. "
        "(4) The name of the main river. "
        "Output as JSON: {river, stations: [{code, type, connected_to}], diversions: [{from, to, label}], infrastructure: [{type, label}]}"
    ),
    "isohyetal_map": (
        "This is an isohyetal map of Mauritius showing annual rainfall contour lines. "
        "Please identify: (1) All contour line values visible (in mm). "
        "(2) The approximate location of each contour (describe relative to island landmarks). "
        "(3) The areas of highest and lowest rainfall. "
        "(4) Any rainfall station markers with their names/codes. "
        "Output as JSON: {contour_lines: [{value_mm, location_description}], max_rainfall_area, min_rainfall_area, stations: [{code, name, approx_location}]}"
    ),
    "drainage_area_map": (
        "This is a drainage area map of Mauritius showing river catchments and gauging stations. "
        "Please identify: (1) All gauging station codes and their locations. "
        "(2) The main rivers and their drainage areas. "
        "(3) Any administrative boundaries shown. "
        "Output as JSON: {stations: [{code, name, river, approx_coords}], rivers: [{name, catchment_area_description}]}"
    ),
    "storage_variation_chart": (
        "This shows bar charts of daily storage variation for a reservoir in Mauritius, one chart per year. "
        "For each year visible, please extract: (1) The year label. "
        "(2) The approximate monthly storage values (Mm3) reading from the bar chart. "
        "(3) The normal/average line if shown. "
        "Output as JSON: {reservoir, years: [{year, monthly_storage_Mm3: {Jan:.., Feb:.., ...}, normal_Mm3}]}"
    ),
    "geological_map": (
        "This is a geological map of Rodrigues Island, Mauritius. "
        "Please identify: (1) The geological formations shown (rock types, ages). "
        "(2) The legend/key entries. "
        "(3) Any structural features (faults, volcanic features). "
        "Output as JSON: {formations: [{name, rock_type, age, color_in_map}], structures: [{type, description}]}"
    ),
}


def get_ai_prompt(page_type, context=None):
    """Return an appropriate AI vision prompt for the given page type."""
    prompt = PROMPTS.get(page_type, "Describe all data and information visible in this image. Output as structured JSON.")
    if context:
        prompt = f"Context: {context}\n\n" + prompt
    return prompt


# ---------------------------------------------------------------------------
# Core rendering function
# ---------------------------------------------------------------------------

def render_pdf(pdf_path, out_base_dir, book_label, dpi=300, force=False):
    """
    Render all pages of a PDF to PNG + JSON manifest.
    Returns list of manifest dicts (one per page).
    """
    stem = pdf_path.stem
    rel_path = pdf_path.relative_to(BOOKS[book_label])
    # Build output directory mirroring the book structure
    out_dir = out_base_dir / book_label / rel_path.parent / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    doc = fitz.open(str(pdf_path))
    mat = fitz.Matrix(dpi / 72, dpi / 72)

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        img_path = out_dir / f"page_{page_num:02d}.png"
        json_path = out_dir / f"page_{page_num:02d}.json"
        page_type = classify_page(stem, page_idx)

        # Render image
        if not img_path.exists() or force:
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            pix.save(str(img_path))

        # Extract text elements
        text_elements = extract_text_elements(page)

        # Build topology for schematic diagrams
        topology = None
        if page_type == "schematic_diagram":
            topology = build_schematic_topology(text_elements, stem.upper())

        # Build manifest
        manifest = {
            "book": book_label,
            "pdf_stem": stem,
            "pdf_path": str(pdf_path),
            "page_num": page_num,
            "page_type": page_type,
            "image_path": str(img_path),
            "image_width_px": page.rect.width * dpi / 72,
            "image_height_px": page.rect.height * dpi / 72,
            "dpi": dpi,
            "text_elements": text_elements,
            "topology": topology,
            "ai_prompt": get_ai_prompt(page_type, context=f"PDF: {stem}, Book: {book_label}"),
        }

        # Save manifest JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # Compact record for index CSV
        records.append({
            "book": book_label,
            "pdf_stem": stem,
            "chapter": rel_path.parts[0] if len(rel_path.parts) > 1 else "",
            "page_num": page_num,
            "page_type": page_type,
            "image_path": str(img_path),
            "json_path": str(json_path),
            "text_element_count": len(text_elements),
            "is_visual": page_type not in ("table", "text", "unknown"),
        })

    doc.close()
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Render hydrology book PDFs to images")
    parser.add_argument("--book", choices=list(BOOKS.keys()) + ["both"], default="both")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--force", action="store_true", help="Re-render existing images")
    parser.add_argument("--visual-only", action="store_true",
                        help="Only render pages classified as visual (not table/text)")
    args = parser.parse_args()

    books_to_process = list(BOOKS.keys()) if args.book == "both" else [args.book]

    all_records = []

    for book_label in books_to_process:
        base_dir = BOOKS[book_label]
        if not base_dir.exists():
            print(f"MISSING book directory: {base_dir}")
            continue

        # Collect all PDFs in book
        all_pdfs = sorted(base_dir.rglob("*.pdf"))
        # Exclude already-extracted flow CSVs directory
        all_pdfs = [p for p in all_pdfs if "extracted_flows" not in str(p)]

        print(f"\n=== {book_label}: {len(all_pdfs)} PDFs ===")

        for pdf_path in all_pdfs:
            stem = pdf_path.stem
            # Quick pre-classification to skip if --visual-only
            if args.visual_only:
                # Check if any page of this PDF is visual
                has_visual = (
                    any(re.search(pat, stem) for pat, _ in VISUAL_ALL_PAGES)
                    or any(re.search(pat, stem) for pat, _, _ in PAGE_TYPE_OVERRIDES if _ == 0)
                )
                if not has_visual:
                    continue

            print(f"  Rendering {stem} ...", end=" ", flush=True)
            try:
                records = render_pdf(pdf_path, BASE_OUT, book_label, dpi=args.dpi, force=args.force)
                all_records.extend(records)
                visual_pages = sum(1 for r in records if r["is_visual"])
                print(f"{len(records)} pages ({visual_pages} visual)")
            except Exception as exc:
                print(f"ERROR: {exc}")

    # Save master index
    if all_records:
        BASE_OUT.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(all_records)
        idx_path = BASE_OUT / "manifest_index.csv"
        df.to_csv(idx_path, index=False)
        print(f"\nSaved index: {idx_path}")
        print(f"  Total pages rendered: {len(df)}")
        print(f"  Visual pages: {df.is_visual.sum()}")
        print(f"  By type:\n{df.page_type.value_counts().to_string()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
