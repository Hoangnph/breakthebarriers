# Frontend Flow View (F3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the whole-document flow (`GET /api/docs/{id}/flow`) the default preview view, surfaced through one unified view switcher with lang + zoom shared across all views.

**Architecture:** Extend the existing `Layout` switcher in `preview/page.tsx` with a 4th option `"flow"` (default), rendered by a new `LayoutFlow` iframe component pointing at `/flow?lang=`. Lang toggle and zoom stay shared (Gốc disabled in flow); per-page editing tools hide in flow. A tiny `<script>` added to `render_flow_html` makes the flow respond to the existing `btb-zoom` postMessage by scaling root font-size.

**Tech Stack:** Next.js 14 (App Router, client component), TypeScript, Tailwind, lucide-react; backend FastAPI + `render_flow_html` (pytest).

---

## Spec

`docs/superpowers/specs/2026-06-07-document-flow-f3-design.md`

## File Structure

- **Backend** `apps/break_the_barriers/backend/app/services/flow_renderer.py` — add `_ZOOM_SCRIPT` constant + inject before `</body>`. Test: `tests/test_flow_renderer.py`.
- **Frontend** `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutFlow.tsx` — NEW. Full-height iframe to `/flow?lang=`, forwards zoom on load.
- **Frontend** `apps/break_the_barriers/frontend/app/books/[id]/preview/page.tsx` — extend `Layout` type + `LAYOUT_ICONS`, default `"flow"`, `flowLang` helper, render `LayoutFlow`, share lang/zoom, hide per-page tools + clean-bg + panel in flow, counter shows total in flow.

**Commands:** backend test from `apps/break_the_barriers/backend` with `.venv/bin/pytest`; frontend typecheck/lint from `apps/break_the_barriers/frontend` (`npx tsc --noEmit`, `npm run lint`). Git from repo root `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`. Branch `feat/document-flow` (already checked out — KHÔNG tạo nhánh). Backend imports `backend.app...`.

**Note on frontend testing:** the frontend has **no unit-test runner** (`package.json` scripts: dev/build/start/lint only). Frontend tasks are verified by TypeScript typecheck (`npx tsc --noEmit`) + ESLint (`npm run lint`) + manual live check (Task 4). Do NOT add a test runner (YAGNI).

---

### Task 1: Backend — flow responds to btb-zoom (font-size scaling)

**Files:**
- Modify: `apps/break_the_barriers/backend/app/services/flow_renderer.py`
- Test: `apps/break_the_barriers/backend/tests/test_flow_renderer.py` (bổ sung)

- [ ] **Step 1: Write the failing test** — append to `tests/test_flow_renderer.py`:

```python
def test_flow_html_has_zoom_listener():
    html = render_flow_html([FlowElement(kind="paragraph", span_id="p")],
                            {"p": "x"}, image_url_base="http://api/a")
    assert "btb-zoom" in html
    assert "documentElement.style.fontSize" in html
    assert "addEventListener('message'" in html
    # script sits inside the body, after the article
    assert html.index("fl-doc") < html.index("btb-zoom") < html.index("</body>")
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `apps/break_the_barriers/backend`): `.venv/bin/pytest tests/test_flow_renderer.py::test_flow_html_has_zoom_listener -v`
Expected: FAIL (`btb-zoom` not in html).

- [ ] **Step 3: Add the script constant** — in `app/services/flow_renderer.py`, immediately after the `_CSS = """ ... """` block (before the `_clamp_level` helper), add:

```python
_ZOOM_SCRIPT = (
    "<script>window.addEventListener('message',function(e){"
    "var d=e.data||{};"
    "if(d.type==='btb-zoom'&&typeof d.zoom==='number'){"
    "document.documentElement.style.fontSize=(d.zoom*100)+'%';}"
    "});</script>"
)
```

- [ ] **Step 4: Inject the script before `</body>`** — in `render_flow_html`, change the final return so the article is followed by `_ZOOM_SCRIPT`:

```python
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="fl-doc">{"".join(parts)}</article>'
        f'{_ZOOM_SCRIPT}</body></html>'
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_flow_renderer.py -v`
Expected: PASS — the new test plus all existing renderer tests (11 prior + 1 = 12).

- [ ] **Step 6: Regression**

Run: `.venv/bin/pytest tests/test_flow_model.py tests/test_flow_renderer.py tests/test_preview_pagemodel.py -q`
Expected: all pass.

- [ ] **Step 7: Commit** (from repo root)

```bash
git add apps/break_the_barriers/backend/app/services/flow_renderer.py \
        apps/break_the_barriers/backend/tests/test_flow_renderer.py
git commit -m "feat(F3): flow document responds to btb-zoom (root font-size scaling)"
```

---

### Task 2: Frontend — LayoutFlow component + flowLang helper

**Files:**
- Create: `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutFlow.tsx`

- [ ] **Step 1: Create the component** — write `app/books/[id]/preview/LayoutFlow.tsx`:

```tsx
export interface FlowLayoutProps {
  docId: string
  apiUrl: string
  lang: "en" | "vi"
  zoom: number
}

export default function LayoutFlow({ docId, apiUrl, lang, zoom }: FlowLayoutProps) {
  const src = `${apiUrl}/api/docs/${docId}/flow?lang=${lang}`
  return (
    <main className="flex-1 min-h-0 bg-[#f4f4f5]">
      <iframe
        key={lang}
        src={src}
        className="w-full h-full border-none block"
        title="Tài liệu liền mạch"
        sandbox="allow-same-origin allow-scripts"
        onLoad={(e) =>
          e.currentTarget.contentWindow?.postMessage({ type: "btb-zoom", zoom }, "*")
        }
      />
    </main>
  )
}
```

- [ ] **Step 2: Typecheck**

Run (from `apps/break_the_barriers/frontend`): `npx tsc --noEmit`
Expected: no errors (component is self-contained; `FlowLayoutProps` fully typed).

- [ ] **Step 3: Lint**

Run: `npm run lint`
Expected: no new lint errors for `LayoutFlow.tsx`.

- [ ] **Step 4: Commit** (from repo root)

```bash
git add apps/break_the_barriers/frontend/app/books/\[id\]/preview/LayoutFlow.tsx
git commit -m "feat(F3): add LayoutFlow iframe component (whole-document flow view)"
```

---

### Task 3: Frontend — unified switcher + flow render + shared/contextual controls

**Files:**
- Modify: `apps/break_the_barriers/frontend/app/books/[id]/preview/page.tsx`

All edits are exact string replacements against the current file. Apply in order.

- [ ] **Step 1: Import the icon + component.** Replace line 5:

```tsx
import { ArrowLeft, AlignJustify, LayoutTemplate, Columns2, ZoomIn, ZoomOut, type LucideIcon } from "lucide-react"
```
with:
```tsx
import { ArrowLeft, AlignJustify, LayoutTemplate, Columns2, ScrollText, ZoomIn, ZoomOut, type LucideIcon } from "lucide-react"
```
Then add an import for the new component alongside the other layout imports (after the `import LayoutSplit from "./LayoutSplit"` line):
```tsx
import LayoutFlow from "./LayoutFlow"
```

- [ ] **Step 2: Extend the `Layout` type.** Replace:
```tsx
type Layout = "reader" | "sidebar" | "split"
```
with:
```tsx
type Layout = "flow" | "reader" | "sidebar" | "split"
```

- [ ] **Step 3: Add `flow` to `LAYOUT_ICONS`.** Replace the `LAYOUT_ICONS` object:
```tsx
const LAYOUT_ICONS: Record<Layout, { icon: LucideIcon; label: string }> = {
  reader:  { icon: AlignJustify,   label: "Reader" },
  sidebar: { icon: LayoutTemplate, label: "Sidebar" },
  split:   { icon: Columns2,       label: "Split" },
}
```
with:
```tsx
const LAYOUT_ICONS: Record<Layout, { icon: LucideIcon; label: string }> = {
  flow:    { icon: ScrollText,     label: "Liền mạch" },
  reader:  { icon: AlignJustify,   label: "Reader" },
  sidebar: { icon: LayoutTemplate, label: "Sidebar" },
  split:   { icon: Columns2,       label: "Split" },
}

// Whole-document flow only renders en|vi (no per-page PDF). Coerce pdf -> vi.
function flowLang(l: Lang): "en" | "vi" {
  return l === "pdf" ? "vi" : l
}
```

- [ ] **Step 4: Default layout to `flow`.** Replace line 45:
```tsx
  const [layout, setLayout] = useState<Layout>("reader")
```
with:
```tsx
  const [layout, setLayout] = useState<Layout>("flow")
```

- [ ] **Step 5: Accept saved `flow`.** Replace line 163:
```tsx
    if (savedLayout && ["reader", "sidebar", "split"].includes(savedLayout)) setLayout(savedLayout)
```
with:
```tsx
    if (savedLayout && ["flow", "reader", "sidebar", "split"].includes(savedLayout)) setLayout(savedLayout)
```

- [ ] **Step 6: Coerce lang when entering flow.** Replace `changeLayout`:
```tsx
  function changeLayout(l: Layout) {
    setLayout(l)
    localStorage.setItem(LAYOUT_KEY, l)
  }
```
with:
```tsx
  function changeLayout(l: Layout) {
    setLayout(l)
    localStorage.setItem(LAYOUT_KEY, l)
    // Flow can't show the original PDF; if Gốc was selected, fall back to Dịch.
    if (l === "flow" && lang === "pdf") changeLang("vi")
  }
```

- [ ] **Step 7: Disable "Gốc" in flow (shared lang toggle).** The lang toggle block is guarded by `{layout !== "split" && (` at line 283 — keep that (flow shows the toggle). Replace the "Gốc" button (lines 285-288):
```tsx
            <button onClick={() => changeLang("pdf")}
                    className={`px-3 py-1 text-xs font-medium ${lang === "pdf" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Gốc
            </button>
```
with:
```tsx
            <button onClick={() => changeLang("pdf")}
                    disabled={layout === "flow"}
                    className={`px-3 py-1 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${lang === "pdf" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Gốc
            </button>
```

- [ ] **Step 8: Hide clean-bg buttons in flow.** Replace the clean-bg condition (line 302):
```tsx
        {(pageMeta.policy_override === "clean-photo" || (pageMeta.policy_override == null && (pageMeta.cover === "front" || pageMeta.cover === "back"))) && (
```
with:
```tsx
        {layout !== "flow" && (pageMeta.policy_override === "clean-photo" || (pageMeta.policy_override == null && (pageMeta.cover === "front" || pageMeta.cover === "back"))) && (
```

- [ ] **Step 9: Switcher renders all four (flow first).** Replace the switcher map (line 333):
```tsx
          {(["reader", "sidebar", "split"] as Layout[]).map((key) => {
```
with:
```tsx
          {(["flow", "reader", "sidebar", "split"] as Layout[]).map((key) => {
```

- [ ] **Step 10: Counter shows total in flow.** Replace the counter (lines 359-361):
```tsx
        <span className="text-xs text-gray-400 flex-shrink-0">
          {currentPage}/{doc.total_pages}
        </span>
```
with:
```tsx
        <span className="text-xs text-gray-400 flex-shrink-0">
          {layout === "flow" ? `${doc.total_pages} trang` : `${currentPage}/${doc.total_pages}`}
        </span>
```

- [ ] **Step 11: Hide per-page panel in flow.** Wrap the per-page control panel. Replace its opening (lines 364-365):
```tsx
      {/* Per-page control panel */}
      <div className="bg-white border-b border-gray-100 px-4 py-2 flex flex-wrap items-center gap-x-6 gap-y-2 flex-shrink-0">
```
with:
```tsx
      {/* Per-page control panel — per-page editing tools, hidden in flow */}
      {layout !== "flow" && (
      <div className="bg-white border-b border-gray-100 px-4 py-2 flex flex-wrap items-center gap-x-6 gap-y-2 flex-shrink-0">
```
Then close the conditional: the panel `</div>` is at line 410. Replace that closing `</div>` (the one immediately before the `<div className="flex-1 min-h-0 ...">` block) with:
```tsx
      </div>
      )}
```

- [ ] **Step 12: Render LayoutFlow.** Replace the content render block (lines 412-416):
```tsx
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {layout === "reader"  && <LayoutReader  {...contentProps} />}
        {layout === "sidebar" && <LayoutSidebar {...contentProps} onTranslate={translatePage} />}
        {layout === "split"   && <LayoutSplit   {...splitProps} />}
      </div>
```
with:
```tsx
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {layout === "flow"    && <LayoutFlow docId={id} apiUrl={API_URL} lang={flowLang(lang)} zoom={zoom} />}
        {layout === "reader"  && <LayoutReader  {...contentProps} />}
        {layout === "sidebar" && <LayoutSidebar {...contentProps} onTranslate={translatePage} />}
        {layout === "split"   && <LayoutSplit   {...splitProps} />}
      </div>
```

- [ ] **Step 13: Typecheck**

Run (from `apps/break_the_barriers/frontend`): `npx tsc --noEmit`
Expected: no errors. (`flowLang` returns `"en" | "vi"` matching `LayoutFlow`'s `lang` prop; `Layout` union covers all switch arms.)

- [ ] **Step 14: Lint**

Run: `npm run lint`
Expected: no new errors/warnings introduced by the change.

- [ ] **Step 15: Commit** (from repo root)

```bash
git add apps/break_the_barriers/frontend/app/books/\[id\]/preview/page.tsx
git commit -m "feat(F3): flow as default view via unified switcher; share lang/zoom, hide per-page tools in flow"
```

---

### Task 4: Live verification (controller — manual)

**Files:** none.

- [ ] **Step 1: Ensure servers run.** Backend on :8000 (`--reload` picks up Task 1). Frontend on :3000 (`npm run dev`). If not running, start them (backend: `.venv/bin/uvicorn app.main:app --reload --port 8000` from backend dir; frontend: `npm run dev` from frontend dir).

- [ ] **Step 2: Default + switcher.** Open `http://localhost:3000/books/2024-wttc-introduction-to-ai/preview`. Confirm: default view is **Liền mạch** (flow iframe), switcher shows 4 buttons with Liền mạch first/active. Click Reader → per-page returns (panel + counter `n/44` reappear); click Liền mạch → flow returns, counter shows `44 trang`, panel hidden.

- [ ] **Step 3: Lang + Gốc disabled.** In flow, confirm "Gốc" is disabled (greyed). Toggle HTML↔Dịch → iframe reloads `/flow?lang=en|vi` (check Network or visible language change).

- [ ] **Step 4: Contents nav + zoom.** Click an entry in the in-document mục lục → page scrolls to that section inside the iframe. Click zoom + / − → flow text grows/shrinks (root font-size). 

- [ ] **Step 5: Screenshots.** Chrome headless (`--force-device-scale-factor=1`) screenshot of the flow-default preview and one after zoom-in. Read them to confirm; report findings to the controller. (Frontend page needs auth — if the headless shot hits the login wall, screenshot the backend `/flow` endpoint directly as a fallback and verify the zoom `<script>` via `curl … | grep btb-zoom`.)

---

## Self-Review

**Spec coverage:**
- A — Flow folded into single view switcher, type `"flow"|...`, reuse `btb_preview_layout`, default flow → Task 3 Steps 2,3,4,5,9. ✓
- B — shared lang 3-button (Gốc disabled in flow) + shared zoom + flowLang coercion → Task 3 Steps 3,6,7; zoom shared via existing broadcast effect + LayoutFlow onLoad (Task 2) + Task 1 backend script. ✓
- B2 — counter total in flow, clean-bg + per-page panel hidden in flow → Task 3 Steps 8,10,11. ✓
- C — LayoutFlow iframe to `/flow?lang=`, key reload, sandbox, onLoad zoom → Task 2. ✓
- D — render_flow_html btb-zoom → font-size; zoom button visible in flow → Task 1 + Task 3 (zoom controls untouched, always rendered). ✓
- Testing — backend pytest (Task 1), tsc + lint (Tasks 2,3), manual + screenshots (Task 4). ✓
- Out of scope (sidebar/scrollspy, F4 editing on flow, whole-doc PDF, scroll↔page sync) — not implemented. ✓

**Placeholder scan:** no TBD/TODO; every step has exact code or command + expected output. ✓

**Type consistency:**
- `Layout = "flow"|"reader"|"sidebar"|"split"` used in state, restore list, switcher map, render arms, `LAYOUT_ICONS`. ✓
- `flowLang(l: Lang) -> "en"|"vi"` feeds `LayoutFlow` prop `lang: "en"|"vi"`. ✓
- `FlowLayoutProps {docId, apiUrl, lang, zoom}` matches the render call `docId={id} apiUrl={API_URL} lang={flowLang(lang)} zoom={zoom}`. ✓
- Backend `_ZOOM_SCRIPT` referenced exactly in `render_flow_html` return. ✓
