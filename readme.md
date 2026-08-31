# MOSDAC Data Download API — Setup, Run & Test Guide

ISRO **MOSDAC** (Meteorological & Oceanographic Satellite Data Archival Centre) ke Data Download API ko
setup karne, chalane aur test karne ki पूरी guide — Hinglish me.

Official manual: <https://www.mosdac.gov.in/downloadapi-manual>

---

## 📦 Is repo me kya hai

| File / Folder | Kya hai |
|---|---|
| `readme.md` | **Ye file** — run + test karne ka tarika |
| `requirement.md` | Poori requirement list, config reference, error codes, checklist |
| `mosdac/mdapi.py` | Official MOSDAC download script (zip se liya, **unedited**) |
| `mosdac/config.json` | Ready-to-use config template (sahi key-names ke saath) |
| `mosdac/check_requirements.py` | Ek hi command me sab kuch check karne wali script |
| `examples/search_only.py` | Bina login ke dataset search karne ka example |
| `mosdac/mdapi.zip` | Official zip (reference ke liye) |

---

## ⚡ Quick Start (5 steps)

```bash
# 1) Clone karo
git clone https://github.com/SangamSitapuri07/mosdac-download-api.git
cd mosdac-download-api

# 2) Dependencies install karo
pip install requests tqdm          # tqdm optional hai (progress bar ke liye)

# 3) Config banao (template copy karke) aur apni details bharo
cp mosdac/config.json mosdac/config.local.json
nano mosdac/config.local.json      # ya koi bhi editor

# 4) Pehle TEST karo (bina login ke search chalti hai)
python3 mosdac/check_requirements.py --config mosdac/config.json
python3 examples/search_only.py 3RIMG_L2B_SST 2024-01-01 2024-01-02 5

# 5) Download karo
cd mosdac
python3 mdapi.py
```

> `config.local.json` **gitignore** hai — isme apne asli username/password rakho,
> galti se GitHub par upload nahi honge. `mdapi.py` `config.json` naam ki file hi padhta hai,
> to download ke waqt apni local file ko `config.json` ke naam se use karo (ya copy kar lo).

---

## ✅ Requirements (short me)

| Cheez | Zaroori? | Command |
|---|---|---|
| Python 3+ | ✅ | `python3 --version` |
| `requests` | ✅ | `pip install requests` |
| `tqdm` | ⚪ optional | `pip install tqdm` |
| Internet / mosdac.gov.in reachable | ✅ | `curl -I https://mosdac.gov.in` |
| MOSDAC account (approved) | ✅ **sirf download ke liye** | <https://www.mosdac.gov.in/signup/> |
| `datasetId` | ✅ | Catalog: <https://www.mosdac.gov.in/catalog-app/satellite> |

Detail ke liye [`requirement.md`](requirement.md) padho.

---

## ⚙️ Configuration

`config.json` me 3 sections hote hain:

```json
{
  "user_credentials": { "username/email": "YOUR_USERNAME", "password": "YOUR_PASSWORD" },
  "search_parameters": {
    "datasetId": "3RIMG_L2B_SST",
    "startTime": "2024-01-01",
    "endTime": "2024-01-02",
    "count": "5",
    "boundingBox": "",
    "gId": ""
  },
  "download_settings": {
    "download_path": "./data",
    "organize_by_date": false,
    "skip_user_input": false,
    "generate_error_logs": true,
    "error_logs_dir": ""
  }
}
```

### ⚠️ Manual vs Script key-name mismatch (bahut important)

Official manual kuch alag naam likhta hai, lekin `mdapi.py` actually ye padhta hai:

| Manual me | Script padhta hai |
|---|---|
| `username` | **`username/email`** |
| `skip_user_prompt` | **`skip_user_input`** |
| `generate_error_log` | **`generate_error_logs`** |
| `error_log_path` | **`error_logs_dir`** |

Galat naam likhoge to wo setting **chup-chaap ignore** ho jayegi (koi error nahi aayega).

**Rules:**
- `datasetId` mandatory hai, catalog se **exact** copy karo (no typos/spaces)
- Dates `YYYY-MM-DD` format me, `count` max **100**
- Booleans `true` / `false` — **bina quotes ke** (`"yes"` galat hai)
- `config.json` ka naam mat badlo

---

## ▶️ Run kaise karein

```bash
cd mosdac
python3 mdapi.py
```

Output kuch aisa aayega:

```
Searching Data for Provided Parameters...

89 Files Found with Total Size of 1.23 GB.
Do you want to Download them? [Y/N]: Y

Verifying User Credentials..
Login Successful. Hello <username>!

Starting with Data Download..
Progress: |████████████████████████| 100%

Download Complete!
Total No. of Files Downloaded: 5
Total Time Taken: 0.75 min

Logout Successful. Goodbye <username>!
```

**Background download** (koi prompt nahi) → `"skip_user_input": true`
**Date-wise folders** → `"organize_by_date": true` → `download_path/datasetId/YYYY/DDMMM/`

---

## 🧪 Test kaise karein (4 levels)

### Level 1 — Environment check (sabse pehle ye)

```bash
python3 mosdac/check_requirements.py
```

Ye check karta hai: Python version, `requests`, `tqdm`, network connectivity, `config.json` ki
structure aur key-names, aur Search API.

Expected output:

```
[PASS] Python version -> 3.13.14 (>= 3 required)
[PASS] Python library: requests -> 2.33.0
[PASS] Python library: tqdm -> 4.69.0
[PASS] Network: mosdac.gov.in reachable -> HTTP 200
[PASS] Config file 'mosdac/config.json' -> structure theek hai
[PASS] Search API (GET /apios/datasets.json) -> HTTP 200 | totalResults=89 | totalSizeMB=1257 | entries=3
        - 3RIMG_02JAN2024_2345_L2B_SST_V02R00.h5  (id=12894020, updated=2024-01-02T23:45:00Z)
===== SUMMARY =====
PASS: 6 | FAIL: 0 | WARN: 1
```

### Level 2 — Search API test (🚫 login ki zarurat nahi)

```bash
# Python example
python3 examples/search_only.py 3RIMG_L2B_SST 2024-01-01 2024-01-02 5

# ya direct curl
curl -G "https://mosdac.gov.in/apios/datasets.json" \
  --data-urlencode "datasetId=3RIMG_L2B_SST" \
  --data-urlencode "startTime=2024-01-01" \
  --data-urlencode "endTime=2024-01-02" \
  --data-urlencode "count=5"
```

Agar `totalResults` aur file list dikhe → API live hai aur tumhara `datasetId` sahi hai.

### Level 3 — Login / Token test (apne real credentials se)

```bash
curl -X POST "https://mosdac.gov.in/download_api/gettoken" \
  -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}'
```

| Response | Matlab |
|---|---|
| `200` + `access_token` / `refresh_token` | ✅ Login theek hai |
| `401 {"error":"Invalid Username/Password..."}` | ❌ Credentials galat |
| `400` | Validation error |
| `503` | Server maintenance |

Ya fir checker script se:

```bash
python3 mosdac/check_requirements.py --check-login --username <user> --password <pass>
```

> ⚠️ **3 baar galat password = account 1 ghante ke liye lock.** Pehle `search` se test kar lo,
> credentials tabhi daalo jab download karna ho.

### Level 4 — Chhota dry-run download (1–2 files)

```json
"search_parameters": {
  "datasetId": "3RIMG_L2B_SST",
  "startTime": "2024-01-01",
  "endTime": "2024-01-01",
  "count": "2",
  "boundingBox": "",
  "gId": ""
},
"download_settings": { "download_path": "./data", "generate_error_logs": true }
```

```bash
cd mosdac && python3 mdapi.py     # 2 files download honi chahiye
ls -lh data/                      # files check karo
cat error_logs/*_error.log        # agar koi error aaya ho
```

Ye sabse safe test hai — poora dataset download kiye bina pipeline verify ho jati hai.
Pura flow theek lage to `count` hata do ya dates badha do.

---

## 🔌 API Endpoints (reference)

| Purpose | Method | Endpoint | Auth |
|---|---|---|---|
| Login/Token | POST | `/download_api/gettoken` | ❌ (body me creds) |
| Refresh token | POST | `/download_api/refresh-token` | refresh_token |
| Search | GET | `/apios/datasets.json` | ❌ |
| Download file | GET | `/download_api/download?id=<record_id>` | ✅ Bearer token |
| Logout | POST | `/download_api/logout` | username |

Base URL: `https://mosdac.gov.in`

---

## 🩺 Troubleshooting

| Problem | Status / Message | Solution |
|---|---|---|
| Config file nahi mila | `[ERROR] 'config.json' Not Found!` | Script `mdapi.py` ke **same folder** me `config.json` hona chahiye |
| Login fail | `401 Invalid Username/Password` | Credentials check karo; 3 galat attempt = 1 hr lock |
| Dataset nahi mila | `400` / search error | `datasetId` catalog se dobara copy karo |
| Product public nahi | `404 NOT_RELEASED` | Dusra `datasetId` try karo |
| Bahut fast requests | `429 minute_limit` | 20 sec ruko (script khud retry karta hai) |
| Limit cross | `429 daily_limit` | 5000 files/day — agle din try karo |
| Server down | `503` | Maintenance — baad me try karo |
| Progress bar ajeeb | `[INFO] 'tqdm' Library is Not Installed` | `pip install tqdm` |
| Boolean error | `must be either: true or false` | `"yes"`/`"no"` ki jagah `true`/`false` (bina quotes) |
| Permission denied | `No Permission to Write` | `download_path` badlo ya permissions theek karo |

---

## 🔒 Safety notes

- ❌ **Kabhi bhi asli username/password commit mat karo.** `config.local.json` (gitignored) use karo.
- Account approval ke baad hi download allowed hai.
- Daily limit: **5000 files/day per user**.
- `data/`, `error_logs/`, `*.zip` gitignore hain — big files repo me mat daalo.
- `mosdac/mdapi.py` MOSDAC ka official code hai (zip se liya, unmodified); is repo me sirf
  reference ke liye rakha gaya hai.

---

## 📞 Help

- Manual: <https://www.mosdac.gov.in/downloadapi-manual>
- Catalog (datasetId dhoondho): <https://www.mosdac.gov.in/catalog-app/satellite>
- Signup: <https://www.mosdac.gov.in/signup/>
- Support: `admin[at]mosdac[dot]gov[dot]in` (error log attach karna na bhoolein)
