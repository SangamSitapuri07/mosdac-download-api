#!/usr/bin/env python3
"""
MarineRegions (VLIZ) WFS se EEZ boundaries + Natural Earth coastline download kar ke
chhota sa JSON banaata hai, taaki maps pe boundaries/coastline dikh sake.

    python build_geo.py

Output: geo/eez.json  (India + padosi deshon ki EEZ)
        geo/coastline.json  (Indian Ocean region ki coastline)
Source : https://www.marineregions.org  (VLIZ) - CC BY 4.0
         https://www.naturalearthdata.com (public domain)
"""

import json
import math
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "geo"
WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
COAST = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
         "master/geojson/ne_50m_coastline.geojson")

COUNTRIES = ["India", "Sri Lanka", "Bangladesh", "Myanmar", "Pakistan",
             "Maldives", "Indonesia", "Oman", "Thailand", "Malaysia", "Iran"]
BBOX = (30.0, -45.0, 110.0, 35.0)     # Indian Ocean region
MIN_D = 0.03                          # simplify: ~3 km


def get(url, params=None, timeout=120):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "mosdac-toolkit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def simplify(coords, min_d=MIN_D):
    """Douglas-Peucker jaisa simple decimation + rounding."""
    out, last = [], None
    for x, y in coords:
        p = (round(float(x), 3), round(float(y), 3))
        if last and abs(p[0] - last[0]) < min_d and abs(p[1] - last[1]) < min_d:
            continue
        out.append(p)
        last = p
    if len(out) < 4:
        return None
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def in_bbox(rings):
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return not (max(xs) < BBOX[0] or min(xs) > BBOX[2] or
                max(ys) < BBOX[1] or min(ys) > BBOX[3])


def fetch_eez(name):
    """MarineRegions WFS se ek desh ki EEZ."""
    data = get(WFS, {"service": "WFS", "version": "1.1.0", "request": "GetFeature",
                     "typeName": "MarineRegions:eez", "outputFormat": "application/json",
                     "cql_filter": f"territory1='{name}'"})
    polys = []
    for f in data.get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") == "MultiPolygon":
            raw = g["coordinates"]
        elif g.get("type") == "Polygon":
            raw = [g["coordinates"]]
        else:
            continue
        rings = []
        for poly in raw:
            for ring in poly[:1]:                    # sirf outer ring
                s = simplify(ring)
                if s:
                    rings.append(s)
        if rings and in_bbox(rings):
            polys.append(rings)
    return polys


def fetch_coast():
    data = get(COAST)
    lines = []
    for f in data.get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            segs = [g["coordinates"]]
        elif g.get("type") == "MultiLineString":
            segs = g["coordinates"]
        else:
            continue
        for seg in segs:
            s = simplify(seg, 0.02)
            if s and len(s) > 1:
                xs = [p[0] for p in s]
                if max(xs) < BBOX[0] or min(xs) > BBOX[2]:
                    continue
                ys = [p[1] for p in s]
                if max(ys) < BBOX[1] or min(ys) > BBOX[3]:
                    continue
                lines.append(s)
    return lines


def main():
    OUT.mkdir(exist_ok=True)
    eez = {}
    for c in COUNTRIES:
        try:
            polys = fetch_eez(c)
            if polys:
                eez[c] = polys
                pts = sum(len(r) for p in polys for r in p)
                print(f"  EEZ  {c:12s} {len(polys)} polygon(s), {pts:,} points")
            else:
                print(f"  EEZ  {c:12s} (region me nahi)")
        except Exception as e:
            print(f"  EEZ  {c:12s} FAIL {type(e).__name__}: {e}")

    (OUT / "eez.json").write_text(json.dumps(eez, separators=(",", ":")), encoding="utf-8")

    try:
        coast = fetch_coast()
        (OUT / "coastline.json").write_text(
            json.dumps(coast, separators=(",", ":")), encoding="utf-8")
        print(f"  COAST {len(coast)} segments, {sum(len(s) for s in coast):,} points")
    except Exception as e:
        print(f"  COAST FAIL {type(e).__name__}: {e}")

    for f in ("eez.json", "coastline.json"):
        p = OUT / f
        if p.exists():
            print(f"  -> {p} ({p.stat().st_size/1024:.0f} KB)")
    print("\nSources: MarineRegions/EEZ v12 (VLIZ, CC BY 4.0) | Natural Earth (public domain)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
