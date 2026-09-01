#!/usr/bin/env python3
"""
MOSDAC API - Direct Python client (mdapi.py ki zarurat nahi!)

Apne code me direct use karo:

    from mosdac_client import Mosdac

    m = Mosdac("username", "password")          # .env se bhi padh lega
    files = m.search("3RIMG_L2B_SST", "2026-09-01", "2026-09-01")
    raw   = m.download_bytes(files[0]["id"])    # seedha memory me (disk pe save nahi)
    m.download_file(files[0]["id"], "out.h5")   # ya file me save
    m.logout()

Note: MOSDAC API binary files (.h5 / HDF5) deti hai, JSON values nahi.
      Inhe padhne ke liye h5py use karo (dekho examples/read_h5.py).
"""

import io
import os
from pathlib import Path

import requests

BASE = "https://mosdac.gov.in"
SEARCH_URL = f"{BASE}/apios/datasets.json"
TOKEN_URL = f"{BASE}/download_api/gettoken"
REFRESH_URL = f"{BASE}/download_api/refresh-token"
DOWNLOAD_URL = f"{BASE}/download_api/download"
LOGOUT_URL = f"{BASE}/download_api/logout"


class MosdacError(Exception):
    pass


class Mosdac:
    def __init__(self, username=None, password=None, timeout=60):
        self.username = username or os.environ.get("MOSDAC_USER", "")
        self.password = password or os.environ.get("MOSDAC_PASS", "")
        if not self.username or not self.password:
            p = Path(".env")
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        v = v.strip().strip('"').strip("'")
                        if k.strip() == "MOSDAC_USER" and not self.username:
                            self.username = v
                        elif k.strip() == "MOSDAC_PASS" and not self.password:
                            self.password = v
        self.timeout = timeout
        self.access_token = None
        self.refresh_token = None

    # ---------------- auth ----------------
    def login(self):
        r = requests.post(TOKEN_URL, json={"username": self.username,
                                           "password": self.password}, timeout=30)
        if r.status_code == 401:
            raise MosdacError(f"401 galat username/password (3 baar galat = 1 ghanta lock)")
        if r.status_code == 429:
            raise MosdacError("429 server rate limit - thodi der baad try karo")
        if r.status_code != 200:
            raise MosdacError(f"login failed: HTTP {r.status_code} | {r.text[:200]}")
        j = r.json()
        self.access_token = j.get("access_token")
        self.refresh_token = j.get("refresh_token")
        return self.access_token

    def refresh(self):
        if not self.refresh_token:
            return self.login()
        r = requests.post(REFRESH_URL, json={"refresh_token": self.refresh_token}, timeout=30)
        if r.status_code != 200:
            return self.login()
        j = r.json()
        self.access_token = j.get("access_token")
        self.refresh_token = j.get("refresh_token")
        return self.access_token

    def logout(self):
        try:
            requests.post(LOGOUT_URL, json={"username": self.username}, timeout=5)
        except Exception:
            pass

    def _token(self):
        if not self.access_token:
            self.login()
        return self.access_token

    # ---------------- search (login zaroori nahi) ----------------
    def search(self, dataset_id, start=None, end=None, count=None,
               bbox=None, gid=None, start_index=1):
        p = {"datasetId": dataset_id, "startIndex": start_index}
        if start:
            p["startTime"] = start
        if end:
            p["endTime"] = end
        if count:
            p["count"] = str(count)
        if bbox:
            p["boundingBox"] = bbox
        if gid:
            p["gId"] = gid

        r = requests.get(SEARCH_URL, params=p, timeout=self.timeout)
        if r.status_code != 200:
            msg = ""
            try:
                msg = r.json().get("message")
            except Exception:
                msg = r.text[:200]
            raise MosdacError(f"search failed: HTTP {r.status_code} | {msg}")
        j = r.json()
        return {
            "total": j.get("totalResults"),
            "total_size_mb": j.get("totalSizeMB"),
            "entries": j.get("entries") or [],
            "raw": j,
        }

    def search_all(self, dataset_id, start=None, end=None, bbox=None, max_files=None):
        """Pagination ke saath saare files lao (100 ke batch me)."""
        out, idx = [], 1
        while True:
            res = self.search(dataset_id, start, end, count=100, bbox=bbox, start_index=idx)
            ents = res["entries"]
            if not ents:
                break
            out.extend(ents)
            if max_files and len(out) >= max_files:
                return out[:max_files]
            if len(out) >= (res["total"] or 0):
                break
            idx += 100
        return out

    # ---------------- download ----------------
    def download_bytes(self, record_id):
        """File ko seedha memory me lao (disk pe save kiye bina)."""
        r = requests.get(DOWNLOAD_URL,
                         headers={"Authorization": f"Bearer {self._token()}"},
                         params={"id": record_id}, stream=True, timeout=self.timeout)
        if r.status_code in (401, 403) and self.refresh_token:
            self.refresh()
            r = requests.get(DOWNLOAD_URL,
                             headers={"Authorization": f"Bearer {self.access_token}"},
                             params={"id": record_id}, stream=True, timeout=self.timeout)
        if r.status_code != 200:
            raise MosdacError(f"download failed: HTTP {r.status_code} | {r.text[:200]}")
        return r.content

    def download_file(self, record_id, dest):
        """File ko disk par save karo, path return karo."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = self.download_bytes(record_id)
        dest.write_bytes(data)
        return str(dest)

    def download_stream(self, record_id, chunk_size=1024 * 1024):
        """Generator - badi file ko chunk-chunk kar ke process karo (RAM bachao)."""
        r = requests.get(DOWNLOAD_URL,
                         headers={"Authorization": f"Bearer {self._token()}"},
                         params={"id": record_id}, stream=True, timeout=self.timeout)
        if r.status_code != 200:
            raise MosdacError(f"download failed: HTTP {r.status_code} | {r.text[:200]}")
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                yield chunk

    def read_h5(self, record_id):
        """File ko memory me la kar h5py object banao (disk pe kuch save nahi hota)."""
        import h5py
        return h5py.File(io.BytesIO(self.download_bytes(record_id)), "r")

    # context manager
    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *a):
        self.logout()
