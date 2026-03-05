from __future__ import annotations

from datetime import datetime

_state: dict = {
    "session_id": None,
    "started_at": None,
    "ended_at": None,
    "current_section_id": None,
    "progress_pct": 0,
}


def get_state() -> dict:
    return dict(_state)


def start_session(session_id: str) -> dict:
    _state["session_id"] = session_id
    _state["started_at"] = datetime.utcnow().isoformat()
    _state["ended_at"] = None
    _state["progress_pct"] = 0
    return get_state()


def end_session() -> dict:
    _state["ended_at"] = datetime.utcnow().isoformat()
    return get_state()


def update_section(section_id: str, progress_pct: int | None = None) -> dict:
    _state["current_section_id"] = section_id
    if progress_pct is not None:
        _state["progress_pct"] = max(0, min(progress_pct, 100))
    return get_state()
