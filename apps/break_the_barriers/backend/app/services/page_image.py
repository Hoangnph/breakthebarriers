import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)


def save_page_image(pil_image, output_dir: str, doc_id: str, page_no: int) -> str:
    """Save a PIL page image as PNG into output_dir. Returns the filename only."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"page-{page_no}.png"
    pil_image.convert("RGB").save(os.path.join(output_dir, filename), "PNG")
    return filename


def sample_bg_color(image_path: str, bbox_px) -> str:
    """Median RGB of the bbox border pixels as '#rrggbb'. Any failure → '#ffffff'."""
    try:
        l, t, r, b = (int(round(v)) for v in bbox_px)
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            l = max(0, min(l, w - 1)); r = max(l + 1, min(r, w))
            t = max(0, min(t, h - 1)); b = max(t + 1, min(b, h))
            pts = []
            sx = max(1, (r - l) // 20)
            sy = max(1, (b - t) // 20)
            for x in range(l, r, sx):
                pts.append(im.getpixel((x, t)))
                pts.append(im.getpixel((x, b - 1)))
            for y in range(t, b, sy):
                pts.append(im.getpixel((l, y)))
                pts.append(im.getpixel((r - 1, y)))
            if not pts:
                return "#ffffff"
            mid = len(pts) // 2
            rr = sorted(p[0] for p in pts)[mid]
            gg = sorted(p[1] for p in pts)[mid]
            bb = sorted(p[2] for p in pts)[mid]
            return f"#{rr:02x}{gg:02x}{bb:02x}"
    except Exception as e:
        logger.warning(f"sample_bg_color failed for {image_path}: {e}")
        return "#ffffff"
