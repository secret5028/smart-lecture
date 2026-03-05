from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from server.db import database
from server.ingest.chunker import chunk_text
from server.ingest.classifier import classify_chunk
from server.ingest.pdf_parser import parse_pdf

ProgressCb = Callable[[dict], Awaitable[None]]


async def run_pipeline(
    pdf_path: Path,
    subject: str,
    gemini_api_key: str,
    progress_cb: ProgressCb | None = None,
) -> dict:
    async def emit(step: str, progress: int, message: str) -> None:
        if progress_cb:
            await progress_cb({"step": step, "progress": progress, "message": message})

    await emit("parsing", 10, "PDF 파싱 중...")
    pages = await asyncio.to_thread(parse_pdf, pdf_path)

    all_chunks: list[dict] = []
    for page in pages:
        all_chunks.extend(chunk_text(page.get("content", ""), page))

    await emit("chunking", 30, f"청크 분해 중... ({len(all_chunks)}/{len(all_chunks)})")

    processed: list[dict] = []
    total = max(len(all_chunks), 1)
    for idx, chunk in enumerate(all_chunks, start=1):
        tag = await classify_chunk(chunk, subject, gemini_api_key)
        processed.append(
            {
                "id": str(uuid.uuid4()),
                **chunk,
                **tag,
                "embedding_id": None,
                "is_processed": True,
            }
        )
        pct = 30 + int((idx / total) * 50)
        await emit("classifying", pct, f"AI 분류 중... ({idx}/{total})")

    await emit("embedding", 85, "임베딩 생성 중...")
    await database.insert_chunks(processed)

    await emit("done", 100, "완료")
    return {"saved_chunks": len(processed), "file": pdf_path.name}
