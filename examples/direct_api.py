#!/usr/bin/env python3
"""
Example: MOSDAC API ko apne code se DIRECT use karo (mdapi.py ke bina).

    python examples/direct_api.py

Credentials .env se padhe jate hain (MOSDAC_USER / MOSDAC_PASS).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mosdac_client import Mosdac, MosdacError  # noqa: E402


def main():
    m = Mosdac()  # .env ya env vars se credentials

    # ---- 1. SEARCH (bina login ke bhi chalta hai) ----
    print("--- Search (no login needed) ---")
    res = m.search("3RIMG_L2B_SST", "2026-09-01", "2026-09-01", count=5)
    print(f"total files : {res['total']}")
    print(f"total size  : {res['total_size_mb']} MB")
    for e in res["entries"]:
        print(f"  - {e['identifier']}  id={e['id']}  {e['updated']}")

    if not res["entries"]:
        print("koi file nahi mila")
        return 0

    first = res["entries"][0]

    # ---- 2. LOGIN ----
    print("\n--- Login ---")
    try:
        m.login()
        print("login OK, token mil gaya")
    except MosdacError as e:
        print("login fail:", e)
        return 1

    # ---- 3. DOWNLOAD seedha MEMORY me (disk pe save nahi) ----
    print("\n--- Download in memory ---")
    try:
        data = m.download_bytes(first["id"])
        print(f"{first['identifier']}: {len(data)/1024/1024:.2f} MB RAM me aa gaya")

        # ab is `data` (bytes) ke saath kuch bhi kar sakte ho
        # jaise h5py se padhna:
        #   import h5py, io
        #   f = h5py.File(io.BytesIO(data), 'r')
        #   print(list(f.keys()))
    except MosdacError as e:
        print("download fail:", e)
        return 1

    # ---- 4. Ya file me save karna ho to ----
    print("\n--- Save to disk ---")
    out = Path("data") / first["identifier"]
    path = m.download_file(first["id"], out)
    print("saved:", path)

    # ---- 5. Streaming (badi files ke liye, RAM bachane ko) ----
    print("\n--- Streaming (chunk-wise) ---")
    total = 0
    for chunk in m.download_stream(first["id"]):
        total += len(chunk)
    print(f"streamed {total/1024/1024:.2f} MB")

    m.logout()
    print("\nDone. Logged out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
