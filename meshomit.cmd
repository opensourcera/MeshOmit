@echo off
rem MeshOmit launcher for Windows. Double-click, or run from a terminal.
cd /d "%~dp0"
set PYTHONUTF8=1
set NO_COLOR=
set COLORTERM=truecolor
python -X utf8 -m meshomit %*
if errorlevel 1 pause
