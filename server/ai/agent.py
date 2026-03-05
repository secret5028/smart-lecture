from __future__ import annotations

import asyncio

from config import RECOMMEND_COUNT, TOP_K_RETRIEVAL
from server.ai.context_engine import ContextEngine
from server.ai.knowledge_retriever import KnowledgeRetriever
from server.ai.slide_composer import SlideComposer
from server.ai.wake_word import WakeWordDetector
from server.db.database import get_lecture_plan, get_settings
from server.lecture.lecture_state import get_state


class LectureAgent:
    def __init__(self, wake_word: str) -> None:
        self.detector = WakeWordDetector(wake_word)
        self.context = ContextEngine()
        self.composer = SlideComposer()

    async def process_transcript(self, text: str) -> list[dict]:
        events: list[dict] = [
            {"event": "transcript_update", "payload": {"text": text, "is_final": True}}
        ]

        detection = self.detector.detect(text)
        if detection is None:
            self.context.update(text)
            events.append(
                {
                    "event": "recommendations_update",
                    "payload": {"slides": await self.get_recommendations()},
                }
            )
            return events

        events.append(
            {
                "event": "agent_message",
                "payload": {
                    "message": f"명령 감지: {detection['command']}",
                    "type": "info",
                },
            }
        )
        return events

    async def get_recommendations(self) -> list[dict]:
        plan = await get_lecture_plan() or {}
        settings = await get_settings()
        raw_query = self.context.recent_text(count=5)
        query = self._build_query_keywords(raw_query)
        if not query:
            seed = " ".join((plan.get("learning_objectives") or [])[:2]) or (plan.get("subject") or "강의 시작")
            query = self._build_query_keywords(seed) or seed

        objectives = plan.get("learning_objectives") or []
        toc = plan.get("toc") or []
        subject = plan.get("subject") or "추천 슬라이드"
        target_audience = plan.get("target_audience") or ""
        state = get_state()

        section_titles = [x.get("title") for x in toc if isinstance(x, dict) and x.get("title")]
        if not section_titles:
            section_titles = ["섹션 미설정"]

        current_section = state.get("current_section_id") or section_titles[0]
        progress_pct = int(state.get("progress_pct") or 0)
        current_idx = section_titles.index(current_section) if current_section in section_titles else 0
        next_section = section_titles[min(current_idx + 1, len(section_titles) - 1)]
        prev_section = section_titles[max(current_idx - 1, 0)]
        goal = objectives[min(current_idx, len(objectives) - 1)] if objectives else "학습 목표 미설정"

        if progress_pct < 35:
            stage = "초반"
        elif progress_pct < 75:
            stage = "중반"
        else:
            stage = "후반"

        retriever = KnowledgeRetriever()
        chunks = await retriever.search_async(query, top_k=TOP_K_RETRIEVAL * 2)
        if not chunks and current_section:
            chunks = await retriever.search_by_category(current_section, top_k=TOP_K_RETRIEVAL * 2)

        image_chunks = await retriever.search_async(subject, top_k=3, filter_type="image")
        if not image_chunks:
            image_chunks = await retriever.search_async("", top_k=1, filter_type="image")

        contexts = [
            {
                "subject": subject,
                "target_audience": target_audience,
                "current_section": current_section,
                "transcript_recent": query,
                "stage": stage,
                "focus": "핵심개념 도입",
            },
            {
                "subject": subject,
                "target_audience": target_audience,
                "current_section": current_section,
                "transcript_recent": query,
                "stage": stage,
                "focus": "오개념 교정",
            },
            {
                "subject": subject,
                "target_audience": target_audience,
                "current_section": next_section,
                "transcript_recent": query,
                "stage": stage,
                "focus": f"다음 흐름 연결 ({prev_section} -> {next_section})",
            },
        ]

        gemini_api_key = settings.get("gemini_api_key", "")
        base_slides: list[dict] = []

        # 강의 초반에는 1) 과목 타이틀 2) 목차 슬라이드를 우선 배치한다.
        if progress_pct <= 10:
            top_image_id = image_chunks[0].get("id") if image_chunks else None
            top_image_sources = [c.get("id") for c in image_chunks[:3] if c.get("id")]
            first_goal = objectives[0] if objectives else "학습 목표 미설정"
            base_slides.append(
                {
                    "title": subject,
                    "bullets": [f"강의 대상: {target_audience or '미설정'}", f"핵심 목표: {first_goal[:42]}", "지금부터 수업을 시작합니다."],
                    "image_id": top_image_id,
                    "note": "수업 오프닝 슬라이드",
                    "source_chunk_ids": top_image_sources,
                    "subject": subject,
                    "current_section": current_section,
                    "progress_pct": progress_pct,
                }
            )

            toc_bullets = [f"{idx + 1}. {name}" for idx, name in enumerate(section_titles[:4])]
            if not toc_bullets:
                toc_bullets = ["저장된 목차가 없습니다."]
            base_slides.append(
                {
                    "title": "오늘의 목차",
                    "bullets": toc_bullets,
                    "image_id": None,
                    "note": "수업 흐름 안내 슬라이드",
                    "source_chunk_ids": [],
                    "subject": subject,
                    "current_section": current_section,
                    "progress_pct": progress_pct,
                }
            )

        dynamic_needed = max(RECOMMEND_COUNT - len(base_slides), 0)
        dynamic_contexts = contexts[:dynamic_needed] if dynamic_needed else []

        if dynamic_contexts and chunks and gemini_api_key:
            per_slide_chunks: list[list[dict]] = []
            for idx in range(dynamic_needed):
                start = idx
                end = idx + TOP_K_RETRIEVAL
                subset = chunks[start:end]
                if not subset:
                    subset = chunks[:TOP_K_RETRIEVAL]
                per_slide_chunks.append(subset)

            tasks = [
                asyncio.to_thread(self.composer.compose, per_slide_chunks[i], dynamic_contexts[i], gemini_api_key)
                for i in range(dynamic_needed)
            ]
            composed = await asyncio.gather(*tasks, return_exceptions=True)

            slides: list[dict] = list(base_slides)
            for idx, item in enumerate(composed):
                if isinstance(item, Exception) or not isinstance(item, dict):
                    item = self._fallback_slide(chunks, dynamic_contexts[idx], goal, progress_pct)
                item.setdefault("image_id", None)
                item.setdefault("source_chunk_ids", [c.get("id") for c in chunks[:TOP_K_RETRIEVAL] if c.get("id")])
                item["subject"] = subject
                item["current_section"] = dynamic_contexts[idx]["current_section"]
                item["progress_pct"] = progress_pct
                slides.append(item)
            return slides[:RECOMMEND_COUNT]

        fallback_dynamic = [self._fallback_slide(chunks, ctx, goal, progress_pct) for ctx in dynamic_contexts]
        return (base_slides + fallback_dynamic)[:RECOMMEND_COUNT]

    def _build_query_keywords(self, text: str) -> str:
        tokens = [t.strip(".,!?()[]{}\"'") for t in (text or "").split()]
        tokens = [t for t in tokens if len(t) >= 2]
        seen: set[str] = set()
        uniq: list[str] = []
        for t in tokens:
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
        uniq.sort(key=len, reverse=True)
        return " ".join(uniq[:5])

    def _fallback_slide(self, chunks: list[dict], context: dict, goal: str, progress_pct: int = 0) -> dict:
        top = chunks[:3]
        bullets = [f"핵심 목표: {goal[:36]}"]
        for c in top:
            text = (c.get("summary") or c.get("content") or "").strip()
            if text:
                bullets.append(text[:48])
        if len(bullets) < 2:
            bullets.append("관련 청크가 부족하여 기본 요약을 표시합니다.")
        return {
            "title": f"{context.get('stage', '진행')} | {context.get('focus', '핵심 정리')}",
            "bullets": bullets[:4],
            "image_id": next((c.get("id") for c in top if c.get("content_type") == "image"), None),
            "note": "Gemini 미사용 기본 추천",
            "source_chunk_ids": [c.get("id") for c in top if c.get("id")],
            "subject": context.get("subject", "과목 미설정"),
            "current_section": context.get("current_section", "섹션 미설정"),
            "progress_pct": progress_pct,
        }

    def make_quiz(self, context: str) -> dict:
        return {
            "type": "ox",
            "question": f"다음 진술이 맞을까요? {context[:40]}",
            "answer": "O",
        }


_agent: LectureAgent | None = None


def init_agent(wake_word: str) -> LectureAgent:
    global _agent
    if _agent is None:
        _agent = LectureAgent(wake_word)
    return _agent


def get_agent() -> LectureAgent:
    global _agent
    if _agent is None:
        _agent = LectureAgent("코덱스야")
    return _agent
