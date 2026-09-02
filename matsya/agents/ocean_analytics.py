"""
Agent 2 — OCEAN ANALYTICS (deterministic, koi LLM nahi)
Real INSAT-3DR grids se: SST, thermal fronts, wind, sea state, PFZ score.
"""

import numpy as np

from .. import physics as P
from .base import Agent


def nearest_idx(lat, lon, la, lo):
    d = (lat - la) ** 2 + ((lon - lo) * np.cos(np.radians(la))) ** 2
    i, j = np.unravel_index(np.nanargmin(d), d.shape)
    return int(i), int(j)


class OceanAnalytics(Agent):
    name = "ocean_analytics"
    role = "SST / fronts / wind / PFZ nikalna (pure numpy)"
    uses_llm = False

    def run(self, state):
        g = state.grids
        sst, grad, lat, lon = g["sst"], g["grad"], g["lat"], g["lon"]
        wind, dist, eez = g.get("wind"), g.get("dist"), g.get("eez")
        chl = g.get("chl")
        cfg = state.meta["cfg"]

        score = P.pfz_score(sst, grad, eez, dist, wind, cfg, chl=chl)
        state.grids["score"] = score

        valid = int(np.isfinite(sst).sum())
        f = {
            "sst_min_c": round(float(np.nanmin(sst)), 2),
            "sst_max_c": round(float(np.nanmax(sst)), 2),
            "sst_mean_c": round(float(np.nanmean(sst)), 2),
            "front_max_c_per_km": round(float(np.nanmax(grad)), 4),
            "front_mean_c_per_km": round(float(np.nanmean(grad)), 4),
            "valid_pixels": valid,
            "pfz_mean": round(float(np.nanmean(score)), 1),
            "pfz_max": round(float(np.nanmax(score)), 1),
            "strong_front_pixels": int((grad >= cfg["physics"]["front_ref_c_per_km"]).sum()),
        }
        if chl is not None:
            f.update({"chl_mean_mg_m3": round(float(np.nanmean(chl)), 3),
                      "chl_max_mg_m3": round(float(np.nanmax(chl)), 3)})
        if wind is not None:
            f.update({"wind_mean_ms": round(float(np.nanmean(wind)), 2),
                      "wind_max_ms": round(float(np.nanmax(wind)), 2)})

        ev = [self.ev("sst", "SST range", f"{f['sst_min_c']}–{f['sst_max_c']} °C",
                      state.meta.get("sst_file", "")),
              self.ev("front", "Max thermal front", f"{f['front_max_c_per_km']} °C/km", "computed")]
        if chl is not None:
            ev.append(self.ev("chl", "Chlorophyll (mean)",
                              f"{f['chl_mean_mg_m3']} mg/m³", state.meta.get("chl_file", "")))
        if wind is not None:
            ev.append(self.ev("wind", "Wind max", f"{f['wind_max_ms']} m/s",
                              state.meta.get("wind_file", "")))

        # point query
        pt = {}
        if state.target:
            i, j = nearest_idx(lat, lon, state.target["lat"], state.target["lon"])
            w = float(wind[i, j]) if wind is not None and np.isfinite(wind[i, j]) else None
            pt = {"lat": round(float(lat[i, j]), 3), "lon": round(float(lon[i, j]), 3),
                  "sst_c": round(float(sst[i, j]), 2) if np.isfinite(sst[i, j]) else None,
                  "front_c_per_km": round(float(grad[i, j]), 4) if np.isfinite(grad[i, j]) else None,
                  "wind_ms": round(w, 1) if w else None,
                  "pfz": round(float(score[i, j]), 1) if np.isfinite(score[i, j]) else None,
                  "chl_mg_m3": round(float(chl[i, j]), 3) if chl is not None and np.isfinite(chl[i, j]) else None,
                  "idx": (i, j)}
            if w is not None:
                pt["sea_state"] = P.sea_state_label(w, cfg)[0]
            f["point"] = pt

        best = P.top_spots(score, lat, lon, sst, grad, wind, dist, eez,
                           n=cfg["advisory"]["top_spots"])
        state.meta["spots"] = best

        return {
            "status": "OK", "confidence": 0.95, "findings": f, "evidence": ev,
            "text": f"SST {f['sst_min_c']}–{f['sst_max_c']} °C, max front "
                    f"{f['front_max_c_per_km']} °C/km, best PFZ {f['pfz_max']}/100. "
                    f"{len(best)} top spots mile."
                    + (f" Query point: {pt.get('sst_c')} °C, PFZ {pt.get('pfz')}." if pt else ""),
        }
