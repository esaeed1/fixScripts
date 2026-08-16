@echo off
:: FindWindow.bat - lists your open windows and lets you jump straight to
:: one, even if it's minimized, off-screen, or buried behind everything else.
::
:: If the window you're looking for belongs to an app running "as
:: Administrator", right-click this file and choose "Run as administrator"
:: instead of double-clicking - Windows won't let a normal script hand focus
:: to an elevated app otherwise.

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0find-window.ps1"
