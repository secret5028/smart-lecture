from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.ai.agent import get_agent
from server.ai.stt_engine import get_stt_engine

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[str, list[WebSocket] | dict[str, WebSocket]] = {
            "instructor": [],
            "display": [],
            "students": {},
        }

    async def connect(self, ws: WebSocket, room: str, client_id: str | None = None) -> str | None:
        await ws.accept()
        if room == "students":
            sid = client_id or str(uuid.uuid4())
            students = self.rooms["students"]
            assert isinstance(students, dict)
            students[sid] = ws
            return sid
        room_list = self.rooms[room]
        assert isinstance(room_list, list)
        room_list.append(ws)
        return None

    async def disconnect(self, ws: WebSocket, room: str, client_id: str | None = None) -> None:
        if room == "students":
            students = self.rooms["students"]
            assert isinstance(students, dict)
            if client_id and client_id in students:
                students.pop(client_id, None)
            return

        room_list = self.rooms[room]
        assert isinstance(room_list, list)
        if ws in room_list:
            room_list.remove(ws)

    async def _send_safe(self, ws: WebSocket, message: dict) -> bool:
        try:
            await ws.send_json(message)
            return True
        except Exception:
            return False

    async def broadcast_to_room(self, room: str, message: dict) -> None:
        if room == "students":
            students = self.rooms["students"]
            assert isinstance(students, dict)
            stale: list[str] = []
            for sid, ws in students.items():
                ok = await self._send_safe(ws, message)
                if not ok:
                    stale.append(sid)
            for sid in stale:
                students.pop(sid, None)
            return

        room_list = self.rooms[room]
        assert isinstance(room_list, list)
        stale: list[WebSocket] = []
        for ws in room_list:
            ok = await self._send_safe(ws, message)
            if not ok:
                stale.append(ws)
        for ws in stale:
            if ws in room_list:
                room_list.remove(ws)

    async def broadcast_to_all(self, message: dict) -> None:
        await self.broadcast_to_room("instructor", message)
        await self.broadcast_to_room("display", message)
        await self.broadcast_to_room("students", message)


manager = ConnectionManager()


async def broadcast_event(event: str, payload: dict) -> None:
    await manager.broadcast_to_all({"event": event, "payload": payload})


async def convert_webm_to_pcm(audio_bytes: bytes) -> bytes:
    src_path: Path | None = None
    dst_path: Path | None = None
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as src, tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False
    ) as dst:
        src.write(audio_bytes)
        src.flush()
        src_path = Path(src.name)
        dst_path = Path(dst.name)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src.name,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            dst.name,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0:
            pcm = b""
        else:
            with open(dst.name, "rb") as f:
                pcm = f.read()

    if src_path:
        src_path.unlink(missing_ok=True)
    if dst_path:
        dst_path.unlink(missing_ok=True)
    return pcm


@router.websocket("/ws/instructor")
async def instructor_ws(ws: WebSocket) -> None:
    await manager.connect(ws, "instructor")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws, "instructor")


@router.websocket("/ws/display")
async def display_ws(ws: WebSocket) -> None:
    await manager.connect(ws, "display")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws, "display")


@router.websocket("/ws/student")
async def student_ws(ws: WebSocket) -> None:
    sid = await manager.connect(ws, "students")
    try:
        await ws.send_json({"event": "student_connected", "payload": {"student_id": sid}})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws, "students", sid)


@router.websocket("/ws/audio")
async def audio_ws(ws: WebSocket) -> None:
    await ws.accept()
    stt_engine = get_stt_engine()
    agent = get_agent()

    try:
        while True:
            audio_bytes = await ws.receive_bytes()
            pcm = await convert_webm_to_pcm(audio_bytes)
            if not pcm:
                continue
            text = await asyncio.to_thread(stt_engine.transcribe_chunk, pcm)
            events = await agent.process_transcript(text)
            for event in events:
                await manager.broadcast_to_all(event)
    except WebSocketDisconnect:
        return
