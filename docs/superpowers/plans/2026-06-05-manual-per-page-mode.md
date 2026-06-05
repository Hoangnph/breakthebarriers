# Manual Per-Page Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Panel per-page cho người dùng tự: ép kiểu nền (override classifier), làm sạch/revert nền, dịch lại trang, và click thẳng vào chữ để sửa bản dịch.

**Architecture:** Thêm `effective_policy(page_class, cover, override)` (override thắng auto), lưu override ở `model_json.background.policy_override`; renderer + gating clean-bg dùng nó. Thêm endpoint `policy` (set/clear override) + `clean-bg/revert` (bỏ clean_image). Renderer gắn `data-span` + script click→postMessage cho click-to-edit. Frontend panel gom tất cả + listener `btb-edit` → `PUT translations/{span_id}`.

**Tech Stack:** Python 3, FastAPI, pytest; Next.js. Backend `apps/break_the_barriers/backend`, test `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-05-manual-per-page-mode-design.md`

## File Structure

- `app/services/background_policy.py` — thêm `effective_policy`.
- `app/services/text_layer_renderer.py` — dùng `effective_policy`; `data-span`; edit script.
- `app/models.py` — thêm `PagePolicyRequest`.
- `app/routers/documents.py` — endpoint `policy`, `clean-bg/revert`; gating dùng effective; metadata thêm `policy_override`/`has_clean_image`.
- Frontend `apps/break_the_barriers/frontend` — panel "Tùy chỉnh trang".
- Tests: `tests/test_effective_policy.py` (mới); bổ sung `tests/test_text_layer_renderer.py`, `tests/test_preview_pagemodel.py`.

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root. Nhánh `feat/manual-per-page` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

**Ngữ cảnh tái dùng (đã có):**
- `POST /api/docs/{id}/translate` body `{page_num, target_lang="vi", quality_tier="high", use_v2=True}` (re-translate trang).
- `PUT /api/docs/{id}/translations/{span_id}` body `{translated_text}` (sửa span).
- `POST /api/docs/{id}/pages/{n}/clean-bg?method=full|inpaint&force=` (làm sạch).
- `render_text_layer`: dòng `policy = resolve_background_policy(model.page_class, model.cover)`; div `<div class="tl-text" data-fit="1" style=...>{text}</div>`; script blob có listener `btb-zoom`.

---

### Task 1: `effective_policy` (override thắng auto)

**Files:**
- Modify: `app/services/background_policy.py`
- Test: `tests/test_effective_policy.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_effective_policy.py`:

```python
from backend.app.services.background_policy import effective_policy


def test_valid_override_wins():
    # preserve+front auto = clean-photo; override base-color thắng.
    assert effective_policy("preserve", "front", "base-color") == "base-color"
    assert effective_policy("text", "none", "keep-raster") == "keep-raster"
    assert effective_policy("regenerable", "none", "clean-photo") == "clean-photo"


def test_none_override_uses_auto():
    assert effective_policy("preserve", "front", None) == "clean-photo"   # auto (cover wins)
    assert effective_policy("text", "none", None) == "base-color"


def test_invalid_override_uses_auto():
    assert effective_policy("preserve", "none", "garbage") == "keep-raster"
    assert effective_policy("text", "none", "") == "base-color"
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_effective_policy.py -v` → ImportError.

- [ ] **Step 3: Cài đặt.** Thêm vào cuối `app/services/background_policy.py`:

```python
_VALID_POLICIES = ("base-color", "keep-raster", "clean-photo")


def effective_policy(page_class: str, cover: str, override) -> str:
    """A valid manual override wins; otherwise fall back to the auto policy."""
    if override in _VALID_POLICIES:
        return override
    return resolve_background_policy(page_class, cover)
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_effective_policy.py -v` → 3 passed.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/background_policy.py \
        apps/break_the_barriers/backend/tests/test_effective_policy.py
git commit -m "feat(manual): effective_policy (override wins over auto)"
```

---

### Task 2: Renderer dùng override + `data-span` + edit script

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_renderer.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_text_layer_renderer.py`:

```python
def test_policy_override_forces_base_color_on_preserve():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#000", "image": "page-1.png", "policy_override": "base-color"},
        blocks=[Block(span_id="s1", role="body", bbox=[70, 480, 300, 14], text="",
                      font=FontSpec(11, 400, False, "#000", "left", "sans"))],
        figures=[], page_class="preserve", cover="none")
    html = render_text_layer(pm, {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' not in html          # override base-color drops raster


def test_blocks_carry_data_span_and_edit_script():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[Block(span_id="s1", role="body", bbox=[72, 40, 200, 24], text="",
                      font=FontSpec(11, 400, False, "#000", "left", "sans"))],
        figures=[], page_class="text", cover="none")
    html = render_text_layer(pm, {"s1": "Xin chào"}, image_url_base="http://api/assets")
    assert 'data-span="s1"' in html             # block tagged with its span id
    assert "btb-edit" in html                   # click-to-edit handler present
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_text_layer_renderer.py -k "override_forces or data_span" -v` → FAIL.

- [ ] **Step 3: Cài đặt.** Trong `app/services/text_layer_renderer.py`:

(a) Đổi import: dòng `from backend.app.services.background_policy import resolve_background_policy` thành:
```python
from backend.app.services.background_policy import resolve_background_policy, effective_policy
```

(b) Đổi dòng tính policy (`policy = resolve_background_policy(model.page_class, model.cover)`) thành:
```python
    policy = effective_policy(model.page_class, model.cover,
                              (model.background or {}).get("policy_override"))
```

(c) Thêm `data-span` vào div `.tl-text`. Đổi dòng mở div:
```python
            f'<div class="tl-text" data-fit="1" '
```
thành:
```python
            f'<div class="tl-text" data-fit="1" '
            f'data-span="{html_lib.escape(blk.span_id, quote=True)}" '
```

(d) Thêm click handler vào script. Tìm dòng (trong blob script):
```python
        "if(document.readyState!=='loading')run();"
```
và chèn NGAY TRƯỚC nó:
```python
        "document.addEventListener('click',function(e){"
        "var el=e.target.closest&&e.target.closest('.tl-text');if(!el)return;"
        "window.parent.postMessage({type:'btb-edit',"
        "span_id:el.getAttribute('data-span'),text:el.textContent},'*');});/*btb-edit*/"
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_text_layer_renderer.py -v` → tất cả pass.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_text_layer_renderer.py
git commit -m "feat(manual): renderer respects policy_override + data-span + edit click"
```

---

### Task 3: Endpoint `POST /pages/{n}/policy`

**Files:**
- Modify: `app/models.py` (thêm `PagePolicyRequest`), `app/routers/documents.py`
- Test: `tests/test_preview_pagemodel.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_preview_pagemodel.py`:

```python
def test_set_page_policy_override(client, db_session):
    _seed_clean_photo(db_session)   # cp_doc page 1 (regenerable/front)
    r = client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "base-color"})
    assert r.status_code == 200
    assert r.json()["policy_override"] == "base-color"
    from backend.app.models_db import DBPage
    page = db_session.query(DBPage).filter(DBPage.document_id == "cp_doc",
                                           DBPage.page_num == 1).first()
    assert '"policy_override": "base-color"' in page.model_json or \
           '"policy_override":"base-color"' in page.model_json


def test_set_page_policy_auto_clears(client, db_session):
    _seed_clean_photo(db_session)
    client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "keep-raster"})
    r = client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "auto"})
    assert r.status_code == 200
    assert r.json()["policy_override"] is None


def test_set_page_policy_invalid_400(client, db_session):
    _seed_clean_photo(db_session)
    r = client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "nope"})
    assert r.status_code == 400
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_preview_pagemodel.py -k page_policy -v` → 404/422 (route/model chưa có).

- [ ] **Step 3a: Thêm model.** Trong `app/models.py`, sau `class TranslationRequest(BaseModel):` block, thêm:
```python
class PagePolicyRequest(BaseModel):
    value: str   # auto | base-color | keep-raster | clean-photo
```

- [ ] **Step 3b: Thêm endpoint.** Trong `app/routers/documents.py`, sau `clean_page_bg`, thêm:
```python
@router.post("/api/docs/{doc_id}/pages/{page_num}/policy")
def set_page_policy(doc_id: str, page_num: int,
                    payload: "PagePolicyRequest", db: Session = Depends(get_db)):
    from backend.app.services.page_model import PageModel
    page = db.query(DBPage).filter(DBPage.document_id == doc_id,
                                   DBPage.page_num == page_num).first()
    if not page or not page.model_json:
        raise HTTPException(status_code=404, detail="Page or model not found")
    pm = PageModel.from_json(page.model_json)
    val = payload.value
    if val == "auto":
        (pm.background or {}).pop("policy_override", None)
    elif val in ("base-color", "keep-raster", "clean-photo"):
        pm.background["policy_override"] = val
    else:
        raise HTTPException(status_code=400, detail="Invalid policy value")
    page.model_json = pm.to_json()
    db.commit()
    return {"policy_override": (pm.background or {}).get("policy_override")}
```
Thêm import `PagePolicyRequest` ở đầu `documents.py` (cùng nơi import models khác, vd `from backend.app.models import ...`); nếu file chưa import models, thêm `from backend.app.models import PagePolicyRequest` và bỏ dấu nháy quanh kiểu trong chữ ký (`payload: PagePolicyRequest`).

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_preview_pagemodel.py -v` → tất cả pass.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/models.py \
        apps/break_the_barriers/backend/app/routers/documents.py \
        apps/break_the_barriers/backend/tests/test_preview_pagemodel.py
git commit -m "feat(manual): POST pages/{n}/policy to set/clear background override"
```

---

### Task 4: Revert endpoint + gating effective + metadata

**Files:**
- Modify: `app/routers/documents.py`
- Test: `tests/test_preview_pagemodel.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_preview_pagemodel.py`:

```python
def test_clean_bg_revert_drops_clean_image(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="rv_doc", filename="r.pdf", total_pages=1, status="translated"))
    model = {"page_w": 595.0, "page_h": 842.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png",
                            "clean_image": "page-1.clean-inpaint.png"},
             "blocks": [], "figures": [], "page_class": "regenerable", "cover": "front"}
    db_session.add(DBPage(document_id="rv_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()
    r = client.post("/api/docs/rv_doc/pages/1/clean-bg/revert")
    assert r.status_code == 200 and r.json()["status"] == "reverted"
    page = db_session.query(DBPage).filter(DBPage.document_id == "rv_doc",
                                           DBPage.page_num == 1).first()
    assert "clean-inpaint" not in page.model_json


def test_metadata_returns_override_and_has_clean(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="md_doc", filename="m.pdf", total_pages=1, status="translated"))
    model = {"page_w": 1.0, "page_h": 1.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png",
                            "clean_image": "page-1.clean.png", "policy_override": "keep-raster"},
             "blocks": [], "figures": [], "page_class": "regenerable", "cover": "front"}
    db_session.add(DBPage(document_id="md_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()
    d = client.get("/api/docs/md_doc/pages/1").json()
    assert d["policy_override"] == "keep-raster"
    assert d["has_clean_image"] is True


def test_clean_bg_gating_respects_override(client, db_session, monkeypatch):
    # A `preserve` page with override clean-photo must be cleanable (not 400).
    from backend.app.models_db import DBDocument, DBPage
    import os, cv2, numpy as np
    db_session.add(DBDocument(id="ov_doc", filename="o.pdf", total_pages=1, status="translated"))
    model = {"page_w": 595.0, "page_h": 842.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png", "policy_override": "clean-photo"},
             "blocks": [], "figures": [], "page_class": "preserve", "cover": "none"}
    db_session.add(DBPage(document_id="ov_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()
    doc_dir = os.path.join(DATA_DIR, "extracted_html", "ov_doc")
    os.makedirs(doc_dir, exist_ok=True)
    cv2.imwrite(os.path.join(doc_dir, "page-1.png"), np.zeros((10, 10, 3), np.uint8))

    def _fake_inpaint(src, out, boxes, **kw):
        open(out, "wb").write(b"X"); return True
    monkeypatch.setattr(_image_cleaner_mod, "clean_page_background_inpaint", _fake_inpaint)

    r = client.post("/api/docs/ov_doc/pages/1/clean-bg?method=inpaint")
    assert r.status_code == 200
    for fn in ("page-1.png", "page-1.clean-inpaint.png"):
        p = os.path.join(doc_dir, fn)
        if os.path.exists(p):
            os.remove(p)
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_preview_pagemodel.py -k "revert or has_clean or gating_respects" -v` → FAIL.

- [ ] **Step 3a: Revert endpoint.** Trong `app/routers/documents.py`, sau `set_page_policy`, thêm:
```python
@router.post("/api/docs/{doc_id}/pages/{page_num}/clean-bg/revert")
def revert_clean_bg(doc_id: str, page_num: int, db: Session = Depends(get_db)):
    from backend.app.services.page_model import PageModel
    page = db.query(DBPage).filter(DBPage.document_id == doc_id,
                                   DBPage.page_num == page_num).first()
    if not page or not page.model_json:
        raise HTTPException(status_code=404, detail="Page or model not found")
    pm = PageModel.from_json(page.model_json)
    (pm.background or {}).pop("clean_image", None)
    page.model_json = pm.to_json()
    db.commit()
    return {"status": "reverted"}
```

- [ ] **Step 3b: Gating dùng effective policy.** Trong `clean_page_bg`, đổi dòng gating
`if resolve_background_policy(pm.page_class, pm.cover) != "clean-photo":` thành (và sửa import):
```python
    from backend.app.services.background_policy import effective_policy
    if effective_policy(pm.page_class, pm.cover,
                        (pm.background or {}).get("policy_override")) != "clean-photo":
        raise HTTPException(status_code=400, detail="Page is not a clean-photo page")
```
(Bỏ/để lại import `resolve_background_policy` cũ tuỳ còn dùng; thêm `effective_policy`.)

- [ ] **Step 3c: Metadata.** Trong `get_page_content`, ở khối non-raw cuối hàm (đang đặt `page_class, cover` từ `_pm`), bổ sung lấy thêm override + has_clean, và thêm vào dict trả về. Sửa khối:
```python
    page_class, cover = "text", "none"
    policy_override, has_clean_image = None, False
    if page.model_json:
        try:
            from backend.app.services.page_model import PageModel
            _pm = PageModel.from_json(page.model_json)
            page_class, cover = _pm.page_class, _pm.cover
            _bg = _pm.background or {}
            policy_override = _bg.get("policy_override")
            has_clean_image = bool(_bg.get("clean_image"))
        except Exception:
            pass
    return {"doc_id": doc_id, "page_num": page_num, "lang": lang, "html": html,
            "page_class": page_class, "cover": cover,
            "policy_override": policy_override, "has_clean_image": has_clean_image}
```

- [ ] **Step 4: Chạy + full suite.** `.venv/bin/pytest tests/test_preview_pagemodel.py -v` → pass. Rồi `.venv/bin/pytest tests/ -q --ignore=tests/test_extractor_box.py --ignore=tests/test_extractor_overhaul.py --ignore=tests/test_extractor_pagemodel.py` → pass. Báo số đếm.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/routers/documents.py \
        apps/break_the_barriers/backend/tests/test_preview_pagemodel.py
git commit -m "feat(manual): clean-bg revert + effective-policy gating + metadata fields"
```

---

### Task 5: Frontend — panel "Tùy chỉnh trang"

**Files:**
- Modify: preview component trong `apps/break_the_barriers/frontend`.

Manual, không TDD. ĐỌC component trước (đã có toggle Gốc/HTML/Dịch + nút Làm sạch từ các pha trước).

- [ ] **Step 1:** Mở preview component. Xác định nơi đặt header/nút và cách build URL/fetch metadata. Báo lại cấu trúc.

- [ ] **Step 2: Panel.** Thêm khối "Tùy chỉnh trang {n}" (dùng `pageMeta` đã fetch — giờ có thêm `policy_override`, `has_clean_image`):
  - **Nền** (radio): Auto / Trắng(base-color) / Giữ ảnh(keep-raster) / Làm sạch(clean-photo) → `POST /api/docs/${id}/pages/${n}/policy` body `{value}` → reload tab (cache-bust). Chọn hiện tại = `pageMeta.policy_override ?? "auto"`.
  - **Làm sạch**: giữ 2 nút Full/Inpaint (đã có) + nút **Revert** (`POST .../clean-bg/revert`) hiện khi `pageMeta.has_clean_image`. Hiện nhóm này khi effective policy = clean-photo (tức `policy_override === "clean-photo"` HOẶC (`policy_override == null` và cover front/back)).
  - **Dịch lại trang**: nút → `POST /api/docs/${id}/translate` body `{page_num: n, target_lang: "vi", quality_tier: "high", use_v2: true}`; hiện trạng thái.

- [ ] **Step 3: Click-to-edit.** Thêm toggle "Bật sửa chữ". Khi bật, đăng ký `window.addEventListener("message", ...)` lọc `e.data.type === "btb-edit"` → mở ô nhập điền sẵn `e.data.text` → khi lưu `PUT /api/docs/${id}/translations/${e.data.span_id}` body `{translated_text}` → reload tab. Khi tắt, gỡ listener.

- [ ] **Step 4: Build check** — `cd apps/break_the_barriers/frontend && npx tsc --noEmit` → không lỗi.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/frontend
git commit -m "feat(manual): per-page panel (policy override / clean+revert / re-translate / edit)"
```

---

### Task 6: Verify thật (manual — controller)

**Files:** không.

- [ ] **Step 1:** Controller chạy live trên `2024-wttc-introduction-to-ai`:
  - `POST policy {value:"base-color"}` cho 1 trang preserve → GET render xác nhận hết raster.
  - `POST policy {value:"auto"}` → trở lại.
  - `POST clean-bg/revert` sau khi có clean_image → render về raster gốc.
  - `GET pages/{n}` xác nhận `policy_override` + `has_clean_image`.
- [ ] **Step 2:** Báo kết quả; nhắc người dùng kiểm panel + click-to-edit trên trình duyệt.

---

## Self-Review

**Spec coverage:**
- A effective_policy + override storage + renderer/gating dùng nó + policy endpoint → Task 1, 2, 3, 4. ✓
- B revert endpoint (+ regenerate = force sẵn có) → Task 4. ✓
- C click-to-edit (data-span + script + frontend listener + PUT span) → Task 2 (render), Task 5 (frontend). ✓
- D re-translate (tái dùng /translate) → Task 5. ✓
- E panel frontend → Task 5. ✓
- Metadata thêm policy_override/has_clean_image → Task 4. ✓
- Kiểm thử: effective_policy, render override+data-span+edit, policy endpoint, revert, gating, metadata → Task 1–4. ✓
- Ngoài phạm vi (batch, re-extract, undo history) → tôn trọng. ✓

**Placeholder scan:** không TBD/TODO; mọi step có code/lệnh. ✓

**Type consistency:**
- `effective_policy(page_class, cover, override) -> str` — Task 1; dùng ở renderer (Task 2) + gating (Task 4). ✓
- `background["policy_override"]` (None|base-color|keep-raster|clean-photo) — set Task 3, đọc Task 2/4, metadata Task 4, frontend Task 5. ✓
- `background["clean_image"]` — revert pop ở Task 4; metadata `has_clean_image` từ nó. ✓
- `PagePolicyRequest{value:str}` — Task 3 model, dùng endpoint Task 3. ✓
- Endpoint `policy` trả `{policy_override}`; `revert` trả `{status:"reverted"}`; metadata trả `{..., policy_override, has_clean_image}` — khớp test. ✓
- `data-span="{span_id}"` + `btb-edit` postMessage `{type, span_id, text}` — Task 2 phát, Task 5 nghe → `PUT translations/{span_id}{translated_text}`. ✓
