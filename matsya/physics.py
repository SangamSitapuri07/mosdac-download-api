"""Ocean physics / advisory scoring - real satellite values se."""

import math

import numpy as np


def gradient_c_per_km(data, lat, lon):
    """Thermal front strength (°C/km)."""
    if lat is None or lon is None or lat.shape != data.shape:
        gy, gx = np.gradient(np.where(np.isfinite(data), data, np.nan))
        return np.sqrt(np.nan_to_num(gx) ** 2 + np.nan_to_num(gy) ** 2)

    dlat = abs(float(np.nanmean(np.diff(lat, axis=0)))) or 0.05
    dlon = abs(float(np.nanmean(np.diff(lon, axis=1)))) or 0.05
    latm = float(np.nanmean(lat))
    dy = dlat * 111.0
    dx = dlon * 111.0 * math.cos(math.radians(latm))
    gy, gx = np.gradient(np.where(np.isfinite(data), data, np.nan))
    return np.sqrt(np.nan_to_num(gx / max(dx, 1e-6)) ** 2 +
                   np.nan_to_num(gy / max(dy, 1e-6)) ** 2)


def sst_score(sst_c, cfg):
    """0..1 : 28 °C ke aas-paas best (Gaussian)."""
    p = cfg["physics"]
    g = np.exp(-(((sst_c - p["sst_optimum_c"]) / p["sst_sigma_c"]) ** 2))
    cold = np.clip((sst_c - p["sst_min_c"]) / 4.0, 0, 1)
    hot = np.clip((p["sst_max_c"] - sst_c) / 4.0, 0, 1)
    return np.clip(g * np.minimum(cold, hot), 0, 1)


def front_score(grad, cfg):
    ref = cfg["physics"]["front_ref_c_per_km"]
    return np.clip(grad / ref, 0, 1)


def shelf_score(dist_km, cfg):
    """Continental shelf ke paas fish zyada; 0 km se 120 km tak ghat-ta faayda."""
    if dist_km is None:
        return np.full_like(next(iter([np.zeros(1)])), 0.5)
    mx = cfg["physics"]["shelf_max_km"]
    s = np.clip(1.0 - (dist_km / mx), 0, 1)
    s = np.where(np.isnan(dist_km), 0.5, s)
    return np.clip(s, 0, 1)


def chl_score(chl, cfg):
    """0..1 — chlorophyll-a (mg/m3). PFZ literature: machhli 0.2-2 mg/m3 me jama hoti hain."""
    if chl is None:
        return None
    c = np.where(np.isfinite(chl), chl, np.nan)
    # log-normal peak around 0.6 mg/m3
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.log10(np.clip(c, 0.01, 30.0))
        s = np.exp(-(((x - np.log10(0.6)) / 0.55) ** 2))
    s = np.where(np.isnan(c), np.nan, s)
    return np.clip(s, 0, 1)


def wind_speed_from_uv(u, v):
    return np.sqrt(np.nan_to_num(u) ** 2 + np.nan_to_num(v) ** 2)


def sea_state(speed_ms, cfg):
    """0..1 safety (1 = bilkul theek)."""
    p = cfg["physics"]
    if speed_ms is None:
        return None
    calm, caut, danger = p["wind_calm_ms"], p["wind_caution_ms"], p["wind_danger_ms"]
    s = np.where(speed_ms <= calm, 1.0,
        np.where(speed_ms <= caut, 1.0 - 0.5 * (speed_ms - calm) / (caut - calm),
        np.where(speed_ms <= danger, 0.5 - 0.5 * (speed_ms - caut) / (danger - caut),
                 0.0)))
    return np.clip(s, 0, 1)


def sea_state_label(speed_ms, cfg):
    if speed_ms is None:
        return "?", "#94a3b8"
    p = cfg["physics"]
    if speed_ms <= p["wind_calm_ms"]:
        return "SHANT (theek hai)", "#22c55e"
    if speed_ms <= p["wind_caution_ms"]:
        return "HALKA (dhyaan rakhein)", "#eab308"
    if speed_ms <= p["wind_danger_ms"]:
        return "TEZ (khatra)", "#f97316"
    return "TOOFANI (mat jao)", "#ef4444"


def pfz_score(sst_c, grad, in_eez, dist_km, wind_ms, cfg, chl=None):
    """
    Final 0-100 PFZ score. Har layer ka contribution uske weight se.
    Jo layer uplabdh NAHI hai uska weight baaki layers me baant diya jata hai
    (taaki chlorophyll na hone par score artificially kam na ho).
    """
    w = dict(cfg["physics"]["weights"])

    parts = []
    parts.append((w.get("front", 35), front_score(grad, cfg)))
    parts.append((w.get("sst", 30), sst_score(sst_c, cfg)))
    parts.append((w.get("eez", 15),
                  np.where(in_eez, 1.0, 0.15) if in_eez is not None else None))
    parts.append((w.get("shelf", 10), shelf_score(dist_km, cfg)))
    parts.append((w.get("wind", 10), sea_state(wind_ms, cfg)))
    parts.append((w.get("chl", 18), chl_score(chl, cfg)))

    num = None
    den = 0.0
    for weight, arr in parts:
        if arr is None or weight is None:
            continue
        arr = np.asarray(arr, dtype=float)
        arr = np.where(np.isfinite(arr), arr, 0.0)
        num = arr * weight if num is None else num + arr * weight
        den += weight
    if num is None or den == 0:
        return np.zeros_like(sst_c)
    score = num / den * 100.0
    score = np.where(np.isfinite(sst_c), score, np.nan)
    return np.clip(score, 0, 100)


def verdict(score, cfg):
    a = cfg["advisory"]
    if not np.isfinite(score):
        return "NO DATA", "#64748b"
    if score >= a["go"]:
        return "JAO - best zone", "#22c55e"
    if score >= a["ok"]:
        return "THEEK HAI", "#84cc16"
    if score >= a["maybe"]:
        return "SHAYAD", "#eab308"
    return "MAT JAO", "#ef4444"


def top_spots(score, lat, lon, sst, grad, wind, dist, eez, n=12, block=30):
    """Best spots - block-wise maxima, duplicates hata kar."""
    if lat is None or lon is None:
        return []
    ny, nx = score.shape
    out = []
    for i in range(0, ny - block, block):
        for j in range(0, nx - block, block):
            blk = score[i:i + block, j:j + block]
            if not np.isfinite(blk).any():
                continue
            r, c = np.unravel_index(np.nanargmax(blk), blk.shape)
            ri, ci = i + r, j + c
            s = float(score[ri, ci])
            if not np.isfinite(s):
                continue
            out.append({
                "lat": round(float(lat[ri, ci]), 3),
                "lon": round(float(lon[ri, ci]), 3),
                "score": round(s, 1),
                "sst": round(float(sst[ri, ci]), 2) if sst is not None and np.isfinite(sst[ri, ci]) else None,
                "front": round(float(grad[ri, ci]), 4) if grad is not None and np.isfinite(grad[ri, ci]) else None,
                "wind": round(float(wind[ri, ci]), 1) if wind is not None and np.isfinite(wind[ri, ci]) else None,
                "coast_km": round(float(dist[ri, ci]), 0) if dist is not None and np.isfinite(dist[ri, ci]) else None,
                "in_eez": bool(eez[ri, ci]) if eez is not None else None,
            })
    out.sort(key=lambda x: -x["score"])
    seen, uniq = set(), []
    for o in out:
        k = (round(o["lat"]), round(o["lon"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(o)
    return uniq[:n]
