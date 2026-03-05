from __future__ import annotations

from config import RECOMMEND_COUNT
from server.ai.context_engine import ContextEngine
from server.ai.slide_composer import SlideComposer
from server.ai.wake_word import WakeWordDetector
from server.db.database import get_lecture_plan
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
        content = self.context.recent_text() or "강의 시작 대기 중"
        objectives = plan.get("learning_objectives") or []
        toc = plan.get("toc") or []
        subject = plan.get("subject") or "추천 슬라이드"
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
            templates = [
                {
                    "title": f"[초반] {current_section} 도입",
                    "bullets": [f"핵심 질문으로 시작: {goal[:30]}", f"현재 맥락 연결: {content[:32]}", "오늘 흐름을 먼저 안내"],
                    "section": current_section,
                    "progress": progress_pct,
                },
                {
                    "title": f"[초반] 선수개념 점검",
                    "bullets": [f"이전 내용 복기: {prev_section}", "용어/개념 빠르게 정리", "학습자 이해도 확인 질문 1개"],
                    "section": current_section,
                    "progress": progress_pct,
                },
                {
                    "title": f"[초반] 다음 섹션 예고",
                    "bullets": [f"곧 다룰 주제: {next_section}", "왜 필요한지 먼저 설명", "전환 질문으로 집중 유도"],
                    "section": next_section,
                    "progress": min(progress_pct + 10, 100),
                },
            ]
        elif progress_pct < 75:
            stage = "중반"
            templates = [
                {
                    "title": f"[중반] {current_section} 핵심 정리",
                    "bullets": [f"핵심 목표 재확인: {goal[:30]}", "개념 3줄 요약 + 예시 1개", f"현재 발화 반영: {content[:28]}"],
                    "section": current_section,
                    "progress": progress_pct,
                },
                {
                    "title": "[중반] 오개념 교정",
                    "bullets": ["자주 틀리는 포인트 2개", "틀린 이유와 정답 기준 비교", "짧은 확인 질문 제시"],
                    "section": current_section,
                    "progress": progress_pct,
                },
                {
                    "title": f"[중반] {next_section} 연결",
                    "bullets": [f"다음 흐름으로 브릿지: {next_section}", "현재 내용과 연결선 제시", "전환 문장 1개로 마무리"],
                    "section": next_section,
                    "progress": min(progress_pct + 15, 100),
                },
            ]
        else:
            stage = "후반"
            templates = [
                {
                    "title": f"[후반] {current_section} 마무리",
                    "bullets": ["핵심 3포인트 재정리", f"목표 달성 점검: {goal[:30]}", "현장 질문 1개 받기"],
                    "section": current_section,
                    "progress": progress_pct,
                },
                {
                    "title": "[후반] 전체 요약",
                    "bullets": [f"이전~현재 흐름: {prev_section} → {current_section}", "오늘 배운 것 3줄 요약", "실무/시험 적용 포인트"],
                    "section": current_section,
                    "progress": progress_pct,
                },
                {
                    "title": f"[후반] 다음 차시 예고",
                    "bullets": [f"다음 차시 핵심: {next_section}", "사전 읽기/복습 과제 안내", "종료 전 체크 질문"],
                    "section": next_section,
                    "progress": min(progress_pct + 5, 100),
                },
            ]

        slides: list[dict] = []
        for idx, t in enumerate(templates[:RECOMMEND_COUNT], start=1):
            slides.append(
                {
                    "title": t["title"],
                    "bullets": t["bullets"],
                    "image_id": None,
                    "note": f"{stage} 단계 추천 {idx}",
                    "source_chunk_ids": [],
                    "subject": subject,
                    "current_section": t["section"],
                    "progress_pct": t["progress"],
                }
            )
        return slides

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
