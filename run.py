#!/usr/bin/env python3
"""
MOSDAC Data Download API - one-command runner.

Credentials kabhi bhi file me nahi likhe jate - .env (ya environment variables) se padhe jate hain.

Commands:
    python3 run.py config      # .env + defaults se mosdac/config.json banata hai
    python3 run.py test        # env + network + Search API test (LOGIN nahi karta)  <-- pehle ye chalao
    python3 run.py login       # token/login test (asli credentials use karta hai - sirf 1 attempt)
    python3 run.py download    # config bana kar mdapi.py chalaata hai (asli download)
    python3 run.py doctor      # config + test + login, ek saath (end-to-end)

Options (har command pe lage sakte hain):
    --dataset 3RIMG_L2B_SST   --start 2026-08-29   --end 2026-09-01
    --count 2                 --path ./data        --bbox "70.0,8.0,90.0,28.0"
    --gid 15039367            --yes (prompt skip)  --no-organize
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MOSDAC_DIR = ROOT / "mosdac"
TEMPLATE = MOSDAC_DIR / "config.template.json"
CONFIG = MOSDAC_DIR / "config.json"
ENV_FILE = ROOT / ".env"

DEFAULTS = {
    "datasetId": "3RIMG_L2B_SST",
    "startTime": "2026-08-29",
    "endTime": "2026-09-01",
    "count": "2",
    "boundingBox": "",
    "gId": "",
}

C = {"g": "\033[92m", "r": "\033[91m", "y": "\033[93m", "b": "\033[1m", "0": "\033[0m"}


def load_dotenv(path=ENV_FILE):
    """Simple .env loader - koi extra dependency nahi."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)  # real env vars ko priority milti hai


def env(name, default=""):
    return os.environ.get(name, default).strip()


def _resolve_path(p):
    """Relative path ko hamesha repo-root se jodo (mdapi.py alag folder se chalta hai)."""
    p = Path(str(p)).expanduser()
    return p if p.is_absolute() else (ROOT / p)


def build_config(a):
    load_dotenv()
    user = a.username or env("MOSDAC_USER") or env("MOSDAC_USERNAME") or env("MOSDAC_EMAIL")
    pw = a.password or env("MOSDAC_PASS") or env("MOSDAC_PASSWORD")

    cfg = {
        "user_credentials": {
            "username/email": user or "CHANGE_ME_USERNAME",
            "password": pw or "CHANGE_ME_PASSWORD",
        },
        "search_parameters": {
            "datasetId": a.dataset or env("MOSDAC_DATASET", DEFAULTS["datasetId"]),
            "startTime": a.start or env("MOSDAC_START", DEFAULTS["startTime"]),
            "endTime": a.end or env("MOSDAC_END", DEFAULTS["endTime"]),
            "count": str(a.count if a.count is not None else env("MOSDAC_COUNT", DEFAULTS["count"])),
            "boundingBox": a.bbox or env("MOSDAC_BBOX", DEFAULTS["boundingBox"]),
            "gId": a.gid or env("MOSDAC_GID", DEFAULTS["gId"]),
        },
        "download_settings": {
            "download_path": str(_resolve_path(a.path or env("MOSDAC_DOWNLOAD_PATH", "data"))),
            "organize_by_date": (not a.no_organize) if a.no_organize else
                                (env("MOSDAC_ORGANIZE", "true").lower() in ("1", "true", "yes")),
            "skip_user_input": bool(a.yes or env("MOSDAC_SKIP_PROMPT", "false").lower() in ("1", "true", "yes")),
            "generate_error_logs": True,
            "error_logs_dir": str(ROOT / "error_logs"),
        },
    }
    return cfg, user, pw


def write_config(a):
    cfg, user, pw = build_config(a)
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"{C['g']}[OK]{C['0']} config likha gaya: {CONFIG}")
    print(f"     datasetId : {cfg['search_parameters']['datasetId']}")
    print(f"     range     : {cfg['search_parameters']['startTime']} -> {cfg['search_parameters']['endTime']}")
    print(f"     count     : {cfg['search_parameters']['count'] or '(sab)'}   path: {cfg['download_settings']['download_path']}")
    return cfg, user, pw


def check_creds(user, pw):
    if not user or not pw or user.startswith("CHANGE_ME") or pw.startswith("CHANGE_ME"):
        print(f"\n{C['r']}[ERROR]{C['0']} Credentials nahi mile.")
        print("  .env file banao (cp .env.example .env) aur MOSDAC_USER / MOSDAC_PASS bharo, ya:")
        print(f'  {C["b"]}export MOSDAC_USER="tumhara_username"; export MOSDAC_PASS="tumhara_password"{C["0"]}\n')
        return False
    return True


def run_py(script, args, cwd=ROOT):
    return subprocess.run([sys.executable, script, *args], cwd=cwd).returncode


def cmd_config(a):
    write_config(a)
    return 0


def cmd_test(a):
    cfg, user, pw = write_config(a)
    print(f"\n{C['b']}--- Environment + Search API test (login nahi karega) ---{C['0']}\n")
    return run_py(str(MOSDAC_DIR / "check_requirements.py"),
                  ["--config", str(CONFIG),
                   "--dataset-id", cfg["search_parameters"]["datasetId"],
                   "--start", cfg["search_parameters"]["startTime"],
                   "--end", cfg["search_parameters"]["endTime"],
                   "--count", cfg["search_parameters"]["count"] or "3"])


def cmd_login(a):
    cfg, user, pw = write_config(a)
    if not check_creds(user, pw):
        return 1
    print(f"\n{C['y']}[WARNING]{C['0']} Ye tumhare ASLI credentials se 1 login attempt karega.")
    print("  (3 galat attempt = account 1 ghante ke liye lock)\n")
    return run_py(str(MOSDAC_DIR / "check_requirements.py"),
                  ["--config", str(CONFIG), "--check-login",
                   "--username", user, "--password", pw,
                   "--dataset-id", cfg["search_parameters"]["datasetId"],
                   "--start", cfg["search_parameters"]["startTime"],
                   "--end", cfg["search_parameters"]["endTime"],
                   "--count", cfg["search_parameters"]["count"] or "3"])


def run_mdapi(cwd, logfile):
    """mdapi.py chalao, live output dikhao aur saath hi log file me likho."""
    import subprocess
    with open(logfile, "a", encoding="utf-8", errors="replace") as lf:
        proc = subprocess.Popen([sys.executable, "mdapi.py"], cwd=cwd,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        for line in proc.stdout:
            print(line, end="", flush=True)
            lf.write(line)
        proc.wait()
        return proc.returncode


def cmd_download(a):
    cfg, user, pw = write_config(a)
    if not check_creds(user, pw):
        return 1
    print(f"\n{C['b']}--- Download shuru: mosdac/mdapi.py ---{C['0']}\n")

    logfile = ROOT / "error_logs" / "mdapi_console.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)

    # MOSDAC server kabhi-kabhi 429 (rate limit) deta hai -> wait kar ke retry
    delays = [0, 60, 120, 180]
    code = 0
    for attempt, delay in enumerate(delays):
        if delay:
            print(f"\n{C['y']}[INFO]{C['0']} Rate limit (429) laga tha - {delay} sec wait kar ke "
                  f"dobara try (attempt {attempt + 1}/{len(delays)})...\n")
            import time as _t
            _t.sleep(delay)
        code = run_mdapi(str(MOSDAC_DIR), logfile)
        tail = ""
        try:
            tail = logfile.read_text(encoding="utf-8", errors="replace")[-4000:].lower()
        except Exception:
            pass
        if "rate_limit" in tail or "429" in tail or "download limit exceeded" in tail:
            continue
        break
    data_dir = Path(cfg["download_settings"]["download_path"])
    if data_dir.exists():
        files = [p for p in data_dir.rglob("*") if p.is_file()]
        print(f"\n{C['g']}[INFO]{C['0']} {data_dir} me {len(files)} file(s) hain.")
    logs = sorted(Path(ROOT / "error_logs").glob("*_error.log")) if (ROOT / "error_logs").exists() else []
    if logs:
        print(f"{C['y']}[INFO]{C['0']} Error log: {logs[-1]}")
    return code


def cmd_doctor(a):
    print(f"{C['b']}===== STEP 1/3 : Environment + Search ====={C['0']}")
    rc = cmd_test(a)
    if rc != 0:
        print(f"\n{C['r']}Search test fail - pehle isko theek karo.{C['0']}")
        return rc
    print(f"\n{C['b']}===== STEP 2/3 : Login / Token ====={C['0']}")
    rc = cmd_login(a)
    if rc != 0:
        print(f"\n{C['r']}Login test fail - credentials / approval check karo.{C['0']}")
        return rc
    if a.skip_download:
        print(f"\n{C['g']}Sab theek hai! Download ke liye: python3 run.py download{C['0']}")
        return 0
    print(f"\n{C['b']}===== STEP 3/3 : Test download (chhota) ====={C['0']}")
    return cmd_download(a)


def main():
    p = argparse.ArgumentParser(description="MOSDAC Download API - one-command runner")
    p.add_argument("command", choices=["config", "test", "login", "download", "doctor"])
    p.add_argument("--dataset", default=None)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--count", default=None)
    p.add_argument("--path", default=None)
    p.add_argument("--bbox", default=None)
    p.add_argument("--gid", default=None)
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--yes", action="store_true", help="download prompt skip (background mode)")
    p.add_argument("--no-organize", action="store_true", help="date-wise folders nahi banana")
    p.add_argument("--skip-download", action="store_true", help="(doctor) sirf test+login, download nahi")
    a = p.parse_args()

    if not TEMPLATE.exists():
        print(f"{C['r']}[ERROR]{C['0']} {TEMPLATE} nahi mila.")
        return 1

    return {"config": cmd_config, "test": cmd_test, "login": cmd_login,
            "download": cmd_download, "doctor": cmd_doctor}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
