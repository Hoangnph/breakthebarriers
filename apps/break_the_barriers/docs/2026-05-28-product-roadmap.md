# Break The Barriers — Product Upgrade Roadmap

> **Mục tiêu:** Từ engine xử lý nội bộ (~30% BA) → Micro-SaaS thương mại đầy đủ  
> **Target:** 200-300 paying users × $29/month = $6,000–9,000 MRR  
> **Nguồn lực:** Solo Dev + AI Code

---

## Tổng quan 5 Sub-projects

```
Hiện tại: Engine xử lý (PDF→HTML→Translated) — chạy được, chưa bán được

Sub-project 1: Parser Upgrade          [Foundation]  4 tuần
Sub-project 2: SaaS Platform           [Revenue]     5 tuần
Sub-project 3: Web-Book Publisher      [USP]         4 tuần
Sub-project 4: Translation Quality     [Quality]     3 tuần
Sub-project 5: Monetization            [Scale]       3 tuần
                                                   ─────────
                                        Tổng:     ~19 tuần
```

---

## Milestone Map

```
Tháng 1-2          Tháng 3            Tháng 4          Tháng 4-5
──────────────────────────────────────────────────────────────────
[SP1: Parser]  ──►  [SP2: SaaS]  ──►  [SP3: Publisher] ──► [SP4+5]
    │                   │                   │
    ▼                   ▼                   ▼
HTML sạch           First MRR           USP launch
responsive          (paying users)       differentiation
```

---

## Sub-project 1: Parser Upgrade (Ưu tiên #1 — Foundation)

**Vì sao làm trước:** `pdftohtml` tạo `position:absolute` — text dịch dài hơn sẽ đè nhau. Đây là blocker chất lượng lớn nhất, phải fix trước khi bán.

**Timeline:** 4 tuần

### Kết quả mong đợi
- PDF → HTML với semantic tags (`<h1>`, `<p>`, `<table>`, `<img>`) thay vì `<span>` tuyệt đối
- HTML responsive (co giãn theo màn hình, không vỡ layout khi text dịch dài hơn)
- EPUB support
- Nhận diện được: Heading / Paragraph / Table / Image / Footnote

### Tech Stack
| Component | Tool | Lý do |
|---|---|---|
| PDF parser | **Docling** (IBM, open-source) | State-of-art, nhận diện layout bằng AI, output Markdown/HTML sạch |
| Fallback parser | **PDFMiner + BeautifulSoup** | Khi Docling không handle được |
| EPUB parser | **ebooklib** (Python) | EPUB = HTML đã nén, chỉ cần extract |
| Image extraction | **pdf2image + Pillow** | Extract ảnh từ PDF |

### Tasks
- [ ] Cài Docling, test với 5 loại PDF phổ biến (textbook, novel, technical manual, scanned, multi-column)
- [ ] Viết `DoclingExtractor` class thay thế `Extractor.extract_pdf_to_html_cli()`
- [ ] Tạo HTML template responsive (CSS Flexbox/Grid, không absolute)
- [ ] EPUB parser: extract chapters → clean HTML per chapter
- [ ] Migration: backward-compatible với `DBPage.original_html` schema
- [ ] A/B test chất lượng output: Docling vs pdftohtml
- [ ] Update Docker image với Docling deps

### File changes
```
backend/app/services/
├── extractor.py          MOD — thêm DoclingExtractor, giữ cũ làm fallback
├── epub_parser.py        NEW — EPUB → chapters HTML
└── html_normalizer.py    NEW — clean HTML output, inject responsive CSS

backend/app/routers/
└── extraction.py         MOD — detect file type (PDF/EPUB), route đúng parser
```

---

## Sub-project 2: SaaS Platform (Ưu tiên #2 — Revenue Engine)

**Vì sao làm thứ 2:** Sau khi có parser tốt, cần auth + billing để có thể bán. Mọi thứ khác đều có thể bán sau khi SP2 xong.

**Timeline:** 5 tuần

### Kết quả mong đợi
- User đăng ký / đăng nhập
- Stripe subscription $29/month (+ free trial 7 ngày)
- Mỗi user chỉ thấy tài liệu của mình (multi-tenant)
- Dashboard: upload, quản lý sách, xem quota
- Usage limit: 500 trang/tháng (Free: 20 trang/lần demo)

### Tech Stack
| Component | Tool | Lý do |
|---|---|---|
| Auth | **Supabase Auth** | JWT, OAuth Google/GitHub, miễn phí tier rất rộng |
| Billing | **Stripe** | Subscription $29/month, webhooks |
| Frontend | **Next.js 14 + Tailwind** | Thay thế vanilla HTML/JS hiện tại |
| Backend | FastAPI (giữ nguyên) | Chỉ thêm auth middleware |
| DB | PostgreSQL (giữ nguyên) | Thêm `user_id` vào tất cả tables |

### Database Changes
```sql
-- Thêm bảng users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    stripe_customer_id VARCHAR,
    plan VARCHAR DEFAULT 'free',   -- free | pro | enterprise
    pages_used_this_month INT DEFAULT 0,
    pages_limit INT DEFAULT 20,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Thêm user_id vào documents
ALTER TABLE documents ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE documents ADD COLUMN is_public BOOLEAN DEFAULT FALSE;

-- Stripe subscriptions tracking
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    stripe_subscription_id VARCHAR UNIQUE,
    status VARCHAR,   -- active | canceled | past_due
    current_period_end TIMESTAMP
);
```

### API Changes
```python
# Middleware: verify JWT từ Supabase
@app.middleware("http")
async def auth_middleware(request, call_next):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user = verify_supabase_jwt(token)
    request.state.user = user
    return await call_next(request)

# Mọi endpoint kiểm tra user_id
@router.post("/api/docs/upload")
async def upload(file, current_user = Depends(get_current_user)):
    # check quota
    # save with user_id
```

### Frontend (Next.js migration)
```
app/
├── (auth)/
│   ├── login/page.tsx         ← Supabase Auth UI
│   └── register/page.tsx
├── dashboard/page.tsx         ← Danh sách sách của user
├── upload/page.tsx            ← Upload PDF/EPUB
├── books/[id]/
│   ├── page.tsx               ← Book processing status
│   ├── editor/page.tsx        ← Bilingual editor
│   └── publish/page.tsx       ← Publish settings
└── pricing/page.tsx           ← Plans + Stripe checkout
```

### Pricing tiers
| Plan | Giá | Quota | Features |
|------|-----|-------|---------|
| Free | $0 | 20 trang demo | 1 upload, watermark |
| Pro | $29/tháng | 500 trang/tháng | Unlimited uploads, Web-Book |
| Enterprise | $99/tháng | 2000 trang/tháng | API access, priority queue |

---

## Sub-project 3: Web-Book Publisher (Ưu tiên #3 — USP)

**Đây là điểm khác biệt với đối thủ.** Immersive Translate cho đọc song ngữ. TranslateABook xuất file. **Break The Barriers xuất bản Web-Book thương mại được.**

**Timeline:** 4 tuần

### Kết quả mong đợi
- User publish sách → nhận link: `books.yourdomain.com/ten-sach`
- Web-Book có: mục lục, phân chương, đổi ngôn ngữ 1 click
- Responsive trên mobile/tablet/desktop
- SEO: Open Graph, meta description, structured data
- Custom domain (Enterprise): `reader.client-domain.com`

### Tech Stack
| Component | Tool |
|---|---|
| Book template | Next.js App Router + Tailwind |
| Subdomain routing | Vercel/Nginx wildcard subdomain |
| Language switcher | i18n với stored translations |
| SEO | Next.js metadata API |

### Book URL structure
```
books.yourdomain.com/
├── {slug}/                    ← Landing page (cover, description, buy)
├── {slug}/read/               ← Reader (auth required nếu paywall)
├── {slug}/read/{chapter}      ← Chapter view
└── {slug}/read?lang=en        ← Language switch via query param
```

### Web-Book Features
```typescript
// Book reader component
interface WebBook {
  slug: string
  title: string
  cover_url: string
  languages: string[]          // ['vi', 'en', 'zh']
  chapters: Chapter[]
  is_paywall: boolean
  price_usd?: number
}

// Language switcher: 1 click
function LanguageSwitcher({ available, current }: Props) {
  return available.map(lang =>
    <button onClick={() => setLang(lang)}>{FLAG[lang]}</button>
  )
}
```

### Publishing flow
```
User → Dashboard → [Publish Book]
         ↓
    Chọn ngôn ngữ muốn publish
    Đặt tên slug (URL)
    Chọn: Public Free / Paywall / Private
    Thêm cover, description, meta
         ↓
    System tạo Web-Book page
    Gán subdomain
    Generate sitemap.xml
         ↓
    User nhận link → share, sell, distribute
```

---

## Sub-project 4: Translation Quality (Ưu tiên #4 — Competitive Edge)

**Timeline:** 3 tuần

### Kết quả mong đợi
- Dịch theo Chapter context (nhất quán nhân vật, văn phong)
- Translation Guide: user nhập danh sách nhân vật, thuật ngữ, văn phong
- Multi-model: Gemini (hiện tại) + DeepSeek (rẻ hơn) + Claude Sonnet
- Auto-detect: tên riêng không dịch, code blocks giữ nguyên

### Chapter-level Translation
```python
# Hiện tại: dịch từng block (1-3 spans)
# Upgrade: gom theo chapter, gửi kèm context

class ChapterTranslator:
    def translate_chapter(
        self,
        chapter_blocks: List[TextBlock],
        translation_guide: TranslationGuide,
        target_lang: str,
        model: str = "gemini-2.0-flash"
    ) -> List[TranslatedBlock]:
        # 1. Build chapter context string
        context = self._build_context(chapter_blocks)
        
        # 2. System prompt với Translation Guide
        system_prompt = f"""
        You are translating Chapter {chapter.num} of "{book.title}".
        
        Translation Guide:
        - Characters: {guide.characters}
        - Style: {guide.style}  # formal/casual/literary
        - Glossary: {guide.glossary}
        - Do NOT translate: {guide.keep_original}
        
        Preserve ALL HTML span placeholders [s:xxx] exactly.
        """
        
        # 3. Translate full chapter in 1 API call
        result = model.translate(context, system_prompt)
        
        # 4. Map back to individual spans
        return self._deinterpolate(result, chapter_blocks)
```

### Translation Guide UI
```
Dashboard > Book > Translation Guide
├── Book Style:     [ ] Literary  [ ] Technical  [ ] Casual
├── Characters:     [Name EN] → [Name VI] [+ Add]
├── Glossary:       [Term EN] → [Term VI] [+ Add]
├── Keep Original:  [ ] Code blocks  [ ] Brand names  [ ] Formulas
└── [Save Guide]    [Preview with Guide]
```

### Multi-model Support
```python
MODEL_REGISTRY = {
    "gemini-flash": GeminiProvider("gemini-2.0-flash"),
    "gemini-pro":   GeminiProvider("gemini-1.5-pro"),
    "deepseek":     DeepSeekProvider("deepseek-chat"),   # ~10x cheaper
    "claude-sonnet": AnthropicProvider("claude-sonnet-4-6"),  # best quality
}

# User chọn model trong dashboard
# Pro plan: gemini-flash (default)
# Enterprise: all models
```

---

## Sub-project 5: Monetization — Reader Paywall (Ưu tiên #5)

**Timeline:** 3 tuần

### Kết quả mong đợi
- User (author) đặt giá cho Web-Book của họ
- Reader trả tiền → unlock toàn bộ nội dung
- Author nhận 80% revenue (Break The Barriers giữ 20%)
- Analytics: lượt đọc, conversion rate, revenue per book

### Paywall flow
```
Reader → books.yourdomain.com/ten-sach
         ↓
    Đọc thử miễn phí (Chapter 1-2)
         ↓
    [Mua để đọc đầy đủ - $X.XX]  ← Stripe Checkout
         ↓
    Thanh toán → Nhận access token
         ↓
    Đọc toàn bộ sách
```

### Revenue split
```python
PLATFORM_FEE = 0.20  # 20% cho platform

# Stripe Connect: author nhận thẳng vào tài khoản của họ
# Platform nhận application_fee_amount tự động
```

### Analytics dashboard (for authors)
```
My Book: "Clean Code (Tiếng Việt)"
├── 📖 Lượt đọc: 1,247
├── 💰 Revenue: $342.50
├── 📊 Conversion: 12.3% (free → paid)
├── 🌍 Top countries: 🇻🇳 68%  🇺🇸 18%  🇸🇬 8%
└── 📈 Chart: Daily readers last 30 days
```

---

## Thứ tự ưu tiên và Dependencies

```
SP1 (Parser)
    │  ← Foundation: HTML quality affects everything
    ▼
SP2 (SaaS Platform)
    │  ← Revenue: auth + billing = paying users
    ▼
SP3 (Web-Book Publisher)      SP4 (Translation Quality)
    │  ← USP: differentiation      │  ← Quality: competitive edge
    │                              │
    └──────────────┬───────────────┘
                   ▼
            SP5 (Monetization)
                   │  ← Scale: additional revenue streams
```

**SP1 và SP2 phải song song một phần:** Trong khi build SaaS platform (Next.js frontend), parser upgrade có thể chạy song song ở backend.

---

## Fast Track (Nếu muốn revenue trong 8 tuần)

**Bỏ qua SP1 tạm thời**, bán với parser hiện tại:

```
Tuần 1-3:  SP2 core (auth + Stripe) với parser hiện tại
Tuần 4-5:  SP3 basic (Web-Book, không paywall)
Tuần 6-7:  SP1 parser upgrade (cải thiện chất lượng)
Tuần 8:    Launch beta, 10-20 early adopters
```

Tradeoff: User early sẽ thấy absolute-positioned HTML. Acceptable nếu document là sách thuần text (không nhiều ảnh).

---

## Tech Stack Summary (Full Product)

| Layer | Current | Upgrade to |
|-------|---------|-----------|
| Frontend | Vanilla HTML/JS | Next.js 14 + Tailwind + shadcn/ui |
| Auth | None | Supabase Auth |
| Billing | None | Stripe Subscriptions + Connect |
| Parser | pdftohtml | Docling + ebooklib |
| AI Translation | Gemini only | Gemini + DeepSeek + Claude |
| Hosting | Docker local | Vercel (frontend) + Hetzner VPS (backend) |
| DB | PostgreSQL local | Supabase PostgreSQL (managed) |
| Storage | Local disk | Supabase Storage / S3 |
| CDN | None | Cloudflare |

---

## KPIs theo từng Milestone

| Milestone | Timeline | KPI |
|-----------|----------|-----|
| SP1 done | Tuần 4 | Parser Docling test pass, HTML responsive |
| SP2 MVP | Tuần 9 | 10 beta users, Stripe connected |
| SP3 launch | Tuần 13 | 5 Web-Books published |
| SP2 growth | Tuần 16 | 50 paying users = $1,450 MRR |
| SP4+SP5 | Tuần 19 | 150 users = $4,350 MRR |
| Scale | Tháng 6+ | 200-300 users = $6,000-9,000 MRR |
