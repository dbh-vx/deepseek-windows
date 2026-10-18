@echo off
setlocal
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ChatGPT Island.lnk"
if exist "%LINK%" del "%LINK%" 2>nul
echo DeepSeek startup is DISABLED.
echo This script will not enable automatic startup.
echo To launch the program, run run.bat manually.
pause
