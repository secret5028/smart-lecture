from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from server.db.database import fetch_all, fetch_one

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _to_image_url(image_path: str | None) -> str | None:
    if not image_path:
        return None
    normalized = image_path.replace("\\", "/")
    if normalized.startswith("/chunks/"):
        return normalized
    name = Path(normalized).name
    return f"/chunks/{name}"


@router.get("/tree")
async def get_tree() -> list[dict]:
    rows = await fetch_all(
        """
        SELECT category_large, category_medium, category_small, COUNT(*) AS cnt
        FROM chunks
        WHERE is_processed = 1
        GROUP BY category_large, category_medium, category_small
        ORDER BY category_large, category_medium, category_small
        """
    )

    tree: dict[str, dict] = {}
    for r in rows:
        large = r.get("category_large") or "미분류"
        medium = r.get("category_medium") or "미분류"
        small = r.get("category_small") or "미분류"
        if large not in tree:
            tree[large] = {"id": large, "label": large, "type": "large", "children": []}

        medium_nodes = {m["id"]: m for m in tree[large]["children"]}
        if medium not in medium_nodes:
            node = {"id": medium, "label": medium, "type": "medium", "children": []}
            tree[large]["children"].append(node)
            medium_nodes[medium] = node

        medium_nodes[medium]["children"].append(
            {"id": small, "label": small, "type": "small", "chunk_count": r["cnt"]}
        )

    return list(tree.values())


@router.get("/chunks")
async def get_chunks(category_small: str) -> list[dict]:
    rows = await fetch_all(
        "SELECT * FROM chunks WHERE category_small = ? ORDER BY created_at DESC",
        (category_small,),
    )
    for r in rows:
        r["keywords"] = json.loads(r.get("keywords") or "[]")
        r["image_url"] = _to_image_url(r.get("image_path"))
    return rows


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str) -> dict:
    row = await fetch_one("SELECT * FROM chunks WHERE id = ?", (chunk_id,))
    if not row:
        raise HTTPException(status_code=404, detail="청크를 찾을 수 없습니다.")
    row["keywords"] = json.loads(row.get("keywords") or "[]")
    row["image_url"] = _to_image_url(row.get("image_path"))
    return row


@router.get("/search")
async def search_chunks(q: str) -> list[dict]:
    rows = await fetch_all(
        "SELECT * FROM chunks WHERE content LIKE ? ORDER BY created_at DESC LIMIT 50",
        (f"%{q}%",),
    )
    for r in rows:
        r["keywords"] = json.loads(r.get("keywords") or "[]")
        r["image_url"] = _to_image_url(r.get("image_path"))
    return rows
