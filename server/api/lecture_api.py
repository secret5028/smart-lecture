from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import DEFAULT_WAKE_WORD
from server.ai.agent import get_agent
from server.db import database
from server.lecture import lecture_state

router = APIRouter(tags=["lecture"])


class LecturePlanPayload(BaseModel):
    subject: str
    target_audience: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    total_sessions: int | None = None
    minutes_per_session: int | None = None
    toc: list[dict[str, Any]] = Field(default_factory=list)


class SectionPayload(BaseModel):
    section_id: str
    progress_pct: int | None = None


class SettingsPayload(BaseModel):
    wake_word: str = DEFAULT_WAKE_WORD
    gemini_api_key: str = ""
    whisper_model: str = "small"
    upload_dir: str = ""


@router.get("/api/lecture/plan")
async def get_plan() -> dict:
    plan = await database.get_lecture_plan()
    return plan or {}


@router.post("/api/lecture/plan")
async def save_plan(payload: LecturePlanPayload) -> dict:
    plan_id = await database.save_lecture_plan(payload.model_dump())
    return {"message": "저장되었습니다.", "id": plan_id}


@router.get("/api/lecture/state")
async def get_state() -> dict:
    return lecture_state.get_state()


@router.post("/api/lecture/state/section")
async def set_section(payload: SectionPayload) -> dict:
    return lecture_state.update_section(payload.section_id, payload.progress_pct)


@router.post("/api/lecture/session/start")
async def start_session() -> dict:
    session_id = str(uuid.uuid4())
    state = lecture_state.start_session(session_id)
    return {"message": "강의를 시작했습니다.", "state": state}


@router.post("/api/lecture/session/end")
async def end_session() -> dict:
    state = lecture_state.end_session()
    return {"message": "강의를 종료했습니다.", "state": state}


@router.get("/api/settings")
async def get_settings() -> dict:
    data = await database.get_settings()
    data.setdefault("wake_word", DEFAULT_WAKE_WORD)
    data.setdefault("gemini_api_key", "")
    data.setdefault("whisper_model", "small")
    data.setdefault("upload_dir", "")
    return data


@router.post("/api/settings")
async def save_settings(payload: SettingsPayload) -> dict:
    data = payload.model_dump()
    upload_dir = (data.get("upload_dir") or "").strip()
    if upload_dir:
        try:
            Path(upload_dir).expanduser().mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"자료 폴더 경로가 올바르지 않습니다: {exc}") from exc

    for key, value in data.items():
        await database.upsert_setting(key, str(value))

    agent = get_agent()
    agent.detector.update_wake_word(data["wake_word"])
    return {"message": "저장되었습니다."}
