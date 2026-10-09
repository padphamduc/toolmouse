# -*- coding: utf-8 -*-
"""
Standalone Setup Window for Tool v3.2
Giao diện cài đặt trực quan, mượt mà:
- Tinh chỉnh Model AI Gemini, độ mờ đáp án, cỡ chữ, thời gian nhấp chuột.
- Hiển thị tình trạng đồng bộ API từ Google Sheets.
- Hỗ trợ lưu cấu hình cục bộ an toàn.
"""

import os
import sys
import json
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Dict, Any, Callable

from core.sheets_config import sheets_manager, mask_key
from core.ai_client import GEMINI_MODELS

# Palette giao diện hiện đại (Dark Theme)
BG = "#121318"
PANEL = "#1a1c23"
CARD = "#242731"
CARD_HOVER = "#2e3240"
TEXT = "#FFFFFF"
MUTED = "#8E92A4"
PURPLE = "#7B2CBF"
PINK = "#E0AAFF"
GREEN = "#00D26A"
YELLOW = "#FBBF24"
BLUE = "#3B82F6"


class SetupDialog:
    def __init__(self, current_config: Dict[str, Any], on_save_callback: Callable[[Dict[str, Any]], None]):
        self.config = dict(current_config)
        self.on_save = on_save_callback
        self.win = None

    def show(self):
        root = tk.Tk()
        self.win = root
        root.title("CÀI ĐẶT CẤU HÌNH - TOOL V3.2")
        root.configure(bg=BG)

        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        setup_w = min(680, screen_w - 60)
        setup_h = min(720, screen_h - 60)
        x = max(0, (screen_w - setup_w) // 2)
        y = max(0, (screen_h - setup_h) // 2)
        root.geometry(f"{setup_w}x{setup_h}+{x}+{y}")
        root.minsize(620, 600)

        try:
            ico_path = Path(__file__).resolve().parent.parent / "assets" / "duc_logo.ico"
            if ico_path.exists():
                root.iconbitmap(str(ico_path))
        except Exception:
            pass

        # Header
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=26, pady=(18, 10))

        tk.Label(
            header,
            text="⚙ THIẾT LẬP CẤU HÌNH • TOOL V3.2",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Semibold", 16)
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Điều khiển 100% bằng chuột • Hiển thị đáp án tại vị trí số câu (99 A / 99 A, C)",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(2, 0))

        # Main scrollable or padded body
        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 10))

        # --- SECTION 1: CẤU HÌNH API GOOGLE SHEETS & GEMINI ---
        sec1 = tk.LabelFrame(
            body,
            text="  1. NGUỒN CẤU HÌNH API GOOGLE SHEETS & GEMINI  ",
            bg=BG,
            fg=YELLOW,
            font=("Segoe UI Semibold", 9),
            bd=1,
            relief="groove"
        )
        sec1.pack(fill="x", pady=(0, 12), ipadx=10, ipady=8)

        # Status Google Sheets
        sheets_info = sheets_manager.get_status_info()
        source_desc = "Đồng bộ từ Google Sheets (Live)" if sheets_info.get("source") == "google_sheets" else (
            "Đang dùng Cache cục bộ" if sheets_info.get("source") == "cache" else "Chưa kết nối"
        )
        masked_k = sheets_info.get("gemini_masked") or "Chưa có"

        status_frame = tk.Frame(sec1, bg=CARD, padx=12, pady=8)
        status_frame.pack(fill="x", padx=12, pady=(4, 8))

        status_lbl = tk.Label(
            status_frame,
            text=f"🌐 Nguồn API: {source_desc} | Key: {masked_k}",
            bg=CARD,
            fg=GREEN if sheets_info.get("has_gemini") else YELLOW,
            font=("Segoe UI Semibold", 9)
        )
        status_lbl.pack(side="left")

        def refresh_sync():
            status_lbl.config(text="⏳ Đang tải từ Google Sheets...", fg=YELLOW)
            root.update_idletasks()

            def _sync_task():
                ok = sheets_manager.fetch_from_sheets_sync(timeout=5.0)
                info = sheets_manager.get_status_info()
                if ok:
                    msg = f"🌐 Nguồn API: Đồng bộ thành công (Live) | Key: {info.get('gemini_masked')}"
                    color = GREEN
                else:
                    msg = f"⚠️ Lỗi tải: {info.get('error', 'Không kết nối được')}"
                    color = YELLOW
                root.after(0, lambda: status_lbl.config(text=msg, fg=color))

            import threading
            threading.Thread(target=_sync_task, daemon=True).start()

        sync_btn = tk.Button(
            status_frame,
            text="🔄 Đồng bộ lại",
            bg=PANEL,
            fg=TEXT,
            activebackground=PURPLE,
            activeforeground=TEXT,
            bd=0,
            cursor="hand2",
            command=refresh_sync,
            font=("Segoe UI", 8)
        )
        sync_btn.pack(side="right", padx=4)

        # Model Selection
        model_frame = tk.Frame(sec1, bg=BG)
        model_frame.pack(fill="x", padx=12, pady=(4, 4))

        tk.Label(
            model_frame,
            text="Mô hình Gemini:",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 9),
            width=18,
            anchor="w"
        ).pack(side="left")

        cur_model = self.config.get("model", "gemini-3.5-flash-lite")
        if cur_model not in GEMINI_MODELS:
            cur_model = GEMINI_MODELS[0]

        model_var = tk.StringVar(value=cur_model)
        model_menu = tk.OptionMenu(model_frame, model_var, *GEMINI_MODELS)
        model_menu.config(
            bg=CARD,
            fg=TEXT,
            activebackground=CARD_HOVER,
            activeforeground=TEXT,
            highlightthickness=0,
            bd=0,
            font=("Segoe UI", 9)
        )
        model_menu["menu"].config(
            bg=CARD,
            fg=TEXT,
            activebackground=PURPLE,
            activeforeground="white"
        )
        model_menu.pack(side="left", fill="x", expand=True)

        # --- SECTION 2: THIẾT LẬP THAO TÁC CHUỘT ---
        sec2 = tk.LabelFrame(
            body,
            text="  2. THIẾT LẬP THAO TÁC CHUỘT & HIỆU ỨNG  ",
            bg=BG,
            fg=YELLOW,
            font=("Segoe UI Semibold", 9),
            bd=1,
            relief="groove"
        )
        sec2.pack(fill="x", pady=(0, 12), ipadx=10, ipady=8)

        # Double click interval
        row_dbl = tk.Frame(sec2, bg=BG)
        row_dbl.pack(fill="x", padx=12, pady=4)
        tk.Label(row_dbl, text="Khoảng cách nhấp đúp (s):", bg=BG, fg=TEXT, font=("Segoe UI", 9), width=24, anchor="w").pack(side="left")
        dbl_var = tk.StringVar(value=str(self.config.get("double_click_interval", 0.35)))
        tk.Entry(row_dbl, textvariable=dbl_var, bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 10), width=10).pack(side="left", ipady=3)
        tk.Label(row_dbl, text=" (Mặc định: 0.35 giây)", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=8)

        # Load cursor duration
        row_cur = tk.Frame(sec2, bg=BG)
        row_cur.pack(fill="x", padx=12, pady=4)
        tk.Label(row_cur, text="Thời gian xoay chuột (s):", bg=BG, fg=TEXT, font=("Segoe UI", 9), width=24, anchor="w").pack(side="left")
        cur_var = tk.StringVar(value=str(self.config.get("load_cursor_duration", 1.0)))
        tk.Entry(row_cur, textvariable=cur_var, bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 10), width=10).pack(side="left", ipady=3)
        tk.Label(row_cur, text=" (Mặc định: 1.0 giây)", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=8)

        # --- SECTION 3: ĐỘ MỜ & HIỂN THỊ ĐÁP ÁN ---
        sec3 = tk.LabelFrame(
            body,
            text="  3. ĐỘ MỜ & KÍCH THƯỚC CHỮ ĐÁP ÁN (GÓC DƯỚI BÊN PHẢI)  ",
            bg=BG,
            fg=YELLOW,
            font=("Segoe UI Semibold", 9),
            bd=1,
            relief="groove"
        )
        sec3.pack(fill="x", pady=(0, 12), ipadx=10, ipady=8)

        # Opacity slider (Số câu & đáp án trắc nghiệm)
        row_op = tk.Frame(sec3, bg=BG)
        row_op.pack(fill="x", padx=12, pady=4)
        tk.Label(row_op, text="Độ mờ đáp án trắc nghiệm:", bg=BG, fg=TEXT, font=("Segoe UI", 9), width=24, anchor="w").pack(side="left")

        op_var = tk.IntVar(value=int(self.config.get("number_opacity", 5)))
        op_lbl = tk.Label(row_op, text=f"{op_var.get()}%", bg=BG, fg=YELLOW, font=("Segoe UI Bold", 9), width=6, anchor="e")

        def on_op_change(val):
            try:
                op_lbl.config(text=f"{int(float(val))}%")
            except Exception:
                pass

        op_scale = tk.Scale(
            row_op,
            from_=1,
            to=100,
            orient="horizontal",
            variable=op_var,
            bg=BG,
            fg=TEXT,
            activebackground=PURPLE,
            troughcolor=CARD,
            highlightthickness=0,
            bd=0,
            showvalue=False,
            command=on_op_change
        )
        op_scale.pack(side="left", fill="x", expand=True, padx=(0, 10))
        op_lbl.pack(side="left")

        # Font size for essay answers
        row_font = tk.Frame(sec3, bg=BG)
        row_font.pack(fill="x", padx=12, pady=4)
        tk.Label(row_font, text="Cỡ chữ tự luận:", bg=BG, fg=TEXT, font=("Segoe UI", 9), width=24, anchor="w").pack(side="left")
        font_var = tk.StringVar(value=str(self.config.get("text_font_size", 11)))
        tk.Entry(row_font, textvariable=font_var, bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 10), width=10).pack(side="left", ipady=3)
        tk.Label(row_font, text=" (Mặc định: 11pt)", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=8)

        # Tips box
        tips_frame = tk.Frame(body, bg=CARD, padx=12, pady=8)
        tips_frame.pack(fill="x", pady=(4, 0))
        tk.Label(
            tips_frame,
            text="🖱 HƯỚNG DẪN THAO TÁC TOOL V3.2:\n"
                 "• Ctrl + Shift + M: Ẩn / Hiện cửa sổ tool\n"
                 "• Chuột Phải x2 : Chụp màn hình & gửi Gemini giải đề\n"
                 "• Chuột Trái x4 : Tự động gõ đáp án tự luận vào ô đang trỏ chuột\n"
                 "• Chuột Trái x2 : Hiện kết quả (Số câu kèm đáp án vd 99 A & tự luận)\n"
                 "• Chuột Trái x1 : Dừng ngay khi đang gõ; ngoài lúc gõ, nhấp ngoài vùng chữ để ẩn kết quả\n"
                 "• Phím ESC      : Thoát tool (khi cửa sổ đang mở)",
            bg=CARD,
            fg="#D1D5DB",
            justify="left",
            font=("Segoe UI", 8)
        ).pack(anchor="w")

        # Footer Actions
        footer = tk.Frame(root, bg=PANEL, height=60)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        def save_and_close():
            try:
                dbl = float(dbl_var.get().strip())
            except Exception:
                dbl = 0.35

            try:
                cur = float(cur_var.get().strip())
            except Exception:
                cur = 1.0

            try:
                fs = int(font_var.get().strip())
            except Exception:
                fs = 11

            op = op_var.get()
            selected_model = model_var.get()

            updated = {
                "model": selected_model,
                "model_name": selected_model,
                "double_click_interval": dbl,
                "load_cursor_duration": cur,
                "number_opacity": op,
                "text_opacity": op,
                "text_font_size": fs,
                "number_fg": self.config.get("number_fg", "#CCCCCC"),
            }

            self.on_save(updated)
            messagebox.showinfo("LƯU CẤU HÌNH", "✔ Đã lưu cấu hình Tool v3.2 thành công!", parent=root)
            root.destroy()

        def reset_defaults():
            dbl_var.set("0.35")
            cur_var.set("1.0")
            font_var.set("11")
            op_var.set(5)
            op_lbl.config(text="5%")
            model_var.set(GEMINI_MODELS[0])

        btn_save = tk.Button(
            footer,
            text="Lưu cấu hình",
            bg=PURPLE,
            fg=TEXT,
            activebackground=PINK,
            activeforeground="#000000",
            font=("Segoe UI Semibold", 10),
            bd=0,
            padx=18,
            pady=6,
            cursor="hand2",
            command=save_and_close
        )
        btn_save.pack(side="right", padx=(8, 26), pady=12)

        btn_reset = tk.Button(
            footer,
            text="Khôi phục mặc định",
            bg=CARD,
            fg=MUTED,
            activebackground=CARD_HOVER,
            activeforeground=TEXT,
            font=("Segoe UI", 9),
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=reset_defaults
        )
        btn_reset.pack(side="right", padx=8, pady=12)

        root.mainloop()


def open_setup_dialog(current_config: Dict[str, Any], on_save_callback: Callable[[Dict[str, Any]], None]):
    dlg = SetupDialog(current_config, on_save_callback)
    dlg.show()
