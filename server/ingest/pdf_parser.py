from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from config import CHUNK_IMAGE_DIR

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None


def parse_pdf(pdf_path: Path) -> list[dict]:
    if fitz is None:
        raise RuntimeError("pymupdf(fitz)가 설치되지 않았습니다.")

    items: list[dict] = []
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

                    image_name = f"{pdf_path.stem}_p{page_number}_{img_idx}.png"
                    image_path = CHUNK_IMAGE_DIR / image_name
                    pil.save(image_path, format="PNG")

                    thumb = pil.copy()
                    thumb.thumbnail((200, 200))
                    thumb.save(CHUNK_IMAGE_DIR / f"{pdf_path.stem}_p{page_number}_{img_idx}_thumb.png", format="PNG")

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
                # 텍스트/이미지 모두 빈 페이지일 때도 최소 레코드는 남긴다.
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
