# Faithful Raster View (B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the document-flow view as a faithful vertical stack of the original page rasters (`page-{n}.png`) so the rendered document is pixel-faithful to the source for any document.

**Architecture:** A new pure renderer `faithful_flow_renderer.render_faithful_flow(page_nums, image_url_base)` emits one `<img>` per page pointing at the existing `page-{n}.png` asset. The `GET /api/docs/{id}/flow` endpoint stops calling the lossy `build_document_flow` reflow and returns this raster stack instead. `lang` is kept for API compatibility (translated overlay is sub-project B2). No model/extractor/frontend changes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest. Spec: `docs/superpowers/specs/2026-06-09-faithful-raster-view-b1-design.md`. Verify doc: `2024-wttc-introduction-to-ai` (44 pages, rasters present).

**Working dir for all commands:** `apps/break_the_barriers/backend`. Tests: `.venv/bin/pytest`. Tests import as `backend.app.services.<x>`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `app/services/faithful_flow_renderer.py` | pure: page_nums + base URL → scrolling raster-stack HTML | Create |
| `app/routers/documents.py` (`get_document_flow`, ~line 357-393) | serve faithful raster stack from DBPage rows | Modify |
| `tests/test_faithful_flow.py` | unit (renderer) + integration (endpoint) | Create |

**Interface (locked):** `render_faithful_flow(page_nums: List[int], image_url_base: str) -> str`. Page raster filename convention: `page-{n}.png`. Per-page anchor id: `pg-{n}`. CSS classes: `fr-doc`, `fr-page`, `fr-img`. Zoom protocol: `postMessage({type:"btb-zoom", zoom})` (same as the old flow).

---

## Task 1: Pure renderer `render_faithful_flow`

**Files:**
- Create: `app/services/faithful_flow_renderer.py`
- Test: `tests/test_faithful_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_faithful_flow.py
from backend.app.services.faithful_flow_renderer import render_faithful_flow


def test_one_img_per_page_in_sorted_order():
    html = render_faithful_flow([3, 1, 2], "http://api/assets")
    assert html.count('class="fr-img"') == 3
    assert html.index("page-1.png") < html.index("page-2.png") < html.index("page-3.png")
    for n in (1, 2, 3):
        assert f'src="http://api/assets/page-{n}.png"' in html
        assert f'id="pg-{n}"' in html


def test_empty_pages_returns_valid_shell():
    html = render_faithful_flow([], "http://api/a")
    assert '<article class="fr-doc">' in html
    assert html.count('class="fr-img"') == 0


def test_has_zoom_script():
    assert "btb-zoom" in render_faithful_flow([1], "http://api/a")


def test_escapes_base_url():
    html = render_faithful_flow([1], 'http://a/x"onerror')
    assert 'x"onerror' not in html
    assert "&quot;" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.app.services.faithful_flow_renderer`

- [ ] **Step 3: Write the implementation**

```python
# app/services/faithful_flow_renderer.py
"""Render a document as a faithful vertical stack of its original page rasters.

The truth layer: each page is shown as its high-fidelity raster page-{n}.png, so the
rendered document is pixel-faithful to the source for ANY document (tables, vector
graphics, multi-column design, banners are all preserved because they ARE the raster).
Translation overlay is a later sub-project (B2); this renders the original pages.
Pure: page numbers + asset base URL in, one HTML document out."""
from __future__ import annotations
import html as html_lib
from typing import List

_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #f4f4f5; }
.fr-doc { max-width: 900px; margin: 0 auto; padding: 16px 12px 80px; }
.fr-page { margin: 0 0 16px; }
.fr-img { width: 100%; height: auto; display: block;
          box-shadow: 0 2px 14px rgba(0,0,0,.25); border-radius: 2px; }
"""

_ZOOM_SCRIPT = (
    "<script>window.addEventListener('message',function(e){"
    "var d=e.data||{};"
    "if(d.type==='btb-zoom'&&typeof d.zoom==='number'){"
    "var el=document.querySelector('.fr-doc');"
    "if(el)el.style.maxWidth=Math.max(200,900*d.zoom)+'px';}"
    "});</script>"
)


def render_faithful_flow(page_nums: List[int], image_url_base: str) -> str:
    base = html_lib.escape(image_url_base, quote=True)
    parts = []
    for n in sorted(int(x) for x in page_nums):
        parts.append(
            f'<figure id="pg-{n}" class="fr-page">'
            f'<img class="fr-img" src="{base}/page-{n}.png" '
            f'alt="Trang {n}" loading="lazy"/></figure>'
        )
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'<style>{_CSS}</style></head><body>'
        f'<article class="fr-doc">{"".join(parts)}</article>'
        f'{_ZOOM_SCRIPT}</body></html>'
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/faithful_flow_renderer.py tests/test_faithful_flow.py
git commit -m "feat(faithful): render_faithful_flow — vertical stack of page rasters"
```

---

## Task 2: Wire `/flow` endpoint to the faithful renderer

**Files:**
- Modify: `app/routers/documents.py` — `get_document_flow` (currently ~line 357-393)
- Test: `tests/test_faithful_flow.py` (append integration tests)

The current `get_document_flow` loads PageModels + translations and calls `build_document_flow` / `render_flow_html` (the lossy reflow). Replace its body to serve the faithful raster stack. Keep the route, signature, and `HTMLResponse` contract so the frontend iframe (`/flow?lang=...`) is unaffected. Leave `flow_model.py` / `flow_renderer.py` in place (unused by this endpoint now; kept for reference/fallback).

- [ ] **Step 1: Write the failing integration tests (append to tests/test_faithful_flow.py)**

```python
def test_flow_endpoint_serves_raster_stack(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="frdoc", filename="f.pdf", total_pages=2, status="extracted"))
    db_session.add(DBPage(document_id="frdoc", page_num=1))
    db_session.add(DBPage(document_id="frdoc", page_num=2))
    db_session.commit()
    r = client.get("/api/docs/frdoc/flow")
    assert r.status_code == 200
    assert "page-1.png" in r.text and "page-2.png" in r.text
    assert r.text.count('class="fr-img"') == 2


def test_flow_endpoint_unknown_doc_404(client):
    assert client.get("/api/docs/nope-doc/flow").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -k endpoint -v`
Expected: FAIL — current endpoint returns reflow HTML, so `class="fr-img"` is absent (count 0 ≠ 2).

- [ ] **Step 3: Replace the `get_document_flow` body**

Find the existing function (starts `@router.get("/api/docs/{doc_id}/flow")`) and replace the WHOLE function with:

```python
@router.get("/api/docs/{doc_id}/flow")
def get_document_flow(doc_id: str, request: Request,
                      lang: str = Query("vi", pattern="^(en|vi)$"),
                      db: Session = Depends(get_db)):
    # B1 — faithful raster view: render the document as a vertical stack of the
    # original page rasters (page-{n}.png). Pixel-faithful to the source for any
    # document. `lang` is accepted for API compatibility but B1 always serves the
    # original rasters; translated overlay is sub-project B2.
    from backend.app.services.faithful_flow_renderer import render_faithful_flow

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page_rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
                 .order_by(DBPage.page_num).all())
    page_nums = [r.page_num for r in page_rows]
    image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
    html = render_faithful_flow(page_nums, image_base)
    return HTMLResponse(content=html)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -v`
Expected: PASS (6 passed: 4 unit + 2 integration)

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `.venv/bin/pytest -q`
Expected: PASS. Note: tests that asserted the OLD reflow flow output (`tests/test_flow_renderer.py`, `tests/test_flow_figures.py`) test the renderer functions directly (not the endpoint), so they still pass. If any test asserted reflow output FROM the `/flow` endpoint, update it to the new contract and note it in the report. (`test_flow_renderer.py`/`test_flow_figures.py` call `render_flow_html`/`build_document_flow` directly — unaffected.)

- [ ] **Step 6: Commit**

```bash
git add app/routers/documents.py tests/test_faithful_flow.py
git commit -m "feat(flow): serve faithful raster stack from /flow (retire reflow render)"
```

---

## Task 3: Verification on the WTTC document

**Files:** none (verification only).

- [ ] **Step 1: Confirm rasters exist for the sample doc**

Run: `ls data/extracted_html/2024-wttc-introduction-to-ai/page-*.png | wc -l`
Expected: 44 (or more).

- [ ] **Step 2: Render the flow HTML and assert all 44 page images are referenced**

Run:
```bash
PYTHONPATH=.. .venv/bin/python -c "
from backend.app.database import SessionLocal
from backend.app.models_db import DBPage
from backend.app.services.faithful_flow_renderer import render_faithful_flow
db=SessionLocal()
ns=[r.page_num for r in db.query(DBPage).filter(DBPage.document_id=='2024-wttc-introduction-to-ai').order_by(DBPage.page_num).all()]
html=render_faithful_flow(ns,'http://x/api/docs/2024-wttc-introduction-to-ai/assets')
print('pages:',len(ns),'imgs:',html.count('fr-img'))
assert all(f'page-{n}.png' in html for n in ns)
print('all page rasters referenced: OK')
db.close()
"
```
Expected: `pages: 44 imgs: 44` and `all page rasters referenced: OK`.

- [ ] **Step 3: Manual visual check**

Start dev servers (`/start-dev`), open `http://localhost:8000/api/docs/2024-wttc-introduction-to-ai/flow`. Scroll all 44 pages and confirm each of the 17 previously-broken pages now renders faithfully (it is the original raster): cover/INTRODUCTION banner (no black box), TOC (background + dotted leaders intact), Data table, numbered list, Data Warehouse/Lake, eFootball Messi, Serial diagram, TSMC venn, CPU/GPU/TPU, ANI/AGI/ASI, chat+table, hallucination icons, QUIZ, ANNEX table, ACKNOWLEDGEMENTS. None should be missing/broken.

- [ ] **Step 4: Final full test run**

Run: `.venv/bin/pytest -q`
Expected: PASS.

---

## Self-Review

**Spec coverage:**
- Renderer `render_faithful_flow` (spec §A) → Task 1. ✓
- Endpoint serves raster stack, keeps signature/iframe contract, `lang` accepted, reflow no longer called (spec §B) → Task 2. ✓
- Asset serving unchanged (spec §C) → no task needed (existing `/assets/{filename}` serves `page-{n}.png`). ✓
- Unit + integration + manual verification (spec Testing) → Tasks 1, 2, 3. ✓
- Out of scope (B2 overlay, B3 nav, images_scale) → not in plan. ✓

Note: the spec mentioned filtering page_nums by on-disk raster existence. The plan emits all DBPage page_nums (rasters exist for every page since the extractor saves one per page; a missing raster yields a single broken `<img>`, a rare extraction-failure signal). This keeps the endpoint DB-only and testable without filesystem fixtures — same intent (only real pages emitted), simpler implementation.

**Placeholder scan:** none — all code steps are complete.

**Type consistency:** `render_faithful_flow(page_nums, image_url_base)`, `page-{n}.png`, ids `pg-{n}`, classes `fr-doc`/`fr-page`/`fr-img`, `btb-zoom` — consistent across Tasks 1–3.
