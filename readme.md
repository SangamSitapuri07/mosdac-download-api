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

## ⚡ Quick Start — 4 commands, bas itna karna hai

> **Windows (PowerShell) users:** `python3` ki jagah **`python`** ya **`py -3`** use karo,
> `cp` ki jagah **`copy`**, `nano` ki jagah **`notepad`**, aur `&&` ki jagah command alag line me
> likho (purane PowerShell me `&&` chalta nahi). Poora Windows wala section neeche hai 👇

```bash
# 1) Clone + dependencies
git clone https://github.com/SangamSitapuri07/mosdac-download-api.git
cd mosdac-download-api
pip install requests tqdm            # tqdm optional (progress bar)

# 2) Apna ID/password .env me daalo (ye file GitHub par kabhi upload nahi hoti)
cp .env.example .env
nano .env                            # MOSDAC_USER aur MOSDAC_PASS bharo

# 3) Test karo (pehle ye - login nahi karta, bilkul safe)
python3 run.py test

# 4) Sab theek aaye to download
python3 run.py download --count 2    # pehle 2 files se test, phir poora
```

> **Credentials sirf `.env` (ya env variables) me rakho** — `mosdac/config.json` har run par
> khud-b-khud generate hota hai aur wo **gitignored** hai, to password kabhi GitHub par nahi jayega.

### 🩺 `run.py` — ek hi command me sab kuch

| Command | Kya karta hai | Login? |
|---|---|---|
| `python3 run.py test` | Python/libs/network check + config banta hai + **Search API** test | ❌ Nahi |
| `python3 run.py login` | Token/login test (asli credentials, **1 attempt**) | ✅ Haan |
| `python3 run.py config` | Sirf `mosdac/config.json` generate karta hai | ❌ |
| `python3 run.py download` | Config bana kar `mdapi.py` chalaata hai (asli download) | ✅ |
| `python3 run.py doctor` | **test → login → download** ek saath (end-to-end) | ✅ |
| `python3 run.py doctor --skip-download` | Sirf test + login verify | ✅ |

**Options (kisi bhi command ke saath):**
```bash
python3 run.py download --dataset 3SIMG_L1B_STD --start 2026-08-29 --end 2026-08-31
python3 run.py download --count 2                 # sirf 2 files (test ke liye best)
python3 run.py download --path ./data --yes       # background, bina Y/N prompt
python3 run.py download --bbox "70.0,8.0,90.0,28.0" --no-organize
python3 run.py test --dataset 3RIMG_L2B_SST --start 2026-09-01 --end 2026-09-01
```

**Env variables** (agar `.env` nahi banani):
```bash
export MOSDAC_USER="tumhara_username"
export MOSDAC_PASS="tumhara_password"
python3 run.py doctor
```

> ⚠️ `run.py login` / `download` **asli credentials use karte hain** — 3 galat attempt = 1 ghanta
> account lock. Isliye pehle hamesha `python3 run.py test` chalao (usme login hota hi nahi).

---

## 🪟 Windows / PowerShell — exact commands

PowerShell me `&&` kaam nahi karta (PowerShell 7 se pehle), `python3`/`nano` bhi nahi hote.
Ye copy-paste karo, **ek line ek baar me**:

```powershell
# 1) Clone (ek baar)
cd C:\Users\sanga\Downloads\mdapi
git clone https://github.com/SangamSitapuri07/mosdac-download-api.git
cd mosdac-download-api

# 2) Dependencies
python -m pip install requests tqdm

# 3) Apna ID/password daalo (Notepad khulega)
copy .env.example .env
notepad .env

# 4) Test (login nahi karta - safe)
python run.py test

# 5) Download (pehle 2 files se test)
python run.py download --count 2
```

**Agar `python` bhi nahi milta** ("Python was not found... Microsoft Store"), to `py` launcher use karo:

```powershell
py --version          # pehle check karo
py -3 run.py test
py -3 run.py download --count 2
```

Agar `py` bhi nahi chalta to **Python launcher / Python 3.x dobara install** karo:
<https://www.python.org/downloads/> → installer me ✅ **"Add python.exe to PATH"** zaroor tick karo.

### Bina `run.py` ke (agar wo repo me abhi available na ho)

```powershell
cd mosdac
notepad config.json
# "username/email" aur "password" me apni MOSDAC ID/password bharo
# datasetId / startTime / endTime / count apni zarurat ke hisaab se (count "2" se test karo)
python mdapi.py
```

> `mdapi.py` hamesha apne **wale folder** ki `config.json` padhta hai — isliye `cd mosdac` karke
> hi chalao.

---

## 🔑 Account kaise banaye (username / password kahan se milega)

MOSDAC ka **koi default ya public username/password nahi hota** — account khud banakar
approval lena padta hai. (Bina login ke sirf *open data* milta hai; API se download ke liye
registered + approved account chahiye.)

### Step 1 — Register karo

👉 <https://www.mosdac.gov.in/signup/>

Form me ye bharna padta hai (* = required):

| Field | Rule |
|---|---|
| **User Name \*** | Min 5 characters, **koi capital letter nahi**, aur **pehle 3 character alphabet** hone chahiye (e.g. `sangam07`) |
| **Password \*** | Min 8 characters — kam se kam 1 number + 1 UPPERCASE + 1 lowercase + 1 special character |
| Confirm Password, Title, First Name, Last Name, **Email \*** | — |
| Organisation, Address, City, Country | — |
| **Mobile Number \*** | Format: `+91-XXXXXXXXXX` |
| **Purpose \*** | Data kis kaam ke liye chahiye |
| Captcha + Terms & Conditions | tick karna zaroori |

### Step 2 — Email verify + approval ka wait

- Email par verification link aata hai → verify karo.
- Uske baad MOSDAC team account review karti hai; **approval ka email** milta hai
  (official FAQ: *"You will be intimated through e-mail about the approval"*).
- Time fix nahi bataya gaya — aam taur par kuch working days lagte hain. Jaldi ho to
  `admin[at]mosdac[dot]gov[dot]in` par mail kar sakte ho.

### Step 3 — Login check karo

1. Browser me <https://www.mosdac.gov.in> par login try karo.
2. Phir API test: `curl -X POST https://mosdac.gov.in/download_api/gettoken -H "Content-Type: application/json" -d '{"username":"<USERNAME>","password":"<PASSWORD>"}'`
   - `200` + token ✅ · `401` ❌ galat credentials
3. Approved hone ke baad hi wo username/password `config.json` me kaam aayenge.

### Useful links

| Kaam | Link |
|---|---|
| Sign up | <https://www.mosdac.gov.in/signup/> |
| Password reset | <https://www.mosdac.gov.in/realms/Mosdac/login-actions/reset-credentials> |
| Password change (login ke baad) | Profile → Change Profile → Password |
| Support | `admin[at]mosdac[dot]gov[dot]in` |

> ⚠️ **Note (NRT vs General user):** General users ko Level-2+ data near-real-time milta hai,
> lekin **Level-1 data 3 din ki latency** ke saad milta hai. NRT access chahiye to MOSDAC admin se
> contact karna padta hai.

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

### Level 0 — Full API test report (ek command me sab endpoints)

```powershell
python apitest.py
```

(ya `apitest.bat` pe **double-click** kar do — khul kar result dikhayega aur rukega)

Ye report deta hai: Network/DNS → Search API → galat `datasetId` error handling → date filter →
**Token/Login API** → **Download endpoint**. Credentials `.env` se padhta hai; nahi mile to
token/download test skip ho jate hain (koi lock ka risk nahi).

```
===== MOSDAC API TEST REPORT =====
  [PASS] HTTPS mosdac.gov.in            HTTP 200 | 866 ms
  [PASS] Search 3RIMG_L2B_SST           totalResults=132 | totalSizeMB=1916
  [PASS] Galat datasetId pe error handling   HTTP 500 (expected error)
  [PASS] Date filter (1990)             HTTP 500
  [FAIL] POST /download_api/gettoken    HTTP 429 | rate_limit_exceeded
  [SKIP] Download endpoint              token nahi mila
===== SUMMARY =====
  PASS: 4 | FAIL: 1 | WARN: 0 | SKIP: 1
```

> **429 = server rate limit** (tumhari galti nahi) — thodi der baad fir chalao.
> Agar `python apitest.py` me "can't open file" aaye to pehle `git pull` kar lo.

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
