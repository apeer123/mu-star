"""
extract_grse_flow_tables.py
============================
Extracts monthly flow tables from Hydrology Data Book Chapter 3 PDFs for all
GRSE E-series stations, outputting one CSV per station per book in the schema:

    station_id | book | year | month | volume_Mm3 | mean_m3s | max_m3s | min_m3s

Canonical station_id mapping (zero-padding normalised, locks E13/E013 apart).
Run:
    python extract_grse_flow_tables.py --images-dir <images_dir> --pdf-dir <pdf_dir> --output-dir <output_dir>
Output folder:
    (Provided via --output-dir argument)
"""

import argparse
import os
import re
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
IMAGES_ROOT = Path("../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book/Images").resolve()
PDF_ROOT     = Path(".")
OUTPUT_DIR   = Path(".")

# ---------------------------------------------------------------------------
# Canonical ID map  (raw_code -> canonical station_id)
# Locked pairs: E13 != E013 by design (C3 self-loop prevention)
#               E15 != E15a by design (different network class)
# ---------------------------------------------------------------------------
CANONICAL_ID: dict[str, str] = {
    # 2006-2010 zero-padded codes -> canonical
    "E008a":  "E08a",
    "E008b":  "E08b",
    "E008c":  "E08c",
    "E010":   "E010",   # kept as E010 (NOT E10) to stay distinct from E01
    "E014":   "E014",
    "E015":   "E015",
    "E015a":  "E015a",
    "E016":   "E016",
    "E020":   "E020",
    # 2000-2005 short codes -> canonical (same target ids)
    "E08a":   "E08a",
    "E08b":   "E08b",
    "E08c":   "E08c",
    "E14":    "E014",
    "E15":    "E015",
    "E15a":   "E015a",
    "E16":    "E016",
    "E20":    "E020",
    # Shared codes (identical across books)
    "E01":    "E01",
    "E04":    "E04",
    "E05":    "E05",
    "E06":    "E06",
    "E07":    "E07",
    "E11":    "E11",
    "E12":    "E12",
    # LOCKED APART — never merge E13 and E013
    "E13":    "E13",
    "E013":   "E013",
    # EF series
    "EF01":   "EF01",
    "EF02":   "EF02",
}

# ---------------------------------------------------------------------------
# FlowExtractionConfig
# ---------------------------------------------------------------------------
@dataclass
class FlowExtractionConfig:
    raw_code:     str
    basin:        str
    book:         str          # "2006-2010" or "2000-2005"
    page_numbers: list[int]
    table_settings: dict = field(default_factory=lambda: {
        "vertical_strategy":   "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance":      4,
        "join_tolerance":      4,
    })
    notes: str = ""

    @property
    def station_id(self) -> str:
        return CANONICAL_ID.get(self.raw_code, self.raw_code)

    @property
    def image_folder(self) -> Path:
        return (IMAGES_ROOT / self.book / "Chapter 3"
                / "Schematic Diagrams and Flow Data" / self.raw_code)

    @property
    def pdf_path(self) -> Optional[Path]:
        """
        Locate the source PDF. PDFs use 2006-2010 zero-padded names (E008a.pdf, not E08a.pdf).
        Try raw_code first, then canonical_id, then the zero-padded cross-book equivalent.
        """
        # Zero-padding map: 2000-2005 short codes -> 2006-2010 PDF filename
        _SHORT_TO_PDF = {
            "E08a": "E008a", "E08b": "E008b", "E08c": "E008c",
            "E14":  "E014",  "E15":  "E015",  "E15a": "E015a",
            "E16":  "E016",  "E20":  "E020",
        }
        for code in [self.raw_code, _SHORT_TO_PDF.get(self.raw_code, ""), self.station_id]:
            if code:
                p = PDF_ROOT / f"{code}.pdf"
                if p.exists():
                    return p
        return None


# ---------------------------------------------------------------------------
# Config list — page numbers auto-populated from image folder scan
# ---------------------------------------------------------------------------
_G = {"vertical_strategy": "lines", "horizontal_strategy": "lines",
      "snap_tolerance": 4, "join_tolerance": 4}

GRSE_FLOW_CONFIGS: list[FlowExtractionConfig] = [
    # Rempart / St-Martin -> E01 -> E12 -> GRSE
    FlowExtractionConfig("E016",  "GRSE", "2006-2010", []),           # backfill only
    FlowExtractionConfig("E01",   "GRSE", "2006-2010", [1, 2, 3, 4], _G),
    FlowExtractionConfig("E01",   "GRSE", "2000-2005", [1, 2, 3, 4], _G),
    FlowExtractionConfig("E12",   "GRSE", "2006-2010", [1],           _G),
    FlowExtractionConfig("E12",   "GRSE", "2000-2005", [1],           _G),
    # Direct GRSE main-stem tributaries
    FlowExtractionConfig("E04",   "GRSE", "2006-2010", [1],           _G, notes="needs_human_review"),
    FlowExtractionConfig("E04",   "GRSE", "2000-2005", [1],           _G, notes="needs_human_review"),
    FlowExtractionConfig("E05",   "GRSE", "2006-2010", [1],           _G),
    FlowExtractionConfig("E05",   "GRSE", "2000-2005", [1],           _G),
    FlowExtractionConfig("E06",   "GRSE", "2006-2010", [1],           _G),
    FlowExtractionConfig("E06",   "GRSE", "2000-2005", [1],           _G),
    FlowExtractionConfig("E07",   "GRSE", "2006-2010", [1, 2, 3, 4], _G),
    FlowExtractionConfig("E07",   "GRSE", "2000-2005", [1, 2, 3, 4], _G),
    # Bel Air / Anse Cunat terminal chain
    FlowExtractionConfig("E010",  "GRSE", "2006-2010", [1],           _G),
    FlowExtractionConfig("E11",   "GRSE", "2006-2010", [1, 2, 3],     _G),
    FlowExtractionConfig("E11",   "GRSE", "2000-2005", [1, 2, 3],     _G),
    FlowExtractionConfig("E13",   "GRSE", "2006-2010", [1, 2, 3],     _G),  # LOCKED: E13 != E013
    FlowExtractionConfig("E13",   "GRSE", "2000-2005", [1, 2, 3],     _G),  # LOCKED: E13 != E013
    FlowExtractionConfig("E013",  "GRSE", "2006-2010", [1],           _G, notes="terminal outfall"),
    FlowExtractionConfig("E013",  "GRSE", "2000-2005", [1],           _G, notes="terminal outfall"),
    # River Francoise sub-network
    FlowExtractionConfig("E014",  "GRSE", "2006-2010", [1],           _G),
    FlowExtractionConfig("E14",   "GRSE", "2000-2005", [1],           _G),
    FlowExtractionConfig("E015",  "GRSE", "2006-2010", []),           # backfill only (E015 = E15 index code)
    FlowExtractionConfig("E015a", "GRSE", "2006-2010", [1],           _G, notes="feeder canal"),
    FlowExtractionConfig("E15a",  "GRSE", "2000-2005", [1],           _G, notes="feeder canal"),
    # Nicoliere feeder/reservoir cascade
    FlowExtractionConfig("E008a", "GRSE", "2006-2010", [1, 2, 3, 4], _G),
    FlowExtractionConfig("E08a",  "GRSE", "2000-2005", [1, 2, 3, 4], _G),
    FlowExtractionConfig("E008b", "GRSE", "2006-2010", [1, 2, 3],     _G),
    FlowExtractionConfig("E08b",  "GRSE", "2000-2005", [1, 2, 3],     _G),
    FlowExtractionConfig("E008c", "GRSE", "2006-2010", [1, 2, 3],     _G, notes="level/stage station"),
    FlowExtractionConfig("E08c",  "GRSE", "2000-2005", [1, 2, 3],     _G, notes="level/stage station"),
    FlowExtractionConfig("E020",  "GRSE", "2006-2010", [1],           _G, notes="level/stage station"),
    FlowExtractionConfig("E20",   "GRSE", "2000-2005", [1],           _G, notes="level/stage station"),
]

# ---------------------------------------------------------------------------
# Word-position parser for Mauritius Hydrology Book Chapter 3 layout
# ---------------------------------------------------------------------------
# Layout per water-year block:
#   Month headers at y_nov:  NOV DEC JAN FEB MAR APR MAY JUN JUL AUG SEP OCT YEAR  (x≈150–535)
#   Year label (rotated 90°) at x≈55, individual chars top→bottom, reversed = "YEAR:YYYY/YY"
#   Metric labels at x≈72:  Volume, Mean, Max, Min  (each on its own row)
#   Data values at x≈150–535 aligned to month column x-positions
# ---------------------------------------------------------------------------
_MONTH_ABBREV: dict[str, str] = {
    "NOV": "Nov", "DEC": "Dec", "JAN": "Jan", "FEB": "Feb",
    "MAR": "Mar", "APR": "Apr", "MAY": "May", "JUN": "Jun",
    "JUL": "Jul", "AUG": "Aug", "SEP": "Sep", "OCT": "Oct",
}
_MONTH_ORDER = ["NOV", "DEC", "JAN", "FEB", "MAR", "APR",
                "MAY", "JUN", "JUL", "AUG", "SEP", "OCT"]


def _decode_year(chars_top_to_bottom: list[str]) -> str:
    """Decode rotated year label.  top→bottom join then reverse → 'YEAR:1999/00'."""
    decoded = "".join(chars_top_to_bottom)[::-1]
    m = re.search(r'(\d{4}/\d{2})', decoded)
    return m.group(1) if m else decoded.strip()


def _parse_page_by_words(page, config: "FlowExtractionConfig",
                         page_num: int) -> list[dict]:
    """
    Parse one PDF page using extract_words() coordinates.
    Handles the rotated-year + merged-month-header table layout.
    Returns one dict per (year, month) with volume/mean/max/min.
    """
    words = page.extract_words()
    if not words:
        return _ocr_required_rows(config, page_num=page_num)

    # Year-block boundaries: each block starts at a NOV header occurrence
    nov_ys = sorted(w["top"] for w in words if w["text"].upper() == "NOV")
    if not nov_ys:
        return []   # schematic / non-flow page

    page_bottom = float(page.height)
    rows: list[dict] = []

    for idx, nov_y in enumerate(nov_ys):
        block_top = nov_y - 5.0
        block_bot = (nov_ys[idx + 1] - 5.0
                     if idx + 1 < len(nov_ys) else page_bottom)
        bw = [w for w in words if block_top <= w["top"] <= block_bot]

        # 1. Month header x-positions (within ±12px of nov_y)
        month_x: dict[str, float] = {}
        for w in bw:
            key = w["text"].upper()
            if key in _MONTH_ABBREV and abs(w["top"] - nov_y) < 12:
                month_x[key] = w["x0"]
        if not month_x:
            continue

        # 2. Year label: single/short tokens at x<65, top→bottom then reversed
        year_chars = sorted(
            [w for w in bw if w["x0"] < 65 and 0 < len(w["text"]) <= 2],
            key=lambda w: w["top"]
        )
        year_str = _decode_year([w["text"] for w in year_chars])

        # 3. Metric row y-positions (labels at x<105)
        metric_ys: dict[str, float] = {}
        for w in bw:
            t = w["text"].lower()
            if w["x0"] > 105:
                continue
            if t == "volume":
                metric_ys["volume"] = w["top"]
            elif t == "mean":
                metric_ys["mean"] = w["top"]
            elif t == "max":
                metric_ys.setdefault("max", w["top"])
            elif t == "min":
                metric_ys.setdefault("min", w["top"])

        # 4. Collect values for each metric (data words at x>120, within ±8px of row y)
        X_TOL, Y_TOL = 20.0, 8.0

        def _vals_for_y(row_y: float) -> dict[str, Optional[float]]:
            row_words = [w for w in bw
                         if abs(w["top"] - row_y) < Y_TOL and w["x0"] > 120.0]
            result: dict[str, Optional[float]] = {}
            for mk, cx in month_x.items():
                cands = [w for w in row_words if abs(w["x0"] - cx) < X_TOL]
                if cands:
                    best = min(cands, key=lambda w: abs(w["x0"] - cx))
                    result[mk] = _safe_float(best["text"])
                else:
                    result[mk] = None
            return result

        vol_vals  = _vals_for_y(metric_ys["volume"]) if "volume" in metric_ys else {}
        mean_vals = _vals_for_y(metric_ys["mean"])   if "mean"   in metric_ys else {}
        max_vals  = _vals_for_y(metric_ys["max"])    if "max"    in metric_ys else {}
        min_vals  = _vals_for_y(metric_ys["min"])    if "min"    in metric_ys else {}

        # 5. Emit one row per month in hydrological year order
        for mk in _MONTH_ORDER:
            if mk not in month_x:
                continue
            rows.append({
                "station_id":   config.station_id,
                "raw_code":     config.raw_code,
                "book":         config.book,
                "year":         year_str,
                "month":        _MONTH_ABBREV[mk],
                "volume_Mm3":   vol_vals.get(mk),
                "mean_m3s":     mean_vals.get(mk),
                "max_m3s":      max_vals.get(mk),
                "min_m3s":      min_vals.get(mk),
                "source_page":  page_num,
                "notes":        config.notes,
                "ocr_required": False,
            })

    return rows

def _safe_float(val: str) -> Optional[float]:
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None

# ---------------------------------------------------------------------------
# pdfplumber extraction
# ---------------------------------------------------------------------------
def extract_flow_table(config: FlowExtractionConfig) -> list[dict]:
    """
    Extract monthly flow rows from a single station's PDF pages.
    Returns list of row dicts: station_id, book, year, month,
    volume_Mm3, mean_m3s, max_m3s, min_m3s.
    Falls back to OCR_REQUIRED marker if the page is a scanned image with
    no extractable text layer.
    """
    try:
        import pdfplumber
    except ImportError:
        print("pdfplumber not installed. Run: pip install pdfplumber")
        return []

    if not config.page_numbers:
        return []  # backfill-only station, no PDF page

    pdf_path = config.pdf_path
    if pdf_path is None:
        print(f"  [WARN] No PDF found for {config.raw_code} ({config.book})")
        return _ocr_required_rows(config)

    rows: list[dict] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num in config.page_numbers:
            if page_num > len(pdf.pages):
                continue
            page = pdf.pages[page_num - 1]  # pdfplumber is 0-indexed

            # Scanned page check (text layer required)
            text = page.extract_text() or ""
            if len(text.strip()) < 30:
                rows.extend(_ocr_required_rows(config, page_num=page_num))
                continue
            rows.extend(_parse_page_by_words(page, config, page_num))

    return rows


def _ocr_required_rows(config: FlowExtractionConfig,
                        page_num: Optional[int] = None) -> list[dict]:
    """Placeholder rows indicating manual OCR is needed."""
    return [{
        "station_id":  config.station_id,
        "raw_code":    config.raw_code,
        "book":        config.book,
        "year":        "OCR_REQUIRED",
        "month":       "OCR_REQUIRED",
        "volume_Mm3":  None,
        "mean_m3s":    None,
        "max_m3s":     None,
        "min_m3s":     None,
        "source_page": page_num,
        "notes":       config.notes,
        "ocr_required": True,
    }]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
SCHEMA = ["station_id", "raw_code", "book", "year", "month",
          "volume_Mm3", "mean_m3s", "max_m3s", "min_m3s",
          "source_page", "notes", "ocr_required"]


def build_grse_csv() -> None:
    """
    Loop all configs, extract flow rows, write:
      - One CSV per station_id (canonical):
          grse_flow_{station_id}.csv
      - One consolidated GRSE master CSV:
          grse_flow_ALL.csv
    """
    all_rows: list[dict] = []
    per_station: dict[str, list[dict]] = {}

    configs_with_pages = [c for c in GRSE_FLOW_CONFIGS if c.page_numbers]
    print(f"Processing {len(configs_with_pages)} configs "
          f"({len(GRSE_FLOW_CONFIGS) - len(configs_with_pages)} skipped — "
          f"backfill-only / no pages)")

    for cfg in configs_with_pages:
        print(f"  {cfg.raw_code:8} ({cfg.book}) pages={cfg.page_numbers}", end=" ... ")
        rows = extract_flow_table(cfg)
        print(f"{len(rows)} rows")
        all_rows.extend(rows)
        sid = cfg.station_id
        per_station.setdefault(sid, []).extend(rows)

    # Write per-station CSVs
    for sid, rows in per_station.items():
        out_path = OUTPUT_DIR / f"grse_flow_{sid}.csv"
        _write_csv(out_path, rows)
        print(f"  -> {out_path.name}  ({len(rows)} rows)")

    # Write master
    master_path = OUTPUT_DIR / "grse_flow_ALL.csv"
    _write_csv(master_path, all_rows)
    print(f"\nMaster CSV: {master_path}  ({len(all_rows)} total rows)")

    # Write OCR report
    ocr_rows = [r for r in all_rows if r.get("ocr_required")]
    if ocr_rows:
        ocr_path = OUTPUT_DIR / "grse_flow_OCR_REQUIRED.csv"
        _write_csv(ocr_path, ocr_rows)
        print(f"OCR-required pages: {ocr_path.name}  ({len(ocr_rows)} entries)")
    else:
        print("No OCR-required pages detected.")


def _write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCHEMA, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def test_pdfs():
    """Quick diagnostic — run with: python extract_grse_flow_tables.py --test"""
    test_codes = ["E01", "E008a", "E013", "E07"]
    for code in test_codes:
        p = PDF_ROOT / f"{code}.pdf"
        if not p.exists():
            print(f"NOT FOUND: {code}.pdf")
            continue
        import pdfplumber
        print(f"\n{'='*55}\nPDF: {code}.pdf")
        with pdfplumber.open(str(p)) as pdf:
            print(f"  Total pages: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                tables = page.extract_tables()
                print(f"  Page {i}: text_chars={len(text):5d}  tables={len(tables)}", end="")
                if text.strip():
                    print(f"  | {text.strip().replace(chr(10),' ')[:80]}")
                else:
                    print("  | [NO TEXT — scanned image / OCR required]")
                for table in tables[:1]:
                    if table:
                        print(f"    Headers: {[str(c).strip()[:15] if c else '' for c in table[0]]}")
                        for row in table[1:3]:
                            print(f"    Row:     {[str(c).strip()[:15] if c else '' for c in row]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract GRSE Flow Tables")
    parser.add_argument("--images-dir", type=str, default=str(IMAGES_ROOT), help="Path to Images root directory")
    parser.add_argument("--pdf-dir", type=str, default=str(PDF_ROOT), help="Path to PDF root directory")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR), help="Path to output directory")
    parser.add_argument("--test", action="store_true", help="Run quick diagnostic test")
    args = parser.parse_args()

    IMAGES_ROOT = Path(args.images_dir)
    PDF_ROOT = Path(args.pdf_dir)
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.test:
        test_pdfs()
    else:
        build_grse_csv()
