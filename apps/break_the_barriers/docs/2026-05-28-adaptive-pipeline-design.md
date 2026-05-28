# Adaptive Pipeline — Design Spec

> **For agentic workers:** Use `superpowers:writing-plans` to implement this spec task-by-task.

**Goal:** Nâng cấp pipeline PDF → HTML → Translated thành Hybrid Adaptive Pipeline hỗ trợ multi-user production, phân loại tài liệu theo volume và xử lý phù hợp với từng tier.

**Date:** 2026-05-28

---

## ① Kiến trúc tổng thể

Hybrid Adaptive Pipeline gồm 2 nhánh xử lý song song, được điều phối bởi **Volume Detector** sau bước Upload:

```
Upload PDF
    ↓
Volume Detector  →  VolumeProfile { tier, tokens, cost, quality, path }
    ↓                    ↓
S/M ≤200 trang       L/XL 200+ trang
asyncio Semaphore    Celery + Redis
SSE progress         Priority queues
PostgreSQL jobs      Dead-letter queue
    ↓                    ↓
      ← Shared modules →
   Quality Tier Engine · Cost Estimator
   translate-all endpoint · google.genai
   main.py → routers/ refactor
```

**Document status flow** (không đổi): `raw` → `extracted` → `translated` → `compiled`

---

## ② Volume Detector — module mới

**File:** `backend/app/services/volume_detector.py`

### Phân loại tier

| Tier | Trang | Concurrency | Processing path |
|------|-------|-------------|-----------------|
| S | < 50 | 3 asyncio workers | asyncio |
| M | 50–200 | 8 asyncio workers | asyncio |
| L | 200–500 | Celery priority-high | Celery + Redis |
| XL | 500+ | Celery priority-low | Celery + Redis |

### Output: VolumeProfile

```python
@dataclass
class VolumeProfile:
    tier: str                      # S / M / L / XL
    page_count: int
    estimated_spans: int           # page_count × avg_spans_per_page (≈ 40)
    estimated_tokens: int          # spans × avg_tokens_per_span × quality_multiplier
    estimated_cost_usd: float      # tokens × gemini_price_per_1M_tokens
    recommended_quality: str       # fast / balanced / high
    processing_path: str           # asyncio / celery
    estimated_duration_min: int    # thời gian ước tính
```

### Cost Estimator (tích hợp trong Volume Detector)

```
estimated_cost = page_count
               × avg_spans_per_page (≈ 40)
               × avg_tokens_per_span (≈ 25)
               × quality_multiplier (fast=1×, balanced=2×, high=3×)
               × gemini_price_per_1M_tokens
```

- `quality_multiplier`: fast=1 (1 call), balanced=2 (2 calls), high=3 (3 calls)
- Gemini Flash price ≈ $0.075/1M input tokens (cập nhật theo API pricing hiện tại)
- `recommended_quality`: S→high, M→balanced, L→fast, XL→fast

---

## ③ Quality Tier Engine

**File:** `backend/app/services/translator.py` (mở rộng method hiện tại)

| Tier | Gemini calls/block | Mô tả | Dùng cho |
|------|--------------------|-------|----------|
| `fast` | 1 | Draft translation only | L, XL docs |
| `balanced` | 2 | Draft + verify | M docs (default) |
| `high` | 3 | Draft + glossary + verify (current) | S docs, doc quan trọng |

User có thể override quality tier bất kể volume tier.

Thay đổi trong `translate_text_agentic()`:
- Thêm param `quality: str = "high"` (backward compatible)
- `fast`: chỉ chạy Phase 1
- `balanced`: Phase 1 + Phase 3
- `high`: Phase 1 + Phase 2 + Phase 3 (hiện tại)

---

## ④ Data Model — thay đổi DB

### Bảng `documents` — thêm columns

```sql
ALTER TABLE documents ADD COLUMN volume_tier VARCHAR DEFAULT NULL;
ALTER TABLE documents ADD COLUMN quality_tier VARCHAR DEFAULT 'high';
ALTER TABLE documents ADD COLUMN estimated_cost_usd FLOAT DEFAULT NULL;
ALTER TABLE documents ADD COLUMN estimated_duration_min INT DEFAULT NULL;
```

### Bảng `jobs` — MỚI HOÀN TOÀN

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_num INT DEFAULT NULL,  -- NULL cho stage=extract (toàn doc), int cho translate/compile
    stage VARCHAR NOT NULL,         -- extract / translate / compile
    status VARCHAR NOT NULL DEFAULT 'pending',  -- pending/running/done/failed
    volume_tier VARCHAR NOT NULL,
    quality_tier VARCHAR NOT NULL DEFAULT 'high',
    retries INT DEFAULT 0,
    error_msg TEXT DEFAULT NULL,
    celery_task_id VARCHAR DEFAULT NULL,  -- NULL nếu asyncio path
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP DEFAULT NULL,   -- checkpoint cho resume
    completed_at TIMESTAMP DEFAULT NULL
);
CREATE INDEX idx_jobs_doc_id ON jobs(doc_id);
CREATE INDEX idx_jobs_status ON jobs(status);
```

### SQLAlchemy model mới: `DBJob`

```python
class DBJob(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    doc_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_num = Column(Integer, nullable=False)
    stage = Column(String, nullable=False)
    status = Column(String, default="pending")
    volume_tier = Column(String, nullable=False)
    quality_tier = Column(String, default="high")
    retries = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)
    celery_task_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    document = relationship("DBDocument", back_populates="jobs")

# Cũng cần thêm vào DBDocument:
# jobs = relationship("DBJob", back_populates="document", cascade="all, delete-orphan")
```

> **Lưu ý `page_num`:** Extraction job áp dụng cho toàn bộ document (không phải 1 trang cụ thể) → dùng `page_num=NULL` cho stage `extract`. Translation và compilation dùng `page_num` bình thường.

---

## ⑤ API Endpoints

### Endpoints mới

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/api/docs/{id}/volume` | Trả về VolumeProfile + cost estimate |
| `POST` | `/api/docs/{id}/translate-all` | Dịch tất cả trang, dispatch jobs theo tier |
| `GET` | `/api/docs/{id}/progress` | **SSE stream** — real-time progress |
| `POST` | `/api/docs/{id}/resume` | Resume từ trang bị gián đoạn |
| `GET` | `/api/jobs/{job_id}` | Job status + metadata |
| `GET` | `/api/docs/{id}/jobs` | Tất cả jobs của 1 document |

### SSE Progress event format

```
GET /api/docs/{id}/progress
Content-Type: text/event-stream

data: {"page": 12, "total": 80, "status": "translating", "percent": 15, "eta_min": 6}
data: {"page": 13, "total": 80, "status": "translating", "percent": 16, "eta_min": 5}
data: {"page": 80, "total": 80, "status": "compiled", "percent": 100, "eta_min": 0}
```

### Endpoints hiện tại — cập nhật

| Method | Path | Thay đổi |
|--------|------|----------|
| `POST` | `/api/docs/upload` | + auto-run Volume Detector sau upload |
| `POST` | `/api/docs/{id}/translate` | + param `quality_tier: str = "high"` |
| `POST` | `/api/docs/{id}/extract` | + tạo job record trong `jobs` table |
| `GET` | `/api/docs` | + trả về `volume_tier`, `estimated_cost_usd` |

### translate-all request body

```json
{
  "quality_tier": "balanced",  // optional, override recommended
  "target_lang": "vi"
}
```

---

## ⑥ Resume Capability

**Endpoint:** `POST /api/docs/{id}/resume`

### Logic

```
Với mỗi page trong document:
  status = "raw"         → queue extract job
  status = "extracted"   → queue translate job
  status = "translating" (stuck > 30 phút) → re-queue translate
  status = "translated"  → queue compile job
  status = "failed"      → retry từ stage bị fail (max 3 lần)
  status = "compiled"    → skip
```

**Stuck job timeout:** Job có `started_at` > 30 phút trước và `status = "running"` → tự động đánh dấu `failed` khi resume được gọi.

**Giữ nguyên dữ liệu:** Các `DBTranslation` rows đã có `translated_text` không bị xóa — resume chỉ re-queue page, không xóa translations đã xong.

---

## ⑦ File Structure Refactor

```
backend/app/
├── main.py                  ← chỉ còn app init, CORS, router includes
├── config.py                ← giữ nguyên
├── database.py              ← giữ nguyên
├── models.py                ← giữ nguyên Pydantic models
├── models_db.py             ← thêm DBJob, thêm columns DBDocument
├── routers/                 ← MỚI
│   ├── __init__.py
│   ├── documents.py         ← upload, list, delete, volume endpoint
│   ├── extraction.py        ← extract endpoint + _perform_extraction
│   ├── translation.py       ← translate, translate-all + _perform_translation
│   ├── compilation.py       ← compile endpoint + _perform_compilation
│   └── jobs.py              ← job status, progress SSE, resume
├── services/
│   ├── extractor.py         ← giữ nguyên
│   ├── translator.py        ← thêm quality_tier param
│   ├── compiler.py          ← giữ nguyên
│   ├── volume_detector.py   ← MỚI
│   └── job_manager.py       ← MỚI: asyncio pool + PostgreSQL queue logic
└── workers/                 ← MỚI (chỉ dùng cho L/XL)
    ├── __init__.py
    ├── celery_app.py         ← Celery config, Redis broker URL
    └── tasks.py              ← Celery task: translate_page_task, compile_page_task
```

---

## ⑧ Rollout — 4 phases

### Phase 1 — Foundation (prerequisite cho tất cả)
- Migrate `google-generativeai` → `google.genai`
- Refactor `main.py` → `routers/` (behavior không đổi, chỉ tổ chức lại)
- DB migration: thêm columns `documents`, tạo bảng `jobs`
- Tạo `VolumeDetector` service + `GET /api/docs/{id}/volume`
- Tạo `Cost Estimator` tích hợp trong VolumeDetector
- Auto-run VolumeDetector sau upload

### Phase 2 — asyncio S/M
- `JobManager` service với asyncio Semaphore pools (3 workers S, 8 workers M)
- `Quality Tier Engine` — thêm param `quality_tier` vào translator
- `POST /api/docs/{id}/translate-all` endpoint
- `GET /api/docs/{id}/progress` SSE endpoint
- Job tracking trong `jobs` table cho asyncio path

### Phase 3 — Celery L/XL
- Redis setup (thêm vào `requirements.txt`: `celery[redis]`, `redis`)
- `workers/celery_app.py` + `workers/tasks.py`
- Priority queues: `celery-high` (L), `celery-low` (XL)
- Dead-letter queue cho failed tasks
- `translate-all` route L/XL sang Celery

### Phase 4 — Resume + Polish
- `POST /api/docs/{id}/resume` endpoint
- Stuck job timeout detection (30 min)
- Exponential backoff retry (max 3 lần, delay 2^n seconds)
- `GET /api/docs/{id}/jobs` endpoint
- Frontend progress bar sử dụng SSE stream

---

## Dependencies mới

```
# requirements.txt additions
celery[redis]>=5.3.0    # Phase 3+
redis>=5.0.0            # Phase 3+
```

## Environment variables mới

```bash
# .env additions
REDIS_URL=redis://localhost:6379/0    # Phase 3+
GEMINI_PRICE_PER_1M_TOKENS=0.075     # Cost estimator
```

---

## Trade-offs & Quyết định thiết kế

| Quyết định | Lý do |
|-----------|-------|
| asyncio cho S/M thay vì Celery | Tránh Redis overhead cho docs nhỏ, response nhanh hơn |
| PostgreSQL jobs table thay vì in-memory | Persist qua restart, visible cho resume, audit trail |
| SSE thay vì WebSocket | Simpler, 1-chiều đủ cho progress, FastAPI support tốt |
| Quality tier người dùng override được | Flexibility — doc lớn cũng có thể chọn high quality |
| Phase rollout | Từng phase độc lập, có thể ship sớm mà không cần toàn bộ |
| Resume ở page level (không phải span) | Đủ granular, tránh phức tạp không cần thiết |
