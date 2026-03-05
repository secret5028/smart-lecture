from __future__ import annotations

import json
import re

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None

from config import GEMINI_MODEL


class SlideComposer:
    def compose_sequence(
        self,
        chunks: list[dict],
        context: dict,
        gemini_api_key: str,
    ) -> list[dict]:
        """강사 발화 흐름에 맞는 슬라이드 3장을 순서대로 생성한다."""

        # Gemini 없을 때 fallback
        if not gemini_api_key or genai is None:
            return self._fallback_sequence(chunks, context)

        if not chunks:
            return self._fallback_sequence([], context)

        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)

        chunks_content = "\n\n".join(
            [f"[{c.get('id','?')}] {c.get('content','')}" for c in chunks[:8]]
        )

        toc_remaining = context.get("toc_remaining", [])
        toc_str = " → ".join(toc_remaining[:4]) if toc_remaining else "없음"

        prompt = f"""당신은 강의 보조 AI입니다. 강사가 지금 말한 내용을 듣고, 강사가 바로 다음에 사용할 슬라이드 3장을 순서대로 만들어야 합니다.

## 강의 맥락
- 과목: {context.get("subject", "")}
- 수강 대상: {context.get("target_audience", "")}
- 현재 섹션: {context.get("current_section", "")}
- 전체 진행률: {context.get("progress_pct", 0)}%
- 현재 학습 목표: {context.get("goal", "")}
- 남은 목차 순서: {toc_str}

## 강사가 방금 한 말 (최근 발화)
{context.get("transcript_recent", "")}

## 참고 자료 (강의 PDF에서 추출된 청크)
{chunks_content}

## 지시
위 발화와 참고 자료를 바탕으로 슬라이드 3장을 만들어라.
- 1장: 강사가 방금 말한 내용을 청중이 이해하기 쉽게 정리
- 2장: 이 개념의 핵심 심화 또는 구체적 예시/적용
- 3장: 다음 섹션({toc_remaining[0] if toc_remaining else "마무리"})으로 자연스럽게 연결하는 브릿지

## 출력 형식
JSON 배열만 출력하라. 마크다운, 설명, 코드블록 없이 순수 JSON만.

[
  {{
    "title": "제목 (15자 이내)",
    "bullets": ["핵심 포인트 1 (25자 이내)", "핵심 포인트 2", "핵심 포인트 3"],
    "note": "강사 참고 노트 (30자 이내)",
    "image_id": null,
    "source_chunk_ids": ["참조한 청크 id"]
  }},
  {{ ...2장... }},
  {{ ...3장... }}
]

슬라이드 원칙: 청중은 슬라이드를 읽는 게 아니라 본다. 글자 최소화, 키워드만, 문장 금지."""

        try:
            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            # Gemini가 마크다운 fence로 감쌀 때 제거
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw.strip())
            slides = json.loads(raw)
            if not isinstance(slides, list):
                raise ValueError("list 아님")
            return slides[:3]
        except Exception:
            return self._fallback_sequence(chunks, context)

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

    def _fallback_sequence(self, chunks: list[dict], context: dict) -> list[dict]:
        """Gemini 실패 시 청크 기반으로 3장 생성"""
        current = context.get("current_section", "섹션 미설정")
        toc_remaining = context.get("toc_remaining", [])
        next_sec = toc_remaining[0] if toc_remaining else "다음 섹션"
        transcript = context.get("transcript_recent", "")
        goal = context.get("goal", "")

        def chunk_bullets(offset: int) -> list[str]:
            items = chunks[offset:offset + 3]
            result = []
            for c in items:
                text = (c.get("summary") or c.get("content") or "").strip()
                if text:
                    result.append(text[:45])
            return result or ["관련 자료를 불러오는 중입니다."]

        return [
            {
                "title": f"{current} 핵심 정리",
                "bullets": chunk_bullets(0) or [transcript[:45]],
                "note": "현재 발화 기반 정리",
                "image_id": None,
                "source_chunk_ids": [c["id"] for c in chunks[:3] if c.get("id")],
            },
            {
                "title": f"{current} 심화",
                "bullets": chunk_bullets(2) or [f"목표: {goal[:40]}"],
                "note": "핵심 개념 심화",
                "image_id": None,
                "source_chunk_ids": [c["id"] for c in chunks[2:5] if c.get("id")],
            },
            {
                "title": f"→ {next_sec}",
                "bullets": [f"다음: {next_sec}", f"지금까지: {current}", "전환 준비"],
                "note": "섹션 브릿지",
                "image_id": None,
                "source_chunk_ids": [],
            },
        ]

    def compose_detail(self, chunk: dict) -> dict:
        return {
            "title": "원문 보기",
            "bullets": [chunk.get("content", "")],
            "image_id": chunk.get("id") if chunk.get("content_type") == "image" else None,
            "note": "원문 그대로 표시",
            "source_chunk_ids": [chunk.get("id")],
        }
