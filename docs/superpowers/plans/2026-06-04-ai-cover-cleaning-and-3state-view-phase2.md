# Pha 2 — AI Cover Cleaning + 3 trạng thái xem — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Người dùng bấm nút làm sạch nền trên trang bìa → AI (Gemini) xóa chữ nung khỏi ảnh → cache `page-N.clean.png` → renderer dùng ảnh sạch + chữ dịch (bìa hết ghost); thêm 3 trạng thái xem Gốc/HTML/Dịch.

**Architecture:** Service `image_cleaner.py` gọi Gemini image-edit (client tiêm được để test). Endpoint `POST .../clean-bg` (gating `clean-photo`, cache, lưu `background.clean_image` — KHÔNG ghi đè `background.image`). `render_text_layer` ưu tiên `clean_image` cho clean-photo. "Gốc" nhúng endpoint PDF sẵn có (không backend mới). Frontend: toggle 3 nút + nút làm sạch (verify thủ công).

**Tech Stack:** Python 3, pytest, google-genai 2.6.0, Pillow; Next.js frontend. Backend ở `apps/break_the_barriers/backend`, test bằng `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-04-ai-cover-cleaning-and-3state-view-phase2-design.md`

## File Structure

- `app/services/image_cleaner.py` — **mới**; `clean_page_background` (Gemini, client tiêm được).
- `app/services/text_layer_renderer.py` — clean-photo ưu tiên `background.clean_image`.
- `app/routers/documents.py` — endpoint `POST /api/docs/{id}/pages/{n}/clean-bg`.
- Frontend `apps/break_the_barriers/frontend` — toggle Gốc/HTML/Dịch + nút "Làm sạch nền AI".
- Tests: `tests/test_image_cleaner.py` (mới); bổ sung `tests/test_text_layer_renderer.py`, `tests/test_preview_pagemodel.py`.

**Lệnh:** test chạy từ `apps/break_the_barriers/backend` bằng `.venv/bin/pytest`; git từ repo root `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`. Import `backend.app...`. Nhánh hiện tại `feat/ai-cover-cleaning` (đã checkout — KHÔNG tạo nhánh).

**Ngữ cảnh code:**
- genai client: `from google import genai; client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")); client.models.generate_content(model=..., contents=[...])`.
- `DATA_DIR` import: `from backend.app.core import DATA_DIR`; thư mục trang: `DATA_DIR/extracted_html/{doc_id}`.
- `render_text_layer` (sau Pha 1): có `policy`/`draw_raster`; khối raster là `image_name = (model.background or {}).get("image")` rồi `if image_name and draw_raster:`.
- Endpoint pages dùng `db.query(DBPage).filter(DBPage.document_id==doc_id, DBPage.page_num==page_num).first()`.

---

### Task 1: `image_cleaner.py` — Gemini xóa chữ (client tiêm được)

**Files:**
- Create: `app/services/image_cleaner.py`
- Test: `tests/test_image_cleaner.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_image_cleaner.py`:

```python
import types
from PIL import Image
from backend.app.services.image_cleaner import clean_page_background


def _make_png(path):
    Image.new("RGB", (8, 8), (10, 20, 30)).save(path)


def _client_returning(data):
    part = types.SimpleNamespace(inline_data=types.SimpleNamespace(data=data))
    content = types.SimpleNamespace(parts=[part])
    resp = types.SimpleNamespace(candidates=[types.SimpleNamespace(content=content)])
    return types.SimpleNamespace(
        models=types.SimpleNamespace(generate_content=lambda **kw: resp))


def test_writes_cleaned_image_on_success(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    out = tmp_path / "page-1.clean.png"
    ok = clean_page_background(str(src), str(out), client=_client_returning(b"PNGBYTES"))
    assert ok is True
    assert out.read_bytes() == b"PNGBYTES"


def test_returns_false_when_no_image_in_response(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    out = tmp_path / "page-1.clean.png"
    empty = types.SimpleNamespace(content=types.SimpleNamespace(parts=[]))
    client = types.SimpleNamespace(models=types.SimpleNamespace(
        generate_content=lambda **kw: types.SimpleNamespace(candidates=[empty])))
    assert clean_page_background(str(src), str(out), client=client) is False
    assert not out.exists()


def test_returns_false_on_client_error(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    out = tmp_path / "page-1.clean.png"
    def _boom(**kw):
        raise RuntimeError("api down")
    client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=_boom))
    assert clean_page_background(str(src), str(out), client=client) is False
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_image_cleaner.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Cài đặt.** Tạo `app/services/image_cleaner.py`:

```python
"""Clean baked-in text off a page raster using Gemini image editing (Phase 2).

Used only on `clean-photo` pages (covers / full-bleed art), on demand. Returns
True and writes a text-free PNG to out_path on success; any failure (no API key,
no image in response, API error) returns False so the caller keeps the original
raster. `client` is injectable so tests run without network."""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

_PROMPT = (
    "Remove ALL overlaid text, letters, numbers, and captions from this image. "
    "Keep the photograph, illustration, colors, lighting, and composition exactly "
    "the same. Output the same image with no text anywhere."
)


def _default_model() -> str:
    return os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")


def clean_page_background(src_path: str, out_path: str, *, client=None,
                          model: str | None = None) -> bool:
    model = model or _default_model()
    try:
        from PIL import Image
        if client is None:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                return False
            client = genai.Client(api_key=api_key)
        img = Image.open(src_path)
        resp = client.models.generate_content(model=model, contents=[_PROMPT, img])
        for cand in (getattr(resp, "candidates", None) or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline else None
                if data:
                    with open(out_path, "wb") as fh:
                        fh.write(data)
                    return True
        return False
    except Exception as e:
        logger.warning(f"clean_page_background failed for {src_path}: {e}")
        return False
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_image_cleaner.py -v` → 3 passed.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/image_cleaner.py \
        apps/break_the_barriers/backend/tests/test_image_cleaner.py
git commit -m "feat(phase2): image_cleaner — Gemini text removal (injectable client)"
```

---

### Task 2: Renderer ưu tiên `clean_image` cho clean-photo

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_renderer.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_text_layer_renderer.py`:

```python
def _clean_photo_model(clean_image=None):
    bg = {"color": "#000", "image": "page-1.png"}
    if clean_image:
        bg["clean_image"] = clean_image
    return PageModel(
        page_w=595.0, page_h=842.0, kind="mixed", background=bg,
        blocks=[Block(span_id="s1", role="heading", bbox=[36, 516, 432, 60],
                      text="", font=FontSpec(36, 700, False, "#fff", "left", "sans"))],
        figures=[],
        page_class="regenerable", cover="front",
    )


def test_clean_photo_uses_clean_image_when_present():
    html = render_text_layer(_clean_photo_model("page-1.clean.png"),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert "page-1.clean.png" in html      # dùng ảnh sạch
    assert "page-1.png" not in html.replace("page-1.clean.png", "")  # không dùng ảnh gốc


def test_clean_photo_falls_back_to_raster_when_not_cleaned():
    html = render_text_layer(_clean_photo_model(None),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert "page-1.png" in html
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_text_layer_renderer.py -k clean_photo -v` → `test_clean_photo_uses_clean_image_when_present` FAIL (vẫn vẽ page-1.png).

- [ ] **Step 3: Cài đặt.** Trong `app/services/text_layer_renderer.py`, sửa khối chọn ảnh nền. Đoạn hiện tại (sau Pha 1):
```python
    image_name = (model.background or {}).get("image")
    if image_name and draw_raster:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
```
Đổi thành (ưu tiên `clean_image` khi policy là clean-photo):
```python
    bgd = model.background or {}
    image_name = bgd.get("image")
    if policy == "clean-photo" and bgd.get("clean_image"):
        image_name = bgd.get("clean_image")
    if image_name and draw_raster:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
```
(`policy` và `draw_raster` đã có từ Pha 1. Không đổi gì khác.)

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_text_layer_renderer.py -v` → tất cả pass.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_text_layer_renderer.py
git commit -m "feat(phase2): renderer prefers background.clean_image on clean-photo"
```

---

### Task 3: Endpoint `POST .../pages/{n}/clean-bg`

**Files:**
- Modify: `app/routers/documents.py`
- Test: `tests/test_preview_pagemodel.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_preview_pagemodel.py` (file đã có `_seed`, `_MODEL`, fixtures `client, db_session`, `import json`):

```python
import os
from backend.app.core import DATA_DIR
from backend.app.services import image_cleaner as _image_cleaner_mod


def _seed_clean_photo(db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="cp_doc", filename="c.pdf", total_pages=1, status="translated"))
    model = {"page_w": 595.0, "page_h": 842.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png"},
             "blocks": [], "figures": [],
             "page_class": "regenerable", "cover": "front"}
    db_session.add(DBPage(document_id="cp_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()


def test_clean_bg_updates_model_json(client, db_session, monkeypatch):
    _seed_clean_photo(db_session)

    def _fake_clean(src, out, **kw):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(b"CLEAN")
        return True
    monkeypatch.setattr(_image_cleaner_mod, "clean_page_background", _fake_clean)

    r = client.post("/api/docs/cp_doc/pages/1/clean-bg")
    assert r.status_code == 200
    assert r.json()["clean_image"] == "page-1.clean.png"
    # model_json now carries clean_image
    from backend.app.models_db import DBPage
    page = db_session.query(DBPage).filter(DBPage.document_id == "cp_doc",
                                           DBPage.page_num == 1).first()
    assert "page-1.clean.png" in page.model_json
    # cleanup the file written under DATA_DIR
    p = os.path.join(DATA_DIR, "extracted_html", "cp_doc", "page-1.clean.png")
    if os.path.exists(p):
        os.remove(p)


def test_clean_bg_rejects_non_clean_photo(client, db_session):
    _seed(db_session, _MODEL)   # _MODEL is a text page -> base-color, not clean-photo
    r = client.post("/api/docs/p_doc/pages/1/clean-bg")
    assert r.status_code == 400
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_preview_pagemodel.py -k clean_bg -v` → 404/405 (route chưa có).

- [ ] **Step 3: Cài đặt.** Trong `app/routers/documents.py`, thêm endpoint mới (đặt sau `get_page_content`). Dùng các import sẵn có ở đầu file (`DATA_DIR`, `os`, `HTTPException`, `Query`, `Depends`, `get_db`, `DBDocument`, `DBPage`); thêm `PageModel` import cục bộ.

```python
@router.post("/api/docs/{doc_id}/pages/{page_num}/clean-bg")
def clean_page_bg(doc_id: str, page_num: int,
                  force: bool = Query(False), db: Session = Depends(get_db)):
    from backend.app.services.page_model import PageModel
    from backend.app.services.background_policy import resolve_background_policy
    from backend.app.services import image_cleaner

    page = db.query(DBPage).filter(DBPage.document_id == doc_id,
                                   DBPage.page_num == page_num).first()
    if not page or not page.model_json:
        raise HTTPException(status_code=404, detail="Page or model not found")
    pm = PageModel.from_json(page.model_json)
    if resolve_background_policy(pm.page_class, pm.cover) != "clean-photo":
        raise HTTPException(status_code=400, detail="Page is not a clean-photo page")
    src_name = (pm.background or {}).get("image")
    if not src_name:
        raise HTTPException(status_code=400, detail="Page has no raster to clean")

    doc_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)
    clean_name = src_name.rsplit(".", 1)[0] + ".clean.png"
    clean_path = os.path.join(doc_dir, clean_name)

    if os.path.exists(clean_path) and not force:
        status = "cached"
    else:
        ok = image_cleaner.clean_page_background(
            os.path.join(doc_dir, src_name), clean_path)
        if not ok:
            raise HTTPException(status_code=502, detail="Background cleaning failed")
        status = "cleaned"

    pm.background["clean_image"] = clean_name
    page.model_json = pm.to_json()
    db.commit()
    return {"status": status, "clean_image": clean_name}
```

Lưu ý import: nếu `Session` chưa import ở đầu `documents.py`, thêm `from sqlalchemy.orm import Session` (kiểm tra — phần lớn router đã có vì dùng `Depends(get_db)`). Endpoint gọi `image_cleaner.clean_page_background` qua module (`image_cleaner.clean_page_background`) để test monkeypatch được.

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_preview_pagemodel.py -v` → tất cả pass (test cũ + 2 mới).

- [ ] **Step 5: Full suite (no regression)** — `.venv/bin/pytest tests/ -q --ignore=tests/test_extractor_box.py --ignore=tests/test_extractor_overhaul.py --ignore=tests/test_extractor_pagemodel.py` → tất cả pass. Báo số đếm.

- [ ] **Step 6: Commit**
```bash
git add apps/break_the_barriers/backend/app/routers/documents.py \
        apps/break_the_barriers/backend/tests/test_preview_pagemodel.py
git commit -m "feat(phase2): POST clean-bg endpoint (gate clean-photo, cache, set clean_image)"
```

---

### Task 4: Frontend — toggle Gốc/HTML/Dịch + nút làm sạch (tối thiểu)

**Files:**
- Modify: component preview trong `apps/break_the_barriers/frontend` (route `/books/[id]/preview`).

Đây là task frontend, verify thủ công (không TDD pytest). Cẩn thận: ĐỌC component hiện tại trước.

- [ ] **Step 1: Tìm component toggle hiện tại.**
Run: `grep -rn "Original\|Translated\|lang=" apps/break_the_barriers/frontend --include=*.tsx --include=*.ts --include=*.jsx -l`
Mở file chứa toggle "Original/Translated" và iframe preview để hiểu cách build URL trang (`pages/{n}?lang=...&raw=true`) và URL PDF (`/api/docs/{id}/pdf?page={n}`).

- [ ] **Step 2: Đổi toggle 2 nút → 3 nút Gốc / HTML / Dịch.**
- `Gốc` → đặt `src` iframe = `${API}/api/docs/${id}/pdf?page=${n}` (nhúng PDF trang).
- `HTML` → iframe `pages/${n}?lang=en&raw=true` (như "Original" cũ).
- `Dịch` → iframe `pages/${n}?lang=vi&raw=true` (như "Translated" cũ).
Giữ nguyên cơ chế scale/zoom hiện có cho HTML/Dịch; với Gốc dùng PDF viewer mặc định của trình duyệt.

- [ ] **Step 3: Thêm nút "Làm sạch nền AI".**
- Lấy `page_class`/`cover` từ JSON non-raw `GET pages/{n}` (đã trả 2 field này từ #0).
- Hiện nút chỉ khi `(page_class === "regenerable" && (cover === "front" || cover === "back"))` (= clean-photo).
- Bấm → `POST /api/docs/${id}/pages/${n}/clean-bg` → khi 200, reload iframe tab hiện tại (cache-bust query `?t=${Date.now()}`).
- Hiện trạng thái đang chạy/lỗi tối thiểu (text "Đang làm sạch..." / "Lỗi").

- [ ] **Step 4: Verify thủ công.**
Mở `http://localhost:3000/books/2024-wttc-introduction-to-ai/preview`. Trang 1 (bìa): thấy 3 nút + nút "Làm sạch nền AI". Tab Gốc hiển thị PDF trang gốc. Bấm làm sạch → đợi → tab Dịch/HTML hiển thị bìa KHÔNG còn chữ tiếng Anh nung sẵn. Báo lại quan sát.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/frontend
git commit -m "feat(phase2): preview 3-state toggle (Gốc/HTML/Dịch) + clean-bg button"
```

---

### Task 5: Verify thật endpoint với Gemini (manual, có tốn AI)

**Files:** không.

- [ ] **Step 1: Xác nhận model ảnh khả dụng với key thật.**
Run (tốn 1 lần gọi AI):
```bash
cd apps/break_the_barriers/backend && PYTHONPATH=/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers .venv/bin/python -c "
import os
from backend.app.services.image_cleaner import clean_page_background
src='data/extracted_html/2024-wttc-introduction-to-ai/2024-wttc-introduction-to-ai-1.png'
ok = clean_page_background(src, '/tmp/cover.clean.png')
print('cleaned ok:', ok, '| exists:', os.path.exists('/tmp/cover.clean.png'))
"
```
Expected: `cleaned ok: True`. Nếu `False` → model ID sai/không có quyền: đặt `GEMINI_IMAGE_MODEL` sang ID đúng (vd `gemini-3-pro-image` hoặc model image hiện hành mà key có quyền) rồi chạy lại. Báo lại ID model hoạt động.

- [ ] **Step 2: Mở `/tmp/cover.clean.png`** xác nhận chữ tiếng Anh đã biến mất, ảnh giữ nguyên. Báo quan sát (gửi file nếu cần).

---

## Self-Review

**Spec coverage:**
- A1 `image_cleaner` (Gemini, client tiêm, fallback False) → Task 1. ✓
- A2 endpoint clean-bg (gate clean-photo→400, cache, set clean_image, không đổi image) → Task 3. ✓
- A3 renderer ưu tiên clean_image → Task 2. ✓
- A4 nút frontend tối thiểu → Task 4. ✓
- B (3 trạng thái: Gốc nhúng PDF, HTML/Dịch dùng lang) → Task 4 (frontend, không backend mới). ✓
- Kiểm thử: image_cleaner (mock), endpoint (monkeypatch + gating + cache), renderer clean_image → Task 1/2/3. ✓
- Verify thật Gemini + chốt model ID → Task 5. ✓
- Ngoài phạm vi (revert/regenerate/#3, TOC, PDF-embed nâng cao, không đổi schema/extraction) → tôn trọng. ✓

**Placeholder scan:** không TBD/TODO; mọi step có code/lệnh. Model ID là env-default có nhánh xử lý nếu sai (Task 5), không phải placeholder. ✓

**Type consistency:**
- `clean_page_background(src_path, out_path, *, client=None, model=None) -> bool` — Task 1, gọi ở Task 3 qua `image_cleaner.clean_page_background(src, clean_path)` và test monkeypatch cùng tên. ✓
- `background["clean_image"]` (key trong dict `background`) — set ở Task 3, đọc ở Task 2 (`bgd.get("clean_image")`), đọc ở frontend Task 4. Nhất quán. ✓
- `resolve_background_policy(page_class, cover)` (#0/Pha1) — dùng ở Task 3 để gate. ✓
- Endpoint trả `{"status", "clean_image"}` — test Task 3 assert `clean_image`. ✓
