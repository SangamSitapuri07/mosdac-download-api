"""
Agent 4 — NAVIGATION ENGINE (deterministic A*)
Real SST/wind/EEZ grid par A* route: hawa aur EEZ-ke-bahar ko penalty,
land/cloud ko detour. Nautical miles, ETA, fuel estimate.
"""

import heapq
import math

import numpy as np

from .base import Agent
from .ocean_analytics import nearest_idx

KN = 1.852                      # km in one nautical mile
CRUISE_KN = 8.0                 # chhoti fishing boat ki typical speed
FUEL_L_PER_NM = 3.0             # approx diesel (8-12 m trawler)


def astar(lat, lon, wind, eez, sst, start, goal, cfg):
    """8-connected A*; returns (path[(i,j)], cost_km) ya (None, None)."""
    ny, nx = sst.shape
    h = lambda a, b: math.hypot(lat[b] - lat[a], (lon[b] - lon[a]) *
                                math.cos(math.radians(lat[a]))) * 111.0

    def cell_cost(i, j):
        c = 1.0
        if wind is not None and np.isfinite(wind[i, j]):
            c += 2.0 * min(wind[i, j], 25.0) / 20.0          # tez hawa me dhima
        if eez is not None and not eez[i, j]:
            c += 3.0                                          # EEZ ke bahar penalty
        if not np.isfinite(sst[i, j]):
            c += 8.0                                          # zameen / cloud -> detour
        return c

    openq = [(h(start, goal), 0.0, start)]
    came, g = {}, {start: 0.0}
    seen = set()
    while openq:
        _, gc, cur = heapq.heappop(openq)
        if cur == goal:
            break
        if cur in seen:
            continue
        seen.add(cur)
        i, j = cur
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di == dj == 0:
                    continue
                ni, nj = i + di, j + dj
                if not (0 <= ni < ny and 0 <= nj < nx):
                    continue
                if lat[ni, nj] != lat[ni, nj] or lon[ni, nj] != lon[ni, nj]:
                    continue
                step = h((i, j), (ni, nj))
                ng = gc + step * cell_cost(ni, nj)
                if ng < g.get((ni, nj), 1e18):
                    g[(ni, nj)] = ng
                    came[(ni, nj)] = cur
                    heapq.heappush(openq, (ng + h((ni, nj), goal), ng, (ni, nj)))
    if goal not in came and goal != start:
        return None, None
    path, cur = [goal], goal
    while cur in came:
        cur = came[cur]
        path.append(cur)
    path.reverse()
    return path, g.get(goal, 0.0)


class Navigation(Agent):
    name = "navigation"
    role = "A* route: doori, samay, fuel (real grid par)"
    uses_llm = False

    def run(self, state):
        g = state.grids
        lat, lon, sst = g["lat"], g["lon"], g["sst"]
        wind, eez = g.get("wind"), g.get("eez")

        if not state.origin or not state.target:
            return {"status": "SKIP", "confidence": 0.0, "findings": {}, "evidence": [],
                    "text": "Route ke liye origin (harbour) aur target dono chahiye — "
                            "query me harbour ka naam bolo, jaise 'Veraval se 40 km SW'"}

        si, sj = nearest_idx(lat, lon, state.origin["lat"], state.origin["lon"])
        ti, tj = nearest_idx(lat, lon, state.target["lat"], state.target["lon"])
        path, cost = astar(lat, lon, wind, eez, sst, (si, sj), (ti, tj), state.meta["cfg"])
        if not path:
            return {"status": "NO_ROUTE", "confidence": 0.3, "findings": {}, "evidence": [],
                    "text": "Is grid me rasta nahi mila (shayad target bahut door ya landlocked)"}

        # ASLI (geometric) doori - penalty cost se alag
        def _geo(a, b):
            return math.hypot(lat[b] - lat[a],
                              (lon[b] - lon[a]) * math.cos(math.radians(lat[a]))) * 111.0
        geo = sum(_geo(path[k], path[k + 1]) for k in range(len(path) - 1))
        direct = _geo((si, sj), (ti, tj))
        nm = geo / KN
        cost = geo
        hrs = nm / CRUISE_KN
        route = [[round(float(lat[i, j]), 4), round(float(lon[i, j]), 4)] for i, j in path]
        line = {"type": "LineString", "coordinates": [[p[1], p[0]] for p in route]}

        f = {
            "from": state.origin["name"],
            "to": f"{lat[ti, tj]:.3f}, {lon[ti, tj]:.3f}",
            "route_km": round(geo, 1), "route_nm": round(nm, 1),
            "detour_km": round(geo - direct, 1),
            "direct_km": round(direct, 1),
            "eta_hours": round(hrs, 1),
            "eta_text": f"{int(hrs)} ghante {int((hrs % 1) * 60)} minute",
            "fuel_litres": round(nm * FUEL_L_PER_NM, 0),
            "saving_pct": round(max(0.0, (1 - direct / max(cost, 1e-6)) * -100), 1),
            "waypoints": len(route),
        }
        state.meta["route"] = line
        return {
            "status": "OK", "confidence": 0.85, "findings": f,
            "evidence": [self.ev("route", "Distance", f"{f['route_nm']} nautical mile "
                                 f"({f['route_km']} km)", "A* on INSAT grid"),
                         self.ev("eta", "ETA", f"{f['eta_text']} @ {CRUISE_KN} knots", "computed"),
                         self.ev("fuel", "Diesel (approx)", f"~{f['fuel_litres']:.0f} L",
                                 f"{FUEL_L_PER_NM} L/NM rule of thumb")],
            "text": f"{state.origin['name']} se {f['route_nm']} NM ({f['route_km']} km), "
                    f"ETA {f['eta_text']}, lagbhag {f['fuel_litres']:.0f} L diesel.",
        }
