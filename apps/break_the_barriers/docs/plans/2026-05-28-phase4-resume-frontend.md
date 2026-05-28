# Adaptive Pipeline — Phase 4: Resume + Frontend Progress

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm Resume capability cho tài liệu bị gián đoạn, cập nhật frontend để dùng translate-all với SSE progress bar, fix API_BASE port.

**Architecture:** Resume endpoint kiểm tra stuck jobs (>30 min), reset page status phù hợp, rồi re-dispatch jobs. Frontend thay vòng lặp page-by-page bằng 1 lần gọi translate-all và hiển thị SSE progress real-time.

**Working directory:** `apps/break_the_barriers/backend/` cho backend, `apps/break_the_barriers/` cho frontend.

---

## File Structure sau Phase 4

```
backend/app/routers/
└── jobs.py           MOD — thêm POST /api/docs/{id}/resume

apps/break_the_barriers/
└── app.js            MOD — fix API_BASE, upgrade triggerTranslation, SSE progress bar, resume button
```

---

## Task 1: Resume endpoint

**Files:**
- Modify: `app/routers/jobs.py`

- [ ] **Step 1: Viết tests cho resume endpoint**

Thêm vào `tests/test_api.py`:

```python
def test_resume_document_not_found(client):
    response = client.post("/api/docs/nonexistent/resume")
    assert response.status_code == 404

def test_resume_document_nothing_to_do(client):
    """Document có status compiled → resume trả về 0 pages re-queued."""
    client.post("/api/docs/clean_code/extract")
    # Không translate/compile — chỉ test endpoint trả về OK
    response = client.post("/api/docs/clean_code/resume")
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "clean_code"
    assert "queued" in data
    assert "status" in data

def test_resume_retranslates_extracted_pages(client, db_session):
    """Pages với status 'extracted' phải được re-queue translate."""
    from backend.app.models_db import DBPage
    from backend.app.database import get_db
    from backend.app.main import app
    from fastapi.testclient import TestClient

    def override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    c = TestClient(app)

    # Extract: creates pages with status 'raw' → 'extracted' after extract
    c.post("/api/docs/clean_code/extract")

    # Manually reset page 1 to 'extracted' to simulate interrupted translation
    page = db_session.query(DBPage).filter(
        DBPage.document_id == "clean_code", DBPage.page_num == 1
    ).first()
    page.status = "extracted"
    db_session.commit()

    resp = c.post("/api/docs/clean_code/resume")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] > 0

def test_resume_marks_stuck_jobs_failed(client, db_session):
    """Jobs running > 30 min phải bị đánh dấu failed khi resume."""
    from backend.app.models_db import DBJob
    from datetime import datetime, timezone, timedelta
    from backend.app.database import get_db
    from backend.app.main import app
    from fastapi.testclient import TestClient

    # Create a "stuck" job (started 45 min ago, still running)
    stuck_job = DBJob(
        doc_id="clean_code",
        page_num=1,
        stage="translate",
        status="running",
        volume_tier="S",
        quality_tier="high",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    )
    db_session.add(stuck_job)
    db_session.commit()
    db_session.refresh(stuck_job)
    job_id = stuck_job.id

    def override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    c = TestClient(app)
    c.post("/api/docs/clean_code/resume")
    app.dependency_overrides.clear()

    db_session.expire_all()
    updated = db_session.query(DBJob).filter(DBJob.id == job_id).first()
    assert updated.status == "failed"
    assert "timeout" in (updated.error_msg or "").lower()
```

- [ ] **Step 2: Chạy tests để verify FAIL**

```bash
.venv/bin/pytest tests/test_api.py -k "resume" -v
```
Expected: 4 FAIL (endpoint không tồn tại)

- [ ] **Step 3: Thêm resume endpoint vào app/routers/jobs.py**

Thêm imports cần thiết ở đầu `jobs.py`:
```python
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from backend.app.models_db import DBDocument, DBPage, DBJob, DBTranslation
```

Thêm endpoint vào cuối file `app/routers/jobs.py`:

```python
STUCK_JOB_TIMEOUT_MINUTES = 30


@router.post("/api/docs/{doc_id}/resume")
async def resume_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Resume processing for an interrupted document.

    Logic per page status:
      raw        → re-trigger full extraction
      extracted  → queue translate
      translating (stuck) → reset to extracted, queue translate
      failed     → queue translate (retry)
      translated → queue compile
      compiled   → skip
    """
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Mark stuck running jobs as failed
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_JOB_TIMEOUT_MINUTES)
    stuck_jobs = (
        db.query(DBJob)
        .filter(
            DBJob.doc_id == doc_id,
            DBJob.status == "running",
            DBJob.started_at != None,
            DBJob.started_at < stuck_cutoff,
        )
        .all()
    )
    for job in stuck_jobs:
        job.status = "failed"
        job.error_msg = f"Timeout: job ran > {STUCK_JOB_TIMEOUT_MINUTES} minutes without completing"
    if stuck_jobs:
        db.commit()
        logger.info(f"Marked {len(stuck_jobs)} stuck jobs as failed for doc {doc_id}")

    # 2. Reset stuck translating pages → extracted (so they get re-queued)
    stuck_pages = db.query(DBPage).filter(
        DBPage.document_id == doc_id, DBPage.status == "translating"
    ).all()
    for page in stuck_pages:
        page.status = "extracted"
    if stuck_pages:
        db.commit()

    # 3. Survey page statuses
    all_pages = db.query(DBPage).filter(DBPage.document_id == doc_id).all()

    raw_pages = [p for p in all_pages if p.status == "raw"]
    translate_pages = [p for p in all_pages if p.status in ("extracted", "failed")]
    compile_pages = [p for p in all_pages if p.status == "translated"]

    tier = doc.volume_tier or "M"
    quality = doc.quality_tier or "high"
    queued = 0

    # 4. Re-extract if pages are still raw
    if raw_pages:
        from backend.app.routers.extraction import run_background_extract
        background_tasks.add_task(run_background_extract, doc_id)
        queued += len(raw_pages)

    # 5. Re-translate extracted/failed pages via JobManager
    if translate_pages:
        from backend.app.models_db import DBJob as DBJobModel

        new_jobs = []
        for page in translate_pages:
            job = DBJobModel(
                doc_id=doc_id,
                page_num=page.page_num,
                stage="translate",
                status="pending",
                volume_tier=tier,
                quality_tier=quality,
            )
            db.add(job)
            new_jobs.append(job)
        db.commit()
        for job in new_jobs:
            db.refresh(job)

        jobs_data = [(job.id, job.page_num) for job in new_jobs]

        async def _dispatch():
            from backend.app.services.job_manager import dispatch_all_translation_jobs
            await dispatch_all_translation_jobs(jobs_data, doc_id, "vi", quality, tier)

        background_tasks.add_task(_dispatch)
        queued += len(translate_pages)

    # 6. Compile translated pages
    if compile_pages:
        from backend.app.routers.compilation import run_background_compile
        for page in compile_pages:
            background_tasks.add_task(run_background_compile, doc_id, page.page_num)
        queued += len(compile_pages)

    return {
        "status": "resumed" if queued > 0 else "nothing_to_do",
        "doc_id": doc_id,
        "queued": queued,
        "detail": {
            "raw_pages_re_extracted": len(raw_pages),
            "pages_re_translated": len(translate_pages),
            "pages_re_compiled": len(compile_pages),
            "stuck_jobs_reset": len(stuck_jobs),
        },
    }
```

- [ ] **Step 4: Chạy tests**

```bash
.venv/bin/pytest tests/test_api.py -k "resume" -v
```
Expected: 4 PASS

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```
Expected: 54 passed

- [ ] **Step 6: Commit**

```bash
git add app/routers/jobs.py tests/test_api.py
git commit -m "feat: add resume endpoint with stuck job timeout and page re-queueing"
```

---

## Task 2: Frontend — fix API_BASE + translate-all + SSE progress bar + resume button

**Files:**
- Modify: `app.js` (tại `apps/break_the_barriers/`)

> Chú ý: file này nằm ở `apps/break_the_barriers/app.js`, không phải trong `backend/`

- [ ] **Step 1: Fix API_BASE port**

Trong `app.js`, tìm dòng:
```javascript
const API_BASE = 'http://localhost:8005';
```

Sửa thành:
```javascript
const API_BASE = 'http://localhost:8000';
```

- [ ] **Step 2: Thêm SSE progress bar helper function**

Tìm vị trí sau dòng khai báo `let pollingInterval = null;` (khoảng dòng 19), thêm biến:
```javascript
let activeProgressESS = null;  // EventSource for SSE progress
```

Tìm hàm `window.triggerTranslation`, thêm hàm mới **TRƯỚC** nó:

```javascript
    // ---------------------------------------------------------
    // SSE Translation Progress Bar
    // ---------------------------------------------------------
    const showTranslationProgress = (docId) => {
        // Find or create progress container for this doc
        const card = document.querySelector(`[data-doc-id="${docId}"]`);
        if (!card) return;

        let progressBar = card.querySelector('.translation-progress');
        if (!progressBar) {
            progressBar = document.createElement('div');
            progressBar.className = 'translation-progress';
            progressBar.innerHTML = `
                <div class="tp-header">
                    <span class="tp-label">🤖 Đang dịch...</span>
                    <span class="tp-percent">0%</span>
                </div>
                <div class="tp-bar-track">
                    <div class="tp-bar-fill" style="width:0%"></div>
                </div>
                <div class="tp-detail">Khởi động pipeline dịch thuật...</div>
            `;
            progressBar.style.cssText = `
                margin-top: 10px;
                padding: 10px 12px;
                background: rgba(99,102,241,0.1);
                border: 1px solid rgba(99,102,241,0.25);
                border-radius: 8px;
                font-size: 12px;
            `;
            progressBar.querySelector('.tp-bar-track').style.cssText = `
                height: 6px; background: rgba(255,255,255,0.1);
                border-radius: 3px; margin: 6px 0;
            `;
            progressBar.querySelector('.tp-bar-fill').style.cssText = `
                height: 100%; background: linear-gradient(90deg, #6366f1, #a855f7);
                border-radius: 3px; transition: width 0.5s ease;
            `;
            card.appendChild(progressBar);
        }

        // Close any existing SSE
        if (activeProgressESS) activeProgressESS.close();

        activeProgressESS = new EventSource(`${API_BASE}/api/docs/${docId}/progress`);

        activeProgressESS.onmessage = async (e) => {
            try {
                const data = JSON.parse(e.data);
                const pct = data.percent || 0;
                const eta = data.eta_min > 0 ? ` · ETA ${data.eta_min} phút` : '';
                const done = data.compiled || 0;
                const total = data.total || 0;

                progressBar.querySelector('.tp-percent').textContent = `${pct}%`;
                progressBar.querySelector('.tp-bar-fill').style.width = `${pct}%`;
                progressBar.querySelector('.tp-detail').textContent =
                    `Trang ${done}/${total} đã hoàn thành${eta}`;

                if (data.status === 'completed' || pct >= 100) {
                    activeProgressESS.close();
                    progressBar.querySelector('.tp-label').textContent = '✅ Dịch hoàn tất!';
                    progressBar.querySelector('.tp-detail').textContent = `Tất cả ${total} trang đã được dịch.`;
                    setTimeout(() => {
                        progressBar.remove();
                        fetchDocuments();
                    }, 3000);
                }
            } catch (_) {}
        };

        activeProgressESS.onerror = () => {
            activeProgressESS.close();
            progressBar.remove();
            fetchDocuments();
        };
    };
```

- [ ] **Step 3: Thay thế triggerTranslation để dùng translate-all + SSE**

Tìm hàm `window.triggerTranslation = async (docId, totalPages = 1)` và thay toàn bộ bằng:

```javascript
    window.triggerTranslation = async (docId, totalPages = 1) => {
        try {
            showNotification('🤖 AI Pipeline', `Gửi ${totalPages} trang tới Adaptive Pipeline...`, 'info');

            const res = await fetch(`${API_BASE}/api/docs/${docId}/translate-all`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_lang: 'vi' }),
                mode: 'cors',
            });

            if (!res.ok) throw new Error('Không thể khởi chạy pipeline dịch thuật.');

            const data = await res.json();
            showNotification('Pipeline Bắt Đầu', `${data.total_pages} trang đang được xử lý (${data.volume_tier} tier)`, 'success');

            // Start SSE progress tracking
            showTranslationProgress(docId);
            await fetchDocuments();
        } catch (err) {
            showNotification('Lỗi', err.message, 'error');
        }
    };
```

- [ ] **Step 4: Thêm triggerResume function**

Ngay sau hàm `window.triggerTranslation`, thêm:

```javascript
    window.triggerResume = async (docId) => {
        try {
            showNotification('🔄 Resume', 'Đang phân tích và tiếp tục pipeline bị gián đoạn...', 'info');

            const res = await fetch(`${API_BASE}/api/docs/${docId}/resume`, {
                method: 'POST',
                mode: 'cors',
            });

            if (!res.ok) throw new Error('Không thể khởi động lại pipeline.');

            const data = await res.json();
            if (data.queued > 0) {
                showNotification('✅ Đã Resume', `Đã khởi động lại ${data.queued} tác vụ bị gián đoạn.`, 'success');
                showTranslationProgress(docId);
            } else {
                showNotification('ℹ️ Không có gì để Resume', 'Tài liệu này đã hoàn tất hoặc chưa bắt đầu.', 'info');
            }
            await fetchDocuments();
        } catch (err) {
            showNotification('Lỗi', err.message, 'error');
        }
    };
```

- [ ] **Step 5: Thêm nút Resume vào card document bị failed/interrupted**

Tìm trong hàm `fetchDocuments` (khoảng dòng 285) đoạn xử lý `doc.status === 'translating'`:

```javascript
} else if (doc.status === 'translating') {
```

Ngay sau đoạn đó, tìm nơi render các action buttons. Thêm nút Resume cho trường hợp `failed`:

Tìm đoạn check `doc.status === 'raw' || doc.status === 'failed'` (khoảng dòng 270-275):

```javascript
if (doc.status === 'raw' || doc.status === 'failed') {
    // ... nút extract hiện tại
```

Và sau khối này, tìm chỗ render button row, thêm điều kiện cho failed status:

Tìm vùng render nút trong `fetchDocuments`, cụ thể là đoạn render nút cho `doc.status === 'translating'` — thêm nút Resume vào đây:

```javascript
} else if (doc.status === 'translating') {
    actionsHtml = `
        <button onclick="triggerResume('${doc.id}')" class="doc-action-btn resume">
            🔄 Resume
        </button>`;
```

- [ ] **Step 6: Test thủ công trên browser**

```bash
# Từ thư mục break_the_barriers, verify API running
curl -s http://localhost:8000/ | python3 -m json.tool
```

Mở http://localhost:8001 trong browser, upload 1 PDF nhỏ, kiểm tra:
1. Upload thành công
2. Extract hoạt động
3. Nút "Dịch" gọi translate-all (xem Network tab → POST /api/docs/.../translate-all)
4. Progress bar xuất hiện khi dịch

- [ ] **Step 7: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/app.js
git commit -m "feat: fix API_BASE port, upgrade translate to translate-all with SSE progress bar, add resume button"
```

---

## Checklist Phase 4 hoàn thành

- [ ] `POST /api/docs/{id}/resume` endpoint hoạt động
- [ ] Stuck jobs (> 30 min) bị mark failed khi resume
- [ ] Translating pages bị reset → re-queued
- [ ] Frontend API_BASE trỏ đúng port 8000
- [ ] triggerTranslation dùng translate-all thay vì loop per page
- [ ] SSE progress bar hiển thị khi dịch đang chạy
- [ ] Resume button xuất hiện khi doc bị gián đoạn
- [ ] 54+ tests pass

**Phase 4 complete → Toàn bộ Adaptive Pipeline từ Phase 1-4 hoàn chỉnh.**
