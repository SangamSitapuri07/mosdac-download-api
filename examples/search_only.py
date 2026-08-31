#!/usr/bin/env python3
"""
Example: MOSDAC Search API - bina login ke dataset khojna / API test karna.

Usage:
    python3 examples/search_only.py
    python3 examples/search_only.py 3SIMG_L1B_STD 2025-01-01 2025-01-02 5
"""

import sys
import json
import requests

SEARCH_URL = "https://mosdac.gov.in/apios/datasets.json"


def main():
    dataset_id = sys.argv[1] if len(sys.argv) > 1 else "3RIMG_L2B_SST"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2024-01-02"
    count = sys.argv[4] if len(sys.argv) > 4 else "5"

    params = {"datasetId": dataset_id, "startTime": start, "endTime": end, "count": count}
    print("GET", SEARCH_URL)
    print("params:", params, "\n")

    r = requests.get(SEARCH_URL, params=params, timeout=60)
    print("HTTP status:", r.status_code)

    if r.status_code != 200:
        print("Response:", r.text[:500])
        return 1

    data = r.json()
    print(f"totalResults : {data.get('totalResults')}")
    print(f"totalSizeMB  : {data.get('totalSizeMB')}")
    print(f"itemsPerPage : {data.get('itemsPerPage')}\n")

    print("Pehli kuch files (id = download ke liye chahiye):")
    for e in data.get("entries", [])[:5]:
        print(f"  - {e.get('identifier')}  id={e.get('id')}  updated={e.get('updated')}")

    print("\nRaw JSON (pehla entry):")
    entries = data.get("entries") or []
    if entries:
        print(json.dumps(entries[0], indent=2)[:900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
