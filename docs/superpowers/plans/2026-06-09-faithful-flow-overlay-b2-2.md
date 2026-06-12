# Faithful Flow + Overlay (B2.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/flow` a continuous, faithful + translated document — a vertical stack of per-page fragments (original raster + masked translated overlay) that scale fluidly via cqw.

**Architecture:** A new pure `render_faithful_page` builds one page fragment (raster + figures + cqw-sized overlay text), and `render_faithful_flow` stacks fragments into one scrolling HTML doc with a cqw shrink-to-fit script. The raster/mask decision is extracted into a shared pure helper `resolve_page_raster` so the per-page renderer and the flow stay consistent. Frontend unchanged (one iframe loads `/flow`).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, CSS container queries (cqw). Spec: `docs/superpowers/specs/2026-06-09-faithful-flow-overlay-b2-2-design.md`. Verify doc: `2024-wttc-introduction-to-ai`.

**Working dir for all commands:** `apps/break_the_barriers/backend`. Tests: `.venv/bin/pytest`. Imports: `backend.app.services.<x>`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `app/services/text_layer_renderer.py` | add pure `resolve_page_raster`; render_text_layer uses it | Modify |
| `app/services/faithful_flow_renderer.py` | rewrite: `render_faithful_page` (fragment) + `render_faithful_flow` (doc) | Rewrite |
| `app/routers/documents.py` (`get_document_flow`) | load PageModels + translations → render | Modify |
| `tests/test_faithful_flow.py` | rewrite for new contract | Rewrite |
| `tests/test_text_layer_mask.py` | add resolve_page_raster unit tests | Modify |
| `tests/test_preview_pagemodel.py` (`test_flow_endpoint_returns_document_html`) | update to B2.2 contract | Modify |

**Interfaces (locked):**
- `resolve_page_raster(model) -> (image_name: str|None, mask_original: bool, force_white: bool)`
- `render_faithful_page(model: PageModel, translations: dict, image_url_base: str) -> str` (fragment)
- `render_faithful_flow(pages: list[PageModel], translations: dict[int, dict], image_url_base: str) -> str`
- CSS classes `ff-doc`/`ff-page`/`ff-bg`/`ff-fig`/`ff-text`(+`ff-toc*`); per-page id `pg-{n}`; text divs carry `data-cqw`.

---

## Task 1: Extract `resolve_page_raster` helper

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_mask.py` (append)

- [ ] **Step 1: Append failing unit tests to `tests/test_text_layer_mask.py`**

```python
def test_resolve_text_page_falls_back_to_page_raster():
    from backend.app.services.page_model import PageModel
    from backend.app.services.text_layer_renderer import resolve_page_raster
    pm = PageModel(595.0, 842.0, "text", {"color": "#fff", "image": None}, [], [],
                   page_class="text", cover="none", page_num=5)
    assert resolve_page_raster(pm) == ("page-5.png", True, False)


def test_resolve_override_base_color_drops_raster():
    from backend.app.services.page_model import PageModel
    from backend.app.services.text_layer_renderer import resolve_page_raster
    pm = PageModel(595.0, 842.0, "mixed",
                   {"color": "#000", "image": "page-1.png", "policy_override": "base-color"},
                   [], [], page_class="preserve", cover="none", page_num=1)
    assert resolve_page_raster(pm) == (None, False, True)


def test_resolve_clean_photo_uses_clean_image_no_mask():
    from backend.app.services.page_model import PageModel
    from backend.app.services.text_layer_renderer import resolve_page_raster
    pm = PageModel(595.0, 842.0, "mixed",
                   {"color": "#000", "image": "page-1.png", "clean_image": "page-1.clean.png"},
                   [], [], page_class="regenerable", cover="front", page_num=1)
    assert resolve_page_raster(pm) == ("page-1.clean.png", False, False)
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -k resolve -v`
Expected: FAIL — `cannot import name 'resolve_page_raster'`

- [ ] **Step 3: Add the helper.** In `app/services/text_layer_renderer.py`, add this function immediately AFTER `_mask_css`:

```python
def resolve_page_raster(model):
    """Decide a page's background raster and whether to mask the baked-in text.
    Returns (image_name | None, mask_original: bool, force_white: bool).

    Faithfulness-first: draw the ORIGINAL raster (page-{n}.png fallback) and mask text
    per block. Exceptions: a manual base-color override drops the raster (clean white
    page — escape hatch); a clean-photo page uses its AI-cleaned image (no mask)."""
    bgd = model.background or {}
    if bgd.get("policy_override") == "base-color":
        return None, False, True
    policy = effective_policy(model.page_class, model.cover, bgd.get("policy_override"))
    if policy == "clean-photo" and bgd.get("clean_image"):
        return bgd["clean_image"], False, False
    image_name = bgd.get("image") or (
        f"page-{model.page_num}.png" if model.page_num else None)
    return image_name, image_name is not None, False
```

- [ ] **Step 4: Refactor `render_text_layer` to use it.** Replace this block (the `policy = ...` line through the raster `if image_name:` append):

```python
    policy = effective_policy(model.page_class, model.cover,
                              (model.background or {}).get("policy_override"))

    parts = []
    bgd = model.background or {}
    # Faithfulness-first: draw the ORIGINAL page raster as the truth layer ...
    #   * an explicit base-color override is the manual "drop this raster" escape hatch
    #     → clean white page, no raster;
    #   * a clean-photo page uses its AI-cleaned image (original text already removed)
    #     → no per-block mask needed.
    force_base_color = bgd.get("policy_override") == "base-color"
    image_name = None
    mask_original = False
    if force_base_color:
        bg = "#ffffff"
    elif policy == "clean-photo" and bgd.get("clean_image"):
        image_name = bgd.get("clean_image")
    else:
        image_name = bgd.get("image") or (
            f"page-{model.page_num}.png" if model.page_num else None)
        mask_original = image_name is not None
    if image_name:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
```

with:

```python
    parts = []
    image_name, mask_original, force_white = resolve_page_raster(model)
    if force_white:
        bg = "#ffffff"
    if image_name:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
```

(The per-block `box_css = _mask_css(blk.box) if mask_original else ""` line stays unchanged — `mask_original` is still defined.)

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py tests/test_text_layer_renderer.py tests/test_text_layer_l2.py tests/test_page_renderer.py -q`
Expected: PASS (resolve tests + all existing text_layer tests still green — behavior unchanged).

- [ ] **Step 6: Commit**

```bash
git add app/services/text_layer_renderer.py tests/test_text_layer_mask.py
git commit -m "refactor(textlayer): extract pure resolve_page_raster helper"
```

---

## Task 2: `render_faithful_page` fragment + `render_faithful_flow` doc

**Files:**
- Rewrite: `app/services/faithful_flow_renderer.py`
- Rewrite: `tests/test_faithful_flow.py` (unit portion)

- [ ] **Step 1: Replace `tests/test_faithful_flow.py` with the unit tests** (endpoint tests are added in Task 3):

```python
from backend.app.services.page_model import PageModel, Block, FontSpec
from backend.app.services.faithful_flow_renderer import (
    render_faithful_page, render_faithful_flow)


def _text_page(page_num):
    blk = Block(span_id="s1", role="body", bbox=[72, 100, 300, 40], text="",
                font=FontSpec(11, 400, False, "#000000", "left", "sans"),
                box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    return PageModel(595.0, 842.0, "text", {"color": "#fff", "image": None}, [blk], [],
                     page_class="text", cover="none", page_num=page_num)


def test_fragment_has_aspect_and_raster_fallback():
    html = render_faithful_page(_text_page(38), {"s1": "đoạn dịch"}, "http://x/assets")
    assert 'class="ff-page"' in html
    assert "aspect-ratio:595.00/842.00" in html
    assert '<img class="ff-bg" src="http://x/assets/page-38.png"' in html


def test_fragment_overlay_text_in_cqw_with_mask():
    html = render_faithful_page(_text_page(38), {"s1": "đoạn dịch"}, "http://x/assets")
    assert "đoạn dịch" in html
    assert "cqw" in html and "data-cqw=" in html
    assert "background:rgba(255,255,255,0.9)" in html


def test_fragment_skips_blocks_without_translation_but_keeps_raster():
    html = render_faithful_page(_text_page(1), {}, "http://x/assets")
    assert 'class="ff-text"' not in html
    assert '<img class="ff-bg"' in html


def test_flow_stacks_pages_in_order_with_scripts():
    html = render_faithful_flow([_text_page(2), _text_page(1)],
                                {1: {"s1": "một"}, 2: {"s1": "hai"}}, "http://x/assets")
    assert html.count('class="ff-page"') == 2
    assert html.index('id="pg-1"') < html.index('id="pg-2"')
    assert "btb-zoom" in html and "data-cqw" in html
    assert "một" in html and "hai" in html


def test_flow_empty_pages_valid_shell():
    html = render_faithful_flow([], {}, "http://x/a")
    assert '<article class="ff-doc">' in html
    assert html.count('class="ff-page"') == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -v`
Expected: FAIL — `cannot import name 'render_faithful_page'`

- [ ] **Step 3: Replace `app/services/faithful_flow_renderer.py` entirely with:**

```python
"""Render a document as a faithful continuous flow: a vertical stack of per-page
fragments. Each page shows its original raster (the truth layer — tables, vector
graphics, multi-column design and banners are preserved because they ARE the raster)
with translated text overlaid on masked text regions. Overlay text is sized in cqw
(1cqw = 1% of the page width) so each page scales fluidly with the column width.
Reuses text_layer_renderer's pure helpers so per-page and flow stay consistent."""
from __future__ import annotations
import html as html_lib
from typing import Dict, List

from backend.app.services.page_model import PageModel
from backend.app.services.text_fitter import fit_font_size
from backend.app.services.toc_parser import parse_toc_entry, is_toc_page
from backend.app.services.text_layer_renderer import (
    _FONT_STACK, _GOOGLE_FONTS, _mask_css, _pct, compute_slot_heights,
    resolve_page_raster)

_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #f4f4f5; }
.ff-doc { max-width: 900px; margin: 0 auto; padding: 16px 12px 80px; }
.ff-page { position: relative; container-type: inline-size; width: 100%;
           margin: 0 0 16px; background: #fff; overflow: hidden;
           box-shadow: 0 2px 14px rgba(0,0,0,.25); border-radius: 2px; }
.ff-bg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.ff-fig { position: absolute; display: block; }
.ff-text { position: absolute; line-height: 1.2; overflow: hidden; word-break: break-word; }
.ff-toc { display: flex; align-items: flex-end; white-space: nowrap; }
.ff-toc-title { flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; }
.ff-toc-leader { flex: 1 1 8px; min-width: 8px; margin: 0 4px 3px;
                 border-bottom: 1px dotted currentColor; }
.ff-toc-num { flex: 0 0 auto; }
"""

_SCRIPT = (
    "<script>(function(){"
    "function fit(el){var c=parseFloat(el.dataset.cqw||'0');if(!c)return;var g=0;"
    "el.style.fontSize=c+'cqw';"
    "while(el.scrollHeight>el.clientHeight+1&&c>1&&g<60){c-=0.2;el.style.fontSize=c+'cqw';g++;}}"
    "function run(){document.querySelectorAll('.ff-text').forEach(fit);}"
    "var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(run,150);});"
    "window.addEventListener('message',function(e){var d=e.data||{};"
    "if(d.type==='btb-zoom'&&typeof d.zoom==='number'){"
    "var doc=document.querySelector('.ff-doc');"
    "if(doc)doc.style.maxWidth=Math.max(200,900*d.zoom)+'px';setTimeout(run,0);}});"
    "if(document.readyState!=='loading')run();"
    "else window.addEventListener('DOMContentLoaded',run);"
    "window.addEventListener('load',run);})();</script>"
)


def render_faithful_page(model: PageModel, translations: dict, image_url_base: str) -> str:
    pw = model.page_w or 1.0
    ph = model.page_h or 1.0
    image_name, mask_original, _white = resolve_page_raster(model)
    parts = [f'<section class="ff-page" id="pg-{int(model.page_num)}" '
             f'style="aspect-ratio:{pw:.2f}/{ph:.2f}">']
    if image_name:
        src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="ff-bg" src="{src}" '
                     f'alt="Trang {int(model.page_num)}" loading="lazy"/>')
    for fig in model.figures:
        l, t, w, h = fig.bbox
        fsrc = html_lib.escape(f"{image_url_base}/{fig.clean_img or fig.img}", quote=True)
        parts.append(f'<img class="ff-fig" src="{fsrc}" alt="figure" '
                     f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
                     f'width:{_pct(w, pw):.3f}%;height:{_pct(h, ph):.3f}%;"/>')
    slots = compute_slot_heights(model.blocks, model.figures, ph)
    toc_page = is_toc_page([(translations or {}).get(b.span_id, "") for b in model.blocks])
    for blk in model.blocks:
        text = (translations or {}).get(blk.span_id)
        if not text:
            continue
        l, t, w, h = blk.bbox
        f = blk.font
        family = _FONT_STACK.get(f.family_class if f else "sans", _FONT_STACK["sans"])
        color = (f.color if f else "#1a1a1a")
        weight = (f.weight if f else (700 if blk.role == "heading" else 400))
        italic = "italic" if (f and f.italic) else "normal"
        align = (f.align if f else "left")
        slot_h = slots.get(blk.span_id, h)
        f_size = f.size if f and f.size else 0
        is_single_line = blk.role == "heading" or (f_size and h <= f_size * 1.8)
        fit_h = h if is_single_line else slot_h
        max_h = h if is_single_line else slot_h
        base_sz = (f.size if f and f.size else max(8.0, h * 0.8))
        size_px = fit_font_size(text, w, fit_h, max_size=base_sz, min_size=6.0,
                                height_growth=1.0)
        cqw = size_px / pw * 100.0
        box_css = _mask_css(blk.box) if mask_original else ""
        entry = parse_toc_entry(text) if toc_page else None
        if entry:
            _title, _num = entry
            inner = (f'<span class="ff-toc-title">{html_lib.escape(_title)}</span>'
                     f'<span class="ff-toc-leader"></span>'
                     f'<span class="ff-toc-num">{html_lib.escape(_num)}</span>')
            cls = "ff-text ff-toc"
        else:
            inner = html_lib.escape(text)
            cls = "ff-text"
        parts.append(
            f'<div class="{cls}" data-cqw="{cqw:.3f}" '
            f'data-span="{html_lib.escape(blk.span_id, quote=True)}" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;'
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(max_h, ph):.3f}%;'
            f'font-family:{family};font-size:{cqw:.3f}cqw;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};{box_css}">'
            f'{inner}</div>')
    parts.append("</section>")
    return "".join(parts)


def render_faithful_flow(pages: List[PageModel], translations: Dict[int, dict],
                         image_url_base: str) -> str:
    body = "".join(
        render_faithful_page(p, (translations or {}).get(p.page_num, {}), image_url_base)
        for p in sorted(pages, key=lambda m: m.page_num))
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_GOOGLE_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="ff-doc">{body}</article>{_SCRIPT}</body></html>'
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/faithful_flow_renderer.py tests/test_faithful_flow.py
git commit -m "feat(flow): faithful per-page fragments (raster + cqw masked overlay)"
```

---

## Task 3: Wire `/flow` endpoint to the overlay renderer

**Files:**
- Modify: `app/routers/documents.py` — `get_document_flow`
- Test: `tests/test_faithful_flow.py` (append endpoint tests) + `tests/test_preview_pagemodel.py` (update contract test)

- [ ] **Step 1: Append endpoint integration tests to `tests/test_faithful_flow.py`**

```python
def test_flow_endpoint_overlays_translation(client, db_session):
    import json
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="ffdoc", filename="f.pdf", total_pages=2, status="translated"))
    m = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
         "background": {"color": "#fff", "image": None},
         "blocks": [{"span_id": "s1", "role": "body", "bbox": [72, 100, 300, 40], "text": "",
                     "font": {"size": 11, "weight": 400, "italic": False, "color": "#000000",
                              "align": "left", "family_class": "sans"},
                     "box": {"mode": "scrim", "fill": "rgba(255,255,255,0.55)"}}],
         "figures": [], "page_class": "text", "cover": "none"}
    for n in (1, 2):
        db_session.add(DBPage(document_id="ffdoc", page_num=n, original_html="<p/>",
                              status="translated", model_json=json.dumps(m)))
    db_session.add(DBTranslation(document_id="ffdoc", page_num=1, span_id="s1",
                                 original_text="a", translated_text="dịch một"))
    db_session.commit()
    r = client.get("/api/docs/ffdoc/flow?lang=vi")
    assert r.status_code == 200
    assert r.text.count('class="ff-page"') == 2
    assert "page-1.png" in r.text and "page-2.png" in r.text
    assert "dịch một" in r.text


def test_flow_endpoint_unknown_doc_404(client):
    assert client.get("/api/docs/nope-doc/flow").status_code == 404
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -k endpoint -v`
Expected: FAIL — endpoint still returns B1 raster stack (`ff-page` absent / `dịch một` absent).

- [ ] **Step 3: Replace the `get_document_flow` function** in `app/routers/documents.py` with:

```python
@router.get("/api/docs/{doc_id}/flow")
def get_document_flow(doc_id: str, request: Request,
                      lang: str = Query("vi", pattern="^(en|vi)$"),
                      db: Session = Depends(get_db)):
    # B2.2 — faithful flow: a vertical stack of per-page fragments (original raster +
    # masked translated overlay). `lang` selects original vs translated text.
    from backend.app.services.page_model import PageModel
    from backend.app.services.faithful_flow_renderer import render_faithful_flow
    from backend.app.models_db import DBTranslation

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page_rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
                 .order_by(DBPage.page_num).all())
    pages = []
    for pr in page_rows:
        if pr.model_json:
            try:
                pm = PageModel.from_json(pr.model_json)
                pm.page_num = pr.page_num
                pages.append(pm)
            except Exception:
                pass
    rows = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id).all()
    translations: dict = {}
    for t in rows:
        txt = (t.original_text if lang == "en" else t.translated_text) or ""
        translations.setdefault(t.page_num, {})[t.span_id] = txt
    image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
    html = render_faithful_flow(pages, translations, image_base)
    return HTMLResponse(content=html)
```

- [ ] **Step 4: Update the contract test in `tests/test_preview_pagemodel.py`.** Find `test_flow_endpoint_returns_document_html` and replace its final assertions:

```python
    r = client.get("/api/docs/fl_doc/flow?lang=vi")
    assert r.status_code == 200
    # B1: /flow now serves a faithful vertical stack of the original page rasters
    # (translated text overlay is sub-project B2), so it references page-{n}.png.
    assert 'class="fr-img"' in r.text
    assert "page-1.png" in r.text and "page-2.png" in r.text
```

with:

```python
    r = client.get("/api/docs/fl_doc/flow?lang=vi")
    assert r.status_code == 200
    # B2.2: /flow is a faithful stack of per-page fragments (raster + translated overlay).
    assert r.text.count('class="ff-page"') == 2
    assert "page-1.png" in r.text and "page-2.png" in r.text
    assert "TIÊU ĐỀ" in r.text          # translated heading overlaid
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_faithful_flow.py tests/test_preview_pagemodel.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (no regressions). If any other test asserted the B1 `fr-img` / page_nums flow contract, update it to the B2.2 `ff-page` contract and report it.

- [ ] **Step 7: Commit**

```bash
git add app/routers/documents.py tests/test_faithful_flow.py tests/test_preview_pagemodel.py
git commit -m "feat(flow): /flow renders faithful per-page fragments with translated overlay"
```

---

## Task 4: Verification on the WTTC document

**Files:** none (verification only).

- [ ] **Step 1: Render the flow and assert structure**

Run:
```bash
PYTHONPATH=.. .venv/bin/python -c "
from backend.app.database import SessionLocal
from backend.app.models_db import DBPage, DBTranslation
from backend.app.services.page_model import PageModel
from backend.app.services.faithful_flow_renderer import render_faithful_flow
db=SessionLocal(); doc='2024-wttc-introduction-to-ai'
pages=[]
for pr in db.query(DBPage).filter(DBPage.document_id==doc).order_by(DBPage.page_num).all():
    if pr.model_json:
        pm=PageModel.from_json(pr.model_json); pm.page_num=pr.page_num; pages.append(pm)
tr={}
for t in db.query(DBTranslation).filter(DBTranslation.document_id==doc).all():
    tr.setdefault(t.page_num,{})[t.span_id]=(t.translated_text or t.original_text or '')
html=render_faithful_flow(pages, tr, f'http://x/api/docs/{doc}/assets')
print('pages:',len(pages),'ff-page:',html.count('ff-page'),'overlays:',html.count('ff-text'),'rasters:',html.count('ff-bg'))
assert html.count('class=\"ff-page\"')==len(pages)
print('OK')
db.close()
"
```
Expected: `ff-page` count == number of pages with model_json (44), overlays > 0, a raster per page.

- [ ] **Step 2: Manual visual check**

Start dev servers (`/start-dev`), open the frontend preview in **flow** (Liền mạch) layout, **Dịch** mode. Scroll all pages and confirm:
- Pages render faithfully (tables, diagrams, full-page design, banners — the raster) with translated text overlaid where translations exist; text does not ghost/overlap.
- Previously-broken pages (TOC, QUIZ, Data table, ANNEX table, eFootball/Serial/ANI/hallucination, TSMC, ACK) now appear faithful in the continuous flow.
- Zoom controls still resize; scrolling is smooth (images lazy-load).

- [ ] **Step 3: Final full test run**

Run: `.venv/bin/pytest -q`
Expected: PASS.

---

## Self-Review

**Spec coverage:**
- `resolve_page_raster` shared helper (spec §A) → Task 1. ✓
- `render_faithful_page` fragment with cqw + mask + figures + TOC (spec §B) → Task 2. ✓
- `render_faithful_flow` doc assembler + cqw fit/zoom script (spec §C) → Task 2. ✓
- Endpoint loads models + `{page_num: {span_id: text}}` translations (spec §D) → Task 3. ✓
- Reuse helpers, frontend unchanged → Tasks 2–3 (imports; no frontend file touched). ✓
- Unit + integration + manual verification → Tasks 1–4. ✓
- Out of scope (B3 mode UI / TOC nav / inpaint) → not in plan. ✓

**Placeholder scan:** none — all code steps complete.

**Type consistency:** `resolve_page_raster(model) -> (image_name, mask_original, force_white)`; `render_faithful_page(model, translations, image_url_base)`; `render_faithful_flow(pages, translations: {page_num: {span_id: text}}, image_url_base)`; classes `ff-doc/ff-page/ff-bg/ff-fig/ff-text`; `data-cqw`; id `pg-{n}` — consistent across Tasks 1–4. Note: pages without `model_json` are not rendered (the extractor writes a model for every page, so this does not drop content for normally-extracted docs).
