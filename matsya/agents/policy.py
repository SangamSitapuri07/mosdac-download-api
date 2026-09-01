"""
Agent 5 — POLICY / REGULATORY RAG (deterministic knowledge base)

Yeh rules public government sources se compile kiye gaye hain. Har entry ke saath
`source` aur `verify=True` hai — kaanooni kaam se pehle state fisheries department /
official gazette se confirm zaroor kar lein (NOTES.md dekho).
"""

import re
from datetime import date

from .base import Agent

RULES = [
    {
        "id": "MONSOON_BAN",
        "title": "Monsoon fishing ban (uniform)",
        "text": "Har saal monsoon me mechanised fishing par rok. West coast: 15 June – 31 July "
                "(~47 din). East coast: 15 April – 14 June (61 din). Exact dates state-wise "
                "badalti hain — apne state ka notification dekho.",
        "tags": ["ban", "monsoon", "season", "mechanised"],
        "source": "Dept. of Fisheries, GoI / state marine fisheries notifications",
        "verify": True,
    },
    {
        "id": "IMBL",
        "title": "International Maritime Boundary Line (IMBL)",
        "text": "IMBL cross karna mana hai. Sri Lanka ya Pakistan ki taraf jaate waqt boundary "
                "se kam se kam 10–15 nautical mile doori rakho. Sri Lankan / Pakistan marine "
                "agencies boat aur crew ko pakad sakti hain.",
        "tags": ["imbl", "sri lanka", "pakistan", "border", "eez", "legal"],
        "source": "Indian Coast Guard advisories; Tamil Nadu Marine Fishing Regulation Act",
        "verify": True,
    },
    {
        "id": "KMFR",
        "title": "Kerala Marine Fishing Regulation Act, 1980",
        "text": "Kerala me zonation lagu hai: chhote/traditional craft ke liye paas ka ilaaka, "
                "mechanised trawlers ko aam taur par 3 nautical mile se aage rehna padta hai. "
                "Seasonal trawl ban bhi hota hai.",
        "tags": ["kerala", "trawl", "zonation", "kmfr", "law"],
        "source": "Kerala Marine Fishing Regulation Act 1980 + amendments",
        "verify": True,
    },
    {
        "id": "TNMFRA",
        "title": "Tamil Nadu Marine Fishing Regulation Act, 1983",
        "text": "Tamil Nadu me bhi 3 nautical mile tak traditional zone; mechanised boats uske "
                "aage. IMBL ke paas Palk Bay me navigation advisory lage rehte hain — VHF sunte raho.",
        "tags": ["tamil nadu", "palk bay", "zonation", "tnmfra", "law"],
        "source": "Tamil Nadu Marine Fishing Regulation Act 1983",
        "verify": True,
    },
    {
        "id": "ODISHA_TURTLE",
        "title": "Odisha — Olive Ridley conservation ban",
        "text": "Rushikulya, Devi aur Dhamara ke muhane ke aas-paas (lagbhag 20 km) November se "
                "May tak fishing ban rehta hai — Olive Ridley kachhue ke mass nesting ke karan.",
        "tags": ["odisha", "turtle", "olive ridley", "rushikulya", "ban"],
        "source": "Odisha Forest & Environment Dept./Wildlife notifications",
        "verify": True,
    },
    {
        "id": "ICG_DISTRESS",
        "title": "Emergency / distress",
        "text": "VHF Channel 16 par mayday bhejo. Indian Coast Guard MRCC (Mumbai) 24x7. "
                "Toll-free 1554. Apne registration number aur position (lat/lon) pehle se ready rakho.",
        "tags": ["emergency", "distress", "mayday", "vhf", "coast guard", "safety"],
        "source": "Indian Coast Guard — maritime safety SOPs",
        "verify": False,
    },
    {
        "id": "SIR_CREEK",
        "title": "Gujarat — Sir Creek / creek belt",
        "text": "Sir Creek aur creek belt security-sensitive area hai. Bina clearance mat jao; "
                "BSF aur Coast Guard ki checking hoti rehti hai.",
        "tags": ["gujarat", "sir creek", "security", "kutch"],
        "source": "Security advisories (Gujarat coast)",
        "verify": True,
    },
    {
        "id": "EEZ_RULE",
        "title": "India Exclusive Economic Zone (EEZ)",
        "text": "India EEZ = coast se 200 nautical mile tak. Iske andar Indian vessels ko fishing "
                "ka adhikar hai. Iske bahar (High Seas) ke liye RFMO/regional permission lagta hai.",
        "tags": ["eez", "legal", "permission", "high seas", "200"],
        "source": "UNCLOS; Maritime Zones of India Act 1976",
        "verify": False,
    },
]


def monsoon_status(today=None):
    d = today or date.today()
    md = d.month * 100 + d.day
    if 615 <= md <= 731:
        return {"coast": "West coast", "active": True,
                "text": f"[{d:%d %b}] WEST COAST monsoon ban chal raha hai (15 Jun – 31 Jul)"}
    if 415 <= md <= 614:
        return {"coast": "East coast", "active": True,
                "text": f"[{d:%d %b}] EAST COAST monsoon ban chal raha hai (15 Apr – 14 Jun)"}
    return {"coast": "-", "active": False,
            "text": f"[{d:%d %b}] Abhi monsoon ban active nahi hai"}


class PolicyRAG(Agent):
    name = "policy_rag"
    role = "Kaanoon / ban / emergency rules (knowledge base)"
    uses_llm = False

    def run(self, state):
        q = (state.user_query or "").lower()
        hits = []
        for r in RULES:
            score = sum(1 for t in r["tags"] if re.search(rf"\b{re.escape(t)}\b", q))
            if score:
                hits.append((score, r))

        ms = monsoon_status()
        # monsoon ban hamesha dikhao agar query me 'ban' ya 'monsoon' ho, ya ban active ho
        if ms["active"] or "ban" in q or "monsoon" in q:
            hits.append((3, {"id": "MONSOON_STATUS", "title": "Aaj ki ban status",
                             "text": ms["text"], "tags": ["ban", "monsoon"],
                             "source": "computed (date-based)", "verify": True}))

        # EEZ context from risk agent
        risk = state.results.get("risk_geofencing") or {}
        pt = (risk.get("findings") or {}).get("point") or {}
        if pt.get("in_india_eez") is False:
            hits.append((4, {"id": "HIGH_SEAS_WARN", "title": "High Seas chetavani",
                             "text": "Target point India EEZ ke bahar hai — bina permission "
                                     "wahan fishing karne par action ho sakta hai.",
                             "tags": ["eez"], "source": "computed + UNCLOS", "verify": True}))
        nf = (risk.get("findings") or {}).get("nearest_foreign_eez")
        if nf and nf.get("distance_km", 999) < 25:
            hits.append((5, {"id": "IMBL_PROXIMITY", "title": "Seema nazdik",
                             "text": f"Target se sirf {nf['distance_km']:.1f} km door "
                                     f"{nf['country']} ki EEZ hai — IMBL cross karne ka khatra.",
                             "tags": ["imbl"], "source": "MarineRegions v12", "verify": True}))

        hits.sort(key=lambda x: -x[0])
        seen, out = set(), []
        for s, r in hits:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            out.append(r)

        if not out:
            out = [r for r in RULES if r["id"] in ("EEZ_RULE", "ICG_DISTRESS")]

        return {
            "status": "OK", "confidence": 0.8 if hits else 0.5,
            "findings": {"rules": out, "count": len(out), "monsoon": ms},
            "evidence": [self.ev("policy", r["title"], r["text"][:90] + "…",
                                 r.get("source", "")) for r in out[:6]],
            "text": f"{len(out)} relevant niyam mile"
                    + (f" — sabse pehla: {out[0]['title']}" if out else ""),
        }
