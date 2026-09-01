# =============================================================
#  MOSDAC Data Download API - Windows Setup Script
#  Branch: agent/mosdac-setup
#  Run:    powershell -ExecutionPolicy Bypass -File setup.ps1
# =============================================================

$repo   = "https://github.com/SangamSitapuri07/mosdac-download-api.git"
$dir    = "mosdac-download-api"
$branch = "agent/mosdac-setup"

Write-Host "`n===== MOSDAC Setup =====" -ForegroundColor Cyan

# 1) Clone (agar folder pehle se hai to skip)
if (-not (Test-Path $dir)) {
    Write-Host "[1/6] Cloning..." -ForegroundColor Yellow
    git clone $repo
} else {
    Write-Host "[1/6] Folder pehle se hai, clone skip." -ForegroundColor Green
}
Set-Location $dir

# 2) Apni branch par aao + latest pull
Write-Host "[2/6] Branch '$branch' par switch + pull..." -ForegroundColor Yellow
git fetch origin
git checkout -B $branch origin/$branch

# 3) Dependencies
Write-Host "[3/6] Python libraries install..." -ForegroundColor Yellow
function PY { if (Get-Command python -ErrorAction SilentlyContinue) { python @args } else { py -3 @args } }
PY -m pip install requests tqdm

# 4) .env banao aur Notepad me kholo
Write-Host "[4/6] .env taiyaar..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
notepad .env
Read-Host "`n.env me MOSDAC_USER aur MOSDAC_PASS bhar kar SAVE kar lo, Notepad band karo, phir Enter dabao"

# 5) Test (login nahi karta - safe)
Write-Host "[5/6] Test chal raha hai (login nahi karega)..." -ForegroundColor Yellow
PY run.py test

# 6) Download (pehle 2 files)
Write-Host "[6/6] Download..." -ForegroundColor Yellow
$ans = Read-Host "`nSab PASS dikh raha hai? 2 files download karein? (Y/N)"
if ($ans -match '^[Yy]') {
    PY run.py download --count 2
    Write-Host "`nDone! Files: $PWD\data" -ForegroundColor Green
} else {
    Write-Host "`nJab download karna ho:  python run.py download --count 2" -ForegroundColor Cyan
}
