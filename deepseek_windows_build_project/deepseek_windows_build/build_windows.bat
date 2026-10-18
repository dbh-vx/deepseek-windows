@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo   DeepSeek - Windows EXE Builder
echo ==========================================
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python launcher not found.
  echo This build script is for developers building the EXE.
  echo End users should download the packaged deepseek.exe from the build artifact.
  pause
  exit /b 1
)
py -3.12 -m pip install --upgrade pip
if errorlevel 1 goto failed
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto failed
py -3.12 -m PyInstaller --noconfirm --clean deepseek.spec
if errorlevel 1 goto failed
echo.
echo Build complete: dist\deepseek.exe
echo Copy the EXE to a folder on your PC and run it.
pause
exit /b 0
:failed
echo.
echo Build failed. Check the error messages above.
pause
exit /b 1
