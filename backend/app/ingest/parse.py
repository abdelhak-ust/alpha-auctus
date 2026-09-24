"""Per-mime-type parsing: raw bytes -> plain text.

Scope (plans/ingestion.md "Scope for this pass"): text/markdown/csv passthrough, PDF via
pypdf, images via the Vertex vision adapter. Audio/video is explicitly out of scope this pass
(accepts only an already-produced transcript, uploaded as text) — matching ui_ux_design.md's
own deferral of transcription-provider specifics.
"""

import base64

import anyio
from pypdf import PdfReader

from app.ai import get_client
from app.config import get_settings

TEXT_MIME_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json", ""}
PDF_MIME_TYPES = {"application/pdf"}
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

SUPPORTED_MIME_TYPES = TEXT_MIME_TYPES | PDF_MIME_TYPES | IMAGE_MIME_TYPES

_VISION_PROMPT = (
    "Transcribe every word of visible text in this image, and describe any diagrams, "
    "whiteboards, or sketches in plain, literal language (shapes, arrows, labels, "
    "relationships). Be exhaustive and precise — this transcription becomes a source "
    "document that other requirements will be cited against. Output plain text only, no "
    "markdown formatting, no commentary about the image itself."
)


class UnsupportedSourceType(ValueError):
    """A mime type outside SUPPORTED_MIME_TYPES was uploaded for ingestion."""

    def __init__(self, mime_type: str, filename: str):
        self.mime_type = mime_type
        self.filename = filename
        super().__init__(
            f"Can't parse \"{filename}\" ({mime_type or 'unknown type'}) — ingestion "
            f"supports text/markdown/csv, PDF, and images (png/jpeg/webp) this pass. "
            f"Audio/video needs an already-produced transcript uploaded as text."
        )


async def parse_to_text(content: bytes, mime_type: str, filename: str) -> str:
    """Dispatch to the right parser for `mime_type`, always returning plain text."""
    if mime_type in TEXT_MIME_TYPES:
        return content.decode("utf-8", errors="replace")
    if mime_type in PDF_MIME_TYPES:
        return await anyio.to_thread.run_sync(_parse_pdf, content)
    if mime_type in IMAGE_MIME_TYPES:
        return await _parse_image(content, mime_type)
    raise UnsupportedSourceType(mime_type, filename)


def _parse_pdf(content: bytes) -> str:
    import io

    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p for p in pages if p.strip())


async def _parse_image(content: bytes, mime_type: str) -> str:
    settings = get_settings()
    client = get_client()
    encoded = base64.standard_b64encode(content).decode("ascii")
    response = await client.messages.create(
        model=settings.vertex_model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime_type, "data": encoded},
                    },
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }
        ],
    )
    return "".join(block.text for block in response.content if block.type == "text")
