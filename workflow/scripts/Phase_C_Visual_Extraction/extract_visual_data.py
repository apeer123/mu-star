"""
AI/CV extraction from rendered visual PDF images.

This script reads the rendered PNG images and JSON manifests produced by
render_visual_pdfs.py and extracts structured data from the visual pages using:

  METHOD 1 (always run): Text-position analysis using the JSON manifests
    - Schematic diagrams: station code extraction + positional topology
    - Isohyetal maps:     contour value annotation extraction
    - Storage charts:     Y-axis label extraction for scale detection

  METHOD 2 (if OPENAI_API_KEY is set): Vision-Extract Vision API
    - Sends each visual page image to the OpenAI API with a structured prompt
    - Parses the JSON response and validates the output

  METHOD 3 (fallback): Saves images + prompts for manual AI processing
    - Creates a submission package that can be uploaded to any AI vision tool

Usage:
    python extract_visual_data.py                        # text analysis only
    python extract_visual_data.py --api                  # also call OpenAI API
    python extract_visual_data.py --type schematic_diagram  # specific type only
    python extract_visual_data.py --station A03          # specific station

Outputs (written to extracted_visual/):
  schematic_topology.csv     - station network topology from all schematics
  isohyetal_contours.csv     - contour line values (when available)
  storage_chart_scale.csv    - storage chart axis scale info
  api_responses/             - raw AI responses (if API mode)
  manual_review/             - images + prompts for manual AI review
"""

import argparse
import base64
from bisect import bisect_left
from collections import defaultdict
import json
import os
import re
import sys
from pathlib import Path

import fitz
import pandas as pd

MANIFEST_INDEX = Path(".")
OUT_DIR = Path(".")
OUT_DIR.mkdir(parents=True, exist_ok=True)

MANUAL_DIR = OUT_DIR / "manual_review"
MANUAL_DIR.mkdir(parents=True, exist_ok=True)

API_DIR = OUT_DIR / "api_responses"


# ---------------------------------------------------------------------------
# Method 1: Text-position analysis from JSON manifests
# ---------------------------------------------------------------------------

STATION_PAT = re.compile(r"^[A-Z]\d{2,4}[a-z]?$", re.IGNORECASE)

RIVER_KEYWORDS = {"RIVER", "RIVIERE", "RIV.", "RUISSEAU", "CANAL", "CREEK", "STREAM"}

INFRA_TYPE_MAP = {
    "WEIR":       "weir",
    "DAM":        "dam",
    "RESERVOIR":  "reservoir",
    "WTP":        "water_treatment_plant",
    "WWTP":       "wastewater_treatment_plant",
    "POWER":      "power_station",
    "DIVERSION":  "diversion",
    "INTAKE":     "intake",
    "SPILLWAY":   "spillway",
    "PUMP":       "pumping_station",
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_TICK_LETTERS = {"J", "F", "M", "A", "S", "O", "N", "D"}


def _approx_color(color, target, tol=0.05):
    if color is None:
        return False
    return all(abs(c - t) <= tol for c, t in zip(color, target))


def _median(values):
    vals = sorted(values)
    n_vals = len(vals)
    if n_vals == 0:
        return None
    mid = n_vals // 2
    if n_vals % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _rect_overlap_ratio(rect_a, rect_b):
    overlap = fitz.Rect(rect_a).intersect(rect_b)
    if overlap.is_empty:
        return 0.0
    inter_area = overlap.width * overlap.height
    base_area = min(rect_a.width * rect_a.height, rect_b.width * rect_b.height)
    if base_area <= 0:
        return 0.0
    return inter_area / base_area


def _dedupe_rects(rects, tol=1.0):
    deduped = []
    for rect in sorted(rects, key=lambda item: (item.y0, item.x0)):
        if any(
            abs(rect.x0 - existing.x0) <= tol and
            abs(rect.y0 - existing.y0) <= tol and
            abs(rect.x1 - existing.x1) <= tol and
            abs(rect.y1 - existing.y1) <= tol
            for existing in deduped
        ):
            continue
        deduped.append(rect)
    return deduped


def _iter_page_spans(page):
    spans = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                bbox = fitz.Rect(span.get("bbox", [0, 0, 0, 0]))
                spans.append({
                    "text": text,
                    "bbox": bbox,
                    "cx": (bbox.x0 + bbox.x1) / 2.0,
                    "cy": (bbox.y0 + bbox.y1) / 2.0,
                    "color": span.get("color"),
                    "fontname": span.get("font", ""),
                    "fontsize": span.get("size", 0),
                })
    return spans


def _find_plot_rects(page):
    plot_rects = []
    for drawing in page.get_drawings():
        if drawing.get("type") != "s":
            continue
        width = drawing.get("width") or 0
        color = drawing.get("color")
        is_black_border = _approx_color(color, (0.0, 0.0, 0.0), tol=0.02) and 0.15 <= width <= 0.35
        is_grey_border = _approx_color(color, (0.5, 0.5, 0.5), tol=0.08) and 0.5 <= width <= 1.2
        if not (is_black_border or is_grey_border):
            continue
        items = drawing.get("items", [])
        if len(items) != 1 or items[0][0] != "re":
            continue
        rect = items[0][1]
        if 100 <= rect.width <= 380 and 100 <= rect.height <= 220:
            plot_rects.append(rect)
    return _dedupe_rects(plot_rects)


def _infer_plot_rects_from_labels(spans, year_labels, page_rect):
    inferred = []
    ordered_labels = sorted(year_labels, key=lambda item: item["cy"])

    for idx, label in enumerate(ordered_labels):
        upper_limit = label["cy"]
        lower_limit = ordered_labels[idx + 1]["cy"] - 20 if idx + 1 < len(ordered_labels) else page_rect.y1 - 20

        month_spans = [
            span for span in spans
            if span["text"] in MONTH_TICK_LETTERS and upper_limit < span["cy"] < lower_limit
        ]
        month_spans = sorted(month_spans, key=lambda item: item["cx"])

        month_centers = []
        for span in month_spans:
            if month_centers and abs(span["cx"] - month_centers[-1]) <= 2:
                continue
            month_centers.append(span["cx"])

        if len(month_centers) != 12:
            continue

        month_diffs = [month_centers[i + 1] - month_centers[i] for i in range(11)]
        month_step = _median(month_diffs) or 10.0

        numeric_spans = []
        for span in spans:
            if not (upper_limit < span["cy"] < lower_limit):
                continue
            if _parse_numeric_value(span["text"]) is None:
                continue
            numeric_spans.append(span)

        left_axis = [span for span in numeric_spans if span["cx"] < month_centers[0]]
        right_axis = [span for span in numeric_spans if span["cx"] > month_centers[-1]]
        y_candidates = [span["cy"] for span in left_axis + right_axis]
        if len(y_candidates) < 2:
            continue

        inferred.append(fitz.Rect(
            month_centers[0] - month_step / 2.0,
            min(y_candidates),
            month_centers[-1] + month_step / 2.0,
            max(y_candidates),
        ))

    return _dedupe_rects(inferred, tol=3.0)


def _extract_year_labels(spans):
    labels = []
    for span in spans:
        match = re.fullmatch(r"YEAR\s*:\s*(\d{4})", span["text"])
        if match:
            labels.append({
                "year": int(match.group(1)),
                "cx": span["cx"],
                "cy": span["cy"],
                "bbox": span["bbox"],
            })
    return labels


def _assign_year_label(rect, year_labels):
    candidates = [
        label for label in year_labels
        if label["cy"] < rect.y0 and (rect.y0 - label["cy"]) <= 60
    ]
    if not candidates:
        return None
    rect_cx = (rect.x0 + rect.x1) / 2.0
    return min(
        candidates,
        key=lambda label: (
            abs(label["cx"] - rect_cx),
            rect.y0 - label["cy"],
        ),
    )


def _parse_numeric_value(text):
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _dedupe_spans_by_y(spans, tol=1.5):
    deduped = []
    for span in sorted(spans, key=lambda item: item["cy"]):
        if deduped and abs(span["cy"] - deduped[-1]["cy"]) <= tol:
            if span["bbox"].x1 > deduped[-1]["bbox"].x1:
                deduped[-1] = span
            continue
        deduped.append(span)
    return deduped


def _axis_labels_for_rect(spans, rect, side):
    candidates = []
    for span in spans:
        text = span["text"]
        value = _parse_numeric_value(text)
        if value is None:
            continue
        if not (rect.y0 - 5 <= span["cy"] <= rect.y1 + 5):
            continue
        if side == "left":
            offset = rect.x0 - span["bbox"].x1
            if offset < 0 or offset > 15:
                continue
        else:
            if "." not in text:
                continue
            offset = span["bbox"].x0 - rect.x1
            if offset < 0 or offset > 15:
                continue
        candidates.append({**span, "value": value})
    return _dedupe_spans_by_y(candidates)


def _fit_linear_axis(axis_labels):
    if len(axis_labels) < 2:
        return None
    ys = [label["cy"] for label in axis_labels]
    vals = [label["value"] for label in axis_labels]
    y_mean = sum(ys) / len(ys)
    v_mean = sum(vals) / len(vals)
    denom = sum((y_val - y_mean) ** 2 for y_val in ys)
    if denom == 0:
        return None
    slope = sum((y_val - y_mean) * (val - v_mean) for y_val, val in zip(ys, vals)) / denom
    intercept = v_mean - slope * y_mean
    return {
        "slope": slope,
        "intercept": intercept,
        "min_value": min(vals),
        "max_value": max(vals),
        "tick_values": sorted(set(vals)),
    }


def _month_boundaries(spans, rect):
    month_spans = [
        span for span in spans
        if span["text"] in MONTH_TICK_LETTERS
        and rect.x0 - 5 <= span["cx"] <= rect.x1 + 5
        and rect.y1 <= span["cy"] <= rect.y1 + 20
    ]
    month_spans = sorted(month_spans, key=lambda item: item["cx"])

    month_centers = []
    for span in month_spans:
        if month_centers and abs(span["cx"] - month_centers[-1]) <= 2:
            continue
        month_centers.append(span["cx"])

    if len(month_centers) != 12:
        step = rect.width / 12.0
        return [rect.x0 + step * idx for idx in range(13)]

    boundaries = [rect.x0]
    for idx in range(11):
        boundaries.append((month_centers[idx] + month_centers[idx + 1]) / 2.0)
    boundaries.append(rect.x1)
    return boundaries


def _candidate_curve_drawings(drawings, rect):
    black = []
    blue = []
    for drawing in drawings:
        if drawing.get("type") != "s":
            continue
        draw_rect = drawing.get("rect")
        width = drawing.get("width") or 0
        if draw_rect is None or width < 0.5:
            continue
        if _rect_overlap_ratio(draw_rect, rect) <= 0.15 and not fitz.Rect(draw_rect).intersects(rect):
            continue
        color = drawing.get("color")
        if _approx_color(color, (0.0, 0.0, 0.0), tol=0.02):
            black.append(drawing)
        elif _approx_color(color, (0.2, 0.2, 0.8), tol=0.08):
            blue.append(drawing)
    return black, blue


def _select_curve_groups(drawings, rect):
    black, blue = _candidate_curve_drawings(drawings, rect)
    black_widths = sorted({round(d.get("width") or 0, 2) for d in black})

    year_drawings = []
    normal_drawings = []
    if len(black_widths) >= 2:
        year_width = min(black_widths)
        normal_width = max(black_widths)
        year_drawings = [d for d in black if abs((d.get("width") or 0) - year_width) <= 0.25]
        normal_drawings = [d for d in black if abs((d.get("width") or 0) - normal_width) <= 0.25]
    elif black_widths:
        year_drawings = black

    return year_drawings, normal_drawings, blue


def _polyline_points(drawings, rect):
    grouped = defaultdict(list)

    for drawing in drawings:
        for item in drawing.get("items", []):
            kind = item[0]
            if kind == "l":
                points = item[1:3]
            elif kind == "c":
                points = item[1:5]
            else:
                continue

            for point in points:
                x_pos = float(point.x)
                y_pos = float(point.y)
                if rect.x0 - 2 <= x_pos <= rect.x1 + 2 and rect.y0 - 20 <= y_pos <= rect.y1 + 20:
                    grouped[round(x_pos, 2)].append(y_pos)

    if not grouped:
        return [], []

    xs = sorted(grouped)
    ys = [_median(grouped[x_pos]) for x_pos in xs]
    return xs, ys


def _interpolate_y(xs, ys, x_query):
    if not xs:
        return None
    if x_query <= xs[0]:
        return ys[0]
    if x_query >= xs[-1]:
        return ys[-1]

    idx = bisect_left(xs, x_query)
    x0 = xs[idx - 1]
    x1 = xs[idx]
    y0 = ys[idx - 1]
    y1 = ys[idx]
    if x1 == x0:
        return y0
    frac = (x_query - x0) / (x1 - x0)
    return y0 + frac * (y1 - y0)


def _monthly_series(xs, ys, boundaries, axis_map):
    if not xs or axis_map is None:
        return {}

    monthly = {}
    for month_name, left_x, right_x in zip(MONTH_NAMES, boundaries[:-1], boundaries[1:]):
        sample_xs = [x_pos for x_pos in xs if left_x <= x_pos <= right_x]
        if len(sample_xs) < 6:
            span = max(right_x - left_x, 1.0)
            sample_xs = [left_x + (span * idx / 15.0) for idx in range(16)]

        values = []
        for x_pos in sample_xs:
            y_pos = _interpolate_y(xs, ys, x_pos)
            if y_pos is None:
                continue
            value = axis_map["slope"] * y_pos + axis_map["intercept"]
            value = max(axis_map["min_value"], min(axis_map["max_value"], value))
            values.append(value)

        monthly[month_name] = round(sum(values) / len(values), 3) if values else None

    return monthly


def digitize_storage_chart_page(pdf_path, page_num):
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num - 1]
        spans = _iter_page_spans(page)
        drawings = page.get_drawings()
        plot_rects = _find_plot_rects(page)
        year_labels = _extract_year_labels(spans)
        if not plot_rects:
            plot_rects = _infer_plot_rects_from_labels(spans, year_labels, page.rect)

        digitized = []
        for rect in plot_rects:
            year_label = _assign_year_label(rect, year_labels)
            if not year_label:
                continue

            left_axis_labels = _axis_labels_for_rect(spans, rect, side="left")
            right_axis_labels = _axis_labels_for_rect(spans, rect, side="right")
            storage_axis = _fit_linear_axis(left_axis_labels)
            outflow_axis = _fit_linear_axis(right_axis_labels)
            boundaries = _month_boundaries(spans, rect)

            year_drawings, normal_drawings, outflow_drawings = _select_curve_groups(drawings, rect)
            year_xs, year_ys = _polyline_points(year_drawings, rect)
            normal_xs, normal_ys = _polyline_points(normal_drawings, rect)
            outflow_xs, outflow_ys = _polyline_points(outflow_drawings, rect)

            digitized.append({
                "year": year_label["year"],
                "plot_rect": [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)],
                "storage_axis_values": storage_axis["tick_values"] if storage_axis else [],
                "outflow_axis_values": outflow_axis["tick_values"] if outflow_axis else [],
                "storage_monthly_Mm3": _monthly_series(year_xs, year_ys, boundaries, storage_axis),
                "normal_monthly_Mm3": _monthly_series(normal_xs, normal_ys, boundaries, storage_axis),
                "outflow_monthly_Mm3": _monthly_series(outflow_xs, outflow_ys, boundaries, outflow_axis),
            })

        return sorted(digitized, key=lambda item: item["year"])
    finally:
        doc.close()


def analyse_schematic_manifest(manifest_data):
    """
    Extract structured topology from a schematic diagram manifest.
    Returns a dict with: stations, infrastructure, river_name, notes
    """
    text_elements = manifest_data.get("text_elements", [])
    pdf_stem = manifest_data.get("pdf_stem", "")
    book = manifest_data.get("book", "")

    stations = []
    infrastructure = []
    river_parts = []
    value_labels = []

    for el in text_elements:
        t = el["text"].strip()
        t_clean = t.rstrip(".,:")
        t_upper = t_clean.upper()

        cx = round((el["x0"] + el["x1"]) / 2, 1)
        cy = round((el["y0"] + el["y1"]) / 2, 1)

        if STATION_PAT.match(t_upper):
            stations.append({
                "code": t_upper,
                "pos_x": cx,
                "pos_y": cy,
                "fontsize": el.get("fontsize", 0),
            })
        elif any(kw in t_upper for kw in INFRA_TYPE_MAP):
            matched_type = next((v for k, v in INFRA_TYPE_MAP.items() if k in t_upper), "infrastructure")
            infrastructure.append({
                "type": matched_type,
                "label": t,
                "pos_x": cx,
                "pos_y": cy,
            })
        elif any(kw in t_upper for kw in RIVER_KEYWORDS):
            river_parts.append(t)
        elif re.match(r"^\d+\.?\d*\s*(km2|ha|mm|m3|Mm3)$", t, re.I):
            value_labels.append({"value": t, "pos_x": cx, "pos_y": cy})

    # Sort stations by Y position (smaller Y = higher on page = upstream)
    stations.sort(key=lambda s: s["pos_y"])

    # Build simple upstream-downstream chain
    topology_chain = []
    for i, st in enumerate(stations):
        node = {
            "code": st["code"],
            "pos_x": st["pos_x"],
            "pos_y": st["pos_y"],
        }
        if i + 1 < len(stations):
            node["likely_downstream"] = stations[i + 1]["code"]
        topology_chain.append(node)

    # Guess river name from labeled text containing river keywords
    river_name = "; ".join(set(river_parts))[:200] if river_parts else None

    return {
        "pdf_stem": pdf_stem,
        "book": book,
        "primary_station": pdf_stem.upper(),
        "river_name_raw": river_name,
        "stations_detected": [s["code"] for s in stations],
        "n_stations": len(stations),
        "topology_chain": topology_chain,
        "infrastructure": infrastructure,
        "value_labels": value_labels,
    }


def analyse_isohyetal_manifest(manifest_data):
    """
    Extract contour values from an isohyetal map manifest.
    Isohyetal line labels are typically numbers like 1000, 1500, 2000, 2500, 3000.
    """
    text_elements = manifest_data.get("text_elements", [])
    book = manifest_data.get("book", "")

    contour_values = []
    for el in text_elements:
        t = el["text"].strip()
        # Match standalone 3-4 digit numbers that look like rainfall mm values
        if re.match(r"^\d{3,4}$", t):
            val = int(t)
            if 500 <= val <= 5000:  # plausible rainfall range for Mauritius
                cx = round((el["x0"] + el["x1"]) / 2, 1)
                cy = round((el["y0"] + el["y1"]) / 2, 1)
                contour_values.append({
                    "value_mm": val,
                    "pos_x": cx,
                    "pos_y": cy,
                    "book": book,
                })

    return {
        "book": book,
        "contour_values_detected": sorted(set(c["value_mm"] for c in contour_values)),
        "contour_annotations": contour_values,
        "n_annotations": len(contour_values),
    }


def analyse_storage_chart_manifest(manifest_data):
    """
    Extract scale information and axis labels from a storage variation chart.
    The charts show Mm3 on the Y-axis; we extract visible numeric labels to
    reconstruct the scale, which is needed for AI chart reading.
    """
    text_elements = manifest_data.get("text_elements", [])
    book = manifest_data.get("book", "")
    pdf_stem = manifest_data.get("pdf_stem", "")
    pdf_path = manifest_data.get("pdf_path", "")
    page_num = manifest_data.get("page_num", 1)

    year_labels = []
    y_axis_values = []

    for el in text_elements:
        t = el["text"].strip()
        # Year labels: 4-digit years 1990-2020
        if re.match(r"^(19|20)\d{2}$", t):
            year_labels.append(int(t))
        # Y-axis values: decimal numbers (storage in Mm3)
        elif re.match(r"^\d+\.?\d*$", t):
            try:
                val = float(t)
                if 0 < val <= 100:  # plausible Mm3 range
                    y_axis_values.append(val)
            except ValueError:
                pass

    digitized_years = []
    if pdf_path and Path(pdf_path).exists():
        digitized_years = digitize_storage_chart_page(pdf_path, page_num)
        for item in digitized_years:
            year_labels.append(item["year"])
            y_axis_values.extend(item.get("storage_axis_values", []))

    return {
        "pdf_stem": pdf_stem,
        "book": book,
        "years_detected": sorted(set(year_labels)),
        "y_axis_values_detected": sorted(set(y_axis_values)),
        "max_storage_Mm3_approx": max(y_axis_values) if y_axis_values else None,
        "digitized_years": digitized_years,
        "n_digitized_years": len(digitized_years),
    }


# ---------------------------------------------------------------------------
# Method 2: OpenAI Vision API (optional)
# ---------------------------------------------------------------------------

def encode_image_b64(image_path):
    """Encode image as base64 string for OpenAI API."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_openai_vision(image_path, prompt, model="vision_extraction"):
    """
    Call OpenAI Vision API to analyse a visual page.
    Requires OPENAI_API_KEY environment variable.
    Returns parsed JSON dict or None on failure.
    """
    try:
        import openai
    except ImportError:
        print("  openai package not installed. Run: pip install openai")
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  OPENAI_API_KEY not set - skipping API call")
        return None

    client = openai.OpenAI(api_key=api_key)
    b64 = encode_image_b64(image_path)
    img_type = "image/png"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{img_type};base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_response": content}
    except Exception as exc:
        print(f"  API error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Method 3: Manual review package
# ---------------------------------------------------------------------------

def save_manual_review_package(manifest_data, text_analysis):
    """
    Save image + prompt + text analysis to the manual_review folder
    so the user can submit to any AI vision tool manually.
    """
    pdf_stem = manifest_data.get("pdf_stem", "unknown")
    book = manifest_data.get("book", "")
    page_num = manifest_data.get("page_num", 1)
    page_type = manifest_data.get("page_type", "unknown")
    prompt = manifest_data.get("ai_prompt", "")
    img_path = manifest_data.get("image_path", "")

    pkg_dir = MANUAL_DIR / book / f"{pdf_stem}_pg{page_num:02d}"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Copy reference to image (don't copy the file to save space)
    readme_content = f"""MANUAL AI REVIEW PACKAGE
========================
Book:       {book}
PDF:        {pdf_stem}
Page:       {page_num}
Type:       {page_type}

IMAGE PATH: {img_path}
(Open this image in any AI vision tool and paste the prompt below)

PROMPT:
-------
{prompt}

TEXT ANALYSIS (automated, may be incomplete):
---------------------------------------------
{json.dumps(text_analysis, indent=2, ensure_ascii=False)}
"""
    with open(pkg_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)

    # Save prompt separately for easy copy-paste
    with open(pkg_dir / "prompt.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    return str(pkg_dir / "README.txt")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract data from visual hydrology PDFs")
    parser.add_argument("--api", action="store_true", help="Call OpenAI Vision API")
    parser.add_argument("--type", help="Only process this page_type (e.g. schematic_diagram)")
    parser.add_argument("--station", help="Only process this station (e.g. A03)")
    parser.add_argument("--book", help="Only process this book (e.g. 2006-2010)")
    args = parser.parse_args()

    if not MANIFEST_INDEX.exists():
        print(f"ERROR: manifest index not found at {MANIFEST_INDEX}")
        print("Run render_visual_pdfs.py first.")
        sys.exit(1)

    df_index = pd.read_csv(MANIFEST_INDEX)
    # Filter to visual pages only
    visual_df = df_index[df_index["is_visual"] == True].copy()

    if args.type:
        visual_df = visual_df[visual_df["page_type"] == args.type]
    if args.station:
        visual_df = visual_df[visual_df["pdf_stem"].str.upper() == args.station.upper()]
    if args.book:
        visual_df = visual_df[visual_df["book"] == args.book]

    print(f"Processing {len(visual_df)} visual pages")
    print(visual_df["page_type"].value_counts().to_string())
    print()

    # Collect results
    schematic_rows = []
    isohyetal_rows = []
    storage_rows = []
    api_results = []

    if args.api:
        API_DIR.mkdir(parents=True, exist_ok=True)

    for _, row in visual_df.iterrows():
        json_path = row.get("json_path", "")
        if not json_path or not Path(json_path).exists():
            print(f"  MISSING manifest: {json_path}")
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        page_type = row["page_type"]
        pdf_stem = row["pdf_stem"]
        book = row["book"]
        print(f"  [{book}] {pdf_stem} p{row['page_num']} ({page_type})", end=" ")

        # --- Method 1: Text analysis
        text_result = {}
        if page_type == "schematic_diagram":
            text_result = analyse_schematic_manifest(manifest)
            schematic_rows.append(text_result)
        elif page_type == "isohyetal_map":
            text_result = analyse_isohyetal_manifest(manifest)
            isohyetal_rows.append(text_result)
        elif page_type == "storage_variation_chart":
            text_result = analyse_storage_chart_manifest(manifest)
            storage_rows.append(text_result)

        n_items = (
            text_result.get("n_stations", 0) or
            text_result.get("n_annotations", 0) or
            text_result.get("n_digitized_years", 0) or
            len(text_result.get("years_detected", []))
        )
        print(f"-> {n_items} items extracted", end="")

        # --- Method 2: OpenAI API (optional)
        if args.api:
            img_path = row.get("image_path", "")
            prompt = manifest.get("ai_prompt", "")
            if img_path and Path(img_path).exists():
                print(f" | calling API...", end="")
                api_result = call_openai_vision(img_path, prompt)
                if api_result:
                    api_out = {
                        "book": book,
                        "pdf_stem": pdf_stem,
                        "page_num": row["page_num"],
                        "page_type": page_type,
                        "response": api_result,
                    }
                    api_results.append(api_out)
                    # Save individual response
                    resp_path = API_DIR / f"{book}_{pdf_stem}_p{row['page_num']:02d}.json"
                    with open(resp_path, "w", encoding="utf-8") as f:
                        json.dump(api_out, f, indent=2)
                    print(f" saved", end="")

        # --- Method 3: Manual review package
        readme = save_manual_review_package(manifest, text_result)
        print(f" | review: {Path(readme).parent.name}")

    # --- Save structured CSVs
    print("\nSaving results...")

    if schematic_rows:
        # Flatten topology to one row per station-pair
        topo_rows = []
        for res in schematic_rows:
            for node in res.get("topology_chain", []):
                topo_rows.append({
                    "book": res["book"],
                    "primary_station": res["primary_station"],
                    "river_name_raw": res.get("river_name_raw"),
                    "station_code": node["code"],
                    "pos_x": node["pos_x"],
                    "pos_y": node["pos_y"],
                    "likely_downstream": node.get("likely_downstream"),
                })
        if topo_rows:
            df_topo = pd.DataFrame(topo_rows)
            out = OUT_DIR / "schematic_topology.csv"
            df_topo.to_csv(out, index=False)
            print(f"  Saved: {out}  ({len(df_topo)} rows)")

    if isohyetal_rows:
        # Flatten contour annotations
        contour_rows = []
        for res in isohyetal_rows:
            for ann in res.get("contour_annotations", []):
                contour_rows.append(ann)
        if contour_rows:
            df_cont = pd.DataFrame(contour_rows)
            out = OUT_DIR / "isohyetal_contours.csv"
            df_cont.to_csv(out, index=False)
            print(f"  Saved: {out}  ({len(df_cont)} rows)")

        # Summary
        for res in isohyetal_rows:
            print(f"  [{res['book']}] Isohyetal contour values detected: {res['contour_values_detected']}")

    if storage_rows:
        df_stor = pd.DataFrame([{
            "pdf_stem": row["pdf_stem"],
            "book": row["book"],
            "years_detected": json.dumps(row.get("years_detected", [])),
            "y_axis_values_detected": json.dumps(row.get("y_axis_values_detected", [])),
            "max_storage_Mm3_approx": row.get("max_storage_Mm3_approx"),
            "n_digitized_years": row.get("n_digitized_years", 0),
        } for row in storage_rows])
        out = OUT_DIR / "storage_chart_scale.csv"
        df_stor.to_csv(out, index=False)
        print(f"  Saved: {out}  ({len(df_stor)} rows)")

        monthly_rows = []
        for res in storage_rows:
            for year_data in res.get("digitized_years", []):
                for month_name in MONTH_NAMES:
                    monthly_rows.append({
                        "book": res["book"],
                        "pdf_stem": res["pdf_stem"],
                        "year": year_data["year"],
                        "month": month_name,
                        "storage_Mm3": year_data.get("storage_monthly_Mm3", {}).get(month_name),
                        "normal_Mm3": year_data.get("normal_monthly_Mm3", {}).get(month_name),
                        "outflow_Mm3": year_data.get("outflow_monthly_Mm3", {}).get(month_name),
                    })
        if monthly_rows:
            df_monthly = pd.DataFrame(monthly_rows)
            out = OUT_DIR / "storage_chart_monthly.csv"
            df_monthly.to_csv(out, index=False)
            print(f"  Saved: {out}  ({len(df_monthly)} rows)")

    if api_results:
        df_api = pd.DataFrame([{
            "book": r["book"],
            "pdf_stem": r["pdf_stem"],
            "page_type": r["page_type"],
            "response_path": str(API_DIR / f"{r['book']}_{r['pdf_stem']}_p{r['page_num']:02d}.json"),
        } for r in api_results])
        out = API_DIR / "api_results_index.csv"
        df_api.to_csv(out, index=False)
        print(f"  Saved: {out}  ({len(df_api)} API responses)")

    print(f"\nManual review packages saved to: {MANUAL_DIR}")
    print("To submit for AI analysis:")
    print("  1. Open each image file listed in the README.txt files")
    print("  2. Copy the prompt from prompt.txt")
    print("  3. Paste into any AI vision tool (Vision-Extract, Topology-Review, Vision-Extract)")
    print("  4. Save the JSON response alongside the README.txt")
    print()
    print("Or set OPENAI_API_KEY and re-run with --api flag for automated processing.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
