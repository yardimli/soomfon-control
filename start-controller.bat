@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Project Python was not found. Set up the .venv environment first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m soomfon_control %*
if errorlevel 1 (
    echo.
    echo The controller exited with an error. See the message above.
    pause
)
