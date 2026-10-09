# 🖱 ToolMouse – Bản Độc Lập Chuyên Biệt Cho SEB (Tool v3.2)

> **Tác giả:** ĐỨC DẠY BẠN HỌC NHÉ <3  
> **Phiên bản:** v3.2.0 (Standalone Optimized)  
> **Repository:** [https://github.com/padphamduc/toolmouse](https://github.com/padphamduc/toolmouse)  
> **Cấu hình Google Sheets:** [Google Spreadsheet API Config](https://docs.google.com/spreadsheets/d/1WHLQmLBRxgAurR0eR27Faey5iK3Ps_vD4dCnJ6wNl3o/edit?usp=sharing)

---

## ⚡ 1. Điểm Nổi Bật & Tối Ưu Hóa

- **Chuyên biệt 100% cho Tool v3.2:** Khởi động mở thẳng vào Tool v3.2, loại bỏ hoàn toàn menu chọn cồng kềnh.
- **Khởi động siêu tốc (Sub-second < 0.25s):** 
  - Cơ chế **Lazy Import** hoãn nạp `google.genai`, `pydantic` cho đến khi thực sự giải đề.
  - Giao diện console và Win32 Mouse Hook (`WH_MOUSE_LL`) sẵn sàng ngay lập tức.
- **Đồng bộ API Google Sheets ngầm (Non-blocking):**
  - Tự động lấy khóa API từ Google Sheets ở luồng nền.
  - Bộ nhớ đệm cục bộ bảo mật bằng **Windows DPAPI** (`C:\duc\configs\toolmouse_cache.json`).
  - Hoạt động mượt mà ngay cả khi mất mạng hoặc không kết nối được Google Sheets.
- **Ẩn đáp án siêu nhạy (0ms Delay):**
  - Nhấp chuột trái 1 lần lập tức ẩn cửa sổ ở cấp độ hệ điều hành (`ShowWindow SW_HIDE`), không độ trễ, không chờ đợi.
- **Hiển thị đáp án ngay tại vị trí số câu:**
  - Dạng hiển thị: `99 A` hoặc `99 A, C` (nhiều đáp án).
  - Không vẽ dấu chấm đỏ. Dùng chung độ mờ đen nhạt (2%) và vị trí số câu.
- **Tự động gõ phím tự luận thông minh (Unicode Win32):**
  - Bắn phím trực tiếp bằng `SendInput` / Win32 Unicode.
  - Tuyệt đối **KHÔNG dùng Clipboard / Ctrl+V**, chống triệt để mọi cơ chế giám sát Clipboard của SEB.

---

## 🎮 2. Bảng Thao Tác Chuột & Phím Tắt

| Thao tác | Chức năng | Chi tiết |
| :--- | :--- | :--- |
| **Chuột Phải x2** | 📸 Chụp màn hình & Giải đề | Tự động chụp toàn màn hình bằng GDI BitBlt đa tầng (vượt bộ lọc WDA DWM của SEB) và gửi AI phân tích. |
| **Chuột Trái x2** | 👁 Hiện kết quả | Hiển thị số câu kèm đáp án (`99 A` / `99 A, C`) và nội dung tự luận ở góc dưới bên phải. |
| **Chuột Trái x1** | ⏹ **Ẩn ngay lập tức / Dừng gõ** | **Nếu đang gõ:** dừng gõ khẩn cấp ngay tức thì.<br>**Nếu đang hiện kết quả:** ẩn biến mất ngay lập tức (0ms). |
| **Chuột Trái x4** | ⌨ Tự động gõ đáp án | Gõ trực tiếp chữ tự luận vào ô đang đặt con trỏ chuột. |
| **Phím F2** | ⚙ Mở bảng Cài đặt (Setup) | Tùy chỉnh Model AI, độ mờ đáp án, thời gian nhấp chuột, kiểm tra kết nối API. |
| **Phím ESC** | 🚪 Thoát ứng dụng | Tắt tool và dọn dẹp tài nguyên. |

---

## 🛠 3. Cài Đặt & Chạy Trực Tiếp

### Yêu cầu:
- Windows 10 / 11 (64-bit).
- Python 3.10 trở lên.

```bash
# Clone repository
git clone https://github.com/padphamduc/toolmouse.git
cd toolmouse

# Cài đặt thư viện tối thiểu
pip install -r requirements.txt

# Khởi chạy tool
python main.py

# Mở trực tiếp màn hình cài đặt cấu hình
python main.py --setup
```

---

## 📦 4. Đóng Gói File EXE Độc Lập (PyInstaller)

Để biên dịch thành file `ToolMouse.exe` chạy độc lập không cần cài đặt Python:

```bash
pyinstaller toolmouse.spec
```

File thực thi sẽ nằm tại: `dist/ToolMouse.exe`.

---

## 🔒 5. Bảo Mật & An Toàn Tuyệt Đối

1. **Khóa API an toàn:** Toàn bộ khóa API nạp từ Google Sheets được mã hóa lưu trữ bằng Windows DPAPI gắn liền với tài khoản người dùng hiện tại, không lưu plain text, không in ra terminal.
2. **Không commit thông tin nhạy cảm:** File `.gitignore` chuẩn loại trừ toàn bộ file credentials, binary, cache, log.
3. **Chống treo luồng:** Các tác vụ mạng (Google Sheets CSV, GitHub Releases Update Check) chạy trên daemon thread riêng, không bao giờ làm khựng thao tác chuột của người dùng trong phòng thi.
