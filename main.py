# -*- coding: utf-8 -*-
# ==============================================================================
# TOOLMOUSE – BẢN ĐỘC LẬP CHUYÊN BIỆT (TOOL V3.2)
# ĐỨC DẠY BẠN HỌC NHÉ <3
# ==============================================================================
# Thao tác:
# - Chuột Phải x2 : Chụp toàn màn hình & gửi Gemini giải bài
# - Chuột Trái x4  : Tự động gõ đáp án tự luận vào ô đang trỏ chuột (Unicode Win32)
# - Chuột Trái x2  : Hiển thị số câu kèm đáp án (99 A / 99 A, C) + chữ tự luận
# - Chuột Trái x1  : Dừng ngay khi đang gõ; ngoài lúc gõ, nhấp ngoài vùng chữ để ẩn kết quả.
# - Phím F2        : Mở cửa sổ Cài đặt (Setup)
# - Phím ESC       : Thoát ứng dụng
# ==============================================================================

import os
import sys
import json
import time
import ctypes
from ctypes import wintypes
import threading
import re
from pathlib import Path
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional

# Thiết lập đường dẫn
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Đảm bảo C:\duc tồn tại
BASE_DIR = Path(r"C:\duc")
BASE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR = BASE_DIR / "configs"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "seb_mouse_v32.json"
PICTURE_DIR = BASE_DIR / "picture"
PICTURE_DIR.mkdir(parents=True, exist_ok=True)
ANSWER_FILE = BASE_DIR / "dapan_v32.txt"

# Cấu hình mặc định
DEFAULT_CONFIG: Dict[str, Any] = {
    "model": "gemini-3.5-flash-lite",
    "model_name": "Gemini 3.5 Flash-Lite",
    "double_click_interval": 0.35,
    "load_cursor_duration": 1.0,
    "number_opacity": 2,
    "text_opacity": 2,
    "text_font_size": 11,
    "text_fg": "#111111",
}
CONFIG: Dict[str, Any] = dict(DEFAULT_CONFIG)


def load_config() -> Dict[str, Any]:
    global CONFIG
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                CONFIG.update(saved)
                if "number_opacity" in saved:
                    CONFIG["text_opacity"] = saved["number_opacity"]
        except Exception:
            pass
    return CONFIG


def save_config(data: Dict[str, Any]):
    global CONFIG
    CONFIG.update(data)
    try:
        CONFIG_FILE.write_text(json.dumps(CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


load_config()

# Module nội bộ
from core.sheets_config import sheets_manager, mask_key
from core.updater import start_background_update_check, CURRENT_VERSION
from core.screen_capture import capture_screen
from core.ai_client import call_gemini_solve_quiz
from ui.overlay import ResultOverlayV32

import keyboard
from colorama import Fore, Style, init

init(autoreset=True)

PINK = Fore.MAGENTA + Style.BRIGHT
CYAN = Fore.CYAN + Style.BRIGHT
GREEN = Fore.GREEN + Style.BRIGHT
YELLOW = Fore.YELLOW + Style.BRIGHT
RED = Fore.RED + Style.BRIGHT
WHITE = Fore.WHITE + Style.BRIGHT
RESET = Style.RESET_ALL

TOOL_TITLE = f"ToolMouse v{CURRENT_VERSION} – Dùng chuột (Hiện đáp án tại vị trí số câu)"

if os.name == "nt":
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
        ctypes.windll.kernel32.SetConsoleTitleW(TOOL_TITLE)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

# Khởi tạo overlay hiển thị kết quả
result_overlay = ResultOverlayV32(get_config_func=load_config)

# ==============================================================================
# QUẢN LÝ CON TRỎ XOAY (LOADING CURSOR)
# ==============================================================================
OCR_WAIT = 32514

def show_loading_cursor_once(duration: float = None):
    dur = duration if (duration is not None and duration > 0) else float(CONFIG.get("load_cursor_duration", 1.0))
    if dur <= 0:
        return

    def _worker():
        try:
            user32 = ctypes.windll.user32
            h_wait = user32.LoadCursorW(None, OCR_WAIT)
            h_copy = user32.CopyImage(h_wait, 2, 0, 0, 0)
            user32.SetSystemCursor(h_copy, 32512)
            time.sleep(dur)
            SPI_SETCURSORS = 0x0057
            user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


# ==============================================================================
# QUẢN LÝ TRẠNG THÁI KẾT QUẢ PHÂN TÍCH
# ==============================================================================
_current_request_id = 0
_request_lock = threading.Lock()

last_mc_badge_text: str = ""
last_mc_items: List[Dict[str, Any]] = []
last_written_items: List[Dict[str, Any]] = []
last_status_message: str = ""

state_lock = threading.Lock()
busy = False
busy_lock = threading.Lock()


def get_next_screenshot_path() -> Path:
    for number in range(1, 101):
        p = PICTURE_DIR / f"{number}.jpg"
        if not p.exists():
            return p
    return PICTURE_DIR / "1.jpg"


def print_box(title: str, lines: list = None, color=PINK, width: int = 76, indent: int = 2):
    if lines is None:
        lines = []
    title = str(title)
    lines = [str(x) for x in lines]
    longest = max([len(title)] + [len(x) for x in lines] + [0])
    box_width = max(width, longest + 4)
    print(color + "╔" + "═" * box_width + "╗")
    print(color + "║" + WHITE + title.center(box_width) + color + "║")
    if lines:
        print(color + "╠" + "═" * box_width + "╣")
        for line in lines:
            print(color + "║" + WHITE + ((" " * indent) + line).ljust(box_width) + color + "║")
    print(color + "╚" + "═" * box_width + "╝")


def show_banner():
    os.system("cls" if os.name == "nt" else "clear")
    print()
    load_config()
    model_name = CONFIG.get("model", "gemini-3.5-flash-lite")
    num_op = CONFIG.get("number_opacity", 2)
    cursor_dur = CONFIG.get("load_cursor_duration", 1.0)
    sheets_info = sheets_manager.get_status_info()
    api_status = f"Google Sheets ({sheets_info.get('gemini_masked', 'Đang tải...')})" if sheets_info.get("has_gemini") else "Đang đồng bộ ngầm..."

    print_box(
        "ĐỨC DẠY BẠN HỌC NHÉ <3",
        [
            f"TOOLMOUSE v{CURRENT_VERSION} – CHUYÊN BIỆT CHO SEB (ĐÁP ÁN TẠI VỊ TRÍ SỐ CÂU)",
            "----------------------------------------------------------------------------",
            "Chuột Phải x2 : Chụp toàn màn hình & gửi Gemini phân tích",
            "Chuột Trái x4  : Tự động gõ đáp án tự luận vào ô đang có con trỏ",
            "Chuột Trái x2  : Hiện kết quả (Số câu kèm đáp án vd '99 A' & tự luận)",
            "Chuột Trái x1  : Dừng ngay khi đang gõ; ngoài lúc gõ, nhấp ngoài vùng chữ để ẩn kết quả.",
            "Phím F2        : Mở cửa sổ Cài đặt cấu hình (Setup)",
            "Phím ESC       : Thoát khỏi tool",
            "----------------------------------------------------------------------------",
            f"Độ mờ số câu   : {num_op}% (Đen mờ, không lộ)",
            f"Load chuột     : {cursor_dur}s • Model: {model_name}",
            f"Khóa API       : {api_status}",
        ],
        color=PINK,
        width=78,
    )
    print()


# ==============================================================================
# HÀM CHỤP MÀN HÌNH & GỬI GEMINI KHI BẤM CHUỘT PHẢI x2
# ==============================================================================
def capture_and_send_gemini():
    global _current_request_id, last_mc_badge_text, last_mc_items, last_written_items, last_status_message, busy

    with _request_lock:
        _current_request_id += 1
        my_req_id = _current_request_id

    with state_lock:
        last_mc_badge_text = ""
        last_mc_items = []
        last_written_items = []
        last_status_message = ""

    result_overlay.hide_all()

    with busy_lock:
        if busy:
            print(YELLOW + "⏳ Đang có yêu cầu phân tích đang chạy, hủy phiên cũ và bắt đầu phiên mới...")
        busy = True

    try:
        load_config()
        active_model = str(CONFIG.get("model", "gemini-3.5-flash-lite")).strip()

        start_time = time.time()
        show_loading_cursor_once(float(CONFIG.get("load_cursor_duration", 1.0)))

        print()
        print(CYAN + f"📸 [Chuột Phải x2] Đã chụp toàn bộ màn hình, đang gửi Gemini ({active_model})...")

        screenshot = capture_screen()

        # Lưu ảnh vào C:\duc\picture
        try:
            image_path = get_next_screenshot_path()
            screenshot.save(image_path, "JPEG", quality=88)
        except Exception:
            pass

        # Giải bài bằng Gemini (Lazy loading google.genai và pydantic)
        try:
            ai_res = call_gemini_solve_quiz(
                screenshot=screenshot,
                preferred_model=active_model
            )
            parsed = ai_res["parsed"]
            used_model = ai_res["used_model"]
        except Exception as api_err:
            err_str = f"{api_err}"
            print(RED + f"❌ {err_str}")
            with state_lock:
                if my_req_id == _current_request_id:
                    last_status_message = err_str
            return

        with _request_lock:
            if my_req_id != _current_request_id:
                print(YELLOW + "ℹ Bỏ qua kết quả do đã có yêu cầu chụp mới hơn.")
                return

        show_loading_cursor_once(float(CONFIG.get("load_cursor_duration", 1.0)))

        mc_badge_text = parsed.get("mc_badge_text", "")
        mc_items = parsed.get("mc_items", [])
        written_items = parsed.get("written_items", [])
        needs_more_info = parsed.get("needs_more_info", False)
        status_msg = parsed.get("status_message", "")

        if needs_more_info and not status_msg:
            status_msg = "Ảnh mờ hoặc thiếu dữ kiện; cần chụp lại ảnh rõ hơn."

        with state_lock:
            if my_req_id == _current_request_id:
                last_mc_badge_text = str(mc_badge_text).strip()
                last_mc_items = list(mc_items)
                last_written_items = list(written_items)
                last_status_message = str(status_msg).strip()

        # Ghi log ra file C:\duc\dapan_v32.txt
        try:
            log_lines = [
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Kết quả phân tích (ToolMouse v3.2):",
            ]
            if mc_badge_text:
                log_lines.append(f"  Trắc nghiệm: {mc_badge_text.replace(chr(10), ' | ')}")
            if written_items:
                for w in written_items:
                    log_lines.append(f"  {w.get('question_type', 'Tự luận')} (Câu {w.get('question_number', '?')}): {w.get('answer_text')}")
            if status_msg:
                log_lines.append(f"  Thông báo: {status_msg}")
            log_lines.append("-" * 50 + "\n")
            with open(ANSWER_FILE, "a", encoding="utf-8") as f:
                f.write("\n".join(log_lines))
        except Exception:
            pass

        elapsed = round(time.time() - start_time, 2)
        print()
        summary_lines = [
            f"Model AI   : {used_model} (Gemini)",
            f"Thời gian  : {elapsed}s",
        ]
        if mc_badge_text:
            summary_lines.append(f"Trắc nghiệm: {mc_badge_text.replace(chr(10), ' | ')}")
        if written_items:
            summary_lines.append(f"Tự luận/Điền: {len(written_items)} câu (Chữ nổi góc dưới phải)")
        if status_msg:
            summary_lines.append(f"Thông báo  : {status_msg}")

        summary_lines.extend([
            "👉 BẤM 2 LẦN CHUỘT TRÁI để hiện kết quả (Số câu & đáp án tại vị trí số câu)!",
            "👉 BẤM 1 LẦN CHUỘT TRÁI ngoài vùng chữ để ẩn kết quả.",
            "👉 BẤM 4 LẦN CHUỘT TRÁI để tự động gõ đáp án tự luận vào ô đang trỏ.",
        ])

        print_box(
            "GEMINI ĐÃ GIẢI XONG ĐỀ THI",
            summary_lines,
            color=GREEN,
            width=78,
        )

    except Exception as e:
        print()
        print(RED + f"❌ Lỗi xử lý: {e}")
        with state_lock:
            if my_req_id == _current_request_id:
                last_status_message = f"Lỗi xử lý: {e}"
    finally:
        with busy_lock:
            busy = False


# ==============================================================================
# CƠ CHẾ GÕ ĐÁP ÁN TỰ LUẬN TRỰC TIẾP (UNICODE WIN32, KHÔNG CLIPBOARD)
# ==============================================================================
is_typing = False
typing_lock = threading.Lock()
stop_typing_event = threading.Event()
typing_trigger_time = 0.0

def stop_auto_typing() -> bool:
    """
    Dừng tiến trình gõ phím ngay lập tức nếu đang gõ.
    Hủy phần chưa gõ, giữ nguyên chữ đã nhập và không tự tiếp tục.
    """
    global is_typing
    with typing_lock:
        if not is_typing:
            return False
        stop_typing_event.set()
        is_typing = False

    try:
        import winsound
        winsound.Beep(1000, 80)
    except Exception:
        pass
    print(YELLOW + "⏹ [Chuột Trái x1] Đã dừng gõ đáp án! Giữ nguyên chữ đã nhập.")
    return True


def start_auto_typing():
    """Bắt đầu tiến trình gõ phím tự luận trong background thread."""
    global is_typing, typing_trigger_time
    with typing_lock:
        if is_typing:
            return
        is_typing = True
        stop_typing_event.clear()
        typing_trigger_time = time.time()

    threading.Thread(target=_auto_type_worker, daemon=True, name="AutoTypeWorker").start()


def type_char_safe(char: str):
    if char == "\r":
        return
    if char == "\n":
        try:
            ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x0D, 0, 0x0002, 0)
            return
        except Exception:
            pass
        return

    if char == "\t":
        for _ in range(4):
            type_char_safe(" ")
        return

    try:
        import keyboard._winkeyboard as wk
        wk.type_unicode(char)
        return
    except Exception:
        pass

    try:
        code = ord(char)
        ctypes.windll.user32.keybd_event(0, code, 0x0004, 0)
        ctypes.windll.user32.keybd_event(0, code, 0x0004 | 0x0002, 0)
        return
    except Exception:
        pass


def get_valid_note_answers() -> str:
    with state_lock:
        items = list(last_written_items)

    valid_answers = []
    for it in items:
        txt = str(it.get("answer_text", "")).strip()
        if not txt and it.get("answers"):
            txt = ", ".join(str(a).strip() for a in it.get("answers") if str(a).strip())
        if txt and txt != "(Không có nội dung trả lời)":
            valid_answers.append(txt)

    if not valid_answers:
        return ""
    return "\n".join(valid_answers)


def _auto_type_worker():
    global is_typing
    try:
        with busy_lock:
            is_currently_busy = busy

        if is_currently_busy:
            print()
            print(YELLOW + "⏳ Gemini đang phân tích đề thi, chưa có đáp án để gõ.")
            try:
                import winsound
                winsound.Beep(800, 150)
            except Exception:
                pass
            return

        text_to_type = get_valid_note_answers()
        if not text_to_type:
            print(YELLOW + "⚠️ [Chuột Trái x4] Không có nội dung đáp án tự luận / điền ngắn để gõ.")
            try:
                import winsound
                winsound.Beep(800, 200)
            except Exception:
                pass
            return

        try:
            import winsound
            winsound.Beep(1600, 60)
            winsound.Beep(2000, 60)
        except Exception:
            pass

        print()
        print_box(
            "TỰ ĐỘNG GÕ ĐÁP ÁN TỰ LUẬN (CHUỘT TRÁI x4)",
            [
                f"Độ dài ký tự  : {len(text_to_type)} ký tự",
                "Phương thức nhập: Win32 Unicode (SendInput / keybd_event)",
                "Bảo mật phím   : KHÔNG dùng Ctrl+V, KHÔNG lưu/đọc Clipboard",
                "Cơ chế an toàn : KHÔNG tự động ấn gửi hoặc nộp bài",
                "Chuột Trái x1  : Dừng gõ ngay lập tức, hủy phần chưa gõ",
                "👉 Đang tiến hành gõ trực tiếp vào ô có con trỏ...",
            ],
            color=CYAN,
            width=78,
        )

        # Chờ 0.25s để chuột nhả hoàn toàn và ô input nhận focus ổn định
        if stop_typing_event.wait(0.25):
            return

        for char in text_to_type:
            if stop_typing_event.is_set():
                break
            type_char_safe(char)
            if stop_typing_event.wait(0.015):
                break

        if not stop_typing_event.is_set():
            try:
                import winsound
                winsound.Beep(2200, 100)
            except Exception:
                pass
            print(GREEN + "✔ [Chuột Trái x4] Đã gõ xong toàn bộ đáp án vào ô nhập liệu!")

    except Exception as e:
        print(RED + f"❌ Lỗi khi tự động gõ đáp án: {e}")
    finally:
        with typing_lock:
            is_typing = False


# ==============================================================================
# HÀM HIỂN THỊ KẾT QUẢ KHI NHẤP ĐÚP CHUỘT TRÁI
# ==============================================================================
def mark_saved_coordinate():
    global last_mc_badge_text, last_mc_items, last_written_items, last_status_message, busy

    with busy_lock:
        is_currently_busy = busy

    with state_lock:
        mc_text = last_mc_badge_text
        written = list(last_written_items)
        status_msg = last_status_message

    if is_currently_busy:
        result_overlay.show_results(
            mc_badge_text="",
            written_items=[],
            status_message="",
            is_waiting=True,
        )
        return

    if not mc_text and not written and not status_msg:
        print(YELLOW + "ℹ Chưa có kết quả giải bài. Bấm Chuột Phải x2 để chụp đề!")
        result_overlay.show_results(
            mc_badge_text="",
            written_items=[],
            status_message="Chưa có kết quả. Bấm Chuột Phải x2 để giải bài!",
            is_waiting=False,
        )
        return

    result_overlay.show_results(
        mc_badge_text=mc_text,
        written_items=written,
        status_message=status_msg,
        is_waiting=False,
    )


def hide_saved_coordinate():
    result_overlay.hide_all()


# ==============================================================================
# CỬA SỔ CÀI ĐẶT SETUP
# ==============================================================================
def open_setup():
    from ui.setup_window import open_setup_dialog

    def on_save_handler(new_cfg):
        save_config(new_cfg)
        print(GREEN + "\n✔ Đã lưu cấu hình mới. Bảng thông tin đã được cập nhật!")
        show_banner()

    open_setup_dialog(CONFIG, on_save_handler)


# ==============================================================================
# LOW-LEVEL WIN32 MOUSE HOOK
# ==============================================================================
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_QUIT = 0x0012

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.c_size_t, ctypes.c_size_t)

win_user32 = ctypes.windll.user32
win_kernel32 = ctypes.windll.kernel32

win_user32.CallNextHookEx.restype = LRESULT
win_user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_size_t]

win_user32.SetWindowsHookExW.restype = ctypes.c_void_p
win_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]

win_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
win_user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

last_right_time = 0.0
last_left_time = 0.0
right_click_count = 0
left_click_count = 0
pending_left_show_timer = None
pending_left_hide_timer = None
mouse_lock = threading.Lock()


def low_level_mouse_handler(nCode, wParam, lParam):
    global last_right_time, last_left_time, right_click_count, left_click_count
    global pending_left_show_timer, pending_left_hide_timer

    if nCode >= 0:
        now = time.time()
        dbl_interval = float(CONFIG.get("double_click_interval", 0.35))

        if wParam == WM_RBUTTONDOWN:
            with mouse_lock:
                if (now - last_right_time) <= dbl_interval:
                    right_click_count += 1
                else:
                    right_click_count = 1
                last_right_time = now

                if right_click_count == 2:
                    right_click_count = 0
                    last_right_time = 0.0
                    threading.Thread(target=capture_and_send_gemini, daemon=True).start()

        elif wParam == WM_LBUTTONDOWN:
            cursor_x, cursor_y = 0, 0
            if lParam:
                try:
                    info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    cursor_x = int(info.pt.x)
                    cursor_y = int(info.pt.y)
                except Exception:
                    pass

            with mouse_lock:
                # 1. ĐANG TỰ ĐỘNG GÕ: Chuột trái 1 lần dừng gõ ngay
                if is_typing:
                    if now - typing_trigger_time >= 0.08:
                        stop_auto_typing()
                        left_click_count = 0
                        last_left_time = 0.0
                        return win_user32.CallNextHookEx(None, nCode, wParam, lParam)
                    else:
                        return win_user32.CallNextHookEx(None, nCode, wParam, lParam)

                # 2. KHÔNG ĐANG GÕ:
                just_hid_overlay = False
                if result_overlay.is_visible():
                    if not result_overlay.is_point_in_text_region(cursor_x, cursor_y):
                        # ẨN NGAY LẬP TỨC (0ms) - Cấp độ Windows Window Handle
                        hide_saved_coordinate()
                        just_hid_overlay = True
                        if pending_left_show_timer:
                            try:
                                pending_left_show_timer.cancel()
                            except Exception:
                                pass
                            pending_left_show_timer = None

                if (now - last_left_time) <= dbl_interval:
                    left_click_count += 1
                else:
                    left_click_count = 1
                last_left_time = now

                # Chuột trái x4 -> Bắt đầu tự gõ
                if left_click_count >= 4:
                    if pending_left_show_timer:
                        try:
                            pending_left_show_timer.cancel()
                        except Exception:
                            pass
                        pending_left_show_timer = None

                    left_click_count = 0
                    last_left_time = 0.0
                    start_auto_typing()

                # Chuột trái x2 -> Hiện kết quả (chỉ hiện khi không phải vừa ấn ẩn)
                elif left_click_count == 2:
                    if just_hid_overlay:
                        # Vừa ấn ẩn xong, giữ nguyên trạng thái ẩn
                        pass
                    else:
                        wait_for_quad = max(0.20, dbl_interval + 0.05)

                        def _execute_show_if_not_quad():
                            global left_click_count, pending_left_show_timer, last_left_time
                            with mouse_lock:
                                if left_click_count == 2:
                                    left_click_count = 0
                                    last_left_time = 0.0
                                    pending_left_show_timer = None
                                    threading.Thread(target=mark_saved_coordinate, daemon=True).start()

                        if pending_left_show_timer:
                            try:
                                pending_left_show_timer.cancel()
                            except Exception:
                                pass
                        pending_left_show_timer = threading.Timer(wait_for_quad, _execute_show_if_not_quad)
                        pending_left_show_timer.daemon = True
                        pending_left_show_timer.start()

                elif left_click_count == 1:
                    # Đã ẩn ngay lập tức ở trên (0ms)
                    pass

    try:
        return win_user32.CallNextHookEx(None, nCode, wParam, lParam)
    except Exception:
        return 0

_c_mouse_proc = HOOKPROC(low_level_mouse_handler)
_hook_thread_id = None
_h_hook = None
_hook_thread = None

def _mouse_message_loop():
    global _hook_thread_id, _h_hook
    _hook_thread_id = win_kernel32.GetCurrentThreadId()
    _h_hook = win_user32.SetWindowsHookExW(WH_MOUSE_LL, _c_mouse_proc, None, 0)
    msg = wintypes.MSG()
    while win_user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        pass
    if _h_hook:
        try:
            win_user32.UnhookWindowsHookEx(_h_hook)
        except Exception:
            pass
        _h_hook = None

def start_mouse_listener():
    global _hook_thread
    _hook_thread = threading.Thread(target=_mouse_message_loop, daemon=True, name="LowLevelMouseHook")
    _hook_thread.start()

def stop_mouse_listener():
    global _hook_thread_id, _h_hook, pending_left_show_timer, pending_left_hide_timer
    stop_auto_typing()
    if pending_left_show_timer:
        try:
            pending_left_show_timer.cancel()
        except Exception:
            pass
        pending_left_show_timer = None
    if pending_left_hide_timer:
        try:
            pending_left_hide_timer.cancel()
        except Exception:
            pass
        pending_left_hide_timer = None
    if _hook_thread_id:
        try:
            win_user32.PostThreadMessageW(_hook_thread_id, WM_QUIT, 0, 0)
        except Exception:
            pass
    if _h_hook:
        try:
            win_user32.UnhookWindowsHookEx(_h_hook)
        except Exception:
            pass
        _h_hook = None


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def on_update_found(update_info):
    """Thông báo có bản cập nhật mới không gây gián đoạn."""
    print(YELLOW + f"\n🔔 Có bản cập nhật mới ToolMouse v{update_info.new_version}: {update_info.release_url}")


def on_sheets_sync_success(keys):
    """Gọi lại khi tải thành công khóa từ Google Sheets ở luồng nền."""
    masked = mask_key(keys.get("gemini", ""))
    print(GREEN + f"\n[Google Sheets] Đã đồng bộ khóa API Gemini mới nhất ({masked}) thành công!")


def main():
    if "--setup" in sys.argv:
        open_setup()
        return

    # 1. Khởi động giao diện console & nạp cấu hình nhanh
    t0 = time.perf_counter()
    load_config()
    show_banner()

    # 2. Đăng ký Hook chuột ngay lập tức (sub-second)
    start_mouse_listener()
    t_ready = time.perf_counter()
    startup_ms = round((t_ready - t0) * 1000, 1)

    dbl_interval = float(CONFIG.get("double_click_interval", 0.35))
    print(GREEN + f"✔ Đã kích hoạt Hook chuột sau {startup_ms}ms (Tốc độ khởi động siêu tốc)")
    print(WHITE + f"  • Khoảng cách nhấp chuột : <= {dbl_interval}s")
    print(WHITE + f"  • File cấu hình          : C:\\duc\\configs\\seb_mouse_v32.json")
    print(YELLOW + "  • Phím F2                : Mở cài đặt (Setup)")
    print(YELLOW + "  • Phím ESC               : Thoát tool")
    print()

    # 3. Chạy các tác vụ mạng ở chế độ chạy ngầm (Non-blocking)
    sheets_manager.start_background_sync(on_success_callback=on_sheets_sync_success)
    start_background_update_check(on_update_found=on_update_found)

    # Đăng ký hotkey F2 để mở Setup
    try:
        keyboard.add_hotkey("f2", open_setup)
    except Exception:
        pass

    try:
        keyboard.wait("esc")
    except KeyboardInterrupt:
        pass
    finally:
        stop_mouse_listener()
        result_overlay.hide_all()
        print(YELLOW + f"\nĐã tắt {TOOL_TITLE}. Tạm biệt!")


if __name__ == "__main__":
    main()
