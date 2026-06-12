# Raster-always + Masking (B2.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the per-page renderer always draw the page raster (every page) and mask the baked-in original text under the translated overlay, so reader/sidebar/split "Dịch" is faithful + translated for ANY page.

**Architecture:** `text_layer_renderer.render_text_layer` always draws `page-{n}.png` (falling back to page number when `background.image` is null) and applies a per-block opaque mask (`_mask_css`) behind every overlaid translation. The `/pages/{n}` endpoint sets `model.page_num` so the raster fallback resolves. No extraction/frontend changes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest. Spec: `docs/superpowers/specs/2026-06-09-raster-always-masking-b2-1-design.md`. Verify doc: `2024-wttc-introduction-to-ai`.

**Working dir for all commands:** `apps/break_the_barriers/backend`. Tests: `.venv/bin/pytest`. Imports: `backend.app.services.<x>`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `app/services/text_layer_renderer.py` | add `_opaque_fill`/`_mask_css`; always draw raster + always mask | Modify |
| `app/routers/documents.py` (`get_page_content`, ~line 255) | set `pm.page_num = page_num` before `render_page` | Modify |
| `tests/test_text_layer_mask.py` | unit (helpers) + integration (render + endpoint) | Create |

**Interface (locked):** `_opaque_fill(fill: str, min_alpha: float = 0.9) -> str`; `_mask_css(box: dict | None) -> str`. Raster filename convention `page-{n}.png`. CSS class `tl-bg` (existing).

---

## Task 1: Mask helpers `_opaque_fill` + `_mask_css`

**Files:**
- Modify: `app/services/text_layer_renderer.py` (add `import re` + two module-level helpers after the existing imports/`_GOOGLE_FONTS`/`_CSS`, before `_pct`)
- Test: `tests/test_text_layer_mask.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_text_layer_mask.py
from backend.app.services.text_layer_renderer import _opaque_fill, _mask_css


def test_opaque_fill_raises_low_alpha():
    assert _opaque_fill("rgba(255,255,255,0.55)") == "rgba(255,255,255,0.9)"


def test_opaque_fill_keeps_high_alpha():
    assert _opaque_fill("rgba(0,0,0,0.95)") == "rgba(0,0,0,0.95)"


def test_opaque_fill_passes_hex_through():
    assert _opaque_fill("#010203") == "#010203"


def test_mask_css_scrim_has_padding():
    css = _mask_css({"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    assert "background:rgba(255,255,255,0.9)" in css
    assert "padding:0 2px" in css


def test_mask_css_fill_no_padding():
    assert _mask_css({"mode": "fill", "fill": "#010203"}) == "background:#010203;"


def test_mask_css_empty_without_fill():
    assert _mask_css(None) == ""
    assert _mask_css({"mode": "scrim"}) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -v`
Expected: FAIL — `ImportError: cannot import name '_opaque_fill'`

- [ ] **Step 3: Implement the helpers**

In `app/services/text_layer_renderer.py`, add `import re` to the imports at the top (the file currently has `import html as html_lib`). Then add these two functions immediately BEFORE `def _pct(`:

```python
def _opaque_fill(fill: str, min_alpha: float = 0.9) -> str:
    """Raise an rgba fill's alpha to at least min_alpha so the mask hides the
    baked-in original text under an overlaid translation. Solid/hex colors (already
    opaque) pass through unchanged."""
    m = re.match(
        r"\s*rgba\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)\s*$",
        fill)
    if not m:
        return fill
    r, g, b, a = m.groups()
    return f"rgba({r},{g},{b},{max(float(a), min_alpha)})"


def _mask_css(box) -> str:
    """CSS background that masks the original text region behind an overlaid block.
    Empty string when there is no box fill."""
    if not box or not box.get("fill"):
        return ""
    fill = _opaque_fill(box["fill"])
    pad = "padding:0 2px;" if box.get("mode") == "scrim" else ""
    return f"background:{fill};{pad}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/text_layer_renderer.py tests/test_text_layer_mask.py
git commit -m "feat(textlayer): _opaque_fill + _mask_css mask helpers"
```

---

## Task 2: Always draw raster + always mask in `render_text_layer`

**Files:**
- Modify: `app/services/text_layer_renderer.py` — the raster block (~lines 95-110) and the per-block mask block (~lines 150-156) inside `render_text_layer`
- Test: `tests/test_text_layer_mask.py` (append)

- [ ] **Step 1: Write the failing integration test (append)**

```python
def test_text_page_always_draws_raster_and_masks():
    from backend.app.services.page_model import PageModel, Block, FontSpec
    from backend.app.services.text_layer_renderer import render_text_layer
    blk = Block(span_id="s1", role="body", bbox=[72, 100, 300, 40], text="",
                font=FontSpec(size=11, weight=400, italic=False, color="#000000",
                              align="left", family_class="sans"),
                box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    pm = PageModel(page_w=595, page_h=842, kind="text",
                   background={"color": "#ffffff", "image": None},
                   blocks=[blk], figures=[], page_class="text", cover="none", page_num=38)
    html = render_text_layer(pm, {"s1": "đoạn dịch"}, "http://x/assets")
    # raster is drawn even though background.image is None (text page)
    assert '<img class="tl-bg" src="http://x/assets/page-38.png"' in html
    assert "đoạn dịch" in html
    # the overlaid block masks the original text with an opaque fill
    assert "background:rgba(255,255,255,0.9)" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -k always_draws -v`
Expected: FAIL — current code sets `draw_raster=False` for base-color (text) pages, so no `tl-bg` img and no mask.

- [ ] **Step 3: Replace the raster block**

In `render_text_layer`, find this block (just after `policy = effective_policy(...)`):

```python
    policy = effective_policy(model.page_class, model.cover,
                              (model.background or {}).get("policy_override"))
    draw_raster = policy != "base-color"
    # On a base-color page the original raster is dropped, so render on a clean
    # WHITE page — not the dark color sampled from the discarded photo.
    if policy == "base-color":
        bg = "#ffffff"

    parts = []
    bgd = model.background or {}
    image_name = bgd.get("image")
    if policy == "clean-photo" and bgd.get("clean_image"):
        image_name = bgd.get("clean_image")
    if image_name and draw_raster:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
```

Replace it with:

```python
    policy = effective_policy(model.page_class, model.cover,
                              (model.background or {}).get("policy_override"))

    parts = []
    bgd = model.background or {}
    # Faithfulness-first: ALWAYS draw the page raster as the truth layer. The raster
    # page-{n}.png exists for every page; background.image is nulled for text pages,
    # so fall back to it by page number. The baked-in original text is hidden per
    # block by _mask_css so the translated overlay reads cleanly.
    image_name = bgd.get("image")
    if policy == "clean-photo" and bgd.get("clean_image"):
        image_name = bgd.get("clean_image")
    if not image_name and model.page_num:
        image_name = f"page-{model.page_num}.png"
    if image_name:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
```

- [ ] **Step 4: Replace the per-block mask block**

In the same function, find:

```python
        box = blk.box or None
        box_css = ""
        if box and box.get("fill") and policy == "keep-raster":
            if box.get("mode") == "scrim":
                box_css = f"background:{box['fill']};padding:0 2px;"
            else:
                box_css = f"background:{box['fill']};"
```

Replace it with:

```python
        # Always mask the baked-in original text under the translation (raster is
        # now always drawn). _mask_css raises the fill to an opaque level.
        box_css = _mask_css(blk.box)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add app/services/text_layer_renderer.py tests/test_text_layer_mask.py
git commit -m "feat(textlayer): always draw page raster + mask original text under overlay"
```

---

## Task 3: Endpoint sets `page_num` so the raster fallback resolves

**Files:**
- Modify: `app/routers/documents.py` — `get_page_content`, right after `pm = PageModel.from_json(page.model_json)` (~line 255)
- Test: `tests/test_text_layer_mask.py` (append)

- [ ] **Step 1: Write the failing integration test (append)**

```python
def test_pages_endpoint_sets_page_num_for_raster(client, db_session):
    import json
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="tldoc", filename="f.pdf", total_pages=5, status="translated"))
    m = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
         "background": {"color": "#ffffff", "image": None},
         "blocks": [{"span_id": "s1", "role": "body", "bbox": [72, 100, 300, 40], "text": "",
                     "font": {"size": 11, "weight": 400, "italic": False, "color": "#000000",
                              "align": "left", "family_class": "sans"},
                     "box": {"mode": "scrim", "fill": "rgba(255,255,255,0.55)"}}],
         "figures": [], "page_class": "text", "cover": "none"}
    db_session.add(DBPage(document_id="tldoc", page_num=5, original_html="<p/>",
                          status="translated", model_json=json.dumps(m)))
    db_session.add(DBTranslation(document_id="tldoc", page_num=5, span_id="s1",
                                 original_text="x", translated_text="dịch"))
    db_session.commit()
    r = client.get("/api/docs/tldoc/pages/5?lang=vi&raw=true")
    assert r.status_code == 200
    assert "page-5.png" in r.text   # raster fallback resolved via page_num
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -k endpoint -v`
Expected: FAIL — endpoint does not set `pm.page_num`, so the fallback yields `page-0.png` (not `page-5.png`).

- [ ] **Step 3: Set `page_num` in the endpoint**

In `app/routers/documents.py`, in `get_page_content`, find:

```python
            pm = PageModel.from_json(page.model_json)
            image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
```

Insert the `pm.page_num` line so it reads:

```python
            pm = PageModel.from_json(page.model_json)
            pm.page_num = page_num
            image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Run the full suite (no regression)**

Run: `.venv/bin/pytest -q`
Expected: PASS. Mixed pages already drew the raster + masked (keep-raster) — the change only ADDS raster+mask to text/base-color pages and raises mask opacity, so existing renderer tests stay green. If a test asserted the OLD "no raster on text page" or the OLD scrim alpha, update it to the new contract and note it.

- [ ] **Step 6: Commit**

```bash
git add app/routers/documents.py tests/test_text_layer_mask.py
git commit -m "fix(pages): set PageModel.page_num so the raster fallback resolves"
```

---

## Task 4: Verification on the WTTC document

**Files:** none (verification only).

- [ ] **Step 1: Render the previously-broken pages and assert raster + mask**

Run:
```bash
PYTHONPATH=.. .venv/bin/python -c "
from backend.app.database import SessionLocal
from backend.app.models_db import DBPage, DBTranslation
from backend.app.services.page_model import PageModel
from backend.app.services.page_renderer import render_page
db=SessionLocal(); doc='2024-wttc-introduction-to-ai'
for n in (38, 29, 12, 34):
    pr=db.query(DBPage).filter_by(document_id=doc,page_num=n).first()
    pm=PageModel.from_json(pr.model_json); pm.page_num=n
    trs={t.span_id:(t.translated_text or t.original_text or '') for t in db.query(DBTranslation).filter_by(document_id=doc,page_num=n).all()}
    html=render_page(pm, trs, f'http://x/api/docs/{doc}/assets')
    print(f'p{n}: tl-bg={(\"class=\\\"tl-bg\\\"\" in html)} raster_ref={(f\"page-{n}.png\" in html or (pm.background or {{}}).get(\"image\") in html)} masks={html.count(\"background:rgba\")+html.count(\"background:#\")}')
db.close()
"
```
Expected: every page prints `tl-bg=True` and a raster reference; p38/p29 (previously `tl-bg=False`) now draw the raster.

- [ ] **Step 2: Manual visual check**

Start dev servers (`/start-dev`), open the frontend preview in **reader** layout, **Dịch** mode, and inspect:
- p38 (ANNEX table), p29 (diagram): the table/graphic is now visible (raster drawn), translated text overlaid without the original text ghosting through.
- p12 (Data table, mixed) and p34 (QUIZ, preserve): no regression — still faithful + translated.

- [ ] **Step 3: Final full test run**

Run: `.venv/bin/pytest -q`
Expected: PASS.

---

## Self-Review

**Spec coverage:**
- Always draw raster + page-{n}.png fallback (spec §A) → Task 2. ✓
- Mask all overlaid blocks + opacity helper (spec §B) → Task 1 (helpers) + Task 2 (apply). ✓
- Endpoint sets page_num (spec §C) → Task 3. ✓
- Unit + integration + manual verification (spec Testing) → Tasks 1–4. ✓
- Out of scope (B2.2 flow, inpaint, mode UI) → not in plan. ✓

**Placeholder scan:** none — all code steps complete.

**Type consistency:** `_opaque_fill(fill, min_alpha=0.9)`, `_mask_css(box)`, `page-{n}.png`, `tl-bg`, `pm.page_num` — consistent across Tasks 1–4. Note: `_opaque_fill` emits the float via `max(float(a), min_alpha)`; `0.55→0.9` renders as `0.9` and `0.95` stays `0.95` (matches the Task 1 test assertions).
