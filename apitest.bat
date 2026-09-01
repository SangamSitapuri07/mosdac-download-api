@echo off
REM MOSDAC API test - double click kar sakte ho
where python >nul 2>nul && (python apitest.py) || (py -3 apitest.py)
echo.
pause
