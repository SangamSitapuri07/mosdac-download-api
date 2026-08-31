#!/usr/bin/env python3
"""
MOSDAC Data Download API - Readiness / API Checker

Ye script bina credentials ke bhi chal sakti hai (sirf SEARCH API test karegi).
Login/token test karne ke liye --username / --password do (ya --check-login flag lagao).

Usage:
    python3 check_requirements.py
    python3 check_requirements.py --dataset-id 3SIMG_L1B_STD --start 2025-01-01 --end 2025-01-02 --count 5
    python3 check_requirements.py --check-login --username <user> --password <pass>
    python3 check_requirements.py --config config.json      # config.json se values uthao
"""

import argparse
import json
import os
import sys
import platform

SEARCH_URL = "https://mosdac.gov.in/apios/datasets.json"
TOKEN_URL = "https://mosdac.gov.in/download_api/gettoken"
REFRESH_URL = "https://mosdac.gov.in/download_api/refresh-token"
LOGOUT_URL = "https://mosdac.gov.in/download_api/logout"
DOWNLOAD_URL = "https://mosdac.gov.in/download_api/download"

OK, BAD, WARN = "[PASS]", "[FAIL]", "[WARN]"
results = []


def record(status, item, detail=""):
    results.append((status, item, detail))
    print(f"{status} {item}" + (f" -> {detail}" if detail else ""))


def check_python():
    v = sys.version_info
    if v.major >= 3:
        record(OK, "Python version", f"{platform.python_version()} (>= 3 required)")
    else:
        record(BAD, "Python version", "Python 3+ chahiye")


def check_module(name, required=True):
    import importlib.util as util
    spec = util.find_spec(name)
    if spec is not None:
        try:
            mod = __import__(name)
            ver = getattr(mod, "__version__", "installed")
        except Exception:
            ver = "installed"
        record(OK, f"Python library: {name}", str(ver))
        return True
    msg = f"pip install {name}"
    record(BAD if required else WARN, f"Python library: {name}",
           ("REQUIRED - " if required else "OPTIONAL (progress bar ke liye) - ") + msg)
    return False


def check_network():
    try:
        import requests
        r = requests.get("https://mosdac.gov.in", timeout=20)
        record(OK, "Network: mosdac.gov.in reachable", f"HTTP {r.status_code}")
        return True
    except Exception as e:
        record(BAD, "Network: mosdac.gov.in reachable", f"{type(e).__name__}: {e}")
        return False


def check_search(dataset_id, start, end, count, bbox=None, gid=None):
    """Search API - isko check karne ke liye LOGIN zaroori NAHI hai."""
    import requests
    if not dataset_id:
        record(WARN, "Search API", "datasetId nahi diya - skip")
        return None
    params = {"datasetId": dataset_id}
    if start:
        params["startTime"] = start
    if end:
        params["endTime"] = end
    if count:
        params["count"] = str(count)
    if bbox:
        params["boundingBox"] = bbox
    if gid:
        params["gId"] = gid

    try:
        r = requests.get(SEARCH_URL, params=params, timeout=60)
    except Exception as e:
        record(BAD, "Search API (GET /apios/datasets.json)", f"{type(e).__name__}: {e}")
        return None

    if r.status_code == 200:
        j = r.json()
        total = j.get("totalResults")
        size = j.get("totalSizeMB")
        entries = j.get("entries") or []
        record(OK, "Search API (GET /apios/datasets.json)",
                f"HTTP 200 | totalResults={total} | totalSizeMB={size} | entries={len(entries)}")
        for e in entries[:3]:
            print(f"        - {e.get('identifier')}  (id={e.get('id')}, updated={e.get('updated')})")
        return j
    else:
        try:
            msg = r.json().get("message") or r.json()
        except Exception:
            msg = r.text[:200]
        record(BAD, "Search API (GET /apios/datasets.json)", f"HTTP {r.status_code} | {msg}")
        return None


def check_login(username, password, do_login):
    """Token API - REAL credentials chahiye. 3 galat attempt = 1 hour lock."""
    import requests
    if not do_login:
        record(WARN, "Login/Token API", "skipped (--check-login nahi lagaya). "
                                        "Sirf search/check ke liye login zaroori nahi.")
        return None
    if not username or not password:
        record(BAD, "Login/Token API", "username/password missing")
        return None

    try:
        r = requests.post(TOKEN_URL, json={"username": username, "password": password}, timeout=30)
    except Exception as e:
        record(BAD, "Login/Token API (POST /download_api/gettoken)", f"{type(e).__name__}: {e}")
        return None

    if r.status_code == 200:
        j = r.json()
        at, rt = j.get("access_token"), j.get("refresh_token")
        record(OK, "Login/Token API", f"HTTP 200 | access_token={'mil gaya' if at else 'NAHI mila'} | "
                                      f"refresh_token={'mil gaya' if rt else 'NAHI mila'}")
        if at:
            print(f"        access_token (pehle 25 char): {str(at)[:25]}...")
        return j
    else:
        try:
            msg = r.json().get("error") or r.json()
        except Exception:
            msg = r.text[:200]
        record(BAD, "Login/Token API", f"HTTP {r.status_code} | {msg}")
        return None


def check_download_probe(access_token, record_id):
    """Sirf HEAD/stream check - poori file download nahi karega."""
    import requests
    if not access_token or not record_id:
        record(WARN, "Download API", "skipped (token ya record id nahi mila)")
        return
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        r = requests.get(DOWNLOAD_URL, headers=headers, params={"id": record_id},
                         stream=True, timeout=20)
        cd = r.headers.get("Content-Disposition", "")
        cl = r.headers.get("Content-Length", "?")
        r.close()
        if r.status_code == 200 and "filename=" in cd:
            record(OK, "Download API (GET /download_api/download?id=)",
                   f"HTTP 200 | Content-Length={cl} | filename header present")
        else:
            record(BAD, "Download API", f"HTTP {r.status_code} | Content-Disposition='{cd}'")
    except Exception as e:
        record(BAD, "Download API", f"{type(e).__name__}: {e}")


def check_config(path):
    if not os.path.exists(path):
        record(BAD, f"Config file '{path}'", "file nahi mila (mdapi.py ke saath same folder me hona chahiye)")
        return {}
    try:
        with open(path) as f:
            cfg = json.load(f)
    except Exception as e:
        record(BAD, f"Config file '{path}'", f"invalid JSON: {e}")
        return {}

    problems = []
    for sec in ("user_credentials", "search_parameters"):
        if sec not in cfg:
            problems.append(f"section missing: {sec}")
    ds = cfg.get("search_parameters", {}).get("datasetId", "")
    if not ds:
        problems.append("search_parameters.datasetId khali hai (mandatory)")
    # NOTE: mdapi.py inhi key-names ko padhta hai (manual me kuch alag naam hain)
    wrong_keys = {"user_credentials": {"username": "username/email"},
                  "download_settings": {"skip_user_prompt": "skip_user_input",
                                        "generate_error_log": "generate_error_logs",
                                        "error_log_path": "error_logs_dir"}}
    for section, mapping in wrong_keys.items():
        present = cfg.get(section, {})
        if not isinstance(present, dict):
            continue
        for key, good in mapping.items():
            if key in present:
                problems.append(f"{section}.'{key}' manual wala naam hai - mdapi.py '{good}' padhta hai")

    for field in ("organize_by_date", "skip_user_input", "generate_error_logs"):
        v = cfg.get("download_settings", {}).get(field)
        if v is not None and not isinstance(v, bool):
            problems.append(f"download_settings.{field} boolean hona chahiye (true/false), mila: {v!r}")

    if problems:
        record(BAD, f"Config file '{path}'", "; ".join(problems))
    else:
        record(OK, f"Config file '{path}'", "structure theek hai")
    return cfg


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--dataset-id", default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--count", default=3)
    ap.add_argument("--bounding-box", default=None)
    ap.add_argument("--g-id", default=None)
    ap.add_argument("--check-login", action="store_true")
    ap.add_argument("--username", default=os.environ.get("MOSDAC_USER", ""))
    ap.add_argument("--password", default=os.environ.get("MOSDAC_PASS", ""))
    ap.add_argument("--probe-download", action="store_true",
                    help="token milne ke baad ek file ka download endpoint probe karega")
    a = ap.parse_args()

    print("\n===== MOSDAC Download API - Requirement Check =====\n")
    print("--- 1. System / Python requirements ---")
    check_python()
    check_module("requests", required=True)
    check_module("tqdm", required=False)

    print("\n--- 2. Network ---")
    net_ok = check_network()

    print("\n--- 3. Config file ---")
    cfg = check_config(a.config)
    sp = cfg.get("search_parameters", {})
    uc = cfg.get("user_credentials", {})

    dataset_id = a.dataset_id or sp.get("datasetId") or "3RIMG_L2B_SST"
    start = a.start or sp.get("startTime") or ""
    end = a.end or sp.get("endTime") or ""
    count = a.count or sp.get("count") or 3
    bbox = a.bounding_box or sp.get("boundingBox") or None
    gid = a.g_id or sp.get("gId") or None
    username = a.username or uc.get("username/email") or uc.get("username") or ""
    password = a.password or uc.get("password") or ""

    print("\n--- 4. Search API (bina login ke chalti hai) ---")
    search_json = None
    if net_ok:
        search_json = check_search(dataset_id, start, end, count, bbox, gid)
    else:
        record(WARN, "Search API", "network fail hone ke kaaran skip")

    print("\n--- 5. Login / Token API ---")
    token_json = check_login(username, password, a.check_login)

    if a.probe_download and token_json:
        print("\n--- 6. Download API probe ---")
        rid = None
        if search_json and search_json.get("entries"):
            rid = search_json["entries"][0].get("id")
        check_download_probe(token_json.get("access_token"), rid)

    print("\n===== SUMMARY =====")
    fails = [r for r in results if r[0] == BAD]
    warns = [r for r in results if r[0] == WARN]
    print(f"PASS: {len([r for r in results if r[0]==OK])} | FAIL: {len(fails)} | WARN: {len(warns)}")
    if fails:
        print("\nFailures:")
        for _, item, detail in fails:
            print(f"  - {item}: {detail}")
    print("\nNote: bina login ke sirf SEARCH/check kar sakte ho. Download ke liye approved")
    print("      MOSDAC account + sahi credentials zaroori hain (3 galat attempt = 1 hr lock).\n")


if __name__ == "__main__":
    main()
