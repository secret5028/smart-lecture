from __future__ import annotations

import json
from datetime import datetime

from server.db.database import execute, fetch_one

_state: dict = {
    "session_id": None,
    "started_at": None,
    "ended_at": None,
    "current_section_id": None,
    "progress_pct": 0,
}


def get_state() -> dict:
    return dict(_state)


async def _persist_state() -> None:
    session_id = _state.get("session_id")
    if not session_id:
        return

    shown = {"progress_pct": _state.get("progress_pct", 0), "slide_ids": []}
    await execute(
        """
        UPDATE lecture_sessions
        SET started_at = ?, ended_at = ?, current_section_id = ?, shown_slide_ids = ?
        WHERE id = ?
        """,
        (
            _state.get("started_at"),
            _state.get("ended_at"),
            _state.get("current_section_id"),
            json.dumps(shown, ensure_ascii=False),
            session_id,
        ),
    )


async def hydrate_state() -> dict:
    row = await fetch_one(
        "SELECT * FROM lecture_sessions ORDER BY started_at DESC, id DESC LIMIT 1"
    )
    if not row:
        return get_state()

    shown = json.loads(row.get("shown_slide_ids") or "{}")
    _state["session_id"] = row.get("id")
    _state["started_at"] = row.get("started_at")
    _state["ended_at"] = row.get("ended_at")
    _state["current_section_id"] = row.get("current_section_id")
    _state["progress_pct"] = int(shown.get("progress_pct") or 0)
    return get_state()


async def start_session(session_id: str) -> dict:
    now = datetime.utcnow().isoformat()
    _state["session_id"] = session_id
    _state["started_at"] = now
    _state["ended_at"] = None
    _state["current_section_id"] = None
    _state["progress_pct"] = 0

    await execute(
        """
        INSERT INTO lecture_sessions (
            id, plan_id, started_at, ended_at, current_section_id, shown_slide_ids, transcript
        ) VALUES (?, NULL, ?, NULL, NULL, ?, ?)
        """,
        (session_id, now, json.dumps({"progress_pct": 0, "slide_ids": []}, ensure_ascii=False), ""),
    )
    return get_state()


async def end_session() -> dict:
    _state["ended_at"] = datetime.utcnow().isoformat()
    await _persist_state()
    return get_state()


async def update_section(section_id: str, progress_pct: int | None = None) -> dict:
    _state["current_section_id"] = section_id
    if progress_pct is not None:
        _state["progress_pct"] = max(0, min(progress_pct, 100))
    await _persist_state()
    return get_state()
