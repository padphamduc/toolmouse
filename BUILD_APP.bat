@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo        TIẾN HÀNH ĐÓNG GÓI ỨNG DỤNG TOOLMOUSE (TOOL V3.2)
echo ============================================================
echo.

python build.py

echo.
if exist "dist\ToolMouse.exe" (
    echo ============================================================
    echo   BUILD APP THÀNH CÔNG!
    echo   File chạy: dist\ToolMouse.exe
    echo ============================================================
) else (
    echo ============================================================
    echo   BUILD APP THẤT BẠI! Vui lòng kiểm tra thông báo lỗi ở trên.
    echo ============================================================
)

pause
