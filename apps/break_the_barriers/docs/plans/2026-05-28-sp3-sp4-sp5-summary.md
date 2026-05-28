# SP3 + SP4 + SP5 — Summary Plans

> Các plan chi tiết đầy đủ sẽ được viết khi SP1 + SP2 hoàn thành.
> Document này là spec-level summary để định hướng implementation.

---

# SP3: Web-Book Publisher (4 tuần)

## Goal
User publish sách → nhận link `books.yourdomain.com/slug` với:
- Responsive book reader (mobile-friendly)
- Language switcher (EN ↔ VI ↔ ZH)
- Table of contents / chapter navigation
- SEO metadata (Open Graph, structured data)
- Optional paywall

## Tasks

### Task 1: Book slug + publish settings API

```python
# POST /api/docs/{id}/publish
{
  "slug": "clean-code-tieng-viet",
  "is_public": true,
  "paywall_price_usd": null,   # null = free
  "available_langs": ["vi", "en"],
  "description": "...",
  "cover_url": "..."
}
```

DB changes:
```sql
ALTER TABLE documents ADD COLUMN IF NOT EXISTS
  slug VARCHAR UNIQUE,
  is_public BOOLEAN DEFAULT FALSE,
  paywall_price_usd FLOAT,
  description TEXT,
  cover_url VARCHAR,
  published_at TIMESTAMP;
```

### Task 2: Web-Book Next.js routes

```
frontend/src/app/
└── books/
    └── [slug]/
        ├── page.tsx           ← Landing: cover, description, CTA
        ├── read/
        │   ├── page.tsx       ← Reader: chapter 1
        │   └── [chapter]/
        │       └── page.tsx   ← Chapter reader
        └── api/
            └── content/
                └── route.ts   ← API: fetch chapter HTML
```

### Task 3: Language switcher component

```typescript
// Stores current lang in localStorage + URL param
// ?lang=en → shows English version
// ?lang=vi → shows Vietnamese version (default)

function LanguageSwitcher({ slug, available }: Props) {
  const [lang, setLang] = useLanguage()
  return (
    <div className="flex gap-2">
      {available.map(l => (
        <button
          key={l}
          onClick={() => setLang(l)}
          className={lang === l ? 'active' : ''}
        >
          {LANG_FLAGS[l]} {LANG_NAMES[l]}
        </button>
      ))}
    </div>
  )
}
```

### Task 4: SEO metadata

```typescript
// app/books/[slug]/page.tsx
export async function generateMetadata({ params }) {
  const book = await getBook(params.slug)
  return {
    title: book.filename,
    description: book.description,
    openGraph: {
      type: 'book',
      images: [book.cover_url],
    }
  }
}
```

### Task 5: Nginx subdomain routing (production)

```nginx
# Wildcard subdomain → Next.js
server {
    server_name books.yourdomain.com;
    location / {
        proxy_pass http://nextjs:3000;
    }
}
```

---

# SP4: Translation Quality (3 tuần)

## Goal
Dịch theo chapter context, Translation Guide, multi-model support.

## Task 1: Translation Guide schema

```sql
CREATE TABLE translation_guides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    style VARCHAR DEFAULT 'neutral',   -- literary | technical | casual | neutral
    characters JSONB DEFAULT '[]',     -- [{name_en: "...", name_vi: "..."}]
    glossary JSONB DEFAULT '[]',       -- [{term_en: "...", term_vi: "..."}]
    keep_original JSONB DEFAULT '[]',  -- ["code", "brand_names"]
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Task 2: Chapter-level translation

```python
class ChapterTranslator:
    @staticmethod
    def translate_chapter(
        spans: List[dict],
        guide: TranslationGuide,
        target_lang: str,
        model: str = "gemini-2.0-flash"
    ) -> List[dict]:
        """
        Group ALL spans of a chapter → 1 API call với full context.
        Returns spans với translated_text filled in.
        """
        # Build full chapter text với span markers
        chapter_text = ""
        for span in spans:
            chapter_text += f"[s:{span['id']}] {span['text']}\n"

        system_prompt = f"""
You are translating a book chapter to {target_lang}.
Style: {guide.style}
Characters: {json.dumps(guide.characters)}
Glossary: {json.dumps(guide.glossary)}
Never translate: {json.dumps(guide.keep_original)}

Rules:
1. Preserve ALL [s:id] markers exactly
2. Maintain consistent terminology throughout
3. Match the author's voice and style
"""
        # Single API call for entire chapter
        result = translate_with_model(chapter_text, system_prompt, model)
        return deinterpolate_chapter(result, spans)
```

## Task 3: Multi-model provider registry

```python
# app/services/model_registry.py

class ModelProvider(ABC):
    @abstractmethod
    def translate(self, text: str, system_prompt: str) -> str: ...

class GeminiProvider(ModelProvider):
    def __init__(self, model: str = "gemini-2.0-flash"):
        self.model = model
    def translate(self, text, system_prompt):
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return client.models.generate_content(
            model=self.model,
            contents=f"{system_prompt}\n\n{text}"
        ).text

class DeepSeekProvider(ModelProvider):
    def translate(self, text, system_prompt):
        import openai
        client = openai.OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content

class AnthropicProvider(ModelProvider):
    def translate(self, text, system_prompt):
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": text}]
        )
        return message.content[0].text

MODEL_REGISTRY = {
    "gemini-flash": GeminiProvider("gemini-2.0-flash"),
    "gemini-pro": GeminiProvider("gemini-1.5-pro"),
    "deepseek": DeepSeekProvider(),
    "claude-sonnet": AnthropicProvider(),
}

# Plan access:
PLAN_MODELS = {
    "free": ["gemini-flash"],
    "pro": ["gemini-flash", "gemini-pro", "deepseek"],
    "enterprise": list(MODEL_REGISTRY.keys()),
}
```

---

# SP5: Reader Paywall + Analytics (3 tuần)

## Goal
Author đặt giá cho Web-Book, reader trả tiền, author nhận 80% revenue.

## Task 1: Stripe Connect cho authors

```python
# Author onboarding: tạo Stripe Connect account
@router.post("/api/billing/connect")
def create_connect_account(current_user: DBUser = Depends(require_user)):
    account = stripe.Account.create(
        type="express",
        email=current_user.email,
    )
    link = stripe.AccountLink.create(
        account=account.id,
        refresh_url=f"{FRONTEND_URL}/dashboard/billing",
        return_url=f"{FRONTEND_URL}/dashboard/billing?connected=true",
        type="account_onboarding",
    )
    return {"onboarding_url": link.url}
```

## Task 2: Reader checkout

```python
# Reader pays to unlock book
@router.post("/api/books/{slug}/purchase")
def purchase_book(slug: str, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.slug == slug).first()
    if not doc or not doc.paywall_price_usd:
        raise HTTPException(status_code=404)

    author = db.query(DBUser).filter(DBUser.id == doc.user_id).first()
    platform_fee = int(doc.paywall_price_usd * 100 * 0.20)  # 20% platform fee

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": int(doc.paywall_price_usd * 100),
                "product_data": {"name": doc.filename},
            },
            "quantity": 1,
        }],
        mode="payment",
        payment_intent_data={
            "application_fee_amount": platform_fee,
            "transfer_data": {"destination": author.stripe_connect_id},
        },
        success_url=f"{FRONTEND_URL}/books/{slug}/read?access=true",
        cancel_url=f"{FRONTEND_URL}/books/{slug}",
        metadata={"doc_id": doc.id, "slug": slug},
    )
    return {"checkout_url": session.url}
```

## Task 3: Reader analytics

```sql
CREATE TABLE reader_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id VARCHAR NOT NULL REFERENCES documents(id),
    event_type VARCHAR NOT NULL,  -- view | purchase | chapter_read | language_switch
    reader_fingerprint VARCHAR,   -- anonymous reader ID
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE book_analytics (
    document_id VARCHAR PRIMARY KEY REFERENCES documents(id),
    total_views INT DEFAULT 0,
    total_purchases INT DEFAULT 0,
    total_revenue_usd FLOAT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW()
);
```

Analytics dashboard API:
```python
@router.get("/api/docs/{doc_id}/analytics")
def get_analytics(doc_id: str, current_user: DBUser = Depends(require_user)):
    # Verify ownership
    # Return views, purchases, revenue, top countries, daily chart
```

---

# Prioritized Feature Backlog

## Phase 1 (MVP — Tuần 1-9): Ship và bán được

| Feature | Sub-project | Priority |
|---------|-------------|----------|
| Docling parser | SP1 | P0 |
| EPUB support | SP1 | P0 |
| User auth (Supabase) | SP2 | P0 |
| Stripe $29/month | SP2 | P0 |
| Multi-tenant DB | SP2 | P0 |
| Next.js dashboard | SP2 | P0 |
| Usage quota tracking | SP2 | P1 |

## Phase 2 (USP — Tuần 10-13): Differentiation

| Feature | Sub-project | Priority |
|---------|-------------|----------|
| Web-Book publisher | SP3 | P0 |
| Language switcher | SP3 | P0 |
| Book slug/URL | SP3 | P0 |
| SEO metadata | SP3 | P1 |
| Translation Guide | SP4 | P1 |

## Phase 3 (Scale — Tuần 14-19): Growth

| Feature | Sub-project | Priority |
|---------|-------------|----------|
| Chapter-level context | SP4 | P1 |
| DeepSeek model support | SP4 | P1 |
| Reader paywall | SP5 | P1 |
| Stripe Connect (author revenue) | SP5 | P1 |
| Reader analytics | SP5 | P2 |
| Custom domain | SP3 | P2 |
| EPUB/PDF export | SP3 | P2 |
| Claude model support | SP4 | P2 |
