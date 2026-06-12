"""Reconcile clean_img for flow banner figures of an already-extracted document.

For every figure on a content page:
  * a genuine banner (wide figure >= _BANNER_MIN_WIDTH_FRAC of the page, holding a
    large overlaid title) gets its TITLE REGION inpaint-cleaned + vision-verified
    (clean_banner_inpaint_verified) so the flow can overlay the translated title;
  * any other figure that still carries a clean_img (e.g. a stale whole-clean that
    damaged content) has it CLEARED, so the flow shows the original image.

Usage (from apps/break_the_barriers/backend, .env must hold GEMINI_API_KEY):
    PYTHONPATH=.. .venv/bin/python scripts/clean_flow_banners.py <doc_id> [--force] [--dry-run]

--force re-cleans banners that already have a clean_img (e.g. to upgrade an old
whole-clean to inpaint). Costs one image-edit + one verify call per cleaned banner.
"""
import os.path as osp
import sys

import backend.app.config  # noqa: F401  (load_dotenv → GEMINI_API_KEY)
from PIL import Image
from backend.app.database import SessionLocal
from backend.app.models_db import DBPage
from backend.app.services.page_model import PageModel
from backend.app.services.background_policy import effective_policy
from backend.app.services.flow_model import (
    _center_inside, _BANNER_MAX_BLOCKS, _BANNER_MIN_WIDTH_FRAC,
    _BANNER_MIN_TITLE_SIZE, _DESIGN_MAX_TEXT_BLOCKS,
)
from backend.app.services.image_cleaner import clean_banner_inpaint_verified


def _banner_title(pm: PageModel, fig):
    """Return the overlaid title block if `fig` is a genuine banner, else None."""
    if (fig.bbox[2] or 0) < _BANNER_MIN_WIDTH_FRAC * pm.page_w:
        return None
    contained = [b for b in pm.blocks if _center_inside(b.bbox, fig.bbox)]
    if not contained or len(contained) > _BANNER_MAX_BLOCKS:
        return None
    primary = max(contained, key=lambda b: (b.font.size if b.font and b.font.size else 0))
    size = primary.font.size if primary.font and primary.font.size else 0
    return primary if size >= _BANNER_MIN_TITLE_SIZE else None


def _title_box_px(fig, title, fig_path):
    fw_px, fh_px = Image.open(fig_path).size
    fx, fy, fw, fh = fig.bbox
    tb = title.bbox
    sxp, syp = fw_px / fw, fh_px / fh
    return ((tb[0] - fx) * sxp, (tb[1] - fy) * syp, tb[2] * sxp, tb[3] * syp)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    doc_id = args[0] if args else "2024-wttc-introduction-to-ai"
    out_dir = osp.join("data", "extracted_html", doc_id)

    db = SessionLocal()
    rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
            .order_by(DBPage.page_num).all())
    cleaned = cleared = failed = 0
    for r in rows:
        if not r.model_json:
            continue
        pm = PageModel.from_json(r.model_json)
        bg = pm.background or {}
        pol = effective_policy(pm.page_class, pm.cover, bg.get("policy_override"))
        if pol in ("clean-photo", "keep-raster") and (
                pm.cover in ("front", "back") or len(pm.blocks) <= _DESIGN_MAX_TEXT_BLOCKS):
            continue  # whole-page image, not a flow banner
        changed = False
        for f in pm.figures:
            title = _banner_title(pm, f)
            if title is None:
                if f.clean_img:                       # stale/bad clean → drop it
                    print(f"p{r.page_num} {f.img}: clear stale clean_img")
                    if not dry:
                        f.clean_img = None
                        changed = True
                    cleared += 1
                continue
            if f.clean_img and not force:
                continue
            src = osp.join(out_dir, f.img)
            if not osp.exists(src):
                print(f"  MISSING {src}")
                failed += 1
                continue
            out_name = f.img.rsplit(".", 1)[0] + ".clean.png"
            print(f"p{r.page_num} {f.img} -> inpaint {out_name}", end=" ", flush=True)
            if dry:
                print("(dry-run)")
                continue
            box_px = _title_box_px(f, title, src)
            if clean_banner_inpaint_verified(src, osp.join(out_dir, out_name), [box_px]):
                f.clean_img = out_name
                changed = True
                cleaned += 1
                print("OK")
            else:
                f.clean_img = None       # verify rejected → keep original
                changed = True
                failed += 1
                print("REJECTED (kept original)")
        if changed and not dry:
            r.model_json = pm.to_json()
    if not dry:
        db.commit()
    db.close()
    print(f"Done. cleaned={cleaned} cleared={cleared} failed/rejected={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
