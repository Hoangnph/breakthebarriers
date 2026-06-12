# Faithful Text-Layer Reconstruction — SP-A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rich PageModel (docling semantics + PyMuPDF fonts + cropped figures) and render translated **text pages** as real HTML/CSS (no raster, no opaque boxes), while image pages keep their raster — wired into the existing side-by-side preview.

**Architecture:** A new `PageModel` JSON sidecar (`{doc_id}-{page_no}.model.json`) becomes the single source of truth. Pure-function services (typography aggregation, figure crop, page classification, text fitting) feed a `page_renderer` dispatcher that picks a handler by `kind` (text → HTML text-layer; image/mixed → existing `render_overlay_html`). The preview endpoint prefers `model_json` and falls back to today's `layout_json` path.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, docling, PyMuPDF (`fitz`), Pillow, pytest. All paths below are relative to `apps/break_the_barriers/backend/` unless noted.

---

## File Structure

| File | Responsibility | New? |
|---|---|---|
| `app/services/page_model.py` | Dataclasses `FontSpec/Block/Figure/PageModel` + JSON (de)serialize | Create |
| `app/services/typography_extractor.py` | PyMuPDF font extraction; pure helpers (font→class, color, bold/italic, IoU, aggregate) | Create |
| `app/services/figure_extractor.py` | Crop `picture` bbox from page raster → PNG | Create |
| `app/services/page_classifier.py` | Classify page `kind` (text/image/mixed) from area ratios | Create |
| `app/services/text_fitter.py` | Fit font size (measure-based estimate + priority chain) | Create |
| `app/services/text_layer_renderer.py` | Render text-page `PageModel` → HTML (flow + absolute modes) | Create |
| `app/services/page_renderer.py` | Dispatcher: pick renderer by `kind` | Create |
| `app/services/extractor.py` | Build & write `.model.json` in `DoclingExtractor` | Modify |
| `app/models_db.py` | Add `DBPage.model_json` column | Modify |
| `app/routers/extraction.py` | Load `.model.json` into `model_json` column | Modify |
| `app/routers/documents.py` | Preview endpoint prefers `model_json` → `page_renderer` | Modify |
| `requirements.txt` | Add `pymupdf` | Modify |
| `tests/test_page_model.py` … `tests/test_page_renderer.py` | Unit + integration tests | Create |

---

## Task 0: Add PyMuPDF dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the dependency line**

Add to `requirements.txt` (after the `docling>=2.0.0` line):

```
pymupdf>=1.24.0
```

- [ ] **Step 2: Install into the venv**

Run: `.venv/bin/pip install "pymupdf>=1.24.0"`
Expected: ends with `Successfully installed PyMuPDF-...`

- [ ] **Step 3: Verify import**

Run: `.venv/bin/python -c "import fitz; print(fitz.__doc__.splitlines()[0])"`
Expected: a line starting with `PyMuPDF` (no `ModuleNotFoundError`).

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build(sp-a): add PyMuPDF for typography extraction"
```

---

## Task 1: PageModel data contract

**Files:**
- Create: `app/services/page_model.py`
- Test: `tests/test_page_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_page_model.py
import json
from backend.app.services.page_model import FontSpec, Block, Figure, PageModel


def test_pagemodel_roundtrip_with_font():
    m = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#ffffff", "image": None},
        blocks=[Block(
            span_id="s1", role="heading", bbox=[72.0, 40.0, 200.0, 24.0],
            text="Hello",
            font=FontSpec(size=24.0, weight=700, italic=False,
                          color="#1a1a1a", align="left", family_class="sans"),
        )],
        figures=[Figure(bbox=[0.0, 0.0, 595.0, 300.0], img="d-1-fig1.png")],
    )
    restored = PageModel.from_json(m.to_json())
    assert restored.kind == "text"
    assert restored.blocks[0].font.weight == 700
    assert restored.blocks[0].font.family_class == "sans"
    assert restored.figures[0].img == "d-1-fig1.png"
    # to_json must be valid JSON
    assert json.loads(m.to_json())["page_w"] == 595.0


def test_pagemodel_roundtrip_font_none():
    m = PageModel(page_w=1.0, page_h=1.0, kind="image",
                  background={"color": "#000000", "image": "page-1.png"},
                  blocks=[Block(span_id="s2", role="body", bbox=[0, 0, 1, 1],
                                text="x", font=None)],
                  figures=[])
    restored = PageModel.from_json(m.to_json())
    assert restored.blocks[0].font is None
    assert restored.background["image"] == "page-1.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_page_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.services.page_model'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/page_model.py
"""PageModel: the rich intermediate representation that is the single source of
truth for both preview rendering and (future SP-B) export."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


@dataclass
class FontSpec:
    size: float            # points, in page-point space
    weight: int            # 400 normal, 700 bold
    italic: bool
    color: str             # "#rrggbb"
    align: str             # left|center|right|justify
    family_class: str      # serif|sans|mono


@dataclass
class Block:
    span_id: str
    role: str              # heading|body|list|code|table|caption
    bbox: List[float]      # [l, t, w, h] top-left points
    text: str
    font: Optional[FontSpec]


@dataclass
class Figure:
    bbox: List[float]      # [l, t, w, h] top-left points
    img: str               # filename only


@dataclass
class PageModel:
    page_w: float
    page_h: float
    kind: str              # text|image|mixed
    background: Dict[str, Any]   # {"color": "#rrggbb", "image": filename|None}
    blocks: List[Block]
    figures: List[Figure]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_w": self.page_w, "page_h": self.page_h, "kind": self.kind,
            "background": self.background,
            "blocks": [asdict(b) for b in self.blocks],
            "figures": [asdict(f) for f in self.figures],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PageModel":
        blocks = []
        for b in d.get("blocks", []):
            f = b.get("font")
            blocks.append(Block(
                span_id=b["span_id"], role=b.get("role", "body"),
                bbox=list(b["bbox"]), text=b.get("text", ""),
                font=FontSpec(**f) if f else None,
            ))
        figures = [Figure(bbox=list(f["bbox"]), img=f["img"]) for f in d.get("figures", [])]
        return cls(
            page_w=d["page_w"], page_h=d["page_h"], kind=d.get("kind", "text"),
            background=d.get("background", {"color": "#ffffff", "image": None}),
            blocks=blocks, figures=figures,
        )

    @classmethod
    def from_json(cls, s: str) -> "PageModel":
        return cls.from_dict(json.loads(s))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_page_model.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/page_model.py tests/test_page_model.py
git commit -m "feat(sp-a): PageModel data contract + JSON roundtrip"
```

---

## Task 2: TypographyExtractor pure helpers

Pure, fully-unit-testable helpers. The PyMuPDF I/O wrapper (next task's note) is thin and covered by the integration test in Task 9.

**Files:**
- Create: `app/services/typography_extractor.py`
- Test: `tests/test_typography_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_typography_extractor.py
from backend.app.services.typography_extractor import (
    classify_font_family, int_color_to_hex, is_bold, is_italic, iou, aggregate_font,
)
from backend.app.services.page_model import FontSpec


def test_classify_font_family():
    assert classify_font_family("Courier New") == "mono"
    assert classify_font_family("JetBrainsMono-Regular") == "mono"
    assert classify_font_family("TimesNewRomanPSMT") == "serif"
    assert classify_font_family("Georgia") == "serif"
    assert classify_font_family("Helvetica-Bold") == "sans"
    assert classify_font_family("ArialMT") == "sans"
    assert classify_font_family("") == "sans"  # default


def test_int_color_to_hex():
    assert int_color_to_hex(0) == "#000000"
    assert int_color_to_hex(0xFFFFFF) == "#ffffff"
    assert int_color_to_hex(0x1A1A1A) == "#1a1a1a"


def test_bold_italic_flags():
    # PyMuPDF span flags: bit 2^4 (16) = bold, bit 2^1 (2) = italic
    assert is_bold(16) is True
    assert is_bold(0) is False
    assert is_italic(2) is True
    assert is_italic(0) is False


def test_iou():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [100, 100, 10, 10]) == 0.0
    # half overlap on x
    assert round(iou([0, 0, 10, 10], [5, 0, 10, 10]), 3) == round(50 / 150, 3)


def test_aggregate_font_picks_dominant():
    spans = [
        {"size": 24.0, "flags": 16, "color": 0x1A1A1A, "font": "Helvetica-Bold"},
        {"size": 24.0, "flags": 16, "color": 0x1A1A1A, "font": "Helvetica-Bold"},
        {"size": 11.0, "flags": 0,  "color": 0x000000, "font": "Helvetica"},
    ]
    fs = aggregate_font(spans, align="center")
    assert isinstance(fs, FontSpec)
    assert fs.size == 24.0           # most common size
    assert fs.weight == 700          # majority bold
    assert fs.italic is False
    assert fs.color == "#1a1a1a"
    assert fs.align == "center"
    assert fs.family_class == "sans"


def test_aggregate_font_empty_returns_none():
    assert aggregate_font([], align="left") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_typography_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/typography_extractor.py
"""Extract real typography (font size/weight/italic/color/align) per text block
using PyMuPDF, mapping PDF font names to coarse family classes.

Pure helpers are unit-tested; extract_page_fonts (PyMuPDF I/O) is covered by the
extractor integration test."""
from __future__ import annotations
import logging
from collections import Counter
from typing import List, Dict, Optional

from backend.app.services.page_model import FontSpec

logger = logging.getLogger(__name__)

_MONO_HINTS = ("mono", "courier", "consol", "menlo", "jetbrains")
_SERIF_HINTS = ("times", "serif", "georgia", "minion", "garamond", "roman")


def classify_font_family(font_name: str) -> str:
    n = (font_name or "").lower()
    if any(h in n for h in _MONO_HINTS):
        return "mono"
    if any(h in n for h in _SERIF_HINTS):
        return "serif"
    return "sans"


def int_color_to_hex(c: int) -> str:
    c = int(c) & 0xFFFFFF
    return f"#{c:06x}"


def is_bold(flags: int) -> bool:
    return bool(int(flags) & (1 << 4))


def is_italic(flags: int) -> bool:
    return bool(int(flags) & (1 << 1))


def iou(a: List[float], b: List[float]) -> float:
    """IoU of two [l, t, w, h] boxes."""
    al, at, aw, ah = a
    bl, bt, bw, bh = b
    ar, ab = al + aw, at + ah
    br, bb = bl + bw, bt + bh
    ix = max(0.0, min(ar, br) - max(al, bl))
    iy = max(0.0, min(ab, bb) - max(at, bt))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def aggregate_font(spans: List[dict], align: str = "left") -> Optional[FontSpec]:
    """Collapse PyMuPDF spans (dicts with size/flags/color/font) into one FontSpec.
    Returns None when there are no spans."""
    if not spans:
        return None
    sizes = Counter(round(float(s.get("size", 0)), 1) for s in spans)
    size = sizes.most_common(1)[0][0]
    bold_votes = sum(1 for s in spans if is_bold(s.get("flags", 0)))
    italic_votes = sum(1 for s in spans if is_italic(s.get("flags", 0)))
    colors = Counter(int(s.get("color", 0)) for s in spans)
    fonts = Counter(str(s.get("font", "")) for s in spans)
    dominant_font = fonts.most_common(1)[0][0]
    return FontSpec(
        size=size,
        weight=700 if bold_votes * 2 >= len(spans) else 400,
        italic=italic_votes * 2 >= len(spans),
        color=int_color_to_hex(colors.most_common(1)[0][0]),
        align=align,
        family_class=classify_font_family(dominant_font),
    )


def detect_align(line_lefts: List[float], block_l: float, block_w: float,
                 tol: float = 2.0) -> str:
    """Infer alignment from where lines start within the block."""
    if not line_lefts:
        return "left"
    block_r = block_l + block_w
    center = block_l + block_w / 2.0
    # If most lines start near the left edge -> left.
    near_left = sum(1 for x in line_lefts if abs(x - block_l) <= max(tol, block_w * 0.05))
    if near_left * 2 >= len(line_lefts):
        return "left"
    near_center = sum(1 for x in line_lefts if abs(x - center) <= block_w * 0.15)
    if near_center * 2 >= len(line_lefts):
        return "center"
    return "left"


def extract_page_fonts(pdf_path: str, page_no: int,
                       blocks: List[dict], iou_threshold: float = 0.1
                       ) -> Dict[str, FontSpec]:
    """Map span_id -> FontSpec by matching docling blocks against PyMuPDF spans.

    `blocks` are docling blocks: {"span_id", "bbox": [l,t,w,h]} (top-left points).
    Any failure returns {} so the renderer falls back to role-based defaults."""
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not installed; skipping font extraction")
        return {}
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_no - 1]  # PyMuPDF is 0-indexed
        raw = page.get_text("dict")
        # Flatten PyMuPDF spans with their [l,t,w,h] boxes (already top-left points).
        pdf_spans = []
        for blk in raw.get("blocks", []):
            for line in blk.get("lines", []):
                for sp in line.get("spans", []):
                    x0, y0, x1, y1 = sp["bbox"]
                    pdf_spans.append({
                        "box": [x0, y0, x1 - x0, y1 - y0],
                        "left": x0,
                        "size": sp.get("size", 0), "flags": sp.get("flags", 0),
                        "color": sp.get("color", 0), "font": sp.get("font", ""),
                    })
        result: Dict[str, FontSpec] = {}
        for b in blocks:
            matched = [s for s in pdf_spans if iou(b["bbox"], s["box"]) >= iou_threshold]
            if not matched:
                continue
            align = detect_align([s["left"] for s in matched], b["bbox"][0], b["bbox"][2])
            fs = aggregate_font(matched, align=align)
            if fs:
                result[b["span_id"]] = fs
        doc.close()
        return result
    except Exception as e:
        logger.warning(f"extract_page_fonts failed for {pdf_path} p{page_no}: {e}")
        return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_typography_extractor.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/typography_extractor.py tests/test_typography_extractor.py
git commit -m "feat(sp-a): TypographyExtractor (PyMuPDF fonts + pure helpers)"
```

---

## Task 3: FigureExtractor

**Files:**
- Create: `app/services/figure_extractor.py`
- Test: `tests/test_figure_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_figure_extractor.py
from PIL import Image
from backend.app.services.figure_extractor import crop_figure


def test_crop_figure_writes_scaled_region(tmp_path):
    # 200x100 raster represents a 100x50 pt page => scale 2x.
    img = Image.new("RGB", (200, 100), (255, 255, 255))
    # paint a red 40x40 px square at (20,20)
    for x in range(20, 60):
        for y in range(20, 60):
            img.putpixel((x, y), (255, 0, 0))
    # bbox in points: l=10,t=10,w=20,h=20 -> px (20,20,40,40) at scale 2
    fname = crop_figure(img, [10, 10, 20, 20], scale_x=2.0, scale_y=2.0,
                        output_dir=str(tmp_path), doc_id="d", page_no=1, idx=1)
    assert fname == "d-1-fig1.png"
    out = Image.open(tmp_path / "d-1-fig1.png")
    assert out.size == (40, 40)
    assert out.getpixel((0, 0)) == (255, 0, 0)


def test_crop_figure_clamps_to_bounds(tmp_path):
    img = Image.new("RGB", (50, 50), (0, 0, 0))
    # bbox extends beyond the raster; must clamp, not crash
    fname = crop_figure(img, [40, 40, 100, 100], scale_x=1.0, scale_y=1.0,
                        output_dir=str(tmp_path), doc_id="d", page_no=2, idx=3)
    assert (tmp_path / fname).exists()
    assert Image.open(tmp_path / fname).size == (10, 10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_figure_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/figure_extractor.py
"""Crop figure (picture) regions from the page raster into standalone PNGs so the
text-layer renderer can place real images instead of empty <img src="">."""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def crop_figure(pil_image, bbox_pt, scale_x: float, scale_y: float,
                output_dir: str, doc_id: str, page_no: int, idx: int) -> str:
    """Crop bbox (in page points) from pil_image (raster px) -> PNG.
    Returns filename only (e.g. 'd-1-fig1.png'). Clamps to image bounds."""
    os.makedirs(output_dir, exist_ok=True)
    l, t, w, h = bbox_pt
    px_l = int(round(l * scale_x)); px_t = int(round(t * scale_y))
    px_r = int(round((l + w) * scale_x)); px_b = int(round((t + h) * scale_y))
    iw, ih = pil_image.size
    px_l = max(0, min(px_l, iw - 1)); px_r = max(px_l + 1, min(px_r, iw))
    px_t = max(0, min(px_t, ih - 1)); px_b = max(px_t + 1, min(px_b, ih))
    crop = pil_image.convert("RGB").crop((px_l, px_t, px_r, px_b))
    filename = f"{doc_id}-{page_no}-fig{idx}.png"
    crop.save(os.path.join(output_dir, filename), "PNG")
    return filename
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_figure_extractor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/figure_extractor.py tests/test_figure_extractor.py
git commit -m "feat(sp-a): FigureExtractor crops picture regions from raster"
```

---

## Task 4: PageClassifier

**Files:**
- Create: `app/services/page_classifier.py`
- Test: `tests/test_page_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_page_classifier.py
from backend.app.services.page_classifier import classify_kind


def test_text_page():
    # lots of small text blocks, no figures
    blocks = [[0, i * 20, 400, 15] for i in range(20)]
    assert classify_kind(595, 842, blocks, []) == "text"


def test_image_page_full_bleed():
    # one full-bleed figure, minimal text
    figures = [[0, 0, 595, 842]]
    blocks = [[40, 700, 120, 18]]
    assert classify_kind(595, 842, blocks, figures) == "image"


def test_mixed_page():
    # half-page figure + a column of text
    figures = [[0, 0, 595, 300]]
    blocks = [[40, 320 + i * 20, 500, 15] for i in range(12)]
    assert classify_kind(595, 842, blocks, figures) == "mixed"


def test_empty_page_defaults_mixed():
    assert classify_kind(595, 842, [], []) == "mixed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_page_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/page_classifier.py
"""Classify a page as text | image | mixed from text/figure area ratios.
When uncertain, return 'mixed' (safe: keeps the raster)."""
from __future__ import annotations
from typing import List


def _area(boxes: List[List[float]]) -> float:
    return sum(max(0.0, b[2]) * max(0.0, b[3]) for b in boxes)


def classify_kind(page_w: float, page_h: float,
                  block_boxes: List[List[float]], figure_boxes: List[List[float]],
                  *, image_dominant_ratio: float = 0.55,
                  text_min_ratio: float = 0.06) -> str:
    page_area = max(page_w * page_h, 1.0)
    text_ratio = _area(block_boxes) / page_area
    fig_ratio = _area(figure_boxes) / page_area

    if not block_boxes and not figure_boxes:
        return "mixed"
    # Image-dominant page with little text -> image.
    if fig_ratio >= image_dominant_ratio and text_ratio < text_min_ratio:
        return "image"
    # Substantial figures AND substantial text -> mixed.
    if fig_ratio >= 0.15 and text_ratio >= text_min_ratio:
        return "mixed"
    # Mostly text -> text.
    if text_ratio >= text_min_ratio:
        return "text"
    return "mixed"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_page_classifier.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/page_classifier.py tests/test_page_classifier.py
git commit -m "feat(sp-a): PageClassifier (text/image/mixed by area ratio)"
```

---

## Task 5: TextFitter

**Files:**
- Create: `app/services/text_fitter.py`
- Test: `tests/test_text_fitter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_text_fitter.py
from backend.app.services.text_fitter import fit_font_size


def test_short_text_keeps_base_size():
    # plenty of room: returns the base/max size
    fs = fit_font_size("Hi", box_w_pt=400, box_h_pt=100, max_size=24, min_size=6)
    assert fs == 24.0


def test_long_text_shrinks_below_base():
    short = fit_font_size("AI", box_w_pt=120, box_h_pt=30, max_size=24, min_size=6)
    long = fit_font_size("HƯỚNG DẪN CÔNG NGHỆ TRÍ TUỆ DÀNH CHO LÃNH ĐẠO DU LỊCH",
                         box_w_pt=120, box_h_pt=30, max_size=24, min_size=6)
    assert long < short


def test_never_below_min():
    fs = fit_font_size("x" * 5000, box_w_pt=20, box_h_pt=10, max_size=24, min_size=8)
    assert fs == 8.0


def test_returns_float_in_range():
    fs = fit_font_size("some heading text", box_w_pt=200, box_h_pt=40,
                       max_size=24, min_size=6)
    assert 6.0 <= fs <= 24.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_text_fitter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/text_fitter.py
"""Server-side initial font fit. Replaces the crude `box_w/(0.5*fs)` heuristic
with a width model that ignores Vietnamese combining diacritics (they add no
advance width) and allows the box to grow up to `height_growth` before shrinking.

The renderer additionally emits a client-side shrink-to-fit refinement, but this
deterministic estimate is what makes fitting unit-testable."""
from __future__ import annotations
import math
import unicodedata

# Average glyph advance as a fraction of font size, by script weight.
_AVG_CHAR_W = 0.52


def _advance_len(text: str) -> int:
    """Count advancing characters: skip Unicode combining marks (Mn)."""
    return sum(1 for ch in text if unicodedata.category(ch) != "Mn") or 1


def fit_font_size(text: str, box_w_pt: float, box_h_pt: float,
                  *, max_size: float = 40.0, min_size: float = 6.0,
                  line_height: float = 1.25, height_growth: float = 1.6) -> float:
    n = _advance_len(text)
    box_w_pt = max(box_w_pt, 1.0)
    box_h_pt = max(box_h_pt, 1.0)
    best = min_size
    fs = min_size
    while fs <= max_size:
        chars_per_line = max(1.0, box_w_pt / (_AVG_CHAR_W * fs))
        lines = math.ceil(n / chars_per_line)
        if lines * fs * line_height <= max(box_h_pt, fs) * height_growth:
            best = fs
        fs += 0.5
    return round(best, 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_text_fitter.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/text_fitter.py tests/test_text_fitter.py
git commit -m "feat(sp-a): TextFitter (diacritic-aware fit + growth chain)"
```

---

## Task 6: TextLayerRenderer (text pages → real HTML)

**Files:**
- Create: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_text_layer_renderer.py
from backend.app.services.page_model import FontSpec, Block, Figure, PageModel
from backend.app.services.text_layer_renderer import render_text_layer


def _model(kind="text"):
    return PageModel(
        page_w=595.0, page_h=842.0, kind=kind,
        background={"color": "#ffffff", "image": None},
        blocks=[Block(span_id="s1", role="heading", bbox=[72, 40, 200, 24],
                      text="INTRODUCTION TO AI",
                      font=FontSpec(24, 700, False, "#1a1a1a", "left", "sans"))],
        figures=[Figure(bbox=[0, 100, 200, 150], img="d-1-fig1.png")],
    )


def test_render_uses_translated_text_not_original():
    html = render_text_layer(_model(), {"s1": "GIỚI THIỆU VỀ AI"},
                             image_url_base="http://api/assets")
    assert "GIỚI THIỆU VỀ AI" in html
    assert "INTRODUCTION TO AI" not in html


def test_render_has_no_raster_background_image():
    # text pages must NOT embed the full-page raster
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="ov-bg"' not in html
    assert "page-1.png" not in html


def test_render_places_figure_image():
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    assert "http://api/assets/d-1-fig1.png" in html


def test_render_applies_font_weight_and_color():
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    assert "font-weight:700" in html
    assert "#1a1a1a" in html


def test_render_emits_fit_script_for_absolute_blocks():
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    # client-side shrink-to-fit refinement must be present
    assert "btb-fit" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_text_layer_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/text_layer_renderer.py
"""Render a text-page PageModel as real positioned HTML/CSS — translated text in
matched fonts, figures as cropped images, NO full-page raster, NO opaque boxes.

SP-A uses absolute positioning (faithful to source coordinates) with a
client-side shrink-to-fit refinement. Flow mode is reserved for SP-B export."""
from __future__ import annotations
import html as html_lib

from backend.app.services.page_model import PageModel
from backend.app.services.text_fitter import fit_font_size

# Vietnamese-capable web fonts, one per family class.
_FONT_STACK = {
    "sans":  "'Be Vietnam Pro', system-ui, sans-serif",
    "serif": "'Source Serif 4', Georgia, serif",
    "mono":  "'JetBrains Mono', ui-monospace, monospace",
}
_GOOGLE_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Be+Vietnam+Pro:ital,wght@0,400;0,700;1,400&'
    'family=Source+Serif+4:ital,wght@0,400;0,700;1,400&'
    'family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">'
)

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body { background: #525659; }
.tl-scroll { position: absolute; inset: 0; overflow: auto; }
.tl-fit { min-width: 100%; min-height: 100%; display: flex;
          align-items: center; justify-content: center; padding: 12px; }
.tl-canvas { position: relative; flex: 0 0 auto; }
.tl-page { position: absolute; top: 0; left: 0; transform-origin: top left;
           box-shadow: 0 2px 14px rgba(0,0,0,.45); overflow: hidden;
           visibility: hidden; }
.tl-fig { position: absolute; display: block; }
.tl-text { position: absolute; line-height: 1.2; overflow: hidden;
           word-break: break-word; }
"""


def _pct(v: float, total: float) -> float:
    return v / total * 100.0 if total else 0.0


def render_text_layer(model: PageModel, translations: dict, image_url_base: str) -> str:
    pw = model.page_w or 1.0
    ph = model.page_h or 1.0
    bg = (model.background or {}).get("color") or "#ffffff"

    parts = []
    # Figures first (z-order below text).
    for fig in model.figures:
        l, t, w, h = fig.bbox
        src = html_lib.escape(f"{image_url_base}/{fig.img}", quote=True)
        parts.append(
            f'<img class="tl-fig" src="{src}" alt="figure" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;height:{_pct(h, ph):.3f}%;"/>'
        )

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
        base = (f.size if f and f.size else max(8.0, h * 0.8))
        size = fit_font_size(text, w, h, max_size=base, min_size=6.0)
        parts.append(
            f'<div class="tl-text" data-fit="1" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;'
            f'font-family:{family};font-size:{size:.1f}px;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};">'
            f'{html_lib.escape(text)}</div>'
        )

    # Fit + scale script: scale whole page to viewport (like the raster overlay),
    # then shrink any text div that still overflows its box (btb-fit).
    script = (
        "<script>(function(){"
        f"var PW={pw:.2f},PH={ph:.2f},pad=24,userZoom=1;"
        "function fitText(){var ds=document.querySelectorAll('.tl-text[data-fit]');"
        "ds.forEach(function(d){var g=0;"
        "while(d.scrollHeight>d.clientHeight+1&&g<40){"
        "var fs=parseFloat(getComputedStyle(d).fontSize);if(fs<=6)break;"
        "d.style.fontSize=(fs-0.5)+'px';g++;}});}"  // btb-fit shrink loop
        "function apply(){var p=document.querySelector('.tl-page'),"
        "c=document.querySelector('.tl-canvas');if(!p||!c)return;"
        "var fit=Math.min((window.innerWidth-pad)/PW,(window.innerHeight-pad)/PH);"
        "var s=fit*userZoom;p.style.transform='scale('+s+')';"
        "c.style.width=(PW*s)+'px';c.style.height=(PH*s)+'px';"
        "p.style.visibility='visible';}"
        "function run(){fitText();apply();}"
        "window.addEventListener('resize',apply);"
        "window.addEventListener('message',function(e){var d=e.data||{};"
        "if(d.type==='btb-zoom'&&typeof d.zoom==='number'){"
        "userZoom=Math.max(0.25,Math.min(5,d.zoom));apply();}});"
        "if(document.readyState!=='loading')run();"
        "else window.addEventListener('DOMContentLoaded',run);"
        "window.addEventListener('load',run);})();</script>"
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"{_GOOGLE_FONTS}<style>{_CSS}</style></head><body>"
        f'<div class="tl-scroll"><div class="tl-fit"><div class="tl-canvas">'
        f'<div class="tl-page" style="width:{pw:.2f}px;height:{ph:.2f}px;'
        f'background:{html_lib.escape(bg, quote=True)};">'
        f'{"".join(parts)}</div></div></div></div>{script}</body></html>'
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_text_layer_renderer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/text_layer_renderer.py tests/test_text_layer_renderer.py
git commit -m "feat(sp-a): TextLayerRenderer renders text pages as real HTML"
```

---

## Task 7: page_renderer dispatcher

**Files:**
- Create: `app/services/page_renderer.py`
- Test: `tests/test_page_renderer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_page_renderer.py
from backend.app.services.page_model import FontSpec, Block, Figure, PageModel
from backend.app.services.page_renderer import render_page


def _text_model():
    return PageModel(595, 842, "text", {"color": "#fff", "image": None},
                     [Block("s1", "heading", [72, 40, 200, 24], "T",
                            FontSpec(24, 700, False, "#111", "left", "sans"))],
                     [])


def _image_model():
    return PageModel(595, 842, "image", {"color": "#000", "image": "page-1.png"},
                     [Block("s1", "body", [40, 700, 120, 18], "C", None)],
                     [])


def test_text_kind_uses_text_layer():
    html = render_page(_text_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-page"' in html       # text-layer markup
    assert "DỊCH" in html


def test_image_kind_uses_raster_overlay():
    html = render_page(_image_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="ov-bg"' in html         # raster overlay markup
    assert "page-1.png" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_page_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/page_renderer.py
"""Dispatch a PageModel to the right renderer by `kind`:
  text          -> TextLayerRenderer (real HTML, no raster)
  image | mixed -> existing render_overlay_html (raster background preserved)
"""
from __future__ import annotations

from backend.app.services.page_model import PageModel
from backend.app.services.text_layer_renderer import render_text_layer
from backend.app.services.overlay_renderer import render_overlay_html


def _model_to_overlay_layout(model: PageModel) -> dict:
    """Adapt PageModel to the dict shape render_overlay_html expects."""
    return {
        "page_w": model.page_w, "page_h": model.page_h,
        "image": (model.background or {}).get("image"),
        "blocks": [
            {"span_id": b.span_id, "bbox": b.bbox,
             "bg": (model.background or {}).get("color", "#ffffff")}
            for b in model.blocks
        ],
    }


def render_page(model: PageModel, translations: dict, image_url_base: str) -> str:
    if model.kind == "text":
        return render_text_layer(model, translations, image_url_base)
    return render_overlay_html(_model_to_overlay_layout(model), translations, image_url_base)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_page_renderer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/page_renderer.py tests/test_page_renderer.py
git commit -m "feat(sp-a): page_renderer dispatch by page kind"
```

---

## Task 8: DBPage.model_json column

**Files:**
- Modify: `app/models_db.py` (DBPage, near `layout_json` at line 44)
- Test: `tests/test_page_model_column.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_page_model_column.py
import json


def test_dbpage_has_model_json_column(db_session):
    from backend.app.models_db import DBPage, DBDocument
    db_session.add(DBDocument(id="m_doc", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    payload = json.dumps({"page_w": 595.0, "page_h": 842.0, "kind": "text",
                          "background": {"color": "#fff", "image": None},
                          "blocks": [], "figures": []})
    db_session.add(DBPage(document_id="m_doc", page_num=1, original_html="<p>x</p>",
                          status="extracted", model_json=payload))
    db_session.commit()
    page = db_session.query(DBPage).filter(DBPage.document_id == "m_doc").first()
    assert json.loads(page.model_json)["kind"] == "text"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_page_model_column.py -v`
Expected: FAIL with `TypeError: 'model_json' is an invalid keyword argument for DBPage`

- [ ] **Step 3: Add the column**

In `app/models_db.py`, immediately after the `layout_json` line (line 44):

```python
    layout_json         = Column(Text, nullable=True)
    model_json          = Column(Text, nullable=True)   # PageModel JSON (SP-A)
```

> **Production note (Postgres):** SQLite test DB is created via `create_all`, so the test passes immediately. The production Postgres DB needs the column added once:
> `ALTER TABLE pages ADD COLUMN model_json TEXT;`
> (same convention used when `layout_json` was introduced — no Alembic in this project).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_page_model_column.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/models_db.py tests/test_page_model_column.py
git commit -m "feat(sp-a): add DBPage.model_json column"
```

---

## Task 9: Build & persist PageModel in the extractor

Wires Tasks 2–4 into `DoclingExtractor.extract_pdf_to_html`: after blocks + raster exist, build a `PageModel` and write a `.model.json` sidecar next to `.layout.json`.

**Files:**
- Modify: `app/services/extractor.py` (`DoclingExtractor.extract_pdf_to_html`, lines ~322-352; `_items_to_page_html` to also collect picture blocks)
- Test: `tests/test_extractor_pagemodel.py`

- [ ] **Step 1: Write the failing test (integration, real PDF)**

```python
# tests/test_extractor_pagemodel.py
import os
import json
import glob
import pytest

PDF = os.path.join(os.path.dirname(__file__), "fixtures", "sample.pdf")


@pytest.mark.skipif(not os.path.exists(PDF), reason="sample.pdf fixture missing")
def test_extractor_writes_model_json(tmp_path):
    from backend.app.services.extractor import DoclingExtractor
    DoclingExtractor.extract_pdf_to_html(PDF, str(tmp_path), "d")
    models = sorted(glob.glob(str(tmp_path / "d-*.model.json")))
    assert models, "no .model.json sidecar written"
    m = json.load(open(models[0]))
    assert m["kind"] in ("text", "image", "mixed")
    assert "blocks" in m and "figures" in m
    assert m["page_w"] > 0 and m["page_h"] > 0
```

> **Fixture:** copy any small (1–3 page) PDF with a cover image + a text page to `tests/fixtures/sample.pdf`. The repo PDF at `assets/Agentic_Design_Patterns.pdf` works — symlink or copy its first pages. If absent, the test self-skips (still committed for when the fixture lands).

- [ ] **Step 2: Run test to verify it fails (or skips without fixture)**

Run: `.venv/bin/pytest tests/test_extractor_pagemodel.py -v`
Expected: SKIP if no fixture; if fixture present, FAIL (no `.model.json` written yet).

- [ ] **Step 3: Collect picture blocks in `_items_to_page_html`**

In `app/services/extractor.py`, change the `picture` branch (line ~411) to record the figure bbox. Replace:

```python
            elif label == "picture":
                body_parts.append(f'<figure><img src="" alt="Figure on page {page_no}"/></figure>')
```

with:

```python
            elif label == "picture":
                prov = getattr(item, "prov", None)
                if prov and page_h is not None:
                    from docling_core.types.doc import CoordOrigin
                    bb = prov[0].bbox
                    tl = bb if bb.coord_origin == CoordOrigin.TOPLEFT else bb.to_top_left_origin(page_height=page_h)
                    figures.append([tl.l, min(tl.t, tl.b), tl.r - tl.l, abs(tl.b - tl.t)])
                body_parts.append(f'<figure><img src="" alt="Figure on page {page_no}"/></figure>')
```

And add a `figures` list next to `blocks` at the top of the function, and return it. Change:

```python
        span_counter = [0]
        blocks: List[dict] = []
        page_h = getattr(page_size, "height", None)
```

to:

```python
        span_counter = [0]
        blocks: List[dict] = []
        figures: List[list] = []
        page_h = getattr(page_size, "height", None)
```

and change the final `return html, blocks` (line ~430) to:

```python
        return html, blocks, figures
```

- [ ] **Step 4: Build & write PageModel in `extract_pdf_to_html`**

In `app/services/extractor.py`, update the unpack of `_items_to_page_html` (line ~316). Replace:

```python
            page_html, blocks = cls._items_to_page_html(pages_items[page_no], page_no, page_size)
```

with:

```python
            page_html, blocks, fig_boxes = cls._items_to_page_html(pages_items[page_no], page_no, page_size)
```

Then, after the existing `layout` dict is written (after line ~350, the `json.dump(layout, f)` block), append:

```python
            # ── PageModel (SP-A): typography + figures + classification ──
            from backend.app.services.page_model import PageModel, Block, Figure
            from backend.app.services.typography_extractor import extract_page_fonts
            from backend.app.services.figure_extractor import crop_figure
            from backend.app.services.page_classifier import classify_kind

            fonts = {}
            try:
                fonts = extract_page_fonts(str(pdf_path), page_no, blocks)
            except Exception as e:
                logger.warning(f"Font extraction failed p{page_no}: {e}")

            figures = []
            if pil_img is not None and page_size is not None and fig_boxes:
                sx = pil_img.width / page_size.width
                sy = pil_img.height / page_size.height
                for i, fb in enumerate(fig_boxes, start=1):
                    try:
                        fname = crop_figure(pil_img, fb, sx, sy, output_dir, doc_id, page_no, i)
                        figures.append(Figure(bbox=fb, img=fname))
                    except Exception as e:
                        logger.warning(f"Figure crop failed p{page_no} #{i}: {e}")

            # role from the HTML tag we emitted is not tracked per block here; default
            # body, upgrade headings via font weight at render time. Carry text+font.
            block_text = {b["span_id"]: "" for b in blocks}  # text lives in DBTranslation
            model_blocks = [
                Block(span_id=b["span_id"], role="body", bbox=b["bbox"],
                      text=block_text.get(b["span_id"], ""),
                      font=fonts.get(b["span_id"]))
                for b in blocks
            ]
            pw = page_size.width if page_size else 1.0
            ph = page_size.height if page_size else 1.0
            kind = classify_kind(pw, ph, [b["bbox"] for b in blocks],
                                 [f.bbox for f in figures])
            bg_color = blocks[0].get("bg", "#ffffff") if blocks else "#ffffff"
            model = PageModel(
                page_w=pw, page_h=ph, kind=kind,
                background={"color": bg_color,
                            "image": image_name if kind != "text" else None},
                blocks=model_blocks, figures=figures,
            )
            model_path = os.path.normpath(os.path.join(output_dir, f"{doc_id}-{page_no}.model.json"))
            with open(model_path, "w", encoding="utf-8") as f:
                f.write(model.to_json())
```

> Note: block `text` is intentionally empty in the model — original/translated text lives in `DBTranslation` and is injected at render time via the `translations` dict keyed by `span_id`. The model carries layout + font only.

- [ ] **Step 5: Run the full extractor + existing tests**

Run: `.venv/bin/pytest tests/test_extractor_pagemodel.py tests/test_overlay.py -v`
Expected: `test_extractor_writes_model_json` PASS (or SKIP without fixture); `test_items_to_page_html_returns_html_and_blocks` — **update it** for the new 3-tuple return (next step).

- [ ] **Step 6: Fix the existing unit test for the new return arity**

In `tests/test_overlay.py`, `test_items_to_page_html_returns_html_and_blocks`, change:

```python
    html, blocks = DoclingExtractor._items_to_page_html([(item, 0)], 1, page_size)
```

to:

```python
    html, blocks, figures = DoclingExtractor._items_to_page_html([(item, 0)], 1, page_size)
```

Run: `.venv/bin/pytest tests/test_overlay.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/extractor.py tests/test_extractor_pagemodel.py tests/test_overlay.py
git commit -m "feat(sp-a): build & persist PageModel sidecar in extractor"
```

---

## Task 10: Load `.model.json` into the column (extraction router)

**Files:**
- Modify: `app/routers/extraction.py` (around lines 107-115)
- Test: covered by Task 11 endpoint test (no isolated unit test — this is glue).

- [ ] **Step 1: Load the sidecar next to layout_json**

In `app/routers/extraction.py`, after the `layout_json` loading block (line ~111), add a parallel block before the `DBPage(...)` construction:

```python
            model_json = None
            model_path = file_path[:-5] + ".model.json"  # ".html" -> ".model.json"
            if os.path.exists(model_path):
                with open(model_path, "r", encoding="utf-8") as mf:
                    model_json = mf.read()
```

- [ ] **Step 2: Pass it into the row**

Change the `DBPage(...)` construction (line ~114) from:

```python
            db.add(DBPage(document_id=doc_id, page_num=page_num, original_html=final_html,
                          status="raw", layout_json=layout_json))
```

to:

```python
            db.add(DBPage(document_id=doc_id, page_num=page_num, original_html=final_html,
                          status="raw", layout_json=layout_json, model_json=model_json))
```

- [ ] **Step 3: Run the extraction router tests**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: PASS (no regressions)

- [ ] **Step 4: Commit**

```bash
git add app/routers/extraction.py
git commit -m "feat(sp-a): persist .model.json sidecar into DBPage.model_json"
```

---

## Task 11: Preview endpoint prefers PageModel

**Files:**
- Modify: `app/routers/documents.py` (preview endpoint, lines ~248-285)
- Test: `tests/test_preview_pagemodel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preview_pagemodel.py
import json


def _seed(db_session, kind, model):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="p_doc", filename="x.pdf", total_pages=1, status="translated"))
    db_session.add(DBPage(document_id="p_doc", page_num=1, original_html="<p>x</p>",
                          status="translated", model_json=json.dumps(model)))
    db_session.add(DBTranslation(document_id="p_doc", page_num=1, span_id="s1",
                                 original_text="INTRODUCTION", translated_text="GIỚI THIỆU"))
    db_session.commit()


def test_preview_text_page_renders_text_layer(client, db_session):
    model = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
             "background": {"color": "#ffffff", "image": None},
             "blocks": [{"span_id": "s1", "role": "heading", "bbox": [72, 40, 200, 24],
                         "text": "", "font": {"size": 24, "weight": 700, "italic": False,
                                              "color": "#111", "align": "left",
                                              "family_class": "sans"}}],
             "figures": []}
    _seed(db_session, "text", model)
    r = client.get("/api/docs/p_doc/pages/1?lang=vi")
    assert r.status_code == 200
    assert "GIỚI THIỆU" in r.text
    assert 'class="ov-bg"' not in r.text   # no raster on text page
```

> Verified against `app/routers/documents.py:229`: the route is
> `@router.get("/api/docs/{doc_id}/pages/{page_num}")`, function `get_page_content`,
> with `lang: str = Query("en", pattern="^(en|vi)$")` and a `request: Request` param.
> It already returns `HTMLResponse(...)` (line 312) and imports `HTMLResponse` (line 7).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_preview_pagemodel.py -v`
Expected: FAIL (endpoint still ignores `model_json`, so no text-layer markup / assertion fails)

- [ ] **Step 3: Prefer model_json in the endpoint**

In `app/routers/documents.py`, inside the preview endpoint, **before** the existing `layout = None` block (line ~251), add:

```python
    # Prefer the rich PageModel when present (SP-A). Falls back to layout_json below.
    if page.model_json:
        try:
            from backend.app.services.page_model import PageModel
            from backend.app.services.page_renderer import render_page
            pm = PageModel.from_json(page.model_json)
            image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
            if lang == "en":
                trans_dict = {b.span_id: (b.text or "") for b in pm.blocks}
                # original text comes from DBTranslation.original_text
                rows = db.query(DBTranslation).filter(
                    DBTranslation.document_id == doc_id,
                    DBTranslation.page_num == page_num).all()
                trans_dict = {t.span_id: (t.original_text or "") for t in rows}
            else:
                rows = db.query(DBTranslation).filter(
                    DBTranslation.document_id == doc_id,
                    DBTranslation.page_num == page_num).all()
                trans_dict = {t.span_id: (t.translated_text or "") for t in rows}
            return HTMLResponse(render_page(pm, trans_dict, image_base))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"PageModel render failed for {doc_id} p{page_num}, falling back: {e}")
            # fall through to the legacy layout_json path
```

> The endpoint already imports `DBTranslation` (line 239) and `HTMLResponse` (line 7), and returns `HTMLResponse(...)` at line 312 — so `return HTMLResponse(render_page(...))` matches the existing response type. The `request` and `lang` params are already in the signature.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_preview_pagemodel.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `.venv/bin/pytest tests/ -v`
Expected: all PASS (Task 9 integration test may SKIP without fixture).

- [ ] **Step 6: Commit**

```bash
git add app/routers/documents.py tests/test_preview_pagemodel.py
git commit -m "feat(sp-a): preview endpoint renders via PageModel (text-layer)"
```

---

## Task 12: Manual verification + docs

**Files:**
- Modify: `CLAUDE.md` (document the new PageModel pipeline) — optional but recommended.

- [ ] **Step 1: Run the dev environment and inspect a real document**

Start backend + frontend per `/start-dev`, upload/extract a PDF with a text page and a cover, open the side-by-side preview, and confirm on a **text page**: translated text in matched fonts, no opaque boxes, copy/zoom works; on a **cover/image page**: raster preserved, no rectangular patches.

- [ ] **Step 2: Use the verify skill**

Invoke `superpowers:verification-before-completion` and confirm every prior task's tests pass:
Run: `.venv/bin/pytest tests/ -v`

- [ ] **Step 3: Document the pipeline (optional)**

Add a short "PageModel pipeline (SP-A)" note to `CLAUDE.md` under the services section describing the sidecar and `kind` routing.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(sp-a): document PageModel pipeline"
```

---

## Self-Review notes

- **Spec coverage:** PageModel (Task 1), TypographyExtractor (Task 2), FigureExtractor (Task 3), PageClassifier (Task 4), TextFitter (Task 5), TextLayerRenderer flow/absolute (Task 6 — SP-A ships absolute + client shrink-to-fit; flow deferred to SP-B export as noted in spec §2), ImagePageHandler (folded into `page_renderer` dispatch reusing `render_overlay_html`, Task 7), degrade paths (Tasks 2/3/9 try/except → role-based / placeholder / mixed), endpoint integration (Tasks 8–11), testing (per-task unit + Task 9 integration). Export (component 8) is out of SP-A scope per spec §8.
- **Type consistency:** `FontSpec(size,weight,italic,color,align,family_class)`, `Block(span_id,role,bbox,text,font)`, `Figure(bbox,img)`, `PageModel(page_w,page_h,kind,background,blocks,figures)` used identically across Tasks 1, 6, 7, 9, 11. `render_text_layer`/`render_page`/`render_overlay_html` signatures `(model_or_layout, translations, image_url_base)` consistent. `crop_figure(...)->filename`, `extract_page_fonts(...)->{span_id:FontSpec}`, `classify_kind(...)->str`, `fit_font_size(...)->float` match all call sites.
- **Known follow-ups (do not block SP-A):** `role` is defaulted to `body` in Task 9 (headings upgraded via font weight at render) because `_items_to_page_html` does not currently thread the semantic label into `blocks`; threading the real role is a small enhancement for SP-B. Flow-mode rendering is SP-B.
