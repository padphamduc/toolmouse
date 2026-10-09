# -*- coding: utf-8 -*-
"""
Screen Capture Engine - Chuyên dụng cho Windows & Safe Exam Browser (SEB).
Tự động kết nối InputDesktop đang hiển thị của SEB trong luồng worker độc lập (tránh ERROR_BUSY 170).
Hỗ trợ đa tầng fallback:
- Tier 1: InputDesktop + BitBlt (SRCCOPY | CAPTUREBLT)
- Tier 2: InputDesktop + BitBlt (SRCCOPY thuần, vượt qua bộ lọc WDA_EXCLUDEFROMCAPTURE của DWM)
- Tier 3: Direct Window Capture (Target SEB / Foreground HWND via PrintWindow)
- Tier 4: Display Device Context (CreateDCW 'DISPLAY')
- Tier 5: Pillow ImageGrab
"""

import ctypes
from ctypes import wintypes
import threading
from typing import Optional, Tuple, List
from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# Win32 Constants
DESKTOP_READOBJECTS = 0x0001
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_SWITCHDESKTOP = 0x0100
GENERIC_ALL = 0x10000000

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
PW_RENDERFULLCONTENT = 2

# Thiết lập DPI Awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

user32.OpenInputDesktop.restype = ctypes.c_void_p
user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

user32.SetThreadDesktop.restype = wintypes.BOOL
user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]

user32.CloseDesktop.restype = wintypes.BOOL
user32.CloseDesktop.argtypes = [ctypes.c_void_p]

user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]

user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]

gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

gdi32.BitBlt.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.DWORD
]

gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT
]

gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]

gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]

user32.PrintWindow.restype = wintypes.BOOL
user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]

gdi32.CreateDCW.restype = ctypes.c_void_p
gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', ctypes.c_long),
        ('biHeight', ctypes.c_long),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', ctypes.c_long),
        ('biYPelsPerMeter', ctypes.c_long),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]


def is_blank_image(im: Optional[Image.Image]) -> bool:
    """Kiểm tra ảnh chụp có bị hỏng / đơn sắc (trắng, đen, xám) hay không."""
    if im is None:
        return True
    try:
        w, h = im.size
        if w < 10 or h < 10:
            return True
        colors = im.getcolors(maxcolors=16)
        if colors is not None and len(colors) <= 2:
            return True
        return False
    except Exception:
        return False


def _capture_dc_to_image(hdc_src: int, rx: int, ry: int, rw: int, rh: int, flags: int) -> Optional[Image.Image]:
    """Chụp một vùng từ HDC sang PIL Image bằng BitBlt + GetDIBits chuẩn 64-bit."""
    try:
        hMemDC = gdi32.CreateCompatibleDC(hdc_src)
        if not hMemDC:
            return None
        hBitmap = gdi32.CreateCompatibleBitmap(hdc_src, rw, rh)
        if not hBitmap:
            gdi32.DeleteDC(hMemDC)
            return None
        old_bmp = gdi32.SelectObject(hMemDC, hBitmap)

        ok = gdi32.BitBlt(hMemDC, 0, 0, rw, rh, hdc_src, rx, ry, flags)
        img = None
        if ok:
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = rw
            bmi.biHeight = -rh  # Top-down bitmap
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf_size = rw * rh * 4
            buf = ctypes.create_string_buffer(buf_size)
            lines = gdi32.GetDIBits(hMemDC, hBitmap, 0, rh, buf, ctypes.byref(bmi), 0)
            if lines > 0:
                img = Image.frombuffer('RGBA', (rw, rh), buf, 'raw', 'BGRA', 0, 1).convert('RGB')

        gdi32.SelectObject(hMemDC, old_bmp)
        gdi32.DeleteObject(hBitmap)
        gdi32.DeleteDC(hMemDC)
        return img
    except Exception:
        return None


def _capture_hwnd_to_image(hwnd: int, flag: int = 2) -> Optional[Image.Image]:
    """Chụp một cửa sổ cụ thể bằng PrintWindow."""
    try:
        if not user32.IsWindow(hwnd):
            return None
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        rw = max(1, rect.right - rect.left)
        rh = max(1, rect.bottom - rect.top)

        hScreenDC = user32.GetDC(0)
        hMemDC = gdi32.CreateCompatibleDC(hScreenDC)
        hBitmap = gdi32.CreateCompatibleBitmap(hScreenDC, rw, rh)
        old_bmp = gdi32.SelectObject(hMemDC, hBitmap)

        ok = user32.PrintWindow(hwnd, hMemDC, flag)
        img = None
        if ok:
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = rw
            bmi.biHeight = -rh
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf_size = rw * rh * 4
            buf = ctypes.create_string_buffer(buf_size)
            lines = gdi32.GetDIBits(hMemDC, hBitmap, 0, rh, buf, ctypes.byref(bmi), 0)
            if lines > 0:
                img = Image.frombuffer('RGBA', (rw, rh), buf, 'raw', 'BGRA', 0, 1).convert('RGB')

        gdi32.SelectObject(hMemDC, old_bmp)
        gdi32.DeleteObject(hBitmap)
        gdi32.DeleteDC(hMemDC)
        user32.ReleaseDC(0, hScreenDC)
        return img
    except Exception:
        return None


def _find_seb_windows(h_desktop: Optional[int] = None) -> List[int]:
    """Tìm HWND các cửa sổ thuộc SafeExamBrowser hoặc trình duyệt đang mở."""
    windows = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            cls_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_name, 256)
            cls_str = cls_name.value.lower()
            if any(k in cls_str for k in ['chrome', 'intermediate d3d', 'cef', 'seb', 'hwndwrapper']):
                windows.append(hwnd)
        return True

    cb = WNDENUMPROC(_enum_cb)
    if h_desktop:
        try:
            user32.EnumDesktopWindows(h_desktop, cb, 0)
        except Exception:
            pass
    if not windows:
        try:
            user32.EnumWindows(cb, 0)
        except Exception:
            pass
    return windows


def capture_screen(region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
    """
    Chụp ảnh màn hình tối ưu hỗ trợ Windows thông thường lẫn Safe Exam Browser (SEB):
    - Chạy hoàn toàn trên một Worker Thread riêng biệt để tránh ERROR_BUSY (170).
    - Vượt qua màn hình trắng/xám đơn sắc do DWM Exclusion.
    - Đa tầng fallback: BitBlt CAPTUREBLT -> BitBlt Direct -> PrintWindow -> Display DC -> ImageGrab.
    """
    result = {'img': None, 'tier': 'None'}

    def _isolated_capture_worker():
        h_input_desktop = None
        for access_mask in [0x01FF, GENERIC_ALL, DESKTOP_READOBJECTS | DESKTOP_WRITEOBJECTS | DESKTOP_SWITCHDESKTOP]:
            try:
                h_input_desktop = user32.OpenInputDesktop(0, False, access_mask)
                if h_input_desktop:
                    user32.SetThreadDesktop(h_input_desktop)
                    break
            except Exception:
                pass

        try:
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)

            if region:
                rx, ry, rw, rh = region
                rx = max(0, min(screen_w - 1, int(rx)))
                ry = max(0, min(screen_h - 1, int(ry)))
                rw = max(1, min(screen_w - rx, int(rw)))
                rh = max(1, min(screen_h - ry, int(rh)))
            else:
                rx, ry, rw, rh = 0, 0, screen_w, screen_h

            # TẦNG 1: Desktop DC + BitBlt CAPTUREBLT
            hScreenDC = user32.GetDC(0)
            if hScreenDC:
                img1 = _capture_dc_to_image(hScreenDC, rx, ry, rw, rh, SRCCOPY | CAPTUREBLT)
                if img1 is not None and not is_blank_image(img1):
                    result['img'] = img1
                    result['tier'] = 'Tier 1 (Desktop CAPTUREBLT)'
                    user32.ReleaseDC(0, hScreenDC)
                    return

                # TẦNG 2: Desktop DC + BitBlt DIRECT (không CAPTUREBLT)
                img2 = _capture_dc_to_image(hScreenDC, rx, ry, rw, rh, SRCCOPY)
                if img2 is not None and not is_blank_image(img2):
                    result['img'] = img2
                    result['tier'] = 'Tier 2 (Desktop GDI Direct)'
                    user32.ReleaseDC(0, hScreenDC)
                    return

                user32.ReleaseDC(0, hScreenDC)

            # TẦNG 3: Target Window Direct Capture (SEB / Foreground HWND)
            target_hwnds = []
            fg_wnd = user32.GetForegroundWindow()
            if fg_wnd:
                target_hwnds.append(fg_wnd)
            target_hwnds.extend(_find_seb_windows(h_input_desktop))

            for hwnd in target_hwnds:
                img3 = _capture_hwnd_to_image(hwnd, PW_RENDERFULLCONTENT)
                if img3 is not None and not is_blank_image(img3):
                    result['img'] = img3
                    result['tier'] = f'Tier 3 (PrintWindow FullContent HWND:{hwnd})'
                    return

                img3_std = _capture_hwnd_to_image(hwnd, 0)
                if img3_std is not None and not is_blank_image(img3_std):
                    result['img'] = img3_std
                    result['tier'] = f'Tier 3 (PrintWindow Standard HWND:{hwnd})'
                    return

            # TẦNG 4: Display Device Context (CreateDCW 'DISPLAY')
            try:
                h_disp = gdi32.CreateDCW("DISPLAY", None, None, None)
                if h_disp:
                    img4 = _capture_dc_to_image(h_disp, rx, ry, rw, rh, SRCCOPY)
                    gdi32.DeleteDC(h_disp)
                    if img4 is not None and not is_blank_image(img4):
                        result['img'] = img4
                        result['tier'] = 'Tier 4 (Display Device Context)'
                        return
            except Exception:
                pass

        finally:
            if h_input_desktop:
                try:
                    user32.CloseDesktop(h_input_desktop)
                except Exception:
                    pass

    worker_thread = threading.Thread(target=_isolated_capture_worker, daemon=True)
    worker_thread.start()
    worker_thread.join(timeout=3.5)

    captured_image = result.get('img')
    if captured_image is not None and not is_blank_image(captured_image):
        return captured_image

    # TẦNG 5: Fallback PIL ImageGrab
    try:
        from PIL import ImageGrab
        if region:
            rx, ry, rw, rh = region
            bbox = (rx, ry, rx + rw, ry + rh)
            img5 = ImageGrab.grab(bbox=bbox)
        else:
            img5 = ImageGrab.grab()
        if img5 is not None and not is_blank_image(img5):
            return img5
    except Exception:
        pass

    w = max(100, user32.GetSystemMetrics(0))
    h = max(100, user32.GetSystemMetrics(1))
    return Image.new('RGB', (w, h), color=(128, 128, 128))
