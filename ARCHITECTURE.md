# 🏗️ MATSYA — System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          DATA INGEST (real)                               │
│  MOSDAC API ──► 3RIMG_L2B_SST (SST)   ─┐                                 │
│              ──► 3RIMG_L2P_VSW (wind) ─┤  HDF5 → scale/fill/2D lat-lon   │
│  local file ──► *CHL*/OCM (optional)  ─┤  crop → bbox → downsample       │
│  MarineRegions WFS ──► EEZ v12        ─┤  point-in-polygon               │
│  Natural Earth ──► coastline          ─┘  cKDTree distance               │
└───────────────────────────┬──────────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     GRIDS (numpy, in AgentState)                          │
│   sst(°C)  grad(°C/km)  wind(m/s)  chl(mg/m³)  dist(km)  eez(mask)       │
└───────────────────────────┬──────────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        7-AGENT SWARM (DAG)                               │
│                                                                          │
│   ┌────────────┐                                                         │
│   │ SUPERVISOR │  intent · 21-harbour gazetteer · "40 km SW" parser      │
│   └─────┬──────┘                                                         │
│         │  wave 1 (parallel)                                             │
│   ┌─────┴──────────────┬──────────────────────┐                          │
│   ▼                    ▼                                                 │
│ ┌──────────────┐  ┌──────────────────┐                                   │
│ │ OCEAN        │  │ RISK & GEOFENCE  │  fronts/PFZ   EEZ/IMBL/coast      │
│ │ ANALYTICS    │  │                  │  wind/sea     border alert        │
│ └──────┬───────┘  └────────┬─────────┘                                   │
│        │  wave 2 (parallel)│                                             │
│   ┌────┴───────┬───────────┴────────┐                                    │
│   ▼            ▼                    ▼                                    │
│ ┌────────┐ ┌──────────┐ ┌────────────────────┐                           │
│ │NAVIGA- │ │ POLICY   │ │ SPECIES FORECASTER │  A* route    rules/RAG    │
│ │TION    │ │ RAG      │ │                    │  NM/ETA/fuel  ban/IMBL    │
│ └────┬───┘ └────┬─────┘ └─────────┬──────────┘              species     │
│      └──────────┴─────────────────┘                                      │
│                     ▼                                                    │
│              ┌─────────────┐                                             │
│              │ SYNTHESIZER │  Hinglish verdict + confidence + evidence   │
│              └──────┬──────┘                                             │
└─────────────────────┼────────────────────────────────────────────────────┘
                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                            OUTPUTS                                       │
│  tactical.html (command center) · index.html · PNG maps · CSV · Excel    │
│  GeoJSON (QGIS/Google Earth) · animation.gif · timeseries.png            │
│  summary.json · audit/execution_audit.jsonl                              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Design principle (ORCA ka rule, follow kiya)

> **"Only use LLMs where semantic reasoning or language synthesis is required;
> use deterministic code for numerical and spatial calculations."**

| Agent | LLM? | Deterministic core | Latency (typ.) |
|---|---|---|---|
| Supervisor | optional | regex + gazetteer | ~1 ms |
| Ocean Analytics | **nahi** | numpy gradient / Gaussian | ~30 ms |
| Risk & Geofencing | **nahi** | `matplotlib.path` point-in-polygon | ~8 ms |
| Navigation | **nahi** | A* (8-connected) | ~5 ms |
| Policy RAG | optional | keyword + context retrieval | ~1 ms |
| Species Forecaster | **nahi** | ecological rule windows | ~2 ms |
| Synthesizer | optional | template + persona tone | ~0.1 ms |

**Total ~50 ms, bina GPU / internet / LLM ke.**

---

## Modules

| File | Kaam |
|---|---|
| `matsya/ingest.py` | MOSDAC download + HDF5 (scale/fill/2D lat-lon) |
| `matsya/composite.py` | multi-file median, time-series, animation GIF |
| `matsya/chlorophyll.py` | optional CHL layer (HDF5/NetCDF/GeoTIFF) |
| `matsya/geo_tools.py` | EEZ mask, coast distance |
| `matsya/physics.py` | fronts, sea state, PFZ score |
| `matsya/species.py` | species likelihood rules |
| `matsya/ais.py` | AISSTREAM live vessels (real only) |
| `matsya/export.py` | GeoJSON |
| `matsya/report.py` | HTML v1 + PNG + CSV/Excel |
| `matsya/report_v2.py` | tactical command center |
| `matsya/server.py` | stdlib HTTP + `/api/ask` |
| `matsya/orchestrator.py` | DAG + waves + audit log |

---

## PFZ scoring

```
score = Σ(weight_i × layer_i) / Σ(weight_i) × 100

front  (30)  SST gradient; 0.05 °C/km = strong front
sst    (25)  Gaussian around 28 °C (σ 3.2)
chl    (17)  log-normal peak 0.6 mg/m³   ← agar uplabdh ho
eez    (12)  andar = 1.0, bahar = 0.15
shelf  (8)   coast se 120 km ke andar
wind   (8)   <6 m/s = 1.0, >14 m/s = 0.0
```

**Jo layer uplabdh nahi hai, uska weight baaki layers me baant diya jata hai** —
isliye chlorophyll na hone par score artificially kam nahi hota.

---

## Reliability / honesty

- Har output ke saath **provenance table** (file + acquisition time + source)
- Jo data nahi mila → **"PENDING"** likha jata hai, chhupaya nahi jata
- AIS **kabhi simulate nahi hota** (ORCA simulation karta hai)
- Agent execution **audit log** (JSONL) — har run ka trace

---

## Extensibility

Naya agent banana ho to:
1. `matsya/agents/<name>.py` me `Agent` subclass banao (`run(state) -> dict`)
2. `orchestrator.AGENTS` me register karo
3. `orchestrator.WAVES` me sahi wave me daalo
4. `report_v2.py` ke `AG` / `EDGES` me node add karo (mesh me dikhega)
