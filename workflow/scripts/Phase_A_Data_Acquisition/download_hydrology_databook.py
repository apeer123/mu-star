"""
Download all PDFs from the Mauritius Hydrology Data Book 2006-2010.

Usage:
    python download_hydrology_databook.py \
        --links data/hydrology-data-book.links.txt \
        --outdir processed_data/Hydrology_Data_Book

Tom's instruction: script the data extraction where possible.
"""

import argparse
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

# Base URL prefix to strip when building local folder structure
BASE_URL = (
    "https://publicutilities.govmu.org/Documents/2020/Legislation/Water/"
    "Hydrology%20Data%20Book/Book/Book/"
)


def url_to_local_path(url: str, outdir: Path) -> Path:
    """Convert a remote URL to a mirrored local path under outdir."""
    # Decode percent-encoding for path construction
    decoded = unquote(url)
    base_decoded = unquote(BASE_URL)
    if decoded.startswith(base_decoded):
        relative = decoded[len(base_decoded):]
    else:
        # Fallback: use the last part of the URL path
        relative = unquote(urlparse(url).path.split("/")[-1])
    return outdir / relative.replace("/", "\\")


def download_file(url: str, dest: Path, session: requests.Session) -> bool:
    """Download a single URL to dest. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  [SKIP] {dest.name} (already exists)")
        return True
    try:
        resp = session.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        print(f"  [OK]   {dest.relative_to(dest.parents[2])} ({dest.stat().st_size // 1024} KB)")
        return True
    except Exception as exc:
        print(f"  [FAIL] {url}  →  {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download Hydrology Data Book PDFs")
    parser.add_argument(
        "--links",
        required=True,
        help="Path to the .txt file with one URL per line",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Root output directory",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between requests (be polite to the server)",
    )
    args = parser.parse_args()

    links_path = Path(args.links)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    urls = [
        line.strip()
        for line in links_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    print(f"Found {len(urls)} URLs to download → {outdir}")

    session = requests.Session()
    session.headers.update({"User-Agent": "MSTAR-research/1.0"})

    ok, fail = 0, 0
    for url in urls:
        dest = url_to_local_path(url, outdir)
        if download_file(url, dest, session):
            ok += 1
        else:
            fail += 1
        time.sleep(args.delay)

    print(f"\nDone. {ok} downloaded, {fail} failed.")
    if fail:
        print("Re-run the script to retry failed downloads (they will be skipped if already saved).")


if __name__ == "__main__":
    main()
