@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
:loop
echo [%date% %time%] Starting automation >> logs\automation.log
"venv\Scripts\python.exe" -u main.py >> logs\automation.log 2>&1
echo [%date% %time%] Stopped (exit code %errorlevel%), restarting in 60s >> logs\automation.log
timeout /t 60 /nobreak >nul
goto loop