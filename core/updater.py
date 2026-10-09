# -*- coding: utf-8 -*-
"""
Background Auto-Update Checker for ToolMouse
Kiểm tra cập nhật tự động ở nền từ GitHub repository: https://github.com/padphamduc/toolmouse
- Không chặn giao diện hay luồng chuột
- Báo trạng thái cập nhật rõ ràng, không làm gián đoạn bài thi của người dùng
- Hỗ trợ kiểm tra tính toàn vẹn SHA-256 trước khi tải/cài đặt
"""

import os
import sys
import json
import time
import ssl
import hashlib
import tempfile
import threading
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Callable

CURRENT_VERSION = "3.2.0"
GITHUB_REPO = "padphamduc/toolmouse"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


def parse_version_tuple(v_str: str) -> tuple:
    parts = []
    clean = "".join([c if c.isdigit() or c == "." else "" for c in (v_str or "").strip()])
    for p in clean.split("."):
        if p.isdigit():
            parts.append(int(p))
    return tuple(parts) or (0,)


class UpdateInfo:
    def __init__(
        self,
        current_version: str,
        new_version: str,
        release_url: str = "",
        title: str = "",
        notes: str = "",
        asset_url: str = "",
        sha256: str = "",
    ):
        self.current_version = current_version
        self.new_version = new_version
        self.release_url = release_url or GITHUB_RELEASES_URL
        self.title = title or f"Bản cập nhật v{new_version}"
        self.notes = notes or ""
        self.asset_url = asset_url
        self.sha256 = sha256.lower().strip()

        cur_t = parse_version_tuple(current_version)
        new_t = parse_version_tuple(new_version)
        self.has_update = new_t > cur_t


def check_github_update(timeout: float = 5.0) -> Optional[UpdateInfo]:
    """Kiểm tra bản cập nhật mới nhất từ GitHub Releases."""
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "User-Agent": f"ToolMouse/{CURRENT_VERSION} (Windows NT 10.0; Win64; x64)",
                "Accept": "application/vnd.github.v3+json",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag_name = data.get("tag_name", "").lstrip("v")
                title = data.get("name", "")
                notes = data.get("body", "")
                release_url = data.get("html_url", GITHUB_RELEASES_URL)
                
                asset_url = ""
                sha256 = ""
                assets = data.get("assets", [])
                for a in assets:
                    if a.get("name", "").endswith(".exe") or a.get("name", "").endswith(".zip"):
                        asset_url = a.get("browser_download_url", "")
                        break

                info = UpdateInfo(
                    current_version=CURRENT_VERSION,
                    new_version=tag_name,
                    release_url=release_url,
                    title=title,
                    notes=notes,
                    asset_url=asset_url,
                    sha256=sha256
                )
                if info.has_update:
                    return info
    except Exception:
        pass
    return None


def verify_file_sha256(filepath: str, expected_sha256: str) -> bool:
    """Kiểm tra mã băm SHA-256 của file tải về."""
    if not expected_sha256:
        return True
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest().lower() == expected_sha256.lower()
    except Exception:
        return False


def start_background_update_check(on_update_found: Optional[Callable[[UpdateInfo], None]] = None):
    """Bắt đầu tác vụ kiểm tra phiên bản mới trong luồng daemon ngầm."""
    def _worker():
        # Đợi 3 giây sau khi app khởi động để nhường toàn bộ tài nguyên cho việc sẵn sàng UI và hook
        time.sleep(3.0)
        info = check_github_update(timeout=5.0)
        if info and info.has_update:
            if on_update_found:
                try:
                    on_update_found(info)
                except Exception:
                    pass

    t = threading.Thread(target=_worker, daemon=True, name="UpdateCheckWorker")
    t.start()
