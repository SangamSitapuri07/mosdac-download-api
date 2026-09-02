"""
SPECIES LIKELIHOOD — rule-based (deterministic).

Indian waters ke commercial species ke liye SST / chlorophyll / coast-doori /
season ke windows. Yeh ecological references par adharit hain (CMFRI-ish ranges);
exact scientific validation pending hai — NOTES.md me likha hai.
"""

from datetime import date

# name, (sst_min, sst_max), (coast_km_min, coast_km_max), (chl_min, chl_max), season_months, note
SPECIES = [
    ("Tuna (Yellowfin)", (26, 30.5), (40, 400), (0.1, 1.5), None,
     "Strong thermal fronts ke paas milta hai; FADs ke aas-paas bhi."),
    ("Seerfish (King mackerel)", (27, 31), (20, 250), (0.15, 2.0), None,
     "Shelf break aur fronts dono pasand."),
    ("Pomfret (Black/Silver)", (26, 30), (10, 120), (0.3, 3.0), None,
     "Continental shelf, thoda turbid paani."),
    ("Ribbonfish (Trichiurus)", (25, 29.5), (5, 100), (0.3, 4.0), None,
     "Monsoon ke baad bhookamp; nearshore shelf."),
    ("Indian Mackerel", (26.5, 29.5), (2, 80), (0.5, 5.0), None,
     "Upwelling zones, high chlorophyll."),
    ("Oil Sardine", (24, 29), (2, 60), (0.5, 6.0), None,
     "Kerala/Karnataka upwelling (Jun-Sep) me bumper."),
    ("Shrimp (Penaeid)", (26, 31), (1, 50), (0.5, 8.0), None,
     "Nearshore/muddy bottom; monsoon ke baad season."),
    ("Squid / Cuttlefish", (25, 30), (10, 200), (0.2, 3.0), None,
     "Shelf edge, clear water."),
    ("Anchovy / Stolephorus", (26, 30), (1, 40), (0.5, 6.0), None,
     "Coastal upwelling, lights se attract."),
    ("Hilsa (Tenualosa)", (25, 30), (1, 60), (0.5, 5.0), (6, 10),
     "Monsoon me nadi ke muhane par (Jun-Oct)."),
    ("Grouper / Snapper", (26, 30), (30, 300), (0.05, 1.5), None,
     "Reef/rocky bottom, offshore islands."),
    ("Bombay Duck", (26, 30), (5, 70), (0.5, 6.0), (9, 3),
     "Gujarat/Maharashtra, monsoon-ke-baad (Sep-Mar)."),
]


def _in(v, lo, hi):
    return lo <= v <= hi


def _season_ok(months, today=None):
    if not months:
        return True, None
    d = today or date.today()
    a, b = months
    ok = (a <= d.month <= b) if a <= b else (d.month >= a or d.month <= b)
    return ok, f"{a:02d}-{b:02d}"


def rank(sst=None, chl=None, coast_km=None, today=None, top=5):
    """conditions ke hisaab se species rank karo (0-100)."""
    out = []
    for name, (t1, t2), (c1, c2), (h1, h2), season, note in SPECIES:
        score, why = 0.0, []

        if sst is not None:
            if _in(sst, t1, t2):
                score += 40
                why.append(f"SST {sst:.1f}°C range me")
            else:
                gap = min(abs(sst - t1), abs(sst - t2))
                score += max(0, 40 - gap * 12)
                why.append(f"SST {sst:.1f}°C thoda bahar ({t1}-{t2})")
        else:
            score += 25

        if coast_km is not None:
            if _in(coast_km, c1, c2):
                score += 25
                why.append(f"coast se {coast_km:.0f} km theek")
            else:
                gap = min(abs(coast_km - c1), abs(coast_km - c2))
                score += max(0, 25 - gap * 0.25)
        else:
            score += 15

        if chl is not None:
            if _in(chl, h1, h2):
                score += 25
                why.append(f"chlorophyll {chl:.2f} mg/m³ achha")
            else:
                score += max(0, 25 - min(abs(chl - h1), abs(chl - h2)) * 15)
        else:
            score += 10

        ok, win = _season_ok(season, today)
        if ok:
            score += 10
            if win:
                why.append(f"season {win} chal raha hai")
        else:
            why.append(f"season {win} nahi hai")

        out.append({"species": name, "score": round(min(score, 100), 1),
                    "reasons": why, "note": note})
    out.sort(key=lambda x: -x["score"])
    return out[:top]
