# Translation Quality Harness — Thiết kế (tier "max")

> **Ngày:** 2026-06-12
> **Branch:** `feat/translation-harness`
> **Trạng thái:** Spec để review

## 1. Bối cảnh & Mục tiêu

App `break_the_barriers` dịch tài liệu sang ngôn ngữ đích bằng `TranslatorV2` (Gemini, batch theo trang, có
glossary + translation memory + quality tier fast/balanced/high). Mục tiêu: thêm một **khung điều phối/đánh giá AI
dịch chạy TRONG production** — mỗi đoạn được dịch bởi **nhiều ứng viên Gemini**, **chấm điểm** và **tự chọn/refine**
bản tốt nhất để lưu vào `DBTranslation`, nâng chất lượng bản dịch người dùng thấy. Hoạt động với **mọi `target_lang`**.

**Quyết định đã chốt (brainstorming 2026-06-12):**
- Vai trò: **production — tự chọn bản dịch tốt nhất** (không phải eval offline).
- Nguồn ứng viên: **chỉ Gemini** (nhiều biến thể model/prompt/nhiệt độ), 1 API key, `google-genai` sẵn có.
- Chấm điểm: **rule-check → LLM-judge → refine nếu điểm thấp** (kết hợp).
- Tích hợp: **tier chất lượng mới `"max"` (opt-in)** — tier cũ giữ nguyên chi phí.

## 2. Kiến trúc

```
translate_page_batch(quality="max")
  └─ TranslationHarness.harmonize_page(blocks, target_lang, context, glossary)
       1) _generate_candidates → N=3 bản dịch-batch (model/temp/style khác nhau)
       2) _rule_check          → loại ứng viên lỗi cứng (không tốn lượt gọi)
       3) _judge (1 lượt batch) → mỗi block: best_idx + score(0-100) + critique
       4) _refine (1 lượt batch)→ block score < ngưỡng → cải thiện 1 vòng + rule-check lại
       5) winner → DBTranslation.translated_text; score → TM + DBPage.translation_quality
```

**Chi phí có chặn:** ~`N + 2` lượt gọi Gemini/trang (3 ứng viên + 1 judge + 1 refine = 5), **độc lập số block**
(judge & refine batch toàn trang trong 1 lượt). Tier `"max"` ≈ 5× chi phí tier `"high"`, opt-in.

## 3. Components (`app/services/translation_harness.py`)

Class `TranslationHarness`:

| Hàm | Trách nhiệm | I/O |
|---|---|---|
| `harmonize_page(blocks, target_lang, context, glossary)` | Điều phối 5 bước, trả winner/block | → `List[{span_id, text, score}]` |
| `_generate_candidates(blocks, target_lang, context, glossary)` | Sinh N bản dịch-batch qua `_batch_translate_variant(blocks, target_lang, context, glossary, model, temperature, style)` — helper mỏng mới trong harness (hoặc mở rộng `_gemini_batch_translate` nhận thêm `model/temperature/style`); KHÔNG route theo `quality` mà nhận model/temp/style tường minh | → `List[Dict[span_id, text]]` (mỗi phần tử 1 ứng viên) |
| `_rule_check(source, candidate, glossary)` | Loại ứng viên lỗi cứng | → `(valid: bool, reason: str)` |
| `_judge(blocks, cands_per_block, target_lang, context)` | 1 lượt Gemini structured-output JSON: mỗi block chọn `best_idx`+`score`+`critique` | → `List[{span_id, best_idx, score, critique}]` |
| `_refine(low_items, target_lang, context, glossary)` | 1 lượt batch cải thiện block điểm thấp (source + best + critique) | → `Dict[span_id, improved_text]` |

**Hằng số cấu hình (trong class):**
```python
CANDIDATE_VARIANTS = [
    ("gemini-3.1-flash-lite", 0.2, "faithful"),   # trung thành, nhiệt độ thấp
    ("gemini-3.5-flash",      0.4, "faithful"),
    ("gemini-3.5-flash",      0.7, "natural"),     # tự nhiên hơn, nhiệt độ cao
]
JUDGE_MODEL  = "gemini-3.5-flash"
REFINE_MODEL = "gemini-3.5-flash"
SCORE_THRESHOLD = 80          # block < ngưỡng → refine
MAX_CANDIDATES  = 3
```
`style` ("faithful"/"natural") chỉ đổi 1 câu chỉ dẫn trong prompt dịch; mọi thứ khác tái dùng đường batch hiện có.

## 4. Rule-check (deterministic, không gọi mạng)

Ứng viên 1 block bị loại nếu vi phạm bất kỳ:
- **Untranslated:** text trùng y nguyên bản gốc (sau strip/lower) khi nguồn có ≥1 từ chữ cái ≥4 (không tính fragment trang trí — tái dùng `TranslatorV2.is_decoration`).
- **Length ratio:** `len(cand)/len(src)` ngoài khoảng `[0.3, 3.0]` (cảnh báo lệch nghĩa/cụt). Khoảng nới cho cặp ngôn ngữ "súc tích" (vi/zh/ja đích → cận dưới 0.25).
- **Glossary:** thiếu ≥1 `target_term` bắt buộc mà bản gốc có `source_term` tương ứng.
- **Format:** số/placeholder/ký hiệu của bản gốc (regex `[\d%$€£#@]|\[[^\]]+\]`) biến mất hết khỏi ứng viên trong khi bản gốc có.
- **Rỗng** sau strip.

Nếu **mọi** ứng viên 1 block đều rớt → giữ ứng viên đầu (degrade), block → `needs_review`.

## 5. LLM-judge & Refine

**Judge (1 lượt/trang):** prompt structured-output — input = list block `{span_id, source, candidates[]}`; yêu cầu Gemini
trả JSON `[{span_id, best_idx (0..N-1), score (0-100), critique (ngắn)}]`, chấm theo **độ chính xác nghĩa, trung thành
với bản gốc, trôi chảy tự nhiên, đúng thuật ngữ glossary**. Parse JSON; lỗi/parse hỏng → fallback (xem §6).

**Refine (1 lượt/trang, chỉ block score < `SCORE_THRESHOLD`):** input = list `{source, best_candidate, critique, glossary}`;
yêu cầu Gemini xuất bản cải thiện. Rule-check lại; nếu pass → thay winner. Vẫn < ngưỡng sau refine → giữ bản refine
nhưng set `needs_review`.

## 6. Data flow & lưu trữ (không đổi schema)

- Input `blocks` (`{span_id, text}`) đến từ `translate_page_batch` (đã lọc TM-hit + decoration như cũ).
- Winner/block → `DBTranslation.translated_text` (như hiện tại).
- Điểm TB trang → `DBPage.translation_quality` (cột Float đã có).
- Winner + score → `TranslatorV2.tm_store(source, target_lang, winner, db, quality=score/100)` (TM tái dùng chéo tier).
- Block còn yếu sau refine → `DBPage.needs_review=True`, `review_reason="harness: <span_id> score <n>"`.
- **Không thêm bảng audit ở v1** (YAGNI). Nếu sau cần lưu ứng viên/critique để soi → thêm `DBHarnessRun` riêng (ngoài phạm vi).

## 7. Tích hợp

- `TranslatorV2.BATCH_MODELS` thêm khoá `"max": "gemini-3.5-flash"` (để `_resolve_batch_model` không vỡ khi fallback).
- `translate_page_batch`: nếu `quality == "max"` → gọi `TranslationHarness.harmonize_page(...)` thay cho 1 lượt
  `_gemini_batch_translate`; phần TM-lookup / decoration / glossary / lưu DB giữ nguyên cấu trúc.
- Router `/api/docs/{id}/translate` đã nhận `quality` (Pydantic) → chỉ cần cho phép giá trị `"max"`.
- **UI nút chọn tier `"max"`: đợt sau** (backend nhận `quality="max"` ngay; phạm vi spec này = backend).

## 8. Error handling (per-page guard, fail-soft — KHÔNG bao giờ để trang dịch thất bại)

- 1 ứng viên gen lỗi → bỏ ứng viên đó, chạy tiếp với số còn lại (tối thiểu 1).
- **Mọi** ứng viên gen lỗi → fallback `_gemini_batch_translate(quality="high")` (1 lượt).
- `_judge` lỗi/JSON hỏng → chọn ứng viên hợp lệ (rule-check pass) đầu tiên/block, score=70.
- `_refine` lỗi → giữ winner trước refine.
- Toàn bộ `harmonize_page` bọc try/except: lỗi bất ngờ → fallback đường `"high"` cũ + log.

## 9. Test (TDD, mock Gemini — không gọi mạng)

- `test_rule_check`: bảng case untranslated / length / glossary / format / empty → valid đúng.
- `test_judge_parse`: mock structured JSON (kể cả JSON bẩn/markdown fence) → parse + chọn best đúng; JSON hỏng → fallback.
- `test_harmonize_selects_winner`: mock `_generate_candidates`+`_judge`+`_refine` → chọn đúng winner; refine khi điểm thấp;
  mọi ứng viên rớt rule-check → degrade + needs_review.
- `test_translate_batch_max_tier`: `translate_page_batch(quality="max")` (mock harness) → lưu winner + `translation_quality`
  vào DB (SQLite in-memory), TM được store.
- `test_fallback_high`: ép `_generate_candidates` raise → đi đường `"high"`, trang vẫn dịch xong.

Chạy: `cd apps/break_the_barriers/backend && .venv/bin/pytest tests/ -v` (SQLite in-memory, mock `google-genai`).

## 10. Ngoài phạm vi (YAGNI)

- Đa nhà cung cấp (Claude/GPT) — đã chốt chỉ Gemini.
- Bảng audit ứng viên/critique (`DBHarnessRun`).
- UI chọn tier `"max"` (đợt sau).
- Back-translation scoring (đã chọn rule+judge+refine).
- Eval offline/benchmark (đã chốt vai trò production).
