# SP2 SaaS Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm local JWT auth, multi-tenant isolation, quota enforcement, và Next.js 14 Minimal Light frontend vào Break The Barriers — 61 existing tests vẫn pass sau khi hoàn tất.

**Architecture:** Backend FastAPI giữ nguyên, thêm `users`/`subscriptions` tables + `user_id` trên `documents`. Auth dùng `python-jose` + `passlib`. Tất cả existing endpoints dùng optional auth (backward compat). Next.js 14 App Router frontend mới tại `apps/break_the_barriers/frontend/`.

**Tech Stack:** Python python-jose[cryptography], passlib[bcrypt], Next.js 14, TypeScript, Tailwind CSS, lucide-react

---

## File Map

| File | Action | Mô tả |
|------|--------|-------|
| `backend/requirements.txt` | MODIFY | Thêm python-jose, passlib |
| `backend/app/models_db.py` | MODIFY | Thêm DBUser, DBSubscription; thêm user_id/is_public vào DBDocument |
| `backend/app/models.py` | MODIFY | Thêm UserRegister, UserLogin, TokenResponse, UserInfo |
| `backend/app/services/auth_service.py` | CREATE | hash_password, verify_password, create_access_token, decode_token |
| `backend/app/dependencies.py` | CREATE | get_optional_user, get_current_user FastAPI dependencies |
| `backend/app/routers/auth.py` | CREATE | POST /register, POST /login, GET /me |
| `backend/app/main.py` | MODIFY | include auth router |
| `backend/app/routers/documents.py` | MODIFY | optional user + quota check on upload |
| `backend/app/routers/extraction.py` | MODIFY | quota consumption after extract |
| `backend/scripts/migrate_sp2.sql` | CREATE | SQL migration cho existing PostgreSQL DB |
| `backend/tests/test_api.py` | MODIFY | Thêm auth tests (register, login, quota) |
| `frontend/` | CREATE | Toàn bộ Next.js 14 project |
| `frontend/app/(auth)/login/page.tsx` | CREATE | Login page — Card Centered |
| `frontend/app/(auth)/register/page.tsx` | CREATE | Register page |
| `frontend/app/dashboard/page.tsx` | CREATE | Dashboard — book list, upload, quota bar |
| `frontend/app/books/[id]/page.tsx` | CREATE | Book detail — pipeline stepper, SSE progress |
| `frontend/app/pricing/page.tsx` | CREATE | 3 Plans cards, Coming Soon modal |
| `frontend/lib/auth.ts` | CREATE | setToken, getToken, logout, isLoggedIn |
| `frontend/lib/api.ts` | CREATE | fetchAPI với auto JWT header |
| `frontend/middleware.ts` | CREATE | Route protection cho /dashboard, /books/* |

---

## Task 1: Backend dependencies

**Files:**
- Modify: `apps/break_the_barriers/backend/requirements.txt`

- [ ] **Step 1: Thêm python-jose và passlib vào requirements.txt**

Nội dung mới của file:
```
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
celery[redis]>=5.3.0
redis>=5.0.0
docling>=2.0.0
ebooklib>=0.18
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
```

- [ ] **Step 2: Install**

```bash
cd apps/break_the_barriers/backend
.venv/bin/pip install python-jose[cryptography] passlib[bcrypt]
```
Expected: Successfully installed python-jose-X.X.X passlib-X.X.X bcrypt-X.X.X

- [ ] **Step 3: Verify import**

```bash
.venv/bin/python3 -c "from jose import jwt; from passlib.context import CryptContext; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add apps/break_the_barriers/backend/requirements.txt
git commit -m "feat(SP2): add python-jose and passlib dependencies"
```

---

## Task 2: Database models — DBUser, DBSubscription, DBDocument changes

**Files:**
- Modify: `apps/break_the_barriers/backend/app/models_db.py`

- [ ] **Step 1: Thêm DBUser, DBSubscription vào models_db.py và thêm user_id/is_public vào DBDocument**

Thêm `Boolean` vào imports và sau đó append toàn bộ file:

```python
# Thêm vào dòng import đầu:
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float, Boolean
# (Boolean đã thêm)

# Thêm user_id và is_public vào class DBDocument (sau estimated_duration_min):
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=False)
    user = relationship("DBUser", back_populates="documents")

# Thêm 2 class mới vào cuối file:

class DBUser(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, default="")
    plan = Column(String, default="free")
    pages_used_this_month = Column(Integer, default=0)
    pages_limit = Column(Integer, default=20)
    pages_reset_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    documents = relationship("DBDocument", back_populates="user", lazy="dynamic")
    subscriptions = relationship("DBSubscription", back_populates="user", cascade="all, delete-orphan")


class DBSubscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    status = Column(String, default="active")
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("DBUser", back_populates="subscriptions")
```

File đầy đủ sau khi sửa:

```python
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float, Boolean
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

    volume_tier = Column(String, nullable=True)
    quality_tier = Column(String, default="high")
    estimated_cost_usd = Column(Float, nullable=True)
    estimated_duration_min = Column(Integer, nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=False)

    pages = relationship("DBPage", back_populates="document", cascade="all, delete-orphan")
    translations = relationship("DBTranslation", back_populates="document", cascade="all, delete-orphan")
    jobs = relationship("DBJob", back_populates="document", cascade="all, delete-orphan")
    user = relationship("DBUser", back_populates="documents")


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


class DBUser(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, default="")
    plan = Column(String, default="free")
    pages_used_this_month = Column(Integer, default=0)
    pages_limit = Column(Integer, default=20)
    pages_reset_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    documents = relationship("DBDocument", back_populates="user", lazy="dynamic")
    subscriptions = relationship("DBSubscription", back_populates="user", cascade="all, delete-orphan")


class DBSubscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    status = Column(String, default="active")
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("DBUser", back_populates="subscriptions")
```

- [ ] **Step 2: Verify existing tests vẫn pass sau thay đổi models**

```bash
cd apps/break_the_barriers/backend
.venv/bin/pytest tests/ -q 2>&1 | tail -4
```
Expected: `61 passed`

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/backend/app/models_db.py
git commit -m "feat(SP2): add DBUser, DBSubscription models; add user_id/is_public to DBDocument"
```

---

## Task 3: Pydantic auth models

**Files:**
- Modify: `apps/break_the_barriers/backend/app/models.py`

- [ ] **Step 1: Thêm auth Pydantic models vào cuối models.py**

```python
# Thêm vào cuối apps/break_the_barriers/backend/app/models.py:

class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str = ""

class UserLogin(BaseModel):
    email: str
    password: str

class UserInfo(BaseModel):
    id: str
    email: str
    full_name: str
    plan: str
    pages_limit: int
    pages_used_this_month: int

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
```

- [ ] **Step 2: Verify import**

```bash
cd apps/break_the_barriers/backend
.venv/bin/python3 -c "from backend.app.models import UserRegister, UserLogin, TokenResponse, UserInfo; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/backend/app/models.py
git commit -m "feat(SP2): add auth Pydantic models — UserRegister, UserLogin, TokenResponse, UserInfo"
```

---

## Task 4: auth_service.py

**Files:**
- Create: `apps/break_the_barriers/backend/app/services/auth_service.py`
- Test: `apps/break_the_barriers/backend/tests/test_services.py`

- [ ] **Step 1: Viết failing tests**

Thêm vào cuối `apps/break_the_barriers/backend/tests/test_services.py`:

```python
# -------------------------------------------------------------
# AuthService Tests
# -------------------------------------------------------------

def test_hash_and_verify_password():
    from backend.app.services.auth_service import hash_password, verify_password
    hashed = hash_password("mypassword123")
    assert hashed != "mypassword123"
    assert verify_password("mypassword123", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_create_and_decode_token():
    from backend.app.services.auth_service import create_access_token, decode_token
    token = create_access_token("user-123", "test@example.com", "free")
    assert isinstance(token, str)
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@example.com"
    assert payload["plan"] == "free"


def test_decode_invalid_token():
    from backend.app.services.auth_service import decode_token
    try:
        decode_token("not.a.valid.token")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid" in str(e)
```

- [ ] **Step 2: Chạy để confirm FAIL**

```bash
cd apps/break_the_barriers/backend
.venv/bin/pytest tests/test_services.py::test_hash_and_verify_password -v 2>&1 | tail -5
```
Expected: `FAILED` — ModuleNotFoundError

- [ ] **Step 3: Tạo auth_service.py**

```python
# apps/break_the_barriers/backend/app/services/auth_service.py
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, email: str, plan: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": user_id, "email": email, "plan": plan, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Invalid or expired token: {e}")
```

- [ ] **Step 4: Chạy 3 tests mới — confirm PASS**

```bash
.venv/bin/pytest tests/test_services.py::test_hash_and_verify_password tests/test_services.py::test_create_and_decode_token tests/test_services.py::test_decode_invalid_token -v 2>&1 | tail -8
```
Expected: `3 passed`

- [ ] **Step 5: Full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```
Expected: `64 passed`

- [ ] **Step 6: Commit**

```bash
git add apps/break_the_barriers/backend/app/services/auth_service.py \
        apps/break_the_barriers/backend/tests/test_services.py
git commit -m "feat(SP2): add auth_service — JWT create/decode, bcrypt hash/verify"
```

---

## Task 5: Auth dependencies

**Files:**
- Create: `apps/break_the_barriers/backend/app/dependencies.py`

- [ ] **Step 1: Tạo dependencies.py**

```python
# apps/break_the_barriers/backend/app/dependencies.py
from typing import Optional

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models_db import DBUser
from backend.app.services.auth_service import decode_token


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[DBUser]:
    """Return DBUser if valid Bearer token present, else None (backward compat)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    return db.query(DBUser).filter(DBUser.id == payload["sub"]).first()


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> DBUser:
    """Return DBUser or raise 401. Use on protected endpoints."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(DBUser).filter(DBUser.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
```

- [ ] **Step 2: Verify import**

```bash
cd apps/break_the_barriers/backend
.venv/bin/python3 -c "from backend.app.dependencies import get_optional_user, get_current_user; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/backend/app/dependencies.py
git commit -m "feat(SP2): add auth dependencies — get_optional_user, get_current_user"
```

---

## Task 6: Auth router

**Files:**
- Create: `apps/break_the_barriers/backend/app/routers/auth.py`
- Test: `apps/break_the_barriers/backend/tests/test_api.py`

- [ ] **Step 1: Viết failing tests — thêm vào cuối test_api.py**

```python
# Thêm vào cuối apps/break_the_barriers/backend/tests/test_api.py

# -------------------------------------------------------------
# Auth Tests (SP2)
# -------------------------------------------------------------

def test_register_user(client):
    response = client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["plan"] == "free"
    assert data["user"]["pages_limit"] == 20


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "pass123", "full_name": "A"}
    client.post("/api/auth/register", json=payload)
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_login_user(client):
    client.post("/api/auth/register", json={
        "email": "login@example.com", "password": "mypassword", "full_name": "Login User"
    })
    response = client.post("/api/auth/login", json={
        "email": "login@example.com", "password": "mypassword"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "email": "wp@example.com", "password": "correct", "full_name": "WP"
    })
    response = client.post("/api/auth/login", json={
        "email": "wp@example.com", "password": "wrong"
    })
    assert response.status_code == 401


def test_get_me(client):
    reg = client.post("/api/auth/register", json={
        "email": "me@example.com", "password": "pass123", "full_name": "Me"
    })
    token = reg.json()["access_token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_get_me_no_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
```

- [ ] **Step 2: Chạy để confirm FAIL**

```bash
cd apps/break_the_barriers/backend
.venv/bin/pytest tests/test_api.py::test_register_user -v 2>&1 | tail -5
```
Expected: `FAILED` — 404 Not Found (route doesn't exist yet)

- [ ] **Step 3: Tạo auth router**

```python
# apps/break_the_barriers/backend/app/routers/auth.py
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies import get_current_user
from backend.app.models import UserRegister, UserLogin, TokenResponse, UserInfo
from backend.app.models_db import DBUser
from backend.app.services.auth_service import hash_password, verify_password, create_access_token

router = APIRouter()

PLAN_LIMITS = {"free": 20, "pro": 500, "enterprise": 2000}


def _user_info(user: DBUser) -> UserInfo:
    return UserInfo(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan=user.plan,
        pages_limit=user.pages_limit,
        pages_used_this_month=user.pages_used_this_month,
    )


@router.post("/api/auth/register", response_model=TokenResponse)
def register(body: UserRegister, db: Session = Depends(get_db)):
    if db.query(DBUser).filter(DBUser.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = DBUser(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(access_token=token, user=_user_info(user))


@router.post("/api/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # Reset quota if new calendar month
    now = datetime.now(timezone.utc)
    reset_at = user.pages_reset_at
    if reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)
    if reset_at.year != now.year or reset_at.month != now.month:
        user.pages_used_this_month = 0
        user.pages_reset_at = now
        db.commit()
        db.refresh(user)
    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(access_token=token, user=_user_info(user))


@router.get("/api/auth/me", response_model=UserInfo)
def me(current_user: DBUser = Depends(get_current_user)):
    return _user_info(current_user)
```

- [ ] **Step 4: Chạy 6 auth tests — confirm PASS (router belum di-wire, jadi masih 404)**

Dừng lại — auth router cần wire vào `main.py` trước. Đây là lý do Task 6 và Task 7 phải làm liên tiếp ngay bên dưới.

---

## Task 7: Wire auth router vào main.py

**Files:**
- Modify: `apps/break_the_barriers/backend/app/main.py`

- [ ] **Step 1: Sửa main.py — thêm auth router**

Thay nội dung `main.py`:
```python
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.database import engine, Base, get_db, SessionLocal
from backend.app.models_db import DBDocument
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs
from backend.app.routers import auth

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Smart Documentations API",
    description="API-First Backend for Digitizing and High-Fidelity Translation of PDF books",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(extraction.router)
app.include_router(translation.router)
app.include_router(compilation.router)
app.include_router(volume.router)
app.include_router(jobs.router)
app.include_router(auth.router)


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

- [ ] **Step 2: Chạy 6 auth tests — confirm PASS**

```bash
cd apps/break_the_barriers/backend
.venv/bin/pytest tests/test_api.py::test_register_user tests/test_api.py::test_register_duplicate_email tests/test_api.py::test_login_user tests/test_api.py::test_login_wrong_password tests/test_api.py::test_get_me tests/test_api.py::test_get_me_no_token -v 2>&1 | tail -12
```
Expected: `6 passed`

- [ ] **Step 3: Full suite — backward compat check**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```
Expected: `67 passed` (61 cũ + 3 auth_service + 6 auth API = 70... nhưng thực tế số có thể khác tùy đếm)  
**Quan trọng: tất cả test cũ PHẢI pass, không được có regression.**

- [ ] **Step 4: Commit**

```bash
git add apps/break_the_barriers/backend/app/main.py \
        apps/break_the_barriers/backend/app/routers/auth.py \
        apps/break_the_barriers/backend/tests/test_api.py
git commit -m "feat(SP2): add auth router — register, login, me endpoints"
```

---

## Task 8: Quota enforcement + upload với auth

**Files:**
- Modify: `apps/break_the_barriers/backend/app/routers/documents.py`
- Test: `apps/break_the_barriers/backend/tests/test_api.py`

- [ ] **Step 1: Viết failing quota tests — thêm vào cuối test_api.py**

```python
def test_upload_with_auth_sets_user_id(client, db_session):
    from backend.app.models_db import DBDocument
    # Register + login
    reg = client.post("/api/auth/register", json={
        "email": "uploader@example.com", "password": "pass123", "full_name": "U"
    })
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]
    # Upload
    files = {"file": ("auth_book.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    doc = db_session.query(DBDocument).filter_by(id="auth_book").first()
    assert doc.user_id == user_id


def test_upload_without_auth_still_works(client):
    files = {"file": ("noauth_book.pdf", b"%PDF-1.4 mock", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files)
    assert resp.status_code == 200


def test_quota_exceeded(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "quota@example.com", "password": "pass123", "full_name": "Q"
    })
    token = reg.json()["access_token"]
    # Set pages_used to limit
    user = db_session.query(DBUser).filter_by(email="quota@example.com").first()
    user.pages_used_this_month = user.pages_limit  # free = 20
    db_session.commit()
    # Upload should be rejected
    files = {"file": ("over_quota.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 402
    assert "Quota" in resp.json()["detail"]
```

- [ ] **Step 2: Confirm FAIL**

```bash
cd apps/break_the_barriers/backend
.venv/bin/pytest tests/test_api.py::test_quota_exceeded -v 2>&1 | tail -5
```
Expected: `FAILED` — 200 instead of 402

- [ ] **Step 3: Sửa upload endpoint trong documents.py**

Import thêm vào đầu `documents.py`:
```python
from typing import Optional
from backend.app.dependencies import get_optional_user
from backend.app.models_db import DBUser
```

Sửa chữ ký `upload_document`:
```python
@router.post("/api/docs/upload", response_model=DocumentMetadata)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[DBUser] = Depends(get_optional_user),
):
```

Sau khi tính `estimated_pages` và trước khi tạo doc, thêm quota check:
```python
    # Quota check (only when authenticated)
    if current_user is not None:
        if current_user.pages_used_this_month + estimated_pages > current_user.pages_limit:
            raise HTTPException(
                status_code=402,
                detail=f"Quota exceeded ({current_user.pages_used_this_month}/{current_user.pages_limit} pages used). Please upgrade your plan."
            )
```

Sau `db.add(doc)` / `doc.total_pages = estimated_pages`, thêm user_id:
```python
    # Link document to authenticated user
    if current_user is not None:
        doc.user_id = current_user.id
        current_user.pages_used_this_month += estimated_pages
```

Đoạn `db.commit(); db.refresh(doc)` giữ nguyên.

File upload endpoint đầy đủ sau khi sửa:
```python
@router.post("/api/docs/upload", response_model=DocumentMetadata)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[DBUser] = Depends(get_optional_user),
):
    is_epub = file.filename.lower().endswith(".epub")
    is_pdf = file.filename.lower().endswith(".pdf")
    if not (is_pdf or is_epub):
        raise HTTPException(status_code=400, detail="Only PDF or EPUB files are supported")

    ext = ".epub" if is_epub else ".pdf"
    doc_id = os.path.splitext(file.filename)[0].lower().replace(" ", "_")
    file_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}{ext}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    if is_epub:
        estimated_pages = _estimate_epub_chapters(content)
    else:
        matches = re.findall(rb"/Count\s+(\d+)", content)
        estimated_pages = 10
        if matches:
            try:
                estimated_pages = max(int(m) for m in matches)
            except ValueError:
                pass

    # Quota check (only when authenticated)
    if current_user is not None:
        if current_user.pages_used_this_month + estimated_pages > current_user.pages_limit:
            raise HTTPException(
                status_code=402,
                detail=f"Quota exceeded ({current_user.pages_used_this_month}/{current_user.pages_limit} pages used). Please upgrade your plan."
            )

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

    # Link document to authenticated user
    if current_user is not None:
        doc.user_id = current_user.id
        current_user.pages_used_this_month += estimated_pages

    db.commit()
    db.refresh(doc)

    return DocumentMetadata(
        id=doc.id, filename=doc.filename, total_pages=doc.total_pages,
        status=doc.status, created_at=doc.created_at.isoformat()
    )
```

- [ ] **Step 4: Chạy 3 quota tests — confirm PASS**

```bash
.venv/bin/pytest tests/test_api.py::test_upload_with_auth_sets_user_id tests/test_api.py::test_upload_without_auth_still_works tests/test_api.py::test_quota_exceeded -v 2>&1 | tail -8
```
Expected: `3 passed`

- [ ] **Step 5: Full suite — no regression**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```
Expected: tất cả pass, không có regression

- [ ] **Step 6: Commit**

```bash
git add apps/break_the_barriers/backend/app/routers/documents.py \
        apps/break_the_barriers/backend/tests/test_api.py
git commit -m "feat(SP2): quota enforcement on upload, link documents to authenticated users"
```

---

## Task 9: SQL migration script cho existing PostgreSQL DB

**Files:**
- Create: `apps/break_the_barriers/backend/scripts/migrate_sp2.sql`

- [ ] **Step 1: Tạo migration script**

```sql
-- apps/break_the_barriers/backend/scripts/migrate_sp2.sql
-- Run against existing PostgreSQL DB: psql -d break_the_barriers -f migrate_sp2.sql

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    full_name VARCHAR DEFAULT '',
    plan VARCHAR DEFAULT 'free',
    pages_used_this_month INTEGER DEFAULT 0,
    pages_limit INTEGER DEFAULT 20,
    pages_reset_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS subscriptions (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR UNIQUE,
    status VARCHAR DEFAULT 'active',
    current_period_end TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE;
```

- [ ] **Step 2: Chạy migration trên local PostgreSQL**

```bash
psql -d break_the_barriers -f apps/break_the_barriers/backend/scripts/migrate_sp2.sql
```
Expected: `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE` (không có ERROR)

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/backend/scripts/migrate_sp2.sql
git commit -m "feat(SP2): add PostgreSQL migration script for users, subscriptions tables"
```

---

## Task 10: Next.js project setup

**Files:**
- Create: `apps/break_the_barriers/frontend/` (toàn bộ)

**Prerequisite:** Node.js 18+ phải được cài. Kiểm tra: `node --version`

- [ ] **Step 1: Tạo Next.js project**

```bash
cd apps/break_the_barriers
npx create-next-app@14 frontend --typescript --tailwind --app --no-src-dir --import-alias "@/*" --eslint
```

Khi được hỏi:
- Would you like to use `src/` directory? → **No**
- Would you like to use App Router? → **Yes**

- [ ] **Step 2: Cài thêm lucide-react**

```bash
cd frontend
npm install lucide-react
```

- [ ] **Step 3: Tạo `.env.local`**

```bash
# apps/break_the_barriers/frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 4: Xóa boilerplate từ create-next-app**

Xóa nội dung mặc định trong `app/page.tsx`, thay bằng redirect:
```typescript
// apps/break_the_barriers/frontend/app/page.tsx
import { redirect } from "next/navigation"

export default function Home() {
  redirect("/dashboard")
}
```

Xóa `app/globals.css` content mặc định (giữ lại Tailwind directives):
```css
/* apps/break_the_barriers/frontend/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 5: Verify Next.js starts**

```bash
cd apps/break_the_barriers/frontend
npm run dev
```
Expected: `ready started server on 0.0.0.0:3000` (hoặc port 3000)  
Mở `http://localhost:3000` → redirect đến `/dashboard` (sẽ 404 vì chưa có page, nhưng redirect xảy ra)

- [ ] **Step 6: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/frontend/
git commit -m "feat(SP2): scaffold Next.js 14 frontend with TypeScript, Tailwind"
```

---

## Task 11: lib/auth.ts + lib/api.ts

**Files:**
- Create: `apps/break_the_barriers/frontend/lib/auth.ts`
- Create: `apps/break_the_barriers/frontend/lib/api.ts`

- [ ] **Step 1: Tạo lib/auth.ts**

```typescript
// apps/break_the_barriers/frontend/lib/auth.ts
const TOKEN_KEY = "btb_token"
const COOKIE_MAX_AGE = 7 * 24 * 60 * 60  // 7 days in seconds

export interface UserInfo {
  id: string
  email: string
  full_name: string
  plan: string
  pages_limit: number
  pages_used_this_month: number
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return
  localStorage.setItem(TOKEN_KEY, token)
  document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(TOKEN_KEY)
}

export function logout(): void {
  if (typeof window === "undefined") return
  localStorage.removeItem(TOKEN_KEY)
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`
}

export function isLoggedIn(): boolean {
  return !!getToken()
}

export function saveUser(user: UserInfo): void {
  if (typeof window === "undefined") return
  localStorage.setItem("btb_user", JSON.stringify(user))
}

export function getUser(): UserInfo | null {
  if (typeof window === "undefined") return null
  const raw = localStorage.getItem("btb_user")
  return raw ? JSON.parse(raw) : null
}
```

- [ ] **Step 2: Tạo lib/api.ts**

```typescript
// apps/break_the_barriers/frontend/lib/api.ts
import { getToken, logout } from "./auth"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export async function fetchAPI<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    ...(options.body && !(options.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> ?? {}),
  }

  const res = await fetch(API_URL + path, { ...options, headers })

  if (res.status === 401) {
    logout()
    if (typeof window !== "undefined") window.location.href = "/login"
    throw new ApiError(401, "Not authenticated")
  }
  if (res.status === 402) {
    if (typeof window !== "undefined") window.location.href = "/pricing?reason=quota"
    throw new ApiError(402, "Quota exceeded")
  }
  if (!res.ok) {
    const text = await res.text()
    throw new ApiError(res.status, text)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}
```

- [ ] **Step 3: Verify TypeScript compile**

```bash
cd apps/break_the_barriers/frontend
npx tsc --noEmit 2>&1 | head -10
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add apps/break_the_barriers/frontend/lib/
git commit -m "feat(SP2): add auth.ts and api.ts client libraries"
```

---

## Task 12: Root layout + middleware route protection

**Files:**
- Modify: `apps/break_the_barriers/frontend/app/layout.tsx`
- Create: `apps/break_the_barriers/frontend/middleware.ts`

- [ ] **Step 1: Tạo middleware.ts**

```typescript
// apps/break_the_barriers/frontend/middleware.ts
import { NextRequest, NextResponse } from "next/server"

const PROTECTED = ["/dashboard", "/books"]

export function middleware(request: NextRequest) {
  const token = request.cookies.get("btb_token")
  const { pathname } = request.nextUrl

  const isProtected = PROTECTED.some((p) => pathname.startsWith(p))
  if (isProtected && !token) {
    return NextResponse.redirect(new URL("/login", request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ["/dashboard/:path*", "/books/:path*"],
}
```

- [ ] **Step 2: Sửa app/layout.tsx — root layout với font và global styles**

```typescript
// apps/break_the_barriers/frontend/app/layout.tsx
import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "Break The Barriers",
  description: "AI-powered bilingual book translation",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/frontend/middleware.ts \
        apps/break_the_barriers/frontend/app/layout.tsx \
        apps/break_the_barriers/frontend/app/globals.css \
        apps/break_the_barriers/frontend/app/page.tsx
git commit -m "feat(SP2): add route protection middleware and root layout"
```

---

## Task 13: Login + Register pages

**Files:**
- Create: `apps/break_the_barriers/frontend/app/(auth)/login/page.tsx`
- Create: `apps/break_the_barriers/frontend/app/(auth)/register/page.tsx`
- Create: `apps/break_the_barriers/frontend/app/(auth)/layout.tsx`

- [ ] **Step 1: Tạo (auth) group layout**

```typescript
// apps/break_the_barriers/frontend/app/(auth)/layout.tsx
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      {children}
    </div>
  )
}
```

- [ ] **Step 2: Tạo login page**

```typescript
// apps/break_the_barriers/frontend/app/(auth)/login/page.tsx
"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { fetchAPI } from "@/lib/api"
import { setToken, saveUser, UserInfo } from "@/lib/auth"

interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const data = await fetchAPI<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      })
      setToken(data.access_token)
      saveUser(data.user)
      router.push("/dashboard")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full max-w-sm bg-white rounded-lg shadow p-8">
      <div className="text-center mb-6">
        <h1 className="text-xl font-bold text-indigo-600">Break The Barriers</h1>
        <p className="text-sm text-gray-500 mt-1">Đăng nhập tài khoản</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Mật khẩu</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 text-white py-2 rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>
      <p className="text-center text-sm text-gray-500 mt-4">
        Chưa có tài khoản?{" "}
        <Link href="/register" className="text-indigo-600 hover:underline">
          Đăng ký miễn phí
        </Link>
      </p>
    </div>
  )
}
```

- [ ] **Step 3: Tạo register page**

```typescript
// apps/break_the_barriers/frontend/app/(auth)/register/page.tsx
"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { fetchAPI } from "@/lib/api"
import { setToken, saveUser, UserInfo } from "@/lib/auth"

interface RegisterResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export default function RegisterPage() {
  const router = useRouter()
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const data = await fetchAPI<RegisterResponse>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName }),
      })
      setToken(data.access_token)
      saveUser(data.user)
      router.push("/dashboard")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng ký thất bại")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full max-w-sm bg-white rounded-lg shadow p-8">
      <div className="text-center mb-6">
        <h1 className="text-xl font-bold text-indigo-600">Break The Barriers</h1>
        <p className="text-sm text-gray-500 mt-1">Tạo tài khoản miễn phí</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Họ tên</label>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Nguyễn Văn A"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Mật khẩu</label>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Tối thiểu 6 ký tự"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 text-white py-2 rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Đang đăng ký..." : "Đăng ký"}
        </button>
      </form>
      <p className="text-center text-sm text-gray-500 mt-4">
        Đã có tài khoản?{" "}
        <Link href="/login" className="text-indigo-600 hover:underline">
          Đăng nhập
        </Link>
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Verify TypeScript compile**

```bash
cd apps/break_the_barriers/frontend
npx tsc --noEmit 2>&1 | head -10
```
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add apps/break_the_barriers/frontend/app/
git commit -m "feat(SP2): add login and register pages — Card Centered design"
```

---

## Task 14: Dashboard page

**Files:**
- Create: `apps/break_the_barriers/frontend/app/dashboard/page.tsx`

- [ ] **Step 1: Tạo dashboard page**

```typescript
// apps/break_the_barriers/frontend/app/dashboard/page.tsx
"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Upload, Trash2, Eye, LogOut } from "lucide-react"
import { fetchAPI, ApiError } from "@/lib/api"
import { getUser, logout, UserInfo } from "@/lib/auth"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
  created_at: string
}

const STATUS_LABEL: Record<string, string> = {
  raw: "Chưa xử lý",
  extracting: "Đang extract",
  extracted: "Đã extract",
  translating: "Đang dịch",
  translated: "Đã dịch",
  compiled: "Hoàn tất",
  failed: "Lỗi",
}

const STATUS_COLOR: Record<string, string> = {
  raw: "bg-gray-100 text-gray-600",
  extracting: "bg-blue-100 text-blue-700",
  extracted: "bg-blue-100 text-blue-700",
  translating: "bg-yellow-100 text-yellow-700",
  translated: "bg-green-100 text-green-700",
  compiled: "bg-purple-100 text-purple-700",
  failed: "bg-red-100 text-red-600",
}

export default function DashboardPage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [docs, setDocs] = useState<Doc[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setUser(getUser())
    loadDocs()
  }, [])

  async function loadDocs() {
    try {
      const data = await fetchAPI<Doc[]>("/api/docs")
      setDocs(data)
    } catch {
      // ignore, token refresh handled by fetchAPI
    }
  }

  async function handleUpload(file: File) {
    setError("")
    setUploading(true)
    const form = new FormData()
    form.append("file", file)
    try {
      await fetchAPI("/api/docs/upload", { method: "POST", body: form })
      await loadDocs()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 402) return
      setError(err instanceof Error ? err.message : "Upload thất bại")
    } finally {
      setUploading(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm(`Xoá "${id}"?`)) return
    await fetchAPI(`/api/docs/${id}`, { method: "DELETE" })
    setDocs((prev) => prev.filter((d) => d.id !== id))
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  function handleLogout() {
    logout()
    router.push("/login")
  }

  const quotaPercent = user
    ? Math.min(100, Math.round((user.pages_used_this_month / user.pages_limit) * 100))
    : 0

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <span className="text-indigo-600 font-bold">Break The Barriers</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">{user?.email}</span>
          <button
            onClick={handleLogout}
            className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
          >
            <LogOut size={14} /> Đăng xuất
          </button>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {/* Quota bar */}
        {user && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-600">
                Quota tháng này: <strong>{user.pages_used_this_month}</strong>/{user.pages_limit} trang
              </span>
              <span className="text-xs text-gray-400 capitalize">{user.plan} plan</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${quotaPercent >= 90 ? "bg-red-500" : "bg-indigo-500"}`}
                style={{ width: `${quotaPercent}%` }}
              />
            </div>
            {quotaPercent >= 90 && (
              <p className="text-xs text-red-500 mt-1">
                Gần hết quota —{" "}
                <a href="/pricing" className="underline">Nâng cấp Pro</a>
              </p>
            )}
          </div>
        )}

        {/* Upload zone */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50 transition-colors"
        >
          <Upload className="mx-auto mb-2 text-gray-400" size={28} />
          <p className="text-sm text-gray-500">
            {uploading ? "Đang tải lên..." : "Kéo thả hoặc click để upload PDF/EPUB"}
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.epub"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {/* Book list */}
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex justify-between items-center">
            <h2 className="font-semibold text-gray-800">Thư viện của tôi</h2>
            <span className="text-xs text-gray-400">{docs.length} cuốn</span>
          </div>
          {docs.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-10">
              Chưa có sách. Upload PDF hoặc EPUB để bắt đầu.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Tên file</th>
                  <th className="text-left px-4 py-2">Trạng thái</th>
                  <th className="text-left px-4 py-2">Trang</th>
                  <th className="text-left px-4 py-2">Ngày tạo</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-800 truncate max-w-[200px]">
                      {doc.filename}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_COLOR[doc.status] ?? "bg-gray-100 text-gray-600"}`}>
                        {STATUS_LABEL[doc.status] ?? doc.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">{doc.total_pages}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {new Date(doc.created_at).toLocaleDateString("vi-VN")}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => router.push(`/books/${doc.id}`)}
                          className="text-indigo-600 hover:text-indigo-800"
                          title="Xem chi tiết"
                        >
                          <Eye size={15} />
                        </button>
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="text-red-400 hover:text-red-600"
                          title="Xoá"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compile**

```bash
cd apps/break_the_barriers/frontend
npx tsc --noEmit 2>&1 | head -10
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/frontend/app/dashboard/
git commit -m "feat(SP2): add dashboard page — book list, upload zone, quota bar"
```

---

## Task 15: Book detail page

**Files:**
- Create: `apps/break_the_barriers/frontend/app/books/[id]/page.tsx`

- [ ] **Step 1: Tạo book detail page**

```typescript
// apps/break_the_barriers/frontend/app/books/[id]/page.tsx
"use client"

import { useEffect, useRef, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, Play, RotateCcw, CheckCircle, Circle, Loader } from "lucide-react"
import { fetchAPI } from "@/lib/api"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
  created_at: string
  volume_tier?: string
  quality_tier?: string
  estimated_cost_usd?: number
}

interface ProgressEvent {
  page: number
  total: number
  status: string
  percent: number
  eta_min: number
}

const PIPELINE_STEPS = ["raw", "extracted", "translated", "compiled"]
const STEP_LABEL: Record<string, string> = {
  raw: "Upload",
  extracted: "Extract",
  translated: "Dịch",
  compiled: "Hoàn tất",
}

function stepIndex(status: string): number {
  const idx = PIPELINE_STEPS.indexOf(status)
  return idx === -1 ? 0 : idx
}

export default function BookDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [doc, setDoc] = useState<Doc | null>(null)
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState("")
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    loadDoc()
    return () => esRef.current?.close()
  }, [id])

  async function loadDoc() {
    try {
      const docs = await fetchAPI<Doc[]>("/api/docs")
      setDoc(docs.find((d) => d.id === id) ?? null)
    } catch { /* handled by fetchAPI */ }
  }

  async function handleExtract() {
    setError("")
    try {
      await fetchAPI(`/api/docs/${id}/extract`, { method: "POST" })
      await loadDoc()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Extract thất bại")
    }
  }

  async function handleResume() {
    setError("")
    try {
      await fetchAPI(`/api/docs/${id}/resume`, { method: "POST" })
      startSSE()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Resume thất bại")
    }
  }

  function startSSE() {
    esRef.current?.close()
    setStreaming(true)
    setProgress(null)
    const token = typeof window !== "undefined" ? localStorage.getItem("btb_token") : null
    const url = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/docs/${id}/progress`
    const es = new EventSource(url + (token ? `?token=${token}` : ""))
    esRef.current = es
    es.onmessage = (e) => {
      const evt: ProgressEvent = JSON.parse(e.data)
      setProgress(evt)
      if (evt.percent >= 100) {
        setStreaming(false)
        es.close()
        loadDoc()
      }
    }
    es.onerror = () => { setStreaming(false); es.close() }
  }

  async function handleTranslateAll() {
    setError("")
    try {
      await fetchAPI(`/api/docs/${id}/translate-all`, {
        method: "POST",
        body: JSON.stringify({ target_lang: "vi" }),
      })
      startSSE()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Translate thất bại")
    }
  }

  if (!doc) return <div className="p-8 text-gray-400">Đang tải...</div>

  const currentStep = stepIndex(doc.status)

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3">
        <button onClick={() => router.push("/dashboard")} className="text-gray-500 hover:text-gray-700">
          <ArrowLeft size={18} />
        </button>
        <span className="font-semibold text-gray-800 truncate">{doc.filename}</span>
      </header>

      <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {/* Metadata */}
        <div className="bg-white border border-gray-200 rounded-lg p-4 grid grid-cols-3 gap-4 text-sm">
          <div><span className="text-gray-400 block text-xs">Số trang</span>{doc.total_pages}</div>
          <div><span className="text-gray-400 block text-xs">Volume tier</span>{doc.volume_tier ?? "—"}</div>
          <div><span className="text-gray-400 block text-xs">Chi phí ước tính</span>
            {doc.estimated_cost_usd != null ? `$${doc.estimated_cost_usd.toFixed(3)}` : "—"}
          </div>
        </div>

        {/* Pipeline stepper */}
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Pipeline</h2>
          <div className="flex items-center gap-0">
            {PIPELINE_STEPS.map((step, i) => {
              const done = i < currentStep
              const active = i === currentStep
              return (
                <div key={step} className="flex items-center flex-1 last:flex-none">
                  <div className={`flex flex-col items-center gap-1 ${active ? "text-indigo-600" : done ? "text-green-600" : "text-gray-300"}`}>
                    {done ? <CheckCircle size={20} /> : active ? <Loader size={20} className="animate-spin" /> : <Circle size={20} />}
                    <span className="text-xs font-medium">{STEP_LABEL[step]}</span>
                  </div>
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div className={`h-0.5 flex-1 mx-1 ${i < currentStep ? "bg-green-400" : "bg-gray-200"}`} />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* SSE Progress */}
        {streaming && progress && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>Trang {progress.page}/{progress.total}</span>
              <span>{progress.percent}% — còn {progress.eta_min} phút</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div className="bg-indigo-500 h-2 rounded-full transition-all" style={{ width: `${progress.percent}%` }} />
            </div>
          </div>
        )}

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {/* Actions */}
        <div className="flex gap-3 flex-wrap">
          {doc.status === "raw" && (
            <button onClick={handleExtract}
              className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded text-sm hover:bg-indigo-700">
              <Play size={14} /> Extract
            </button>
          )}
          {doc.status === "extracted" && (
            <button onClick={handleTranslateAll}
              className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded text-sm hover:bg-indigo-700">
              <Play size={14} /> Dịch tất cả
            </button>
          )}
          {(doc.status === "translating" || doc.status === "failed") && (
            <button onClick={handleResume}
              className="flex items-center gap-2 border border-indigo-600 text-indigo-600 px-4 py-2 rounded text-sm hover:bg-indigo-50">
              <RotateCcw size={14} /> Resume
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compile**

```bash
cd apps/break_the_barriers/frontend
npx tsc --noEmit 2>&1 | head -10
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/frontend/app/books/
git commit -m "feat(SP2): add book detail page — pipeline stepper, SSE progress, actions"
```

---

## Task 16: Pricing page

**Files:**
- Create: `apps/break_the_barriers/frontend/app/pricing/page.tsx`

- [ ] **Step 1: Tạo pricing page**

```typescript
// apps/break_the_barriers/frontend/app/pricing/page.tsx
"use client"

import { useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Check, X, ArrowLeft } from "lucide-react"

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "/tháng",
    pages: "20 trang/lần",
    features: ["1 upload", "PDF & EPUB", "AI dịch Gemini"],
    missing: ["Unlimited uploads", "Web-Book", "API access", "Watermark-free"],
    cta: "Đang dùng",
    ctaDisabled: true,
    highlight: false,
  },
  {
    name: "Pro",
    price: "$29",
    period: "/tháng",
    pages: "500 trang/tháng",
    features: ["Unlimited uploads", "PDF & EPUB", "AI dịch Gemini", "Web-Book", "Không watermark"],
    missing: ["API access"],
    cta: "Chọn Pro",
    ctaDisabled: false,
    highlight: true,
    badge: "Phổ biến nhất",
  },
  {
    name: "Enterprise",
    price: "$99",
    period: "/tháng",
    pages: "2000 trang/tháng",
    features: ["Tất cả tính năng Pro", "API access", "Priority queue", "Custom domain"],
    missing: [],
    cta: "Liên hệ",
    ctaDisabled: false,
    highlight: false,
  },
]

export default function PricingPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const quotaExceeded = searchParams.get("reason") === "quota"
  const [showModal, setShowModal] = useState(false)

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3">
        <button onClick={() => router.push("/dashboard")} className="text-gray-500 hover:text-gray-700">
          <ArrowLeft size={18} />
        </button>
        <span className="font-bold text-indigo-600">Break The Barriers</span>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-12">
        {quotaExceeded && (
          <div className="mb-6 bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-sm text-orange-700">
            Bạn đã hết quota tháng này. Nâng cấp để tiếp tục dịch sách.
          </div>
        )}

        <div className="text-center mb-10">
          <h1 className="text-2xl font-bold text-gray-900">Chọn gói phù hợp</h1>
          <p className="text-gray-500 mt-2 text-sm">Bắt đầu miễn phí, nâng cấp bất cứ lúc nào</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`bg-white rounded-xl p-6 border-2 relative flex flex-col ${
                plan.highlight ? "border-indigo-500 shadow-lg" : "border-gray-200"
              }`}
            >
              {plan.badge && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-xs px-3 py-1 rounded-full whitespace-nowrap">
                  {plan.badge}
                </span>
              )}
              <div className="mb-4">
                <h2 className={`font-bold text-lg ${plan.highlight ? "text-indigo-600" : "text-gray-800"}`}>
                  {plan.name}
                </h2>
                <div className="mt-1">
                  <span className="text-3xl font-bold text-gray-900">{plan.price}</span>
                  <span className="text-gray-400 text-sm">{plan.period}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{plan.pages}</p>
              </div>

              <ul className="space-y-2 mb-6 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-700">
                    <Check size={14} className="text-green-500 shrink-0" /> {f}
                  </li>
                ))}
                {plan.missing.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-400">
                    <X size={14} className="shrink-0" /> {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => {
                  if (plan.name === "Enterprise") {
                    window.location.href = "mailto:contact@breakthebarriers.app"
                  } else if (!plan.ctaDisabled) {
                    setShowModal(true)
                  }
                }}
                disabled={plan.ctaDisabled}
                className={`w-full py-2 rounded text-sm font-medium transition-colors ${
                  plan.highlight
                    ? "bg-indigo-600 text-white hover:bg-indigo-700"
                    : plan.ctaDisabled
                    ? "border border-gray-300 text-gray-400 cursor-default"
                    : "border border-indigo-600 text-indigo-600 hover:bg-indigo-50"
                }`}
              >
                {plan.cta}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Coming Soon Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 max-w-sm w-full shadow-xl">
            <h3 className="font-bold text-gray-900 mb-2">Sắp ra mắt 🚀</h3>
            <p className="text-sm text-gray-600 mb-4">
              Tính năng billing đang được phát triển. Liên hệ email để được nâng cấp tài khoản thủ công:
            </p>
            <a
              href="mailto:contact@breakthebarriers.app"
              className="block w-full text-center bg-indigo-600 text-white py-2 rounded text-sm hover:bg-indigo-700"
            >
              Liên hệ qua email
            </a>
            <button onClick={() => setShowModal(false)} className="w-full mt-2 text-sm text-gray-400 hover:text-gray-600">
              Đóng
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compile**

```bash
cd apps/break_the_barriers/frontend
npx tsc --noEmit 2>&1 | head -10
```
Expected: no errors

- [ ] **Step 3: Full backend test suite — final regression check**

```bash
cd apps/break_the_barriers/backend
.venv/bin/pytest tests/ -q 2>&1 | tail -4
```
Expected: tất cả pass (không có regression)

- [ ] **Step 4: Commit**

```bash
git add apps/break_the_barriers/frontend/app/pricing/
git commit -m "feat(SP2): add pricing page — 3 plans, Coming Soon modal for Pro upgrade"
```

---

## Task 17: Dev run script + .gitignore update

**Files:**
- Create: `apps/break_the_barriers/frontend/.gitignore` (Next.js default gitignore)
- Create: `apps/break_the_barriers/run-dev.sh` (optional convenience script)

- [ ] **Step 1: Verify .gitignore tồn tại cho frontend**

`create-next-app` tạo `.gitignore` tự động. Kiểm tra:
```bash
cat apps/break_the_barriers/frontend/.gitignore | head -5
```
Expected: thấy `node_modules`, `.next` trong file

- [ ] **Step 2: Thêm .superpowers/ vào project .gitignore nếu chưa có**

```bash
grep -q ".superpowers" /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/.gitignore 2>/dev/null || echo ".superpowers/" >> /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/.gitignore
```

- [ ] **Step 3: Build frontend để kiểm tra không có lỗi compile**

```bash
cd apps/break_the_barriers/frontend
npm run build 2>&1 | tail -20
```
Expected: `✓ Compiled successfully` hoặc `Route ... done`

- [ ] **Step 4: Final commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/frontend/
git commit -m "feat(SP2): complete Next.js frontend — dashboard, books, pricing, auth pages"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Plan task |
|-----------------|-----------|
| Local JWT auth (python-jose + passlib) | Tasks 1, 4, 5, 6 |
| users + subscriptions tables | Task 2, 9 |
| user_id trên documents | Task 2, 8 |
| Quota enforcement | Task 8 |
| Quota reset khi login tháng mới | Task 6 (login endpoint) |
| Backward compat (61 existing tests pass) | Tasks 2, 7, 8 |
| Register + Login endpoints | Tasks 6, 7 |
| GET /me endpoint | Tasks 6, 7 |
| Next.js 14 App Router setup | Task 10 |
| lib/auth.ts + lib/api.ts | Task 11 |
| middleware.ts route protection | Task 12 |
| Login page — Card Centered | Task 13 |
| Register page | Task 13 |
| Dashboard — Minimal Light, quota bar, upload, list | Task 14 |
| Book detail — pipeline stepper, SSE | Task 15 |
| Pricing — 3 Cards, Pro highlighted, Coming Soon modal | Task 16 |
| SQL migration script | Task 9 |

### Type consistency

- `UserInfo` defined in Task 3 (Pydantic) → used in Tasks 6, 8
- `UserInfo` TypeScript interface defined in Task 11 (lib/auth.ts) → used in Tasks 13, 14
- `fetchAPI<T>` defined in Task 11 (lib/api.ts) → used in Tasks 13, 14, 15, 16
- `get_optional_user` defined in Task 5 → used in Task 8
- `get_current_user` defined in Task 5 → used in Task 6
- `hash_password`, `verify_password`, `create_access_token`, `decode_token` defined in Task 4 → used in Tasks 5, 6

### Placeholder scan

Không có TBD, TODO, hay incomplete sections.
