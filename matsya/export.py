"""GeoJSON / CSV export — GIS tools (QGIS, Google Earth) me kholne ke liye."""

import json
from pathlib import Path

import numpy as np

from . import geo_tools as G


def _pt(lon, lat, props):
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(float(lon), 4),
                                                          round(float(lat), 4)]},
            "properties": props}


def build(spots, route=None, eez_country="India", grid=None, step=8,
          provenance=None):
    feats = []
    for i, s in enumerate(spots):
        feats.append(_pt(s["lon"], s["lat"], {
            "rank": i + 1, "name": f"PFZ-{i+1}", "score": s["score"],
            "sst_c": s["sst"], "wind_ms": s["wind"],
            "front_c_per_km": s["front"], "coast_km": s["coast_km"],
            "in_india_eez": s.get("in_eez"), "marker-color": "#22c55e"}))
    if route:
        feats.append({"type": "Feature",
                      "geometry": route,
                      "properties": {"name": "A* route", "stroke": "#f43f5e",
                                     "stroke-width": 3}})
    for poly in (G.eez_rings(eez_country).get(eez_country) or []):
        feats.append({"type": "Feature",
                      "geometry": {"type": "Polygon",
                                   "coordinates": [
                                       [[float(p[0]), float(p[1])] for p in ring]
                                       for ring in poly]},
                      "properties": {"name": f"{eez_country} EEZ",
                                     "stroke": "#0891b2", "fill-opacity": 0.05}})
    if grid:
        lat, lon, score = grid.get("lat"), grid.get("lon"), grid.get("score")
        if lat is not None and score is not None:
            for i in range(0, score.shape[0], step):
                for j in range(0, score.shape[1], step):
                    v = score[i, j]
                    if v is None or not np.isfinite(v):
                        continue
                    feats.append(_pt(lon[i, j], lat[i, j],
                                     {"pfz": round(float(v), 1), "kind": "grid"}))
    fc = {"type": "FeatureCollection", "features": feats}
    if provenance:
        fc["metadata"] = {"provenance": provenance,
                          "note": "MATSYA — real MOSDAC + MarineRegions data"}
    return fc


def write(fc, out_path):
    Path(out_path).write_text(json.dumps(fc, separators=(",", ":")),
                              encoding="utf-8")
    return str(out_path)
