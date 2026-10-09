# -*- coding: utf-8 -*-
"""
Lazy-loaded AI Client for Tool v3.2 (Gemini with Automatic Failover & Zero Startup Latency)
- Không nạp google.genai hay pydantic lúc mở app, chỉ nạp khi bấm chuột phải x2 giải bài.
- Tự động lấy khóa API từ SheetsConfigManager (Google Sheets / Cache cục bộ).
- Khả năng tự phục hồi: Tự động chuyển đổi giữa các model khi gặp 503 UNAVAILABLE hoặc 429 quá tải.
- Tắt cảnh báo Automatic Function Calling (AFC).
"""

import os
import sys
import json
import re
import time
import base64
import warnings
from io import BytesIO
from typing import Dict, Any, List, Optional
from PIL import Image

from core.sheets_config import sheets_manager, mask_key

warnings.filterwarnings("ignore", message=".*automatic function calling.*", category=UserWarning)

# Danh sách model Google Gemini hỗ trợ giải đề (sắp xếp theo tốc độ & ưu tiên dự phòng)
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]

QUIZ_PROMPT_V32 = """
Bạn là trợ lý giải đề thi từ ảnh chụp màn hình bài thi trực tiếp.
Nhiệm vụ của bạn:
1. Đọc đầy đủ toàn bộ câu hỏi, dữ kiện và yêu cầu trả lời xuất hiện trong ảnh chụp.
2. Trực tiếp giải bài và đưa ra câu trả lời chính xác nhất:
   - Nhận diện riêng từng câu hỏi thuộc một trong các loại: 'multiple_choice', 'short_answer', 'essay', 'unknown'.
   - ĐỐI VỚI CÂU TRẮC NGHIỆM ('multiple_choice'):
     + BẮT BUỘC XÁC ĐỊNH RÕ số thứ tự câu hỏi vào 'question_number' (ví dụ: '99', '100', '1', '22').
     + BẮT BUỘC XÁC ĐỊNH RÕ ký hiệu chữ cái đáp án đã chọn vào danh sách 'answers' (ví dụ: ['A'], hoặc ['A', 'C'] nếu câu có nhiều đáp án đúng).
     + Tuyệt đối KHÔNG bỏ trống số câu và ký hiệu đáp án đối với câu trắc nghiệm.
   - ĐỐI VỚI CÂU ĐIỀN NGẮN ('short_answer'):
     + BẮT BUỘC giải bài và ghi trực tiếp nội dung cần điền vào 'answer_text' (ngắn gọn, đúng định dạng và đơn vị).
   - ĐỐI VỚI CÂU TỰ LUẬN ('essay'):
     + BẮT BUỘC giải bài và ghi nội dung trả lời hoàn chỉnh, chính xác, mạch lạc và đủ ý vào 'answer_text'.
3. Quy tắc nghiêm ngặt:
   - Tuyệt đối không đoán mò khi ảnh mờ, thiếu dữ kiện (đặt needs_more_info = true và status_message báo rõ).
   - Không mở đầu bằng lời xã giao, không lặp lại đề bài.

Trả về DUY NHẤT định dạng JSON tuân thủ schema:
{
  "questions": [
    {
      "question_number": "99",
      "question_type": "multiple_choice",
      "answers": ["A"],
      "boxes_2d": [],
      "answer_text": ""
    }
  ],
  "needs_more_info": false,
  "status_message": ""
}
Tuyệt đối chỉ trả về JSON hợp lệ, không dùng markdown codeblocks.
"""


def parse_quiz_result_v32(json_text: str) -> Dict[str, Any]:
    """
    Phân tích JSON phản hồi từ Gemini cho Tool v3.2:
    - Trích xuất số câu và ký hiệu đáp án trắc nghiệm.
    - Định dạng hiển thị '99 A' hoặc '99 A, C' hoặc nhiều câu.
    - Báo lỗi rõ ràng nếu thiếu số câu hoặc thiếu ký hiệu đáp án (không tự đoán).
    """
    clean_text = str(json_text).strip()
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\s*```$", "", clean_text)
    m = re.search(r"(\{.*\})", clean_text, flags=re.DOTALL)
    if m:
        clean_text = m.group(1).strip()

    data = None
    try:
        data = json.loads(clean_text)
    except Exception:
        try:
            data = json.loads(clean_text, strict=False)
        except Exception:
            try:
                sanitized = re.sub(r'(?<!\\)\n', r'\\n', clean_text)
                data = json.loads(sanitized, strict=False)
            except Exception:
                pass

    if not isinstance(data, dict):
        return {
            "questions": [],
            "mc_badge_text": "",
            "mc_items": [],
            "written_items": [],
            "needs_more_info": False,
            "status_message": "Không thể phân tích cú pháp JSON phản hồi từ Gemini.",
        }

    raw_questions = data.get("questions", [])
    if not isinstance(raw_questions, list):
        raw_questions = []

    # Tương thích ngược nếu Gemini trả dạng phẳng
    if not raw_questions:
        q_num = str(data.get("question_number", "")).strip()
        q_type = str(data.get("question_type", "multiple_choice")).strip().lower()
        ans = data.get("answers", [])
        if not ans and "answer" in data:
            ans = [data["answer"]]
        ans_txt = str(data.get("answer_text", "")).strip()
        raw_questions.append({
            "question_number": q_num,
            "question_type": q_type,
            "answers": ans,
            "boxes_2d": [],
            "answer_text": ans_txt,
        })

    mc_items = []
    written_items = []
    placeholder_patterns = {
        "câu tự luận", "tự luận", "essay", "short_answer",
        "short answer", "điền vào ô", "câu hỏi điền", "câu hỏi viết",
        "(không có nội dung)", "không có nội dung", "none", "n/a", "null"
    }

    for item in raw_questions:
        if not isinstance(item, dict):
            continue

        q_num = str(item.get("question_number", "")).strip()
        q_num_clean = re.sub(r"^(?:Câu|Question|No\.?)\s*", "", q_num, flags=re.IGNORECASE).strip()

        q_type = str(item.get("question_type", "")).strip().lower()
        raw_ans = item.get("answers", []) or []
        cleaned_answers = [str(a).strip().upper() for a in raw_ans if str(a).strip()]

        item_text = str(
            item.get("answer_text") or
            item.get("answer") or
            item.get("solution") or
            item.get("text") or
            item.get("content") or
            ""
        ).strip()
        if item_text.lower() in placeholder_patterns:
            item_text = ""

        is_written_type = ("short" in q_type) or ("essay" in q_type) or ("điền" in q_type) or ("tự luận" in q_type)
        is_mc = (q_type == "multiple_choice") or (bool(cleaned_answers) and not is_written_type)

        if is_mc:
            err_reasons = []
            if not q_num_clean:
                err_reasons.append("Thiếu số câu")
            if not cleaned_answers:
                err_reasons.append("Thiếu ký hiệu đáp án")

            if err_reasons:
                if not q_num_clean and not cleaned_answers:
                    display_str = "[Lỗi: Thiếu số câu & đáp án]"
                elif not q_num_clean:
                    display_str = f"[Lỗi: Thiếu số câu] {', '.join(cleaned_answers)}"
                else:
                    display_str = f"{q_num_clean} [Lỗi: Thiếu đáp án]"
            else:
                ans_str = " ".join(cleaned_answers)
                display_str = f"{q_num_clean} {ans_str}".strip()

            mc_items.append({
                "question_number": q_num_clean,
                "answers": cleaned_answers,
                "display": display_str,
                "errors": err_reasons,
            })

        if is_written_type or (not is_mc and bool(item_text)):
            if item_text:
                written_items.append({
                    "question_number": q_num_clean or q_num,
                    "question_type": "short_answer" if ("short" in q_type or "điền" in q_type) else ("essay" if ("essay" in q_type or "tự luận" in q_type) else q_type),
                    "answer_text": item_text,
                    "answers": cleaned_answers,
                })

    mc_badge_text = "\n".join(it["display"] for it in mc_items).strip()
    needs_info = bool(data.get("needs_more_info", False))
    status_msg = str(data.get("status_message", "")).strip()

    return {
        "questions": raw_questions,
        "mc_badge_text": mc_badge_text,
        "mc_items": mc_items,
        "written_items": written_items,
        "needs_more_info": needs_info,
        "status_message": status_msg,
    }


def call_gemini_solve_quiz(
    screenshot: Image.Image,
    preferred_model: str = "gemini-3.5-flash-lite",
    custom_api_key: str = "",
) -> Dict[str, Any]:
    """
    Hàm thực thi giải đề thi với Gemini:
    - Lazy import google.genai và pydantic (giúp khởi động app < 0.2s)
    - Tự động lấy khóa API từ Google Sheets hoặc cache
    - Thử lại và tự động chuyển model dự phòng nếu gặp 503 UNAVAILABLE
    """
    # 1. Kiểm tra khóa API
    api_key = custom_api_key.strip() or sheets_manager.get_api_key("gemini").strip()
    if not api_key:
        # Chờ tối đa 1.5s xem tiến trình nền Google Sheets đã tải xong chưa
        sheets_manager.wait_until_ready(timeout=1.5)
        api_key = sheets_manager.get_api_key("gemini").strip()

    if not api_key:
        raise RuntimeError("⏳ Chưa có khóa API Gemini. Đang chờ đồng bộ từ Google Sheets hoặc bấm F2 để nhập trực tiếp.")

    # 2. Lazy Import thư viện nặng
    from google import genai
    from pydantic import BaseModel, Field
    from typing import Literal

    # Khởi tạo schema Pydantic
    class QuestionItem(BaseModel):
        question_number: str = Field(..., description="Số thứ tự câu hỏi (ví dụ '99', '1', 'Câu 5').")
        question_type: Literal["multiple_choice", "short_answer", "essay", "unknown"] = Field(...)
        answers: list[str] = Field(default_factory=list, description="Ký hiệu đáp án trắc nghiệm ['A'] hoặc ['A', 'C'].")
        boxes_2d: list[list[int]] = Field(default_factory=list)
        answer_text: str = Field(default="", description="Nội dung tự luận hoặc đáp án điền ngắn.")

    class QuizResultSchema(BaseModel):
        questions: list[QuestionItem] = Field(..., description="Danh sách các câu hỏi nhận diện và giải được.")
        needs_more_info: bool = Field(default=False)
        status_message: str = Field(default="")

    # Chuẩn bị dữ liệu hình ảnh
    buf = BytesIO()
    screenshot.save(buf, format="JPEG", quality=85)
    image_bytes = buf.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    client = genai.Client(api_key=api_key)

    # Xây dựng danh sách model ưu tiên
    model_pool = []
    if preferred_model in GEMINI_MODELS:
        model_pool.append(preferred_model)
    for m in GEMINI_MODELS:
        if m not in model_pool:
            model_pool.append(m)

    last_error = None
    raw_output_text = ""
    used_model = preferred_model

    quiz_schema = {
        "type": "text",
        "mime_type": "application/json",
        "schema": QuizResultSchema.model_json_schema()
    }

    # 3. Vòng lặp giải quyết & chuyển model khi 503
    for target_model in model_pool:
        used_model = target_model
        for attempt in range(2):
            try:
                # Tầng 1: Client interactions
                try:
                    interaction = client.interactions.create(
                        model=target_model,
                        input=[
                            {"type": "image", "data": image_b64},
                            {"type": "text", "text": QUIZ_PROMPT_V32}
                        ],
                        response_format=quiz_schema
                    )
                    raw_output_text = interaction.output_text
                    return {
                        "parsed": parse_quiz_result_v32(raw_output_text),
                        "used_model": target_model,
                        "raw_text": raw_output_text,
                    }
                except Exception as inter_err:
                    err_str = str(inter_err).lower()
                    if any(k in err_str for k in ["503", "unavailable", "high demand"]):
                        raise inter_err

                    # Tầng 2: models.generate_content
                    contents = [
                        genai.types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        QUIZ_PROMPT_V32
                    ]
                    try:
                        afc_cfg = genai.types.AutomaticFunctionCallingConfig(disable=True)
                    except Exception:
                        afc_cfg = None

                    gen_config = genai.types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=QuizResultSchema,
                        automatic_function_calling=afc_cfg,
                        temperature=0.1
                    )
                    resp = client.models.generate_content(
                        model=target_model,
                        contents=contents,
                        config=gen_config
                    )
                    raw_output_text = resp.text
                    return {
                        "parsed": parse_quiz_result_v32(raw_output_text),
                        "used_model": target_model,
                        "raw_text": raw_output_text,
                    }

            except Exception as call_err:
                last_error = call_err
                err_msg = str(call_err).lower()
                is_transient = any(k in err_msg for k in [
                    "503", "unavailable", "high demand", "overloaded",
                    "429", "resource_exhausted", "quota"
                ])

                if is_transient:
                    if attempt == 0:
                        time.sleep(0.8)
                        continue
                    else:
                        print(f"\n⚠️ Model '{target_model}' đang quá tải (503 / High Demand). Đang chuyển sang model tiếp theo...")
                        break
                else:
                    if "404" in err_msg or "not found" in err_msg:
                        break
                    raise RuntimeError(f"Lỗi Gemini API: {call_err}")

    raise RuntimeError(f"Toàn bộ máy chủ Google Gemini đang quá tải (503 UNAVAILABLE). Chi tiết: {last_error}")
