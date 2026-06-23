"""Scrape PDF links from both Hydrology Data Book pages."""
import requests, re, sys

BASE = "https://publicutilities.govmu.org"
URLS = {
    "2006-2010": f"{BASE}/Pages/Hydrology-Data-Book-2006-2010.aspx",
    "2000-2005": f"{BASE}/Pages/Hydrology-Data-Book-2000-2005.aspx",
}
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

for label, url in URLS.items():
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        html = resp.text
        links = re.findall(r'href=["\'](/[Dd]ocuments[^"\']+\.pdf)', html, re.IGNORECASE)
        print(f"\n=== {label} ({len(links)} PDF links) ===")
        for lnk in sorted(set(links)):
            print(" ", lnk)
    except Exception as e:
        print(f"ERROR {label}: {e}", file=sys.stderr)
