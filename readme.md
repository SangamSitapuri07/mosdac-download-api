# 🐟 MATSYA — Real-Data Marine Fishing Advisory

**ISRO MOSDAC satellites + MarineRegions EEZ + Natural Earth coastline se bana
100% real-data fishing advisory system. Koi bhi dummy/simulated data nahi.**

```
python matsya.py run          # MOSDAC se ASLI data lao, analysis karo, report banao
start out\index.html          # browser me kholo, map pe CLICK karo
```

---

## 🎯 Ye karta kya hai

1. **MOSDAC API** se INSAT-3DR ki **SST** (Sea Surface Temperature) aur **sea wind** files download karta hai
2. Unse **thermal fronts** (SST gradient), **EEZ zone**, **coast se doori**, **wind/sea state** nikalta hai
3. Sab mila kar **PFZ score (0–100)** banata hai → "yahan jana chahiye ya nahi"
4. **Interactive HTML report** banata hai — map pe click karo, us jagah ka poora analysis
5. **Top 12 fishing spots** deta hai (coordinates + Google Maps link)
6. CSV / Excel / JSON export + **provenance table** (kaunsa data kahan se aaya)

---

## ⚡ Quick start

```powershell
pip install -r requirements.txt
copy .env.example .env
notepad .env            # MOSDAC_USER aur MOSDAC_PASS bharo
python matsya.py run
start out\index.html
```

Pehle apne credentials verify kar lo:
```powershell
python apitest.py
```

---

## 🛰️ Data sources (sab real)

| Layer | Source | Dataset / File | License |
|---|---|---|---|
| SST | ISRO MOSDAC (INSAT-3DR IMAGER) | `3RIMG_L2B_SST` (~35 files/day) | MOSDAC ToU |
| Sea wind | ISRO MOSDAC (INSAT-3DR IMAGER) | `3RIMG_L2P_VSW` (~24 files/day) | MOSDAC ToU |
| EEZ boundary | MarineRegions / VLIZ | `geo/eez.json` (EEZ v12, 2023-10-25) | CC BY 4.0 |
| Coastline | Natural Earth | `geo/coastline.json` (ne_50m) | Public domain |

🌊 **Chlorophyll-a uplabdh NAHI hai** MOSDAC API me — isliye score me shamil nahi.
Detail: [`NOTES.md`](NOTES.md)

---

## 🧠 PFZ score kaise banta hai

```
Thermal front  (35)  SST gradient; 0.05 °C/km = strong front
SST optimum    (30)  28 °C ke aas-paas Gaussian peak (σ = 3.2)
EEZ            (15)  India EEZ ke andar = 100%, bahar = 15%
Shelf          (10)  coast se 120 km ke andar behtar
Wind           (10)  <6 m/s shant, >14 m/s khatra
─────────────────────────────────────────────
70-100  →  🟢 JAO - best zone
55-70   →  🟡 THEEK HAI
40-55   →  🟠 SHAYAD
<40     →  🔴 MAT JAO
```

Ye INCOIS PFZ (Potential Fishing Zone) ke approach par adharit hai:
**SST front + SST range + chlorophyll**. Chlorophyll nahi milne ke karan uski jagah
EEZ + shelf + wind weights use kiye gaye hain (documented in NOTES.md).

---

## 📁 Project structure

```
matsya/
  __init__.py      package info
  config.py        settings.json loading + paths
  ingest.py        MOSDAC download + HDF5 reading (SST/wind/generic)
  geo_tools.py     EEZ mask (point-in-polygon), coast distance
  physics.py       gradient/fronts, wind/sea-state, PFZ score, top spots
  report.py        HTML (interactive) + PNG maps + CSV + Excel
  cli.py           commands: run / ingest / datasets
matsya.py          entry point
settings.json      sab parameters (region, weights, datasets)
geo/               eez.json, coastline.json (real geospatial data)
build_geo.py       MarineRegions WFS + Natural Earth se geo/ banata hai
h5inspect.py       HDF5 file inspector (structure dekhne ke liye)
mosdac_client.py   MOSDAC API client (login/search/download/resume)
toolkit.py         single-file analysis + dashboard
monitor.py         live auto-updating monitor
fishing.py         lightweight fishing advisory (SST only)
```

---

## 🎮 Commands

```powershell
python matsya.py run                       # poora pipeline (API se real data)
python matsya.py run --local data          # local .h5 files se (koi API call nahi)
python matsya.py run --no-wind             # sirf SST
python matsya.py ingest --hours 24 --max 5 # sirf download
python matsya.py datasets                  # kaunse datasets uplabdh hain (real check)

python h5inspect.py data --values          # HDF5 ke andar kya hai
python apitest.py                          # API endpoints test (network/search/token/download)
python monitor.py --interval 30 --gif      # live auto-updating dashboard
python fishing.py --local data             # SST-only advisory
```

---

## ⚙️ Settings (`settings.json`)

```json
{
  "datasets": { "sst": "3RIMG_L2B_SST", "wind": "3RIMG_L2P_VSW", "chlorophyll": null },
  "region":   { "name": "indian-ocean", "bbox": [40, -40, 110, 30], "max_grid": 700 },
  "fetch":    { "max_files": 2, "hours_back": 24 },
  "physics":  { "front_ref_c_per_km": 0.05, "sst_optimum_c": 28.0,
                "weights": { "front": 35, "sst": 30, "eez": 15, "shelf": 10, "wind": 10 } }
}
```

Region badalna hai to `bbox` badlo: `[minLon, minLat, maxLon, maxLat]`
- Gujarat coast: `[66, 18, 74, 24]`
- Kerala: `[74, 7, 78, 13]`
- Bay of Bengal: `[80, 5, 95, 22]`

---

## 🔒 Credentials

`.env` file me (kabhi commit mat karo):
```
MOSDAC_USER="tumhara_username"
MOSDAC_PASS="tumhara_password"
```
Account nahi hai? <https://www.mosdac.gov.in/signup/> — approval ka email aata hai.

⚠️ 3 galat login = 1 ghanta lock. Pehle `python apitest.py` chalao.

---

## 🆚 ORCA (SIH-26176) se comparison

| | ORCA | MATSYA |
|---|---|---|
| Data | multiple sources claim | **MOSDAC live API — verified download** |
| AIS vessels | **simulated** by default (unka README) | real API se banayenge (pending) |
| EEZ | PostGIS | **MarineRegions EEZ v12** — verified |
| Stack | Next.js + FastAPI + PostGIS + Docker | **Python + static HTML** |
| Offline | partial | **fully offline** after data fetch |
| Missing layers | claim karta hai | **honestly "PENDING"** likha hai (NOTES.md) |

---

## ⚠️ Disclaimer

Ye advisory satellite data par adharit hai. Hamesha **local weather forecast**,
**Indian Coast Guard / INCOIS notices**, **monsoon fishing ban**, aur apni boat ki
capacity check karein. Research / decision-support ke liye hai, guarantee nahi.

---

## 📄 Pending work

Sab [`NOTES.md`](NOTES.md) me likha hai — chlorophyll, wind structure validation,
monsoon ban, AIS, bathymetry, multi-day composite.

## 🙏 Attribution

- **ISRO / MOSDAC** — satellite data
- **MarineRegions (VLIZ)** — EEZ boundaries, CC BY 4.0
- **Natural Earth** — coastline, public domain
