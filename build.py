# -*- coding: utf-8 -*-
"""
Build Script for ToolMouse (PyInstaller Standalone Executable)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent

def build():
    print("=" * 60)
    print(" BẮT ĐẦU ĐÓNG GÓI TOOLMOUSE THÀNH FILE EXE ĐỘC LẬP")
    print("=" * 60)

    dist_dir = ROOT_DIR / "dist"
    build_dir = ROOT_DIR / "build"

    spec_file = ROOT_DIR / "toolmouse.spec"
    if not spec_file.exists():
        print(f"Lỗi: Không tìm thấy file {spec_file}")
        sys.exit(1)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_file)]
    print(f"Đang thực thi lệnh: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))

    if result.returncode == 0:
        exe_path = dist_dir / "ToolMouse.exe"
        if exe_path.exists():
            size_mb = round(exe_path.stat().st_size / (1024 * 1024), 2)
            print()
            print("=" * 60)
            print(f"✔ ĐÓNG GÓI THÀNH CÔNG!")
            print(f"  File thực thi: {exe_path}")
            print(f"  Dung lượng   : {size_mb} MB")
            print("=" * 60)
        else:
            print("✔ PyInstaller hoàn thành.")
    else:
        print(f"❌ Quá trình đóng gói thất bại với mã lỗi: {result.returncode}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build()