# Figure-Group Merge (Plan A: merge-image) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When extraction splits one embedded image into several stacked figures (e.g. the 3 portraits Yann LeCun / Geoffrey Hinton / Yoshua Bengio), merge that cluster back into a single raster crop so the flow shows the original row layout + baked captions.

**Architecture:** A pure `figure_grouper` module clusters nearby figures, decides per cluster whether it came from ONE embedded PDF image (→ merge), computes the merged bbox (union + caption strip below), and crops that region from the page raster. Extraction and a backfill script call it. The renderer is unchanged (a merged figure is just an `illustration`). Plan B (coordinate grid for distinct-image clusters) is separate.

**Tech Stack:** Python 3, pytest, Pillow (PIL), PyMuPDF (fitz). Backend `apps/break_the_barriers/backend`, tests `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-07-figure-group-merge-design.md` (this plan implements the **merge-image** path only; `decide_mode == "grid"` clusters are LEFT UNCHANGED here and handled in Plan B).

## File Structure

- Create `app/services/figure_grouper.py` — pure helpers: `cluster_figures`, `decide_mode`, `group_merge_bbox`, `plan_merge_groups`; + I/O `crop_group_region`.
- Modify `app/services/extractor.py` — after building `figures`, apply merge groups.
- Create `scripts/merge_figure_groups.py` — backfill for already-extracted docs.
- Tests: `tests/test_figure_grouper.py`.

**Commands:** test from `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git from repo root `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`. Branch `feat/figure-group-layout` (already checked out — KHÔNG tạo nhánh). Imports `backend.app...`. bbox format is `[x0, y0, w, h]` (top-left + size) for figures/blocks; PDF image bbox is `(x0, y0, x1, y1)`.

---

### Task 1: cluster_figures (proximity clustering)

**Files:**
- Create: `app/services/figure_grouper.py`
- Test: `tests/test_figure_grouper.py`

- [ ] **Step 1: Write failing tests** — create `tests/test_figure_grouper.py`:

```python
from backend.app.services.figure_grouper import cluster_figures


def test_three_same_row_figures_cluster():
    # 3 portraits in a row, small gaps → one cluster of 3
    bboxes = [[143, 153, 91, 100], [249, 153, 91, 100], [358, 153, 91, 100]]
    assert cluster_figures(bboxes) == [[0, 1, 2]]


def test_far_apart_figures_do_not_cluster():
    bboxes = [[40, 40, 80, 80], [400, 600, 80, 80]]
    assert cluster_figures(bboxes) == []


def test_two_by_two_grid_clusters():
    bboxes = [[40, 40, 80, 80], [140, 40, 80, 80],
              [40, 140, 80, 80], [140, 140, 80, 80]]
    assert cluster_figures(bboxes) == [[0, 1, 2, 3]]
```

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/pytest tests/test_figure_grouper.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** — create `app/services/figure_grouper.py`:

```python
"""Group figures that a PDF split into several crops back into a faithful unit.

Pure geometry helpers (cluster, decide mode, merged bbox) + a raster crop. bbox is
[x0, y0, w, h] for figures/blocks; PDF embedded-image bbox is (x0, y0, x1, y1)."""
from __future__ import annotations
from typing import List


def _inflate(bbox, frac: float):
    x0, y0, w, h = bbox
    dx, dy = w * frac, h * frac
    return (x0 - dx, y0 - dy, x0 + w + dx, y0 + h + dy)


def _intersects(a, b) -> bool:   # a, b = (x0, y0, x1, y1)
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def cluster_figures(bboxes: List[list], inflate: float = 0.3) -> List[List[int]]:
    """Cluster figures whose bboxes (each inflated by `inflate`) intersect, by
    transitive closure. Returns sorted index lists for clusters of >= 2 figures."""
    n = len(bboxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    inf = [_inflate(b, inflate) for b in bboxes]
    for i in range(n):
        for j in range(i + 1, n):
            if _intersects(inf[i], inf[j]):
                parent[find(i)] = find(j)
    groups: dict = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values() if len(g) >= 2]
```

- [ ] **Step 4: Run, confirm PASS** — `.venv/bin/pytest tests/test_figure_grouper.py -q` → 3 pass.

- [ ] **Step 5: Commit** (from repo root)

```bash
git add apps/break_the_barriers/backend/app/services/figure_grouper.py \
        apps/break_the_barriers/backend/tests/test_figure_grouper.py
git commit -m "feat(figgroup): cluster_figures — proximity clustering of split figures"
```

---

### Task 2: decide_mode + group_merge_bbox

**Files:**
- Modify: `app/services/figure_grouper.py`
- Test: `tests/test_figure_grouper.py` (bổ sung)

- [ ] **Step 1: Append failing tests** to `tests/test_figure_grouper.py`:

```python
from backend.app.services.figure_grouper import decide_mode, group_merge_bbox


def test_decide_mode_merge_when_inside_one_pdf_image():
    cluster = [143, 153, 306, 100]                  # union of the 3 portraits
    pdf_imgs = [(129, 140, 467, 285)]               # one embedded image covering it
    assert decide_mode(cluster, pdf_imgs) == "merge"


def test_decide_mode_grid_when_not_in_one_image():
    cluster = [40, 40, 400, 80]
    pdf_imgs = [(40, 40, 120, 120), (300, 40, 380, 120)]   # two separate images
    assert decide_mode(cluster, pdf_imgs) == "grid"


def test_group_merge_bbox_extends_down_to_caption_block():
    members = [[143, 153, 91, 100], [358, 153, 91, 100]]   # union y 153..253
    blocks = [[221, 288, 154, 12]]                          # caption-ish block below
    bb = group_merge_bbox(members, blocks)
    # extends below union bottom (253) toward the block (288) but stops above it
    assert bb[0] == 143 and bb[1] == 153
    assert 253 < bb[1] + bb[3] <= 288


def test_group_merge_bbox_default_extension_without_block():
    members = [[100, 100, 80, 100]]                         # union h=100
    bb = group_merge_bbox(members, [])
    assert abs((bb[1] + bb[3]) - (200 + 0.35 * 100)) < 0.01  # +35% of group height
```

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/pytest tests/test_figure_grouper.py -k "decide or merge_bbox" -q` → FAIL.

- [ ] **Step 3: Implement** — append to `app/services/figure_grouper.py`:

```python
def decide_mode(cluster_bbox, pdf_image_bboxes, tol: float = 2.0) -> str:
    """`merge` if some embedded PDF image fully covers the cluster (it was one image
    split into crops); otherwise `grid` (distinct images — handled by Plan B)."""
    x0, y0, w, h = cluster_bbox
    x1, y1 = x0 + w, y0 + h
    for (ix0, iy0, ix1, iy1) in pdf_image_bboxes:
        if ix0 - tol <= x0 and iy0 - tol <= y0 and ix1 + tol >= x1 and iy1 + tol >= y1:
            return "merge"
    return "grid"


def group_merge_bbox(member_bboxes, block_bboxes,
                     default_frac: float = 0.35, cap_frac: float = 0.5):
    """Union of the members, extended downward to capture a baked caption strip:
    down to just above the nearest text block below (x-overlapping), capped at
    +cap_frac of group height; if none, +default_frac. Returns [x0, y0, w, h]."""
    x0 = min(b[0] for b in member_bboxes)
    y0 = min(b[1] for b in member_bboxes)
    x1 = max(b[0] + b[2] for b in member_bboxes)
    y1 = max(b[1] + b[3] for b in member_bboxes)
    gh = y1 - y0
    belows = [b[1] for b in block_bboxes
              if b[1] >= y1 and x0 <= (b[0] + b[2] / 2) <= x1]
    if belows:
        new_y1 = max(y1, min(min(belows), y1 + cap_frac * gh) - 2.0)
    else:
        new_y1 = y1 + default_frac * gh
    return [x0, y0, x1 - x0, new_y1 - y0]
```

- [ ] **Step 4: Run, confirm PASS** — `.venv/bin/pytest tests/test_figure_grouper.py -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/break_the_barriers/backend/app/services/figure_grouper.py \
        apps/break_the_barriers/backend/tests/test_figure_grouper.py
git commit -m "feat(figgroup): decide_mode (merge vs grid) + group_merge_bbox (caption-aware)"
```

---

### Task 3: plan_merge_groups + crop_group_region

**Files:**
- Modify: `app/services/figure_grouper.py`
- Test: `tests/test_figure_grouper.py` (bổ sung)

- [ ] **Step 1: Append failing tests** to `tests/test_figure_grouper.py`:

```python
from PIL import Image
from backend.app.services.figure_grouper import plan_merge_groups, crop_group_region


def test_plan_merge_groups_returns_merge_clusters_only():
    fig_bboxes = [[143, 153, 91, 100], [249, 153, 91, 100], [358, 153, 91, 100]]
    block_bboxes = [[221, 288, 154, 12]]
    pdf_imgs = [(129, 140, 467, 285)]
    plans = plan_merge_groups(fig_bboxes, block_bboxes, pdf_imgs)
    assert len(plans) == 1
    assert plans[0]["members"] == [0, 1, 2]
    assert plans[0]["bbox"][0] == 143 and plans[0]["bbox"][1] == 153


def test_plan_merge_groups_skips_grid_clusters():
    fig_bboxes = [[40, 40, 80, 80], [140, 40, 80, 80]]      # adjacent → cluster
    pdf_imgs = [(40, 40, 120, 120), (140, 40, 220, 120)]    # but two separate images
    assert plan_merge_groups(fig_bboxes, [], pdf_imgs) == []


def test_crop_group_region_scales_to_raster_pixels(tmp_path):
    src = tmp_path / "page.png"
    Image.new("RGB", (600, 800), (10, 20, 30)).save(src)   # 2x of a 300x400 page
    crop = crop_group_region(Image.open(src), [10, 20, 30, 40], 300.0, 400.0)
    assert crop.size == (60, 80)     # 30*2 x 40*2
```

- [ ] **Step 2: Run, confirm FAIL** — `.venv/bin/pytest tests/test_figure_grouper.py -k "plan_merge or crop_group" -q` → FAIL.

- [ ] **Step 3: Implement** — append to `app/services/figure_grouper.py`:

```python
def plan_merge_groups(fig_bboxes, block_bboxes, pdf_image_bboxes):
    """For each figure cluster decided `merge`, return {"members": [idx...],
    "bbox": merged_bbox}. `grid` clusters are skipped (Plan B)."""
    out = []
    for members in cluster_figures(fig_bboxes):
        mb = [fig_bboxes[i] for i in members]
        x0 = min(b[0] for b in mb); y0 = min(b[1] for b in mb)
        x1 = max(b[0] + b[2] for b in mb); y1 = max(b[1] + b[3] for b in mb)
        if decide_mode([x0, y0, x1 - x0, y1 - y0], pdf_image_bboxes) == "merge":
            out.append({"members": members,
                        "bbox": group_merge_bbox(mb, block_bboxes)})
    return out


def crop_group_region(img, bbox, page_w: float, page_h: float):
    """Crop region `bbox` (page units) from a PIL raster `img`, scaling page→pixels."""
    sx, sy = img.width / page_w, img.height / page_h
    x0, y0, w, h = bbox
    box = (int(x0 * sx), int(y0 * sy), int((x0 + w) * sx), int((y0 + h) * sy))
    return img.crop(box)
```

- [ ] **Step 4: Run, confirm PASS** — `.venv/bin/pytest tests/test_figure_grouper.py -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/break_the_barriers/backend/app/services/figure_grouper.py \
        apps/break_the_barriers/backend/tests/test_figure_grouper.py
git commit -m "feat(figgroup): plan_merge_groups + crop_group_region"
```

---

### Task 4: Wire merge into extraction

**Files:**
- Modify: `app/services/extractor.py` (after the figure-build loop, ~line 473)

- [ ] **Step 1: Implement.** In `app/services/extractor.py`, immediately AFTER the figure loop block that ends with `figures.append(_fig)` / its `except`, and BEFORE the `boxes = {}` line, insert:

```python
            # Merge figures that a PDF split from ONE embedded image (e.g. a row of
            # portraits) back into a single faithful crop — restores row layout and
            # baked captions. Distinct-image clusters are left for the grid path.
            if pil_img is not None and page_size is not None and len(figures) >= 2:
                try:
                    import fitz
                    from backend.app.services.figure_grouper import (
                        plan_merge_groups, crop_group_region)
                    _pdoc = fitz.open(str(pdf_path))
                    _imgbb = [im["bbox"] for im in _pdoc[page_no - 1].get_image_info()]
                    _pdoc.close()
                    _figbb = [list(f.bbox) for f in figures]
                    _blkbb = [list(b["bbox"]) for b in blocks]
                    _plans = plan_merge_groups(_figbb, _blkbb, _imgbb)
                    if _plans:
                        _merged_idx: set = set()
                        _new: list = []
                        for _gi, _plan in enumerate(_plans, start=1):
                            _merged_idx.update(_plan["members"])
                            _gname = f"{doc_id}-{page_no}-figgroup{_gi}.png"
                            _crop = crop_group_region(
                                pil_img, _plan["bbox"], page_size.width, page_size.height)
                            _crop.save(os.path.join(output_dir, _gname))
                            _new.append(Figure(bbox=_plan["bbox"], img=_gname,
                                               kind="illustration"))
                        figures = [f for _k, f in enumerate(figures)
                                   if _k not in _merged_idx] + _new
                except Exception as _e:
                    logger.warning(f"Figure grouping failed p{page_no}: {_e}")
```

- [ ] **Step 2: Sanity import check** — run from `apps/break_the_barriers/backend`:

`.venv/bin/python -c "import backend.app.services.extractor"`
Expected: no error (module imports cleanly).

- [ ] **Step 3: Regression** — `.venv/bin/pytest tests/test_extractor_pagemodel.py tests/test_figure_grouper.py -q`
Expected: all pass (extraction figure-merge path is guarded; not exercised in unit tests but must not break import/existing tests).

- [ ] **Step 4: Commit**

```bash
git add apps/break_the_barriers/backend/app/services/extractor.py
git commit -m "feat(figgroup): extraction merges split-image figure clusters into one crop"
```

---

### Task 5: Backfill script for existing docs

**Files:**
- Create: `scripts/merge_figure_groups.py`

- [ ] **Step 1: Implement** — create `apps/break_the_barriers/backend/scripts/merge_figure_groups.py`:

```python
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
import fitz
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
    pdf_path = osp.join("data", "raw_pdf", f"{doc_id}.pdf")
    pdoc = fitz.open(pdf_path)

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
        raster = (pm.background or {}).get("image")
        if not raster or not osp.exists(osp.join(out_dir, raster)):
            continue
        imgbb = [im["bbox"] for im in pdoc[r.page_num - 1].get_image_info()]
        figbb = [list(f.bbox) for f in pm.figures]
        blkbb = [list(b.bbox) for b in pm.blocks]
        plans = plan_merge_groups(figbb, blkbb, imgbb)
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
    pdoc.close()
    print(f"Done. merged groups = {merged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Dry-run** — from `apps/break_the_barriers/backend`:

`PYTHONPATH=.. .venv/bin/python scripts/merge_figure_groups.py 2024-wttc-introduction-to-ai --dry-run`
Expected: lists pages with merge groups including `p11` (the 3 portraits), p1/p4/p5/p6/p20/p34.

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/backend/scripts/merge_figure_groups.py
git commit -m "chore(figgroup): backfill script to merge split-image groups in existing docs"
```

---

### Task 6: Run backfill + live verify (controller — manual)

**Files:** none.

- [ ] **Step 1: Run backfill for real** — from `apps/break_the_barriers/backend`:
`PYTHONPATH=.. .venv/bin/python scripts/merge_figure_groups.py 2024-wttc-introduction-to-ai`
Expected: merges groups on p1/p4/p5/p6/p11/p20/p34, prints OK.

- [ ] **Step 2: Verify page 11** — fetch `GET /api/docs/2024-wttc-introduction-to-ai/flow?lang=en`; confirm page 11 now contributes ONE figure (a `figgroup` image) instead of 3 stacked, and the merged crop visually contains the 3 portraits in a row WITH the baked names. Chrome headless screenshot the region; report.

- [ ] **Step 3: Confirm no over-merge** — confirm grid-only clusters (p9, p27, p28, p44) were NOT merged (still separate figures), since they are `decide_mode == "grid"` (Plan B).

---

## Self-Review

**Spec coverage (merge-image path):**
- Cluster detection (proximity, transitive, ≥2) → Task 1 `cluster_figures`. ✓
- Decide merge vs grid by embedded PDF image → Task 2 `decide_mode`. ✓
- Merged bbox = union + caption-strip extension → Task 2 `group_merge_bbox`. ✓
- Compose + raster crop → Task 3 `plan_merge_groups`, `crop_group_region`. ✓
- Extraction produces merged figure replacing members → Task 4. ✓
- Backfill existing docs → Task 5. ✓
- Live verify (p11 merged, grid clusters untouched) → Task 6. ✓
- Renderer unchanged (merged figure is `illustration`) — no task needed. ✓
- `grid` clusters explicitly deferred to Plan B. ✓

**Placeholder scan:** no TBD/TODO; every code step has complete code; commands have expected output. ✓

**Type consistency:**
- bbox `[x0,y0,w,h]` for figures/blocks; PDF image bbox `(x0,y0,x1,y1)` — used consistently across `cluster_figures`, `decide_mode`, `group_merge_bbox`, `plan_merge_groups`, `crop_group_region`. ✓
- `plan_merge_groups(fig_bboxes, block_bboxes, pdf_image_bboxes) -> [{"members","bbox"}]` consumed identically in Task 4 + Task 5. ✓
- `Figure(bbox, img, kind="illustration")` matches the dataclass (bbox, img, clean_img=None, kind="illustration"). ✓
- `crop_group_region(img, bbox, page_w, page_h)` called with PIL image in both extraction and backfill. ✓
