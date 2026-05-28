# Adaptive Pipeline — Phase 2: asyncio S/M Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm khả năng dịch song song cho tài liệu S/M (≤200 trang) bằng asyncio Semaphore pools, với SSE real-time progress và endpoint translate-all.

**Architecture:** `translate-all` endpoint tạo `DBJob` records rồi dispatch async background task. Task dùng `asyncio.Semaphore` để giới hạn concurrency theo volume tier, chạy blocking translator trong `ThreadPoolExecutor`. SSE endpoint stream job progress từ DB mỗi giây.

**Tech Stack:** FastAPI BackgroundTasks, asyncio.Semaphore, asyncio.gather, ThreadPoolExecutor, StreamingResponse (SSE), SQLAlchemy

**Working directory cho mọi lệnh:** `apps/break_the_barriers/backend/`

**Prerequisites:** Phase 1 phải complete — `DBJob`, `VolumeDetector`, routers/ đã tồn tại.

---

## File Structure sau Phase 2

```
backend/app/
├── main.py                   MOD — thêm jobs router
├── models.py                 MOD — thêm TranslateAllRequest
├── routers/
│   ├── translation.py        MOD — thêm translate-all endpoint
│   └── jobs.py               NEW — GET /jobs/{id}, GET /docs/{id}/jobs, GET /docs/{id}/progress (SSE)
└── services/
    └── job_manager.py        NEW — asyncio Semaphore pools + ThreadPoolExecutor dispatch
```

---

## Task 1: TranslateAllRequest model + jobs router skeleton

**Files:**
- Modify: `app/models.py`
- Create: `app/routers/jobs.py`
- Modify: `app/main.py`

- [ ] **Step 1: Thêm TranslateAllRequest vào app/models.py**

Thêm vào cuối file `app/models.py`:

```python
class TranslateAllRequest(BaseModel):
    target_lang: str = "vi"
    quality_tier: Optional[str] = None  # None = dùng recommended từ volume tier
```

Thêm `Optional` vào import nếu chưa có:
```python
from typing import List, Dict, Optional
```

- [ ] **Step 2: Tạo app/routers/jobs.py với 2 endpoints cơ bản**

```python
import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.app.database import get_db, SessionLocal
from backend.app.models_db import DBDocument, DBPage, DBJob

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(DBJob).filter(DBJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "doc_id": job.doc_id,
        "page_num": job.page_num,
        "stage": job.stage,
        "status": job.status,
        "volume_tier": job.volume_tier,
        "quality_tier": job.quality_tier,
        "retries": job.retries,
        "error_msg": job.error_msg,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/api/docs/{doc_id}/jobs")
def list_document_jobs(
    doc_id: str,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    query = db.query(DBJob).filter(DBJob.doc_id == doc_id)
    if status:
        query = query.filter(DBJob.status == status)
    jobs = query.order_by(DBJob.created_at).all()
    return [
        {
            "id": j.id,
            "page_num": j.page_num,
            "stage": j.stage,
            "status": j.status,
            "quality_tier": j.quality_tier,
            "retries": j.retries,
            "error_msg": j.error_msg,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/api/docs/{doc_id}/progress")
async def progress_stream(doc_id: str):
    """SSE endpoint — stream translation progress cho 1 document."""

    async def event_generator():
        max_iterations = 300  # safety: tối đa 5 phút (300 × 1s)
        for _ in range(max_iterations):
            db = SessionLocal()
            try:
                doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
                if not doc:
                    yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
                    return

                total = db.query(DBPage).filter(DBPage.document_id == doc_id).count()
                compiled = db.query(DBPage).filter(
                    DBPage.document_id == doc_id, DBPage.status == "compiled"
                ).count()
                translated = db.query(DBPage).filter(
                    DBPage.document_id == doc_id, DBPage.status == "translated"
                ).count()
                failed = db.query(DBPage).filter(
                    DBPage.document_id == doc_id, DBPage.status == "failed"
                ).count()

                done = compiled + translated
                percent = int((done / total) * 100) if total > 0 else 0

                # Estimate remaining time: each page ~30s average
                remaining = total - done
                eta_min = max(0, int(remaining * 30 / 60))

                data = {
                    "total": total,
                    "compiled": compiled,
                    "translated": translated,
                    "failed": failed,
                    "percent": percent,
                    "eta_min": eta_min,
                    "status": "completed" if (done == total and total > 0) else "in_progress",
                }
                yield f"data: {json.dumps(data)}\n\n"

                if done == total and total > 0:
                    return
            finally:
                db.close()

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 3: Thêm jobs router vào app/main.py**

Trong `app/main.py`, thêm import:
```python
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs
```

Và thêm router include sau volume:
```python
app.include_router(jobs.router)
```

- [ ] **Step 4: Chạy test để verify không regression**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: 33 passed (không thêm test ở task này, chỉ verify không regression)

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/routers/jobs.py app/main.py
git commit -m "feat: add jobs router (GET /jobs/{id}, GET /docs/{id}/jobs, GET /docs/{id}/progress SSE)"
```

---

## Task 2: JobManager service

**Files:**
- Create: `app/services/job_manager.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: Viết tests cho JobManager**

Thêm vào `tests/test_services.py`:

```python
def test_job_manager_semaphore_tiers():
    from backend.app.services.job_manager import SEMAPHORE_LIMITS
    assert SEMAPHORE_LIMITS["S"] == 3
    assert SEMAPHORE_LIMITS["M"] == 8
    assert SEMAPHORE_LIMITS["L"] == 10
    assert SEMAPHORE_LIMITS["XL"] == 5

def test_run_translation_job_marks_done(db_session):
    """Test that _run_translation_job updates job status in DB."""
    import asyncio
    from backend.app.models_db import DBJob
    from backend.app.services.job_manager import _run_translation_job

    # Create a job record
    job = DBJob(
        doc_id="clean_code",
        page_num=1,
        stage="translate",
        volume_tier="S",
        quality_tier="high",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    job_id = job.id

    # Run the job (will use mock translator in pytest)
    # We need to extract first so the page exists
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.database import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.post("/api/docs/clean_code/extract")
    app.dependency_overrides.clear()

    # Run the job
    _run_translation_job(job_id, "clean_code", 1, "vi", "high")

    # Verify job status updated
    db_session.expire_all()
    updated_job = db_session.query(DBJob).filter(DBJob.id == job_id).first()
    assert updated_job.status in ("done", "failed")  # depends on whether extraction worked
```

- [ ] **Step 2: Chạy tests để verify FAIL**

```bash
.venv/bin/pytest tests/test_services.py -k "job_manager" -v
```

Expected: FAIL với ModuleNotFoundError

- [ ] **Step 3: Tạo app/services/job_manager.py**

```python
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List, Tuple

from backend.app.database import get_background_db
from backend.app.models_db import DBJob, DBPage

logger = logging.getLogger(__name__)

# Concurrency limits per volume tier
SEMAPHORE_LIMITS = {
    "S": 3,
    "M": 8,
    "L": 10,   # Phase 3 will route L/XL to Celery instead
    "XL": 5,
}

# Module-level semaphores — shared across all requests
_semaphores: dict = {}


def _get_semaphore(tier: str) -> asyncio.Semaphore:
    """Return (or lazily create) the semaphore for a given tier."""
    if tier not in _semaphores:
        limit = SEMAPHORE_LIMITS.get(tier, SEMAPHORE_LIMITS["M"])
        _semaphores[tier] = asyncio.Semaphore(limit)
    return _semaphores[tier]


def _run_translation_job(job_id: str, doc_id: str, page_num: int, target_lang: str, quality: str) -> None:
    """Synchronous function — safe to run in ThreadPoolExecutor. Creates its own DB session."""
    from backend.app.routers.translation import _perform_translation

    db = get_background_db()
    try:
        # Mark job as running
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if job:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

        _perform_translation(doc_id, page_num, target_lang, db, quality)

        # Mark job as done
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if job:
            job.status = "done"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

    except Exception as e:
        logger.error(f"Translation job {job_id} (doc={doc_id} page={page_num}) failed: {e}")
        try:
            job = db.query(DBJob).filter(DBJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_msg = str(e)[:500]
                job.retries += 1
                db.commit()
            # Also mark the page as failed
            page = db.query(DBPage).filter(
                DBPage.document_id == doc_id, DBPage.page_num == page_num
            ).first()
            if page:
                page.status = "failed"
                db.commit()
        except Exception as inner:
            logger.error(f"Failed to update job status after error: {inner}")
    finally:
        db.close()


async def dispatch_translation_job(
    job_id: str, doc_id: str, page_num: int, target_lang: str, quality: str, tier: str
) -> None:
    """Async wrapper — acquires semaphore then runs blocking job in thread pool."""
    semaphore = _get_semaphore(tier)
    async with semaphore:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _run_translation_job,
            job_id, doc_id, page_num, target_lang, quality,
        )


async def dispatch_all_translation_jobs(
    jobs: List[Tuple[str, int]],   # [(job_id, page_num), ...]
    doc_id: str,
    target_lang: str,
    quality: str,
    tier: str,
) -> None:
    """Launch all translation jobs concurrently, bounded by tier semaphore."""
    tasks = [
        dispatch_translation_job(job_id, doc_id, page_num, target_lang, quality, tier)
        for job_id, page_num in jobs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            job_id, page_num = jobs[i]
            logger.error(f"Job {job_id} page {page_num} raised unhandled exception: {result}")
```

- [ ] **Step 4: Chạy tests**

```bash
.venv/bin/pytest tests/test_services.py -k "job_manager" -v
```

Expected: `test_job_manager_semaphore_tiers` PASS (the integration test may vary)

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: 33+ passed

- [ ] **Step 6: Commit**

```bash
git add app/services/job_manager.py tests/test_services.py
git commit -m "feat: add JobManager with asyncio Semaphore pools and ThreadPoolExecutor dispatch"
```

---

## Task 3: translate-all endpoint

**Files:**
- Modify: `app/routers/translation.py`

- [ ] **Step 1: Viết test cho translate-all**

Thêm vào `tests/test_api.py`:

```python
def test_translate_all_creates_jobs(client):
    # Extract first so pages exist
    client.post("/api/docs/clean_code/extract")

    # Translate all pages
    response = client.post(
        "/api/docs/clean_code/translate-all",
        json={"target_lang": "vi", "quality_tier": "high"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["doc_id"] == "clean_code"
    assert data["total_pages"] == 10
    assert "job_ids" in data
    assert len(data["job_ids"]) == 10

def test_translate_all_doc_not_found(client):
    response = client.post(
        "/api/docs/nonexistent/translate-all",
        json={"target_lang": "vi"}
    )
    assert response.status_code == 404

def test_translate_all_jobs_visible_in_list(client):
    client.post("/api/docs/clean_code/extract")
    client.post("/api/docs/clean_code/translate-all", json={"target_lang": "vi"})

    # Jobs should appear in the jobs list
    response = client.get("/api/docs/clean_code/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) > 0
    assert all(j["stage"] == "translate" for j in jobs)
```

- [ ] **Step 2: Chạy test để verify FAIL**

```bash
.venv/bin/pytest tests/test_api.py -k "translate_all" -v
```

Expected: FAIL (endpoint chưa tồn tại)

- [ ] **Step 3: Thêm translate-all endpoint vào app/routers/translation.py**

Thêm imports ở đầu file (nếu chưa có):
```python
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from backend.app.models import TranslationRequest, TranslationItem, TranslationUpdate, TranslateAllRequest
from backend.app.models_db import DBDocument, DBPage, DBTranslation, DBJob
```

Thêm function và endpoint vào cuối file `app/routers/translation.py`:

```python
async def _dispatch_all_jobs_background(
    jobs_data: list,   # [(job_id, page_num), ...]
    doc_id: str,
    target_lang: str,
    quality: str,
    tier: str,
) -> None:
    """Async background task — dispatches all jobs via JobManager."""
    from backend.app.services.job_manager import dispatch_all_translation_jobs
    await dispatch_all_translation_jobs(jobs_data, doc_id, target_lang, quality, tier)


@router.post("/api/docs/{doc_id}/translate-all")
async def translate_all_pages(
    doc_id: str,
    payload: TranslateAllRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Only translate pages not yet compiled
    pages = (
        db.query(DBPage)
        .filter(DBPage.document_id == doc_id, DBPage.status != "compiled")
        .order_by(DBPage.page_num)
        .all()
    )
    if not pages:
        return {"status": "nothing_to_do", "doc_id": doc_id, "total_pages": 0, "job_ids": []}

    tier = doc.volume_tier or "M"
    quality = payload.quality_tier or doc.quality_tier or "high"

    # Create a DBJob record for every page
    created_jobs = []
    for page in pages:
        job = DBJob(
            doc_id=doc_id,
            page_num=page.page_num,
            stage="translate",
            status="pending",
            volume_tier=tier,
            quality_tier=quality,
        )
        db.add(job)
        created_jobs.append(job)
    db.commit()
    for job in created_jobs:
        db.refresh(job)

    jobs_data = [(job.id, job.page_num) for job in created_jobs]

    # Dispatch background task (async — FastAPI supports async BackgroundTasks)
    background_tasks.add_task(
        _dispatch_all_jobs_background,
        jobs_data,
        doc_id,
        payload.target_lang,
        quality,
        tier,
    )

    return {
        "status": "started",
        "doc_id": doc_id,
        "total_pages": len(created_jobs),
        "quality_tier": quality,
        "volume_tier": tier,
        "job_ids": [j.id for j in created_jobs],
    }
```

- [ ] **Step 4: Chạy translate-all tests**

```bash
.venv/bin/pytest tests/test_api.py -k "translate_all" -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: 36 passed

- [ ] **Step 6: Commit**

```bash
git add app/routers/translation.py tests/test_api.py
git commit -m "feat: add translate-all endpoint with async job dispatch via JobManager"
```

---

## Task 4: Tests cho jobs endpoints + SSE progress

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Thêm tests cho jobs endpoints**

Thêm vào `tests/test_api.py`:

```python
def test_get_job_status(client):
    # Setup: extract then translate-all to create jobs
    client.post("/api/docs/clean_code/extract")
    translate_resp = client.post(
        "/api/docs/clean_code/translate-all",
        json={"target_lang": "vi"}
    )
    job_ids = translate_resp.json()["job_ids"]
    assert len(job_ids) > 0

    # Get status of first job
    job_id = job_ids[0]
    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["doc_id"] == "clean_code"
    assert data["stage"] == "translate"
    assert "status" in data
    assert "volume_tier" in data
    assert "quality_tier" in data

def test_get_job_status_not_found(client):
    response = client.get("/api/jobs/nonexistent-job-id")
    assert response.status_code == 404

def test_list_document_jobs_empty(client):
    # No jobs created yet for clean_code (fresh test isolation)
    response = client.get("/api/docs/clean_code/jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_list_document_jobs_after_translate_all(client):
    client.post("/api/docs/clean_code/extract")
    client.post("/api/docs/clean_code/translate-all", json={"target_lang": "vi"})

    response = client.get("/api/docs/clean_code/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 10  # 10 pages
    for job in jobs:
        assert "id" in job
        assert "page_num" in job
        assert job["stage"] == "translate"

def test_list_document_jobs_filter_by_status(client):
    client.post("/api/docs/clean_code/extract")
    client.post("/api/docs/clean_code/translate-all", json={"target_lang": "vi"})

    # Filter by pending status (jobs just created)
    response = client.get("/api/docs/clean_code/jobs?status=pending")
    assert response.status_code == 200
    jobs = response.json()
    # All freshly created jobs should be pending (background task hasn't run yet in sync test)
    assert isinstance(jobs, list)

def test_progress_stream_returns_sse(client):
    client.post("/api/docs/clean_code/extract")

    # SSE endpoint should return 200 with correct content-type
    # Use stream=True to avoid blocking on the generator
    with client.stream("GET", "/api/docs/clean_code/progress") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        # Read first event
        first_line = next(response.iter_lines())
        assert first_line.startswith("data:")
        import json
        data = json.loads(first_line[5:].strip())  # strip "data:" prefix
        assert "total" in data
        assert "percent" in data
        assert "status" in data
```

- [ ] **Step 2: Chạy tests**

```bash
.venv/bin/pytest tests/test_api.py -k "job_status or document_jobs or progress_stream" -v
```

Expected: 6 tests PASS

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: 42 passed

- [ ] **Step 4: Commit**

```bash
git add tests/test_api.py
git commit -m "test: add jobs endpoints and SSE progress stream tests"
```

---

## Checklist Phase 2 hoàn thành

- [ ] `TranslateAllRequest` Pydantic model tồn tại trong models.py
- [ ] `routers/jobs.py` có: GET /api/jobs/{id}, GET /api/docs/{id}/jobs, GET /api/docs/{id}/progress (SSE)
- [ ] `services/job_manager.py` có: SEMAPHORE_LIMITS, _run_translation_job, dispatch_translation_job, dispatch_all_translation_jobs
- [ ] `routers/translation.py` có: POST /api/docs/{id}/translate-all
- [ ] translate-all tạo DBJob records trước khi dispatch
- [ ] JobManager dùng asyncio.Semaphore giới hạn theo tier (S=3, M=8, L=10, XL=5)
- [ ] SSE endpoint stream progress từ DB mỗi 1 giây
- [ ] Tất cả tests pass (42+)

**Tiếp theo:** Phase 3 — Celery + Redis cho L/XL documents.
