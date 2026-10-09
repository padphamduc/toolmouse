# -*- coding: utf-8 -*-
"""
Overlay Rendering Engine for Tool v3.2
- Form mảnh mai ẩn giấu (như '1abd', '1 A B D', '99 A')
- HOÀN TOÀN KHÔNG CÓ VIỀN HỒNG: Sử dụng phối màu Grayscale thuần túy, loại bỏ triệt để màu hồng #FF00FF
- Nền sáng: Dùng màu nền #FFFFFF và chữ xám đậm #1A1A1A, mép khử răng cưa hòa sắc mượt mà không lem màu
- Nền tối: Dùng màu nền #000000 và chữ xám bạc #CDD5E2
- Tự động kiểm tra toạ độ an toàn (Safe Bounds Check): Tránh tuyệt đối lỗi trôi toạ độ ra ngoài màn hình
- TÍNH NĂNG CHUYỂN ĐỔI ĐỘ MỜ BẰNG 1 CÚ NHẤP CHUỘT VÀO ĐÁP ÁN:
  Chu kỳ: 2% -> 4% -> 6% -> 8% -> 10% -> 20% -> 40% -> 60% -> 80% -> 100% và đảo ngược lại, tự động lưu!
- Hỗ trợ KÉO THẢ (Drag and Drop) mượt mà đến mọi vị trí trên màn hình
- TỰ ĐỘNG GHI NHỚ VỊ TRÍ lần cuối khi thả để các lần sau mở đúng vị trí đó
- Vị trí mặc định: Tại khu vực đồng hồ hệ thống trên Taskbar
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
import threading
import tkinter as tk
from typing import List, Dict, Any, Tuple, Optional

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

OPACITY_STEPS = [2, 4, 6, 8, 10, 20, 40, 60, 80, 100]


class ResultOverlayV32:
    def __init__(self, get_config_func, on_save_pos_func=None, on_save_opacity_func=None):
        self.get_config = get_config_func
        self.on_save_pos = on_save_pos_func
        self.on_save_opacity = on_save_opacity_func
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="OverlayGUIThread")
        self._ready = threading.Event()
        self._root = None
        self._q_badge_win = None
        self._q_hwnd = None
        self._badge_x = 0
        self._badge_y = 0
        self._badge_w = 0
        self._badge_h = 0
        self._is_showing = False
        self._is_dragging = False
        self._has_moved = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x = 0
        self._win_start_y = 0
        self.last_show_time = 0.0

        # Quản lý chu kỳ độ mờ
        self._current_opacity = 100
        self._opacity_index = len(OPACITY_STEPS) - 1
        self._opacity_direction = -1
        self._colorkey_hex = 0x00FFFFFF
        self._last_cycle_time = 0.0

        self._thread.start()
        self._ready.wait(timeout=3)

    def _run_loop(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._ready.set()
        self._root.mainloop()

    def is_visible(self) -> bool:
        return getattr(self, "_is_showing", False) and bool(self._q_badge_win)

    def is_point_in_badge(self, x: int, y: int) -> bool:
        """Kiểm tra xem toạ độ chuột có nằm trong vùng của form mảnh mai (có thêm vùng đệm) hay không."""
        if not getattr(self, "_is_showing", False) or not self._q_badge_win:
            return False
        margin = 10  # 10px đệm xung quanh giúp người dùng dễ dàng bấm trúng để kéo thả / click
        x1 = self._badge_x - margin
        y1 = self._badge_y - margin
        x2 = self._badge_x + self._badge_w + margin
        y2 = self._badge_y + self._badge_h + margin
        return (x1 <= x <= x2) and (y1 <= y <= y2)

    def get_badge_pos(self) -> Tuple[int, int]:
        """Lấy toạ độ (x, y) hiện tại của badge."""
        return (self._badge_x, self._badge_y)

    def move_badge(self, x: int, y: int):
        """Di chuyển badge ngay lập tức ở cấp độ Win32 SetWindowPos (0ms latency, mượt 60fps+)."""
        self._badge_x = int(x)
        self._badge_y = int(y)
        if self._q_hwnd:
            try:
                ctypes.windll.user32.SetWindowPos(
                    self._q_hwnd, HWND_TOPMOST, int(x), int(y), 0, 0,
                    SWP_NOSIZE | SWP_NOACTIVATE
                )
            except Exception:
                pass
        if self._q_badge_win and self._root:
            try:
                self._root.after(0, lambda: self._q_badge_win.geometry(f"+{int(x)}+{int(y)}") if self._q_badge_win else None)
            except Exception:
                pass

    def set_opacity(self, op: int):
        """Thiết lập độ mờ ngay lập tức ở cả cấp độ Win32 Layered Window và Tkinter."""
        self._current_opacity = max(1, min(100, int(op)))
        alpha_ratio = float(self._current_opacity) / 100.0
        alpha_byte = max(1, min(255, int(round(255 * alpha_ratio))))

        if self._q_hwnd:
            try:
                ctypes.windll.user32.SetLayeredWindowAttributes(
                    self._q_hwnd, self._colorkey_hex, alpha_byte, 1 | 2
                )
            except Exception:
                pass
        if self._q_badge_win and self._root:
            try:
                self._root.after(0, lambda: self._q_badge_win.attributes("-alpha", alpha_ratio) if self._q_badge_win else None)
            except Exception:
                pass

    def cycle_opacity(self) -> int:
        """
        Đổi độ mờ tuần tự khi bấm 1 lần vào số đáp án:
        2% -> 4% -> 6% -> 8% -> 10% -> 20% -> 40% -> 60% -> 80% -> 100% và đảo ngược lại.
        Tự động lưu vào cấu hình ngay sau khi click!
        """
        now = time.time()
        if now - getattr(self, "_last_cycle_time", 0.0) < 0.15:
            return getattr(self, "_current_opacity", 100)
        self._last_cycle_time = now

        if not hasattr(self, "_opacity_index"):
            self._opacity_index = len(OPACITY_STEPS) - 1
            self._opacity_direction = -1

        if self._opacity_direction == 1:
            self._opacity_index += 1
            if self._opacity_index >= len(OPACITY_STEPS) - 1:
                self._opacity_index = len(OPACITY_STEPS) - 1
                self._opacity_direction = -1
        else:
            self._opacity_index -= 1
            if self._opacity_index <= 0:
                self._opacity_index = 0
                self._opacity_direction = 1

        new_op = OPACITY_STEPS[self._opacity_index]
        self.set_opacity(new_op)

        if self.on_save_opacity:
            try:
                self.on_save_opacity(new_op)
            except Exception:
                pass

        return new_op

    def show_results(
        self,
        mc_badge_text: str = "",
        written_items: List[Dict[str, Any]] = None,
        status_message: str = "",
        is_waiting: bool = False,
    ):
        if not self._root:
            return
        self._root.after(
            0,
            self._show_results_on_ui_thread,
            mc_badge_text,
            written_items or [],
            status_message,
            is_waiting,
        )

    def hide_all(self):
        """Ẩn form mảnh mai ngay lập tức (0ms) ở cấp độ Win32 Window Handle."""
        self._is_showing = False
        user32 = ctypes.windll.user32
        if getattr(self, "_q_hwnd", None):
            try:
                user32.ShowWindow(self._q_hwnd, 0)  # SW_HIDE
            except Exception:
                pass

        if self._root:
            self._root.after(0, self._hide_all_on_ui_thread)

    def _hide_all_on_ui_thread(self):
        self._is_showing = False
        if self._q_badge_win:
            try:
                self._q_badge_win.destroy()
            except Exception:
                pass
            self._q_badge_win = None
        self._q_hwnd = None

    def _get_toplevel_hwnd(self, win):
        try:
            f = win.frame()
            if f:
                return int(f, 16)
        except Exception:
            pass
        try:
            user32 = ctypes.windll.user32
            child = win.winfo_id()
            p = user32.GetParent(child)
            return p if p else child
        except Exception:
            return win.winfo_id()

    def _show_results_on_ui_thread(
        self,
        mc_badge_text: str,
        written_items: List[Dict[str, Any]],
        status_message: str,
        is_waiting: bool,
    ):
        self._hide_all_on_ui_thread()
        cfg = self.get_config()

        self.last_show_time = time.time()
        screen_w = max(self._root.winfo_screenwidth(), ctypes.windll.user32.GetSystemMetrics(0))
        screen_h = max(self._root.winfo_screenheight(), ctypes.windll.user32.GetSystemMetrics(1))

        work_l, work_t, work_r, work_b = 0, 0, screen_w, screen_h
        if os.name == "nt":
            try:
                rect = wintypes.RECT()
                SPI_GETWORKAREA = 0x0030
                if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                    work_l = int(rect.left)
                    work_t = int(rect.top)
                    work_r = int(rect.right)
                    work_b = int(rect.bottom)
            except Exception:
                pass

        # ----------------------------------------------------------------------
        # 1. XÂY DỰNG NỘI DUNG FORM MẢNH MAI ẨN GIẤU
        # ----------------------------------------------------------------------
        badge_text = ""
        if is_waiting:
            badge_text = "⏳"
        elif mc_badge_text and str(mc_badge_text).strip():
            badge_text = str(mc_badge_text).strip()
        elif written_items:
            lines = []
            for it in written_items:
                q_num_item = str(it.get("question_number", "")).strip()
                ans_content = str(it.get("answer_text", "")).strip()
                if not ans_content and it.get("answers"):
                    ans_content = " ".join(str(a) for a in it.get("answers"))
                if ans_content:
                    if q_num_item:
                        lines.append(f"{q_num_item} {ans_content}")
                    else:
                        lines.append(ans_content)
            badge_text = "\n".join(lines).strip()
        elif status_message and str(status_message).strip():
            badge_text = str(status_message).strip()

        if not badge_text:
            badge_text = "Chưa có kết quả"

        lines = [line.strip() for line in badge_text.split("\n") if line.strip()]
        line_count = len(lines)
        font_family = str(cfg.get("number_font_family", "Times New Roman")).strip() or "Times New Roman"
        font_size = 11 if line_count <= 2 else 10

        try:
            # 2. TẠO CỬA SỔ TKINTER TOPLEVEL
            q_win = tk.Toplevel(self._root)
            q_win.overrideredirect(True)
            q_win.attributes("-topmost", True)
            q_win.lift()

            # 3. ĐO ĐẠC KÍCH THƯỚC CHỮ BẰNG DUMMY CANVAS
            dummy_canvas = tk.Canvas(q_win, highlightthickness=0)
            temp_item = dummy_canvas.create_text(
                0, 0,
                text=badge_text,
                font=(font_family, font_size),
                justify="center",
                anchor="nw"
            )
            dummy_canvas.update_idletasks()
            bbox = dummy_canvas.bbox(temp_item)
            if bbox:
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            else:
                text_w = 40
                text_h = 20
            dummy_canvas.destroy()

            pad_x = 6
            pad_y = 2
            w = max(38, text_w + pad_x * 2)
            h = max(20, text_h + pad_y * 2)

            # 4. TÍNH TOÁN TOẠ ĐỘ & KIỂM TRA GIỚI HẠN AN TOÀN (BOUNDS CHECK)
            saved_x = cfg.get("badge_pos_x")
            saved_y = cfg.get("badge_pos_y")

            # Nếu toạ độ đã lưu bị văng ra ngoài màn hình do đổi độ phân giải/DPI -> Tự động khôi phục
            if saved_x is not None and saved_y is not None:
                sx = int(saved_x)
                sy = int(saved_y)
                if sx < 0 or sx > (screen_w - 20) or sy < 0 or sy > (screen_h - 20):
                    saved_x = None
                    saved_y = None

            if saved_x is not None and saved_y is not None:
                x = int(saved_x)
                y = int(saved_y)
                x = max(0, min(screen_w - w, x))
                y = max(0, min(screen_h - h, y))
            else:
                # Mặc định: Nằm ngay tại khu vực đồng hồ hệ thống ở góc dưới bên phải
                tb_h = max(36, screen_h - work_b) if screen_h > work_b else 40
                clock_right_margin = 75
                if screen_h > work_b:
                    y = work_b + (tb_h - h) // 2
                else:
                    y = screen_h - h - 6
                x = max(10, screen_w - w - clock_right_margin)

            # 5. KHỬ VIỀN HỒNG: DÙNG MÀU NỀN VÀ MÀU TRONG SUỐT GRAYSCALE CHUẨN
            # Tuyệt đối không dùng #FF00FF (Màu hồng magenta)
            is_light_bg = True
            try:
                hdc = ctypes.windll.user32.GetDC(0)
                pixel = ctypes.windll.gdi32.GetPixel(hdc, int(x + w // 2), int(y + h // 2))
                ctypes.windll.user32.ReleaseDC(0, hdc)
                if pixel != -1:
                    pr = pixel & 0xFF
                    pg = (pixel >> 8) & 0xFF
                    pb = (pixel >> 16) & 0xFF
                    lum = 0.299 * pr + 0.587 * pg + 0.114 * pb
                    is_light_bg = (lum > 140)
            except Exception:
                pass

            if is_light_bg:
                bg_key = "#FFFFFF"
                text_color = "#1A1A1A"
                colorkey_hex = 0x00FFFFFF
            else:
                bg_key = "#000000"
                text_color = "#CDD5E2"
                colorkey_hex = 0x00000000

            self._colorkey_hex = colorkey_hex

            # 6. KHỞI TẠO ĐỘ MỜ (OPACITY) TỪ CẤU HÌNH
            saved_op = int(cfg.get("number_opacity", 100))
            self._current_opacity = max(1, min(100, saved_op))
            if self._current_opacity in OPACITY_STEPS:
                self._opacity_index = OPACITY_STEPS.index(self._current_opacity)
            else:
                self._opacity_index = min(range(len(OPACITY_STEPS)), key=lambda i: abs(OPACITY_STEPS[i] - self._current_opacity))
            self._opacity_direction = -1 if self._opacity_index == len(OPACITY_STEPS) - 1 else 1

            alpha_ratio = float(self._current_opacity) / 100.0
            q_win.attributes("-alpha", alpha_ratio)

            q_win.configure(bg=bg_key)
            q_win.attributes("-transparentcolor", bg_key)

            q_canvas = tk.Canvas(q_win, bg=bg_key, highlightthickness=0)
            q_canvas.pack(fill="both", expand=True)

            text_item = q_canvas.create_text(
                w // 2, h // 2,
                text=badge_text,
                fill=text_color,
                font=(font_family, font_size),
                justify="center",
                anchor="center"
            )

            self._badge_x = x
            self._badge_y = y
            self._badge_w = w
            self._badge_h = h

            q_win.geometry(f"{w}x{h}+{x}+{y}")
            q_win.update_idletasks()

            # 7. GẮN SỰ KIỆN KÉO THẢ (DRAG & DROP) VÀ NHẤP ĐỔI ĐỘ MỜ (CLICK OPACITY)
            def _tk_on_press(event):
                self._is_dragging = True
                self._has_moved = False
                self._drag_start_x = event.x_root
                self._drag_start_y = event.y_root
                self._win_start_x = self._badge_x
                self._win_start_y = self._badge_y

            def _tk_on_motion(event):
                if not getattr(self, "_is_dragging", False):
                    return
                dx = event.x_root - self._drag_start_x
                dy = event.y_root - self._drag_start_y
                if abs(dx) > 3 or abs(dy) > 3:
                    self._has_moved = True
                    self.move_badge(self._win_start_x + dx, self._win_start_y + dy)

            def _tk_on_release(event):
                if getattr(self, "_is_dragging", False):
                    self._is_dragging = False
                    if getattr(self, "_has_moved", False):
                        if self.on_save_pos:
                            self.on_save_pos(self._badge_x, self._badge_y)
                    else:
                        # Bấm 1 lần vào số đáp án -> Đổi độ mờ và lưu cấu hình ngay
                        self.cycle_opacity()

            q_canvas.bind("<Button-1>", _tk_on_press)
            q_canvas.bind("<B1-Motion>", _tk_on_motion)
            q_canvas.bind("<ButtonRelease-1>", _tk_on_release)

            # 8. ÁP DỤNG THUỘC TÍNH WIN32 WINDOW
            top_q_hwnd = self._get_toplevel_hwnd(q_win)
            user32 = ctypes.windll.user32
            q_style = user32.GetWindowLongW(top_q_hwnd, GWL_EXSTYLE)
            q_style |= (WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW)
            q_style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(top_q_hwnd, GWL_EXSTYLE, q_style)

            alpha_byte = max(1, min(255, int(round(255 * alpha_ratio))))
            user32.SetLayeredWindowAttributes(top_q_hwnd, colorkey_hex, alpha_byte, 1 | 2)

            # Luôn giữ ở lớp trên cùng (HWND_TOPMOST) và hiển thị
            user32.SetWindowPos(
                top_q_hwnd, HWND_TOPMOST, int(x), int(y), int(w), int(h),
                SWP_NOACTIVATE | SWP_SHOWWINDOW
            )
            user32.ShowWindow(top_q_hwnd, 5)  # SW_SHOW = 5

            self._q_badge_win = q_win
            self._q_hwnd = top_q_hwnd
            self._is_showing = True
        except Exception as e:
            pass
