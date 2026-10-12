@echo off
setlocal

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
    echo Windows PowerShell was not found.
    pause
    exit /b 1
)

"%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-soul-trading.ps1"
if errorlevel 1 pause

endlocal
