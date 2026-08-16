@echo off
:: RestartHeadset.bat - double-click this to reset your USB wireless dongle
:: Requires admin rights to disable/re-enable a device, so it asks for
:: permission (UAC prompt) automatically if you're not already elevated.

NET SESSION >nul 2>&1
if %errorLevel% == 0 (
    goto :run
) else (
    echo Requesting administrator permission...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:run
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-headset.ps1"
