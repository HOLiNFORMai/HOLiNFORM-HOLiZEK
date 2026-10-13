@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 main.py --mode server
) else (
  python main.py --mode server
)
if errorlevel 1 pause
