# Adaptive Pipeline — Phase 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuẩn bị nền tảng cho Adaptive Pipeline: migrate Gemini SDK, tách main.py thành routers, thêm DBJob model, và tạo VolumeDetector service.

**Architecture:** Refactor thuần túy + thêm module mới. Behavior của API không đổi sau refactor. VolumeDetector chạy tự động sau upload và expose qua GET /api/docs/{id}/volume.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, google-genai (thay google-generativeai), pytest, httpx

**Working directory cho mọi lệnh:** `apps/break_the_barriers/backend/`

---

## File Structure sau Phase 1

```
backend/app/
├── main.py                   MOD — chỉ còn app init + CORS + router includes + startup
├── config.py                 MOD — thêm GEMINI_PRICE_PER_1M_TOKENS, DATA_DIR
├── database.py               MOD — thêm get_background_db()
├── models.py                 MOD — thêm VolumeProfileResponse, TranslationRequest thêm quality_tier
├── models_db.py              MOD — thêm columns DBDocument, thêm class DBJob
├── core.py                   NEW — is_mock_run(), estimate_pdf_pages()
├── routers/                  NEW dir
│   ├── __init__.py           NEW
│   ├── documents.py          NEW — upload, list, delete, get_pdf, get_asset, get_page, list_pages
│   ├── extraction.py         NEW — extract endpoint + _perform_extraction
│   ├── translation.py        NEW — translate + translation CRUD endpoints
│   ├── compilation.py        NEW — compile endpoint
│   └── volume.py             NEW — GET /api/docs/{id}/volume
└── services/
    ├── extractor.py          KEEP — không đổi
    ├── translator.py         MOD — migrate google.genai, thêm quality param
    ├── compiler.py           KEEP — không đổi
    └── volume_detector.py    NEW — VolumeDetector + VolumeProfile

tests/
├── conftest.py               MOD — thêm DBJob vào Base.metadata
├── test_api.py               MOD — thêm tests cho volume endpoint + upload auto-detect
└── test_services.py          MOD — thêm tests cho VolumeDetector
```

---

## Task 1: Migrate google-generativeai → google.genai

**Files:**
- Modify: `requirements.txt`
- Modify: `app/services/translator.py` (dòng 1-10 và `translate_text_agentic` method)

- [ ] **Step 1: Cập nhật requirements.txt**

```txt
fastapi>=0.110.0
uvicorn>=0.28.0
pydantic>=2.6.0
beautifulsoup4>=4.12.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
python-dotenv>=1.0.0
python-multipart>=0.0.9
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
google-genai>=1.0.0
```

- [ ] **Step 2: Cài package mới**

```bash
../.venv/bin/pip install google-genai>=1.0.0
```

Expected output: `Successfully installed google-genai-...`

- [ ] **Step 3: Thay đổi import và API calls trong translator.py**

Tìm trong `app/services/translator.py` phần `try:` bên trong `translate_text_agentic`, thay toàn bộ block Gemini API:

```python
    @staticmethod
    def translate_text_agentic(text: str, target_lang: str = "vi", glossary: Dict[str, str] = None, quality: str = "high") -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        is_pytest = "pytest" in sys.modules

        if is_pytest or not api_key:
            return Translator._translate_mock(text, target_lang, glossary)

        try:
            from google import genai as google_genai

            client = google_genai.Client(api_key=api_key)
            MODEL = "gemini-2.0-flash"

            lang_names = {
                "vi": "Vietnamese", "en": "English", "zh": "Chinese",
                "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German"
            }
            lang_name = lang_names.get(target_lang.lower(), target_lang)

            # PHASE 1: Draft Translation
            prompt_draft = (
                f"You are a professional book translator and editor.\n"
                f"Translate the source text to high-fidelity {lang_name}, OR restore mangled PDF characters.\n"
                f"Rules:\n"
                f"1. Strictly preserve placeholders like '[s:span_id]' in exact positions.\n"
                f"2. Translate to beautiful, fluent {lang_name}.\n"
                f"3. If input is already {lang_name} with missing accents, restore them.\n\n"
                f"Source Text:\n{text}\n\n{lang_name} Draft:"
            )
            draft_text = client.models.generate_content(model=MODEL, contents=prompt_draft).text.strip()

            if quality == "fast":
                return draft_text

            # PHASE 2: Glossary Refinement (only for quality="high")
            refined_text = draft_text
            if quality == "high" and glossary:
                glossary_str = "\n".join([f"- '{e}': '{v}'" for e, v in glossary.items()])
                prompt_refine = (
                    f"Refine the {lang_name} translation using the glossary. Preserve '[s:span_id]' placeholders.\n\n"
                    f"Glossary:\n{glossary_str}\n\nDraft:\n{draft_text}\n\nRefined {lang_name}:"
                )
                refined_text = client.models.generate_content(model=MODEL, contents=prompt_refine).text.strip()

            # PHASE 3: Verification (for quality="balanced" and "high")
            prompt_verify = (
                f"Check the {lang_name} translation for natural flow. Ensure all '[s:span_id]' placeholders are intact.\n"
                f"Output ONLY the final {lang_name} string.\n\n"
                f"Source:\n{text}\n\nTranslated:\n{refined_text}\n\nFinal {lang_name} Output:"
            )
            return client.models.generate_content(model=MODEL, contents=prompt_verify).text.strip()

        except Exception as e:
            logger.error(f"Gemini API Translation failed: {e}. Falling back to mock translator.")
            return Translator._translate_mock(text, target_lang, glossary)
```

- [ ] **Step 4: Chạy test để verify không regression**

```bash
../.venv/bin/pytest tests/ -x -q
```

Expected: tất cả tests PASS (mock translator vẫn chạy khi pytest)

- [ ] **Step 5: Commit**

```bash
git add app/services/translator.py requirements.txt
git commit -m "feat: migrate google-generativeai to google.genai, add quality param"
```

---

## Task 2: Tạo core.py và cập nhật config.py + database.py

**Files:**
- Create: `app/core.py`
- Modify: `app/config.py`
- Modify: `app/database.py`

- [ ] **Step 1: Viết test cho is_mock_run và estimate_pdf_pages**

Thêm vào `tests/test_services.py`:

```python
import os, sys

def test_is_mock_run_returns_true_in_pytest():
    from backend.app.core import is_mock_run
    assert is_mock_run("any_doc") is True

def test_estimate_pdf_pages_fallback_on_invalid_file(tmp_path):
    from backend.app.core import estimate_pdf_pages
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not a real pdf")
    assert estimate_pdf_pages(str(fake_pdf)) == 10

def test_estimate_pdf_pages_reads_count(tmp_path):
    from backend.app.core import estimate_pdf_pages
    pdf_content = b"%PDF-1.4\n/Count 42\n"
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(pdf_content)
    assert estimate_pdf_pages(str(fake_pdf)) == 42
```

- [ ] **Step 2: Chạy test để verify FAIL trước**

```bash
../.venv/bin/pytest tests/test_services.py::test_is_mock_run_returns_true_in_pytest -v
```

Expected: FAIL với `ModuleNotFoundError: No module named 'backend.app.core'`

- [ ] **Step 3: Tạo app/core.py**

```python
import os
import re
import sys
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(os.path.join(DATA_DIR, "raw_pdf"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "extracted_html"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "pages"), exist_ok=True)


def is_mock_run(doc_id: str) -> bool:
    if "pytest" in sys.modules:
        return True
    pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        return True
    if os.path.getsize(pdf_path) < 1000:
        return True
    return False


def estimate_pdf_pages(pdf_path: str) -> int:
    try:
        with open(pdf_path, "rb") as f:
            content = f.read(5 * 1024 * 1024)
            matches = re.findall(rb"/Count\s+(\d+)", content)
            if matches:
                return max(int(m) for m in matches)
    except Exception as e:
        logger.error(f"Error estimating PDF pages: {e}")
    return 10
```

- [ ] **Step 4: Cập nhật app/config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/break_the_barriers"
)

GEMINI_PRICE_PER_1M_TOKENS = float(os.getenv("GEMINI_PRICE_PER_1M_TOKENS", "0.075"))
```

- [ ] **Step 5: Cập nhật app/database.py — thêm get_background_db()**

```python
import sys
import inspect
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.app.config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_background_db():
    """DB session cho background tasks — test-aware."""
    from backend.app.main import app

    if get_db in app.dependency_overrides:
        override = app.dependency_overrides[get_db]
        globals_dict = getattr(override, "__globals__", {})
        TestingSessionLocal = globals_dict.get("TestingSessionLocal")
        if TestingSessionLocal is not None:
            return TestingSessionLocal()
        if inspect.isgeneratorfunction(override):
            try:
                return next(override())
            except StopIteration:
                pass
        else:
            return override()

    if "pytest" in sys.modules:
        for name, mod in list(sys.modules.items()):
            if name.endswith("conftest") and hasattr(mod, "TestingSessionLocal"):
                try:
                    return getattr(mod, "TestingSessionLocal")()
                except Exception:
                    pass

    return SessionLocal()
```

- [ ] **Step 6: Chạy test**

```bash
../.venv/bin/pytest tests/test_services.py -k "mock_run or pdf_pages" -v
```

Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/core.py app/config.py app/database.py
git commit -m "refactor: extract DATA_DIR, is_mock_run, estimate_pdf_pages to core.py"
```

---

## Task 3: Cập nhật DB Models — thêm DBDocument columns + DBJob

**Files:**
- Modify: `app/models_db.py`
- Modify: `app/models.py` (thêm VolumeProfileResponse)
- Create: `migrate_v2.py` (migration script)
- Modify: `tests/conftest.py` (auto-include DBJob trong test schema)

- [ ] **Step 1: Viết test cho DBJob model**

Thêm vào `tests/test_services.py`:

```python
def test_dbjob_can_be_created(db_session):
    from backend.app.models_db import DBJob
    job = DBJob(
        doc_id="clean_code",
        stage="translate",
        volume_tier="S",
        quality_tier="high",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    assert job.id is not None
    assert job.status == "pending"
    assert job.retries == 0
    assert job.page_num is None
```

- [ ] **Step 2: Chạy test để verify FAIL**

```bash
../.venv/bin/pytest tests/test_services.py::test_dbjob_can_be_created -v
```

Expected: FAIL với `ImportError` hoặc `NoSuchTableError`

- [ ] **Step 3: Cập nhật app/models_db.py**

```python
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base


class DBDocument(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    total_pages = Column(Integer, default=0)
    status = Column(String, default="raw")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Phase 1 additions
    volume_tier = Column(String, nullable=True)
    quality_tier = Column(String, default="high")
    estimated_cost_usd = Column(Float, nullable=True)
    estimated_duration_min = Column(Integer, nullable=True)

    pages = relationship("DBPage", back_populates="document", cascade="all, delete-orphan")
    translations = relationship("DBTranslation", back_populates="document", cascade="all, delete-orphan")
    jobs = relationship("DBJob", back_populates="document", cascade="all, delete-orphan")


class DBPage(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=False)
    original_html = Column(Text, nullable=True)
    translated_html = Column(Text, nullable=True)
    status = Column(String, default="raw")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("DBDocument", back_populates="pages")


class DBTranslation(Base):
    __tablename__ = "translations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=False)
    span_id = Column(String, nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("DBDocument", back_populates="translations")


class DBJob(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    doc_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=True)
    stage = Column(String, nullable=False)
    status = Column(String, default="pending", index=True)
    volume_tier = Column(String, nullable=False)
    quality_tier = Column(String, default="high")
    retries = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)
    celery_task_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    document = relationship("DBDocument", back_populates="jobs")
```

- [ ] **Step 4: Cập nhật app/models.py — thêm VolumeProfileResponse, sửa TranslationRequest**

Trong `app/models.py`, **replace** class `TranslationRequest` hiện tại:

```python
# Thay class này (dòng ~15):
class TranslationRequest(BaseModel):
    page_num: int
    target_lang: str = "vi"
    quality_tier: str = "high"   # <-- thêm field mới, default "high" = backward compatible
```

Và **thêm vào cuối file** class mới:

```python
class VolumeProfileResponse(BaseModel):
    tier: str
    page_count: int
    estimated_spans: int
    estimated_tokens: int
    estimated_cost_usd: float
    recommended_quality: str
    processing_path: str
    estimated_duration_min: int
```

- [ ] **Step 5: Tạo migrate_v2.py để áp dụng lên production DB**

```python
"""
Migration v2: Add volume/quality columns to documents; create jobs table.
Run: ../.venv/bin/python migrate_v2.py
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/break_the_barriers")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
    ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS volume_tier VARCHAR DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS quality_tier VARCHAR DEFAULT 'high',
    ADD COLUMN IF NOT EXISTS estimated_cost_usd FLOAT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS estimated_duration_min INT DEFAULT NULL;
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id VARCHAR PRIMARY KEY,
        doc_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        page_num INT DEFAULT NULL,
        stage VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'pending',
        volume_tier VARCHAR NOT NULL,
        quality_tier VARCHAR NOT NULL DEFAULT 'high',
        retries INT DEFAULT 0,
        error_msg TEXT DEFAULT NULL,
        celery_task_id VARCHAR DEFAULT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP DEFAULT NULL,
        completed_at TIMESTAMP DEFAULT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_doc_id ON jobs(doc_id);
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
""")

conn.commit()
cur.close()
conn.close()
print("Migration v2 complete.")
```

- [ ] **Step 6: Chạy migration lên production DB**

```bash
../.venv/bin/python migrate_v2.py
```

Expected: `Migration v2 complete.`

- [ ] **Step 7: Chạy test**

```bash
../.venv/bin/pytest tests/test_services.py::test_dbjob_can_be_created -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/models_db.py app/models.py migrate_v2.py
git commit -m "feat: add DBJob model, volume/quality columns to DBDocument"
```

---

## Task 4: Tạo VolumeDetector service

**Files:**
- Create: `app/services/volume_detector.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: Viết tests cho VolumeDetector**

Thêm vào `tests/test_services.py`:

```python
def test_volume_detector_tier_s():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=30)
    assert profile.tier == "S"
    assert profile.processing_path == "asyncio"
    assert profile.recommended_quality == "high"
    assert profile.estimated_spans == 30 * 40
    assert profile.estimated_cost_usd > 0

def test_volume_detector_tier_m():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=100)
    assert profile.tier == "M"
    assert profile.processing_path == "asyncio"
    assert profile.recommended_quality == "balanced"

def test_volume_detector_tier_l():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=300)
    assert profile.tier == "L"
    assert profile.processing_path == "celery"
    assert profile.recommended_quality == "fast"

def test_volume_detector_tier_xl():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=600)
    assert profile.tier == "XL"
    assert profile.processing_path == "celery"

def test_volume_detector_quality_override():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=300, quality_override="high")
    assert profile.tier == "L"
    assert profile.recommended_quality == "fast"
    # cost with override=high (3x) > cost with fast (1x)
    profile_fast = VolumeDetector.detect(page_count=300)
    assert profile.estimated_tokens > profile_fast.estimated_tokens

def test_volume_detector_cost_calculation():
    from backend.app.services.volume_detector import VolumeDetector, AVG_SPANS_PER_PAGE, AVG_TOKENS_PER_SPAN, GEMINI_PRICE_PER_1M_TOKENS
    profile = VolumeDetector.detect(page_count=10, quality_override="fast")
    expected_spans = 10 * AVG_SPANS_PER_PAGE
    expected_tokens = expected_spans * AVG_TOKENS_PER_SPAN * 1  # fast multiplier = 1
    expected_cost = round((expected_tokens / 1_000_000) * GEMINI_PRICE_PER_1M_TOKENS, 4)
    assert profile.estimated_spans == expected_spans
    assert profile.estimated_tokens == expected_tokens
    assert profile.estimated_cost_usd == expected_cost
```

- [ ] **Step 2: Chạy tests để verify FAIL**

```bash
../.venv/bin/pytest tests/test_services.py -k "volume_detector" -v
```

Expected: 6 tests FAIL với `ModuleNotFoundError`

- [ ] **Step 3: Tạo app/services/volume_detector.py**

```python
import os
import logging
from dataclasses import dataclass
from typing import Optional
from backend.app.config import GEMINI_PRICE_PER_1M_TOKENS

logger = logging.getLogger(__name__)

AVG_SPANS_PER_PAGE = 40
AVG_TOKENS_PER_SPAN = 25
QUALITY_MULTIPLIERS = {"fast": 1, "balanced": 2, "high": 3}
SECS_PER_SPAN = {"fast": 0.5, "balanced": 1.0, "high": 2.0}

_TIER_TABLE = [
    # (tier, lo, hi, processing_path, recommended_quality)
    ("S",  0,   50,  "asyncio", "high"),
    ("M",  50,  200, "asyncio", "balanced"),
    ("L",  200, 500, "celery",  "fast"),
    ("XL", 500, 10_000_000, "celery", "fast"),
]


@dataclass
class VolumeProfile:
    tier: str
    page_count: int
    estimated_spans: int
    estimated_tokens: int
    estimated_cost_usd: float
    recommended_quality: str
    processing_path: str
    estimated_duration_min: int


class VolumeDetector:
    @staticmethod
    def detect(page_count: int, quality_override: Optional[str] = None) -> VolumeProfile:
        tier = "XL"
        processing_path = "celery"
        recommended_quality = "fast"

        for t, lo, hi, path, quality in _TIER_TABLE:
            if lo <= page_count < hi:
                tier, processing_path, recommended_quality = t, path, quality
                break

        effective_quality = quality_override or recommended_quality
        multiplier = QUALITY_MULTIPLIERS.get(effective_quality, 3)

        estimated_spans = page_count * AVG_SPANS_PER_PAGE
        estimated_tokens = estimated_spans * AVG_TOKENS_PER_SPAN * multiplier
        estimated_cost_usd = round(
            (estimated_tokens / 1_000_000) * GEMINI_PRICE_PER_1M_TOKENS, 4
        )
        secs = SECS_PER_SPAN.get(effective_quality, 2.0)
        estimated_duration_min = max(1, int(estimated_spans * secs / 60))

        return VolumeProfile(
            tier=tier,
            page_count=page_count,
            estimated_spans=estimated_spans,
            estimated_tokens=estimated_tokens,
            estimated_cost_usd=estimated_cost_usd,
            recommended_quality=recommended_quality,
            processing_path=processing_path,
            estimated_duration_min=estimated_duration_min,
        )
```

- [ ] **Step 4: Chạy tests**

```bash
../.venv/bin/pytest tests/test_services.py -k "volume_detector" -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/volume_detector.py app/config.py tests/test_services.py
git commit -m "feat: add VolumeDetector service with tier classification and cost estimation"
```

---

## Task 5: Tạo routers/ — tách main.py thành các router

**Files:**
- Create: `app/routers/__init__.py`
- Create: `app/routers/documents.py`
- Create: `app/routers/extraction.py`
- Create: `app/routers/translation.py`
- Create: `app/routers/compilation.py`
- Modify: `app/main.py`

> **Quan trọng:** Task này là pure refactor — behavior KHÔNG đổi. Tests phải PASS trước và sau.

- [ ] **Step 1: Chạy full test suite để có baseline**

```bash
../.venv/bin/pytest tests/ -q
```

Ghi lại số tests PASS. Tất cả phải pass trước khi refactor.

- [ ] **Step 2: Tạo app/routers/__init__.py**

```python
```
(file rỗng)

- [ ] **Step 3: Tạo app/routers/documents.py**

```python
import os
import re
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import DocumentMetadata
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR, estimate_pdf_pages
from backend.app.services.volume_detector import VolumeDetector

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
def get_status():
    return {"status": "online", "service": "Smart Documentations Backend", "docs_url": "/docs"}


@router.get("/api/docs", response_model=List[DocumentMetadata])
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(DBDocument).all()
    return [
        DocumentMetadata(
            id=d.id, filename=d.filename, total_pages=d.total_pages,
            status=d.status, created_at=d.created_at.isoformat()
        )
        for d in docs
    ]


@router.get("/api/docs/{doc_id}/pages")
def list_document_pages(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    pages = db.query(DBPage).filter(DBPage.document_id == doc_id).order_by(DBPage.page_num).all()
    return [
        {"page_num": p.page_num, "status": p.status,
         "has_original": p.original_html is not None,
         "has_translated": p.translated_html is not None}
        for p in pages
    ]


@router.post("/api/docs/upload", response_model=DocumentMetadata)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    doc_id = os.path.splitext(file.filename)[0].lower().replace(" ", "_")
    pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
    content = await file.read()
    with open(pdf_path, "wb") as f:
        f.write(content)

    matches = re.findall(rb"/Count\s+(\d+)", content)
    estimated_pages = 10
    if matches:
        try:
            estimated_pages = max(int(m) for m in matches)
        except ValueError:
            pass

    # Auto-detect volume profile after upload
    volume = VolumeDetector.detect(page_count=estimated_pages)

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        doc = DBDocument(
            id=doc_id, filename=file.filename, total_pages=estimated_pages, status="raw",
            volume_tier=volume.tier, quality_tier=volume.recommended_quality,
            estimated_cost_usd=volume.estimated_cost_usd,
            estimated_duration_min=volume.estimated_duration_min,
        )
        db.add(doc)
    else:
        doc.total_pages = estimated_pages
        doc.status = "raw"
        doc.volume_tier = volume.tier
        doc.quality_tier = volume.recommended_quality
        doc.estimated_cost_usd = volume.estimated_cost_usd
        doc.estimated_duration_min = volume.estimated_duration_min
    db.commit()
    db.refresh(doc)

    return DocumentMetadata(
        id=doc.id, filename=doc.filename, total_pages=doc.total_pages,
        status=doc.status, created_at=doc.created_at.isoformat()
    )


@router.delete("/api/docs/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    import shutil
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    for path in [
        os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf"),
    ]:
        if os.path.exists(path):
            try: os.remove(path)
            except Exception as e: logger.error(f"Failed to delete {path}: {e}")
    for dirpath in [
        os.path.join(DATA_DIR, "extracted_html", doc_id),
        os.path.join(DATA_DIR, "pages", doc_id),
    ]:
        if os.path.exists(dirpath):
            try: shutil.rmtree(dirpath)
            except Exception as e: logger.error(f"Failed to delete {dirpath}: {e}")
    return {"status": "deleted", "doc_id": doc_id, "message": "Document and all related assets deleted successfully"}


@router.get("/api/docs/{doc_id}/pdf")
def get_pdf_file(doc_id: str, page: Optional[int] = Query(None), db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if page is not None:
        page_pdf_path = os.path.join(DATA_DIR, "raw_pdf", doc_id, f"{page}.pdf")
        if not os.path.exists(page_pdf_path):
            pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
            if not os.path.exists(pdf_path):
                raise HTTPException(status_code=404, detail="PDF file not found")
            try:
                from pypdf import PdfReader, PdfWriter
                reader = PdfReader(pdf_path)
                if page < 1 or page > len(reader.pages):
                    raise HTTPException(status_code=400, detail="Page number out of bounds")
                os.makedirs(os.path.join(DATA_DIR, "raw_pdf", doc_id), exist_ok=True)
                writer = PdfWriter()
                writer.add_page(reader.pages[page - 1])
                with open(page_pdf_path, "wb") as f:
                    writer.write(f)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to split PDF: {str(e)}")
        return FileResponse(page_pdf_path, media_type="application/pdf")
    pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(pdf_path, media_type="application/pdf")


@router.get("/api/docs/{doc_id}/assets/{filename}")
def get_document_asset(doc_id: str, filename: str):
    file_path = os.path.join(DATA_DIR, "extracted_html", doc_id, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(DATA_DIR, "pages", doc_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = "application/octet-stream"
    if filename.lower().endswith(".png"): media_type = "image/png"
    elif filename.lower().endswith((".jpg", ".jpeg")): media_type = "image/jpeg"
    elif filename.lower().endswith(".gif"): media_type = "image/gif"
    return FileResponse(file_path, media_type=media_type)


@router.get("/api/docs/{doc_id}/pages/{page_num}")
def get_page_content(
    doc_id: str, page_num: int,
    lang: str = Query("en", pattern="^(en|vi)$"),
    raw: bool = Query(False),
    db: Session = Depends(get_db)
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if lang == "vi":
        html_content = page.translated_html or page.original_html or ""
    else:
        html_content = page.original_html or ""
    if raw:
        return HTMLResponse(content=html_content)
    return {
        "doc_id": doc_id, "page_num": page_num, "lang": lang,
        "html": html_content, "status": page.status,
    }
```

- [ ] **Step 4: Tạo app/routers/extraction.py**

```python
import logging
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db, get_background_db
from backend.app.models import ExtractionResult
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR, is_mock_run
from backend.app.services.extractor import Extractor
from bs4 import BeautifulSoup
import os

logger = logging.getLogger(__name__)
router = APIRouter()


def _perform_extraction(doc_id: str, db: Session) -> ExtractionResult:
    # --- copy toàn bộ hàm _perform_extraction từ main.py (dòng 222–380) ---
    # Import sys tại đây vì cần cho is_mock_run fallback
    import sys, shutil
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    db.query(DBPage).filter(DBPage.document_id == doc_id).delete()
    db.query(DBTranslation).filter(DBTranslation.document_id == doc_id).delete()

    if is_mock_run(doc_id):
        for page_num in range(1, doc.total_pages + 1):
            if page_num == 1:
                original_html = """<!DOCTYPE html>
<html><head><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">
<style type="text/css">body { background-color: #A0A0A0; } .ff0 { font-family: sans-serif; }</style>
</head><body><div id="page-container"><div class="pf w0 h0" data-page-no="1">
<span id="s1" class="ff0 fs0 fc0 sc0 ls0" style="position:absolute; left:100.5px; top:200.0px;">Introductory</span>
<span id="s2" class="ff0 fs0 fc0 sc0 ls0" style="position:absolute; left:180.2px; top:200.3px;">Programming</span>
<span id="s3" class="ff0 fs0 fc0 sc0 ls0" style="position:absolute; left:100.5px; top:230.0px;">Second line of text</span>
<span id="s4" class="ff0 fs0 fc0 sc0 ls0" style="position:absolute; left:100.5px; top:260.0px;">Hello World</span>
</div></div></body></html>"""
            else:
                original_html = f"""<!DOCTYPE html><html><head>
<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"></head>
<body><div id="page-container"><div class="pf w0 h0" data-page-no="{page_num}">
<span id="s1" style="position:absolute; left:100px; top:200px;">Hello World page {page_num}</span>
</div></div></body></html>"""

            sanitized_html = Extractor.sanitize_html(original_html)
            spans = Extractor.extract_spans(sanitized_html)
            db.add(DBPage(document_id=doc_id, page_num=page_num, original_html=sanitized_html, status="raw"))
            for s in spans:
                db.add(DBTranslation(document_id=doc_id, page_num=page_num, span_id=s["id"], original_text=s["text"]))
    else:
        pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
        extracted_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)
        try:
            html_files = Extractor.extract_pdf_to_html_cli(pdf_path, extracted_dir, doc_id)
        except Exception as e:
            logger.error(f"pdftohtml CLI failed: {e}. Falling back to mock extraction.")
            import sys as _sys
            old = _sys.modules.copy()
            _sys.modules["pytest"] = _sys.modules.get("pytest", "mock")
            res = _perform_extraction(doc_id, db)
            _sys.modules = old
            return res

        if html_files:
            doc.total_pages = len(html_files)

        for i, file_path in enumerate(html_files):
            page_num = i + 1
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                original_html = f.read()
            sanitized_html = Extractor.sanitize_html(original_html)
            soup = BeautifulSoup(sanitized_html, "html.parser")
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if src and not (src.startswith("http") or src.startswith("/")):
                    img["src"] = f"/api/docs/{doc_id}/assets/{src}"
            sanitized_html = str(soup)
            spans = Extractor.extract_spans(sanitized_html)
            db.add(DBPage(document_id=doc_id, page_num=page_num, original_html=sanitized_html, status="raw"))
            for s in spans:
                db.add(DBTranslation(document_id=doc_id, page_num=page_num, span_id=s["id"], original_text=s["text"]))

    doc.status = "extracted"
    db.commit()
    db.refresh(doc)
    return ExtractionResult(id=doc.id, pages_count=doc.total_pages, extracted_html_dir=f"data/extracted_html/{doc_id}")


def run_background_extract(doc_id: str):
    db = get_background_db()
    try:
        _perform_extraction(doc_id, db)
    except Exception as e:
        logger.error(f"Background extraction failed for {doc_id}: {e}")
        doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
        if doc:
            doc.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/api/docs/{doc_id}/extract")
def extract_document(
    doc_id: str,
    async_mode: bool = Query(False),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if async_mode:
        doc.status = "extracting"
        db.commit()
        if background_tasks:
            background_tasks.add_task(run_background_extract, doc_id)
        else:
            run_background_extract(doc_id)
        return JSONResponse(status_code=202, content={"status": "extracting", "doc_id": doc_id, "message": "Extraction started in background"})
    return _perform_extraction(doc_id, db)
```

- [ ] **Step 5: Tạo app/routers/translation.py**

```python
import logging
from typing import List
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.database import get_db, get_background_db
from backend.app.models import TranslationRequest, TranslationItem, TranslationUpdate
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.services.extractor import Extractor
from backend.app.services.translator import Translator
from backend.app.routers.compilation import _perform_compilation

logger = logging.getLogger(__name__)
router = APIRouter()


def _perform_translation(doc_id: str, page_num: int, target_lang: str, db: Session, quality: str = "high") -> dict:
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if page_num <= 0:
        raise HTTPException(status_code=400, detail="Invalid page number")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    page.translated_html = None
    spans_list = Extractor.extract_spans(page.original_html)
    reconstructed = Translator.reconstruct_context_and_index(spans_list)

    for block in reconstructed:
        translated_block = Translator.translate_text_agentic(block["text"], target_lang=target_lang, quality=quality)
        if len(block["span_ids"]) == 1:
            span_id = block["span_ids"][0]
            t_row = db.query(DBTranslation).filter(
                DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num,
                DBTranslation.span_id == span_id
            ).first()
            if t_row:
                t_row.translated_text = translated_block
        else:
            span_translations = Translator.deinterpolate_translation(translated_block, block["span_ids"])
            for sid, text in span_translations.items():
                t_row = db.query(DBTranslation).filter(
                    DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num,
                    DBTranslation.span_id == sid
                ).first()
                if t_row:
                    t_row.translated_text = text

    page.status = "translated"
    all_pages = db.query(DBPage).filter(DBPage.document_id == doc_id).all()
    if all_pages and all(p.status in ["translated", "compiled"] for p in all_pages):
        doc.status = "translated"
    db.commit()
    return {"status": "translated", "doc_id": doc_id, "page_num": page_num, "target_lang": target_lang}


def run_background_translate(doc_id: str, page_num: int, target_lang: str, quality: str = "high"):
    db = get_background_db()
    try:
        _perform_translation(doc_id, page_num, target_lang, db, quality)
    except Exception as e:
        logger.error(f"Background translation failed for {doc_id} page {page_num}: {e}")
        page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
        if page:
            page.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/api/docs/{doc_id}/translate")
def translate_page(
    doc_id: str, payload: TranslationRequest,
    async_mode: bool = Query(False),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    if payload.page_num <= 0:
        raise HTTPException(status_code=400, detail="Invalid page number")
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == payload.page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    quality = getattr(payload, "quality_tier", "high") or "high"

    if async_mode:
        page.status = "translating"
        db.commit()
        if background_tasks:
            background_tasks.add_task(run_background_translate, doc_id, payload.page_num, payload.target_lang, quality)
        else:
            run_background_translate(doc_id, payload.page_num, payload.target_lang, quality)
        return JSONResponse(status_code=202, content={"status": "translating", "doc_id": doc_id, "page_num": payload.page_num, "message": "Translation started in background"})
    return _perform_translation(doc_id, payload.page_num, payload.target_lang, db, quality)


@router.get("/api/docs/{doc_id}/translations", response_model=List[TranslationItem])
def list_translations(doc_id: str, limit: int = Query(50, ge=1), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    translations = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id)\
        .order_by(DBTranslation.page_num, DBTranslation.id).offset(offset).limit(limit).all()
    return [TranslationItem(id=t.id, document_id=t.document_id, page_num=t.page_num, span_id=t.span_id,
                            original_text=t.original_text, translated_text=t.translated_text,
                            created_at=t.created_at.isoformat()) for t in translations]


@router.get("/api/docs/{doc_id}/translations/search", response_model=List[TranslationItem])
def search_translations(doc_id: str, q: str = Query(...), db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    translations = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id)\
        .filter(or_(DBTranslation.original_text.ilike(f"%{q}%"), DBTranslation.translated_text.ilike(f"%{q}%")))\
        .order_by(DBTranslation.page_num, DBTranslation.id).all()
    return [TranslationItem(id=t.id, document_id=t.document_id, page_num=t.page_num, span_id=t.span_id,
                            original_text=t.original_text, translated_text=t.translated_text,
                            created_at=t.created_at.isoformat()) for t in translations]


@router.put("/api/docs/{doc_id}/translations/{span_id}")
def update_translation(doc_id: str, span_id: str, payload: TranslationUpdate, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    translations = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id, DBTranslation.span_id == span_id).all()
    if not translations:
        raise HTTPException(status_code=404, detail="Translation span not found in document")
    for t in translations:
        t.translated_text = payload.translated_text
    db.commit()
    affected_pages = sorted({t.page_num for t in translations})
    recompiled_pages = []
    for page_num in affected_pages:
        page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
        if page and page.status == "compiled":
            try:
                _perform_compilation(doc_id, page_num, db)
                recompiled_pages.append(page_num)
            except Exception as e:
                logger.error(f"Auto Re-compile failed for page {page_num}: {e}")
    return {"status": "updated", "doc_id": doc_id, "span_id": span_id, "recompiled_pages": recompiled_pages}
```

- [ ] **Step 6: Tạo app/routers/compilation.py**

```python
import os
import shutil
import logging
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db, get_background_db
from backend.app.models import CompilationRequest
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR
from backend.app.services.compiler import Compiler

logger = logging.getLogger(__name__)
router = APIRouter()


def _perform_compilation(doc_id: str, page_num: int, db: Session) -> dict:
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if page_num <= 0:
        raise HTTPException(status_code=400, detail="Invalid page number")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    translations = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num).all()
    translated_texts = {t.span_id: (t.translated_text or t.original_text) for t in translations}

    if not Compiler.verify_quality_gates(page.original_html, translated_texts):
        raise HTTPException(status_code=422, detail="Quality Gate 2 Failed: Mismatched tag count")

    compiled_html = Compiler.inject_translation(page.original_html, translated_texts)
    page.translated_html = compiled_html
    page.status = "compiled"

    compiled_dir = os.path.join(DATA_DIR, "pages", doc_id)
    os.makedirs(compiled_dir, exist_ok=True)
    with open(os.path.join(compiled_dir, f"page_{page_num}.html"), "w", encoding="utf-8") as f:
        f.write(compiled_html)

    extracted_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)
    if os.path.exists(extracted_dir):
        for item in os.listdir(extracted_dir):
            if item.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                try: shutil.copy2(os.path.join(extracted_dir, item), os.path.join(compiled_dir, item))
                except Exception: pass

    all_pages = db.query(DBPage).filter(DBPage.document_id == doc_id).all()
    if all_pages and all(p.status == "compiled" for p in all_pages):
        doc.status = "compiled"
    db.commit()
    return {"status": "compiled", "doc_id": doc_id, "page_num": page_num, "html_path": f"data/pages/{doc_id}/page_{page_num}.html"}


def run_background_compile(doc_id: str, page_num: int):
    db = get_background_db()
    try:
        _perform_compilation(doc_id, page_num, db)
    except Exception as e:
        logger.error(f"Background compilation failed for {doc_id} page {page_num}: {e}")
        page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
        if page:
            page.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/api/docs/{doc_id}/compile")
def compile_page(
    doc_id: str, payload: CompilationRequest,
    async_mode: bool = Query(False),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    if payload.page_num <= 0:
        raise HTTPException(status_code=400, detail="Invalid page number")
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == payload.page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if async_mode:
        page.status = "compiling"
        db.commit()
        if background_tasks:
            background_tasks.add_task(run_background_compile, doc_id, payload.page_num)
        else:
            run_background_compile(doc_id, payload.page_num)
        return JSONResponse(status_code=202, content={"status": "compiling", "doc_id": doc_id, "page_num": payload.page_num, "message": "Compilation started in background"})
    return _perform_compilation(doc_id, payload.page_num, db)
```

- [ ] **Step 7: Tạo app/routers/volume.py**

```python
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import VolumeProfileResponse
from backend.app.models_db import DBDocument
from backend.app.services.volume_detector import VolumeDetector

router = APIRouter()


@router.get("/api/docs/{doc_id}/volume", response_model=VolumeProfileResponse)
def get_volume_profile(doc_id: str, quality_override: str = None, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    profile = VolumeDetector.detect(page_count=doc.total_pages, quality_override=quality_override)
    return VolumeProfileResponse(
        tier=profile.tier,
        page_count=profile.page_count,
        estimated_spans=profile.estimated_spans,
        estimated_tokens=profile.estimated_tokens,
        estimated_cost_usd=profile.estimated_cost_usd,
        recommended_quality=profile.recommended_quality,
        processing_path=profile.processing_path,
        estimated_duration_min=profile.estimated_duration_min,
    )
```

- [ ] **Step 8: Cập nhật app/main.py thành minimal**

```python
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.database import engine, Base, get_db, SessionLocal
from backend.app.models_db import DBDocument
from backend.app.routers import documents, extraction, translation, compilation, volume

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Smart Documentations API",
    description="API-First Backend for Digitizing and High-Fidelity Translation of PDF books",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(extraction.router)
app.include_router(translation.router)
app.include_router(compilation.router)
app.include_router(volume.router)


@app.on_event("startup")
def startup_populate():
    import sys
    if "pytest" in sys.modules:
        return
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        if not db.query(DBDocument).filter(DBDocument.id == "clean_code").first():
            db.add(DBDocument(id="clean_code", filename="Clean_Code.pdf", total_pages=10, status="raw"))
            db.commit()
    finally:
        db.close()
```

- [ ] **Step 9: Chạy full test suite — phải giống baseline**

```bash
../.venv/bin/pytest tests/ -q
```

Expected: cùng số tests PASS như baseline ở Step 1 của task này. Nếu có FAIL, debug trước khi commit.

- [ ] **Step 10: Commit**

```bash
git add app/routers/ app/main.py
git commit -m "refactor: split main.py into routers (documents, extraction, translation, compilation, volume)"
```

---

## Task 6: Tests cho volume endpoint và upload auto-detect

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Thêm tests**

Thêm vào `tests/test_api.py`:

```python
def test_get_volume_profile(client):
    response = client.get("/api/docs/clean_code/volume")
    assert response.status_code == 200
    data = response.json()
    assert "tier" in data
    assert "estimated_cost_usd" in data
    assert "processing_path" in data
    assert data["page_count"] == 10
    assert data["tier"] == "S"  # clean_code có 10 trang
    assert data["processing_path"] == "asyncio"
    assert data["recommended_quality"] == "high"

def test_get_volume_profile_not_found(client):
    response = client.get("/api/docs/nonexistent_doc/volume")
    assert response.status_code == 404

def test_get_volume_profile_quality_override(client):
    response = client.get("/api/docs/clean_code/volume?quality_override=fast")
    assert response.status_code == 200
    data = response.json()
    # Cost với fast (1x) phải nhỏ hơn high (3x)
    response_high = client.get("/api/docs/clean_code/volume?quality_override=high")
    data_high = response_high.json()
    assert data["estimated_tokens"] < data_high["estimated_tokens"]

def test_upload_auto_detects_volume(client):
    files = {"file": ("small_book.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    response = client.post("/api/docs/upload", files=files)
    assert response.status_code == 200
    # Volume detection không fail upload — doc vẫn tạo thành công
    data = response.json()
    assert data["filename"] == "small_book.pdf"
    assert data["status"] == "raw"
```

- [ ] **Step 2: Chạy tests**

```bash
../.venv/bin/pytest tests/test_api.py -k "volume or auto_detect" -v
```

Expected: 4 tests PASS

- [ ] **Step 3: Chạy full suite lần cuối**

```bash
../.venv/bin/pytest tests/ -q
```

Expected: tất cả PASS

- [ ] **Step 4: Commit cuối Phase 1**

```bash
git add tests/test_api.py tests/test_services.py
git commit -m "test: add volume endpoint and upload auto-detect tests"
```

---

## Checklist Phase 1 hoàn thành

- [ ] `google-generativeai` → `google.genai` migration xong, tests pass
- [ ] `core.py` có `DATA_DIR`, `is_mock_run`, `estimate_pdf_pages`
- [ ] `database.py` có `get_background_db()`
- [ ] `models_db.py` có `DBJob` + columns mới cho `DBDocument`
- [ ] Migration v2 đã chạy lên production DB
- [ ] `main.py` chỉ còn app init + router includes (~30 dòng)
- [ ] `routers/` có 5 files: documents, extraction, translation, compilation, volume
- [ ] `VolumeDetector` service hoạt động với tier S/M/L/XL
- [ ] `GET /api/docs/{id}/volume` endpoint hoạt động
- [ ] Upload tự động detect volume và lưu vào DB
- [ ] Tất cả existing tests vẫn PASS

**Tiếp theo:** Phase 2 — asyncio S/M pipeline, SSE progress, translate-all endpoint, Quality Tier Engine.
