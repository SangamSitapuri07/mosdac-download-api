# NOTES — kya complete hai, kya pending hai

> Ye file **pending kaamo ki list** hai. Jo cheezein abhi data/access issue se ruki hain,
> wo yahan likhi hain — code unko gracefully skip karta hai, crash nahi hota.

---

## ✅ COMPLETE (real data, kaam kar raha hai)

| # | Cheez | Source | Status |
|---|---|---|---|
| 1 | MOSDAC login / token | `POST /download_api/gettoken` | ✅ working |
| 2 | Dataset search (pagination) | `GET /apios/datasets.json` | ✅ working |
| 3 | File download + resume/retry | `GET /download_api/download` | ✅ working (Range resume + 5 retries) |
| 4 | SST ingest (INSAT-3DR L2B) | `3RIMG_L2B_SST` (35 files/day) | ✅ real |
| 5 | Sea wind ingest (INSAT-3DR L2P) | `3RIMG_L2P_VSW` (24 files/day) | ✅ real |
| 6 | HDF5 parsing (scale/fill/2D lat-lon) | h5py | ✅ real |
| 7 | Thermal fronts (°C/km gradient) | computed | ✅ real |
| 8 | India EEZ boundary + mask | MarineRegions EEZ v12 (VLIZ, CC BY 4.0) | ✅ real |
| 9 | Coastline + distance-from-coast | Natural Earth ne_50m (public domain) | ✅ real |
| 10 | PFZ score (front+SST+EEZ+shelf+wind) | computed | ✅ real |
| 11 | Interactive map (click → details) | static HTML + JS | ✅ working |
| 12 | Top-spot ranking + Google Maps links | computed | ✅ working |
| 13 | CSV / Excel / JSON export | — | ✅ working |
| 14 | Provenance table (kaunsa data kahan se) | — | ✅ working |

---

## ⏳ PENDING — data uplabdh nahi (complete karna hai)

### 1. 🔴 Chlorophyll-a (sabse important missing layer)
- **Kya chahiye:** Oceansat/EOS-06 OCM chlorophyll concentration (mg/m³)
- **Kyun:** PFZ ka doosra aadha hissa — fish wahan jama hote hain jahan chlorophyll zyada
- **Status:** MOSDAC API me **maujood nahi**
  - 15 dataset IDs try kiye (`E06OCM_L2C_CHL`, `O3OCM_L2C_CHL`, `E06OCM_L3A_CHL`, …) → sab HTTP 500
  - NASA CMR (IN/ISRO/MOSDAC) me sirf 20 collections hain — sirf INSAT (SST/OLR/wind/fog/snow)
- **Kaise complete karein:**
  1. MOSDAC admin ko mail (`admin@mosdac.gov.in`) — OCM chlorophyll ka datasetId poochhein
  2. Ya Bhuvan / NRSC portal (`bhuvan.nrsc.gov.in`) se OCM L2C CHL file manually download karke
     `data/` me daalein → `matsya/ingest.py` me `kind="chlorophyll"` add karein
  3. Ya Copernicus Marine Service (CMEMS) / NASA OceanColor — alag API key chahiye
- **Code me jagah:** `settings.json → datasets.chlorophyll` (abhi `null`),
  `physics.pfz_score()` me weight add karna hai

### 2. 🟡 Wind layer ki andaruni structure confirm karni hai
- `3RIMG_L2P_VSW` file download to ho jayegi, par uske andar ke dataset naam abhi **verify nahi hue**
  (mere paas wo file nahi thi)
- Code generic hai: `WindSpeed`/`wspd`/`speed` dhoondhta hai, warna `u`+`v` components se
  `sqrt(u²+v²)` bana leta hai, warna sabse bada 2D dataset le leta hai
- **Karein:** ek wind file download kar ke `python h5inspect.py data\...VSW....h5 --values` chalao,
  output dekho. Agar naam alag mile to `matsya/ingest.py::read_grid()` me preference list badhao

### 3. 🟡 SST front threshold validation
- `front_ref_c_per_km = 0.05` — literature-based estimate hai
- **Karein:** INCOIS ke asli PFZ advisories se compare karke threshold tune karein
  (INCOIS: <https://incois.gov.in/portal/datainfo/pfz.jsp>)

### 4. 🟡 NRT latency
- INSAT-3DR L2B SST ki processing latency ~1 ghanta hai (acquisition → product)
- General users ko L1 data 3 din ki latency par milta hai (L2 products NRT hain)
- **Karein:** agar aur real-time chahiye to MOSDAC admin se NRT access maangein

---

## 🔵 PENDING — features (baad me banane hain)

| # | Feature | Kaise banayenge | Priority |
|---|---|---|---|
| 1 | **Monsoon fishing ban** (61 din) | Fishing ban dates (state-wise) JSON me daal kar advisory me red flag | High |
| 2 | **Multi-day composite** | 3-7 din ke files ka median SST → cloud gaps kam | High |
| 3 | **Time-series / animation** | `monitor.py` already karta hai — MATSYA me merge karein | Medium |
| 4 | **AIS vessel tracking** | aisstream.io free API key (ORCA bhi yahi use karta hai) | Medium |
| 5 | **Bathymetry / shelf depth** | GEBCO grid (free) → shelf score behtar | Medium |
| 6 | **Species likelihood** | SST + chlorophyll + season se species rank (rule-based) | Low |
| 7 | **Coast Guard / INCOIS notices** | Web scrape ya manual JSON | Medium |
| 8 | **Live auto-update** | `monitor.py` ka scheduler MATSYA ke saath | Medium |
| 9 | **Mobile-friendly UI / PWA** | HTML responsive hai, PWA manifest add karein | Low |
| 10 | **Multilingual** (Hindi/Gujarati/Tamil) | Static translation strings | Low |



---

## 🤖 AGENTIC ARCHITECTURE (ORCA-style, par real data pe)

```
User query (Hindi/Hinglish/English)
        │
        ▼
┌───────────────────────────┐
│ 1. SUPERVISOR             │  intent + harbour gazetteer + "40 km SW" parsing
└──────────┬────────────────┘
           │ parallel wave 1
   ┌───────┴────────┐
   ▼                ▼
┌────────────┐  ┌──────────────────┐
│ 2. OCEAN   │  │ 3. RISK & GEO    │  SST/front/wind/PFZ   EEZ/IMBL/coast risk
│ ANALYTICS  │  │    FENCING       │  (numpy)              (point-in-polygon)
└─────┬──────┘  └────────┬─────────┘
      │  parallel wave 2 │
      ▼                  ▼
┌────────────┐    ┌──────────────┐
│ 4. NAVIGA- │    │ 5. POLICY    │  A* route: NM/ETA/fuel   monsoon ban, IMBL,
│   TION     │    │    RAG       │  (real grid par)         KMFR, TNMFRA, ICG SOPs
└─────┬──────┘    └──────┬───────┘
      └────────┬─────────┘
               ▼
      ┌─────────────────┐
      │ 6. SYNTHESIZER  │  Hinglish advisory + confidence + evidence
      └─────────────────┘
```

**ORCA ka golden rule follow kiya hai:** LLM sirf wahan jahan semantic/language kaam;
saare numbers aur spatial calculations deterministic Python me.

| Agent | LLM? | Deterministic core | Real data input |
|---|---|---|---|
| Supervisor | optional | regex + gazetteer (21 Indian harbours) | — |
| Ocean Analytics | **nahi** | numpy gradient / Gaussian scoring | INSAT-3DR SST + wind |
| Risk & Geofencing | **nahi** | matplotlib Path point-in-polygon | MarineRegions EEZ v12 |
| Navigation | **nahi** | A* (8-connected, wind/EEZ penalty) | SST + wind + EEZ grid |
| Policy RAG | optional | keyword+context retrieval | 8 real Indian rules |
| Synthesizer | optional | template + persona tone | sab agents ke findings |

Har run ki **execution_audit.jsonl** banati hai (ORCA ki tarah) —
`out/audit/execution_audit.jsonl` me har agent ka latency, status, confidence.

### Comparison with ORCA
| | ORCA | MATSYA |
|---|---|---|
| Orchestrator | LangGraph + Qwen 2.5 7B | **pure-Python DAG, zero dependency** (LLM optional) |
| Runs without GPU/LLM | nahi (LLM zaroori) | **haan — sab kuch offline chalta hai** |
| AIS vessels | simulated by default | **pending, real API se banayenge** (honest) |
| Geo DB | PostGIS + Docker | **Shapely-free point-in-polygon, static JSON** |
| Frontend | Next.js + Deck.GL | **single static HTML + stdlib server** |
| Install | Node + Docker + Postgres | **`pip install -r requirements.txt`** |

### Naye pending (agentic layer)
1. 🔴 **Chlorophyll-a** — abhi bhi unavailable (upar dekho)
2. 🟡 **Wind file structure verify** — `3RIMG_L2P_VSW` ke andar ke dataset names
3. 🟡 **AIS vessel traffic** — aisstream.io key (real, simulation nahi)
4. 🟡 **Ocean currents** — ORCA Copernicus NetCDF use karta hai; humein source chahiye
5. 🔵 **LLM synthesis** — `OPENAI_API_KEY` set karke chalao (optional, offline default hai)
6. 🔵 **Voice input (Bhashini)** — SIH ke liye achha feature
7. 🔵 **pgvector RAG** — policy docs zyada hone par

---

## 🆚 ORCA (SIH-26176) se comparison — hum behtar kaise hain

| Cheez | ORCA | MATSYA (hum) |
|---|---|---|
| Data | MOSDAC + Copernicus + Sentinel-3 + INCOIS (claim) | **MOSDAC live API — verified real download** |
| AIS vessels | **simulated** agar key na ho (unka README kehta hai) | abhi nahi hai, par jab banayenge to real API se |
| EEZ / geofencing | PostGIS + sovereign geofencing | **MarineRegions EEZ v12** — verified real boundaries |
| Stack | Next.js + FastAPI + PostGIS + Docker (bhari) | **Python + static HTML** — `pip install` aur chalao |
| Offline / air-gap | partial | **fully offline** (ek baar data aa jaye to) |
| Chlorophyll | claim | humne **honestly "PENDING"** likha hai |

**Humari line:** chhota, sachcha, chalne layak. Har number ke saath **provenance** likha hai —
kaunsa file, kab ka, kahan se aaya.

---

## 🧪 Testing note (developer ke liye)

Repo me **koi dummy/synthetic data nahi hai**. Development ke time grid structure verify karne ke
liye `/tmp` me asli file ke exact structure jaisi fixture banayi gayi thi
(`SST (1,2816,2805) float32, fill -999, units K` + `Latitude/Longitude int16 scale 0.01`) —
wo repo ka hissa nahi hai.

Asli data se verify karne ka tarika:
```powershell
python matsya.py run                 # MOSDAC se asli files
python h5inspect.py data --values    # structure confirm
```
