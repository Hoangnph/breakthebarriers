"""Backfill merge-image figure groups for an already-extracted document.

For each page: cluster its figures, and where a cluster came from ONE embedded PDF
image, replace the member crops with a single crop of the union (+ caption strip)
taken from the page raster. Updates DBPage.model_json.

Usage (from apps/break_the_barriers/backend):
    PYTHONPATH=.. .venv/bin/python scripts/merge_figure_groups.py <doc_id> [--dry-run]
"""
import os.path as osp
import sys

import backend.app.config  # noqa: F401
from PIL import Image
from backend.app.database import SessionLocal
from backend.app.models_db import DBPage
from backend.app.services.page_model import PageModel, Figure
from backend.app.services.figure_grouper import plan_merge_groups, crop_group_region


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    doc_id = args[0] if args else "2024-wttc-introduction-to-ai"
    out_dir = osp.join("data", "extracted_html", doc_id)

    db = SessionLocal()
    rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
            .order_by(DBPage.page_num).all())
    merged = 0
    for r in rows:
        if not r.model_json:
            continue
        pm = PageModel.from_json(r.model_json)
        if len(pm.figures) < 2:
            continue
        # background.image is None on content pages (white bg) even though the page
        # raster page-{n}.png was still saved at extraction — use it directly.
        raster = (pm.background or {}).get("image") or f"page-{r.page_num}.png"
        if not osp.exists(osp.join(out_dir, raster)):
            continue
        figbb = [list(f.bbox) for f in pm.figures]
        blkbb = [list(b.bbox) for b in pm.blocks]
        plans = plan_merge_groups(figbb, blkbb, pm.page_w, pm.page_h)
        if not plans:
            continue
        print(f"p{r.page_num}: {len(plans)} group(s) merge", end=" ")
        if dry:
            print("(dry-run)")
            continue
        img = Image.open(osp.join(out_dir, raster))
        merged_idx: set = set()
        new: list = []
        for gi, plan in enumerate(plans, start=1):
            merged_idx.update(plan["members"])
            gname = f"{doc_id}-{r.page_num}-figgroup{gi}.png"
            crop_group_region(img, plan["bbox"], pm.page_w, pm.page_h).save(
                osp.join(out_dir, gname))
            new.append(Figure(bbox=plan["bbox"], img=gname, kind="illustration"))
        pm.figures = [f for k, f in enumerate(pm.figures) if k not in merged_idx] + new
        r.model_json = pm.to_json()
        merged += len(plans)
        print("OK")
    if not dry:
        db.commit()
    db.close()
    print(f"Done. merged groups = {merged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
