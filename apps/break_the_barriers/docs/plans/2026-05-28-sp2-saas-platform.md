# SP2: SaaS Platform — Auth + Billing + Multi-tenant

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task.

**Goal:** Biến Break The Barriers thành Micro-SaaS có thể thu tiền: user đăng ký, chọn plan $29/tháng qua Stripe, dữ liệu tách biệt theo user.

**Architecture:** Supabase Auth (JWT) + FastAPI middleware + Stripe webhooks + PostgreSQL multi-tenant (thêm `user_id`). Frontend chuyển sang Next.js 14.

**Tech Stack:** Next.js 14 + Tailwind + shadcn/ui, Supabase Auth, Stripe, FastAPI (giữ nguyên backend), PostgreSQL

---

## File Structure

```
apps/break_the_barriers/
├── frontend/                     NEW — Next.js app (thay vanilla HTML/JS)
│   ├── app/
│   │   ├── (auth)/login/
│   │   ├── (auth)/register/
│   │   ├── dashboard/
│   │   ├── upload/
│   │   ├── books/[id]/
│   │   └── pricing/
│   ├── components/
│   │   ├── BookCard.tsx
│   │   ├── UploadZone.tsx
│   │   ├── ProgressBar.tsx
│   │   └── PricingTable.tsx
│   └── lib/
│       ├── supabase.ts
│       ├── stripe.ts
│       └── api.ts               ← API client cho FastAPI backend

backend/app/
├── middleware/
│   └── auth.py                  NEW — JWT verify từ Supabase
├── routers/
│   └── users.py                 NEW — GET /api/users/me, usage stats
└── models_db.py                 MOD — thêm DBUser, DBSubscription
```

---

## Task 1: Database schema cho multi-tenant

**Files:** `backend/app/models_db.py`, `backend/migrate_v3.py`

- [ ] **Step 1: Tạo migrate_v3.py**

```python
"""
Migration v3: Add users, subscriptions tables; add user_id to documents.
Run: .venv/bin/python migrate_v3.py
"""
import psycopg2, os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/break_the_barriers")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        supabase_id VARCHAR UNIQUE NOT NULL,
        email VARCHAR UNIQUE NOT NULL,
        full_name VARCHAR,
        avatar_url VARCHAR,
        stripe_customer_id VARCHAR,
        plan VARCHAR DEFAULT 'free',
        pages_used_this_month INT DEFAULT 0,
        pages_limit INT DEFAULT 20,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS subscriptions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        stripe_subscription_id VARCHAR UNIQUE,
        stripe_price_id VARCHAR,
        status VARCHAR DEFAULT 'inactive',
        current_period_start TIMESTAMP,
        current_period_end TIMESTAMP,
        cancel_at_period_end BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    );

    ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS slug VARCHAR UNIQUE;

    CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
    CREATE INDEX IF NOT EXISTS idx_documents_slug ON documents(slug);
""")

conn.commit()
cur.close()
conn.close()
print("Migration v3 complete.")
```

- [ ] **Step 2: Chạy migration**

```bash
cd backend && .venv/bin/python migrate_v3.py
```

Expected: `Migration v3 complete.`

- [ ] **Step 3: Thêm DBUser, DBSubscription vào models_db.py**

```python
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base


class DBUser(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    supabase_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    plan = Column(String, default="free")            # free | pro | enterprise
    pages_used_this_month = Column(Integer, default=0)
    pages_limit = Column(Integer, default=20)        # free: 20, pro: 500
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    documents = relationship("DBDocument", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship("DBSubscription", back_populates="user", uselist=False)


class DBSubscription(Base):
    __tablename__ = "subscriptions"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    stripe_price_id = Column(String, nullable=True)
    status = Column(String, default="inactive")
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("DBUser", back_populates="subscription")
```

Thêm vào `DBDocument`:
```python
user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
is_public = Column(Boolean, default=False)
slug = Column(String, unique=True, nullable=True)
user = relationship("DBUser", back_populates="documents")
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: all pass (models thêm column không break tests hiện tại)

- [ ] **Step 5: Commit**

```bash
git add backend/migrate_v3.py backend/app/models_db.py
git commit -m "feat: add DBUser, DBSubscription, user_id to documents (multi-tenant)"
```

---

## Task 2: Auth middleware cho FastAPI

**Files:**
- Create: `backend/app/middleware/auth.py`
- Create: `backend/app/routers/users.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Tạo backend/app/middleware/auth.py**

```python
import os
import logging
from typing import Optional
from fastapi import HTTPException, Header, Depends
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models_db import DBUser

logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


def verify_supabase_token(authorization: str) -> dict:
    """Verify Supabase JWT and return payload."""
    import jwt
    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Optional[DBUser]:
    """FastAPI dependency: get authenticated user from JWT. Returns None if no auth."""
    if not authorization or not SUPABASE_JWT_SECRET:
        return None   # Auth optional for now (backward compatible)

    payload = verify_supabase_token(authorization)
    supabase_id = payload.get("sub")
    email = payload.get("email", "")

    # Get or create user in our DB
    user = db.query(DBUser).filter(DBUser.supabase_id == supabase_id).first()
    if not user:
        user = DBUser(supabase_id=supabase_id, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def require_user(user: Optional[DBUser] = Depends(get_current_user)) -> DBUser:
    """Strict version: raises 401 if not authenticated."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def check_quota(user: DBUser, pages_to_process: int) -> None:
    """Check if user has enough page quota."""
    if user.pages_used_this_month + pages_to_process > user.pages_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Page quota exceeded. Used: {user.pages_used_this_month}/{user.pages_limit}. Upgrade to Pro for 500 pages/month."
        )
```

- [ ] **Step 2: Tạo backend/app/routers/users.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models_db import DBUser, DBSubscription
from backend.app.middleware.auth import require_user

router = APIRouter()


@router.get("/api/users/me")
def get_me(current_user: DBUser = Depends(require_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan": current_user.plan,
        "pages_used": current_user.pages_used_this_month,
        "pages_limit": current_user.pages_limit,
        "pages_remaining": max(0, current_user.pages_limit - current_user.pages_used_this_month),
    }


@router.get("/api/users/usage")
def get_usage(current_user: DBUser = Depends(require_user), db: Session = Depends(get_db)):
    total_docs = db.query(DBUser).filter(DBUser.id == current_user.id).first()
    return {
        "plan": current_user.plan,
        "pages_used_this_month": current_user.pages_used_this_month,
        "pages_limit": current_user.pages_limit,
        "stripe_customer_id": current_user.stripe_customer_id,
    }
```

- [ ] **Step 3: Thêm vào main.py**

```python
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs, users
# ...
app.include_router(users.router)
```

- [ ] **Step 4: Thêm .env.example vars**

Thêm vào `.env.example`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ENTERPRISE=price_...
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/ backend/app/routers/users.py backend/app/main.py backend/.env.example
git commit -m "feat: add Supabase JWT auth middleware, /api/users/me endpoint"
```

---

## Task 3: Stripe billing integration

**Files:**
- Create: `backend/app/routers/billing.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Cài stripe**

```bash
.venv/bin/pip install stripe
echo "stripe>=7.0.0" >> requirements.txt
```

- [ ] **Step 2: Tạo backend/app/routers/billing.py**

```python
import os
import stripe
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models_db import DBUser, DBSubscription
from backend.app.middleware.auth import require_user

logger = logging.getLogger(__name__)
router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PRICE_IDS = {
    "pro": os.getenv("STRIPE_PRICE_PRO", ""),
    "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", ""),
}
PLAN_LIMITS = {
    "free": 20,
    "pro": 500,
    "enterprise": 2000,
}


@router.post("/api/billing/checkout")
def create_checkout(
    plan: str,
    current_user: DBUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create Stripe Checkout session for subscription."""
    price_id = PRICE_IDS.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")

    # Create or get Stripe customer
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        current_user.stripe_customer_id = customer.id
        db.commit()

    session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/dashboard?upgraded=true",
        cancel_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/pricing",
        metadata={"user_id": current_user.id, "plan": plan},
    )
    return {"checkout_url": session.url}


@router.post("/api/billing/portal")
def billing_portal(
    current_user: DBUser = Depends(require_user),
):
    """Create Stripe Customer Portal session for managing subscription."""
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found")

    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/dashboard",
    )
    return {"portal_url": session.url}


@router.post("/api/billing/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """Handle Stripe webhook events."""
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    db = next(get_db())
    try:
        _handle_stripe_event(event, db)
    finally:
        db.close()

    return {"status": "ok"}


def _handle_stripe_event(event: dict, db: Session):
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data["metadata"].get("user_id")
        plan = data["metadata"].get("plan", "pro")
        user = db.query(DBUser).filter(DBUser.id == user_id).first()
        if user:
            user.plan = plan
            user.pages_limit = PLAN_LIMITS.get(plan, 500)
            # Create subscription record
            sub = DBSubscription(
                user_id=user.id,
                stripe_subscription_id=data.get("subscription"),
                status="active",
            )
            db.add(sub)
            db.commit()
            logger.info(f"User {user.email} upgraded to {plan}")

    elif event_type in ("customer.subscription.deleted", "customer.subscription.paused"):
        stripe_sub_id = data["id"]
        sub = db.query(DBSubscription).filter(
            DBSubscription.stripe_subscription_id == stripe_sub_id
        ).first()
        if sub:
            sub.status = "canceled"
            user = db.query(DBUser).filter(DBUser.id == sub.user_id).first()
            if user:
                user.plan = "free"
                user.pages_limit = PLAN_LIMITS["free"]
            db.commit()
```

- [ ] **Step 3: Include billing router trong main.py**

```python
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs, users, billing
app.include_router(billing.router)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/billing.py backend/app/main.py backend/requirements.txt
git commit -m "feat: add Stripe checkout, billing portal, webhook handler"
```

---

## Task 4: Next.js Frontend

**Files:**
- Create: `apps/break_the_barriers/frontend/` (Next.js project)

- [ ] **Step 1: Init Next.js project**

```bash
cd apps/break_the_barriers
npx create-next-app@latest frontend \
  --typescript --tailwind --eslint --app \
  --src-dir --import-alias "@/*"
cd frontend
npm install @supabase/supabase-js @supabase/ssr stripe @stripe/stripe-js
npm install @radix-ui/react-dialog @radix-ui/react-progress lucide-react
```

- [ ] **Step 2: Cấu hình Supabase client**

Tạo `frontend/src/lib/supabase.ts`:
```typescript
import { createBrowserClient } from '@supabase/ssr'

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
```

- [ ] **Step 3: Tạo API client**

Tạo `frontend/src/lib/api.ts`:
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function apiRequest(path: string, options: RequestInit = {}) {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  
  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`
  }
  
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export const api = {
  docs: {
    list: () => apiRequest('/api/docs'),
    upload: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return apiRequest('/api/docs/upload', { method: 'POST', body: form, headers: {} })
    },
    translateAll: (docId: string, quality = 'high') =>
      apiRequest(`/api/docs/${docId}/translate-all`, {
        method: 'POST',
        body: JSON.stringify({ target_lang: 'vi', quality_tier: quality }),
      }),
    volume: (docId: string) => apiRequest(`/api/docs/${docId}/volume`),
  },
  user: {
    me: () => apiRequest('/api/users/me'),
  },
  billing: {
    checkout: (plan: string) =>
      apiRequest(`/api/billing/checkout?plan=${plan}`, { method: 'POST' }),
    portal: () => apiRequest('/api/billing/portal', { method: 'POST' }),
  },
}
```

- [ ] **Step 4: Dashboard page**

Tạo `frontend/src/app/dashboard/page.tsx`:
```typescript
'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

interface Doc {
  id: string; filename: string; status: string; total_pages: number;
  volume_tier?: string; estimated_cost_usd?: number;
}

export default function Dashboard() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [usage, setUsage] = useState<any>(null)

  useEffect(() => {
    api.docs.list().then(setDocs)
    api.user.me().then(setUsage)
  }, [])

  return (
    <main className="max-w-5xl mx-auto p-6">
      {/* Usage bar */}
      {usage && (
        <div className="mb-6 p-4 rounded-xl bg-indigo-950/50 border border-indigo-800">
          <div className="flex justify-between text-sm mb-2">
            <span>Trang đã dùng tháng này</span>
            <span className="font-bold">{usage.pages_used}/{usage.pages_limit}</span>
          </div>
          <div className="h-2 bg-white/10 rounded-full">
            <div
              className="h-full bg-indigo-500 rounded-full transition-all"
              style={{ width: `${(usage.pages_used / usage.pages_limit) * 100}%` }}
            />
          </div>
          {usage.plan === 'free' && (
            <a href="/pricing" className="text-xs text-indigo-400 mt-2 block hover:underline">
              Nâng cấp Pro → 500 trang/tháng
            </a>
          )}
        </div>
      )}

      {/* Book shelf */}
      <div className="grid gap-4">
        {docs.map(doc => (
          <div key={doc.id} className="p-4 rounded-xl bg-white/5 border border-white/10">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold">{doc.filename}</h3>
                <p className="text-sm text-gray-400">
                  {doc.total_pages} trang · {doc.volume_tier || '?'} tier
                  {doc.estimated_cost_usd ? ` · ~$${doc.estimated_cost_usd} cost` : ''}
                </p>
              </div>
              <span className={`px-2 py-1 rounded text-xs font-medium ${
                doc.status === 'compiled' ? 'bg-green-900 text-green-300' :
                doc.status === 'translating' ? 'bg-indigo-900 text-indigo-300' :
                'bg-gray-800 text-gray-400'
              }`}>
                {doc.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </main>
  )
}
```

- [ ] **Step 5: Pricing page**

Tạo `frontend/src/app/pricing/page.tsx`:
```typescript
'use client'
import { api } from '@/lib/api'

const PLANS = [
  { id: 'free', name: 'Free', price: '$0', pages: '20 trang/demo',
    features: ['1 upload', 'Xem preview', 'Watermark'] },
  { id: 'pro', name: 'Pro', price: '$29/tháng', pages: '500 trang/tháng',
    features: ['Upload không giới hạn', 'Web-Book publish', 'Priority queue', 'No watermark'],
    highlighted: true },
  { id: 'enterprise', name: 'Enterprise', price: '$99/tháng', pages: '2000 trang/tháng',
    features: ['All Pro features', 'API access', 'Custom domain', 'Dedicated support'] },
]

export default function Pricing() {
  const handleUpgrade = async (planId: string) => {
    if (planId === 'free') return
    const { checkout_url } = await api.billing.checkout(planId)
    window.location.href = checkout_url
  }

  return (
    <main className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold text-center mb-2">Pricing</h1>
      <p className="text-center text-gray-400 mb-8">Biến sách của bạn thành sản phẩm Web đa ngôn ngữ</p>
      <div className="grid md:grid-cols-3 gap-6">
        {PLANS.map(plan => (
          <div key={plan.id} className={`rounded-xl p-6 border ${
            plan.highlighted ? 'border-indigo-500 bg-indigo-950/50' : 'border-white/10 bg-white/5'
          }`}>
            <h2 className="text-xl font-bold">{plan.name}</h2>
            <p className="text-3xl font-bold my-3">{plan.price}</p>
            <p className="text-sm text-gray-400 mb-4">{plan.pages}</p>
            <ul className="space-y-2 mb-6">
              {plan.features.map(f => (
                <li key={f} className="text-sm flex items-center gap-2">
                  <span className="text-green-400">✓</span> {f}
                </li>
              ))}
            </ul>
            <button
              onClick={() => handleUpgrade(plan.id)}
              className={`w-full py-2 rounded-lg font-medium ${
                plan.highlighted
                  ? 'bg-indigo-600 hover:bg-indigo-700'
                  : 'bg-white/10 hover:bg-white/20'
              }`}
            >
              {plan.id === 'free' ? 'Bắt đầu miễn phí' : 'Upgrade'}
            </button>
          </div>
        ))}
      </div>
    </main>
  )
}
```

- [ ] **Step 6: Run Next.js dev**

```bash
cd frontend && npm run dev
```

Mở http://localhost:3000 verify dashboard và pricing page hoạt động.

- [ ] **Step 7: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/frontend/
git commit -m "feat: add Next.js frontend with dashboard, pricing, Supabase auth, Stripe checkout"
```

---

## Checklist SP2 hoàn thành

- [ ] `migrate_v3.py` chạy thành công: users, subscriptions tables tạo xong
- [ ] `DBUser`, `DBSubscription` trong models_db.py
- [ ] `user_id` trong `documents` table
- [ ] JWT middleware verify Supabase token
- [ ] `/api/users/me` trả về user info + quota
- [ ] `/api/billing/checkout` tạo Stripe checkout session
- [ ] `/api/billing/webhook` handle subscription events
- [ ] Next.js frontend chạy được ở localhost:3000
- [ ] Dashboard hiển thị books + usage bar
- [ ] Pricing page → redirect Stripe checkout

**Tiếp theo:** SP3 — Web-Book Publisher (USP differentiation)
