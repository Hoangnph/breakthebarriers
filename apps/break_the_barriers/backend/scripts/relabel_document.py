"""Backfill #0 eligibility labels onto an already-extracted document.

Reads each `{doc}-{n}.model.json` plus its figure crops (already on disk),
recomputes page_class/cover with the heuristic classifier, and rewrites the
model.json in place. Usage:

    .venv/bin/python scripts/relabel_document.py <doc_dir>
"""
import os
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.page_model import PageModel
from app.services.picture_classifier import classify_picture_file
from app.services.page_eligibility import classify_page, detect_cover


def relabel_document(doc_dir: str) -> int:
    files = glob.glob(os.path.join(doc_dir, "*.model.json"))
    files.sort(key=lambda p: int(p.split("-")[-1].split(".")[0]))
    total = len(files)
    changed = 0
    for idx, path in enumerate(files):
        pm = PageModel.from_json(open(path, encoding="utf-8").read())
        labels = [classify_picture_file(os.path.join(doc_dir, f.img))[0] for f in pm.figures]
        page_area = max(pm.page_w * pm.page_h, 1.0)
        text_ratio = sum(b.bbox[2] * b.bbox[3] for b in pm.blocks) / page_area
        fig_ratio = sum(f.bbox[2] * f.bbox[3] for f in pm.figures) / page_area
        has_table = any(b.role == "table" for b in pm.blocks)
        bg_is_photo = bool((pm.background or {}).get("image")) and pm.kind != "text"
        pm.page_class = classify_page(text_ratio, fig_ratio, labels,
                                      has_table=has_table, bg_is_photo=bg_is_photo)
        pm.cover = detect_cover(idx, total, text_ratio=text_ratio,
                                fig_ratio=fig_ratio, bg_is_photo=bg_is_photo)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(pm.to_json())
        changed += 1
        print(f"{os.path.basename(path)}: page_class={pm.page_class} cover={pm.cover} "
              f"(figs={labels})")
    return changed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: relabel_document.py <doc_dir>", file=sys.stderr)
        sys.exit(2)
    n = relabel_document(sys.argv[1])
    print(f"relabelled {n} pages")
