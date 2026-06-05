# Figure Text Cleaning Implementation Plan (#2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tự động dò chữ trong figure (tesseract, offline) lúc extract và xóa chữ đó bằng AI inpaint, lưu thành asset figure sạch dùng chung cho mọi ngôn ngữ; renderer ưu tiên ảnh figure sạch.

**Architecture:** `figure_text_detector.detect_text_boxes` (tesseract TSV) → tái dùng `clean_page_background_inpaint` để xóa chữ figure theo mask → lưu `Figure.clean_img` → renderer dùng `clean_img or img`. Wiring ở extractor (guard không gọi mạng khi test/không key).

**Tech Stack:** Python 3, tesseract binary, OpenCV/numpy, google-genai, pytest. Backend `apps/break_the_barriers/backend`, test `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-05-figure-text-cleaning-design.md`

## File Structure

- `app/services/figure_text_detector.py` — **mới**; `detect_text_boxes` (tesseract).
- `app/services/page_model.py` — `Figure.clean_img` field + from_dict.
- `app/services/text_layer_renderer.py` — figure src dùng `clean_img or img`.
- `app/services/extractor.py` — detect+clean figure lúc extract (guard).
- Tests: `tests/test_figure_text_detector.py` (mới); bổ sung `tests/test_page_model.py`, `tests/test_text_layer_renderer.py`.

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root. Nhánh `feat/manual-per-page` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

**Ngữ cảnh code:**
- Renderer figure emit (dòng ~106-110): `for fig in model.figures: ... src = html_lib.escape(f"{image_url_base}/{fig.img}", quote=True)`.
- `Figure` from_dict (dòng 70): `Figure(bbox=list(f["bbox"]), img=f["img"])`.
- Extractor crop (dòng ~410-411): `fname = crop_figure(...)` rồi `figures.append(Figure(bbox=fb, img=fname))`.
- Tái dùng: `clean_page_background_inpaint(src, out, boxes) -> bool` (image_cleaner.py).
- tesseract: `/opt/homebrew/bin/tesseract` (v5).

---

### Task 1: `figure_text_detector.detect_text_boxes`

**Files:**
- Create: `app/services/figure_text_detector.py`
- Test: `tests/test_figure_text_detector.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_figure_text_detector.py`:

```python
import cv2
import numpy as np
from backend.app.services.figure_text_detector import detect_text_boxes


def _text_png(path, word="FOREWORD"):
    img = np.full((140, 600, 3), 255, np.uint8)            # white bg
    cv2.putText(img, word, (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 5)
    cv2.imwrite(str(path), img)


def test_detects_text_returns_boxes(tmp_path):
    p = tmp_path / "banner.png"; _text_png(p)
    boxes = detect_text_boxes(str(p))
    assert len(boxes) >= 1
    l, t, w, h = boxes[0]
    assert w > 0 and h > 0


def test_blank_image_no_boxes(tmp_path):
    p = tmp_path / "blank.png"
    cv2.imwrite(str(p), np.full((140, 600, 3), 255, np.uint8))
    assert detect_text_boxes(str(p)) == []


def test_missing_path_no_boxes(tmp_path):
    assert detect_text_boxes(str(tmp_path / "nope.png")) == []
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_figure_text_detector.py -v` → ImportError.

- [ ] **Step 3: Cài đặt.** Tạo `app/services/figure_text_detector.py`:

```python
"""Detect baked-in text regions inside a figure crop using the tesseract binary
(offline). Returns word bounding boxes in figure pixels; empty list = no text."""
from __future__ import annotations
import os
import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)

_TESSERACT = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"


def detect_text_boxes(crop_path: str, *, min_conf: int = 40,
                      min_h_frac: float = 0.04) -> list:
    """List of (left, top, width, height) px boxes for confident text words.
    Any failure (no tesseract, unreadable image) returns []."""
    try:
        if not os.path.exists(crop_path):
            return []
        from PIL import Image
        height = Image.open(crop_path).height or 1
        proc = subprocess.run(
            [_TESSERACT, crop_path, "stdout", "--psm", "11", "tsv"],
            capture_output=True, text=True, timeout=30)
        boxes = []
        for line in proc.stdout.splitlines()[1:]:   # skip TSV header
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            text = parts[11].strip()
            if not text:
                continue
            try:
                conf = float(parts[10])
                l, t, w, h = (int(parts[6]), int(parts[7]),
                              int(parts[8]), int(parts[9]))
            except ValueError:
                continue
            if conf < min_conf or h < min_h_frac * height:
                continue
            boxes.append((l, t, w, h))
        return boxes
    except Exception as e:
        logger.warning(f"detect_text_boxes failed for {crop_path}: {e}")
        return []
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_figure_text_detector.py -v` → 3 passed.
  Nếu `test_detects_text_returns_boxes` không ra box (tesseract không đọc được ảnh tổng hợp), KHÔNG nới test — tăng kích thước/độ tương phản chữ trong `_text_png` (vd font scale 3.0, ảnh lớn hơn) cho tới khi tesseract đọc rõ "FOREWORD"; báo lại chỉnh gì.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/figure_text_detector.py \
        apps/break_the_barriers/backend/tests/test_figure_text_detector.py
git commit -m "feat(#2): figure_text_detector.detect_text_boxes (tesseract, offline)"
```

---

### Task 2: `Figure.clean_img` field

**Files:**
- Modify: `app/services/page_model.py`
- Test: `tests/test_page_model.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào `tests/test_page_model.py`:

```python
def test_figure_clean_img_roundtrip_and_default():
    from backend.app.services.page_model import PageModel, Figure
    pm = PageModel(page_w=1.0, page_h=1.0, kind="mixed",
                   background={"color": "#fff", "image": "p.png"}, blocks=[],
                   figures=[Figure(bbox=[0, 0, 10, 10], img="f.png", clean_img="f.clean.png")])
    d = pm.to_dict()
    assert d["figures"][0]["clean_img"] == "f.clean.png"
    pm2 = PageModel.from_dict(d)
    assert pm2.figures[0].clean_img == "f.clean.png"
    # old json without clean_img -> None
    pm3 = PageModel.from_dict({"page_w": 1.0, "page_h": 1.0, "kind": "mixed",
                               "background": {"color": "#fff", "image": None},
                               "blocks": [], "figures": [{"bbox": [0, 0, 5, 5], "img": "g.png"}]})
    assert pm3.figures[0].clean_img is None
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_page_model.py -k figure_clean_img -v` → FAIL (`unexpected keyword 'clean_img'`).

- [ ] **Step 3: Cài đặt.** Trong `app/services/page_model.py`:
  (a) Thêm field vào dataclass `Figure` (sau `img: str`):
  ```python
      clean_img: Optional[str] = None   # AI-cleaned (text-removed) variant filename
  ```
  (b) Trong `from_dict`, sửa dòng tạo figures (dòng 70):
  ```python
          figures = [Figure(bbox=list(f["bbox"]), img=f["img"],
                            clean_img=f.get("clean_img")) for f in d.get("figures", [])]
  ```
  (`to_dict` dùng `asdict` nên tự kèm `clean_img`.)

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_page_model.py -v` → tất cả pass.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/page_model.py \
        apps/break_the_barriers/backend/tests/test_page_model.py
git commit -m "feat(#2): Figure.clean_img field (cleaned figure asset)"
```

---

### Task 3: Renderer dùng `clean_img or img`

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_renderer.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào `tests/test_text_layer_renderer.py`:

```python
def test_figure_uses_clean_img_when_present():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[],
        figures=[Figure(bbox=[10, 10, 100, 50], img="f1.png", clean_img="f1.clean.png")],
        page_class="text", cover="none")
    html = render_text_layer(pm, {}, image_url_base="http://api/assets")
    assert "f1.clean.png" in html
    assert "f1.png" not in html.replace("f1.clean.png", "")


def test_figure_falls_back_to_img_without_clean():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[], figures=[Figure(bbox=[10, 10, 100, 50], img="f1.png")],
        page_class="text", cover="none")
    html = render_text_layer(pm, {}, image_url_base="http://api/assets")
    assert "f1.png" in html
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_text_layer_renderer.py -k "figure_uses_clean or figure_falls_back" -v` → `figure_uses_clean` FAIL.

- [ ] **Step 3: Cài đặt.** Trong `app/services/text_layer_renderer.py`, vòng vẽ figure (dòng ~106-108), đổi:
```python
    for fig in model.figures:
        l, t, w, h = fig.bbox
        src = html_lib.escape(f"{image_url_base}/{fig.img}", quote=True)
```
thành:
```python
    for fig in model.figures:
        l, t, w, h = fig.bbox
        fig_name = fig.clean_img or fig.img
        src = html_lib.escape(f"{image_url_base}/{fig_name}", quote=True)
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_text_layer_renderer.py -v` → tất cả pass.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_text_layer_renderer.py
git commit -m "feat(#2): renderer prefers figure.clean_img"
```

---

### Task 4: Extractor — detect + clean figure lúc extract

**Files:**
- Modify: `app/services/extractor.py`

Integration — verify bằng import + full suite (không gọi mạng nhờ guard) + backfill (Task 5).

- [ ] **Step 1: Thêm guard helper.** Trong `app/services/extractor.py`, gần đầu (sau imports/logger), thêm:
```python
def _figure_cleaning_enabled() -> bool:
    """Only auto-clean figures outside tests and when an API key exists."""
    return (not os.getenv("PYTEST_CURRENT_TEST")) and bool(os.getenv("GEMINI_API_KEY"))
```

- [ ] **Step 2: Wiring.** Thay khối crop figure (dòng ~405-411) — hiện:
```python
                for i, fb in enumerate(fig_boxes, start=1):
                    try:
                        fname = crop_figure(pil_img, fb, sx, sy, output_dir, doc_id, page_no, i)
                        figures.append(Figure(bbox=fb, img=fname))
                    except Exception as e:
                        logger.warning(f"Figure crop failed p{page_no} #{i}: {e}")
```
thành:
```python
                for i, fb in enumerate(fig_boxes, start=1):
                    try:
                        fname = crop_figure(pil_img, fb, sx, sy, output_dir, doc_id, page_no, i)
                        _fig = Figure(bbox=fb, img=fname)
                        if _figure_cleaning_enabled():
                            try:
                                from backend.app.services.figure_text_detector import detect_text_boxes
                                from backend.app.services.image_cleaner import clean_page_background_inpaint
                                _cp = os.path.join(output_dir, fname)
                                _tboxes = detect_text_boxes(_cp)
                                if _tboxes:
                                    _cn = fname.rsplit(".", 1)[0] + ".clean.png"
                                    if clean_page_background_inpaint(_cp, os.path.join(output_dir, _cn), _tboxes):
                                        _fig.clean_img = _cn
                            except Exception as _e:
                                logger.warning(f"Figure clean failed p{page_no} #{i}: {_e}")
                        figures.append(_fig)
                    except Exception as e:
                        logger.warning(f"Figure crop failed p{page_no} #{i}: {e}")
```

- [ ] **Step 3: Kiểm tra import + full suite.**
Run: `PYTHONPATH=/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers .venv/bin/python -c "import backend.app.services.extractor; print('ok')"` → ok.
Run: `.venv/bin/pytest tests/ -q --ignore=tests/test_extractor_box.py --ignore=tests/test_extractor_overhaul.py --ignore=tests/test_extractor_pagemodel.py` → all pass (guard ⇒ không gọi mạng). Báo số đếm.

- [ ] **Step 4: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/extractor.py
git commit -m "feat(#2): extractor auto-detects + cleans baked text in figures"
```

---

### Task 5: Verify thật trên doc (manual — controller)

**Files:** không.

- [ ] **Step 1:** Controller chạy one-off: với `2024-wttc-introduction-to-ai` trang 3, load model_json, với mỗi figure: `detect_text_boxes` trên crop; nếu có chữ → `clean_page_background_inpaint` (gọi AI thật, có key) → set `figure.clean_img`; lưu DB model_json. In số box phát hiện + figure nào được clean.
- [ ] **Step 2:** Chrome headless screenshot `pages/3?lang=vi&raw=true`; xác nhận banner "FOREWORD" KHÔNG còn chữ (chỉ overlay "LỜI NÓI ĐẦU"). Đọc ảnh figure sạch `*-3-*.clean.png` để đối chiếu.
- [ ] **Step 3:** Gửi ảnh + báo cáo; xác nhận #2 đạt (banner hết ghost).

---

## Self-Review

**Spec coverage:**
- A `detect_text_boxes` (tesseract TSV, conf+size filter, fail→[]) → Task 1. ✓
- B `Figure.clean_img` + serialize → Task 2. ✓
- C tái dùng `clean_page_background_inpaint` (không hàm clean mới) → Task 4 wiring. ✓
- D extractor detect+clean + guard test/key + fail-safe → Task 4. ✓
- E renderer `clean_img or img` → Task 3. ✓
- Kiểm thử: detector, Figure round-trip, renderer; verify backfill → Task 1/2/3/5. ✓
- Ngoài phạm vi (dịch chữ trong figure, manual trigger, TOC) → tôn trọng. ✓

**Placeholder scan:** không TBD; mọi step có code/lệnh. ✓

**Type consistency:**
- `detect_text_boxes(crop_path, *, min_conf=40, min_h_frac=0.04) -> list[(l,t,w,h)]` — Task 1; dùng ở Task 4 + verify Task 5. ✓
- `Figure(..., clean_img=None)` + `.clean_img` — Task 2; đọc renderer Task 3, set extractor Task 4. ✓
- `clean_page_background_inpaint(src, out, boxes) -> bool` (đã có) — gọi Task 4/5 với `boxes` = text boxes. ✓
- `fig_name = fig.clean_img or fig.img` — Task 3. ✓
