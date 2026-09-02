"""
Agent 7 — SPECIES FORECASTER (rule-based)
SST / chlorophyll / coast-doori / season se kaunsi machhli mil sakti hai.
"""

from datetime import date

from .. import species as S
from .base import Agent
from .ocean_analytics import nearest_idx


class SpeciesForecaster(Agent):
    name = "species_forecaster"
    role = "Kaunsi machhli milegi (rule-based)"
    uses_llm = False

    def run(self, state):
        g = state.grids
        lat, lon = g["lat"], g["lon"]
        pt = None
        if state.target:
            i, j = nearest_idx(lat, lon, state.target["lat"], state.target["lon"])
            sst = g["sst"][i, j]
            chl = g.get("chl")
            dist = g.get("dist")
            pt = {
                "sst": float(sst) if sst == sst else None,
                "chl": float(chl[i, j]) if chl is not None and chl[i, j] == chl[i, j] else None,
                "coast_km": float(dist[i, j]) if dist is not None and dist[i, j] == dist[i, j] else None,
            }
        else:
            # poore grid ke best spot ke liye
            spots = state.meta.get("spots") or []
            if spots:
                s = spots[0]
                pt = {"sst": s.get("sst"), "chl": None, "coast_km": s.get("coast_km")}
        if not pt or pt.get("sst") is None:
            return {"status": "SKIP", "confidence": 0.2, "findings": {}, "evidence": [],
                    "text": "Species ke liye SST value chahiye — target point par data nahi mila"}

        ranked = S.rank(sst=pt["sst"], chl=pt["chl"], coast_km=pt["coast_km"])
        return {
            "status": "OK", "confidence": 0.7,
            "findings": {"conditions": pt, "species": ranked},
            "evidence": [self.ev("species", r["species"], f"{r['score']}/100", "rule-based")
                         for r in ranked[:3]],
            "text": "Sabse zyada sambhavna: " + ", ".join(
                f"{r['species']} ({r['score']:.0f})" for r in ranked[:3]),
        }
