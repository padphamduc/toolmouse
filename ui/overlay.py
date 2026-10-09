# -*- coding: utf-8 -*-
"""
Overlay Rendering Engine for Tool v3.2
- Form mảnh mai ẩn giấu (như '1abd', '1 A B D', '99 A')
- SỬ DỤNG CƠ CHẾ UPDATE LAYERED WINDOW 32-BIT ARGB CHUẨN XÁC
- XÓA BỎ 100% VIỀN HỒNG / CHROMA KEY: Không dùng màu nền hồng, không bị lem màu viền chữ
- Trong suốt hoàn toàn từng pixel (Per-pixel Alpha), chữ khử răng cưa mượt mà không tì vết
- Hỗ trợ KÉO THẢ (Drag and Drop) mượt mà đến mọi vị trí trên màn hình
- TỰ ĐỘNG GHI NHỚ VỊ TRÍ lần cuối khi thả để các lần sau mở đúng vị trí đó
- Vị trí mặc định: Tại khu vực đồng hồ hệ thống trên Taskbar
- Màu chữ tự động thích ứng với màu nền đồng hồ (nền sáng dùng xám đậm #1F1F1F, nền tối dùng #CDD5E2)
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
import threading
import tkinter as tk
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

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
ULW_ALPHA = 2


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


def get_pil_font(size: int = 12):
    font_paths = [
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


class ResultOverlayV32:
    def __init__(self, get_config_func, on_save_pos_func=None):
        self.get_config = get_config_func
        self.on_save_pos = on_save_pos_func
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
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x = 0
        self._win_start_y = 0
        self.last_show_time = 0.0
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
        margin = 10  # 10px đệm xung quanh giúp người dùng dễ dàng bấm trúng để kéo thả
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
        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()

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
        # XÂY DỰNG NỘI DUNG FORM MẢNH MAI ẨN GIẤU
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
        font_size = 12 if line_count <= 2 else 11
        pil_font = get_pil_font(font_size)

        try:
            # 1. ĐO ĐẠC KÍCH THƯỚC CHỮ CHÍNH XÁC BẰNG PIL
            dummy_im = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
            dummy_draw = ImageDraw.Draw(dummy_im)

            max_line_w = 0
            line_heights = []
            for l in lines:
                bb = dummy_draw.textbbox((0, 0), l, font=pil_font)
                lw = bb[2] - bb[0]
                lh = bb[3] - bb[1]
                if lw > max_line_w:
                    max_line_w = lw
                line_heights.append(lh)

            total_h = sum(line_heights) + (line_count - 1) * 3
            pad_x = 8
            pad_y = 4
            w = max(38, max_line_w + pad_x * 2)
            h = max(22, total_h + pad_y * 2)

            # 2. XÁC ĐỊNH VỊ TRÍ HIỂN THỊ (ĐÃ LƯU HOẶC MẶC ĐỊNH KHU VỰC ĐỒNG HỒ)
            saved_x = cfg.get("badge_pos_x")
            saved_y = cfg.get("badge_pos_y")

            if saved_x is not None and saved_y is not None:
                x = int(saved_x)
                y = int(saved_y)
                x = max(0, min(screen_w - w, x))
                y = max(0, min(screen_h - h, y))
            else:
                tb_h = max(36, screen_h - work_b) if screen_h > work_b else 40
                clock_right_margin = 75
                if screen_h > work_b:
                    y = work_b + (tb_h - h) // 2
                else:
                    y = screen_h - h - 6
                x = max(10, screen_w - w - clock_right_margin)

            # 3. TỰ ĐỘNG THÍCH ỨNG MÀU CHỮ THEO NỀN MÀN HÌNH TẠI VỊ TRÍ ĐÓ
            # Nền sáng (như Windows Light Theme Taskbar): màu xám đen #1F1F1F
            # Nền tối (như Windows Dark Theme Taskbar): màu xám bạc #CDD5E2
            fill_r, fill_g, fill_b = 31, 31, 31
            try:
                hdc = ctypes.windll.user32.GetDC(0)
                pixel = ctypes.windll.gdi32.GetPixel(hdc, int(x + w // 2), int(y + h // 2))
                ctypes.windll.user32.ReleaseDC(0, hdc)
                if pixel != -1:
                    pr = pixel & 0xFF
                    pg = (pixel >> 8) & 0xFF
                    pb = (pixel >> 16) & 0xFF
                    lum = 0.299 * pr + 0.587 * pg + 0.114 * pb
                    if lum <= 150:
                        fill_r, fill_g, fill_b = 205, 213, 226
            except Exception:
                pass

            # 4. VẼ HÌNH ẢNH TRONG SUỐT 32-BIT ARGB (HOÀN TOÀN KHÔNG CÓ VIỀN HỒNG)
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)

            cur_y = pad_y
            for idx, l in enumerate(lines):
                bb = draw.textbbox((0, 0), l, font=pil_font)
                lw = bb[2] - bb[0]
                lh = bb[3] - bb[1]
                lx = (w - lw) // 2
                draw.text((lx, cur_y), l, font=pil_font, fill=(fill_r, fill_g, fill_b, 255))
                cur_y += lh + 3

            # Chuyển đổi sang BGRA Premultiplied Alpha theo chuẩn Win32 UpdateLayeredWindow
            raw = bytearray(im.tobytes("raw", "BGRA"))
            for i in range(0, len(raw), 4):
                alpha = raw[i + 3]
                if alpha == 0:
                    raw[i] = 0
                    raw[i + 1] = 0
                    raw[i + 2] = 0
                elif alpha < 255:
                    inv = alpha / 255.0
                    raw[i] = int(raw[i] * inv)
                    raw[i + 1] = int(raw[i + 1] * inv)
                    raw[i + 2] = int(raw[i + 2] * inv)

            # 5. TẠO CỬA SỔ VÀ ÁP DỤNG UPDATE LAYERED WINDOW
            q_win = tk.Toplevel(self._root)
            q_win.overrideredirect(True)
            q_win.geometry(f"{w}x{h}+{x}+{y}")
            q_win.update_idletasks()

            top_q_hwnd = self._get_toplevel_hwnd(q_win)
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            q_style = user32.GetWindowLongW(top_q_hwnd, GWL_EXSTYLE)
            q_style = (q_style | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW) & ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(top_q_hwnd, GWL_EXSTYLE, q_style)

            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h  # Top-down DIB
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            ppv = ctypes.c_void_p()
            hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bmi), 0, ctypes.byref(ppv), 0, 0)
            ctypes.memmove(ppv, bytes(raw), w * h * 4)

            old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

            blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_ALPHA = 1
            pt_src = wintypes.POINT(0, 0)
            pt_dst = wintypes.POINT(x, y)
            size = wintypes.SIZE(w, h)

            user32.UpdateLayeredWindow(
                top_q_hwnd, hdc_screen, ctypes.byref(pt_dst), ctypes.byref(size),
                hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA
            )

            # Giải phóng GDI resources
            user32.ReleaseDC(0, hdc_screen)
            gdi32.SelectObject(hdc_mem, old_bmp)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)

            # Đảm bảo hiển thị TOPMOST trên cùng ngay lập tức
            user32.SetWindowPos(
                top_q_hwnd, HWND_TOPMOST, int(x), int(y), int(w), int(h),
                SWP_NOACTIVATE | SWP_SHOWWINDOW
            )
            user32.ShowWindow(top_q_hwnd, 5)  # SW_SHOW = 5

            self._badge_x = x
            self._badge_y = y
            self._badge_w = w
            self._badge_h = h
            self._q_badge_win = q_win
            self._q_hwnd = top_q_hwnd
            self._is_showing = True
        except Exception as e:
            pass
