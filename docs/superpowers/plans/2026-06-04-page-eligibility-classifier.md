# Page Eligibility Classifier (#0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gắn nhãn mỗi trang `page_class` (`text`/`preserve`/`regenerable`) + `cover` (`front`/`back`/`none`) lúc extract, phân biệt photo vs sơ đồ bằng heuristic tất định, mặc định mọi nghi ngờ → `preserve`.

**Architecture:** Hai module thuần mới — `picture_classifier.py` (heuristic thị giác trên crop figure) và `page_eligibility.py` (logic quyết định nhãn trang + cover). `extractor.py` gọi chúng sau khi crop figure và lưu nhãn vào `PageModel` (đi kèm `model_json`, không đổi schema DB). Một script backfill gắn nhãn lại tài liệu đã extract. AI vision chỉ là Protocol, chưa gọi (để #2/#3).

**Tech Stack:** Python 3, pytest, OpenCV (`cv2`), numpy, PyMuPDF — tất cả đã cài. Làm việc trong `apps/break_the_barriers/backend`, chạy test bằng `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-04-page-eligibility-classifier-design.md`

## File Structure

- `app/services/page_model.py` — thêm 2 field `page_class`, `cover` vào dataclass + serialize.
- `app/services/page_eligibility.py` — **mới**; `classify_page` + `detect_cover` (thuần).
- `app/services/picture_classifier.py` — **mới**; `classify_picture` heuristic + Protocol `PictureVisionClassifier`.
- `app/services/extractor.py` — lắp ráp: phân loại figure, tính `has_table`, gọi 2 hàm trên, gán vào PageModel.
- `app/routers/documents.py` — trả thêm `page_class`/`cover` ở endpoint non-raw.
- `scripts/relabel_document.py` — **mới**; backfill gắn nhãn lại tài liệu đã extract.
- Tests: `tests/test_page_model.py` (bổ sung), `tests/test_page_eligibility.py` (mới), `tests/test_picture_classifier.py` (mới), `tests/test_preview_pagemodel.py` (bổ sung 1 test API).

**Lưu ý chạy lệnh:** mọi lệnh chạy từ `apps/break_the_barriers/backend`; git chạy từ repo root `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`. Import dùng đường dẫn package `backend.app.services...`.

---

### Task 1: PageModel thêm field `page_class` + `cover`

**Files:**
- Modify: `app/services/page_model.py` (dataclass `PageModel`, `to_dict`, `from_dict`)
- Test: `tests/test_page_model.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_page_model.py`:

```python
def test_pagemodel_defaults_page_class_and_cover():
    from backend.app.services.page_model import PageModel
    pm = PageModel(page_w=595.0, page_h=842.0, kind="text",
                   background={"color": "#fff", "image": None}, blocks=[], figures=[])
    assert pm.page_class == "text"
    assert pm.cover == "none"


def test_pagemodel_roundtrip_preserves_page_class_and_cover():
    from backend.app.services.page_model import PageModel
    pm = PageModel(page_w=1.0, page_h=1.0, kind="image",
                   background={"color": "#fff", "image": "p.png"}, blocks=[], figures=[],
                   page_class="regenerable", cover="front")
    d = pm.to_dict()
    assert d["page_class"] == "regenerable" and d["cover"] == "front"
    pm2 = PageModel.from_dict(d)
    assert pm2.page_class == "regenerable" and pm2.cover == "front"


def test_pagemodel_from_dict_old_json_defaults():
    from backend.app.services.page_model import PageModel
    # model.json cũ thiếu page_class/cover → default an toàn.
    pm = PageModel.from_dict({"page_w": 1.0, "page_h": 1.0, "kind": "text",
                              "background": {"color": "#fff", "image": None},
                              "blocks": [], "figures": []})
    assert pm.page_class == "text" and pm.cover == "none"
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `\.venv/bin/pytest tests/test_page_model.py -k "page_class or cover" -v` → FAIL (`unexpected keyword argument 'page_class'` / `AttributeError`).

- [ ] **Step 3: Cài đặt.** Trong `app/services/page_model.py`:

(a) Thêm 2 field vào dataclass `PageModel` (sau `figures: List[Figure]`):
```python
    page_class: str = "text"     # text | preserve | regenerable
    cover: str = "none"          # front | back | none
```

(b) Trong `to_dict`, thêm 2 khoá vào dict trả về (sau `"figures": [...]`):
```python
            "page_class": self.page_class,
            "cover": self.cover,
```

(c) Trong `from_dict`, truyền 2 field vào constructor `cls(...)` (sau `figures=figures`):
```python
            page_class=d.get("page_class", "text"),
            cover=d.get("cover", "none"),
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `\.venv/bin/pytest tests/test_page_model.py -v` → PASS toàn bộ.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/page_model.py \
        apps/break_the_barriers/backend/tests/test_page_model.py
git commit -m "feat(#0): PageModel.page_class + cover fields (safe defaults)"
```

---

### Task 2: `page_eligibility.py` — `classify_page` + `detect_cover`

**Files:**
- Create: `app/services/page_eligibility.py`
- Test: `tests/test_page_eligibility.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_page_eligibility.py`:

```python
from backend.app.services.page_eligibility import classify_page, detect_cover


# --- classify_page ---
def test_table_forces_preserve():
    assert classify_page(0.4, 0.2, ["photo"], has_table=True, bg_is_photo=False) == "preserve"


def test_diagram_figure_forces_preserve():
    assert classify_page(0.1, 0.5, ["diagram"], has_table=False, bg_is_photo=False) == "preserve"


def test_uncertain_figure_forces_preserve():
    assert classify_page(0.1, 0.5, ["uncertain"], has_table=False, bg_is_photo=False) == "preserve"


def test_all_photo_low_text_is_regenerable():
    assert classify_page(0.1, 0.5, ["photo", "photo"], has_table=False, bg_is_photo=False) == "regenerable"


def test_photo_background_cover_is_regenerable():
    # Bìa: bg là photo, không figure, ít chữ.
    assert classify_page(0.24, 0.03, [], has_table=False, bg_is_photo=True) == "regenerable"


def test_no_image_with_text_is_text():
    assert classify_page(0.4, 0.0, [], has_table=False, bg_is_photo=False) == "text"


def test_text_heavy_page_with_photo_is_preserve():
    # Có ảnh nhưng chữ nhiều → không tái tạo, giữ raster (an toàn).
    assert classify_page(0.5, 0.2, ["photo"], has_table=False, bg_is_photo=False) == "preserve"


# --- detect_cover ---
def test_front_cover_first_page_image_low_text():
    assert detect_cover(0, 44, text_ratio=0.24, fig_ratio=0.03, bg_is_photo=True) == "front"


def test_back_cover_last_page_image_dominant():
    assert detect_cover(43, 44, text_ratio=0.07, fig_ratio=0.80, bg_is_photo=False) == "back"


def test_middle_page_is_not_cover():
    assert detect_cover(5, 44, text_ratio=0.30, fig_ratio=0.20, bg_is_photo=False) == "none"


def test_text_heavy_first_page_is_not_cover():
    assert detect_cover(0, 44, text_ratio=0.50, fig_ratio=0.02, bg_is_photo=False) == "none"
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `\.venv/bin/pytest tests/test_page_eligibility.py -v` → FAIL (`ModuleNotFoundError: page_eligibility`).

- [ ] **Step 3: Cài đặt.** Tạo `app/services/page_eligibility.py`:

```python
"""Page eligibility labels for background reconstruction (#0).

Pure decision logic: given area ratios + per-figure photo/diagram labels,
decide whether a page is plain `text`, must-`preserve` (diagram/chart/table or
anything uncertain), or `regenerable` (image-dominant, low-text, all photos).
Any doubt resolves to `preserve` — a chart must never become regenerable."""
from __future__ import annotations
from typing import List


def classify_page(text_ratio: float, fig_ratio: float, figure_labels: List[str],
                  *, has_table: bool, bg_is_photo: bool,
                  text_max: float = 0.30, fig_min: float = 0.15) -> str:
    has_image = bg_is_photo or fig_ratio >= fig_min or bool(figure_labels)
    if not has_image and text_ratio > 0:
        return "text"
    if has_table or any(lbl in ("diagram", "uncertain") for lbl in figure_labels):
        return "preserve"
    if text_ratio < text_max and has_image and all(lbl == "photo" for lbl in figure_labels):
        return "regenerable"
    return "preserve"


def detect_cover(page_index: int, total_pages: int,
                 *, text_ratio: float, fig_ratio: float, bg_is_photo: bool,
                 cover_text_max: float = 0.35, fig_min: float = 0.15) -> str:
    image_like = bg_is_photo or fig_ratio >= fig_min
    if not image_like or text_ratio >= cover_text_max:
        return "none"
    if page_index == 0:
        return "front"
    if page_index == total_pages - 1:
        return "back"
    return "none"
```

Lưu ý: test gọi `detect_cover(0, 44, text_ratio=..., fig_ratio=..., bg_is_photo=...)` với
`page_index`/`total_pages` là vị trí, còn lại keyword — khớp chữ ký trên.

- [ ] **Step 4: Chạy để xác nhận PASS** — `\.venv/bin/pytest tests/test_page_eligibility.py -v` → PASS (11 tests).

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/page_eligibility.py \
        apps/break_the_barriers/backend/tests/test_page_eligibility.py
git commit -m "feat(#0): page_eligibility classify_page + detect_cover"
```

---

### Task 3: `picture_classifier.py` — heuristic photo vs diagram

**Files:**
- Create: `app/services/picture_classifier.py`
- Test: `tests/test_picture_classifier.py`

Heuristic dùng 4 chỉ báo (BGR/numpy/cv2), mỗi chỉ báo bỏ phiếu photo hoặc diagram;
`margin = photo_votes - diagram_votes`; `>=2`→photo, `<=-2`→diagram, còn lại uncertain.

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_picture_classifier.py`:

```python
import numpy as np
import cv2
from backend.app.services.picture_classifier import classify_picture


def test_black_lines_on_white_is_diagram():
    img = np.full((256, 256, 3), 255, np.uint8)        # nền trắng
    for y in (40, 90, 140, 190):                       # nhiều đường thẳng dài
        cv2.line(img, (10, y), (245, y), (0, 0, 0), 2)
    cv2.rectangle(img, (20, 20), (230, 230), (0, 0, 0), 2)
    label, conf = classify_picture(img)
    assert label == "diagram"
    assert 0.0 <= conf <= 1.0


def test_colorful_noise_is_photo():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)   # nhiễu nhiều màu, bão hoà cao
    label, _ = classify_picture(img)
    assert label == "photo"


def test_flat_gray_block_is_uncertain():
    img = np.full((256, 256, 3), 128, np.uint8)        # xám phẳng: bằng chứng lẫn lộn
    label, _ = classify_picture(img)
    assert label == "uncertain"
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `\.venv/bin/pytest tests/test_picture_classifier.py -v` → FAIL (`ModuleNotFoundError: picture_classifier`).

- [ ] **Step 3: Cài đặt.** Tạo `app/services/picture_classifier.py`:

```python
"""Heuristic photo-vs-diagram classifier for cropped 'picture' figures (#0).

Deterministic, offline (OpenCV/numpy). Each of four cues votes 'photo' or
'diagram'; the signed margin decides, with an ambiguous band returning
'uncertain' (which callers treat as preserve). An AI vision fallback is declared
as a Protocol only — it is NOT used at extraction time (reserved for #2/#3)."""
from __future__ import annotations
from typing import Protocol, Tuple
import numpy as np
import cv2

# Cue thresholds (clear margins; tuned against synthetic extremes).
_COLOR_RATIO_HI = 0.20      # unique-color ratio: above → photo
_COLOR_RATIO_LO = 0.05      # below → diagram
_SAT_HI = 0.25              # mean saturation [0,1]: above → photo
_SAT_LO = 0.10              # below → diagram
_WHITE_HI = 0.45            # near-white fraction: above → diagram
_WHITE_LO = 0.10            # below → photo
_LINES_HI = 4               # # long straight lines: >= → diagram, 0 → photo


class PictureVisionClassifier(Protocol):
    """AI fallback contract (reserved for #2/#3; not used at extraction)."""
    def classify(self, crop_bgr: np.ndarray) -> str: ...   # "photo" | "diagram"


def _features(img: np.ndarray) -> dict:
    h, w = img.shape[:2]
    scale = 256.0 / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                         interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    n = max(1, h * w)
    # unique quantised colors (4 bits/channel)
    q = (img >> 4).astype(np.uint16)
    codes = (q[..., 0].astype(np.uint32) << 8) | (q[..., 1].astype(np.uint32) << 4) | q[..., 2]
    color_ratio = np.unique(codes).size / n
    # mean saturation
    sat_mean = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].mean() / 255.0
    # near-white fraction
    white_frac = float((img.min(axis=2) > 230).sum()) / n
    # long straight lines
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=int(min(h, w) * 0.3), maxLineGap=5)
    n_lines = 0 if lines is None else len(lines)
    return {"color_ratio": color_ratio, "sat_mean": sat_mean,
            "white_frac": white_frac, "n_lines": n_lines}


def classify_picture(img_bgr: np.ndarray) -> Tuple[str, float]:
    """Return (label, confidence) with label in {photo, diagram, uncertain}."""
    f = _features(img_bgr)
    photo = diagram = 0
    if f["color_ratio"] > _COLOR_RATIO_HI: photo += 1
    elif f["color_ratio"] < _COLOR_RATIO_LO: diagram += 1
    if f["sat_mean"] > _SAT_HI: photo += 1
    elif f["sat_mean"] < _SAT_LO: diagram += 1
    if f["white_frac"] > _WHITE_HI: diagram += 1
    elif f["white_frac"] < _WHITE_LO: photo += 1
    if f["n_lines"] >= _LINES_HI: diagram += 1
    elif f["n_lines"] == 0: photo += 1
    margin = photo - diagram
    conf = abs(margin) / 4.0
    if margin >= 2:
        return "photo", conf
    if margin <= -2:
        return "diagram", conf
    return "uncertain", conf


def classify_picture_file(path: str) -> Tuple[str, float]:
    """Load an image file and classify it; missing/unreadable → ('uncertain', 0.0)."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return "uncertain", 0.0
    return classify_picture(img)
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `\.venv/bin/pytest tests/test_picture_classifier.py -v` → PASS (3 tests). Nếu `test_flat_gray_block_is_uncertain` không ra uncertain, KHÔNG nới lỏng test — báo lại số phiếu (mong đợi: xám phẳng → color_ratio thấp (diagram+1) + sat≈0 (diagram+1) + white_frac≈0 (photo+1) + n_lines=0 (photo+1) = margin 0 → uncertain).

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/picture_classifier.py \
        apps/break_the_barriers/backend/tests/test_picture_classifier.py
git commit -m "feat(#0): heuristic picture_classifier (photo vs diagram)"
```

---

### Task 4: Lắp ráp vào `extractor.py`

**Files:**
- Modify: `app/services/extractor.py` (khối PageModel, hiện ~dòng 401-448)

Đây là task tích hợp (không TDD đơn vị riêng vì phụ thuộc docling/PDF runtime); xác minh bằng backfill ở Task 6 + full suite. Cẩn thận, bọc try/except để một lỗi phân loại không phá cả lần extract.

- [ ] **Step 1: Thêm import + tính tổng số trang.** Ở đầu vòng lặp trang (ngay sau `for page_no in sorted(pages_items.keys()):`, hiện dòng 314), thêm:
```python
            _pages_sorted = sorted(pages_items.keys())
            _total_pages = len(_pages_sorted)
            _page_index = _pages_sorted.index(page_no)
```

- [ ] **Step 2: Phân loại figure + tính nhãn trang.** Ngay TRƯỚC khi tạo `model = PageModel(...)` (hiện dòng 443), chèn:
```python
            # ── #0 eligibility: per-figure photo/diagram → page_class + cover ──
            from backend.app.services.picture_classifier import classify_picture_file
            from backend.app.services.page_eligibility import classify_page, detect_cover
            figure_labels = []
            for _fig in figures:
                try:
                    figure_labels.append(
                        classify_picture_file(os.path.join(output_dir, _fig.img))[0])
                except Exception as _e:
                    logger.warning(f"picture classify failed p{page_no} {_fig.img}: {_e}")
                    figure_labels.append("uncertain")   # an toàn → preserve
            _page_area = max(pw * ph, 1.0)
            _text_ratio = sum(b["bbox"][2] * b["bbox"][3] for b in blocks) / _page_area
            _fig_ratio = sum(f.bbox[2] * f.bbox[3] for f in figures) / _page_area
            _has_table = any(b.get("role") == "table" for b in blocks)
            page_class = classify_page(_text_ratio, _fig_ratio, figure_labels,
                                       has_table=_has_table, bg_is_photo=bg_is_photo)
            cover = detect_cover(_page_index, _total_pages, text_ratio=_text_ratio,
                                 fig_ratio=_fig_ratio, bg_is_photo=bg_is_photo)
```

- [ ] **Step 3: Gán vào PageModel.** Sửa lời gọi `PageModel(...)` (hiện dòng 443-448) để thêm 2 tham số:
```python
            model = PageModel(
                page_w=pw, page_h=ph, kind=kind,
                background={"color": bg_color,
                            "image": image_name if kind != "text" else None},
                blocks=model_blocks, figures=figures,
                page_class=page_class, cover=cover,
            )
```

- [ ] **Step 4: Kiểm tra cú pháp + full suite (không hồi quy).**
Run: `\.venv/bin/python -c "import backend.app.services.extractor"` → không lỗi import.
Run: `\.venv/bin/pytest tests/ -q --ignore=tests/test_extractor_box.py` → PASS (bỏ qua `test_extractor_box.py` vì chạy docling rất chậm; nó không liên quan logic #0).

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/extractor.py
git commit -m "feat(#0): wire eligibility labels into extraction"
```

---

### Task 5: Trả `page_class`/`cover` ở endpoint page (non-raw)

**Files:**
- Modify: `app/routers/documents.py` (`get_page_content`, return non-raw dòng 338)
- Test: `tests/test_preview_pagemodel.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_preview_pagemodel.py`:

```python
def test_preview_nonraw_returns_page_class_and_cover(client, db_session):
    model = dict(_MODEL)
    model["page_class"] = "regenerable"
    model["cover"] = "front"
    _seed(db_session, model)
    r = client.get("/api/docs/p_doc/pages/1?lang=vi")
    assert r.status_code == 200
    data = r.json()
    assert data["page_class"] == "regenerable"
    assert data["cover"] == "front"
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `\.venv/bin/pytest tests/test_preview_pagemodel.py -k page_class -v` → FAIL (`KeyError: 'page_class'`).

- [ ] **Step 3: Cài đặt.** Trong `app/routers/documents.py`, thay câu `return {"doc_id": ...}` cuối hàm (dòng 338) bằng:
```python
    page_class, cover = "text", "none"
    if page.model_json:
        try:
            from backend.app.services.page_model import PageModel
            _pm = PageModel.from_json(page.model_json)
            page_class, cover = _pm.page_class, _pm.cover
        except Exception:
            pass
    return {"doc_id": doc_id, "page_num": page_num, "lang": lang, "html": html,
            "page_class": page_class, "cover": cover}
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `\.venv/bin/pytest tests/test_preview_pagemodel.py -v` → PASS toàn bộ (kể cả các test cũ).

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/routers/documents.py \
        apps/break_the_barriers/backend/tests/test_preview_pagemodel.py
git commit -m "feat(#0): expose page_class/cover in page metadata endpoint"
```

---

### Task 6: Script backfill gắn nhãn lại tài liệu đã extract

**Files:**
- Create: `scripts/relabel_document.py`

Đây là tiện ích vận hành (đọc model.json + crop trên đĩa, tính lại nhãn, ghi đè). Verify bằng cách chạy thật trên `2024-wttc-introduction-to-ai`.

- [ ] **Step 1: Tạo `scripts/relabel_document.py`:**

```python
"""Backfill #0 eligibility labels onto an already-extracted document.

Reads each `{doc}-{n}.model.json` plus its figure crops (already on disk),
recomputes page_class/cover with the heuristic classifier, and rewrites the
model.json in place. Usage:

    .venv/bin/python scripts/relabel_document.py <doc_dir>
"""
import os
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.services.page_model import PageModel
from backend.app.services.picture_classifier import classify_picture_file
from backend.app.services.page_eligibility import classify_page, detect_cover


def relabel_document(doc_dir: str) -> int:
    files = glob.glob(os.path.join(doc_dir, "*.model.json"))
    files.sort(key=lambda p: int(p.split("-")[-1].split(".")[0]))
    total = len(files)
    changed = 0
    for idx, path in enumerate(files):
        pm = PageModel.from_json(open(path, encoding="utf-8").read())
        labels = [classify_picture_file(os.path.join(doc_dir, f.img))[0] for f in pm.figures]
        page_area = max(pm.page_w * pm.page_h, 1.0)
        text_ratio = sum(b.bbox[2] * b.bbox[3] for b in pm.blocks) / page_area
        fig_ratio = sum(f.bbox[2] * f.bbox[3] for f in pm.figures) / page_area
        has_table = any(b.role == "table" for b in pm.blocks)
        bg_is_photo = bool((pm.background or {}).get("image")) and pm.kind != "text"
        pm.page_class = classify_page(text_ratio, fig_ratio, labels,
                                      has_table=has_table, bg_is_photo=bg_is_photo)
        pm.cover = detect_cover(idx, total, text_ratio=text_ratio,
                                fig_ratio=fig_ratio, bg_is_photo=bg_is_photo)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(pm.to_json())
        changed += 1
        print(f"{os.path.basename(path)}: page_class={pm.page_class} cover={pm.cover} "
              f"(figs={labels})")
    return changed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: relabel_document.py <doc_dir>", file=sys.stderr)
        sys.exit(2)
    n = relabel_document(sys.argv[1])
    print(f"relabelled {n} pages")
```

Lưu ý: `bg_is_photo` ở backfill là xấp xỉ (suy từ việc có ảnh nền + kind ≠ text)
vì raster gốc đã có nhưng ta không chạy lại `is_photo_background`; đủ tốt cho backfill/test.

- [ ] **Step 2: Chạy thật để verify** trên tài liệu mẫu:
```bash
.venv/bin/python scripts/relabel_document.py data/extracted_html/2024-wttc-introduction-to-ai
```
Expected: in ra nhãn từng trang; **trang 1 → `cover=front`**, **trang 44 → `cover=back`**;
không trang nào có figure `diagram`/`uncertain` mà lại `regenerable` (kiểm mắt: mọi
`regenerable` phải là trang ảnh/bìa thật, KHÔNG phải trang sơ đồ/bảng).

- [ ] **Step 3: Kiểm tra qua API** (server :8000 đang chạy `--reload`): sau backfill, DB vẫn giữ `model_json` cũ — backfill chỉ sửa file đĩa. Để API phản ánh nhãn mới cần nạp lại sidecar vào DB qua luồng extraction sẵn có HOẶC kiểm trực tiếp file. Xác nhận file đã đổi:
```bash
.venv/bin/python -c "import json; m=json.load(open('data/extracted_html/2024-wttc-introduction-to-ai/2024-wttc-introduction-to-ai-1.model.json')); print(m['page_class'], m['cover'])"
```
Expected: in ra `page_class` và `cover=front`.

- [ ] **Step 4: Commit**
```bash
git add apps/break_the_barriers/backend/scripts/relabel_document.py
git commit -m "feat(#0): backfill script to relabel extracted documents"
```

---

## Self-Review

**Spec coverage:**
- A — nhãn `page_class`/`cover` + lưu trong PageModel → Task 1 (field), Task 4 (tính). ✓
- B — heuristic photo/diagram + Protocol AI (chưa gọi) → Task 3. ✓
- C — `detect_cover` vị trí + tỉ lệ → Task 2. ✓
- D — `classify_page` thuần → Task 2. ✓
- E — wiring extractor + endpoint metadata → Task 4, Task 5. ✓
- E (backfill) — script relabel → Task 6. ✓
- F — kiểm thử: page_eligibility (Task 2), picture_classifier (Task 3), PageModel round-trip/old-json (Task 1), API metadata (Task 5). ✓
- G — ngoài phạm vi (không inpaint/sinh ảnh/không gọi Gemini khi extract/không đổi DB schema) → tôn trọng: AI chỉ Protocol; PageModel field đi kèm model_json. ✓

**Placeholder scan:** không có TBD/TODO; mọi step có code/lệnh cụ thể. ✓

**Type consistency:**
- `classify_page(text_ratio, fig_ratio, figure_labels, *, has_table, bg_is_photo, text_max=0.30, fig_min=0.15) -> str` — định nghĩa Task 2, gọi đúng ở Task 4 & test Task 2 & backfill Task 6. ✓
- `detect_cover(page_index, total_pages, *, text_ratio, fig_ratio, bg_is_photo, cover_text_max=0.35, fig_min=0.15) -> str` — nhất quán Task 2/4/6. ✓
- `classify_picture(img_bgr) -> (label, conf)` và `classify_picture_file(path) -> (label, conf)` — Task 3, dùng ở Task 4/6. ✓
- `PageModel(..., page_class="text", cover="none")` + `.page_class`/`.cover` — Task 1, dùng ở Task 4/5/6. ✓
- Figure có `.img` (filename) và `.bbox` — khớp `page_model.py` hiện tại. ✓
- Block role `"table"` tồn tại (semantic_tagger map `"table":"table"`). ✓
