@echo off
setlocal

rem Double-click launcher for Soul Trading (backend + dashboard + news-bias engine).
rem It calls start-soul-trading.ps1, which sets all env vars, starts both servers,
rem waits for them to be healthy, and opens http://localhost:3000.

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
    echo Windows PowerShell was not found.
    pause
    exit /b 1
)

echo Starting Soul Trading (backend + dashboard)...
echo This window stays open while everything launches. You can close it after the dashboard opens.
echo.

"%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-soul-trading.ps1"
if errorlevel 1 (
    echo.
    echo Soul Trading failed to start. See %LOCALAPPDATA%\SoulTrading\startup.log for details.
    pause
)

endlocal

