@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "dist\ToolMouse.exe" (
    start "" "dist\ToolMouse.exe"
) else (
    python main.py
)
