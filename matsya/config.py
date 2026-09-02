"""Settings + paths. Sab kuch settings.json se control hota hai (repo root me)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
OUT = ROOT / "out"
GEO = ROOT / "geo"
CACHE = ROOT / "cache"

DEFAULTS = {
    "datasets": {
        "sst": "3RIMG_L2B_SST",          # INSAT-3DR L2B Sea Surface Temperature
        "wind": "3RIMG_L2P_VSW",         # INSAT-3DR L2P Vector Sea Wind
        "chlorophyll": None,             # MOSDAC API me uplabdh NAHI - NOTES.md dekho
    },
    "region": {
        "name": "indian-ocean",
        "bbox": [40.0, -40.0, 110.0, 30.0],   # minlon, minlat, maxlon, maxlat
        "max_grid": 700,                      # analysis grid size cap
    },
    "fetch": {
        "max_files": 2,        # kitne naye files laayein
        "hours_back": 24,
    },
    "physics": {
        "front_ref_c_per_km": 0.05,   # itna gradient = strong thermal front
        "sst_optimum_c": 28.0,
        "sst_sigma_c": 3.2,
        "sst_min_c": 24.0,            # isse kam = bahut thanda
        "sst_max_c": 32.0,
        "weights": {"front": 30, "sst": 25, "eez": 12, "shelf": 8, "wind": 8, "chl": 17},
        "shelf_max_km": 120.0,        # continental shelf ~ fish zyada
        "wind_calm_ms": 6.0,          # isse kam = theek
        "wind_caution_ms": 10.0,      # isse upar = dhyaan
        "wind_danger_ms": 14.0,       # isse upar = mat jao
    },
    "advisory": {
        "go": 70, "ok": 55, "maybe": 40,
        "top_spots": 12,
    },
}


def load():
    f = ROOT / "settings.json"
    cfg = json.loads(json.dumps(DEFAULTS))     # deep copy
    if f.exists():
        try:
            user = json.loads(f.read_text(encoding="utf-8"))
            _merge(cfg, user)
        except Exception as e:
            print(f"[warn] settings.json padh nahi paye ({e}), defaults use ho rahe hain")
    return cfg


def _merge(base, new):
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def ensure_dirs():
    for d in (DATA, OUT, CACHE):
        d.mkdir(exist_ok=True)
    return DATA, OUT
