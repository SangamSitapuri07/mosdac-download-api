"""
Geo utilities: EEZ (MarineRegions) + coastline (Natural Earth).

Real data - geo/eez.json aur geo/coastline.json (build_geo.py se bante hain).
"""

import json
from pathlib import Path

import numpy as np

from .config import GEO

_loaded = None


def load():
    global _loaded
    if _loaded is not None:
        return _loaded
    out = {"eez": {}, "coast": []}
    f1, f2 = GEO / "eez.json", GEO / "coastline.json"
    if f1.exists():
        out["eez"] = json.loads(f1.read_text(encoding="utf-8"))
    if f2.exists():
        out["coast"] = json.loads(f2.read_text(encoding="utf-8"))
    _loaded = out
    return out


def eez_names():
    return sorted(load().get("eez", {}).keys())


def eez_mask(lon2d, lat2d, country="India"):
    """Grid par bool mask: True = us desh ke EEZ ke andar."""
    from matplotlib.path import Path as MPath

    polys = load().get("eez", {}).get(country, [])
    if not polys:
        return np.zeros(lon2d.shape, dtype=bool)
    pts = np.column_stack([lon2d.ravel(), lat2d.ravel()])
    mask = np.zeros(pts.shape[0], dtype=bool)
    for poly in polys:
        ring = np.asarray(poly[0], dtype=float)
        if ring.shape[0] < 4:
            continue
        p = MPath(ring, closed=True)
        mask |= p.contains_points(pts)
    return mask.reshape(lon2d.shape)


def coast_distance_km(lon2d, lat2d):
    """Har grid point se najdiki coastline ki doori (km)."""
    coast = load().get("coast", [])
    if not coast:
        return np.full(lon2d.shape, np.nan)
    try:
        from scipy.spatial import cKDTree
    except ImportError:
        return _coast_distance_bruteforce(lon2d, lat2d, coast)

    pts = np.vstack([np.asarray(s, dtype=float) for s in coast if len(s) > 1])
    tree = cKDTree(pts)
    q = np.column_stack([lon2d.ravel(), lat2d.ravel()])
    d, _ = tree.query(q, workers=-1)
    # degrees -> km (approx, 1 deg ~ 111 km; lon cos(lat) se scale)
    lat_rad = np.radians(lat2d.ravel())
    scale = 111.0 * np.cos(np.clip(lat_rad, -1.4, 1.4))
    d_km = d * 111.0                     # conservative (lat direction)
    return d_km.reshape(lon2d.shape)


def _coast_distance_bruteforce(lon2d, lat2d, coast, step=5):
    """scipy na ho to coarse fallback."""
    pts = np.vstack([np.asarray(s, dtype=float)[::step] for s in coast if len(s) > 1])
    out = np.full(lon2d.shape, np.nan)
    flat_lon, flat_lat = lon2d.ravel(), lat2d.ravel()
    best = np.full(flat_lon.shape, 1e9)
    for cx, cy in pts[::3]:
        d = ((flat_lon - cx) ** 2 + (flat_lat - cy) ** 2)
        best = np.minimum(best, d)
    return (np.sqrt(best) * 111.0).reshape(lon2d.shape)


def coastline_segments():
    return load().get("coast", [])


def eez_rings(country=None):
    g = load().get("eez", {})
    if country:
        return {country: g.get(country, [])}
    return g
