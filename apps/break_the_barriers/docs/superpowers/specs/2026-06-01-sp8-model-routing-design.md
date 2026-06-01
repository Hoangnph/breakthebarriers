# SP8 Model Routing — Design Spec

**Goal:** Route Gemini model selection theo vai trò + quality tier: model mạnh cho context/glossary (1×/doc, quyết định chất lượng cả sách), model rẻ+nhanh cho batch translation theo tier.

---

## Model Registry

Thay `MODEL = "gemini-2.5-flash"` trong `TranslatorV2` bằng:

```python
ANCHOR_MODEL = "gemini-3.5-flash"          # context + glossary (1×/doc)
BATCH_MODELS = {
    "fast":     "gemini-3.1-flash-lite",
    "balanced": "gemini-3.1-flash-lite",
    "high":     "gemini-3.5-flash",
}
MODEL = ANCHOR_MODEL                        # backward-compat alias
```

## Routing

| Call | Model |
|------|-------|
| `extract_document_context` | `ANCHOR_MODEL` |
| `build_glossary_from_context` | `ANCHOR_MODEL` |
| `_gemini_batch_translate` | `_resolve_batch_model(quality)` |

## Helper

```python
@staticmethod
def _resolve_batch_model(quality: str) -> str:
    return TranslatorV2.BATCH_MODELS.get(quality, TranslatorV2.BATCH_MODELS["balanced"])
```

## Rationale

- **Context + glossary** chạy 1 lần/doc nhưng cascade ra mọi trang → đầu tư `gemini-3.5-flash` (chất lượng vượt Pro năm ngoái).
- **Batch translation** tốn token nhất, chạy mỗi trang → `gemini-3.1-flash-lite` ($0.25/$1.50, nhanh 1.4s) cho fast/balanced; `gemini-3.5-flash` cho high.

## Test

- `test_resolve_batch_model`: fast/balanced → flash-lite, high → 3.5-flash, invalid → balanced default.
- Mock path không phụ thuộc model name → không cần test API call.

## Scope

Chỉ `translator_v2.py`. ~15 dòng. Không chạm DB/API/frontend. Backward-compat qua `MODEL` alias.
