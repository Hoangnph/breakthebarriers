# L3 Text-Overlap Fix (Available-Slot Clamp) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop translated text from overlapping the block below it on reconstructed text-layer pages by bounding each block to its real vertical slot.

**Architecture:** A new pure function `compute_slot_heights` measures, for each text block, the vertical distance to the nearest obstacle below it (another block or a figure whose x-range overlaps). The renderer feeds that slot to the server-side font fitter and emits `min-height` (= original bbox height, so box fills still mask the source) and `max-height` (= slot) CSS on each block. With the existing `overflow:hidden`, the client shrink-to-fit loop finally fires and clips at the slot — no overlap, minimal font shrink, faithful top position.

**Tech Stack:** Python 3, pytest, plain HTML/CSS string rendering (no framework). All work is in `apps/break_the_barriers/backend`.

---

## Spec

`docs/superpowers/specs/2026-06-04-text-overlap-fix-l3-design.md`

## File Structure

- `app/services/text_layer_renderer.py` — add `_x_overlap_frac` + `compute_slot_heights` pure helpers; wire slot into `render_text_layer` (fitter call + CSS bounds).
- `app/services/text_fitter.py` — **no edits**; only the call site changes (`height_growth=1.0`).
- `tests/test_slot_heights.py` — **new**; unit tests for `compute_slot_heights`.
- `tests/test_text_layer_renderer.py` — add assertions that bounds are emitted.

**Note on running tests:** all commands run from `apps/break_the_barriers/backend`. The venv pytest is `.venv/bin/pytest`. Imports use the `backend.app.services...` package path (see existing `tests/test_text_layer_renderer.py`).

---

### Task 1: `compute_slot_heights` pure function

**Files:**
- Modify: `app/services/text_layer_renderer.py` (add helpers near the top, after `_pct`)
- Test: `tests/test_slot_heights.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_slot_heights.py`:

```python
from backend.app.services.page_model import FontSpec, Block, Figure
from backend.app.services.text_layer_renderer import compute_slot_heights


def _blk(span_id, l, t, w, h):
    return Block(span_id=span_id, role="body", bbox=[l, t, w, h], text="x",
                 font=FontSpec(11, 400, False, "#000", "left", "sans"))


def _fig(l, t, w, h):
    return Figure(bbox=[l, t, w, h], img="f.png")


def test_single_block_slot_reaches_page_bottom():
    slots = compute_slot_heights([_blk("s1", 72, 100, 200, 50)], [], page_h=842.0)
    assert slots["s1"] == 742.0  # 842 - 100


def test_stacked_blocks_clip_to_next_top():
    blocks = [_blk("s1", 72, 100, 200, 50), _blk("s2", 72, 200, 200, 50)]
    slots = compute_slot_heights(blocks, [], page_h=842.0)
    assert slots["s1"] == 100.0   # 200 - 100 (next block top)
    assert slots["s2"] == 642.0   # 842 - 200 (page bottom)


def test_side_by_side_blocks_do_not_constrain_each_other():
    # b1 left column (50..250), b2 right column (300..500): no x-overlap.
    blocks = [_blk("s1", 50, 100, 200, 50), _blk("s2", 300, 300, 200, 50)]
    slots = compute_slot_heights(blocks, [], page_h=842.0)
    assert slots["s1"] == 742.0   # not clipped by b2 (different column)
    assert slots["s2"] == 542.0   # 842 - 300


def test_figure_below_clips_slot():
    block = _blk("s1", 72, 100, 200, 50)
    fig = _fig(72, 300, 200, 150)
    slots = compute_slot_heights([block], [fig], page_h=842.0)
    assert slots["s1"] == 200.0   # 300 (figure top) - 100


def test_preexisting_overlap_keeps_original_height():
    # b2 top (150) sits inside b1 (100..200): slot must not drop below b1's height.
    blocks = [_blk("s1", 72, 100, 200, 100), _blk("s2", 72, 150, 200, 50)]
    slots = compute_slot_heights(blocks, [], page_h=842.0)
    assert slots["s1"] == 100.0   # max(h=100, 150-100=50) == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_slot_heights.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_slot_heights'`

- [ ] **Step 3: Implement the helpers**

In `app/services/text_layer_renderer.py`, immediately after the existing `_pct`
function (currently ending at line 46), add:

```python
def _x_overlap_frac(a: list, b: list) -> float:
    """Fraction of the narrower box's width covered by the horizontal overlap
    of two bboxes [l, t, w, h]. 0.0 means no horizontal overlap."""
    al, aw = a[0], a[2]
    bl, bw = b[0], b[2]
    ov = min(al + aw, bl + bw) - max(al, bl)
    if ov <= 0:
        return 0.0
    return ov / max(1.0, min(aw, bw))


def compute_slot_heights(blocks: list, figures: list, page_h: float,
                         *, overlap_frac: float = 0.25) -> dict:
    """For each block, the vertical slot from its top down to the nearest
    obstacle below it (a block or figure whose x-range overlaps by more than
    `overlap_frac`), floored at the block's own height. Points in, points out."""
    obstacles = [fig.bbox for fig in figures] + [b.bbox for b in blocks]
    slots: dict = {}
    for blk in blocks:
        l, t, w, h = blk.bbox
        nearest = float(page_h)
        for ob in obstacles:
            if ob is blk.bbox:
                continue
            ot = ob[1]
            if ot <= t:
                continue
            if _x_overlap_frac(blk.bbox, ob) < overlap_frac:
                continue
            nearest = min(nearest, ot)
        slots[blk.span_id] = max(h, nearest - t)
    return slots
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_slot_heights.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_slot_heights.py
git commit -m "feat(l3): compute_slot_heights — vertical slot to nearest obstacle"
```

---

### Task 2: Wire slots into `render_text_layer` (CSS bounds + fitter)

**Files:**
- Modify: `app/services/text_layer_renderer.py` (the `render_text_layer` block loop, currently lines 69-96)
- Test: `tests/test_text_layer_renderer.py` (add assertions)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_text_layer_renderer.py`:

```python
def _two_block_model():
    return PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#ffffff", "image": None},
        blocks=[
            Block(span_id="s1", role="body", bbox=[72, 100, 200, 50],
                  text="A", font=FontSpec(11, 400, False, "#000", "left", "sans")),
            Block(span_id="s2", role="body", bbox=[72, 200, 200, 50],
                  text="B", font=FontSpec(11, 400, False, "#000", "left", "sans")),
        ],
        figures=[],
    )


def test_render_emits_min_and_max_height_bounds():
    html = render_text_layer(_two_block_model(), {"s1": "Một", "s2": "Hai"},
                             image_url_base="http://api/assets")
    # Two blocks, each bounded.
    assert html.count("min-height:") == 2
    assert html.count("max-height:") == 2


def test_render_max_height_uses_slot_not_bbox():
    # s1 slot = next-top(200) - top(100) = 100pt -> 100/842*100 = 11.876%,
    # which is larger than its bbox-height bound 50/842*100 = 5.938%.
    html = render_text_layer(_two_block_model(), {"s1": "Một", "s2": "Hai"},
                             image_url_base="http://api/assets")
    assert "max-height:11.876%" in html   # slot-based, not 5.938%
    assert "min-height:5.938%" in html     # bbox-height floor
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_text_layer_renderer.py -v`
Expected: FAIL — `min-height:`/`max-height:` not found in output.

- [ ] **Step 3: Add the import-free slot call and edit the block loop**

In `render_text_layer`, just before the `for blk in model.blocks:` loop
(currently line 69), insert:

```python
    slots = compute_slot_heights(model.blocks, model.figures, ph)
```

Then, inside the loop, replace the current fit + emit code (currently lines
80-96) so that it uses `slot_h`:

```python
        slot_h = slots.get(blk.span_id, h)
        base = (f.size if f and f.size else max(8.0, h * 0.8))
        size = fit_font_size(text, w, slot_h, max_size=base, min_size=6.0,
                             height_growth=1.0)
        box = blk.box or None
        box_css = ""
        if box and box.get("fill"):
            if box.get("mode") == "scrim":
                box_css = f"background:{box['fill']};padding:0 2px;"
            else:
                box_css = f"background:{box['fill']};"
        parts.append(
            f'<div class="tl-text" data-fit="1" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;'
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(slot_h, ph):.3f}%;'
            f'font-family:{family};font-size:{size:.1f}px;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};{box_css}">'
            f'{html_lib.escape(text)}</div>'
        )
```

- [ ] **Step 4: Run the renderer tests to verify they pass**

Run: `.venv/bin/pytest tests/test_text_layer_renderer.py -v`
Expected: PASS (all tests, including the two new ones)

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `.venv/bin/pytest tests/ -q`
Expected: PASS — no failures. (Pay attention to `test_text_layer_l2.py`,
`test_page_renderer.py`, `test_preview_pagemodel.py`, `test_text_fitter.py`.)

- [ ] **Step 6: Commit**

```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_text_layer_renderer.py
git commit -m "feat(l3): bound .tl-text by real slot (min/max-height) to stop overlap"
```

---

### Task 3: Manual verification on the real Next.js preview

**Files:** none (verification only).

- [ ] **Step 1: Confirm CSS already clips.** Open `app/services/text_layer_renderer.py`
  and verify `.tl-text` in `_CSS` still has `overflow: hidden;` (line ~40) and the
  client loop still contains `while(d.scrollHeight>d.clientHeight+1` (the
  `btb-fit` script). No code change — just confirm the two bounds now make that
  loop effective.

- [ ] **Step 2: Start backend (reload) and the Next.js frontend.**

```bash
# Terminal 1
cd apps/break_the_barriers/backend && .venv/bin/uvicorn app.main:app --reload --port 8000
# Terminal 2
cd apps/break_the_barriers/frontend && npm run dev   # Next.js on :3000
```

- [ ] **Step 3: Open a previously-broken text page** at
  `http://localhost:3000/books/<id>/preview` (the page the user reported with
  overlapping Vietnamese text). Confirm: no text overlaps the block below; long
  paragraphs grow into the whitespace gap rather than colliding; headings stay
  readable (not shrunk to tiny). Note the doc/page id used so it is reproducible.

- [ ] **Step 4: Spot-check a dense page** (small inter-block gaps) to confirm font
  shrink kicks in only where the slot is genuinely tight, and a sparse page to
  confirm minimal/no shrink.

---

## Self-Review

**Spec coverage:**
- "compute_slot_heights pure function" with x-overlap + nearest-below + `max(h,…)` guard, figures as obstacles → Task 1. ✓
- "min-height = bbox_h, max-height = slot" CSS bounds → Task 2 Step 3. ✓
- "feed slot to fit_font_size with height_growth=1.0" → Task 2 Step 3. ✓
- "client loop unchanged, just works" → Task 3 Step 1 (confirm, no edit). ✓
- "no DB/extraction/model.json change; fitter signature unchanged" → only call site + renderer touched. ✓
- Testing matrix (single / stacked / side-by-side / figure-below / pre-existing overlap; renderer bounds) → Task 1 + Task 2 tests. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `compute_slot_heights(blocks, figures, page_h, *, overlap_frac=0.25) -> dict` keyed by `span_id`; called in Task 2 as `compute_slot_heights(model.blocks, model.figures, ph)` and read via `slots.get(blk.span_id, h)`. `fit_font_size(text, w, slot_h, max_size=, min_size=, height_growth=1.0)` matches the existing signature in `text_fitter.py`. ✓
