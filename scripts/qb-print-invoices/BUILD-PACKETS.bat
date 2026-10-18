@echo off
rem Drag the invoices folder (e.g. YOSHI INVOICES) onto this file.
if "%~1"=="" (
  echo Drag the invoices folder onto BUILD-PACKETS.bat
  pause
  exit /b
)
python "%~dp0build_packets.py" "%~1" "%~dp0balances.csv"
pause
