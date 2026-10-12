@echo off
setlocal

rem Double-click launcher to STOP Soul Trading (backend + dashboard).
rem This only stops the local servers; it does not close open broker positions.

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
    echo Windows PowerShell was not found.
    pause
    exit /b 1
)

"%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-soul-trading.ps1"

echo.
pause
endlocal
