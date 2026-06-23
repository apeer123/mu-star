"""
Download all PDFs from the Mauritius Hydrology Data Book 2000-2005.

URL base: https://publicutilities.govmu.org/Documents/2020/Legislation/Water/
          Hydrology%20Data%20Book/Book%202000-2005/
Output:   Downloads/Hydrology_Data_Book_2000_2005/
"""

import requests
import time
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_URL = "https://publicutilities.govmu.org"
OUT_DIR = Path(".")

# All 75 PDFs discovered from the 2000-2005 book page
PDF_PATHS = [
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%201/INTRODUCTION.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%202/Isohyetal%20maps.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%202/Precipitation%20data.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%202/Rainfall%20Stations.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%202/Rainfall%20data.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Flow%20Data%20on%20Rivers%20and%20Canals.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Map%20Drainage%20areas%20%26%20stations.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/River%20Gauging%20Stations.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/A03.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/B01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/D01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E008a.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E008b.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E008c.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E013.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E014.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E015a.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E020.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E04.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E05.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E06.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E07.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E11.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E12.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/E13.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/G09.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/H02.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/J001.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/J01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/J04.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/L01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/M01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/N03.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/P01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/Q01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/R01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/S07.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/T02.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/U04.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/U05.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/W013.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/W018b.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/W019.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/W03.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/W04.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/W05.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/W08.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/Y01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/Y02a.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/ZA01.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Schematic%20Diagrams%20and%20Flow%20Data/totgrse.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Stations%20data%20provided.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/Stations%20on%20Diversions.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%203/descriptive%20notes%20on%20hydrology.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%204/Brief%20Description%20groundwater.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%204/Small%20well%20characteristics.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%204/Well%20characteristics.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%205/Brief%20Description%20Reservoirs.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%205/Salient%20Features%2c%20Storage%20variation/La%20Ferme.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%205/Salient%20Features%2c%20Storage%20variation/Mare%20Aux%20Vacoas.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%205/Salient%20Features%2c%20Storage%20variation/Mare%20Longue.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%205/Salient%20Features%2c%20Storage%20variation/Midlands.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%205/Salient%20Features%2c%20Storage%20variation/Nicoliere.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%205/Salient%20Features%2c%20Storage%20variation/Piton%20Du%20Milieu.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%206/Water%20quality.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%207/Agalega.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%207/Brief%20Description%20Rod%26Aga.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%207/Geological%20Map%20Rodrigues.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%207/Rodrigues%20well%20characteristics.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Chapter%207/drainage%20areas%20Rodrigues.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Glossary.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/Staff%20List.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/minister%20message+foreword.pdf",
    "/Documents/2020/Legislation/Water/Hydrology%20Data%20Book/Book%202000-2005/table%20of%20contents.pdf",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def url_path_to_local(server_path: str) -> Path:
    """Convert server path like /Documents/.../Chapter 2/Isohyetal maps.pdf
    to a local path under OUT_DIR, stripping the Book 2000-2005 prefix."""
    decoded = unquote(server_path)
    # Strip leading /Documents/.../Book 2000-2005/
    prefix = "/Documents/2020/Legislation/Water/Hydrology Data Book/Book 2000-2005/"
    rel = decoded.replace(prefix, "")
    return OUT_DIR / Path(rel)


def download_pdf(server_path: str, session: requests.Session, retries: int = 3) -> bool:
    url = BASE_URL + server_path
    local_path = url_path_to_local(server_path)

    if local_path.exists() and local_path.stat().st_size > 0:
        print(f"  [SKIP] {local_path.relative_to(OUT_DIR)}")
        return True

    local_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30, stream=True)
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            size_kb = local_path.stat().st_size // 1024
            print(f"  [OK ] {local_path.relative_to(OUT_DIR)}  ({size_kb} KB)")
            return True
        except Exception as exc:
            print(f"  [ERR] attempt {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(2 ** attempt)

    print(f"  [FAIL] {server_path}")
    return False


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    total = len(PDF_PATHS)
    ok = 0
    fail = []

    print(f"Downloading {total} PDFs to: {OUT_DIR}")
    print("=" * 60)

    for i, path in enumerate(PDF_PATHS, 1):
        print(f"[{i:02d}/{total}]", end=" ")
        success = download_pdf(path, session)
        if success:
            ok += 1
        else:
            fail.append(path)
        time.sleep(0.3)

    print("\n" + "=" * 60)
    print(f"Done: {ok}/{total} downloaded successfully.")
    if fail:
        print(f"Failed ({len(fail)}):")
        for f in fail:
            print(f"  {f}")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
