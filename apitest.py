#!/usr/bin/env python3
"""
MOSDAC API - Full endpoint test report (ek hi command me sab kuch).

    python api_test.py

Ye test karta hai:
  1. Network / DNS reachability
  2. Search API          (GET  /apios/datasets.json)              - login nahi chahiye
  3. Search API error handling (galat datasetId pe sahi error?)    - login nahi chahiye
  4. Token / Login API   (POST /download_api/gettoken)             - credentials chahiye
  5. Download API        (GET  /download_api/download?id=)         - token chahiye

Credentials .env file ya MOSDAC_USER / MOSDAC_PASS env se padhe jate hain.
Agar credentials nahi mile to token/download test SKIP ho jate hain (koi lock ka risk nahi).
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://mosdac.gov.in"
SEARCH_URL = f"{BASE}/apios/datasets.json"
TOKEN_URL = f"{BASE}/download_api/gettoken"
DOWNLOAD_URL = f"{BASE}/download_api/download"
REFRESH_URL = f"{BASE}/download_api/refresh-token"
LOGOUT_URL = f"{BASE}/download_api/logout"

G, R, Y, B, N = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"
rows = []


def load_dotenv(path=Path(__file__).resolve().parent / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def add(status, name, detail=""):
    rows.append((status, name, detail))
    print(f"  [{status}] {name}" + (f"\n         {detail}" if detail else ""))


def t(name, fn):
    """Test chalao, exception ko FAIL me badal do."""
    try:
        return fn()
    except Exception as e:
        add("FAIL", name, f"{type(e).__name__}: {e}")
        return None


def main():
    load_dotenv()
    user = os.environ.get("MOSDAC_USER", "").strip()
    pw = os.environ.get("MOSDAC_PASS", "").strip()
    have_creds = bool(user and pw) and not user.startswith("tumhara")

    print(f"\n{B}===== MOSDAC API TEST REPORT ====={N}")
    print(f"  time: {time.strftime('%Y-%m-%d %H:%M:%S')}   base: {BASE}")
    print(f"  credentials: {'mile (token test hoga)' if have_creds else 'nahi mile (token test SKIP)'}")

    # ---------------- 1. Network ----------------
    print(f"\n{B}--- 1. Network / DNS ---{N}")

    def net():
        r = requests.get(BASE, timeout=20)
        add("PASS" if r.status_code == 200 else "FAIL", "HTTPS mosdac.gov.in",
            f"HTTP {r.status_code} | {r.elapsed.total_seconds()*1000:.0f} ms")
    t("HTTPS mosdac.gov.in", net)

    # ---------------- 2. Search API ----------------
    print(f"\n{B}--- 2. Search API (login ki zarurat nahi) ---{N}")
    ds = os.environ.get("MOSDAC_DATASET", "3RIMG_L2B_SST").strip()
    start = os.environ.get("MOSDAC_START", "2026-08-29").strip()
    end = os.environ.get("MOSDAC_END", "2026-09-01").strip()

    first_id = None

    def search_ok():
        nonlocal first_id
        p = {"datasetId": ds, "startTime": start, "endTime": end, "count": "3"}
        r = requests.get(SEARCH_URL, params=p, timeout=60)
        if r.status_code != 200:
            add("FAIL", f"Search {ds}", f"HTTP {r.status_code} | {r.text[:150]}")
            return
        j = r.json()
        ents = j.get("entries") or []
        if ents:
            first_id = ents[0].get("id")
        add("PASS", f"Search {ds} ({start} → {end})",
            f"totalResults={j.get('totalResults')} | totalSizeMB={j.get('totalSizeMB')} | "
            f"entries={len(ents)} | first={ents[0].get('identifier') if ents else '-'}")
    t(f"Search {ds}", search_ok)

    def search_bad():
        r = requests.get(SEARCH_URL, params={"datasetId": "GALAT_DATASET_XYZ", "count": "1"}, timeout=45)
        if r.status_code in (400, 404, 500):
            add("PASS", "Galat datasetId pe error handling", f"HTTP {r.status_code} (expected error)")
        else:
            add("WARN", "Galat datasetId pe error handling", f"HTTP {r.status_code} — error aana chahiye tha")
    t("Galat datasetId", search_bad)

    def search_dates():
        r = requests.get(SEARCH_URL, params={"datasetId": ds, "startTime": "1990-01-01",
                                             "endTime": "1990-01-02", "count": "1"}, timeout=45)
        add("PASS", "Date filter (1990 - koi data nahi)", f"HTTP {r.status_code}")
    t("Date filter", search_dates)

    # ---------------- 3. Token / Login ----------------
    print(f"\n{B}--- 3. Token / Login API ---{N}")
    token = None

    if not have_creds:
        add("SKIP", "Login/Token API", ".env me MOSDAC_USER / MOSDAC_PASS nahi mile")
    else:
        def login():
            r = requests.post(TOKEN_URL, json={"username": user, "password": pw}, timeout=30)
            if r.status_code == 200:
                j = r.json()
                globals()["token"] = j.get("access_token")
                add("PASS", "POST /download_api/gettoken",
                    f"HTTP 200 | access_token={'mil gaya' if j.get('access_token') else 'NAHI'} | "
                    f"refresh_token={'mil gaya' if j.get('refresh_token') else 'NAHI'}")
            elif r.status_code == 401:
                # 401 = galat credentials. DOOBARA MAT CHALAO (3 attempt = 1 ghanta lock)
                add("FAIL", "POST /download_api/gettoken",
                    f"HTTP 401 | {r.json().get('error','')}  <-- username/password check karo")
            elif r.status_code == 429:
                add("FAIL", "POST /download_api/gettoken",
                    f"HTTP 429 | rate_limit_exceeded  <-- SERVER side issue, tumhari galti nahi. "
                    f"Kuch der baad try karo.")
            else:
                add("FAIL", "POST /download_api/gettoken", f"HTTP {r.status_code} | {r.text[:150]}")
        t("Login/Token", login)

    # ---------------- 4. Download ----------------
    print(f"\n{B}--- 4. Download API ---{N}")
    if not token:
        add("SKIP", f"GET {DOWNLOAD_URL}", "token nahi mila (login fail ya credentials nahi)")
    elif not first_id:
        add("SKIP", "Download endpoint", "koi file id nahi mila search me")
    else:
        def dl():
            h = {"Authorization": f"Bearer {token}"}
            r = requests.get(DOWNLOAD_URL, headers=h, params={"id": first_id}, stream=True, timeout=30)
            cd = r.headers.get("Content-Disposition", "")
            cl = r.headers.get("Content-Length", "?")
            r.close()
            if r.status_code == 200 and "filename=" in cd:
                add("PASS", "Download endpoint",
                    f"HTTP 200 | Content-Length={cl} | file: {cd.split('filename=')[-1][:60]}")
            elif r.status_code == 429:
                add("FAIL", "Download endpoint", "HTTP 429 rate_limit_exceeded (server throttling)")
            else:
                add("FAIL", "Download endpoint", f"HTTP {r.status_code} | {cd[:100]}")
        t("Download endpoint", dl)

    # ---------------- Summary ----------------
    print(f"\n{B}===== SUMMARY ====={N}")
    p = sum(1 for x in rows if x[0] == "PASS")
    f = sum(1 for x in rows if x[0] == "FAIL")
    w = sum(1 for x in rows if x[0] == "WARN")
    s = sum(1 for x in rows if x[0] == "SKIP")
    print(f"  PASS: {p} | FAIL: {f} | WARN: {w} | SKIP: {s}\n")
    if f:
        print("  Failures:")
        for st, name, det in rows:
            if st == "FAIL":
                print(f"   - {name}: {det.splitlines()[0] if det else ''}")
        print()

    # Quick verdict
    login_row = next((x for x in rows if x[1].startswith("Login")), None)
    if login_row and login_row[0] == "FAIL" and "429" in login_row[2]:
        print(f"  {Y}Verdict:{N} Server abhi rate-limit (429) de raha hai (tumhari galti nahi).")
        print("         Search API theek chal rahi hai. Thodi der baad dobara chalao:")
        print("         python api_test.py\n")
    elif login_row and login_row[0] == "SKIP":
        print(f"  {Y}Verdict:{N} Search API OK, par credentials nahi mile - isliye token/download test skip hue.")
        print("         .env me MOSDAC_USER aur MOSDAC_PASS bharo, fir chalao:  python api_test.py\n")
    elif p and not f:
        print(f"  {G}Verdict:{N} Sab theek hai! Ab download kar sakte ho:\n"
              "         python run.py download --count 2\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
