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


def build_text_mask(boxes_px, width: int, height: int, *,
                    dilate: int = 6, feather: int = 9):
    """Soft mask (float [0,1], shape HxW) = 1 where text boxes are.
    boxes_px: iterable of (l, t, w, h) in pixels."""
    import numpy as np
    import cv2
    mask = np.zeros((height, width), dtype=np.uint8)
    for (l, t, w, h) in boxes_px:
        x0 = max(0, int(round(l))); y0 = max(0, int(round(t)))
        x1 = min(width, int(round(l + w))); y1 = min(height, int(round(t + h)))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = 255
    if dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (dilate * 2 + 1, dilate * 2 + 1))
        mask = cv2.dilate(mask, k)
    if feather > 0:
        kf = feather if feather % 2 == 1 else feather + 1
        mask = cv2.GaussianBlur(mask, (kf, kf), 0)
    return mask.astype(np.float32) / 255.0


def composite_inpaint(original_bgr, ai_bgr, mask):
    """result = original*(1-mask) + resize(ai)*mask. Outside the mask the output
    is pixel-identical to original_bgr."""
    import numpy as np
    import cv2
    h, w = original_bgr.shape[:2]
    if ai_bgr.shape[:2] != (h, w):
        ai_bgr = cv2.resize(ai_bgr, (w, h), interpolation=cv2.INTER_AREA)
    m3 = np.dstack([mask, mask, mask]).astype(np.float32)
    out = original_bgr.astype(np.float32) * (1.0 - m3) + ai_bgr.astype(np.float32) * m3
    return np.clip(out, 0, 255).astype(np.uint8)


def clean_page_background_inpaint(src_path: str, out_path: str, boxes_px, *,
                                  client=None, model: str | None = None) -> bool:
    """Gemini-clean the whole page, then composite ONLY the text-box regions onto
    the original so everything else stays pixel-identical. Returns False on any
    failure (caller keeps the original raster)."""
    try:
        import numpy as np
        import cv2
        data = _gemini_clean_bytes(src_path, client=client, model=model)
        if not data:
            return False
        ai = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        original = cv2.imread(src_path, cv2.IMREAD_COLOR)
        if ai is None or original is None:
            return False
        h, w = original.shape[:2]
        mask = build_text_mask(boxes_px, w, h)
        result = composite_inpaint(original, ai, mask)
        cv2.imwrite(out_path, result)
        return True
    except Exception as e:
        logger.warning(f"clean_page_background_inpaint failed for {src_path}: {e}")
        return False
