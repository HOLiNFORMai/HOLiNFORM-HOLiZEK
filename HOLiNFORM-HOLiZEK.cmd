@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m main
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo HOLiZEK: Python 3.11+ nem talalhato. 1>&2
        exit /b 1
    )
    python -m main
)
exit /b %errorlevel%
