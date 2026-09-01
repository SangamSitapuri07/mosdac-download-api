"""
Agent 1 — SUPERVISOR & ORCHESTRATOR
Natural language query -> intent + origin/target coordinates + task plan.

Deterministic by default (zero LLM, offline). Agar OPENAI_API_KEY / compatible
endpoint set ho to LLM se intent bhi nikalwa sakta hai (--llm flag).
"""

import math
import re

from .base import Agent

# REAL Indian fishing harbours / landing centres (lat, lon) - gazetteer
HARBOURS = {
    "veraval": (20.902, 70.368, "Gujarat"),
    "porbandar": (21.641, 69.629, "Gujarat"),
    "mangrol": (21.117, 70.107, "Gujarat"),
    "okha": (22.468, 69.077, "Gujarat"),
    "dwarka": (22.240, 68.970, "Gujarat"),
    "bhavnagar": (21.764, 72.152, "Gujarat"),
    "gandhidham": (22.993, 70.215, "Gujarat"),
    "mumbai": (18.927, 72.836, "Maharashtra"),
    "sassoon dock": (18.927, 72.836, "Maharashtra"),
    "ratnagiri": (16.994, 73.300, "Maharashtra"),
    "karwar": (14.813, 74.128, "Karnataka"),
    "mangalore": (12.914, 74.836, "Karnataka"),
    "kochi": (9.931, 76.267, "Kerala"),
    "kollam": (8.893, 76.586, "Kerala"),
    "kozhikode": (11.248, 75.780, "Kerala"),
    "kanyakumari": (8.088, 77.539, "Tamil Nadu"),
    "tuticorin": (8.764, 78.135, "Tamil Nadu"),
    "rameswaram": (9.288, 79.313, "Tamil Nadu"),
    "nagapattinam": (10.767, 79.842, "Tamil Nadu"),
    "chennai": (13.104, 80.301, "Tamil Nadu"),
    "kakinada": (16.989, 82.247, "Andhra Pradesh"),
    "visakhapatnam": (17.686, 83.295, "Andhra Pradesh"),
    "paradip": (20.317, 86.611, "Odisha"),
    "digha": (21.626, 87.508, "West Bengal"),
    "kavaratti": (10.566, 72.636, "Lakshadweep"),
    "port blair": (11.623, 92.727, "Andaman & Nicobar"),
}

DIRS = {
    "north": (1, 0), "uttar": (1, 0), "upar": (1, 0),
    "south": (-1, 0), "dakshin": (-1, 0), "neeche": (-1, 0),
    "east": (0, 1), "purab": (0, 1), "e": (0, 1),
    "west": (0, -1), "paschim": (0, -1), "w": (0, -1),
    "ne": (0.707, 0.707), "nw": (0.707, -0.707),
    "se": (-0.707, 0.707), "sw": (-0.707, -0.707),
    "southeast": (-0.707, 0.707), "southwest": (-0.707, -0.707),
    "northeast": (0.707, 0.707), "northwest": (0.707, -0.707),
}

INTENT_WORDS = {
    "FIND_FISHING_ZONE": ["machhli", "machli", "fish", "fishing", "shikar", "pfz",
                          "kahaan", "kahan", "where", "best", "spot", "zone", "catch"],
    "CHECK_SAFETY": ["safe", "surakshit", "khatra", "danger", "toofan", "storm",
                     "wind", "hawa", "sea state", "rough", "samundar kaisa"],
    "POLICY_QUERY": ["ban", "rule", "niyam", "law", "kanoon", "policy", "imbl",
                     "eez", "legal", "permission", "monsoon"],
    "NAVIGATE": ["route", "distance", "kitna door", "kitni door", "time", "fuel",
                 "kitna samay", "paani", "reach"],
}


class Supervisor(Agent):
    name = "supervisor"
    role = "Intent + jagah samajhna (query -> plan)"
    uses_llm = False

    def run(self, state):
        q = (state.user_query or "").lower()
        ev = []

        # ---- intent ----
        scores = {k: sum(1 for w in v if w in q) for k, v in INTENT_WORDS.items()}
        intent = max(scores, key=lambda k: scores[k]) if max(scores.values()) > 0 \
            else "FIND_FISHING_ZONE"

        # ---- origin harbour ----
        origin = None
        for name, (la, lo, st) in HARBOURS.items():
            if re.search(rf"\b{re.escape(name)}\b", q):
                origin = {"name": name.title(), "lat": la, "lon": lo, "state": st}
                ev.append(self.ev("origin", "Home harbour", f"{name.title()} ({st})",
                                  "gazetteer"))
                break
        if origin is None and state.origin:
            origin = state.origin

        # ---- explicit coordinates in query? ----
        target = state.target
        m = re.search(r"(-?\d+\.?\d*)\s*[,\s]\s*(-?\d+\.?\d*)", q)
        if m and not target:
            try:
                a, b = float(m.group(1)), float(m.group(2))
                la, lo = (a, b) if abs(a) <= 90 else (b, a)
                target = {"lat": la, "lon": lo, "label": "query se"}
                ev.append(self.ev("target", "Coordinates", f"{la:.3f}, {lo:.3f}", "query"))
            except Exception:
                pass

        # ---- "Veraval se 40 km SW" ----
        if origin and not target:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(km|kilometer|kilometre|nautical|nm)", q)
            dist_km = float(m.group(1)) * (1.852 if m.group(2) in ("nautical", "nm") else 1.0) \
                if m else None
            direc = None
            # direction sirf distance ke BAAD wale hisson me dhoondo
            # ("Veraval se 40 km SW" me "se" Hindi ka "from" hai, compass nahi)
            after = q[m.end():] if m else q
            for d in ("southwest", "sw", "nw", "ne", "northwest", "northeast",
                      "north", "south", "east", "west", "uttar", "dakshin",
                      "purab", "paschim"):
                if re.search(rf"\b{re.escape(d)}\b", after):
                    direc = d[:2] if d in ("southwest", "northwest", "northeast",
                                           "southeast") else d
                    break
            if dist_km:
                dlat, dlon = DIRS.get(direc, (1, 0))
                dla = dlat * dist_km / 111.0
                dlo = dlon * dist_km / (111.0 * math.cos(math.radians(origin["lat"])))
                target = {"lat": round(origin["lat"] + dla, 4),
                          "lon": round(origin["lon"] + dlo, 4),
                          "label": f"{origin['name']} se {dist_km:.0f} km {direc or 'N'}"}
                ev.append(self.ev("target", "Target",
                                  f"{target['lat']:.3f}, {target['lon']:.3f}", "bearing+range"))

        # ---- tasks ----
        tasks = ["ocean_analytics", "risk_geofencing", "policy_rag"]
        if intent in ("FIND_FISHING_ZONE", "NAVIGATE"):
            tasks.append("navigation")
        if intent == "NAVIGATE":
            tasks.insert(0, "navigation")
        if intent == "POLICY_QUERY":
            tasks = ["policy_rag", "risk_geofencing"]
        tasks.append("synthesizer")

        state.intent, state.origin, state.target, state.tasks = intent, origin, target, tasks

        return {
            "status": "OK", "confidence": 0.9 if origin or target else 0.6,
            "findings": {"intent": intent, "origin": origin, "target": target, "tasks": tasks},
            "evidence": ev,
            "text": f"Intent = {intent.replace('_',' ').title()}; "
                    f"origin = {origin['name'] if origin else '—'}; "
                    f"target = {target['label'] if target else 'poora grid'}; "
                    f"{len(tasks)} agents chalenge",
        }
