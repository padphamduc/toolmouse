# -*- coding: utf-8 -*-
"""
Overlay Rendering Engine for Tool v3.2
- KHÔNG vẽ dấu chấm đỏ
- Hiển thị số câu kèm ký hiệu đáp án (ví dụ '99 A', '99 A, C') trực tiếp ở vị trí số câu
- Hiển thị văn bản tự luận / câu trả lời ngắn ở góc dưới bên phải màn hình
- Tối ưu trong suốt và click-through (WS_EX_TRANSPARENT, WS_EX_LAYERED)
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


class ResultOverlayV32:
    def __init__(self, get_config_func):
        self.get_config = get_config_func
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="OverlayGUIThread")
        self._ready = threading.Event()
        self._root = None
        self._q_badge_win = None
        self._text_win = None
        self._text_region_rect = None
        self.last_show_time = 0.0
        self._thread.start()
        self._ready.wait(timeout=3)

    def _run_loop(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._ready.set()
        self._root.mainloop()

    def is_visible(self) -> bool:
        return getattr(self, "_is_showing", False) and bool(self._q_badge_win or self._text_win)

    def is_point_in_text_region(self, x: int, y: int) -> bool:
        """Kiểm tra con trỏ chuột có đang nằm bên trong vùng chữ đáp án hay không."""
        if not self._text_win or not self._text_region_rect:
            return False
        x1, y1, x2, y2 = self._text_region_rect
        return (x1 <= x <= x2) and (y1 <= y <= y2)

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
        """Ẩn kết quả ngay lập tức (0ms) ở cấp độ Windows Window Handle, sau đó hủy widget."""
        self._is_showing = False
        user32 = ctypes.windll.user32
        if getattr(self, "_q_hwnd", None):
            try:
                user32.ShowWindow(self._q_hwnd, 0)  # SW_HIDE
            except Exception:
                pass
        if getattr(self, "_t_hwnd", None):
            try:
                user32.ShowWindow(self._t_hwnd, 0)  # SW_HIDE
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

        if self._text_win:
            try:
                self._text_win.destroy()
            except Exception:
                pass
            self._text_win = None
        self._t_hwnd = None

        if self._text_win:
            try:
                self._text_win.destroy()
            except Exception:
                pass
            self._text_win = None

        self._text_region_rect = None

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

        has_text_content = bool(written_items or status_message or is_waiting)
        text_y_top = work_b - 40

        # ----------------------------------------------------------------------
        # 1. ĐÁP ÁN TỰ LUẬN / ĐIỀN NGẮN: LỚP CHỮ NỔI KHÔNG VIỀN Ở GÓC DƯỚI PHẢI
        # ----------------------------------------------------------------------
        if has_text_content:
            try:
                lines = []
                if is_waiting:
                    lines.append("⏳ Đang phân tích bài thi...")
                elif written_items:
                    if len(written_items) == 1:
                        it = written_items[0]
                        q_num_item = str(it.get("question_number", "")).strip()
                        ans_content = str(it.get("answer_text", "")).strip()
                        if not ans_content and it.get("answers"):
                            ans_content = ", ".join(str(a) for a in it.get("answers"))
                        if ans_content:
                            if q_num_item:
                                lines.append(f"Câu {q_num_item}: {ans_content}")
                            else:
                                lines.append(ans_content)
                    else:
                        for idx, it in enumerate(written_items):
                            q_num_item = str(it.get("question_number", "")).strip() or str(idx + 1)
                            ans_content = str(it.get("answer_text", "")).strip()
                            if not ans_content and it.get("answers"):
                                ans_content = ", ".join(str(a) for a in it.get("answers"))
                            if ans_content:
                                lines.append(f"Câu {q_num_item}: {ans_content}")

                if status_message and not is_waiting:
                    lines.append(f"[{status_message}]")

                full_text = "\n".join(lines).strip()

                if full_text:
                    font_size = int(cfg.get("text_font_size", 11))
                    font_size = max(8, min(40, font_size))
                    text_fg = str(cfg.get("text_fg", "#111111"))
                    text_op_val = int(cfg.get("text_opacity", cfg.get("number_opacity", 5)))
                    text_op_val = max(1, min(100, text_op_val))
                    alpha_ratio = float(text_op_val) / 100.0

                    wrap_w = min(560, max(280, work_r - 60))

                    t_win = tk.Toplevel(self._root)
                    t_win.overrideredirect(True)
                    t_win.attributes("-topmost", True)
                    t_win.lift()

                    bg_chroma = "#FF00FE"
                    t_win.configure(bg=bg_chroma)
                    t_win.attributes("-transparentcolor", bg_chroma)
                    t_win.attributes("-alpha", alpha_ratio)

                    canvas = tk.Canvas(t_win, bg=bg_chroma, highlightthickness=0)
                    canvas.pack(fill="both", expand=True)

                    t_item = canvas.create_text(
                        6, 6,
                        text=full_text,
                        font=("Segoe UI", font_size, "bold"),
                        fill=text_fg,
                        anchor="nw",
                        width=wrap_w
                    )

                    t_win.update_idletasks()
                    bbox = canvas.bbox(t_item)
                    if bbox:
                        content_w = (bbox[2] - bbox[0]) + 14
                        content_h = (bbox[3] - bbox[1]) + 14
                    else:
                        content_w = 340
                        content_h = 100

                    margin_r = 20
                    margin_b = 20
                    tx = max(10, work_r - content_w - margin_r)
                    ty = max(10, work_b - content_h - margin_b)
                    text_y_top = ty

                    t_win.geometry(f"{content_w}x{content_h}+{tx}+{ty}")
                    t_win.update_idletasks()

                    top_t_hwnd = self._get_toplevel_hwnd(t_win)
                    user32 = ctypes.windll.user32
                    t_style = user32.GetWindowLongW(top_t_hwnd, GWL_EXSTYLE)
                    t_style |= (WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW)
                    user32.SetWindowLongW(top_t_hwnd, GWL_EXSTYLE, t_style)
                    alpha_byte = max(1, min(255, int(round(255 * alpha_ratio))))
                    user32.SetLayeredWindowAttributes(top_t_hwnd, 0x00FE00FF, alpha_byte, 1 | 2)

                    self._text_win = t_win
                    self._t_hwnd = top_t_hwnd
                    self._text_region_rect = (tx, ty, tx + content_w, ty + content_h)
                    self._is_showing = True

            except Exception as e:
                pass

        # ----------------------------------------------------------------------
        # 2. HIỂN THỊ SỐ CÂU KÈM ĐÁP ÁN TRẮC NGHIỆM TẠI PHẦN GIỜ (TOOL V3.2)
        # Nằm ở góc dưới bên phải, ngay phần hiển thị giờ hệ thống của Taskbar / SEB
        # Màu chữ xám (#A0A0A0) đồng bộ với màu chữ của phần giờ hệ thống
        # KHÔNG vẽ dấu chấm đỏ.
        # ----------------------------------------------------------------------
        badge_text = str(mc_badge_text).strip()
        num_opacity = int(cfg.get("number_opacity", 5))
        number_color = str(cfg.get("number_fg", "#CDD5E2")).strip() or "#CDD5E2"
        font_family = str(cfg.get("number_font_family", "Times New Roman")).strip() or "Times New Roman"

        if badge_text:
            try:
                lines = [line.strip() for line in badge_text.split("\n") if line.strip()]
                line_count = len(lines)
                max_line_len = max(len(l) for l in lines) if lines else 4

                # Dáng chữ thon gọn thanh thoát chuẩn văn bản Word (Times New Roman)
                font_size = 11 if line_count <= 2 else 10
                pad_x = 6
                pad_y = 2
                w = max(42, max_line_len * 8 + pad_x * 2)
                h = max(22, line_count * (font_size + 4) + pad_y * 2)

                # Căn dọc ngay giữa dải Taskbar / phần giờ dưới cùng bên phải
                tb_h = max(36, screen_h - work_b) if screen_h > work_b else 40
                clock_right_margin = 75  # Nằm ngay sát bên trái phần giờ hệ thống

                if screen_h > work_b:
                    y = work_b + (tb_h - h) // 2
                else:
                    y = screen_h - h - 6

                x = max(10, screen_w - w - clock_right_margin)

                q_win = tk.Toplevel(self._root)
                q_win.overrideredirect(True)
                q_win.attributes("-topmost", True)
                q_win.lift()

                # Độ mờ 5% tinh tế
                alpha_ratio = max(0.01, min(1.0, float(num_opacity) / 100.0))
                q_win.attributes("-alpha", alpha_ratio)

                bg_key = "#FF00FF"
                q_win.configure(bg=bg_key)
                q_win.attributes("-transparentcolor", bg_key)

                q_canvas = tk.Canvas(q_win, width=w, height=h, bg=bg_key, highlightthickness=0)
                q_canvas.pack(fill="both", expand=True)

                # Chữ thon gọn chuẩn kiểu Word (Times New Roman), màu xám bạc tiệp màu đồng hồ hệ thống
                text_item = q_canvas.create_text(
                    w // 2, h // 2,
                    text=badge_text,
                    fill=number_color,
                    font=(font_family, font_size),
                    justify="center"
                )

                q_win.update_idletasks()
                bbox = q_canvas.bbox(text_item)
                if bbox:
                    meas_w = (bbox[2] - bbox[0]) + 12
                    meas_h = (bbox[3] - bbox[1]) + 6
                    if meas_w > w or meas_h > h:
                        w = max(w, meas_w)
                        h = max(h, meas_h)
                        if screen_h > work_b:
                            y = work_b + (tb_h - h) // 2
                        else:
                            y = screen_h - h - 6
                        x = max(10, screen_w - w - clock_right_margin)

                q_win.geometry(f"{w}x{h}+{x}+{y}")
                q_win.update_idletasks()

                top_q_hwnd = self._get_toplevel_hwnd(q_win)
                user32 = ctypes.windll.user32
                q_style = user32.GetWindowLongW(top_q_hwnd, GWL_EXSTYLE)
                q_style |= (WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW)
                user32.SetWindowLongW(top_q_hwnd, GWL_EXSTYLE, q_style)
                alpha_byte = max(1, min(255, int(round(255 * alpha_ratio))))
                user32.SetLayeredWindowAttributes(top_q_hwnd, 0x00FF00FF, alpha_byte, 1 | 2)

                self._q_badge_win = q_win
                self._q_hwnd = top_q_hwnd
                self._is_showing = True
            except Exception:
                pass
