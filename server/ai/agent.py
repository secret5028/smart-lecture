from __future__ import annotations

from config import RECOMMEND_COUNT
from server.ai.context_engine import ContextEngine
from server.ai.slide_composer import SlideComposer
from server.ai.wake_word import WakeWordDetector
from server.db.database import get_lecture_plan


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
        content = self.context.recent_text() or "강의 시작 대기 중"
        slide = {
            "title": plan.get("subject") or "추천 슬라이드",
            "bullets": [content[:40]],
            "image_id": None,
            "note": "실시간 맥락 기반 추천",
            "source_chunk_ids": [],
        }
        return [slide for _ in range(RECOMMEND_COUNT)]

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
