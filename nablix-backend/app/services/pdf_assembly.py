"""Combine ordered canvas pages into one PDF.

Phase 4 stores a student's Phase 3 work as a single PDF per attempt rather
than as separate page images, so the tutor review can show the original
handwriting and reference a page by number.
"""

from __future__ import annotations

import base64
import binascii
from io import BytesIO

from PIL import Image, UnidentifiedImageError


class PdfAssemblyError(ValueError):
    pass


def _decode_page(page_data_url: str) -> Image.Image:
    _, _, payload = page_data_url.partition(",")
    try:
        image = Image.open(BytesIO(base64.b64decode(payload, validate=True)))
        image.load()
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError) as error:
        raise PdfAssemblyError(f"canvas page is not a readable image: {error}") from error
    # PDF has no alpha channel. Composite transparent pages onto white so transparent pixels do not turn black.
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, image.convert("RGBA")).convert("RGB")
    return image.convert("RGB")


def assemble_pdf(page_data_urls: list[str]) -> bytes:
    """Return a single PDF containing every page, in the given order."""
    if not page_data_urls:
        raise PdfAssemblyError("at least one canvas page is required.")

    first, *rest = [_decode_page(page) for page in page_data_urls]
    buffer = BytesIO()
    first.save(buffer, format="PDF", save_all=True, append_images=rest)
    return buffer.getvalue()
