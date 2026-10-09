@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo =======================================================
echo   ĐẨY MÃ NGUỒN LÊN GITHUB: padphamduc/toolmouse
echo =======================================================
echo.

git branch -M main
git push -u origin main

echo.
echo Hoàn tất!
pause
