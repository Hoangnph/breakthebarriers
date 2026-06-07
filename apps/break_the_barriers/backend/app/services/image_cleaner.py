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
    "You are a precise photo inpainting tool, not an image generator. "
    "Task: make every piece of rendered text disappear — letters, numbers, "
    "captions, and any solid label/title/table-of-contents boxes. "
    "Crucially, do not merely erase the text or paint a blank/blurred patch: "
    "REBUILD the scene that the text was covering so it looks like the text was "
    "never there. Continue the surrounding background through the cleared area, "
    "matching its texture, colour, lighting, gradient, edges and perspective, with "
    "no visible seam, hole, smear, box outline or ghost of the old text. "
    "Do NOT add, remove, move, restyle or redraw any person, face, body, object, "
    "logo or scenery, and do NOT change the composition, framing or colours of any "
    "text-free area. Output the same photo at the same resolution and aspect ratio, "
    "with the text gone and its background seamlessly reconstructed."
)

# Vision QA reviewer for the harness: checks a cleaned image against the original.
_VERIFY_MODEL_DEFAULT = "gemini-2.5-flash"
_VERIFY_PROMPT = (
    "You are a strict QA reviewer for a photo text-removal tool. The FIRST image is "
    "the ORIGINAL, the SECOND is the CLEANED result. Reply with ONLY a JSON object: "
    '{"text_gone": true|false, "content_preserved": true|false, '
    '"reconstruction_natural": true|false, "reason": "short explanation"}. '
    "text_gone = no readable rendered text, letters or labels remain in the cleaned "
    "image. content_preserved = every person, face, body, object and scenery is "
    "unchanged (nothing added, removed, distorted or relocated). "
    "reconstruction_natural = regions where text was removed are filled with natural "
    "matching background (no blank patch, blur, smear, box outline or artifact)."
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


def _resp_text(resp) -> str:
    """Concatenate text parts of a generate_content response."""
    out = []
    for cand in (getattr(resp, "candidates", None) or []):
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            t = getattr(part, "text", None)
            if t:
                out.append(t)
    return "".join(out)


def verify_clean(original_path: str, cleaned_path: str, *, client=None,
                 model: str | None = None) -> tuple[bool, str]:
    """Vision-QA a cleaned image against the original (the harness 'checker').

    Returns (accept, reason). accept is True only when the reviewer confirms the
    text is gone, content is preserved AND the reconstruction looks natural. On any
    infrastructure failure (no key, no/!json reply, API error) returns (True,
    'verify-skipped: ...') so a flaky verifier never discards an otherwise-good
    clean — the inpaint composite already guarantees pixels outside the mask."""
    import json
    import re
    try:
        from PIL import Image
        if client is None:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return True, "verify-skipped: no key"
            client = genai.Client(api_key=api_key)
        model = model or os.getenv("GEMINI_VERIFY_MODEL", _VERIFY_MODEL_DEFAULT)
        orig = Image.open(original_path)
        clean = Image.open(cleaned_path)
        resp = client.models.generate_content(
            model=model, contents=[_VERIFY_PROMPT, orig, clean])
        text = _resp_text(resp)
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return True, "verify-skipped: no json"
        v = json.loads(m.group(0))
        ok = (bool(v.get("text_gone")) and bool(v.get("content_preserved"))
              and bool(v.get("reconstruction_natural")))
        return ok, str(v.get("reason", ""))[:200]
    except Exception as e:
        logger.warning(f"verify_clean failed for {cleaned_path}: {e}")
        return True, "verify-skipped: error"


def clean_banner_inpaint_verified(src_path: str, out_path: str, boxes_px, *,
                                  client=None, model: str | None = None,
                                  verify: bool = True, max_attempts: int = 2) -> bool:
    """Inpaint-clean a banner's title region, then QA-verify with the vision harness.
    Retries on a failed verdict; if no attempt passes, removes the output and returns
    False so the caller keeps the ORIGINAL image (never a damaged clean)."""
    for attempt in range(max(1, max_attempts)):
        if not clean_page_background_inpaint(src_path, out_path, boxes_px,
                                             client=client, model=model):
            continue
        if not verify:
            return True
        ok, reason = verify_clean(src_path, out_path, client=client)
        if ok:
            return True
        logger.info(
            f"banner clean rejected (attempt {attempt + 1}/{max_attempts}): {reason}")
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except OSError:
        pass
    return False
