from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from config import UPLOAD_DIR
from server.db import database
from server.ingest.pipeline import run_pipeline

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

_progress_subscribers: set[asyncio.Queue] = set()
_last_progress: dict = {"step": "idle", "progress": 0, "message": "대기 중"}


async def publish_progress(data: dict) -> None:
    global _last_progress
    _last_progress = data
    stale: list[asyncio.Queue] = []
    for q in _progress_subscribers:
        try:
            q.put_nowait(data)
        except Exception:
            stale.append(q)
    for q in stale:
        _progress_subscribers.discard(q)


async def get_upload_dir() -> Path:
    settings = await database.get_settings()
    custom = (settings.get("upload_dir") or "").strip()
    upload_dir = Path(custom).expanduser() if custom else UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    upload_dir = await get_upload_dir()
    save_path = upload_dir / file.filename
    async with aiofiles.open(save_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)

    return {"message": "업로드 완료", "filename": file.filename}


async def _run_file_pipeline(pdf_path: Path, subject: str, gemini_api_key: str) -> None:
    try:
        await run_pipeline(pdf_path, subject, gemini_api_key, progress_cb=publish_progress)
    except Exception as exc:
        await publish_progress({"step": "error", "progress": 100, "message": f"오류: {exc}"})


@router.post("/run")
async def run_ingest(background_tasks: BackgroundTasks, filename: str | None = None) -> dict:
    settings = await database.get_settings()
    plan = await database.get_lecture_plan() or {}

    subject = plan.get("subject") or "미설정 과목"
    gemini_api_key = settings.get("gemini_api_key", "")

    upload_dir = await get_upload_dir()
    targets: list[Path] = []
    if filename:
        path = upload_dir / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        targets = [path]
    else:
        targets = sorted(upload_dir.glob("*.pdf"))

    if not targets:
        raise HTTPException(status_code=400, detail="처리할 PDF 파일이 없습니다.")

    async def run_all() -> None:
        for pdf in targets:
            await _run_file_pipeline(pdf, subject, gemini_api_key)

    background_tasks.add_task(run_all)
    return {"message": "파이프라인을 시작했습니다.", "files": [p.name for p in targets]}


@router.get("/progress")
async def ingest_progress() -> StreamingResponse:
    q: asyncio.Queue = asyncio.Queue()
    _progress_subscribers.add(q)

    async def event_stream():
        try:
            yield f"data: {json.dumps(_last_progress, ensure_ascii=False)}\n\n"
            while True:
                data = await q.get()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            _progress_subscribers.discard(q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/files")
async def list_files() -> dict:
    upload_dir = await get_upload_dir()
    files = [p.name for p in sorted(upload_dir.glob("*.pdf"))]
    return {"files": files}


@router.delete("/files/{filename}")
async def delete_file(filename: str) -> dict:
    upload_dir = await get_upload_dir()
    path = upload_dir / filename
    if path.exists():
        path.unlink()

    await database.execute("DELETE FROM chunks WHERE source_file = ?", (filename,))
    return {"message": "삭제되었습니다.", "filename": filename}
