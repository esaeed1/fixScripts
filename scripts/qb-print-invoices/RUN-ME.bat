@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Mark-YoshisInvoicesToPrint.ps1"
if %errorlevel%==9 exit /b
pause
