from __future__ import annotations

import re

from config import CHUNK_OVERLAP, CHUNK_SIZE


def _find_cut_index(block: str, max_len: int) -> int:
    if len(block) <= max_len:
        return len(block)
    window = block[: max_len + 1]
    candidates = [window.rfind("."), window.rfind("\n"), window.rfind("!"), window.rfind("?")]
    cut = max(candidates)
    return cut + 1 if cut > int(max_len * 0.6) else max_len


def chunk_text(text: str, source_meta: dict) -> list[dict]:
    content_type = source_meta.get("content_type", "text")

    if content_type == "image":
        return [
            {
                "chunk_index": 0,
                "content_type": "image",
                "content": source_meta.get("content", ""),
                "source_file": source_meta.get("source_file"),
                "page_number": source_meta.get("page_number"),
                "image_path": source_meta.get("image_path"),
            }
        ]

    clean_text = re.sub(r"\s+", " ", text or "").strip()
    if not clean_text:
        return []

    chunks: list[dict] = []
    start = 0
    idx = 0
    while start < len(clean_text):
        remain = clean_text[start:]
        cut = _find_cut_index(remain, CHUNK_SIZE)
        body = remain[:cut].strip()
        if body:
            chunks.append(
                {
                    "chunk_index": idx,
                    "content_type": "text",
                    "content": body,
                    "source_file": source_meta.get("source_file"),
                    "page_number": source_meta.get("page_number"),
                    "image_path": None,
                }
            )
            idx += 1

        if cut >= len(remain):
            break
        start += max(cut - CHUNK_OVERLAP, 1)

    return chunks
