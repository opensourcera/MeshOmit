@echo off
rem Builds dist\MeshOmit.exe, a single file that needs no Python installed.
rem Needs: pip install pyinstaller  (plus the packages in requirements.txt)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --console --name MeshOmit ^
  --collect-all textual --collect-all rich --collect-all meshcore --collect-all bleak ^
  --collect-submodules winrt --collect-submodules serial ^
  --add-data "messages.json;." --add-data "config.example.json;." ^
  meshomit_exe.py
if errorlevel 1 (echo BUILD FAILED & pause & exit /b 1)
copy /y messages.json dist\ >nul
copy /y config.example.json dist\ >nul
echo.
echo Done: dist\MeshOmit.exe  (keep messages.json next to it; config.json is written on the first run)
