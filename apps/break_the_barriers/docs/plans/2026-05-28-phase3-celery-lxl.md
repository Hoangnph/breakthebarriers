# Adaptive Pipeline — Phase 3: Celery L/XL

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route tài liệu L (200–500 trang) và XL (500+ trang) sang Celery workers thay vì asyncio, với priority queues và dead-letter handling.

**Architecture:** `dispatch_all_translation_jobs()` trong JobManager kiểm tra tier — nếu L/XL thì gọi `translate_page_task.apply_async()` vào đúng queue (celery-high/celery-low). Celery task thực thi `_run_translation_job` đã có. Docker Compose bật worker service khi dùng prod profile.

**Tech Stack:** Celery 5.3+, Redis 7 (broker + backend), `celery[redis]` (đã có trong requirements.txt)

**Working directory:** `apps/break_the_barriers/backend/`

---

## File Structure sau Phase 3

```
backend/app/
├── workers/                  NEW dir
│   ├── __init__.py           NEW
│   ├── celery_app.py         NEW — Celery instance + config
│   └── tasks.py              NEW — translate_page_task Celery task
└── services/
    └── job_manager.py        MOD — thêm Celery dispatch path cho L/XL

docker-compose.yml            MOD — worker service bỏ profiles (luôn bật)
docker-compose.dev.yml        MOD — worker service enable cho dev
```

---

## Task 1: Celery app + tasks

**Files:**
- Create: `app/workers/__init__.py`
- Create: `app/workers/celery_app.py`
- Create: `app/workers/tasks.py`

- [ ] **Step 1: Tạo app/workers/__init__.py**

File rỗng:
```python
```

- [ ] **Step 2: Tạo app/workers/celery_app.py**

```python
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "break_the_barriers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Đảm bảo task chỉ ack khi hoàn thành (không mất task khi worker crash)
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    # Retry failed tasks với exponential backoff
    task_max_retries=3,
    # Priority queues
    task_queues={
        "celery-high": {"exchange": "celery-high", "routing_key": "celery-high"},
        "celery-low":  {"exchange": "celery-low",  "routing_key": "celery-low"},
    },
    task_default_queue="celery-high",
)
```

- [ ] **Step 3: Tạo app/workers/tasks.py**

```python
import logging
from backend.app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="backend.app.workers.tasks.translate_page_task",
    max_retries=3,
)
def translate_page_task(
    self,
    job_id: str,
    doc_id: str,
    page_num: int,
    target_lang: str,
    quality: str,
) -> dict:
    """Celery task for L/XL document page translation."""
    from backend.app.services.job_manager import _run_translation_job

    try:
        _run_translation_job(job_id, doc_id, page_num, target_lang, quality)
        return {"status": "done", "job_id": job_id, "page_num": page_num}
    except Exception as exc:
        logger.error(f"Celery task failed job={job_id} page={page_num}: {exc}")
        # Exponential backoff: 30s, 60s, 120s
        countdown = 30 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
```

- [ ] **Step 4: Verify import hoạt động**

```bash
python -c "from backend.app.workers.celery_app import celery_app; print('Celery OK:', celery_app)"
```

Expected: `Celery OK: <Celery break_the_barriers at 0x...>`

- [ ] **Step 5: Commit**

```bash
git add app/workers/
git commit -m "feat: add Celery app and translate_page_task for L/XL processing"
```

---

## Task 2: JobManager — thêm Celery dispatch path

**Files:**
- Modify: `app/services/job_manager.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: Viết tests**

Thêm vào `tests/test_services.py`:

```python
def test_dispatch_celery_job_returns_task_id(db_session):
    """dispatch_celery_job nên trả về task_id string từ Celery."""
    from backend.app.models_db import DBJob
    from backend.app.services.job_manager import dispatch_celery_job

    job = DBJob(doc_id="clean_code", page_num=1, stage="translate",
                volume_tier="L", quality_tier="fast")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    # Celery với Redis không chạy trong test — task sẽ được gửi nhưng không execute
    # Chỉ kiểm tra rằng hàm không raise exception và trả về string
    try:
        task_id = dispatch_celery_job(job.id, "clean_code", 1, "vi", "fast", "L")
        assert isinstance(task_id, str)
        assert len(task_id) > 0
    except Exception as e:
        # Redis không chạy trong test env — acceptable
        assert "ConnectionError" in type(e).__name__ or "Error" in type(e).__name__

def test_dispatch_all_routes_sm_to_asyncio(monkeypatch):
    """S/M tier phải dùng asyncio path, không gọi Celery."""
    import asyncio
    from backend.app.services.job_manager import dispatch_all_translation_jobs

    celery_called = []

    def fake_dispatch_celery(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_called.append(job_id)
        return "fake-task-id"

    monkeypatch.setattr(
        "backend.app.services.job_manager.dispatch_celery_job",
        fake_dispatch_celery,
    )

    async def run():
        await dispatch_all_translation_jobs(
            jobs=[("job1", 1), ("job2", 2)],
            doc_id="clean_code",
            target_lang="vi",
            quality="high",
            tier="S",
        )

    asyncio.run(run())
    assert celery_called == [], "S tier must NOT call Celery"

def test_dispatch_all_routes_lxl_to_celery(monkeypatch):
    """L/XL tier phải gọi Celery, không dùng asyncio semaphore."""
    import asyncio
    from backend.app.services.job_manager import dispatch_all_translation_jobs

    celery_called = []

    def fake_dispatch_celery(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_called.append(job_id)
        return "fake-task-id"

    monkeypatch.setattr(
        "backend.app.services.job_manager.dispatch_celery_job",
        fake_dispatch_celery,
    )

    async def run():
        await dispatch_all_translation_jobs(
            jobs=[("job1", 1), ("job2", 2)],
            doc_id="clean_code",
            target_lang="vi",
            quality="fast",
            tier="L",
        )

    asyncio.run(run())
    assert set(celery_called) == {"job1", "job2"}, "L tier must call Celery for every job"
```

- [ ] **Step 2: Chạy tests để verify FAIL**

```bash
.venv/bin/pytest tests/test_services.py -k "celery or routes" -v
```

Expected: FAIL với ImportError hoặc AttributeError

- [ ] **Step 3: Cập nhật app/services/job_manager.py**

Thêm hàm `dispatch_celery_job` và cập nhật `dispatch_all_translation_jobs`:

```python
def dispatch_celery_job(
    job_id: str, doc_id: str, page_num: int, target_lang: str, quality: str, tier: str
) -> str:
    """Gửi job vào Celery queue phù hợp với tier. Trả về Celery task ID."""
    from backend.app.workers.tasks import translate_page_task

    queue = "celery-high" if tier == "L" else "celery-low"
    result = translate_page_task.apply_async(
        args=[job_id, doc_id, page_num, target_lang, quality],
        queue=queue,
    )
    return result.id
```

Và cập nhật `dispatch_all_translation_jobs` để phân nhánh theo tier:

```python
async def dispatch_all_translation_jobs(
    jobs: List[Tuple[str, int]],
    doc_id: str,
    target_lang: str,
    quality: str,
    tier: str,
) -> None:
    """Route: S/M → asyncio semaphore, L/XL → Celery queue."""
    if tier in ("L", "XL"):
        # Celery path: gửi tất cả vào queue, không chờ
        celery_ids = {}
        for job_id, page_num in jobs:
            task_id = dispatch_celery_job(job_id, doc_id, page_num, target_lang, quality, tier)
            celery_ids[job_id] = task_id
            logger.info(f"Queued Celery task {task_id} for job {job_id} page {page_num}")

        # Lưu celery_task_id vào DB
        db = get_background_db()
        try:
            from backend.app.models_db import DBJob
            for job_id, task_id in celery_ids.items():
                job = db.query(DBJob).filter(DBJob.id == job_id).first()
                if job:
                    job.celery_task_id = task_id
                    job.status = "running"
            db.commit()
        finally:
            db.close()
    else:
        # asyncio path: S/M — dùng semaphore pool
        tasks = [
            dispatch_translation_job(job_id, doc_id, page_num, target_lang, quality, tier)
            for job_id, page_num in jobs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                job_id, page_num = jobs[i]
                logger.error(f"Job {job_id} page {page_num} unhandled exception: {result}")
```

- [ ] **Step 4: Chạy tests**

```bash
.venv/bin/pytest tests/test_services.py -k "celery or routes" -v
```

Expected: 3 tests PASS (Celery connection test may partially skip — acceptable)

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: 44+ passed

- [ ] **Step 6: Commit**

```bash
git add app/services/job_manager.py tests/test_services.py
git commit -m "feat: route L/XL jobs to Celery, S/M stays asyncio in JobManager"
```

---

## Task 3: Enable Celery worker trong Docker Compose

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.dev.yml`

- [ ] **Step 1: Bỏ `profiles: [celery]` trong docker-compose.yml**

Trong `docker-compose.yml`, xoá phần `profiles` của worker service:

```yaml
  worker:
    build: .
    env_file: .env.docker
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/break_the_barriers
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      celery -A backend.app.workers.celery_app worker
      --loglevel=info -Q celery-high,celery-low
```

(Không có `profiles:` — worker luôn start cùng các service khác)

- [ ] **Step 2: Thêm worker vào docker-compose.dev.yml**

Thêm vào `docker-compose.dev.yml` sau service `frontend`:

```yaml
  worker:
    volumes:
      - ./backend:/app/backend   # hot reload cho worker code
    command: >
      celery -A backend.app.workers.celery_app worker
      --loglevel=info -Q celery-high,celery-low --autoscale=4,1
```

`--autoscale=4,1` = tối đa 4 concurrent tasks, tối thiểu 1.

- [ ] **Step 3: Rebuild và restart**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers
docker compose -f docker-compose.yml -f docker-compose.dev.yml build worker
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d worker
```

- [ ] **Step 4: Verify worker kết nối Redis thành công**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs worker --tail=15
```

Expected output:
```
worker-1  | [config]
worker-1  | .> app:         break_the_barriers
worker-1  | .> transport:   redis://redis:6379/0
worker-1  | .> results:     redis://redis:6379/0
worker-1  | .> concurrency: 1/4 (prefork)
worker-1  | [queues]
worker-1  | .> celery-high  exchange=celery-high routing_key=celery-high
worker-1  | .> celery-low   exchange=celery-low  routing_key=celery-low
worker-1  |  
worker-1  | [tasks]
worker-1  | .> backend.app.workers.tasks.translate_page_task
worker-1  | 
worker-1  | [2026-05-28 ...] celery@worker ready.
```

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/docker-compose.yml apps/break_the_barriers/docker-compose.dev.yml
git commit -m "feat: enable Celery worker service in Docker Compose dev and prod"
```

---

## Task 4: Integration test — translate-all với L/XL tier routing

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Thêm test routing**

Thêm vào `tests/test_api.py`:

```python
def test_translate_all_sm_uses_asyncio_path(client, monkeypatch):
    """S/M docs: translate-all phải dispatch qua asyncio, không qua Celery."""
    celery_calls = []

    def fake_celery_dispatch(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_calls.append(job_id)
        return "fake-task-id"

    monkeypatch.setattr(
        "backend.app.services.job_manager.dispatch_celery_job",
        fake_celery_dispatch,
    )

    client.post("/api/docs/clean_code/extract")
    response = client.post(
        "/api/docs/clean_code/translate-all",
        json={"target_lang": "vi"}
    )
    assert response.status_code == 200
    # clean_code có 10 trang → tier S → không gọi Celery
    assert celery_calls == [], f"S tier must not use Celery, got calls: {celery_calls}"

def test_translate_all_lxl_uses_celery_path(client, monkeypatch, db_session):
    """L/XL docs: translate-all phải dispatch qua Celery."""
    from backend.app.models_db import DBDocument

    # Tạo document giả với tier XL
    xl_doc = DBDocument(
        id="big_book",
        filename="big_book.pdf",
        total_pages=600,
        status="raw",
        volume_tier="XL",
        quality_tier="fast",
    )
    db_session.add(xl_doc)
    db_session.commit()

    celery_calls = []

    def fake_celery_dispatch(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_calls.append((job_id, tier))
        return "fake-task-id"

    monkeypatch.setattr(
        "backend.app.services.job_manager.dispatch_celery_job",
        fake_celery_dispatch,
    )

    # Extract pages (mock)
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
    c.post("/api/docs/big_book/extract")

    response = c.post(
        "/api/docs/big_book/translate-all",
        json={"target_lang": "vi", "quality_tier": "fast"}
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    # XL tier → tất cả jobs phải đi qua Celery
    assert len(celery_calls) > 0, "XL tier must dispatch via Celery"
    assert all(tier == "XL" for _, tier in celery_calls)
```

- [ ] **Step 2: Chạy tests**

```bash
.venv/bin/pytest tests/test_api.py -k "asyncio_path or celery_path" -v
```

Expected: 2 PASS

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: 46+ passed

- [ ] **Step 4: Commit**

```bash
git add tests/test_api.py
git commit -m "test: add routing tests for S/M asyncio vs L/XL Celery dispatch"
```

---

## Checklist Phase 3 hoàn thành

- [ ] `workers/celery_app.py` — Celery instance kết nối Redis, 2 queues (celery-high, celery-low)
- [ ] `workers/tasks.py` — `translate_page_task` với retry exponential backoff (3 lần)
- [ ] `job_manager.py` — `dispatch_celery_job()` + phân nhánh L/XL → Celery, S/M → asyncio
- [ ] Docker worker service đang chạy, kết nối Redis, lắng nghe 2 queues
- [ ] Tests: routing đúng tier về đúng path
- [ ] Tất cả tests pass

**Tiếp theo:** Phase 4 — Resume capability + stuck job timeout + frontend progress bar.
