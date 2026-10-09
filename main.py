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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
    "number_opacity": 100,
    "text_opacity": 100,
    "text_font_size": 11,
    "text_fg": "#111111",
    "number_fg": "#CDD5E2",
    "number_font_family": "Times New Roman",
    "badge_pos_x": None,
    "badge_pos_y": None,
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


def save_badge_position(x: int, y: int):
    """Ghi nhớ toạ độ lần cuối khi người dùng thả badge (Drag and Drop)."""
    global CONFIG
    CONFIG["badge_pos_x"] = int(x)
    CONFIG["badge_pos_y"] = int(y)
    save_config({"badge_pos_x": int(x), "badge_pos_y": int(y)})
    try:
        print(GREEN + f"✔ Đã ghi nhớ vị trí hiển thị: ({int(x)}, {int(y)})")
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

# ==============================================================================
# QUẢN LÝ ẨN / HIỆN CỬA SỔ TOOL BẰNG CTRL + SHIFT + M
# ==============================================================================
def get_console_hwnd():
    if os.name == "nt":
        return ctypes.windll.kernel32.GetConsoleWindow()
    return None


def is_console_visible() -> bool:
    hwnd = get_console_hwnd()
    if hwnd:
        return bool(ctypes.windll.user32.IsWindowVisible(hwnd))
    return False


def hide_console():
    hwnd = get_console_hwnd()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0


def show_console():
    hwnd = get_console_hwnd()
    if not hwnd and os.name == "nt":
        try:
            ctypes.windll.kernel32.AllocConsole()
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleTitleW(TOOL_TITLE)
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
            sys.stderr = open("CONOUT$", "w", encoding="utf-8")
            hwnd = get_console_hwnd()
        except Exception:
            pass

    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW = 5
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        show_banner()


def toggle_console():
    if is_console_visible():
        hide_console()
    else:
        show_console()


# Ẩn cửa sổ console ngay lập tức khi khởi động (chỉ hiện khi bấm Ctrl+Shift+M)
if os.name == "nt" and "--setup" not in sys.argv and "--no-hide" not in sys.argv:
    hide_console()

# Khởi tạo overlay hiển thị kết quả
result_overlay = ResultOverlayV32(get_config_func=load_config, on_save_pos_func=save_badge_position)

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
    num_op = CONFIG.get("number_opacity", 4)
    cursor_dur = CONFIG.get("load_cursor_duration", 1.0)
    sheets_info = sheets_manager.get_status_info()
    api_status = f"Google Sheets ({sheets_info.get('gemini_masked', 'Đang tải...')})" if sheets_info.get("has_gemini") else "Đang đồng bộ ngầm..."

    print_box(
        "ĐỨC DẠY BẠN HỌC NHÉ <3",
        [
            f"TOOLMOUSE v{CURRENT_VERSION} – CHUYÊN BIỆT CHO SEB (ĐÁP ÁN FORM MẢNH MAI)",
            "Ctrl + Shift + M: Ẩn / Hiện cửa sổ tool này",
            "Chuột Phải x2   : Chụp toàn màn hình & gửi Gemini phân tích",
            "Chuột Trái x4   : Tự động gõ đáp án tự luận vào ô đang có con trỏ",
            "Chuột Trái x2   : Hiện kết quả (Form mảnh mai ẩn giấu)",
            "Kéo thả chuột   : Nhấp giữ chuột trái vào đáp án để kéo thả (Tự nhớ vị trí)",
            "Chuột Trái x1   : Dừng ngay khi đang gõ; nhấp ra ngoài đáp án để ẩn (0ms)",
            "Phím F2         : Mở cửa sổ Cài đặt cấu hình (Setup)",
            "Phím ESC        : Thoát khỏi tool (khi cửa sổ đang mở)",
            "----------------------------------------------------------------------------",
            "Vị trí & kiểu chữ: Kéo thả tự do / Mặc định ở đồng hồ (Times New Roman • Rõ 100%)",
            f"Load chuột      : {cursor_dur}s • Model: {model_name}",
            f"Khóa API        : {api_status}",
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
            summary_lines.append(f"Tự luận/Điền: {len(written_items)} câu")
        if status_msg:
            summary_lines.append(f"Thông báo  : {status_msg}")

        summary_lines.extend([
            "👉 BẤM 2 LẦN CHUỘT TRÁI để hiện kết quả (Form mảnh mai)!",
            "👉 NHẤP GIỮ CHUỘT TRÁI vào đáp án để kéo thả (Tự nhớ vị trí lần cuối)!",
            "👉 BẤM 1 LẦN CHUỘT TRÁI ngoài đáp án để ẩn kết quả (0ms).",
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

    try:
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
            try:
                print(YELLOW + "ℹ Chưa có kết quả giải bài. Bấm Chuột Phải x2 để chụp đề!")
            except Exception:
                pass
            result_overlay.show_results(
                mc_badge_text="Chưa có kết quả",
                written_items=[],
                status_message="",
                is_waiting=False,
            )
            return

        result_overlay.show_results(
            mc_badge_text=mc_text,
            written_items=written,
            status_message=status_msg,
            is_waiting=False,
        )
    except Exception as e:
        try:
            print(RED + f"❌ Lỗi hiển thị: {e}")
        except Exception:
            pass


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
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
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

is_dragging_badge = False
drag_start_mouse_x = 0
drag_start_mouse_y = 0
drag_start_badge_x = 0
drag_start_badge_y = 0
has_moved_while_dragging = False


def low_level_mouse_handler(nCode, wParam, lParam):
    global last_right_time, last_left_time, right_click_count, left_click_count
    global pending_left_show_timer, pending_left_hide_timer
    global is_dragging_badge, drag_start_mouse_x, drag_start_mouse_y
    global drag_start_badge_x, drag_start_badge_y, has_moved_while_dragging

    if nCode >= 0:
        now = time.time()
        dbl_interval = float(CONFIG.get("double_click_interval", 0.35))

        cursor_x, cursor_y = 0, 0
        if lParam:
            try:
                info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                cursor_x = int(info.pt.x)
                cursor_y = int(info.pt.y)
            except Exception:
                pass

        # ----------------------------------------------------------------------
        # 1. XỬ LÝ KÉO THẢ (DRAG AND DROP) KHI DI CHUYỂN CHUỘT
        # ----------------------------------------------------------------------
        if wParam == WM_MOUSEMOVE:
            if is_dragging_badge:
                dx = cursor_x - drag_start_mouse_x
                dy = cursor_y - drag_start_mouse_y
                if abs(dx) > 1 or abs(dy) > 1:
                    has_moved_while_dragging = True
                    result_overlay.move_badge(drag_start_badge_x + dx, drag_start_badge_y + dy)
            try:
                return win_user32.CallNextHookEx(None, nCode, wParam, lParam)
            except Exception:
                return 0

        # ----------------------------------------------------------------------
        # 2. XỬ LÝ THẢ CHUỘT (DROP) VÀ LƯU VỊ TRÍ MỚI
        # ----------------------------------------------------------------------
        elif wParam == WM_LBUTTONUP:
            if is_dragging_badge:
                is_dragging_badge = False
                if has_moved_while_dragging:
                    final_x, final_y = result_overlay.get_badge_pos()
                    save_badge_position(final_x, final_y)
                with mouse_lock:
                    left_click_count = 0
                    last_left_time = 0.0
            try:
                return win_user32.CallNextHookEx(None, nCode, wParam, lParam)
            except Exception:
                return 0

        # ----------------------------------------------------------------------
        # 3. XỬ LÝ CHUỘT PHẢI (CHỤP TOÀN MÀN HÌNH & GỬI GEMINI GIẢI BÀI)
        # ----------------------------------------------------------------------
        elif wParam == WM_RBUTTONDOWN:
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

        # ----------------------------------------------------------------------
        # 4. XỬ LÝ CHUỘT TRÁI (KÉO THẢ / ẨN / HIỆN / GÕ TỰ LUẬN)
        # ----------------------------------------------------------------------
        elif wParam == WM_LBUTTONDOWN:
            with mouse_lock:
                # 4.1 Đang tự động gõ: Chuột trái 1 lần dừng gõ ngay
                if is_typing:
                    if now - typing_trigger_time >= 0.08:
                        stop_auto_typing()
                        left_click_count = 0
                        last_left_time = 0.0
                        return win_user32.CallNextHookEx(None, nCode, wParam, lParam)
                    else:
                        return win_user32.CallNextHookEx(None, nCode, wParam, lParam)

                # 4.2 Kiểm tra nếu kết quả đang hiển thị:
                if result_overlay.is_visible():
                    if result_overlay.is_point_in_badge(cursor_x, cursor_y):
                        # Bắt đầu kéo thả form mảnh mai! Không ẩn kết quả
                        is_dragging_badge = True
                        has_moved_while_dragging = False
                        drag_start_mouse_x = cursor_x
                        drag_start_mouse_y = cursor_y
                        drag_start_badge_x, drag_start_badge_y = result_overlay.get_badge_pos()
                        left_click_count = 0
                        last_left_time = 0.0
                        return win_user32.CallNextHookEx(None, nCode, wParam, lParam)
                    else:
                        # Nhấp ra NGOÀI form đáp án: Ẩn ngay lập tức (0ms)
                        hide_saved_coordinate()
                        # Reset để cú nhấp ẩn không làm lệch số lần nhấp đúp sau
                        left_click_count = 0
                        last_left_time = 0.0
                        return win_user32.CallNextHookEx(None, nCode, wParam, lParam)

                # 4.3 Khi kết quả đang ẩn: Tính số lần nhấp chuột
                if (now - last_left_time) <= dbl_interval:
                    left_click_count += 1
                else:
                    left_click_count = 1
                last_left_time = now

                # Chuột trái x4 -> Bắt đầu tự gõ
                if left_click_count >= 4:
                    left_click_count = 0
                    last_left_time = 0.0
                    start_auto_typing()

                # Chuột trái x2 -> HIỂN THỊ KẾT QUẢ NGAY LẬP TỨC (0ms, KHÔNG CHỜ TIMER!)
                elif left_click_count == 2:
                    threading.Thread(target=mark_saved_coordinate, daemon=True).start()

                elif left_click_count == 1:
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
    """Đồng bộ ngầm khóa từ Google Sheets (không in thông báo để giữ màn hình gọn gàng)."""
    pass


_exit_event = threading.Event()


def on_esc_key():
    """Phím ESC chỉ thoát nếu cửa sổ console đang hiển thị để tránh thoát nhầm trong lúc làm bài thi."""
    if is_console_visible():
        _exit_event.set()


def main():
    if "--setup" in sys.argv:
        open_setup()
        return

    # 1. Ẩn cửa sổ console ngay lập tức & xoay con trỏ chuột 1 giây báo hiệu đã kích hoạt
    hide_console()
    show_loading_cursor_once(1.0)

    # 2. Nạp cấu hình & Đăng ký Hook chuột ngay lập tức (sub-second)
    load_config()
    start_mouse_listener()

    # 3. Chạy các tác vụ mạng ở chế độ chạy ngầm (Non-blocking)
    sheets_manager.start_background_sync(on_success_callback=on_sheets_sync_success)
    start_background_update_check(on_update_found=on_update_found)

    # 4. Đăng ký các hotkey toàn cục
    try:
        # Bắt buộc bấm Ctrl+Shift+M để hiện / ẩn cửa sổ tool
        keyboard.add_hotkey("ctrl+shift+m", toggle_console)
    except Exception:
        pass

    try:
        # Phím F2 mở cài đặt (Setup)
        keyboard.add_hotkey("f2", open_setup)
    except Exception:
        pass

    try:
        # Thoát tool an toàn
        keyboard.add_hotkey("esc", on_esc_key)
        keyboard.add_hotkey("ctrl+shift+q", lambda: _exit_event.set())
    except Exception:
        pass

    try:
        while not _exit_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        stop_mouse_listener()
        result_overlay.hide_all()
        print(YELLOW + f"\nĐã tắt {TOOL_TITLE}. Tạm biệt!")


if __name__ == "__main__":
    main()
