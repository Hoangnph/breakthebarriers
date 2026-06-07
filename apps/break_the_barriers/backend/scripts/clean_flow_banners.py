"""Backfill clean_img for flow banner figures of an already-extracted document.

A flow banner = a figure (on a non image-only page) that overlaps a small number
of text blocks (a title or two). Overlaying a translated title on such a figure
only looks right when the figure's baked-in text has been removed, so this script
runs the Gemini whole-clean on each banner figure that still lacks a clean_img and
writes the result back into DBPage.model_json.

Usage (from apps/break_the_barriers/backend, .env must hold GEMINI_API_KEY):
    PYTHONPATH=.. .venv/bin/python scripts/clean_flow_banners.py <doc_id> [--dry-run]

Costs one Gemini image-edit call per cleaned figure.
"""
import os
import os.path as osp
import sys

import backend.app.config  # noqa: F401  (load_dotenv → GEMINI_API_KEY)
from backend.app.database import SessionLocal
from backend.app.models_db import DBPage
from backend.app.services.page_model import PageModel
from backend.app.services.background_policy import effective_policy
from backend.app.services.flow_model import (
    _center_inside, _BANNER_MAX_BLOCKS, _DESIGN_MAX_TEXT_BLOCKS,
)
from backend.app.services.image_cleaner import clean_page_background


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    doc_id = args[0] if args else "2024-wttc-introduction-to-ai"
    out_dir = osp.join("data", "extracted_html", doc_id)

    db = SessionLocal()
    rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
            .order_by(DBPage.page_num).all())
    cleaned = failed = 0
    for r in rows:
        if not r.model_json:
            continue
        pm = PageModel.from_json(r.model_json)
        bg = pm.background or {}
        pol = effective_policy(pm.page_class, pm.cover, bg.get("policy_override"))
        is_cover = pm.cover in ("front", "back")
        if pol in ("clean-photo", "keep-raster") and (
                is_cover or len(pm.blocks) <= _DESIGN_MAX_TEXT_BLOCKS):
            continue  # whole-page image, not a flow banner
        changed = False
        for f in pm.figures:
            if f.clean_img:
                continue
            contained = [b for b in pm.blocks if _center_inside(b.bbox, f.bbox)]
            if not contained or len(contained) > _BANNER_MAX_BLOCKS:
                continue
            src = osp.join(out_dir, f.img)
            if not osp.exists(src):
                print(f"  MISSING {src}")
                failed += 1
                continue
            out_name = f.img.rsplit(".", 1)[0] + ".clean.png"
            print(f"p{r.page_num} {f.img} -> {out_name}", end=" ", flush=True)
            if dry:
                print("(dry-run)")
                continue
            if clean_page_background(src, osp.join(out_dir, out_name)):
                f.clean_img = out_name
                changed = True
                cleaned += 1
                print("OK")
            else:
                failed += 1
                print("FAIL")
        if changed and not dry:
            r.model_json = pm.to_json()
    if not dry:
        db.commit()
    db.close()
    print(f"Done. cleaned={cleaned} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
