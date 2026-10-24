@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Blinter.ps1"
if errorlevel 1 (
  echo.
  echo BLINTER INSTALL FAILED. Nothing was changed in regular Blender.
  pause
  exit /b 1
)
echo.
echo Blinter Alpha is installed. Launch from your Start Menu.
pause
