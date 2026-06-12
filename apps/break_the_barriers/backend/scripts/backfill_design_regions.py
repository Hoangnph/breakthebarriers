# scripts/backfill_design_regions.py
"""Backfill figure alignment + composite design-region crops for an extracted doc.

Per page: set Figure.align from geometry; detect chat-like design regions (icon-figures
interleaved with text); crop each from the page raster; replace the member figures+blocks
with one `content-region` Figure (centered). Updates DBPage.model_json + the on-disk
{doc}-{n}.model.json. Idempotent: a page already collapsed to a content-region has no
icons left, so no new region is produced.

Usage (from apps/break_the_barriers/backend):
    PYTHONPATH=.. .venv/bin/python scripts/backfill_design_regions.py <doc_id> [--dry-run]
"""
import os.path as osp
import sys

import backend.app.config  # noqa: F401
from PIL import Image
from backend.app.database import SessionLocal
from backend.app.models_db import DBPage
from backend.app.services.page_model import PageModel, Figure
from backend.app.services.design_region import infer_figure_align, detect_design_regions
from backend.app.services.figure_grouper import crop_group_region


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    doc_id = args[0] if args else "2024-wttc-introduction-to-ai"
    out_dir = osp.join("data", "extracted_html", doc_id)

    db = SessionLocal()
    rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
            .order_by(DBPage.page_num).all())
    n_align = 0
    n_region = 0
    for r in rows:
        if not r.model_json:
            continue
        pm = PageModel.from_json(r.model_json)
        for f in pm.figures:
            new = infer_figure_align(list(f.bbox), pm.page_w)
            if f.align != new:
                f.align = new
                n_align += 1
        raster = (pm.background or {}).get("image") or f"page-{r.page_num}.png"
        rpath = osp.join(out_dir, raster)
        if pm.figures and osp.exists(rpath):
            figbb = [list(f.bbox) for f in pm.figures]
            blk = [(b.span_id, list(b.bbox)) for b in pm.blocks]
            regs = detect_design_regions(figbb, blk, pm.page_w, pm.page_h)
            if regs:
                print(f"p{r.page_num}: {len(regs)} region(s)",
                      "(dry-run)" if dry else "OK")
                if not dry:
                    img = Image.open(rpath)
                    rm_fig, rm_blk, newr = set(), set(), []
                    for ri, rg in enumerate(regs, start=1):
                        rm_fig.update(rg.figure_idx)
                        rm_blk.update(rg.block_ids)
                        rname = f"{doc_id}-{r.page_num}-region{ri}.png"
                        crop_group_region(img, rg.bbox, pm.page_w, pm.page_h).save(
                            osp.join(out_dir, rname))
                        newr.append(Figure(bbox=rg.bbox, img=rname,
                                           kind="content-region", align="center"))
                    pm.figures = [f for k, f in enumerate(pm.figures)
                                  if k not in rm_fig] + newr
                    pm.blocks = [b for b in pm.blocks if b.span_id not in rm_blk]
                n_region += len(regs)
        if not dry:
            r.model_json = pm.to_json()
            mp = osp.join(out_dir, f"{doc_id}-{r.page_num}.model.json")
            if osp.exists(mp):
                with open(mp, "w", encoding="utf-8") as fh:
                    fh.write(pm.to_json())
    if not dry:
        db.commit()
    db.close()
    print(f"Done. align updated = {n_align}, regions = {n_region}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
