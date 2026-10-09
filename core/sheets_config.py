# -*- coding: utf-8 -*-
"""
Google Sheets API Config Manager & Local Secure Cache
Tự động đồng bộ khóa API từ Google Sheets ở chế độ chạy ngầm (Non-blocking):
- Google Sheets URL: https://docs.google.com/spreadsheets/d/1WHLQmLBRxgAurR0eR27Faey5iK3Ps_vD4dCnJ6wNl3o/edit?usp=sharing
- Hỗ trợ đa tầng fallback khi mất mạng: Bộ nhớ cache cục bộ (DPAPI / C:\\duc\\configs\\toolmouse_cache.json).
- Thread-safe tuyệt đối: Không tráo đổi khóa giữa lúc đang phân tích đề thi.
- Bảo mật: Tuyệt đối không log hoặc in rõ khóa API ra console/file log.
"""

import os
import sys
import csv
import io
import time
import json
import ssl
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

SHEET_ID = "1WHLQmLBRxgAurR0eR27Faey5iK3Ps_vD4dCnJ6wNl3o"
SHEET_EXPORT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
SHEET_GVIZ_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

BASE_DIR = Path(r"C:\duc")
CONFIG_DIR = BASE_DIR / "configs"
CACHE_FILE = CONFIG_DIR / "toolmouse_cache.json"
LEGACY_KEY_FILE = BASE_DIR / "key.txt"

BASE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def mask_key(k: str) -> str:
    """Ẩn bớt ký tự khóa API để hiển thị an toàn trên giao diện/log."""
    if not k:
        return ""
    k_clean = str(k).strip()
    if len(k_clean) <= 8:
        return "********"
    return f"{k_clean[:4]}...{k_clean[-4:]}"


def _dpapi_protect(text: str) -> bytes:
    if not text:
        return b""
    if os.name != "nt":
        import base64, zlib
        return base64.b64encode(zlib.compress(text.encode("utf-8")))

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    raw = text.encode("utf-8")
    raw_buffer = ctypes.create_string_buffer(raw)
    in_blob = DATA_BLOB(len(raw), ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    CRYPTPROTECT_UI_FORBIDDEN = 0x1

    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "ToolMouse API Credentials",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        import base64
        return base64.b64encode(raw)

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> str:
    if not data:
        return ""
    if os.name != "nt":
        import base64, zlib
        try:
            return zlib.decompress(base64.b64decode(data)).decode("utf-8")
        except Exception:
            return ""

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    try:
        encrypted = bytes(data)
        encrypted_buffer = ctypes.create_string_buffer(encrypted)
        in_blob = DATA_BLOB(len(encrypted), ctypes.cast(encrypted_buffer, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        CRYPTPROTECT_UI_FORBIDDEN = 0x1

        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(out_blob),
        )
        if not ok:
            import base64
            return base64.b64decode(data).decode("utf-8", errors="ignore")

        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8", errors="replace")
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return ""


class SheetsConfigManager:
    """Quản lý nạp cấu hình API từ Google Sheets và lưu cache cục bộ an toàn."""

    def __init__(self):
        self._lock = threading.RLock()
        self._ready_event = threading.Event()
        self._config: Dict[str, str] = {
            "gemini": "",
            "claude": "",
            "chatgpt": "",
        }
        self._source = "none"
        self._last_sync_time = 0.0
        self._sync_error = ""

        # Khởi tạo nhanh từ cache máy cục bộ trước (không chờ mạng)
        self._load_from_local_cache()

    def _load_from_local_cache(self):
        """Đọc nhanh cấu hình từ file cache cục bộ."""
        with self._lock:
            if CACHE_FILE.exists():
                try:
                    raw_data = CACHE_FILE.read_bytes()
                    decrypted_text = _dpapi_unprotect(raw_data)
                    if decrypted_text:
                        parsed = json.loads(decrypted_text)
                        if isinstance(parsed, dict):
                            for k in ["gemini", "claude", "chatgpt"]:
                                if parsed.get(k):
                                    self._config[k] = parsed[k].strip()
                            if self._config.get("gemini"):
                                self._source = "cache"
                                self._ready_event.set()
                except Exception:
                    pass

            # Fallback sang C:\duc\key.txt nếu vẫn chưa có Gemini key
            if not self._config.get("gemini") and LEGACY_KEY_FILE.exists():
                try:
                    k = LEGACY_KEY_FILE.read_text(encoding="utf-8", errors="ignore").strip()
                    if k:
                        self._config["gemini"] = k
                        self._source = "legacy_key"
                        self._ready_event.set()
                except Exception:
                    pass

    def _save_to_local_cache(self):
        """Lưu cấu hình an toàn bằng DPAPI vào file cache cục bộ."""
        with self._lock:
            try:
                dumped = json.dumps(self._config, ensure_ascii=False)
                encrypted = _dpapi_protect(dumped)
                CACHE_FILE.write_bytes(encrypted)
            except Exception:
                pass

            # Đồng bộ khóa Gemini vào key.txt để các tool khác nếu cần dùng chung
            if self._config.get("gemini"):
                try:
                    LEGACY_KEY_FILE.write_text(self._config["gemini"], encoding="utf-8")
                except Exception:
                    pass

    def get_api_key(self, provider: str = "gemini") -> str:
        """Lấy API key của provider tương ứng (thread-safe snapshot)."""
        with self._lock:
            return self._config.get(provider.lower(), "")

    def get_all_keys(self) -> Dict[str, str]:
        """Lấy bản sao toàn bộ cấu hình API hiện tại."""
        with self._lock:
            return dict(self._config)

    def get_status_info(self) -> Dict[str, Any]:
        """Lấy thông tin trạng thái đồng bộ cho UI."""
        with self._lock:
            return {
                "source": self._source,
                "has_gemini": bool(self._config.get("gemini")),
                "gemini_masked": mask_key(self._config.get("gemini")),
                "last_sync": self._last_sync_time,
                "error": self._sync_error,
            }

    def wait_until_ready(self, timeout: float = 2.0) -> bool:
        """Chờ cho đến khi có ít nhất 1 khóa API hợp lệ (tối đa timeout giây)."""
        if self._config.get("gemini"):
            return True
        return self._ready_event.wait(timeout=timeout)

    def fetch_from_sheets_sync(self, timeout: float = 5.0) -> bool:
        """Thực hiện tải trực tiếp từ Google Sheets và cập nhật cache an toàn."""
        urls = [SHEET_EXPORT_URL, SHEET_GVIZ_URL]
        ctx = ssl.create_default_context()
        csv_text = None

        for url in urls:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ToolMouse/3.2"}
                )
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    if resp.status == 200:
                        raw = resp.read()
                        if raw and len(raw) > 5:
                            csv_text = raw.decode("utf-8-sig", errors="replace")
                            break
            except Exception:
                continue

        if not csv_text:
            with self._lock:
                self._sync_error = "Không kết nối được Google Sheets"
            return False

        try:
            reader = csv.reader(io.StringIO(csv_text))
            rows = [row for row in reader if any(cell.strip() for cell in row)]
            if not rows:
                with self._lock:
                    self._sync_error = "Dữ liệu Google Sheets rỗng"
                return False

            headers = [h.strip().upper() for h in rows[0]]
            col_idx = {
                "gemini": -1,
                "claude": -1,
                "chatgpt": -1,
            }

            for idx, h in enumerate(headers):
                if "GEMINI" in h:
                    col_idx["gemini"] = idx
                elif "CLAUDE" in h:
                    col_idx["claude"] = idx
                elif "CHATGPT" in h or "OPENAI" in h:
                    col_idx["chatgpt"] = idx

            # Đọc dòng dữ liệu đầu tiên (hàng 1 sau header)
            new_keys = {"gemini": "", "claude": "", "chatgpt": ""}
            if len(rows) > 1:
                first_row = rows[1]
                for provider, c_idx in col_idx.items():
                    if c_idx >= 0 and c_idx < len(first_row):
                        val = first_row[c_idx].strip()
                        if val:
                            new_keys[provider] = val

            # Cập nhật an toàn vào bộ nhớ
            with self._lock:
                updated = False
                for p, k in new_keys.items():
                    if k:
                        self._config[p] = k
                        updated = True

                if updated:
                    self._source = "google_sheets"
                    self._last_sync_time = time.time()
                    self._sync_error = ""
                    self._ready_event.set()
                    self._save_to_local_cache()
                    return True
                else:
                    self._sync_error = "Không tìm thấy khóa API trong bảng tính"
                    return False

        except Exception as e:
            with self._lock:
                self._sync_error = f"Lỗi phân tích bảng tính: {e}"
            return False

    def start_background_sync(self, on_success_callback=None):
        """Khởi chạy đồng bộ nền mà không chặn luồng chính."""
        def _worker():
            for retry in range(2):
                success = self.fetch_from_sheets_sync(timeout=5.0)
                if success:
                    if on_success_callback:
                        try:
                            on_success_callback(self.get_all_keys())
                        except Exception:
                            pass
                    break
                time.sleep(2.0)

        t = threading.Thread(target=_worker, daemon=True, name="SheetsConfigSync")
        t.start()


# Singleton instance
sheets_manager = SheetsConfigManager()
