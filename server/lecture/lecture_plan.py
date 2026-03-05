from __future__ import annotations

from server.db.database import get_lecture_plan, save_lecture_plan


async def save_plan(payload: dict) -> int:
    return await save_lecture_plan(payload)


async def load_plan() -> dict | None:
    return await get_lecture_plan()
