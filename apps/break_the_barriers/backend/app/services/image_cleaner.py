"""Clean baked-in text off a page raster using Gemini image editing (Phase 2).

Used only on `clean-photo` pages (covers / full-bleed art), on demand. Returns
True and writes a text-free PNG to out_path on success; any failure (no API key,
no image in response, API error) returns False so the caller keeps the original
raster. `client` is injectable so tests run without network."""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

_PROMPT = (
    "You are a precise image inpainting tool, NOT an image generator. "
    "Remove ONLY the rendered text, letters, numbers, and any "
    "table-of-contents/caption boxes from this image. Do NOT redraw, regenerate, "
    "restyle, or move any person, face, object, background, lighting, or color. "
    "Reconstruct strictly the small regions directly beneath the removed text by "
    "extending the immediately surrounding pixels (inpainting). Every area that "
    "had no text MUST remain pixel-identical to the input. Output the same photo, "
    "same composition, with the text gone."
)


def _default_model() -> str:
    return os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")


def _gemini_clean_bytes(src_path: str, *, client=None,
                        model: str | None = None) -> bytes | None:
    """Call Gemini image-edit and return the cleaned image bytes, or None on any
    failure (no key, no image in response, API error)."""
    model = model or _default_model()
    try:
        from PIL import Image
        if client is None:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return None
            client = genai.Client(api_key=api_key)
        img = Image.open(src_path)
        resp = client.models.generate_content(model=model, contents=[_PROMPT, img])
        for cand in (getattr(resp, "candidates", None) or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline else None
                if data:
                    return data
        return None
    except Exception as e:
        logger.warning(f"_gemini_clean_bytes failed for {src_path}: {e}")
        return None


def clean_page_background(src_path: str, out_path: str, *, client=None,
                         model: str | None = None) -> bool:
    data = _gemini_clean_bytes(src_path, client=client, model=model)
    if not data:
        return False
    with open(out_path, "wb") as fh:
        fh.write(data)
    return True
