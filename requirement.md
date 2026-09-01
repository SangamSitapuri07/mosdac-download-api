# MOSDAC Data Download API — Requirements & Checklist

> Source: [https://www.mosdac.gov.in/downloadapi-manual](https://www.mosdac.gov.in/downloadapi-manual)
> Script package: [https://www.mosdac.gov.in/software/mdapi.zip](https://www.mosdac.gov.in/software/mdapi.zip)
> Ye file manual + `mdapi.py` (actual source code) dono ko padh kar banayi gayi hai.

---

## 1. API kya hai (Overview)

MOSDAC (Meteorological & Oceanographic Satellite Data Archival Centre, ISRO) ka **Data Download API** ek Python-based tool hai jisse aap satellite data **command line se** download kar sakte ho.

- Poori logic `mdapi.py` me hai — **aapko code change karne ki zarurat nahi**.
- Saari settings ek hi file me hoti hain: **`config.json`** (naam change mat karna, script isi naam se file dhoondhti hai).
- Flow: **Search → Authentication → Download → Logout**

### Workflow (4 steps)

| Step | Kya hota hai | Login zaroori? |
|---|---|---|
| i. Data Search | `datasetId` + filters se total files count aur size fetch hota hai | ❌ Nahi |
| ii. Authentication | Username/password se token milta hai | ✅ Haan (download ke liye) |
| iii. Data Download | Har file `id` ke through download hoti hai (100 files ke batch me) | ✅ Haan |
| iv. Logout | Session automatically band ho jata hai | — |

**Important:** Sirf search/preview ke liye account ki zarurat nahi — `user_credentials` khali chhod sakte ho. **Download** ke liye approved account zaroori hai.

---

## 2. API Endpoints (mdapi.py se extract kiye gaye)

| Purpose | Method | Endpoint | Auth |
|---|---|---|---|
| Login / Token | POST | `https://mosdac.gov.in/download_api/gettoken` | ❌ (body me username/password) |
| Refresh token | POST | `https://mosdac.gov.in/download_api/refresh-token` | refresh_token |
| Search data | GET | `https://mosdac.gov.in/apios/datasets.json` | ❌ Nahi |
| Internet/product release check | GET | `https://mosdac.gov.in/download_api/check-internet` | ❌ |
| Download file | GET | `https://mosdac.gov.in/download_api/download?id=<record_id>` | ✅ `Authorization: Bearer <access_token>` |
| Logout | POST | `https://mosdac.gov.in/download_api/logout` | username |

**Token request body:** `{"username": "...", "password": "..."}` → response: `{"access_token": "...", "refresh_token": "..."}`

**Search query params:** `datasetId` (required), `startTime`, `endTime`, `count`, `boundingBox`, `gId`, `startIndex` (pagination, 100 ke batch me)
**Search response keys:** `totalResults`, `totalSizeMB`, `itemsPerPage`, `startIndex`, `entries[]`
**Har entry me milta hai:** `identifier` (filename), `id` (record id — download ke liye chahiye), `updated`, `dcDate`, `enclosureLink`, `boundbox`

---

## 3. Requirements — API check karne ke liye kya kya chahiye

### A. System / Software requirements

| # | Requirement | Zaroori? | Check command |
|---|---|---|---|
| 1 | Python 3+ | ✅ Haan | `python3 --version` |
| 2 | Python library `requests` | ✅ Haan | `pip show requests` → warna `pip install requests` |
| 3 | Python library `tqdm` | ⚪ Optional (progress bar) | `pip install tqdm` |
| 4 | `mdapi.zip` package (mdapi.py + config.json) | ✅ Haan (download ke liye) | [Download](https://www.mosdac.gov.in/software/mdapi.zip) |
| 5 | Internet + mosdac.gov.in reachable (HTTPS/443) | ✅ Haan | `curl -I https://mosdac.gov.in` |
| 6 | Disk space (data GBs me ho sakta hai — `totalSizeMB` check karo) | ✅ Haan | search response me milta hai |

> Agar aap corporate/proxy network pe ho to `HTTPS_PROXY` / `HTTP_PROXY` env variables set karne pade sakte hain — `requests` unhe automatically use karta hai.

### B. Account requirements (sirf **download** ke liye)

| # | Requirement | Detail |
|---|---|---|
| 1 | Registered MOSDAC account | [https://mosdac.gov.in/signup/](https://www.mosdac.gov.in/signup/) |
| 2 | Account **approved** hona chahiye | Registration ke baad approval ka wait |
| 3 | Username (ya email) + password | `config.json` me dalna hai |
| 4 | Password reset link (agar bhool gaye) | [Reset credentials](https://www.mosdac.gov.in/realms/Mosdac/login-actions/reset-credentials) |
| 5 | ⚠️ **3 galat attempts = account 1 hour ke liye lock** | Script chalane se pehle credentials double-check karo |
| 6 | Daily limit: **5000 files/day per user** | Cross karne pe auto logout + "Daily Download Quota" message |

### C. Data requirement

| # | Requirement | Detail |
|---|---|---|
| 1 | **`datasetId`** (mandatory) | Catalog se product name copy karo: [https://mosdac.gov.in/catalog-app/satellite](https://www.mosdac.gov.in/catalog-app/satellite) (filter: Satellite / Sensor / Search). Example: `3SIMG_L1B_STD`, `3RIMG_L2B_SST`, `E06OCM_L2C_AD` |
| 2 | Date range (`startTime`, `endTime`) | Format: `YYYY-MM-DD`. Recommended — warna dataset ki poori lifespan scan hogi |
| 3 | `count` (optional) | Max **100** |
| 4 | `boundingBox` (optional) | Format: `minLon,minLat,maxLon,maxLat` → `"70.0,8.0,90.0,28.0"` |
| 5 | `gId` (optional) | Granule ID — exact hona chahiye, ek hi file ke liye. Example: `"15039367"` |

---

## 4. `config.json` — sahi format (⚠️ manual vs script mismatch)

Manual me kuch key-names alag likhe hain, lekin **`mdapi.py` actually ye keys padhta hai** (zip ke andar wali `config.json` ke hisaab se):

| Manual me likha hai | Script actually padhta hai | Section |
|---|---|---|
| `username` | **`username/email`** | user_credentials |
| `skip_user_prompt` | **`skip_user_input`** | download_settings |
| `generate_error_log` | **`generate_error_logs`** | download_settings |
| `error_log_path` | **`error_logs_dir`** | download_settings |

### Ready-to-use template (mosdac/config.json)

```json
{
"user_credentials": {
        "username/email": "YOUR_MOSDAC_USERNAME",
        "password": "YOUR_MOSDAC_PASSWORD"
},

"search_parameters": {
        "datasetId": "3RIMG_L2B_SST",
        "startTime": "2024-01-01",
        "endTime": "2024-01-02",
        "count": "5",
        "boundingBox": "",
        "gId": ""
},

"download_settings": {
        "download_path" : "/home/user/mosdac/data",
        "organize_by_date": false,
        "skip_user_input": false,
        "generate_error_logs": true,
        "error_logs_dir": ""
}
}
```

### Field reference

**`search_parameters`**

| Field | Required | Format / Notes |
|---|---|---|
| `datasetId` | ✅ Yes | `"3SIMG_L1B_STD"` — exact match, no typos/spaces |
| `startTime` | No | `"YYYY-MM-DD"` |
| `endTime` | No | `"YYYY-MM-DD"` (>= startTime) |
| `count` | No | Max 100 |
| `boundingBox` | No | `"minLon,minLat,maxLon,maxLat"` |
| `gId` | No | exact Granule ID |

**`download_settings`** (optional section)

| Field | Values | Notes |
|---|---|---|
| `download_path` | path string | Khali chhodoge to current directory me `MOSDAC Data Download/` banega |
| `organize_by_date` | `true`/`false` (boolean) | `download_path/datasetId/YYYY/DDMMM/` |
| `skip_user_input` | `true`/`false` (boolean) | `true` = background download, koi prompt nahi |
| `generate_error_logs` | `true`/`false` (boolean) | Error log banata hai |
| `error_logs_dir` | path string | Default: `[source folder]/error_logs/DD-MM-YY_error.log` |

> ❌ Galat: `"organize_by_date": "yes"` — string nahi, **boolean** (`true`/`false` bina quotes ke) chahiye.

### Folder structure (agar `organize_by_date: true`)

```
[download_path]/
└── datasetId/
    └── YYYY/
        └── DDMMM/
            └── [downloaded files...]
```

---

## 5. Run karne ka tarika

```bash
# 1. Download + unzip
curl -L -o mdapi.zip https://www.mosdac.gov.in/software/mdapi.zip
unzip mdapi.zip          # mdapi.py + config.json

# 2. config.json edit karo (datasetId, dates, credentials)

# 3. Run
python mdapi.py

# 4. Prompt aayega (agar skip_user_input: false)
#    "Do you want to start downloading? (Y/N):"  → Y + Enter

# 5. End me:
#    Download Complete!
#    Logout Successful. Goodbye <username>!
```

Background/unattended download ke liye: `"skip_user_input": true`.

---

## 6. API check kaise karein (bina download ke)

### Method 1 — Search API (login ki zarurat nahi) ✅ Sabse safe pehla test

```bash
curl -G "https://mosdac.gov.in/apios/datasets.json" \
  --data-urlencode "datasetId=3RIMG_L2B_SST" \
  --data-urlencode "startTime=2024-01-01" \
  --data-urlencode "endTime=2024-01-02" \
  --data-urlencode "count=5"
```

```python
import requests
r = requests.get("https://mosdac.gov.in/apios/datasets.json",
                 params={"datasetId": "3RIMG_L2B_SST",
                         "startTime": "2024-01-01",
                         "endTime": "2024-01-02",
                         "count": "5"}, timeout=60)
print(r.status_code, r.json()["totalResults"], r.json()["totalSizeMB"])
for e in r.json()["entries"]:
    print(e["identifier"], e["id"])
```

### Method 2 — Token/Login API (sirf apne real credentials se)

```bash
curl -X POST "https://mosdac.gov.in/download_api/gettoken" \
  -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}'
```

- `200` → `{"access_token": "...", "refresh_token": "..."}` ✅
- `401` → `{"error": "Invalid Username/Password..."}` ❌ (**3 baar galat = 1 hour lock**)
- `400` → validation error · `503` → server maintenance

### Method 3 — Ek hi command me sab check (ready script)

```bash
python3 check_requirements.py                       # Python, libs, network, search API
python3 check_requirements.py --dataset-id 3SIMG_L1B_STD --start 2025-01-01 --end 2025-01-02
python3 check_requirements.py --check-login --username <user> --password <pass>
python3 check_requirements.py --check-login --username <user> --password <pass> --probe-download
```

---

## 7. Hamare sandbox me live test ke results (01-Sep-2026)

| Check | Result |
|---|---|
| Python | 3.13.14 ✅ |
| `requests` | 2.33.0 ✅ |
| `tqdm` | 4.69.0 ✅ |
| Network `mosdac.gov.in` | HTTP 200 ✅ |
| Search API `3RIMG_L2B_SST` (2024-01-01 → 2024-01-02, count=3) | HTTP 200, `totalResults=89`, `totalSizeMB=1257`, 3 entries ✅ |
| Sample file mila | `3RIMG_02JAN2024_2345_L2B_SST_V02R00.h5` (id=12894020) ✅ |
| Token API (dummy creds se test) | HTTP 401 — `Invalid Username/Password` (expected) ✅ endpoint live hai |
| `check-internet` endpoint | ⚠️ GET+JSON body pe 404 aa raha hai; `mdapi.py` ise try/except me handle karta hai, download par asar nahi |

---

## 8. HTTP status codes / errors

| Code | Matlab | Kya karein |
|---|---|---|
| 200 | Success | — |
| 400 | Validation error | `config.json` ke params check karo (date format, count, bbox) |
| 401 | Invalid username/password, ya `NO_ACCESS_TOKEN` / `INVALID_TOKEN` | Credentials check karo; token expire hone pe script auto refresh karta hai |
| 404 | `NOT_RELEASED` (product abhi public nahi hua) | Dusra `datasetId` try karo |
| 429 | Rate limit — `minute_limit` (20 sec wait, auto-retry) ya `daily_limit` (5000 files/day, logout) | Thoda ruko / kal try karo |
| 503 | Server unavailable / maintenance | Baad me try karo |

Common galtiyan: galat `datasetId`, `25-10-2024` jaisa date format, `count > 100`, `endTime < startTime`, boolean ki jagah `"yes"/"no"` string, config file ka naam badal dena.

---

## 9. Final Checklist (tick karo)

- [ ] Python 3+ installed
- [ ] `pip install requests` ho gaya
- [ ] `pip install tqdm` (optional)
- [ ] `mdapi.zip` download + unzip (mdapi.py + config.json ek hi folder me)
- [ ] MOSDAC account banaya **aur approved** hai
- [ ] Username/password sahi hai (3 galat attempt = 1 hr lock yaad rakho)
- [ ] `datasetId` catalog se exact copy kiya
- [ ] `startTime` / `endTime` `YYYY-MM-DD` format me
- [ ] `count` <= 100
- [ ] `download_path` likhne ke permission hain + disk space kaafi hai
- [ ] Booleans `true`/`false` (quotes ke bina)
- [ ] `config.json` ka naam nahi badla
- [ ] Search API se pehle test kar liya (bina login ke) ✅
- [ ] Daily limit 5000 files/day ka dhyaan

---

## 10. Help

Error persist kare to error log (`generate_error_logs: true` se banta hai) attach karke likho:
**admin[at]mosdac[dot]gov[dot]in** (manual me `mosdsac` typo ke saath likha hai — sahi domain `mosdac.gov.in` hai).

---

### Files is workspace me

| File | Kya hai |
|---|---|
| `requirement.md` | Ye document (requirements + explanation) |
| `mosdac/mdapi.py`, `mosdac/config.json` | Official script package (zip se extract) |
| `mosdac/check_requirements.py` | Ek-command me sab check karne wali script |
| `mosdac/mdapi.zip` | Original download |
