# SP2 SaaS Platform — Design Spec

**Date:** 2026-05-29  
**Status:** Approved  
**Goal:** Thêm auth, multi-tenant isolation, quota enforcement, và Next.js 14 frontend vào Break The Barriers. Cloud services (Supabase, Stripe) sẽ tích hợp sau — SP2 dùng local JWT + placeholder billing.

---

## 1. Scope

### Làm trong SP2
- Local JWT auth (email + password, `python-jose` + `passlib`)
- `users` + `subscriptions` tables trong PostgreSQL
- `user_id` trên `documents` (multi-tenant isolation)
- Quota enforcement (pages_used / pages_limit per user)
- Next.js 14 App Router frontend — login, register, dashboard, book detail, pricing
- Backward compat: existing 61 tests vẫn pass

### Để sau (SP2b / SP3)
- Supabase Auth (OAuth Google/GitHub)
- Stripe subscriptions + webhooks
- Stripe Checkout page
- Proper monthly quota reset via cron/webhook

---

## 2. Architecture

```
apps/break_the_barriers/
├── frontend/                    ← NEW: Next.js 14 App Router
│   ├── app/
│   │   ├── (auth)/login/page.tsx
│   │   ├── (auth)/register/page.tsx
│   │   ├── dashboard/page.tsx
│   │   ├── books/[id]/page.tsx
│   │   ├── pricing/page.tsx
│   │   ├── layout.tsx
│   │   └── page.tsx             ← redirect → /dashboard | /login
│   ├── lib/
│   │   ├── api.ts               ← fetchAPI() với auto JWT header
│   │   └── auth.ts              ← login(), logout(), getUser()
│   ├── middleware.ts             ← route protection
│   ├── next.config.js
│   ├── tailwind.config.js
│   └── package.json
│
└── backend/app/
    ├── routers/auth.py          ← NEW
    ├── services/auth_service.py ← NEW
    └── models_db.py             ← MODIFY: DBUser, DBSubscription, DBDocument.user_id
```

**Request flow:**
```
Browser (port 3000) → Next.js → FastAPI (port 8000)
  /dashboard           GET /api/docs   Authorization: Bearer <jwt>
  /login               POST /api/auth/login → { access_token, user }
```

---

## 3. Database

### Bảng `users` (mới)
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    full_name VARCHAR DEFAULT '',
    plan VARCHAR DEFAULT 'free',          -- free | pro | enterprise
    pages_used_this_month INT DEFAULT 0,
    pages_limit INT DEFAULT 20,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Bảng `subscriptions` (mới — skeleton cho Stripe sau)
```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR UNIQUE,
    status VARCHAR DEFAULT 'active',
    current_period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Bảng `documents` (thay đổi)
```sql
ALTER TABLE documents ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN is_public BOOLEAN DEFAULT FALSE;
```

### Plan limits
| Plan | pages_limit | pages_used reset |
|------|-------------|-----------------|
| free | 20 | khi login tháng mới |
| pro | 500 | khi login tháng mới |
| enterprise | 2000 | khi login tháng mới |

---

## 4. Backend

### 4a. Auth endpoints (`routers/auth.py`)

| Method | Path | Auth | Mô tả |
|--------|------|------|-------|
| `POST` | `/api/auth/register` | — | Tạo user, trả `access_token` |
| `POST` | `/api/auth/login` | — | Verify password, trả `access_token` |
| `GET` | `/api/auth/me` | Required | Trả user hiện tại |

**Request/Response:**
```python
# POST /api/auth/register & /api/auth/login
# Request body:
{ "email": "user@example.com", "password": "secret", "full_name": "Nguyen Van A" }

# Response:
{ "access_token": "<jwt>", "token_type": "bearer",
  "user": { "id": "...", "email": "...", "plan": "free", "pages_limit": 20, "pages_used_this_month": 0 } }
```

### 4b. Auth service (`services/auth_service.py`)
```python
JWT_SECRET_KEY: str          # từ .env
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7          # từ .env, default 7

def hash_password(password: str) -> str          # bcrypt
def verify_password(plain, hashed) -> bool
def create_access_token(user_id, email, plan) -> str
def decode_token(token: str) -> dict             # raise 401 nếu expired/invalid
```

### 4c. Dependencies
```python
def get_optional_user(token=Header(None), db=Depends(get_db)) -> Optional[DBUser]:
    """Trả None nếu không có token — backward compat cho existing endpoints"""

def get_current_user(token=Header(...), db=Depends(get_db)) -> DBUser:
    """Raise 401 nếu không có hoặc invalid token"""
```

### 4d. Quota enforcement
```python
# Inject vào upload + extract endpoints
def check_and_consume_quota(user: DBUser, pages: int, db: Session):
    if user and user.pages_used_this_month + pages > user.pages_limit:
        raise HTTPException(402, "Quota exceeded. Upgrade your plan.")
    if user:
        user.pages_used_this_month += pages
        db.commit()
```

### 4e. Quota reset logic
Khi `GET /api/auth/me`: nếu `user.created_at.month != datetime.now().month` → reset `pages_used_this_month = 0` và save. Đơn giản nhất cho MVP, không cần cron.

### 4f. Backward compatibility
- Tất cả existing `/api/docs/*` endpoints dùng `get_optional_user` (không bắt buộc auth)
- Nếu không có token → `user_id = NULL`, không check quota → behavior cũ
- 61 existing tests tiếp tục pass vì không có token → optional user = None

### 4g. New dependencies (requirements.txt)
```
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
```

---

## 5. Frontend

### 5a. Visual design
- **Style**: Minimal Light (trắng + xám nhạt + accent tím `#4f46e5`)
- **Font**: system font stack (không import Google Fonts)
- **Icons**: `lucide-react`

### 5b. Pages

**`/login` và `/register`** — Card Centered
- Card trắng, box-shadow nhẹ, nền `#f9fafb`
- Email + password fields (+ full_name cho register)
- Submit → POST `/api/auth/login` hoặc `/register`
- Lưu token vào `localStorage["btb_token"]` + cookie `btb_token` (7 ngày)
- Redirect → `/dashboard`

**`/dashboard`** — Minimal Light
- Header: "Break The Barriers" logo + email + Logout button
- Quota bar: `{pages_used}/{pages_limit} trang đã dùng tháng này` + progress bar
- Upload zone: drag & drop hoặc click, accept `.pdf` và `.epub`
- Book list: table với columns — Tên file, Trạng thái, Số trang, Ngày tạo, Actions
- Status badges: raw (xám) | extracted (xanh dương) | translated (xanh lá) | compiled (tím) | failed (đỏ)
- Actions: View (→ `/books/[id]`) | Delete

**`/books/[id]`** — Book detail
- Tên file + metadata (pages, created_at, plan tier)
- Pipeline steps: `raw → extracted → translated → compiled` (visual stepper)
- Buttons: Extract | Translate All (SSE progress bar) | Compile | Resume
- SSE progress: real-time page counter từ `/api/docs/{id}/progress`

**`/pricing`** — 3 Cards, Pro Highlighted
- 3 columns: Free ($0) | Pro ($29/mo, viền tím, badge "Phổ biến nhất") | Enterprise ($99/mo)
- Nút "Chọn Pro" → modal: "Tính năng billing sẽ sớm có. Liên hệ [email] để nâng cấp thủ công."
- Nút "Liên hệ Enterprise" → mailto link

### 5c. Auth lib (`lib/auth.ts`)
```typescript
const TOKEN_KEY = "btb_token"

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
  document.cookie = `${TOKEN_KEY}=${token}; path=/; max-age=${7*86400}`
}
export function getToken(): string | null { return localStorage.getItem(TOKEN_KEY) }
export function logout() { localStorage.removeItem(TOKEN_KEY); document.cookie = `${TOKEN_KEY}=; max-age=0` }
export function isLoggedIn(): boolean { return !!getToken() }
```

### 5d. API client (`lib/api.ts`)
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export async function fetchAPI<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const res = await fetch(API_URL + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (res.status === 401) { logout(); window.location.href = "/login"; throw new Error("Unauthorized") }
  if (res.status === 402) { window.location.href = "/pricing?reason=quota"; throw new Error("Quota exceeded") }
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
```

### 5e. Route protection (`middleware.ts`)
```typescript
// Bảo vệ /dashboard và /books/* — redirect /login nếu không có cookie btb_token
export function middleware(request: NextRequest) {
  const token = request.cookies.get("btb_token")
  if (!token) return NextResponse.redirect(new URL("/login", request.url))
}
export const config = { matcher: ["/dashboard/:path*", "/books/:path*"] }
```

### 5f. Environment variables
```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 6. Testing

### Backend tests (thêm vào `test_api.py`)
- `test_register_user` — POST /api/auth/register → 200, nhận token
- `test_login_user` — POST /api/auth/login → 200, nhận token
- `test_login_wrong_password` — → 401
- `test_get_me` — GET /api/auth/me với valid token → user data
- `test_get_me_no_token` — → 401
- `test_upload_with_auth_sets_user_id` — upload với token → document.user_id set
- `test_upload_without_auth_still_works` — upload không có token → 200, user_id = NULL
- `test_quota_exceeded` — user đã dùng hết quota → upload → 402

### Frontend smoke tests (manual checklist)
- [ ] `/login` render đúng, submit với wrong password → error message
- [ ] `/register` → tạo account → redirect `/dashboard`
- [ ] `/dashboard` hiển thị danh sách documents của user hiện tại
- [ ] Upload PDF → xuất hiện trong list
- [ ] Logout → redirect `/login`
- [ ] `/pricing` hiển thị 3 cards, nút Pro → modal Coming Soon
- [ ] Truy cập `/dashboard` khi chưa đăng nhập → redirect `/login`

---

## 7. Rollout order

1. **Backend**: DB migration → auth_service → auth router → tests (không ảnh hưởng frontend)
2. **Frontend**: Next.js setup → lib/auth + lib/api → pages từng cái
3. **Integration**: wire frontend → backend API
4. **Backward compat check**: chạy 61 existing tests → tất cả pass

---

## 8. Out of scope

- Supabase Auth (OAuth)
- Stripe billing + webhooks
- Email verification
- Password reset flow
- Admin panel
- Rate limiting
- Session revocation
