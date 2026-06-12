# Flow Polish (B3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the faithful flow: an in-document TOC navigation (hybrid: printed TOC entries mapped to pages by heading match), stronger text masking (kill edge ghosting), and a cleaned-up Gốc/Dịch mode toggle.

**Architecture:** Pure TOC helpers (`extract_toc_entries`, `map_entry_to_page`) in `toc_parser.py`; the `/flow` endpoint builds `nav=[(label, target_page)]` and `render_faithful_flow` renders a `<details class="ff-nav">` block at the top with `#pg-{n}` anchors. Masking gains a `box-shadow` ring in `_mask_css`. Frontend drops the redundant HTML(en) mode.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest; Next.js/React (frontend); CSS. Spec: `docs/superpowers/specs/2026-06-09-flow-polish-b3-design.md`. Verify doc: `2024-wttc-introduction-to-ai` (backend live on :8000; Chrome headless for screenshots).

**Working dir for backend commands:** `apps/break_the_barriers/backend`. Tests: `.venv/bin/pytest`. Frontend: `apps/break_the_barriers/frontend`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `app/services/toc_parser.py` | add `extract_toc_entries`, `map_entry_to_page` | Modify |
| `app/services/text_layer_renderer.py` (`_mask_css`) | add box-shadow ring to mask | Modify |
| `app/services/faithful_flow_renderer.py` (`render_faithful_flow`) | optional `nav` → render `ff-nav` | Modify |
| `app/routers/documents.py` (`get_document_flow`) | build nav (TOC→page) | Modify |
| `frontend/app/books/[id]/preview/page.tsx` | Gốc/Dịch toggle (drop HTML) | Modify |
| `tests/test_toc_parser.py` | unit for new helpers | Create |
| `tests/test_faithful_flow.py` | nav render + endpoint nav | Modify |
| `tests/test_text_layer_mask.py` | mask box-shadow | Modify |

**Interfaces (locked):** `extract_toc_entries(block_texts) -> list[tuple[str, str]]`; `map_entry_to_page(title, page_headings, printed_num=None) -> int|None` where `page_headings: list[tuple[int, str]]`; `render_faithful_flow(pages, translations, image_url_base, nav=None)` with `nav: list[tuple[str, int]] | None`; nav CSS classes `ff-nav`/`ff-nav-link`.

---

## Task 1: TOC helpers `extract_toc_entries` + `map_entry_to_page`

**Files:**
- Modify: `app/services/toc_parser.py`
- Test: `tests/test_toc_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_toc_parser.py
from backend.app.services.toc_parser import extract_toc_entries, map_entry_to_page


def test_extract_accepts_dots_and_spaces_skips_plain_lines():
    entries = extract_toc_entries([
        "Algorithms : The Brains of AI    8",
        "FOREWORD....3",
        "Body text with no trailing number",
        "Sub item ……  7",
    ])
    assert entries == [("Algorithms : The Brains of AI", "8"),
                       ("FOREWORD", "3"), ("Sub item", "7")]


def test_map_matches_heading_case_insensitive():
    assert map_entry_to_page("Algorithms : The Brains of AI",
                             [(8, "ALGORITHMS : THE BRAINS OF AI")]) == 8


def test_map_two_way_prefix():
    assert map_entry_to_page("Generative AI",
                             [(24, "GENERATIVE AI : MAKING THINGS UP")]) == 24


def test_map_falls_back_to_printed_number():
    assert map_entry_to_page("Nope", [(8, "Something else")], printed_num="12") == 12


def test_map_returns_none_when_no_match_no_number():
    assert map_entry_to_page("Nope", [(8, "Something else")]) is None
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_toc_parser.py -v`
Expected: FAIL — `cannot import name 'extract_toc_entries'`

- [ ] **Step 3: Append to `app/services/toc_parser.py`:**

```python
_TOC_LOOSE_RE = re.compile(
    r'^(?P<title>.*?\S)\s*(?:\.{2,}|…+|\t|\s{2,})\s*(?P<num>\d+)\s*$')


def extract_toc_entries(block_texts):
    """Ordered (title, page_num) entries from a TOC page's block texts. Looser than
    parse_toc_entry (also accepts a run of 2+ spaces as a leader) — safe because
    callers only use it on a confirmed TOC page (is_toc_page)."""
    out = []
    for t in block_texts:
        if not t:
            continue
        m = _TOC_LOOSE_RE.match(t)
        if not m:
            continue
        title = m.group("title").strip(" .…\t")
        if title:
            out.append((title, m.group("num")))
    return out


def _norm_title(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def map_entry_to_page(title, page_headings, printed_num=None):
    """Map a TOC title to a raster page_num by matching against page headings
    (normalized equality / two-way prefix). Fallback: the printed number. Else None.
    page_headings: list[(page_num, heading_text)]."""
    nt = _norm_title(title)
    if nt:
        for pnum, htext in page_headings:
            nh = _norm_title(htext)
            if nh and (nh == nt or nh.startswith(nt) or nt.startswith(nh)):
                return pnum
    if printed_num is not None:
        try:
            return int(printed_num)
        except (TypeError, ValueError):
            return None
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_toc_parser.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/toc_parser.py tests/test_toc_parser.py
git commit -m "feat(toc): extract_toc_entries + map_entry_to_page (hybrid TOC nav helpers)"
```

---

## Task 2: Mask box-shadow ring (kill edge ghosting)

**Files:**
- Modify: `app/services/text_layer_renderer.py` (`_mask_css`)
- Test: `tests/test_text_layer_mask.py` (append)

- [ ] **Step 1: Append the failing test to `tests/test_text_layer_mask.py`**

```python
def test_mask_css_adds_box_shadow_ring():
    css = _mask_css({"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    assert "box-shadow:0 0 0 3px rgba(255,255,255,0.9)" in css
```

(`_mask_css` is already imported at the top of this test file.)

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py -k box_shadow -v`
Expected: FAIL — no box-shadow in current mask CSS.

- [ ] **Step 3: Update `_mask_css`** in `app/services/text_layer_renderer.py`. Replace:

```python
def _mask_css(box) -> str:
    """CSS background that masks the original text region behind an overlaid block.
    Empty string when there is no box fill."""
    if not box or not box.get("fill"):
        return ""
    fill = _opaque_fill(box["fill"])
    pad = "padding:0 2px;" if box.get("mode") == "scrim" else ""
    return f"background:{fill};{pad}"
```

with:

```python
def _mask_css(box) -> str:
    """CSS background that masks the original text region behind an overlaid block.
    A 3px box-shadow ring of the same fill extends the mask just past the block edge
    so baked-in glyphs that overhang the bbox do not ghost through. Empty string when
    there is no box fill."""
    if not box or not box.get("fill"):
        return ""
    fill = _opaque_fill(box["fill"])
    pad = "padding:0 2px;" if box.get("mode") == "scrim" else ""
    return f"background:{fill};box-shadow:0 0 0 3px {fill};{pad}"
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_text_layer_mask.py tests/test_text_layer_l2.py tests/test_page_renderer.py tests/test_faithful_flow.py -q`
Expected: PASS (existing mask tests assert `background:rgba(...)` as a substring, still present).

- [ ] **Step 5: Commit**

```bash
git add app/services/text_layer_renderer.py tests/test_text_layer_mask.py
git commit -m "fix(mask): box-shadow ring extends mask past block edge (kill ghosting)"
```

---

## Task 3: `render_faithful_flow` nav block

**Files:**
- Modify: `app/services/faithful_flow_renderer.py`
- Test: `tests/test_faithful_flow.py` (append)

- [ ] **Step 1: Append the failing tests to `tests/test_faithful_flow.py`**

```python
def test_flow_renders_nav_when_provided():
    html = render_faithful_flow([_text_page(8)], {8: {"s1": "x"}}, "http://x/a",
                                nav=[("Mục A", 8), ("Mục B", 12)])
    assert '<details class="ff-nav"' in html
    assert 'href="#pg-8"' in html and "Mục A" in html
    assert 'href="#pg-12"' in html and "Mục B" in html


def test_flow_no_nav_by_default():
    html = render_faithful_flow([_text_page(1)], {1: {"s1": "x"}}, "http://x/a")
    assert 'class="ff-nav"' not in html
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -k nav -v`
Expected: FAIL — `render_faithful_flow() got an unexpected keyword argument 'nav'`

- [ ] **Step 3: Implement.** In `app/services/faithful_flow_renderer.py`, add the nav CSS to `_CSS` (append these rules inside the `_CSS` string):

```css
.ff-nav { max-width: 900px; margin: 0 auto 16px; background: #fff; border-radius: 2px;
          box-shadow: 0 2px 14px rgba(0,0,0,.25); padding: 12px 18px;
          font-family: 'Be Vietnam Pro', system-ui, sans-serif; color: #1a1a1a; }
.ff-nav summary { cursor: pointer; font-weight: 700; margin-bottom: 6px; }
.ff-nav-link { display: block; color: #1a1a1a; text-decoration: none; padding: 3px 0;
               border-bottom: 1px solid #f0f0f0; }
.ff-nav-link:hover { text-decoration: underline; }
```

Then change the `render_faithful_flow` signature + body:

```python
def render_faithful_flow(pages: List[PageModel], translations: Dict[int, dict],
                         image_url_base: str, nav=None) -> str:
    nav_html = ""
    if nav:
        links = "".join(
            f'<a class="ff-nav-link" href="#pg-{int(tp)}">{html_lib.escape(label)}</a>'
            for label, tp in nav)
        nav_html = ('<details class="ff-nav" open><summary>Mục lục</summary>'
                    f'{links}</details>')
    body = "".join(
        render_faithful_page(p, (translations or {}).get(p.page_num, {}), image_url_base)
        for p in sorted(pages, key=lambda m: m.page_num))
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_GOOGLE_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="ff-doc">{nav_html}{body}</article>{_SCRIPT}</body></html>'
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -v`
Expected: PASS (all flow tests, incl. nav).

- [ ] **Step 5: Commit**

```bash
git add app/services/faithful_flow_renderer.py tests/test_faithful_flow.py
git commit -m "feat(flow): render in-document TOC nav block (ff-nav)"
```

---

## Task 4: Endpoint builds the TOC nav

**Files:**
- Modify: `app/routers/documents.py` (`get_document_flow`)
- Test: `tests/test_faithful_flow.py` (append endpoint test)

- [ ] **Step 1: Append the failing integration test to `tests/test_faithful_flow.py`**

```python
def test_flow_endpoint_builds_toc_nav(client, db_session):
    import json
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="navdoc", filename="f.pdf", total_pages=3, status="translated"))
    # page 1 = TOC (3 entries), page 8-like content lives on raster page_num 2 & 3
    toc = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
           "background": {"color": "#fff", "image": None},
           "blocks": [{"span_id": f"e{i}", "role": "body", "bbox": [72, 100 + i * 20, 300, 14],
                       "text": "", "font": {"size": 11, "weight": 400, "italic": False,
                                            "color": "#000", "align": "left", "family_class": "sans"}}
                      for i in range(2)],
           "figures": [], "page_class": "text", "cover": "none"}
    content = lambda hid: {"page_w": 595.0, "page_h": 842.0, "kind": "text",
                           "background": {"color": "#fff", "image": None},
                           "blocks": [{"span_id": hid, "role": "heading", "bbox": [72, 40, 300, 28],
                                       "text": "", "font": {"size": 28, "weight": 700, "italic": False,
                                                            "color": "#000", "align": "left", "family_class": "sans"}}],
                           "figures": [], "page_class": "text", "cover": "none"}
    db_session.add(DBPage(document_id="navdoc", page_num=1, status="translated", model_json=json.dumps(toc)))
    db_session.add(DBPage(document_id="navdoc", page_num=2, status="translated", model_json=json.dumps(content("h2"))))
    db_session.add(DBPage(document_id="navdoc", page_num=3, status="translated", model_json=json.dumps(content("h3"))))
    # TOC entries (original text with dotted leaders) → titles match the headings
    db_session.add(DBTranslation(document_id="navdoc", page_num=1, span_id="e0",
                                 original_text="Alpha Section.....2", translated_text="Phần Alpha....2"))
    db_session.add(DBTranslation(document_id="navdoc", page_num=1, span_id="e1",
                                 original_text="Beta Section.....3", translated_text="Phần Beta....3"))
    db_session.add(DBTranslation(document_id="navdoc", page_num=2, span_id="h2",
                                 original_text="Alpha Section", translated_text="Phần Alpha"))
    db_session.add(DBTranslation(document_id="navdoc", page_num=3, span_id="h3",
                                 original_text="Beta Section", translated_text="Phần Beta"))
    db_session.commit()
    r = client.get("/api/docs/navdoc/flow?lang=vi")
    assert r.status_code == 200
    assert '<details class="ff-nav"' in r.text
    assert 'href="#pg-2"' in r.text and 'href="#pg-3"' in r.text
    assert "Phần Alpha" in r.text and "Phần Beta" in r.text
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -k toc_nav -v`
Expected: FAIL — endpoint passes no nav, so `ff-nav` absent.

- [ ] **Step 3: Update `get_document_flow`** in `app/routers/documents.py`. Replace the body from the `rows = db.query(DBTranslation)...` line through the `html = render_faithful_flow(...)` line with:

```python
    from backend.app.services.toc_parser import (
        is_toc_page, extract_toc_entries, map_entry_to_page)

    rows = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id).all()
    translations: dict = {}
    orig: dict = {}
    for t in rows:
        txt = (t.original_text if lang == "en" else t.translated_text) or ""
        translations.setdefault(t.page_num, {})[t.span_id] = txt
        orig.setdefault(t.page_num, {})[t.span_id] = t.original_text or ""

    # Hybrid TOC nav: list from the printed TOC, target page resolved by heading match.
    page_headings: list = []          # (page_num, original heading text)
    thead: dict = {}                  # page_num -> translated heading (nav label)
    for pm in pages:
        o = orig.get(pm.page_num, {})
        tm = translations.get(pm.page_num, {})
        for b in pm.blocks:
            if b.role == "heading":
                oh = o.get(b.span_id, "")
                if oh:
                    page_headings.append((pm.page_num, oh))
                if pm.page_num not in thead:
                    th = tm.get(b.span_id, "") or oh
                    if th:
                        thead[pm.page_num] = th
    nav = None
    for pm in pages:
        o = orig.get(pm.page_num, {})
        texts = [o.get(b.span_id, "") for b in pm.blocks]
        if is_toc_page(texts):
            nav = []
            for title, num in extract_toc_entries(texts):
                target = map_entry_to_page(title, page_headings, num)
                if target is not None:
                    nav.append((thead.get(target, title), target))
            break

    image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
    html = render_faithful_flow(pages, translations, image_base, nav=nav)
    return HTMLResponse(content=html)
```

(Keep the earlier part of the function — doc lookup, page_rows, building `pages` from model_json — unchanged.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_faithful_flow.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add app/routers/documents.py tests/test_faithful_flow.py
git commit -m "feat(flow): /flow builds hybrid TOC nav (printed entries → page by heading)"
```

---

## Task 5: Frontend — Gốc/Dịch mode cleanup

**Files:**
- Modify: `frontend/app/books/[id]/preview/page.tsx`

No automated frontend tests exist in this repo; verify by reading the diff + the manual browser check in Task 6. Make these exact edits.

- [ ] **Step 1: Narrow the `Lang` type.** Change:

```tsx
type Lang = "pdf" | "en" | "vi"
```
to
```tsx
type Lang = "pdf" | "vi"
```

- [ ] **Step 2: Update `flowLang`.** Change:

```tsx
// Whole-document flow only renders en|vi (no per-page PDF). Coerce pdf -> vi.
function flowLang(l: Lang): "en" | "vi" {
  return l === "pdf" ? "vi" : l
}
```
to
```tsx
// Flow has no whole-document PDF, so "Gốc" in flow = the faithful original render
// (raster + original-text overlay = lang "en"); "Dịch" = "vi".
function flowLang(l: Lang): "en" | "vi" {
  return l === "pdf" ? "en" : "vi"
}
```

- [ ] **Step 3: Default to Dịch.** Change `const [lang, setLang] = useState<Lang>("en")` to:

```tsx
  const [lang, setLang] = useState<Lang>("vi")
```

- [ ] **Step 4: Fix localStorage restore.** Change:

```tsx
    if (savedLang && ["pdf", "en", "vi"].includes(savedLang)) setLang(savedLang as Lang)
```
to
```tsx
    if (savedLang === "en") setLang("pdf")           // legacy HTML mode → Gốc
    else if (savedLang && ["pdf", "vi"].includes(savedLang)) setLang(savedLang as Lang)
```

- [ ] **Step 5: Drop the flow→pdf coercion in `changeLayout`.** Find and remove:

```tsx
    // Flow can't show the original PDF; if Gốc was selected, fall back to Dịch.
    if (l === "flow" && lang === "pdf") changeLang("vi")
```
(Delete those two lines — flow now renders Gốc as the faithful `en` view via `flowLang`.)

- [ ] **Step 6: Replace the lang toggle (3 buttons → 2).** Replace:

```tsx
          <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
            <button onClick={() => changeLang("pdf")}
                    disabled={layout === "flow"}
                    className={`px-3 py-1 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${lang === "pdf" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Gốc
            </button>
            <button onClick={() => changeLang("en")}
                    className={`px-3 py-1 text-xs font-medium ${lang === "en" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              HTML
            </button>
            <button onClick={() => changeLang("vi")}
                    disabled={!canTranslated}
                    className={`px-3 py-1 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${lang === "vi" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Dịch
            </button>
          </div>
```

with:

```tsx
          <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
            <button onClick={() => changeLang("pdf")}
                    className={`px-3 py-1 text-xs font-medium ${lang === "pdf" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Gốc
            </button>
            <button onClick={() => changeLang("vi")}
                    disabled={!canTranslated}
                    className={`px-3 py-1 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${lang === "vi" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Dịch
            </button>
          </div>
```

- [ ] **Step 7: Commit**

```bash
git add frontend/app/books/[id]/preview/page.tsx
git commit -m "feat(ui): collapse mode toggle to Gốc/Dịch (drop redundant HTML mode)"
```

---

## Task 6: Verification (Chrome headless)

**Files:** none. Backend must be running on :8000 (`/start-dev` if not).

- [ ] **Step 1: Render the WTTC flow and screenshot the top (nav) + a dense page**

```bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
URL="http://localhost:8000/api/docs/2024-wttc-introduction-to-ai/flow?lang=vi"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=960,1400 --virtual-time-budget=8000 \
  --screenshot=/tmp/b3_nav.png "$URL"
ls -la /tmp/b3_nav.png
```
Read `/tmp/b3_nav.png` and confirm the `Mục lục` nav block renders at the top with section links.

- [ ] **Step 2: Confirm nav anchors + no ghosting** by rendering a single dense page fragment (reuse the B2.2 verification recipe) for p38, screenshot, and confirm the right-edge ghosting is gone (mask box-shadow). Compare against the B2.2 capture if available.

- [ ] **Step 3: Backend full test run**

Run (from backend): `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 4: Manual frontend check**

Start the frontend (`/start-dev`), open the preview: confirm the toggle shows only **Gốc / Dịch**; flow defaults to Dịch; switching to Gốc in flow shows the faithful original (not broken); reader Gốc still shows the PDF.

---

## Self-Review

**Spec coverage:**
- B3a `extract_toc_entries` + `map_entry_to_page` (spec §B3a) → Task 1. ✓
- B3a nav render in flow (spec §B3a) → Task 3. ✓
- B3a endpoint builds nav, hybrid mapping, translated labels (spec §B3a) → Task 4. ✓
- B3c mask box-shadow (spec §B3c) → Task 2. ✓
- B3b frontend Gốc/Dịch (spec §B3b) → Task 5. ✓
- Verification (Chrome + manual) → Task 6. ✓
- Out of scope (inpaint, React sidebar/scrollspy) → not in plan. ✓

**Placeholder scan:** none — all code steps complete.

**Type consistency:** `extract_toc_entries(block_texts)->[(title,num)]`; `map_entry_to_page(title, page_headings:[(page_num,text)], printed_num)`; `render_faithful_flow(pages, translations, image_url_base, nav=[(label,target)])`; nav classes `ff-nav`/`ff-nav-link`; `Lang = "pdf"|"vi"`, `flowLang` returns `"en"|"vi"`. Consistent across Tasks 1–6.
