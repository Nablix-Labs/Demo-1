import base64
from io import BytesIO

import pytest
from PIL import Image

from app.services.pdf_assembly import PdfAssemblyError, assemble_pdf


def _page(color: str = "white", size: tuple[int, int] = (40, 30)) -> str:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def _page_count(pdf: bytes) -> int:
    # Every page object in a PDF carries one /Type /Page entry.
    return pdf.count(b"/Type /Page\n") or pdf.count(b"/Type/Page")


def test_assemble_pdf_returns_a_pdf() -> None:
    pdf = assemble_pdf([_page()])

    assert pdf.startswith(b"%PDF-")


@pytest.mark.parametrize("page_count", [1, 2, 5])
def test_assemble_pdf_keeps_every_page(page_count: int) -> None:
    pdf = assemble_pdf([_page() for _ in range(page_count)])

    assert _page_count(pdf) == page_count


def test_assemble_pdf_accepts_rgba_pages() -> None:
    buffer = BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()

    pdf = assemble_pdf([f"data:image/png;base64,{encoded}"])

    assert pdf.startswith(b"%PDF-")


def test_assemble_pdf_rejects_empty_input() -> None:
    with pytest.raises(PdfAssemblyError):
        assemble_pdf([])


def test_assemble_pdf_rejects_unreadable_page() -> None:
    with pytest.raises(PdfAssemblyError):
        assemble_pdf(["data:image/png;base64,bm90YW5pbWFnZQ=="])
