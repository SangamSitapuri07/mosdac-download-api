"""
Agent 3 — RISK & GEOFENCING (deterministic)
India EEZ ke andar/bahar, coast se doori, foreign EEZ / IMBL standoff, wind hazard.
"""

import numpy as np

from .. import geo_tools as G
from .. import physics as P
from .base import Agent
from .ocean_analytics import nearest_idx


class RiskGeofencing(Agent):
    name = "risk_geofencing"
    role = "EEZ / border / coast risk check (point-in-polygon)"
    uses_llm = False

    def run(self, state):
        g = state.grids
        lat, lon, eez, dist = g["lat"], g["lon"], g.get("eez"), g.get("dist")
        wind = g.get("wind")
        cfg = state.meta["cfg"]

        f, ev = {}, []
        if eez is not None:
            f["eez_pixels"] = int(eez.sum())
            f["eez_fraction"] = round(float(np.nansum(eez) / max(np.isfinite(g["sst"]).sum(), 1)), 3)

        # distance to nearest FOREIGN EEZ (proxy for IMBL standoff)
        foreign = [c for c in G.eez_names() if c != "India"]
        if foreign and state.target:
            la, lo = state.target["lat"], state.target["lon"]
            best_d, best_c = None, None
            for c in foreign:
                rings = G.eez_rings(c)[c]
                for poly in rings:
                    r = np.asarray(poly[0], dtype=float)
                    d = np.hypot(r[:, 0] - lo, (r[:, 1] - la) * np.cos(np.radians(la))) * 111.0
                    k = float(np.min(d))
                    if best_d is None or k < best_d:
                        best_d, best_c = k, c
            f["nearest_foreign_eez"] = {"country": best_c, "distance_km": round(best_d, 1)}
            if best_d < 10:
                f["border_alert"] = "CRITICAL"
            elif best_d < 25:
                f["border_alert"] = "CAUTION"
            else:
                f["border_alert"] = "CLEAR"
            ev.append(self.ev("border", f"{best_c} EEZ se doori",
                              f"{best_d:.1f} km ({f['border_alert']})", "MarineRegions"))

        # point-level risk
        pt = {}
        if state.target:
            i, j = nearest_idx(lat, lon, state.target["lat"], state.target["lon"])
            inz = bool(eez[i, j]) if eez is not None else None
            dkm = float(dist[i, j]) if dist is not None and np.isfinite(dist[i, j]) else None
            w = float(wind[i, j]) if wind is not None and np.isfinite(wind[i, j]) else None
            pt = {"in_india_eez": inz, "coast_km": round(dkm, 1) if dkm is not None else None,
                  "wind_ms": round(w, 1) if w is not None else None}
            if w is not None:
                pt["sea_state"], pt["sea_color"] = P.sea_state_label(w, cfg)

            level, reasons = "LOW", []
            if inz is False:
                level = "HIGH"
                reasons.append("Ye jagah **India EEZ ke bahar** hai (international waters ya kisi aur desh ka zone)")
            if w is not None and w >= cfg["physics"]["wind_danger_ms"]:
                level = "CRITICAL"
                reasons.append(f"Hawa **{w:.1f} m/s** — toofani, mat jao")
            elif w is not None and w >= cfg["physics"]["wind_caution_ms"] and level != "CRITICAL":
                level = "MEDIUM"
                reasons.append(f"Hawa **{w:.1f} m/s** — dhyaan rakhein")
            if f.get("border_alert") == "CRITICAL":
                level = "CRITICAL"
                reasons.append(f"Sirf {f['nearest_foreign_eez']['distance_km']} km door "
                               f"{f['nearest_foreign_eez']['country']} ki seema — cross mat karo")
            if dkm is not None and dkm > 200 and level == "LOW":
                level = "MEDIUM"
                reasons.append(f"Coast se {dkm:.0f} km door — chhoti boat ke liye theek nahi")
            pt["risk_level"] = level
            pt["reasons"] = reasons or ["Koi bada khatra nahi mila"]
            f["point"] = pt
            ev.append(self.ev("eez", "India EEZ", "andar" if inz else "bahar", "MarineRegions v12"))
            if dkm is not None:
                ev.append(self.ev("coast", "Coast se doori", f"{dkm:.0f} km", "Natural Earth"))

        return {
            "status": "OK", "confidence": 0.9,
            "findings": f, "evidence": ev,
            "text": (f"Risk {pt.get('risk_level','?')}: "
                     f"{'EEZ ke andar' if pt.get('in_india_eez') else 'EEZ ke bahar'}, "
                     f"coast se {pt.get('coast_km')} km"
                     + (f", hawa {pt.get('wind_ms')} m/s" if pt.get('wind_ms') else ""))
                    if pt else f"Grid me EEZ coverage {f.get('eez_fraction')}",
        }
