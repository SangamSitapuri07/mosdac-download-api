@echo off
chcp 65001 >nul
title MATSYA - Marine Fishing Advisory
cd /d "%~dp0"

echo.
echo   ============================================================
echo     M A T S Y A   -  Real-Data Marine Fishing Advisory
echo     ISRO MOSDAC + MarineRegions EEZ + Natural Earth
echo   ============================================================
echo.
echo   1.  PULL latest code from GitHub
echo   2.  CHECK environment (doctor)
echo   3.  RUN full pipeline  (download + agents + report)
echo   4.  RUN on local files only (no download)
echo   5.  LIVE console  (http://localhost:8000)
echo   6.  WATCH mode (auto-update every 30 min)
echo   7.  Download today's SST files only
echo   0.  Exit
echo.
set /p CHOICE=  Enter choice (0-7): 

if "%CHOICE%"=="1" goto pull
if "%CHOICE%"=="2" goto doctor
if "%CHOICE%"=="3" goto run
if "%CHOICE%"=="4" goto localrun
if "%CHOICE%"=="5" goto serve
if "%CHOICE%"=="6" goto watch
if "%CHOICE%"=="7" goto ingest
if "%CHOICE%"=="0" goto end
goto run

:pull
echo.
git fetch origin
git reset --hard origin/agent/mosdac-setup
echo.
echo   Done. Press any key...
pause >nul
goto end

:doctor
python matsya.py doctor
pause
goto end

:run
python matsya.py run --composite --animation
if exist out\tactical.html start out\tactical.html
pause
goto end

:localrun
set /p P= Folder with .h5 files (e.g. mosdac\data): 
python matsya.py run --local "%P%" --composite --animation
if exist out\tactical.html start out\tactical.html
pause
goto end

:serve
start "" http://localhost:8000
python matsya.py serve
goto end

:watch
python matsya.py watch --interval 30
goto end

:ingest
python matsya.py ingest --hours 24 --max 10
pause
goto end

:end
echo.
echo   Band kiya.
