from __future__ import annotations

import json

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None

from config import GEMINI_MODEL


class SlideComposer:
    def compose(self, chunks: list[dict], context: dict, gemini_api_key: str) -> dict:
        if not chunks:
            return {
                "title": "추천 자료 없음",
                "bullets": ["관련 자료를 찾지 못했습니다."],
                "image_id": None,
                "note": "",
                "source_chunk_ids": [],
            }

        if not gemini_api_key or genai is None:
            first = chunks[0]
            return {
                "title": first.get("category_small") or "핵심 정리",
                "bullets": [first.get("content", "")[:40]],
                "image_id": first.get("id") if first.get("content_type") == "image" else None,
                "note": "Gemini API 키 미설정",
                "source_chunk_ids": [c.get("id") for c in chunks[:3] if c.get("id")],
            }

        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)

        chunks_content = "\n\n".join([f"[{c.get('id')}] {c.get('content','')}" for c in chunks[:5]])
        prompt = f'''당신은 강의 슬라이드 전문 디자이너입니다.
과목: {context.get("subject", "")}
대상: {context.get("target_audience", "")}
현재 섹션: {context.get("current_section", "")}
강사 최근 발화: {context.get("transcript_recent", "")}

아래 자료를 바탕으로 강의 슬라이드 1장을 JSON으로만 구성하세요 (마크다운 없이):
{{
  "title": "슬라이드 제목 (15자 이내)",
  "bullets": ["핵심 포인트 1 (20자 이내)", "핵심 포인트 2"],
  "image_id": "관련 이미지 청크 id 또는 null",
  "note": "강사 참고 노트 (50자 이내)",
  "source_chunk_ids": ["chunk_id1"]
}}
슬라이드 원칙: 글씨 최소화, 핵심만, 학습자 수준에 맞게

자료:
{chunks_content}'''
        try:
            resp = model.generate_content(prompt)
            return json.loads((resp.text or "").strip())
        except Exception:
            return {
                "title": "슬라이드 생성 실패",
                "bullets": ["네트워크 상태 또는 API 설정을 확인해주세요."],
                "image_id": None,
                "note": "",
                "source_chunk_ids": [c.get("id") for c in chunks[:3] if c.get("id")],
            }

    def compose_detail(self, chunk: dict) -> dict:
        return {
            "title": "원문 보기",
            "bullets": [chunk.get("content", "")],
            "image_id": chunk.get("id") if chunk.get("content_type") == "image" else None,
            "note": "원문 그대로 표시",
            "source_chunk_ids": [chunk.get("id")],
        }
