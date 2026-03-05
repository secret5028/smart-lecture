from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from config import CHUNK_IMAGE_DIR

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None


def _image_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_existing_hash_map() -> dict[str, Path]:
    hashes: dict[str, Path] = {}
    for p in CHUNK_IMAGE_DIR.glob("*.png"):
        if p.stem.endswith("_thumb"):
            continue
        try:
            hashes[_image_hash(p.read_bytes())] = p
        except Exception:
            continue
    return hashes


def _thumb_path(image_path: Path) -> Path:
    return image_path.with_name(f"{image_path.stem}_thumb{image_path.suffix}")


def parse_pdf(pdf_path: Path) -> list[dict]:
    if fitz is None:
        raise RuntimeError("pymupdf(fitz)가 설치되지 않았습니다.")

    items: list[dict] = []
    known_hashes = _load_existing_hash_map()
    doc = fitz.open(pdf_path)

    try:
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            page_number = page_index + 1
            text = (page.get_text("text") or "").strip()

            if len(text) >= 200:
                items.append(
                    {
                        "source_file": pdf_path.name,
                        "page_number": page_number,
                        "content_type": "text",
                        "content": text,
                        "image_path": None,
                    }
                )
                continue

            images = page.get_images(full=True)
            if images:
                for img_idx, img in enumerate(images, start=1):
                    xref = img[0]
                    base = doc.extract_image(xref)
                    image_bytes = base["image"]
                    pil = Image.open(BytesIO(image_bytes)).convert("RGB")

                    buffer = BytesIO()
                    pil.save(buffer, format="PNG")
                    png_bytes = buffer.getvalue()
                    digest = _image_hash(png_bytes)

                    if digest in known_hashes:
                        image_path = known_hashes[digest]
                    else:
                        image_path = CHUNK_IMAGE_DIR / f"img_{digest[:16]}.png"
                        image_path.write_bytes(png_bytes)
                        known_hashes[digest] = image_path

                        thumb = pil.copy()
                        thumb.thumbnail((200, 200))
                        thumb.save(_thumb_path(image_path), format="PNG")

                    items.append(
                        {
                            "source_file": pdf_path.name,
                            "page_number": page_number,
                            "content_type": "image",
                            "content": f"이미지 페이지 {page_number}-{img_idx}",
                            "image_path": str(image_path),
                        }
                    )
            else:
                items.append(
                    {
                        "source_file": pdf_path.name,
                        "page_number": page_number,
                        "content_type": "text",
                        "content": text,
                        "image_path": None,
                    }
                )
    finally:
        doc.close()

    return items
