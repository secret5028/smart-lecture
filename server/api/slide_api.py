from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.ai.agent import get_agent
from server.api.websocket_api import manager
from server.db.database import fetch_all, get_lecture_plan
from server.lecture.lecture_state import get_state

router = APIRouter(prefix="/api/slide", tags=["slide"])

_current_slide: dict[str, Any] | None = None


class ShowSlidePayload(BaseModel):
    slide: dict[str, Any]


class ComposePayload(BaseModel):
    chunk_ids: list[str] = Field(default_factory=list)


@router.post("/show")
async def show_slide(payload: ShowSlidePayload) -> dict:
    global _current_slide
    plan = await get_lecture_plan() or {}
    state = get_state()
    _current_slide = {
        **payload.slide,
        "subject": payload.slide.get("subject") or plan.get("subject") or "과목 미설정",
        "current_section": payload.slide.get("current_section") or state.get("current_section_id") or "섹션 미설정",
        "progress_pct": payload.slide.get("progress_pct") if payload.slide.get("progress_pct") is not None else state.get("progress_pct", 0),
    }
    event = {"event": "slide_change", "payload": {"slide": _current_slide}}
    await manager.broadcast_to_room("display", event)
    await manager.broadcast_to_room("instructor", event)
    return {"message": "화면에 표시했습니다."}


@router.get("/recommendations")
async def get_recommendations() -> dict:
    agent = get_agent()
    slides = await agent.get_recommendations()
    return {"slides": slides}


@router.post("/compose")
async def compose_slide(payload: ComposePayload) -> dict:
    if not payload.chunk_ids:
        raise HTTPException(status_code=400, detail="청크 ID가 필요합니다.")

    placeholders: list[str] = ["?"] * len(payload.chunk_ids)
    sql = f"SELECT * FROM chunks WHERE id IN ({', '.join(placeholders)})"
    rows = await fetch_all(sql, tuple(payload.chunk_ids))
    if not rows:
        raise HTTPException(status_code=404, detail="청크를 찾지 못했습니다.")

    first = rows[0]
    slide = {
        "title": first.get("category_small") or "직접 구성 슬라이드",
        "bullets": [r.get("content", "")[:40] for r in rows[:4]],
        "image_id": next((r["id"] for r in rows if r.get("content_type") == "image"), None),
        "note": "선택한 청크 기반 구성",
        "source_chunk_ids": [r["id"] for r in rows],
    }
    return {"slide": slide}


@router.get("/current")
async def get_current() -> dict:
    return {"slide": _current_slide}
