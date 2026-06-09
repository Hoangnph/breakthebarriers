# Faithful Figures in Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa lỗi figure ở đường render original → HTML (flow): căn lề figure (#3), không mất figure (#1), và giữ layout vùng thiết kế dạng hội thoại bằng cách crop thành 1 ảnh (#4).

**Architecture:** Đẩy phần nặng về extraction + backfill (giống `figure_grouper`), giữ `flow_model` thuần và `flow_renderer` đổi tối thiểu. Thêm module thuần `design_region.py` (suy align + phát hiện vùng thiết kế), mở rộng `Figure`/`FlowElement` với field `align`, và một backfill script áp dụng cho doc đã extract.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PyMuPDF/Pillow (crop), pytest. Spec: `docs/superpowers/specs/2026-06-09-faithful-figures-flow-design.md`. PDF kiểm chứng: `apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf`. Doc mẫu đã extract: `data/extracted_html/2024-wttc-introduction-to-ai/`.

**Working dir cho mọi lệnh:** `apps/break_the_barriers/backend`. Chạy test: `.venv/bin/pytest`.

---

## File Structure

| File | Trách nhiệm | Hành động |
|------|-------------|-----------|
| `app/services/design_region.py` | `infer_figure_align`, `Region`, `detect_design_regions` (thuần, list-based) | Create |
| `app/services/page_model.py` | thêm `Figure.align` + (de)serialize | Modify |
| `app/services/flow_model.py` | thêm `FlowElement.align` + truyền align khi phát figure | Modify |
| `app/services/flow_renderer.py` | CSS + HTML căn lề figure | Modify |
| `app/services/extractor.py` | set align + crop design-region khi extract | Modify |
| `scripts/backfill_design_regions.py` | áp dụng align + region cho doc đã extract | Create |
| `tests/test_design_region.py` | unit cho design_region | Create |
| `tests/test_flow_figures.py` | unit cho flow_model/flow_renderer (align, no-drop) | Create |

**Lưu ý interface (khoá tên):** `infer_figure_align(bbox, page_w, tol_frac=0.08) -> str`; `detect_design_regions(fig_bboxes, blocks, page_w, page_h, min_icons=2, min_span_frac=0.2) -> List[Region]` với `blocks = List[Tuple[span_id, bbox]]`; `Region(bbox, figure_idx: set[int], block_ids: set[str])`. bbox luôn `[x0, y0, w, h]` (điểm).

---

## Task 1: Helper `infer_figure_align` + module `design_region.py`

**Files:**
- Create: `app/services/design_region.py`
- Test: `tests/test_design_region.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_region.py
from backend.app.services.design_region import infer_figure_align


def test_align_center_symmetric_margins():
    # p7-like figure on a 595-wide page: left 158 ≈ right 155 → center
    assert infer_figure_align([158, 53, 282, 273], 595) == "center"


def test_align_left_when_left_margin_small():
    assert infer_figure_align([40, 0, 200, 100], 595) == "left"


def test_align_right_when_pushed_right():
    # left 355 >> right 40 → right
    assert infer_figure_align([355, 0, 200, 100], 595) == "right"


def test_align_left_when_no_page_width():
    assert infer_figure_align([10, 0, 50, 50], 0) == "left"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_design_region.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.app.services.design_region`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/design_region.py
"""Detect composite design regions (e.g. chat: avatar icons interleaved with text)
that must render as one faithful raster crop, not decomposed into scattered figures +
reflowed text — and infer per-figure horizontal alignment. Pure geometry; the actual
cropping/IO happens in the caller (extractor / backfill). bbox = [x0, y0, w, h] pts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Set, Tuple

from backend.app.services.figure_grouper import cluster_figures  # noqa: F401 (used later)

_ICON_MAX_FRAC = 0.15      # icon: small in BOTH dims relative to the page


def infer_figure_align(bbox, page_w: float, tol_frac: float = 0.08) -> str:
    """Infer a figure's horizontal alignment from its left/right margins on the page.
    `center` when margins are near-equal; `right` when clearly pushed right; else left."""
    if not page_w:
        return "left"
    left = bbox[0]
    right = page_w - (bbox[0] + bbox[2])
    if left <= 0 or right <= 0:
        return "left"
    if abs(left - right) <= tol_frac * page_w:
        return "center"
    if left > 2 * right:
        return "right"
    return "left"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_design_region.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/design_region.py tests/test_design_region.py
git commit -m "feat(figalign): infer_figure_align helper (design_region module)"
```

---

## Task 2: `Figure.align` field + serialization

**Files:**
- Modify: `app/services/page_model.py:29-35` (Figure), `:74-77` (from_dict)
- Test: `tests/test_design_region.py`

- [ ] **Step 1: Write the failing test (append to tests/test_design_region.py)**

```python
def test_figure_align_roundtrip():
    from backend.app.services.page_model import PageModel, Figure
    pm = PageModel(page_w=1, page_h=1, kind="text", background={},
                   blocks=[], figures=[Figure(bbox=[1, 2, 3, 4], img="a.png", align="center")])
    pm2 = PageModel.from_json(pm.to_json())
    assert pm2.figures[0].align == "center"


def test_figure_align_defaults_left_on_old_json():
    import json
    from backend.app.services.page_model import PageModel
    j = json.dumps({"page_w": 1, "page_h": 1, "kind": "text", "background": {},
                    "blocks": [], "figures": [{"bbox": [1, 2, 3, 4], "img": "a.png"}]})
    assert PageModel.from_json(j).figures[0].align == "left"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_design_region.py -k align -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'align'`

- [ ] **Step 3: Implement — add field + from_dict**

In `app/services/page_model.py`, change the `Figure` dataclass:

```python
@dataclass
class Figure:
    bbox: List[float]      # [l, t, w, h] top-left points
    img: str               # filename only
    clean_img: Optional[str] = None   # AI-cleaned (text-removed) variant filename
    kind: str = "illustration"        # banner | icon | illustration | content-region
    align: str = "left"               # left | center | right (flow horizontal align)
```

In `from_dict`, change the figures comprehension:

```python
        figures = [Figure(bbox=list(f["bbox"]), img=f["img"],
                          clean_img=f.get("clean_img"),
                          kind=f.get("kind", "illustration"),
                          align=f.get("align", "left"))
                   for f in d.get("figures", [])]
```

(`to_dict` uses `asdict(f)` so `align` serializes automatically.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_design_region.py -k align -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/page_model.py tests/test_design_region.py
git commit -m "feat(figalign): Figure.align field + JSON (de)serialization"
```

---

## Task 3: `Region` + `detect_design_regions`

**Files:**
- Modify: `app/services/design_region.py`
- Test: `tests/test_design_region.py`

- [ ] **Step 1: Write the failing test (append)**

```python
def test_detect_chat_region_groups_icons_and_text():
    # 3 avatar icons spanning a tall band + 2 body blocks interleaved → 1 region
    figs = [[71, 90, 31, 31], [493, 338, 31, 31], [66, 595, 31, 31]]
    blocks = [("s1", [120, 100, 300, 20]), ("s2", [120, 400, 300, 20])]
    regs = detect_design_regions(figs, blocks, 595, 842)
    assert len(regs) == 1
    assert regs[0].figure_idx == {0, 1, 2}
    assert {"s1", "s2"} <= regs[0].block_ids
    # union bbox covers from top icon to bottom icon (with padding)
    assert regs[0].bbox[1] <= 90 and regs[0].bbox[1] + regs[0].bbox[3] >= 626


def test_no_region_on_plain_text_page():
    blocks = [("s1", [120, 100, 300, 20]), ("s2", [120, 200, 300, 20])]
    assert detect_design_regions([], blocks, 595, 842) == []


def test_no_region_with_single_icon():
    figs = [[71, 90, 31, 31]]
    assert detect_design_regions(figs, [("s1", [120, 300, 300, 20])], 595, 842) == []


def test_no_region_when_icons_span_too_short():
    # two icons very close together (span ~51 pt << 0.2*842) → not a design band
    figs = [[71, 90, 31, 31], [71, 110, 31, 31]]
    assert detect_design_regions(figs, [("s1", [120, 95, 300, 20])], 595, 842) == []
```

(Add `from backend.app.services.design_region import detect_design_regions, Region` at top of the test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_design_region.py -k region -v`
Expected: FAIL — `ImportError: cannot import name 'detect_design_regions'`

- [ ] **Step 3: Implement — append to `app/services/design_region.py`**

```python
@dataclass
class Region:
    bbox: List[float]                       # [x0, y0, w, h] union (page points)
    figure_idx: Set[int] = field(default_factory=set)
    block_ids: Set[str] = field(default_factory=set)


def _is_icon(bbox, page_w: float, page_h: float) -> bool:
    return bool(page_w and page_h
                and bbox[2] < _ICON_MAX_FRAC * page_w
                and bbox[3] < _ICON_MAX_FRAC * page_h)


def detect_design_regions(fig_bboxes, blocks, page_w: float, page_h: float,
                          min_icons: int = 2, min_span_frac: float = 0.2) -> List["Region"]:
    """Find composite design regions: pages whose layout is built from >= min_icons
    icon-figures spanning a tall vertical band with body text interleaved (chat-like).
    Such a band must be one faithful crop. Returns at most one region per page.

    `fig_bboxes`: List[[x0,y0,w,h]]. `blocks`: List[(span_id, [x0,y0,w,h])]."""
    if not page_h:
        return []
    icon_idx = [i for i, b in enumerate(fig_bboxes) if _is_icon(b, page_w, page_h)]
    if len(icon_idx) < min_icons:
        return []
    icon_bb = [fig_bboxes[i] for i in icon_idx]
    top = min(b[1] for b in icon_bb)
    bot = max(b[1] + b[3] for b in icon_bb)
    if (bot - top) < min_span_frac * page_h:
        return []
    member_figs: Set[int] = {i for i, b in enumerate(fig_bboxes)
                             if top <= (b[1] + b[3] / 2) <= bot}
    member_figs |= set(icon_idx)
    band_blocks = [(sid, bb) for sid, bb in blocks
                   if top <= (bb[1] + bb[3] / 2) <= bot]
    if not band_blocks:
        return []
    allbb = [fig_bboxes[i] for i in member_figs] + [bb for _sid, bb in band_blocks]
    x0 = min(b[0] for b in allbb)
    y0 = min(b[1] for b in allbb)
    x1 = max(b[0] + b[2] for b in allbb)
    y1 = max(b[1] + b[3] for b in allbb)
    pad = 6.0
    return [Region(
        bbox=[max(0.0, x0 - pad), max(0.0, y0 - pad),
              (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad],
        figure_idx=set(member_figs),
        block_ids={sid for sid, _bb in band_blocks},
    )]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_design_region.py -v`
Expected: PASS (all design_region tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/design_region.py tests/test_design_region.py
git commit -m "feat(figregion): detect_design_regions — chat-like composite band detection"
```

---

## Task 4: `FlowElement.align` + flow_model passthrough

**Files:**
- Modify: `app/services/flow_model.py:62-71` (FlowElement), `:233` and `:226-227` (figure emission)
- Test: `tests/test_flow_figures.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_figures.py
from backend.app.services.page_model import PageModel, Figure
from backend.app.services.flow_model import build_document_flow


def _page(figs, blocks=None):
    return PageModel(page_w=595, page_h=842, kind="mixed",
                     background={"color": "#fff", "image": None},
                     blocks=blocks or [], figures=figs,
                     page_class="text", cover="none", page_num=1)


def test_flow_passes_figure_align():
    pm = _page([Figure(bbox=[158, 53, 282, 273], img="f.png", align="center")])
    flow = build_document_flow([pm])
    figs = [e for e in flow if e.kind == "figure"]
    assert figs and figs[0].align == "center"


def test_flow_does_not_drop_figures():
    pm = _page([Figure(bbox=[60, 60, 120, 120], img="a.png"),
                Figure(bbox=[300, 60, 120, 120], img="b.png")])
    flow = build_document_flow([pm])
    srcs = {e.src for e in flow if e.kind == "figure"}
    assert srcs == {"a.png", "b.png"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_figures.py -v`
Expected: FAIL — `test_flow_passes_figure_align` (FlowElement has no `align`, or align defaults wrong)

- [ ] **Step 3: Implement**

In `app/services/flow_model.py`, add `align` to `FlowElement`:

```python
@dataclass
class FlowElement:
    kind: str                      # heading|paragraph|caption|list|figure|image_block
    span_id: Optional[str] = None
    level: int = 0                 # heading: 1..3
    src: Optional[str] = None      # figure/image_block filename
    overlay: Optional[dict] = None
    align: str = "left"            # figure horizontal align: left|center|right
```

(The `overlay` comment block above it stays; just add the `align` line after `overlay`.)

In the standalone-figure emission (currently `flow.append(FlowElement(kind="figure", src=obj.img))` inside the `items` loop), add align:

```python
            if tag == "fig":
                # Standalone (non-banner) figures keep their ORIGINAL image — never
                # the AI-cleaned one, which can lose content (faces, labels).
                flow.append(FlowElement(kind="figure", src=obj.img,
                                        align=getattr(obj, "align", "left")))
                continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_flow_figures.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/flow_model.py tests/test_flow_figures.py
git commit -m "feat(flow): carry figure align onto FlowElement"
```

---

## Task 5: flow_renderer alignment (CSS + HTML)

**Files:**
- Modify: `app/services/flow_renderer.py:26` (`.fl-fig` CSS), `:151-154` (figure branch)
- Test: `tests/test_flow_figures.py`

- [ ] **Step 1: Write the failing test (append)**

```python
from backend.app.services.flow_model import FlowElement
from backend.app.services.flow_renderer import render_flow_html


def test_renderer_centers_figure():
    html = render_flow_html(
        [FlowElement(kind="figure", src="f.png", align="center")], {}, "http://x/assets")
    assert "text-align:center" in html
    assert "http://x/assets/f.png" in html


def test_renderer_sanitizes_bad_align():
    html = render_flow_html(
        [FlowElement(kind="figure", src="f.png", align="evil;}")], {}, "http://x/assets")
    assert "evil" not in html
    assert "text-align:left" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_flow_figures.py -k renderer -v`
Expected: FAIL — no `text-align:center` in output

- [ ] **Step 3: Implement**

In `app/services/flow_renderer.py`, change the `.fl-fig` rule (line ~26) from `display: block;` to `display: inline-block;`:

```python
.fl-fig { max-width: 100%; height: auto; display: inline-block; }
```

Change the figure branch (the `if el.kind == "figure" and el.src:` block):

```python
        if el.kind == "figure" and el.src:
            ensure_section()
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            align = el.align if el.align in ("left", "center", "right") else "left"
            parts.append(f'<figure style="text-align:{align}">'
                         f'<img class="fl-fig" src="{src}" alt="figure"/></figure>')
            continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_flow_figures.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite (no regressions)**

Run: `.venv/bin/pytest -q`
Expected: PASS (no new failures vs baseline)

- [ ] **Step 6: Commit**

```bash
git add app/services/flow_renderer.py tests/test_flow_figures.py
git commit -m "feat(flow): render figure with inferred horizontal alignment"
```

---

## Task 6: Backfill script `backfill_design_regions.py`

**Files:**
- Create: `scripts/backfill_design_regions.py`

This mirrors `scripts/merge_figure_groups.py` (DB-driven, updates `DBPage.model_json` + the on-disk `*.model.json`). No new unit test — verified end-to-end in Task 8.

- [ ] **Step 1: Create the script**

```python
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
```

- [ ] **Step 2: Smoke-check it imports (dry-run, safe)**

Run: `PYTHONPATH=.. .venv/bin/python scripts/backfill_design_regions.py 2024-wttc-introduction-to-ai --dry-run`
Expected: prints per-page region counts (e.g. `p26: 1 region(s) (dry-run)`) and `Done. align updated = N, regions = M`. If it prints `Done. align updated = 0, regions = 0`, the doc is not in Postgres — re-extract it via the API first (see Task 8 verification).

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_design_regions.py
git commit -m "feat(figregion): backfill script — align + design-region crop for extracted docs"
```

---

## Task 7: Extractor integration (set align + crop region during extraction)

**Files:**
- Modify: `app/services/extractor.py` — insert after the figure-grouping block (after line ~500, before `boxes = {}` at line ~502)

New extractions must produce the same model as backfill: aligned figures and collapsed design regions. This runs on the live extraction path; it is verified end-to-end (Task 8), not via a new unit test (PyMuPDF/docling IO).

- [ ] **Step 1: Insert the integration block**

In `app/services/extractor.py`, immediately AFTER the `Figure grouping failed` try/except block (the one ending at line ~500) and BEFORE `boxes = {}`:

```python
            # ── Faithful figures: per-figure alignment + composite design-region
            # crop (chat-like icon+text bands → one image, kept centered). ──
            if page_size is not None:
                from backend.app.services.design_region import (
                    infer_figure_align, detect_design_regions)
                for _f in figures:
                    _f.align = infer_figure_align(list(_f.bbox), page_size.width)
                if pil_img is not None and figures:
                    try:
                        from backend.app.services.figure_grouper import crop_group_region
                        _figbb = [list(f.bbox) for f in figures]
                        _blk = [(b["span_id"], list(b["bbox"])) for b in blocks]
                        _regs = detect_design_regions(
                            _figbb, _blk, page_size.width, page_size.height)
                        if _regs:
                            _rm_fig: set = set()
                            _rm_blk: set = set()
                            _newr: list = []
                            for _ri, _rg in enumerate(_regs, start=1):
                                _rm_fig.update(_rg.figure_idx)
                                _rm_blk.update(_rg.block_ids)
                                _rname = f"{doc_id}-{page_no}-region{_ri}.png"
                                crop_group_region(
                                    pil_img, _rg.bbox,
                                    page_size.width, page_size.height
                                ).save(os.path.join(output_dir, _rname))
                                _newr.append(Figure(bbox=_rg.bbox, img=_rname,
                                                    kind="content-region", align="center"))
                            figures = [f for _k, f in enumerate(figures)
                                       if _k not in _rm_fig] + _newr
                            blocks = [b for b in blocks
                                      if b["span_id"] not in _rm_blk]
                    except Exception as _e:
                        logger.warning(f"Design-region crop failed p{page_no}: {_e}")
```

(Placed before `boxes`, `model_blocks`, `classify_kind`, `classify_page` — so removed blocks/figures are correctly excluded from box analysis and classification downstream.)

- [ ] **Step 2: Run full suite (no import/logic regressions)**

Run: `.venv/bin/pytest -q`
Expected: PASS (extractor still imports; existing extractor tests unaffected — design-region only triggers on multi-icon pages).

- [ ] **Step 3: Commit**

```bash
git add app/services/extractor.py
git commit -m "feat(extract): set figure align + crop chat-like design regions"
```

---

## Task 8: Verification on the WTTC AI document

**Files:** none (verification only). PDF: `apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf`.

- [ ] **Step 1: Ensure the sample doc is in Postgres**

Run: `PYTHONPATH=.. .venv/bin/python scripts/backfill_design_regions.py 2024-wttc-introduction-to-ai --dry-run`

- If it reports regions on p26/p27/p28 → doc is present, go to Step 2.
- If `align updated = 0, regions = 0` → re-extract via API: start backend (`/start-dev`) and POST the PDF through the upload→extract endpoints (or the project's extraction route) so Task 7 code regenerates the model. Then re-run this dry-run.

- [ ] **Step 2: Apply the backfill (real run)**

Run: `PYTHONPATH=.. .venv/bin/python scripts/backfill_design_regions.py 2024-wttc-introduction-to-ai`
Expected: `*-region1.png` files written for chat pages; `Done. align updated = N (>0), regions = M (>=1)`.

- [ ] **Step 3: Inspect rendered flow**

Start dev servers (`/start-dev`), open `http://localhost:8000/api/docs/2024-wttc-introduction-to-ai/flow?lang=vi` (or via frontend). Confirm:
- **p7**: standalone illustration is centered (not left-aligned). [#3]
- **p26–28**: the AI conversation renders as ONE coherent cropped image (avatars beside bubbles intact), not scattered icons + reflowed text. [#4]
- **No page lost a figure** compared to the original PDF render. [#1]

- [ ] **Step 4: Final full test run**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit any fixture/threshold tweaks made during verification**

If p26–28 over/under-capture, tune `min_icons` / `min_span_frac` in `detect_design_regions`, update the Task 3 tests accordingly, re-run, then:

```bash
git add app/services/design_region.py tests/test_design_region.py
git commit -m "tune(figregion): adjust design-region thresholds from WTTC verification"
```

---

## Self-Review

**Spec coverage:**
- #3 figure centering → Task 1 (infer), Task 2 (field), Task 4 (passthrough), Task 5 (render). ✓
- #1 missing images → Task 4 no-drop test + Task 5 alt; design-region preserves design graphics (Task 3/7/8). ✓
- #4 chat layout → Task 3 (detect), Task 6/7 (crop), Task 8 (verify). ✓
- Backfill for existing docs → Task 6. ✓
- Extraction parity → Task 7. ✓
- Verification on the named PDF → Task 8. ✓
- Out of scope (#2 inline emphasis) → not in plan, deferred to sub-project B. ✓

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `infer_figure_align(bbox, page_w, tol_frac)`, `detect_design_regions(fig_bboxes, blocks, page_w, page_h, min_icons, min_span_frac)`, `Region(bbox, figure_idx, block_ids)`, `Figure.align`, `FlowElement.align`, region crop filename `{doc}-{n}-region{k}.png`, kind `"content-region"` — consistent across Tasks 1–8.
