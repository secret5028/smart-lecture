from __future__ import annotations

import json
from typing import Any

import aiosqlite

from config import DB_FILE
from server.db.models import ALL_TABLES_SQL, DEFAULT_SETTINGS_SQL


async def init_db() -> None:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_FILE) as db:
        for sql in ALL_TABLES_SQL:
            await db.execute(sql)
        for sql in DEFAULT_SETTINGS_SQL:
            await db.execute(sql)
        await db.commit()


async def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None


async def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(r) for r in rows]


async def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(query, params)
        await db.commit()


async def executemany(query: str, params: list[tuple[Any, ...]]) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executemany(query, params)
        await db.commit()


async def upsert_setting(key: str, value: str) -> None:
    await execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
        """,
        (key, value),
    )


async def get_settings() -> dict[str, str]:
    rows = await fetch_all("SELECT key, value FROM settings")
    return {row["key"]: row["value"] for row in rows}


async def save_lecture_plan(payload: dict[str, Any]) -> int:
    await execute(
        "DELETE FROM lecture_plan"
    )
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            """
            INSERT INTO lecture_plan (
                subject, target_audience, learning_objectives,
                total_sessions, minutes_per_session, toc, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                payload["subject"],
                payload.get("target_audience", ""),
                json.dumps(payload.get("learning_objectives", []), ensure_ascii=False),
                payload.get("total_sessions"),
                payload.get("minutes_per_session"),
                json.dumps(payload.get("toc", []), ensure_ascii=False),
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def get_lecture_plan() -> dict[str, Any] | None:
    row = await fetch_one("SELECT * FROM lecture_plan ORDER BY id DESC LIMIT 1")
    if not row:
        return None
    row["learning_objectives"] = json.loads(row["learning_objectives"] or "[]")
    row["toc"] = json.loads(row["toc"] or "[]")
    return row


async def insert_chunks(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    values = [
        (
            r["id"],
            r["source_file"],
            r.get("page_number"),
            r.get("chunk_index"),
            r["content_type"],
            r.get("content"),
            r.get("image_path"),
            r.get("category_large"),
            r.get("category_medium"),
            r.get("category_small"),
            json.dumps(r.get("keywords", []), ensure_ascii=False),
            r.get("embedding_id"),
            int(bool(r.get("is_processed", False))),
        )
        for r in rows
    ]
    await executemany(
        """
        INSERT OR REPLACE INTO chunks (
            id, source_file, page_number, chunk_index, content_type,
            content, image_path, category_large, category_medium, category_small,
            keywords, embedding_id, is_processed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
