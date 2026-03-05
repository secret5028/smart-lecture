from __future__ import annotations

import json

from server.db.database import fetch_all

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover
    SentenceTransformer = None

_embedding_model = None


def load_embedding_model(model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
    global _embedding_model
    if _embedding_model is None and SentenceTransformer is not None:
        _embedding_model = SentenceTransformer(model_name)
    return _embedding_model


class KnowledgeRetriever:
    def search(self, query: str, top_k: int = 5, filter_type: str | None = None) -> list[dict]:
        sql = "SELECT * FROM chunks WHERE is_processed = 1"
        params: list = []
        if query:
            sql += " AND content LIKE ?"
            params.append(f"%{query}%")
        if filter_type in {"text", "image"}:
            sql += " AND content_type = ?"
            params.append(filter_type)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)
        return []

    async def search_async(self, query: str, top_k: int = 5, filter_type: str | None = None) -> list[dict]:
        sql = "SELECT * FROM chunks WHERE is_processed = 1"
        params: list = []
        if query:
            sql += " AND content LIKE ?"
            params.append(f"%{query}%")
        if filter_type in {"text", "image"}:
            sql += " AND content_type = ?"
            params.append(filter_type)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(top_k)

        rows = await fetch_all(sql, tuple(params))
        for row in rows:
            row["keywords"] = json.loads(row.get("keywords") or "[]")
            row["score"] = 1.0
        return rows

    async def search_by_category(self, category_small: str, top_k: int = 20) -> list[dict]:
        rows = await fetch_all(
            "SELECT * FROM chunks WHERE category_small = ? AND is_processed = 1 ORDER BY created_at DESC LIMIT ?",
            (category_small, top_k),
        )
        for row in rows:
            row["keywords"] = json.loads(row.get("keywords") or "[]")
            row["score"] = 1.0
        return rows
