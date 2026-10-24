@echo off
rem Builds dist\MeshOmit.exe, a single file that needs no Python installed.
rem Needs: pip install pyinstaller  (plus the packages in requirements.txt)
cd /d "%~dp0"
set DIST=%~1
if "%DIST%"=="" set DIST=dist
python -m PyInstaller --noconfirm --clean --onefile --console --name MeshOmit --distpath "%DIST%" ^
  --collect-all textual --collect-all rich --collect-all meshcore --collect-all bleak ^
  --collect-submodules winrt --collect-submodules serial ^
  --hidden-import winrt.windows.foundation.collections --hidden-import winrt.windows.storage.streams ^
  --hidden-import winrt.windows.devices.bluetooth.advertisement --hidden-import winrt.windows.devices.enumeration ^
  --hidden-import winrt.windows.devices.bluetooth.genericattributeprofile --hidden-import winrt.windows.devices.radios ^
  --add-data "messages.json;." --add-data "config.example.json;." ^
  meshomit_exe.py
if errorlevel 1 (echo BUILD FAILED & pause & exit /b 1)
copy /y messages.json "%DIST%\" >nul
copy /y config.example.json "%DIST%\" >nul
echo.
echo Done: %DIST%\MeshOmit.exe  (keep messages.json next to it; config.json is written on the first run)
