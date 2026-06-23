"""
Extract the Chapter 3 river gauging station index from both Hydrology Data Books.

The PDF is text-like rather than a machine-readable table, so this parser:
  - merges wrapped lines
  - detects each station entry by serial number + station code
  - separates station name/location, type/equipment, previous number, and remarks

Outputs written to extracted_river_gauging/:
  river_gauging_stations_index.csv
  river_gauging_station_parse_issues.csv
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber


BOOKS = {
    "2006-2010": Path(Path("../Incoming Data/Natural/Hydrology/Mauritius Hydrology Book").resolve()),
    "2000-2005": Path("."),
}

OUT_DIR = Path(
    "."
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENTRY_RE = re.compile(
    r"^(?P<serial_no>\d+)\s+"
    r"(?P<station_code>[A-Z]+\d+[A-Za-z]*)\s+"
    r"(?P<station_name_location>.+?)\s+"
    r"(?P<type_equipment>(?:Reg\.|Occ\.|Aband\.)(?:\s+[A-Z.]+)?)\s*"
    r"(?P<trail>.*)$"
)


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def repair_common_ocr_noise(line):
    repairs = {
        ")Reg.": ") Reg.",
        "SAtbna.)nd.": "Station) Aband.",
        "SecAtiobnand.": "Section Aband.",
    }
    for bad, good in repairs.items():
        line = line.replace(bad, good)
    return line


def merge_wrapped_lines(page_text):
    merged = []
    current = None

    for raw_line in (page_text or "").split("\n"):
        line = repair_common_ocr_noise(clean_text(raw_line))
        if not line:
            continue
        if line.startswith("TABLE 3.2") or line.startswith("Type &") or line.startswith("Equipment"):
            continue
        if line.startswith("S.N ") or line.startswith("S.N Station"):
            continue

        if re.match(r"^\d+\s+[A-Z]+\d+[A-Za-z]*\s+", line):
            if current:
                merged.append(current)
            current = line
        elif current:
            current = f"{current} {line}"

    if current:
        merged.append(current)

    return merged


def split_status(type_equipment):
    parts = clean_text(type_equipment).split(None, 1)
    status = parts[0] if parts else None
    equipment = parts[1] if len(parts) > 1 else None
    return status, equipment


def split_previous_and_remarks(trail):
    trail = clean_text(trail)
    if not trail:
        return None, None

    tokens = trail.split()
    previous_tokens = []
    index = 0
    while index < len(tokens):
        token = tokens[index].strip(",.;")
        if token and not re.search(r"[a-z]", token):
            previous_tokens.append(tokens[index].strip(","))
            index += 1
        else:
            break

    previous_no = " ".join(previous_tokens) if previous_tokens else None
    remarks = " ".join(tokens[index:]).strip() or None
    return previous_no, remarks


def parse_pdf(pdf_path, book_label):
    records = []
    issues = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for line in merge_wrapped_lines(page.extract_text() or ""):
                match = ENTRY_RE.match(line)
                if not match:
                    issues.append({
                        "book": book_label,
                        "page_num": page_num,
                        "raw_line": line,
                    })
                    continue

                row = match.groupdict()
                status, equipment = split_status(row["type_equipment"])
                previous_no, remarks = split_previous_and_remarks(row["trail"])
                records.append({
                    "book": book_label,
                    "page_num": page_num,
                    "serial_no": int(row["serial_no"]),
                    "station_code": row["station_code"],
                    "station_name_location": clean_text(row["station_name_location"]),
                    "status": status,
                    "equipment": equipment,
                    "type_equipment": clean_text(row["type_equipment"]),
                    "previous_no": previous_no,
                    "remarks": remarks,
                    "raw_line": line,
                })

    return records, issues


def main():
    all_records = []
    all_issues = []

    for book_label, base_dir in BOOKS.items():
        pdf_path = base_dir / "Chapter 3" / "River Gauging Stations.pdf"
        if not pdf_path.exists():
            print(f"MISSING: {pdf_path}")
            continue

        records, issues = parse_pdf(pdf_path, book_label)
        all_records.extend(records)
        all_issues.extend(issues)

    df_records = pd.DataFrame(all_records, columns=[
        "book", "page_num", "serial_no", "station_code", "station_name_location",
        "status", "equipment", "type_equipment", "previous_no", "remarks", "raw_line",
    ]).sort_values(["book", "serial_no"])
    df_issues = pd.DataFrame(all_issues, columns=["book", "page_num", "raw_line"])

    out_records = OUT_DIR / "river_gauging_stations_index.csv"
    out_issues = OUT_DIR / "river_gauging_station_parse_issues.csv"
    df_records.to_csv(out_records, index=False)
    df_issues.to_csv(out_issues, index=False)

    print(f"Saved: {out_records} ({len(df_records)} rows)")
    print(f"Saved: {out_issues} ({len(df_issues)} issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())