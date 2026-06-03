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


def is_photo_background(image_path: str, page_w: float, page_h: float,
                        block_boxes_pt, figure_boxes_pt,
                        scale_x: float, scale_y: float,
                        *, near_paper_thresh: float = 0.70, samples: int = 40) -> bool:
    """True if the page background (area OUTSIDE text/figure boxes) looks like a
    photo/graphic rather than near-uniform paper.

    Used to keep the raster on full-bleed cover/infographic pages that docling
    reports as text-dominant (the cover photo is the page background, not a
    detected picture block). Any failure returns False (safe: behave as before)."""
    try:
        covered = []
        for b in list(block_boxes_pt) + list(figure_boxes_pt):
            l, t, w, h = b
            covered.append((l * scale_x, t * scale_y, (l + w) * scale_x, (t + h) * scale_y))

        def is_covered(x, y):
            for (cl, ct, cr, cb) in covered:
                if cl <= x <= cr and ct <= y <= cb:
                    return True
            return False

        with Image.open(image_path) as im:
            im = im.convert("RGB")
            W, H = im.size
            sx = max(1, W // samples)
            sy = max(1, H // samples)
            paper = 0
            total = 0
            for x in range(0, W, sx):
                for y in range(0, H, sy):
                    if is_covered(x, y):
                        continue
                    r, g, b = im.getpixel((x, y))
                    total += 1
                    lum = 0.299 * r + 0.587 * g + 0.114 * b
                    sat = max(r, g, b) - min(r, g, b)
                    if lum >= 235 and sat <= 12:
                        paper += 1
            if total == 0:
                return False
            return (paper / total) < near_paper_thresh
    except Exception as e:
        logger.warning(f"is_photo_background failed for {image_path}: {e}")
        return False


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


def analyze_block_box(image_path: str, bbox_pt, scale_x: float, scale_y: float,
                      *, var_threshold: float = 18.0, samples: int = 24) -> dict:
    """Decide the background treatment for a translated-text block over a raster.
    Uniform local background -> {"mode":"fill","fill":"#rrggbb"} (median color).
    Photo-like (high colour variance) -> {"mode":"scrim","fill":"rgba(...)"} whose
    tone matches the local luminance (dark scrim on dark bg, light on light) so the
    original text colour stays readable. Any failure -> fill via sample_bg_color."""
    l, t, w, h = bbox_pt
    bbox_px = (l * scale_x, t * scale_y, (l + w) * scale_x, (t + h) * scale_y)
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            W, H = im.size
            x0 = max(0, min(int(l * scale_x), W - 1)); y0 = max(0, min(int(t * scale_y), H - 1))
            x1 = max(x0 + 1, min(int((l + w) * scale_x), W)); y1 = max(y0 + 1, min(int((t + h) * scale_y), H))
            sx = max(1, (x1 - x0) // samples); sy = max(1, (y1 - y0) // samples)
            pts = [im.getpixel((x, y)) for x in range(x0, x1, sx) for y in range(y0, y1, sy)]
            if not pts:
                return {"mode": "fill", "fill": sample_bg_color(image_path, bbox_px)}
            n = len(pts)
            mean = [sum(p[i] for p in pts) / n for i in range(3)]
            var = sum((p[i] - mean[i]) ** 2 for p in pts for i in range(3)) / (3 * n)
            std = var ** 0.5
            lum = 0.299 * mean[0] + 0.587 * mean[1] + 0.114 * mean[2]
            if std <= var_threshold:
                rr = sorted(p[0] for p in pts)[n // 2]
                gg = sorted(p[1] for p in pts)[n // 2]
                bb = sorted(p[2] for p in pts)[n // 2]
                return {"mode": "fill", "fill": f"#{rr:02x}{gg:02x}{bb:02x}"}
            if lum >= 140:
                return {"mode": "scrim", "fill": "rgba(255,255,255,0.55)"}
            return {"mode": "scrim", "fill": "rgba(0,0,0,0.45)"}
    except Exception as e:
        logger.warning(f"analyze_block_box failed for {image_path}: {e}")
        try:
            return {"mode": "fill", "fill": sample_bg_color(image_path, bbox_px)}
        except Exception:
            return {"mode": "fill", "fill": "#ffffff"}
