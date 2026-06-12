# Raster-Page Render (L2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render image/mixed pages with real model fonts + TextFitter + per-block local fill/scrim backgrounds (computed at extraction), via a single unified PageModel renderer — eliminating the opaque-box overlay path for model-based pages.

**Architecture:** A `Block.box` field carries `{mode:"fill"|"scrim", fill}` computed at extraction by `analyze_block_box` (uniform local bg → fill; photo → scrim). `render_text_layer` is generalized to render an optional raster background plus per-block box backgrounds, so it serves text/image/mixed alike; `page_renderer` routes all model kinds to it. `render_overlay_html` stays only for the legacy layout_json fallback.

**Tech Stack:** Python 3.12, Pillow, pytest. Paths relative to `apps/break_the_barriers/backend/`. Git root: `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`.

---

## File Structure

| File | Responsibility | New? |
|---|---|---|
| `app/services/page_model.py` | Add optional `Block.box` field + (de)serialize | Modify |
| `app/services/page_image.py` | `analyze_block_box` (fill vs scrim from raster) | Modify |
| `app/services/text_layer_renderer.py` | Generalize: raster bg + per-block box | Modify |
| `app/services/page_renderer.py` | Route all model kinds → `render_text_layer` | Modify |
| `app/services/extractor.py` | Compute `box` per block → model | Modify |
| `tests/test_block_box.py`, `tests/test_text_layer_l2.py`, `tests/test_page_renderer.py` | Unit | Create/Modify |

---

## Task 1: `Block.box` field

**Files:**
- Modify: `app/services/page_model.py`
- Test: `tests/test_block_box.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_block_box.py
from backend.app.services.page_model import Block, FontSpec, PageModel


def test_block_box_roundtrip():
    b = Block(span_id="s1", role="heading", bbox=[0, 0, 10, 10], text="x",
              font=FontSpec(11, 400, False, "#111", "left", "sans"),
              box={"mode": "scrim", "fill": "rgba(0,0,0,0.45)"})
    m = PageModel(1, 1, "mixed", {"color": "#fff", "image": "p.png"}, [b], [])
    r = PageModel.from_json(m.to_json())
    assert r.blocks[0].box == {"mode": "scrim", "fill": "rgba(0,0,0,0.45)"}


def test_block_box_defaults_none():
    b = Block(span_id="s1", role="body", bbox=[0, 0, 1, 1], text="x", font=None)
    assert b.box is None
    # old-style dict (no "box") deserializes to None
    m = PageModel.from_dict({"page_w": 1, "page_h": 1, "kind": "text",
                             "background": {"color": "#fff", "image": None},
                             "blocks": [{"span_id": "s1", "role": "body",
                                         "bbox": [0, 0, 1, 1], "text": "x", "font": None}],
                             "figures": []})
    assert m.blocks[0].box is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_block_box.py -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'box'`).

- [ ] **Step 3: Add the field**

In `app/services/page_model.py`, in the `Block` dataclass, add `box` as the LAST field with a default (defaults must come last):

```python
@dataclass
class Block:
    span_id: str
    role: str              # heading|body|list|code|table|caption
    bbox: List[float]      # [l, t, w, h] top-left points
    text: str
    font: Optional[FontSpec]
    box: Optional[Dict[str, Any]] = None   # {"mode":"fill"|"scrim","fill": "#rrggbb"|"rgba(...)"} for raster overlay
```

In `PageModel.from_dict`, where each Block is constructed, pass `box`:

```python
            blocks.append(Block(
                span_id=b["span_id"], role=b.get("role", "body"),
                bbox=list(b["bbox"]), text=b.get("text", ""),
                font=FontSpec(**f) if f else None,
                box=b.get("box"),
            ))
```

(`to_dict` already uses `asdict(b)` which includes `box` automatically. `Dict`/`Any` are already imported.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_block_box.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/page_model.py apps/break_the_barriers/backend/tests/test_block_box.py
git commit -m "feat(sp-a.2): PageModel Block.box field for raster overlay backgrounds

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `analyze_block_box`

**Files:**
- Modify: `app/services/page_image.py`
- Test: `tests/test_analyze_block_box.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyze_block_box.py
from PIL import Image
from backend.app.services.page_image import analyze_block_box


def test_uniform_region_returns_fill(tmp_path):
    img = Image.new("RGB", (200, 200), (250, 250, 250))
    p = tmp_path / "u.png"; img.save(p)
    box = analyze_block_box(str(p), [10, 10, 80, 40], 2.0, 2.0)
    assert box["mode"] == "fill"
    assert box["fill"].startswith("#")


def test_dark_photo_region_returns_dark_scrim(tmp_path):
    img = Image.new("RGB", (200, 200), (0, 0, 0))
    for y in range(200):
        for x in range(200):
            img.putpixel((x, y), (0, 0, min(255, y)))   # strong dark→blue gradient
    p = tmp_path / "d.png"; img.save(p)
    box = analyze_block_box(str(p), [0, 0, 100, 100], 2.0, 2.0)
    assert box["mode"] == "scrim"
    assert box["fill"] == "rgba(0,0,0,0.45)"


def test_light_photo_region_returns_light_scrim(tmp_path):
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    for y in range(200):
        for x in range(200):
            img.putpixel((x, y), (255, 255, max(0, 255 - y)))  # bright varied
    p = tmp_path / "l.png"; img.save(p)
    box = analyze_block_box(str(p), [0, 0, 100, 100], 2.0, 2.0)
    assert box["mode"] == "scrim"
    assert box["fill"] == "rgba(255,255,255,0.55)"


def test_missing_file_falls_back_to_fill(tmp_path):
    box = analyze_block_box(str(tmp_path / "nope.png"), [0, 0, 10, 10], 1.0, 1.0)
    assert box["mode"] == "fill"
    assert box["fill"].startswith("#")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_analyze_block_box.py -v`
Expected: FAIL (`ImportError: cannot import name 'analyze_block_box'`).

- [ ] **Step 3: Add the function to `app/services/page_image.py`**

Append (Image + logger already imported; `sample_bg_color` already defined in this file):

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_analyze_block_box.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/page_image.py apps/break_the_barriers/backend/tests/test_analyze_block_box.py
git commit -m "feat(sp-a.2): analyze_block_box (local fill vs scrim from raster)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Generalize `render_text_layer` (raster bg + per-block box)

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_l2.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_text_layer_l2.py
from backend.app.services.page_model import FontSpec, Block, PageModel
from backend.app.services.text_layer_renderer import render_text_layer


def _img_model(box=None):
    return PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#000", "image": "page-2.png"},
        blocks=[Block("s1", "heading", [72, 40, 200, 24], "x",
                      FontSpec(24, 700, False, "#fff", "left", "sans"), box=box)],
        figures=[],
    )


def test_raster_background_rendered_when_image_present():
    html = render_text_layer(_img_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-bg"' in html
    assert "http://api/assets/page-2.png" in html
    assert "DỊCH" in html


def test_block_fill_box_applies_solid_background():
    html = render_text_layer(_img_model({"mode": "fill", "fill": "#ffffff"}),
                             {"s1": "X"}, "http://api/assets")
    # the text div carries the fill colour
    assert "#ffffff" in html


def test_block_scrim_box_applies_rgba_background():
    html = render_text_layer(_img_model({"mode": "scrim", "fill": "rgba(0,0,0,0.45)"}),
                             {"s1": "X"}, "http://api/assets")
    assert "rgba(0,0,0,0.45)" in html


def test_text_page_unchanged_no_raster():
    # background.image None, no box -> behaves like before (no tl-bg)
    m = PageModel(595.0, 842.0, "text", {"color": "#fff", "image": None},
                  [Block("s1", "body", [10, 10, 100, 20], "x",
                         FontSpec(11, 400, False, "#111", "left", "sans"))], [])
    html = render_text_layer(m, {"s1": "Y"}, "http://api/assets")
    assert 'class="tl-bg"' not in html
    assert "Y" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_text_layer_l2.py -v`
Expected: FAIL (no `tl-bg`; box not applied).

- [ ] **Step 3: Add `.tl-bg` CSS**

In `app/services/text_layer_renderer.py`, in the `_CSS` string, add a `.tl-bg` rule (e.g. right after the `.tl-fig` line):

```python
.tl-fig { position: absolute; display: block; }
.tl-bg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.tl-text { position: absolute; line-height: 1.2; overflow: hidden;
           word-break: break-word; }
```

- [ ] **Step 4: Emit the raster background**

In `render_text_layer`, right after `parts = []` and BEFORE the figures loop, insert the raster bg (so it sits behind figures+text):

```python
    parts = []
    image_name = (model.background or {}).get("image")
    if image_name:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
    # Figures first (z-order below text).
```

- [ ] **Step 5: Apply per-block box background**

In the block loop, after `size = fit_font_size(...)` and before building the div, compute box CSS; then add it to the div style. Replace the `parts.append(` block for text with:

```python
        size = fit_font_size(text, w, h, max_size=base, min_size=6.0)
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
            f'font-family:{family};font-size:{size:.1f}px;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};{box_css}">'
            f'{html_lib.escape(text)}</div>'
        )
```

(No other changes — `bg` page-div colour, figures, and the fit/zoom script stay as-is. When `image_name` is None and no box, output is identical to before.)

- [ ] **Step 6: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_text_layer_l2.py tests/test_text_layer_renderer.py -v`
Expected: new L2 tests PASS (4) and existing text-layer tests PASS (unchanged for text pages).

- [ ] **Step 7: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py apps/break_the_barriers/backend/tests/test_text_layer_l2.py
git commit -m "feat(sp-a.2): generalize render_text_layer (raster bg + per-block box)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Route all model kinds through the unified renderer

**Files:**
- Modify: `app/services/page_renderer.py`
- Test: `tests/test_page_renderer.py` (update existing)

- [ ] **Step 1: Update the test**

The existing `tests/test_page_renderer.py` asserts image kind uses the old `ov-bg` overlay. After unification, image kind renders via `render_text_layer` (`tl-bg`). Replace the whole file with:

```python
# tests/test_page_renderer.py
from backend.app.services.page_model import FontSpec, Block, PageModel
from backend.app.services.page_renderer import render_page


def _text_model():
    return PageModel(595, 842, "text", {"color": "#fff", "image": None},
                     [Block("s1", "heading", [72, 40, 200, 24], "T",
                            FontSpec(24, 700, False, "#111", "left", "sans"))],
                     [])


def _image_model():
    return PageModel(595, 842, "image", {"color": "#000", "image": "page-1.png"},
                     [Block("s1", "body", [40, 700, 120, 18], "C", None,
                            box={"mode": "scrim", "fill": "rgba(0,0,0,0.45)"})],
                     [])


def test_text_kind_uses_unified_renderer():
    html = render_page(_text_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-page"' in html
    assert 'class="tl-bg"' not in html      # text page: no raster
    assert "DỊCH" in html


def test_image_kind_uses_unified_renderer_with_raster():
    html = render_page(_image_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-page"' in html        # unified renderer markup
    assert 'class="tl-bg"' in html          # raster preserved
    assert "page-1.png" in html
    assert "rgba(0,0,0,0.45)" in html       # scrim box applied
    assert "DỊCH" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_page_renderer.py -v`
Expected: FAIL (image kind currently routes to `render_overlay_html` → no `tl-bg`).

- [ ] **Step 3: Simplify `page_renderer.py` to one renderer**

Replace the entire `app/services/page_renderer.py` with:

```python
"""Dispatch a PageModel to the unified text-layer renderer for ALL kinds:
text (no raster), image/mixed (raster background + per-block fill/scrim boxes).
The legacy render_overlay_html remains in overlay_renderer.py for the
layout_json fallback path used when a page has no PageModel."""
from __future__ import annotations

from backend.app.services.page_model import PageModel
from backend.app.services.text_layer_renderer import render_text_layer


def render_page(model: PageModel, translations: dict, image_url_base: str) -> str:
    return render_text_layer(model, translations, image_url_base)
```

(This removes the now-unused `_model_to_overlay_layout` helper and the `render_overlay_html` import from this module. `render_overlay_html` itself is untouched in `overlay_renderer.py`.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_page_renderer.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run preview-endpoint regression**

Run: `.venv/bin/pytest tests/test_preview_pagemodel.py tests/test_overlay.py -q`
Expected: PASS. (`test_preview_pagemodel.py::test_preview_text_page_raw_renders_text_layer_with_pagesize` still passes — text page still has no `ov-bg`; the page_size raw injection is added by the endpoint, unaffected.)

- [ ] **Step 6: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/page_renderer.py apps/break_the_barriers/backend/tests/test_page_renderer.py
git commit -m "refactor(sp-a.2): page_renderer routes all model kinds to unified renderer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Compute `box` per block in the extractor

**Files:**
- Modify: `app/services/extractor.py` (the PageModel build in `extract_pdf_to_html`)
- Test: covered by Task 6 integration (glue; no isolated unit test).

- [ ] **Step 1: Read the model-build block**

In `app/services/extractor.py`, find (post-L1) the model build inside the page loop:

```python
            model_blocks = [
                Block(span_id=b["span_id"], role=b.get("role", "body"), bbox=b["bbox"],
                      text="", font=b.get("font") or fonts.get(b["span_id"]))
                for b in blocks
            ]
```

- [ ] **Step 2: Compute per-block boxes before the comprehension**

Immediately BEFORE that `model_blocks = [...]` line, insert:

```python
            boxes = {}
            if image_name and pil_img is not None and page_size is not None:
                from backend.app.services.page_image import analyze_block_box
                _bsx = pil_img.width / page_size.width
                _bsy = pil_img.height / page_size.height
                _img_path = os.path.join(output_dir, image_name)
                for b in blocks:
                    try:
                        boxes[b["span_id"]] = analyze_block_box(_img_path, b["bbox"], _bsx, _bsy)
                    except Exception as e:
                        logger.warning(f"analyze_block_box failed p{page_no} {b['span_id']}: {e}")
```

- [ ] **Step 3: Pass `box` into the Block**

Change the comprehension to:

```python
            model_blocks = [
                Block(span_id=b["span_id"], role=b.get("role", "body"), bbox=b["bbox"],
                      text="", font=b.get("font") or fonts.get(b["span_id"]),
                      box=boxes.get(b["span_id"]))
                for b in blocks
            ]
```

- [ ] **Step 4: Run extractor regression**

Run: `.venv/bin/pytest tests/test_extractor_pagemodel.py tests/test_extractor_overhaul.py tests/test_overlay.py -q`
Expected: PASS (real docling, ~5 min — be patient). The model now also carries `box` per block.

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/extractor.py
git commit -m "feat(sp-a.2): compute per-block box (fill/scrim) at extraction

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Full verification + real-document check

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass (~8-10 min; multiple docling extractions).

- [ ] **Step 2: Real-document render check**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend
PYTHONPATH=/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers \
  .venv/bin/python -c "
from backend.app.services.extractor import DoclingExtractor
from backend.app.services.page_model import PageModel
from backend.app.services.page_renderer import render_page
import json
DoclingExtractor.extract_pdf_to_html('/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf','/tmp/l2_check','l2')
m=PageModel.from_json(open('/tmp/l2_check/l2-2.model.json',encoding='utf-8').read())
print('kind:', m.kind, '| blocks with box:', sum(1 for b in m.blocks if b.box))
print('box modes:', sorted({b.box['mode'] for b in m.blocks if b.box}))
trans={b.span_id:'DỊCH '+str(i) for i,b in enumerate(m.blocks)}
html=render_page(m, trans, 'http://api/assets')
print('has tl-bg:', 'tl-bg' in html, '| has tl-page:', 'tl-page' in html, '| no ov-bg:', 'ov-bg' not in html)
"
```
Expected: `kind: mixed`, several blocks with box, modes include `fill` and/or `scrim`, `has tl-bg: True`, `no ov-bg: True`.

- [ ] **Step 3: Note for the user**

Report: to see L2 in the app, the document must be **re-extracted** (to populate `box`) and re-translated. Image/mixed pages now render via the unified renderer (raster bg + real fonts + TextFitter + fill/scrim) — no opaque boxes, no oversized overflow.

---

## Self-Review notes

- **Spec coverage:** Block.box §4.1 → Task 1; BlockBoxAnalyzer §4.2 → Task 2; render_text_layer generalization §4.4 → Task 3; page_renderer routing §4.5 → Task 4; extractor wiring §4.3 → Task 5; degrade paths (§6: analyzer failure→fill, missing box→none, no raster→none) → Tasks 2/3/5; testing §7 → per-task unit + Task 6 integration. Unification decision §3 → Tasks 3+4 (one renderer; render_overlay_html kept for legacy).
- **Placeholder scan:** none — all code steps complete.
- **Type consistency:** `Block.box` shape `{"mode","fill"}` defined Task 1, produced by `analyze_block_box` Task 2, consumed in `render_text_layer` Task 3 and stored in extractor Task 5; `render_page(model, translations, image_url_base)` signature unchanged (Task 4). `.tl-bg` class introduced in Task 3 CSS, asserted in Tasks 3/4/6.
- **Known follow-ups (not L2):** scrim is a flat translucent panel (not true per-glyph inpaint); good enough per spec §2. Threshold tuning (`var_threshold`, alpha) lives in `analyze_block_box` defaults and can be adjusted later without interface change.
```
