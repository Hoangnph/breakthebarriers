# SP7 TranslatorV2 — High-Fidelity AI Translation Harness

**Goal:** Thay thế pipeline dịch span-by-span (60-90 Gemini calls/trang) bằng batch page-level pipeline (1-3 calls/trang) với document context, glossary enforcement, translation memory, và prompt caching.

---

## Problem Analysis

| Metric | Current (V1) | Target (V2) |
|--------|-------------|-------------|
| API calls / trang | 60–90 | 1–3 |
| Chi phí / 33 trang | ~$0.15 | ~$0.005 |
| Thời gian / trang | 60–120s | 5–15s |
| Terminology consistency | ~30% | 95%+ |
| Cross-page context | ❌ | ✅ |

---

## Architecture

```
[Document Context Extraction]  1 Gemini call / tài liệu → documents.ai_metadata
         ↓
[Terminology Pre-pass]         1 Gemini call / tài liệu → document_glossaries
         ↓
[Per-page Batch Translation]   1 Gemini call / trang (3 concurrent)
    ├── Check Translation Memory → reuse if hit ≥ 0.8
    ├── Gemini CachedContent (prompt cache, TTL 1h)
    ├── Structured JSON output (response_mime_type="application/json")
    └── Store results → translations + translation_memory
         ↓
[Quality Spot-check]           Chỉ quality="high": verify placeholders + glossary
```

---

## New DB Schema

### `documents.ai_metadata` (JSON column, thêm vào bảng hiện có)

```sql
ALTER TABLE documents ADD COLUMN ai_metadata JSONB DEFAULT '{}';
```

```json
{
  "title": "Đạo Đức Kinh",
  "author": "Lão Tử",
  "domain": "classical_philosophy",
  "style": "literary_poetic",
  "detected_lang": "vi",
  "context_extracted_at": "2026-06-01T09:00:00Z"
}
```

### `document_glossaries` (bảng mới)

```sql
CREATE TABLE document_glossaries (
    id          VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    is_manual   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (document_id, source_term, target_lang)
);
CREATE INDEX idx_glossaries_doc_lang ON document_glossaries(document_id, target_lang);
```

### `translation_memory` (bảng mới, global)

```sql
CREATE TABLE translation_memory (
    source_hash VARCHAR(64) PRIMARY KEY,  -- SHA256(source_text + "|" + target_lang)
    source_text TEXT NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    translated  TEXT NOT NULL,
    quality     FLOAT DEFAULT 1.0,
    hit_count   INT DEFAULT 0,
    last_used   TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_tm_lang ON translation_memory(target_lang);
```

---

## Component Design

### `TranslatorV2` class (`services/translator_v2.py`)

```python
class TranslatorV2:
    MODEL = "gemini-2.5-flash"
    MAX_CONCURRENT = 3
    TM_QUALITY_THRESHOLD = 0.8

    @staticmethod
    def extract_document_context(doc_id, sample_html_pages, db) -> dict:
        """1 Gemini call. Returns {title, author, domain, style, key_terms[]}."""

    @staticmethod
    def build_glossary(doc_id, target_lang, context, db) -> list[dict]:
        """1 Gemini call. Returns [{source_term, target_term}]."""

    @staticmethod
    def translate_page_batch(doc_id, page_num, target_lang, context, glossary,
                              cached_content_name, db) -> dict:
        """
        1 Gemini call per page (uses cached system prompt).
        Input: all blocks as JSON array.
        Output: {block_id: translated_text} dict.
        Falls back to V1 line-by-line if JSON parse fails.
        """

    @staticmethod
    async def translate_all_v2(doc_id, target_lang, quality, db):
        """
        Full pipeline: context → glossary → parallel page translation.
        MAX_CONCURRENT=3 semaphore.
        """
```

### Fallback Chain

```
Gemini batch call fails
  → Retry (backoff: 1s, 2s, 4s, 8s)
  → Split page into 2 half-batches
  → Fallback to V1 line-by-line for this page
  → Mark page: needs_review=TRUE, review_reason="batch_failed"

JSON parse error
  → Retry with stricter JSON prompt
  → Regex-extract JSON from markdown wrapper
  → Fallback to V1

Placeholder [s:id] missing in output
  → Re-inject from original spans
  → Flag: needs_review=TRUE, review_reason="placeholder_missing"
```

---

## Prompt Design

### Phase 0 — Context Extraction

```
You are analyzing a PDF document to identify its metadata.
Return ONLY valid JSON, no markdown.

Sample text (first 3 pages):
{sample}

JSON schema:
{
  "title": "string",
  "author": "string or null",
  "domain": "one of: classical_philosophy|technical|literature|medicine|law|general",
  "style": "one of: literary_poetic|formal_academic|conversational|technical_precise",
  "key_terms": ["term1", "term2", ...]  // up to 15 domain-specific terms
}
```

### Phase 1 — Glossary Pre-pass

```
You are establishing translation standards for '{title}' by {author}.
Domain: {domain}. Target language: {lang_name}.

Provide authoritative, consistent translations for these key terms.
Return ONLY valid JSON array, no markdown.

Terms to translate: {key_terms}

JSON schema:
[{"source": "term", "target": "translation"}, ...]
```

### Phase 2 — Batch Page Translation (Cached system prompt)

**System (cached):**
```
You are a professional translator for '{title}' by {author}.
Domain: {domain}. Style: {style}. Target language: {lang_name}.

MANDATORY GLOSSARY — use these translations exactly:
{glossary_formatted}

RULES:
1. Preserve ALL [s:span_id] placeholders in exact positions
2. Follow glossary strictly — no improvisation on listed terms
3. Maintain the {style} tone throughout
4. Return ONLY valid JSON matching the schema below
5. If a block is already in {lang_name}, return it unchanged
```

**User (per page):**
```
Translate ALL blocks to {lang_name}.

Input:
[{"id": "b0", "text": "..."}, {"id": "b1", "text": "..."}, ...]

Output JSON schema:
{"translations": [{"id": "b0", "text": "translated..."}, ...]}
```

---

## Quality Tiers

| Tier | Pipeline | Calls/page | Use case |
|------|----------|-----------|---------|
| `fast` | Batch only (no TM check) | 1 | Draft preview |
| `balanced` | TM check + Batch | 1-2 | Default production |
| `high` | TM check + Batch + Verify pass | 2-3 | Publication-grade |

---

## Pages Table Extension

```sql
ALTER TABLE pages ADD COLUMN needs_review     BOOLEAN DEFAULT FALSE;
ALTER TABLE pages ADD COLUMN review_reason    VARCHAR DEFAULT NULL;
ALTER TABLE pages ADD COLUMN translation_quality FLOAT DEFAULT NULL;
```

---

## New API Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/api/docs/{id}/extract-context` | Run context extraction + glossary |
| `GET` | `/api/docs/{id}/glossary?lang=vi` | List glossary terms |
| `POST` | `/api/docs/{id}/glossary` | Add manual term |
| `PUT` | `/api/docs/{id}/glossary/{term_id}` | Edit term |
| `DELETE` | `/api/docs/{id}/glossary/{term_id}` | Delete term |

`POST /api/docs/{id}/translate-all` — thêm `use_v2: bool = True` param (backward compat).

---

## Migration SQL (`migrate_sp7.sql`)

```sql
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ai_metadata JSONB DEFAULT '{}';
ALTER TABLE pages     ADD COLUMN IF NOT EXISTS needs_review     BOOLEAN DEFAULT FALSE;
ALTER TABLE pages     ADD COLUMN IF NOT EXISTS review_reason    VARCHAR;
ALTER TABLE pages     ADD COLUMN IF NOT EXISTS translation_quality FLOAT;

CREATE TABLE IF NOT EXISTS document_glossaries (
    id          VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    is_manual   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (document_id, source_term, target_lang)
);
CREATE INDEX IF NOT EXISTS idx_glossaries_doc_lang ON document_glossaries(document_id, target_lang);

CREATE TABLE IF NOT EXISTS translation_memory (
    source_hash VARCHAR(64) PRIMARY KEY,
    source_text TEXT NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    translated  TEXT NOT NULL,
    quality     FLOAT DEFAULT 1.0,
    hit_count   INT DEFAULT 0,
    last_used   TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tm_lang ON translation_memory(target_lang);
```

---

## Self-Review

- ✅ Không TBD hay placeholder
- ✅ Backward compatible: `use_v2=False` → V1 pipeline cũ
- ✅ Fallback chain đầy đủ: không trang nào bị bỏ sót
- ✅ TM cleanup: cron job hàng tháng (out of scope for this SP)
- ✅ Prompt caching: xóa sớm sau job xong (tránh charge idle time)
- ✅ Concurrency: asyncio.Semaphore(3) tránh rate limit
- ✅ Tests: mock Gemini client, test từng phase độc lập
