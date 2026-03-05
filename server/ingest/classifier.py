from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None

from config import GEMINI_MODEL


def _empty_result() -> dict:
    return {
        "category_large": "",
        "category_medium": "",
        "category_small": "",
        "keywords": [],
        "summary": "",
    }


def _build_prompt(subject: str, chunk_content: str) -> str:
    return f'''다음은 "{subject}" 과목의 강의 자료입니다.
아래 내용을 분석하여 JSON으로만 응답하세요 (마크다운 없이):
{{
  "category_large": "대분류명",
  "category_medium": "중분류명",
  "category_small": "소분류명",
  "keywords": ["키워드1", "키워드2"],
  "summary": "50자 이내 요약"
}}
내용: {chunk_content}'''


async def classify_chunk(chunk: dict, subject: str, gemini_api_key: str) -> dict:
    await asyncio.sleep(0.5)

    if not gemini_api_key or genai is None:
        return _empty_result()

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    content_type = chunk.get("content_type")
    payload: list = []

    if content_type == "image" and chunk.get("image_path"):
        image_bytes = Path(chunk["image_path"]).read_bytes()
        payload = [
            _build_prompt(subject, chunk.get("content", "")),
            {
                "mime_type": "image/png",
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            },
        ]
    else:
        payload = [_build_prompt(subject, chunk.get("content", ""))]

    for _ in range(3):
        try:
            resp = await asyncio.to_thread(model.generate_content, payload)
            text = (resp.text or "").strip()
            return json.loads(text)
        except Exception:
            await asyncio.sleep(0.5)

    return _empty_result()
