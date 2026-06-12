# Masked AI Inpaint Cleaning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm method làm sạch nền `inpaint`: Gemini sinh ảnh sạch toàn phần nhưng chỉ composite vùng có chữ (theo mask từ bbox block) lên ảnh gốc → bảo toàn phần ảnh ngoài chữ; để so chất lượng với method `full` hiện có.

**Architecture:** Tách phần gọi Gemini thành `_gemini_clean_bytes`. Thêm `build_text_mask` + `composite_inpaint` (numpy/cv2 thuần) + `clean_page_background_inpaint`. Endpoint `clean-bg` thêm `method=full|inpaint`, tính `boxes_px` từ block bbox × scale raster. Frontend thêm chọn method (manual). Tôi chạy thật cả 2 biến thể để người dùng đánh giá.

**Tech Stack:** Python 3, pytest, OpenCV (`cv2`), numpy, Pillow, google-genai. Backend ở `apps/break_the_barriers/backend`, test bằng `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-05-masked-ai-inpaint-cleaning-design.md`

## File Structure

- `app/services/image_cleaner.py` — refactor `_gemini_clean_bytes`; thêm `build_text_mask`, `composite_inpaint`, `clean_page_background_inpaint`.
- `app/routers/documents.py` — `clean-bg` thêm `method` + tính `boxes_px`.
- Frontend `apps/break_the_barriers/frontend` — chọn method trong nút làm sạch (manual).
- Tests: bổ sung `tests/test_image_cleaner.py`, `tests/test_preview_pagemodel.py`.

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`. Nhánh `feat/ai-cover-cleaning` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

---

### Task 1: Refactor `_gemini_clean_bytes`

**Files:**
- Modify: `app/services/image_cleaner.py`
- Test: `tests/test_image_cleaner.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_image_cleaner.py` (đã có `_client_returning`, `_make_png`):

```python
from backend.app.services.image_cleaner import _gemini_clean_bytes


def test_gemini_clean_bytes_returns_data(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    data = _gemini_clean_bytes(str(src), client=_client_returning(b"AIBYTES"))
    assert data == b"AIBYTES"


def test_gemini_clean_bytes_none_when_no_image(tmp_path):
    import types
    src = tmp_path / "page-1.png"; _make_png(src)
    empty = types.SimpleNamespace(content=types.SimpleNamespace(parts=[]))
    client = types.SimpleNamespace(models=types.SimpleNamespace(
        generate_content=lambda **kw: types.SimpleNamespace(candidates=[empty])))
    assert _gemini_clean_bytes(str(src), client=client) is None
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_image_cleaner.py -k gemini_clean_bytes -v` → ImportError.

- [ ] **Step 3: Refactor.** Trong `app/services/image_cleaner.py`, thay hàm `clean_page_background` (dòng 29-54) bằng helper + wrapper:

```python
def _gemini_clean_bytes(src_path: str, *, client=None,
                        model: str | None = None) -> bytes | None:
    """Call Gemini image-edit and return the cleaned image bytes, or None on any
    failure (no key, no image in response, API error)."""
    model = model or _default_model()
    try:
        from PIL import Image
        if client is None:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return None
            client = genai.Client(api_key=api_key)
        img = Image.open(src_path)
        resp = client.models.generate_content(model=model, contents=[_PROMPT, img])
        for cand in (getattr(resp, "candidates", None) or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline else None
                if data:
                    return data
        return None
    except Exception as e:
        logger.warning(f"_gemini_clean_bytes failed for {src_path}: {e}")
        return None


def clean_page_background(src_path: str, out_path: str, *, client=None,
                         model: str | None = None) -> bool:
    data = _gemini_clean_bytes(src_path, client=client, model=model)
    if not data:
        return False
    with open(out_path, "wb") as fh:
        fh.write(data)
    return True
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_image_cleaner.py -v` → tất cả pass (3 test cũ vẫn xanh + 2 mới).

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/image_cleaner.py \
        apps/break_the_barriers/backend/tests/test_image_cleaner.py
git commit -m "refactor(phase2): extract _gemini_clean_bytes from clean_page_background"
```

---

### Task 2: `build_text_mask` + `composite_inpaint` (numpy/cv2 thuần)

**Files:**
- Modify: `app/services/image_cleaner.py`
- Test: `tests/test_image_cleaner.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_image_cleaner.py`:

```python
import numpy as np
from backend.app.services.image_cleaner import build_text_mask, composite_inpaint


def test_build_text_mask_marks_box_and_clears_corner():
    mask = build_text_mask([(40, 40, 20, 20)], 100, 100, dilate=0, feather=0)
    assert mask.shape == (100, 100)
    assert mask[50, 50] == 1.0      # bên trong box
    assert mask[0, 0] == 0.0        # góc xa


def test_build_text_mask_dilate_expands():
    base = build_text_mask([(40, 40, 20, 20)], 100, 100, dilate=0, feather=0)
    grown = build_text_mask([(40, 40, 20, 20)], 100, 100, dilate=6, feather=0)
    assert grown.sum() > base.sum()      # nới biên → vùng rộng hơn


def test_composite_takes_ai_inside_mask_original_outside():
    original = np.zeros((40, 40, 3), np.uint8); original[:, :, 0] = 255   # BGR: xanh dương
    ai = np.zeros((40, 40, 3), np.uint8); ai[:, :, 2] = 255               # BGR: đỏ
    mask = build_text_mask([(15, 15, 10, 10)], 40, 40, dilate=0, feather=0)
    out = composite_inpaint(original, ai, mask)
    assert out[20, 20, 2] > 200 and out[20, 20, 0] < 60   # giữa = đỏ (ai)
    assert out[0, 0, 0] > 200 and out[0, 0, 2] < 60       # góc = xanh (gốc)
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_image_cleaner.py -k "mask or composite" -v` → ImportError.

- [ ] **Step 3: Cài đặt.** Thêm vào `app/services/image_cleaner.py` (sau `clean_page_background`):

```python
def build_text_mask(boxes_px, width: int, height: int, *,
                    dilate: int = 6, feather: int = 9):
    """Soft mask (float [0,1], shape HxW) = 1 where text boxes are.
    boxes_px: iterable of (l, t, w, h) in pixels."""
    import numpy as np
    import cv2
    mask = np.zeros((height, width), dtype=np.uint8)
    for (l, t, w, h) in boxes_px:
        x0 = max(0, int(round(l))); y0 = max(0, int(round(t)))
        x1 = min(width, int(round(l + w))); y1 = min(height, int(round(t + h)))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = 255
    if dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (dilate * 2 + 1, dilate * 2 + 1))
        mask = cv2.dilate(mask, k)
    if feather > 0:
        kf = feather if feather % 2 == 1 else feather + 1
        mask = cv2.GaussianBlur(mask, (kf, kf), 0)
    return mask.astype(np.float32) / 255.0


def composite_inpaint(original_bgr, ai_bgr, mask):
    """result = original*(1-mask) + resize(ai)*mask. Outside the mask the output
    is pixel-identical to original_bgr."""
    import numpy as np
    import cv2
    h, w = original_bgr.shape[:2]
    if ai_bgr.shape[:2] != (h, w):
        ai_bgr = cv2.resize(ai_bgr, (w, h), interpolation=cv2.INTER_AREA)
    m3 = np.dstack([mask, mask, mask]).astype(np.float32)
    out = original_bgr.astype(np.float32) * (1.0 - m3) + ai_bgr.astype(np.float32) * m3
    return np.clip(out, 0, 255).astype(np.uint8)
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_image_cleaner.py -v` → tất cả pass.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/image_cleaner.py \
        apps/break_the_barriers/backend/tests/test_image_cleaner.py
git commit -m "feat(inpaint): build_text_mask + composite_inpaint (pure numpy/cv2)"
```

---

### Task 3: `clean_page_background_inpaint`

**Files:**
- Modify: `app/services/image_cleaner.py`
- Test: `tests/test_image_cleaner.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_image_cleaner.py`:

```python
import cv2
from backend.app.services.image_cleaner import clean_page_background_inpaint


def _png_bytes(bgr):
    ok, buf = cv2.imencode(".png", bgr)
    return buf.tobytes()


def test_inpaint_composites_ai_only_in_mask(tmp_path):
    src = tmp_path / "page-1.png"
    blue = np.zeros((40, 40, 3), np.uint8); blue[:, :, 0] = 255   # ảnh gốc xanh
    cv2.imwrite(str(src), blue)
    red = np.zeros((40, 40, 3), np.uint8); red[:, :, 2] = 255     # ảnh AI đỏ
    out = tmp_path / "page-1.clean-inpaint.png"
    ok = clean_page_background_inpaint(
        str(src), str(out), [(15, 15, 10, 10)],
        client=_client_returning(_png_bytes(red)))
    assert ok is True
    res = cv2.imread(str(out))
    assert res[20, 20, 2] > 200      # giữa = đỏ (AI trám)
    assert res[0, 0, 0] > 200        # góc = xanh (gốc giữ nguyên)


def test_inpaint_false_when_ai_returns_no_image(tmp_path):
    import types
    src = tmp_path / "page-1.png"
    cv2.imwrite(str(src), np.zeros((10, 10, 3), np.uint8))
    out = tmp_path / "o.png"
    empty = types.SimpleNamespace(content=types.SimpleNamespace(parts=[]))
    client = types.SimpleNamespace(models=types.SimpleNamespace(
        generate_content=lambda **kw: types.SimpleNamespace(candidates=[empty])))
    assert clean_page_background_inpaint(str(src), str(out), [(1, 1, 2, 2)],
                                         client=client) is False
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_image_cleaner.py -k inpaint_ -v` → ImportError.

- [ ] **Step 3: Cài đặt.** Thêm vào `app/services/image_cleaner.py` (sau `composite_inpaint`):

```python
def clean_page_background_inpaint(src_path: str, out_path: str, boxes_px, *,
                                  client=None, model: str | None = None) -> bool:
    """Gemini-clean the whole page, then composite ONLY the text-box regions onto
    the original so everything else stays pixel-identical. Returns False on any
    failure (caller keeps the original raster)."""
    try:
        import numpy as np
        import cv2
        data = _gemini_clean_bytes(src_path, client=client, model=model)
        if not data:
            return False
        ai = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        original = cv2.imread(src_path, cv2.IMREAD_COLOR)
        if ai is None or original is None:
            return False
        h, w = original.shape[:2]
        mask = build_text_mask(boxes_px, w, h)
        result = composite_inpaint(original, ai, mask)
        cv2.imwrite(out_path, result)
        return True
    except Exception as e:
        logger.warning(f"clean_page_background_inpaint failed for {src_path}: {e}")
        return False
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_image_cleaner.py -v` → tất cả pass.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/image_cleaner.py \
        apps/break_the_barriers/backend/tests/test_image_cleaner.py
git commit -m "feat(inpaint): clean_page_background_inpaint (mask-composite AI clean)"
```

---

### Task 4: Endpoint `clean-bg` thêm `method=full|inpaint`

**Files:**
- Modify: `app/routers/documents.py` (hàm `clean_page_bg` từ Pha 2)
- Test: `tests/test_preview_pagemodel.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_preview_pagemodel.py` (đã có `_seed_clean_photo`, `_image_cleaner_mod`, `DATA_DIR`, `import os`):

```python
def test_clean_bg_inpaint_method_sets_inpaint_file(client, db_session, monkeypatch):
    _seed_clean_photo(db_session)
    # raster gốc phải tồn tại để endpoint mở lấy kích thước tính boxes_px
    import cv2, numpy as np
    doc_dir = os.path.join(DATA_DIR, "extracted_html", "cp_doc")
    os.makedirs(doc_dir, exist_ok=True)
    cv2.imwrite(os.path.join(doc_dir, "page-1.png"), np.zeros((20, 20, 3), np.uint8))

    def _fake_inpaint(src, out, boxes, **kw):
        with open(out, "wb") as f:
            f.write(b"INP")
        return True
    monkeypatch.setattr(_image_cleaner_mod, "clean_page_background_inpaint", _fake_inpaint)

    r = client.post("/api/docs/cp_doc/pages/1/clean-bg?method=inpaint")
    assert r.status_code == 200
    assert r.json()["clean_image"] == "page-1.clean-inpaint.png"
    from backend.app.models_db import DBPage
    page = db_session.query(DBPage).filter(DBPage.document_id == "cp_doc",
                                           DBPage.page_num == 1).first()
    assert "page-1.clean-inpaint.png" in page.model_json
    for fn in ("page-1.png", "page-1.clean-inpaint.png"):
        p = os.path.join(doc_dir, fn)
        if os.path.exists(p):
            os.remove(p)
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_preview_pagemodel.py -k inpaint_method -v` → FAIL (vẫn ra `page-1.clean.png` / route chưa nhận method).

- [ ] **Step 3: Cài đặt.** Sửa hàm `clean_page_bg` trong `app/routers/documents.py`. Thêm tham số `method` và nhánh inpaint. Hàm hiện tại (Pha 2) bắt đầu bằng `def clean_page_bg(doc_id, page_num, force=Query(False), db=...)`. Đổi chữ ký + phần tính tên file & gọi cleaner:

(a) Chữ ký:
```python
@router.post("/api/docs/{doc_id}/pages/{page_num}/clean-bg")
def clean_page_bg(doc_id: str, page_num: int,
                  method: str = Query("full"), force: bool = Query(False),
                  db: Session = Depends(get_db)):
```

(b) Sau khi đã có `pm`, gating clean-photo, `src_name` (như Pha 2) và `doc_dir`, thay khối tính `clean_name`/gọi cleaner bằng:
```python
    if method == "inpaint":
        clean_name = src_name.rsplit(".", 1)[0] + ".clean-inpaint.png"
    else:
        clean_name = src_name.rsplit(".", 1)[0] + ".clean.png"
    clean_path = os.path.join(doc_dir, clean_name)

    if os.path.exists(clean_path) and not force:
        status = "cached"
    else:
        src_path = os.path.join(doc_dir, src_name)
        if method == "inpaint":
            # boxes_px = block bbox (points) scaled to raster pixels
            boxes_px = []
            try:
                from PIL import Image as _Image
                rw, rh = _Image.open(src_path).size
                sx = rw / (pm.page_w or 1.0)
                sy = rh / (pm.page_h or 1.0)
                for b in pm.blocks:
                    l, t, w, h = b.bbox
                    boxes_px.append((l * sx, t * sy, w * sx, h * sy))
            except Exception:
                boxes_px = []
            ok = image_cleaner.clean_page_background_inpaint(src_path, clean_path, boxes_px)
        else:
            ok = image_cleaner.clean_page_background(src_path, clean_path)
        if not ok:
            raise HTTPException(status_code=502, detail="Background cleaning failed")
        status = "cleaned"

    pm.background["clean_image"] = clean_name
    page.model_json = pm.to_json()
    db.commit()
    return {"status": status, "clean_image": clean_name, "method": method}
```
Giữ nguyên các guard 404/400 và import `image_cleaner`/`PageModel`/`resolve_background_policy` ở đầu hàm như Pha 2. Gọi cleaner qua module `image_cleaner.clean_page_background_inpaint(...)` để test monkeypatch được.

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_preview_pagemodel.py -v` → tất cả pass (gồm test full cũ + inpaint mới).

- [ ] **Step 5: Full suite** — `.venv/bin/pytest tests/ -q --ignore=tests/test_extractor_box.py --ignore=tests/test_extractor_overhaul.py --ignore=tests/test_extractor_pagemodel.py` → tất cả pass. Báo số đếm.

- [ ] **Step 6: Commit**
```bash
git add apps/break_the_barriers/backend/app/routers/documents.py \
        apps/break_the_barriers/backend/tests/test_preview_pagemodel.py
git commit -m "feat(inpaint): clean-bg method=full|inpaint (scale block bbox to mask)"
```

---

### Task 5: Frontend — chọn method (tối thiểu)

**Files:**
- Modify: preview component trong `apps/break_the_barriers/frontend`.

Manual, không TDD. ĐỌC component (đã sửa ở Pha 2) trước.

- [ ] **Step 1:** Mở component preview (chứa nút "Làm sạch nền AI" từ Pha 2). Xác định chỗ gọi `POST .../clean-bg`.

- [ ] **Step 2:** Đổi nút thành **2 nút con**: "Làm sạch (Full)" → `POST clean-bg?method=full`; "Làm sạch (Inpaint)" → `POST clean-bg?method=inpaint`. Sau 200, reload tab hiện tại với cache-bust (`&t=${Date.now()}`). Giữ điều kiện hiện chỉ trên trang clean-photo.

- [ ] **Step 3:** Build check — `cd apps/break_the_barriers/frontend && npx tsc --noEmit` → không lỗi.

- [ ] **Step 4: Commit**
```bash
git add apps/break_the_barriers/frontend
git commit -m "feat(inpaint): preview method buttons (Full / Inpaint)"
```

---

### Task 6: Chạy thật & so sánh Full vs Inpaint (manual — controller làm)

**Files:** không.

- [ ] **Step 1:** Controller chạy CLI (2 lần gọi AI) tạo 2 biến thể trên bìa thật: `page-1` full vs inpaint (boxes từ block bbox × 2.0). Dùng `clean_page_background` và `clean_page_background_inpaint` với key thật (`dotenv.load_dotenv('../.env')`).

- [ ] **Step 2:** Controller gửi cả hai ảnh cho người dùng so sánh và hỏi chọn method mặc định. (Việc này do controller thực hiện sau khi Task 1–4 xanh, KHÔNG phải subagent.)

---

## Self-Review

**Spec coverage:**
- `_gemini_clean_bytes` refactor (full vẫn hoạt động) → Task 1. ✓
- `build_text_mask` (bbox→rect, dilate, feather) → Task 2. ✓
- `composite_inpaint` (ngoài mask = gốc) → Task 2. ✓
- `clean_page_background_inpaint` (AI bytes → composite) → Task 3. ✓
- Endpoint `method=full|inpaint` + boxes_px từ block×scale + file biến thể → Task 4. ✓
- Frontend chọn method → Task 5. ✓
- Chạy thật so sánh → Task 6. ✓
- Kiểm thử mask/composite/inpaint/_gemini_clean_bytes/endpoint → Task 1–4. ✓
- Ngoài phạm vi (cv2.inpaint cổ điển, mask bám nét, side-by-side UI, chốt default) → tôn trọng. ✓

**Placeholder scan:** không TBD/TODO; mọi step có code/lệnh. ✓

**Type consistency:**
- `_gemini_clean_bytes(src, *, client, model) -> bytes|None` — Task 1, dùng ở `clean_page_background` (Task 1) và `clean_page_background_inpaint` (Task 3). ✓
- `build_text_mask(boxes_px, width, height, *, dilate=6, feather=9) -> ndarray` — Task 2, dùng ở Task 3. ✓
- `composite_inpaint(original_bgr, ai_bgr, mask) -> ndarray` — Task 2, dùng ở Task 3. ✓
- `clean_page_background_inpaint(src, out, boxes_px, *, client, model) -> bool` — Task 3, gọi ở endpoint Task 4 và test monkeypatch cùng tên. ✓
- `background["clean_image"]` (= `page-N.clean.png` | `page-N.clean-inpaint.png`) — set Task 4, đọc renderer (Pha 2) + frontend. ✓
- `boxes_px` = list `(l,t,w,h)` pixel — tính ở Task 4, nhận ở `build_text_mask`/`clean_page_background_inpaint`. ✓
