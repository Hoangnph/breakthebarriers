# Translation Quality Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm tier dịch `"max"` chạy production: mỗi trang sinh 3 ứng viên Gemini → rule-check → LLM-judge → refine → lưu bản tốt nhất + điểm vào DB.

**Architecture:** Service mới `TranslationHarness` (Gemini-only) cắm vào `TranslatorV2.translate_page_batch` khi `quality=="max"`. Mọi nhánh lỗi fail-soft về tier `"high"`. Không đổi schema DB.

**Tech Stack:** Python, `google-genai` (Gemini), SQLAlchemy, pytest (mock — không gọi mạng).

**Spec:** `docs/superpowers/specs/2026-06-12-translation-quality-harness-design.md`

**Môi trường:** chạy mọi lệnh từ `apps/break_the_barriers/backend`; test = `.venv/bin/pytest`. Branch `feat/translation-harness`.

---

## File Structure

| File | Trạng thái | Trách nhiệm |
|---|---|---|
| `app/services/translation_harness.py` | tạo mới | `TranslationHarness`: rule-check, candidates, judge, refine, harmonize_page |
| `app/services/translator_v2.py` | sửa | `BATCH_MODELS["max"]`; nhánh `quality=="max"` trong `translate_page_batch` |
| `tests/test_translation_harness.py` | tạo mới | unit test harness (mock Gemini ở mức method) |
| `tests/test_translator_v2.py` | sửa | test tích hợp tier `max` ghi winner+score+TM |

**Tái dùng:** `TranslatorV2.is_decoration`, `_format_glossary`, `LANG_NAMES`, `tm_store`, `Translator.deinterpolate_translation`.

---

## Task 1: Skeleton + `_rule_check` + `_parse_judge_json`

**Files:**
- Create: `app/services/translation_harness.py`
- Create: `tests/test_translation_harness.py`

- [ ] **Step 1: Viết test fail trước**

Tạo `tests/test_translation_harness.py`:

```python
from backend.app.services.translation_harness import TranslationHarness as H


def test_rule_check_empty_and_untranslated():
    assert H._rule_check("Hello world", "", [], "vi")[0] is False           # rỗng
    assert H._rule_check("Hello world", "Hello world", [], "vi")[0] is False  # chưa dịch
    assert H._rule_check("Hello world", "Xin chào thế giới", [], "vi")[0] is True


def test_rule_check_length_glossary_format():
    # quá dài (>3x)
    assert H._rule_check("Hi", "a" * 50, [], "vi")[0] is False
    # thiếu glossary term
    gl = [{"source": "AI", "target": "Trí tuệ nhân tạo"}]
    assert H._rule_check("AI is here", "Nó ở đây", gl, "vi")[0] is False
    assert H._rule_check("AI is here", "Trí tuệ nhân tạo ở đây", gl, "vi")[0] is True
    # mất format số
    assert H._rule_check("Pay 50%", "Tra tien", [], "vi")[0] is False
    assert H._rule_check("Pay 50%", "Trả 50%", [], "vi")[0] is True


def test_parse_judge_json_handles_fences():
    raw = '```json\n[{"id":"b0","best_idx":1,"score":90,"critique":"ok"}]\n```'
    parsed = H._parse_judge_json(raw)
    assert parsed and parsed[0]["best_idx"] == 1
    assert H._parse_judge_json("not json") is None
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: translation_harness`)

Run: `.venv/bin/pytest tests/test_translation_harness.py -v`

- [ ] **Step 3: Tạo `app/services/translation_harness.py`**

```python
"""Translation quality harness (tier "max"): đa ứng viên Gemini → rule-check →
LLM-judge → refine → chọn bản tốt nhất. Gemini-only, fail-soft về "high"."""
import os
import re
import json
import logging
from typing import List, Dict, Tuple, Optional

from backend.app.services.translator_v2 import TranslatorV2

logger = logging.getLogger(__name__)

_SYM = re.compile(r"\[[^\]]+\]|[\d%$€£#@]")


class TranslationHarness:
    CANDIDATE_VARIANTS = [
        ("gemini-3.1-flash-lite", 0.2, "faithful"),
        ("gemini-3.5-flash", 0.4, "faithful"),
        ("gemini-3.5-flash", 0.7, "natural"),
    ]
    JUDGE_MODEL = "gemini-3.5-flash"
    REFINE_MODEL = "gemini-3.5-flash"
    SCORE_THRESHOLD = 80
    MAX_CANDIDATES = 3

    @staticmethod
    def _rule_check(source: str, candidate: str, glossary: List[dict],
                    target_lang: str) -> Tuple[bool, str]:
        src = (source or "").strip()
        cand = (candidate or "").strip()
        if not cand:
            return (False, "empty")
        if not TranslatorV2.is_decoration(src) and cand.lower() == src.lower():
            return (False, "untranslated")
        if src:
            ratio = len(cand) / len(src)
            lo = 0.25 if target_lang in ("vi", "zh", "ja", "ko") else 0.3
            if ratio < lo or ratio > 3.0:
                return (False, f"length_ratio {ratio:.2f}")
        for e in (glossary or []):
            s, t = (e.get("source") or ""), (e.get("target") or "")
            if s and s.lower() in src.lower() and t and t.lower() not in cand.lower():
                return (False, f"glossary_missing {t}")
        if _SYM.search(src) and not _SYM.search(cand):
            return (False, "format_lost")
        return (True, "ok")

    @staticmethod
    def _parse_judge_json(text: str) -> Optional[list]:
        t = (text or "").strip()
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE).strip()
        try:
            data = json.loads(t)
        except Exception:
            return None
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("results") or data.get("items")
        return None
```

- [ ] **Step 4: Run → PASS** (3 passed)

Run: `.venv/bin/pytest tests/test_translation_harness.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/services/translation_harness.py tests/test_translation_harness.py
git commit -m "feat(harness): TranslationHarness skeleton + rule_check + judge json parse"
```

---

## Task 2: `_judge` (chọn best có chặn lỗi)

**Files:**
- Modify: `app/services/translation_harness.py`
- Modify: `tests/test_translation_harness.py`

- [ ] **Step 1: Thêm test fail**

Thêm vào `tests/test_translation_harness.py`:

```python
def test_judge_single_and_empty_candidates():
    blocks = [{"text": "Hello", "span_ids": ["s1"]}]
    assert H._judge(blocks, [], "vi", {})[0]["score"] == 0           # 0 ứng viên
    one = H._judge(blocks, [["Xin chào"]], "vi", {})                  # 1 ứng viên → idx 0
    assert one[0]["best_idx"] == 0 and one[0]["score"] >= 0


def test_judge_uses_parsed_result(monkeypatch):
    blocks = [{"text": "Hello", "span_ids": ["s1"]},
              {"text": "World", "span_ids": ["s2"]}]
    cands = [["A0", "B0"], ["A1", "B1"]]
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(H, "_judge_call",
                        staticmethod(lambda items: [
                            {"id": "b0", "best_idx": 1, "score": 92, "critique": "good"},
                            {"id": "b1", "best_idx": 0, "score": 60, "critique": "weak"}]))
    out = H._judge(blocks, cands, "vi", {})
    assert out[0]["best_idx"] == 1 and out[0]["score"] == 92
    assert out[1]["best_idx"] == 0 and out[1]["score"] == 60
```

- [ ] **Step 2: Run → FAIL** (`_judge` chưa có)

Run: `.venv/bin/pytest tests/test_translation_harness.py -k judge -v`

- [ ] **Step 3: Thêm `_judge` + `_judge_call` vào class**

```python
    @staticmethod
    def _judge_call(items: list) -> Optional[list]:
        """1 lượt Gemini judge structured-output. Tách riêng để test mock được.
        items: [{"id","source","candidates":[...]}] → [{"id","best_idx","score","critique"}]."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            "You judge translations. For each item pick the BEST candidate by meaning "
            "accuracy, faithfulness to source, fluency, and terminology.\n"
            'Return ONLY JSON list: '
            '[{"id":"b0","best_idx":<0-based int>,"score":<0-100 int>,"critique":"short"}].\n'
            f"Items:\n{json.dumps(items, ensure_ascii=False)}"
        )
        resp = client.models.generate_content(
            model=TranslationHarness.JUDGE_MODEL, contents=prompt,
            config={"response_mime_type": "application/json"})
        return TranslationHarness._parse_judge_json(resp.text)

    @staticmethod
    def _judge(blocks, candidates, target_lang, context) -> List[dict]:
        n = len(candidates)
        if n == 0:
            return [{"best_idx": 0, "score": 0, "critique": "no candidates"} for _ in blocks]
        if n == 1:
            return [{"best_idx": 0, "score": 75, "critique": "single"} for _ in blocks]
        items = [{"id": f"b{bi}", "source": b["text"],
                  "candidates": [candidates[ci][bi] for ci in range(n)]}
                 for bi, b in enumerate(blocks)]
        try:
            parsed = TranslationHarness._judge_call(items)
            if not parsed:
                raise ValueError("judge parse failed")
            by_id = {p.get("id"): p for p in parsed}
            out = []
            for bi in range(len(blocks)):
                p = by_id.get(f"b{bi}", {})
                idx = int(p.get("best_idx", 0))
                idx = idx if 0 <= idx < n else 0
                out.append({"best_idx": idx, "score": int(p.get("score", 70)),
                            "critique": str(p.get("critique", ""))})
            return out
        except Exception as e:
            logger.warning(f"judge failed: {e}")
            return [{"best_idx": 0, "score": 70, "critique": "judge error"} for _ in blocks]
```

- [ ] **Step 4: Run → PASS**

Run: `.venv/bin/pytest tests/test_translation_harness.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/translation_harness.py tests/test_translation_harness.py
git commit -m "feat(harness): _judge selects best candidate per block (fail-soft)"
```

---

## Task 3: `_generate_candidates` + `_batch_translate_variant`

**Files:**
- Modify: `app/services/translation_harness.py`
- Modify: `tests/test_translation_harness.py`

- [ ] **Step 1: Thêm test fail**

```python
def test_generate_candidates_aggregates(monkeypatch):
    blocks = [{"text": "Hello", "span_ids": ["s1"]}]
    calls = {"n": 0}

    def fake_variant(blocks, tl, ctx, gl, model, temp, style):
        calls["n"] += 1
        return [f"{style}-{model}"]
    monkeypatch.setattr(H, "_batch_translate_variant", staticmethod(fake_variant))
    cands = H._generate_candidates(blocks, "vi", {}, [])
    assert calls["n"] == 3 and len(cands) == 3       # 3 biến thể
    assert all(len(c) == 1 for c in cands)


def test_generate_candidates_skips_failed_variant(monkeypatch):
    blocks = [{"text": "Hello", "span_ids": ["s1"]}]
    seq = [None, ["ok"], None]
    monkeypatch.setattr(H, "_batch_translate_variant",
                        staticmethod(lambda *a, **k: seq.pop(0)))
    cands = H._generate_candidates(blocks, "vi", {}, [])
    assert len(cands) == 1                            # bỏ 2 cái None
```

- [ ] **Step 2: Run → FAIL**

Run: `.venv/bin/pytest tests/test_translation_harness.py -k candidates -v`

- [ ] **Step 3: Thêm vào class**

```python
    @staticmethod
    def _batch_translate_variant(blocks, target_lang, context, glossary,
                                 model, temperature, style) -> Optional[List[str]]:
        """Dịch-batch 1 lượt với model/temp/style tường minh. → list[str] aligned blocks."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            lang_name = TranslatorV2.LANG_NAMES.get(target_lang, target_lang)
            glossary_str = TranslatorV2._format_glossary(glossary)
            style_line = ("Prioritize literal faithfulness to the source meaning.\n"
                          if style == "faithful"
                          else "Prioritize natural fluent phrasing while preserving meaning.\n")
            input_json = json.dumps(
                [{"id": f"b{i}", "text": b["text"]} for i, b in enumerate(blocks)],
                ensure_ascii=False)
            prompt = (
                f"Professional translator. Domain: {context.get('domain', 'general')}. "
                f"Target: {lang_name}.\nGLOSSARY (follow exactly):\n{glossary_str}\n{style_line}"
                'Return ONLY JSON {"translations":[{"id":"b0","text":"..."},...]}.\n'
                f"Input:\n{input_json}")
            resp = client.models.generate_content(
                model=model, contents=prompt,
                config={"response_mime_type": "application/json", "temperature": temperature})
            tmap = {it["id"]: it["text"] for it in json.loads(resp.text)["translations"]}
            return [tmap.get(f"b{i}", blocks[i]["text"]) for i in range(len(blocks))]
        except Exception as e:
            logger.warning(f"variant translate failed ({model}/{style}): {e}")
            return None

    @staticmethod
    def _generate_candidates(blocks, target_lang, context, glossary) -> List[List[str]]:
        out = []
        for model, temp, style in TranslationHarness.CANDIDATE_VARIANTS:
            c = TranslationHarness._batch_translate_variant(
                blocks, target_lang, context, glossary, model, temp, style)
            if c is not None:
                out.append(c)
        return out
```

- [ ] **Step 4: Run → PASS**

Run: `.venv/bin/pytest tests/test_translation_harness.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/translation_harness.py tests/test_translation_harness.py
git commit -m "feat(harness): generate N candidate batch-translations (model/temp/style)"
```

---

## Task 4: `_refine`

**Files:**
- Modify: `app/services/translation_harness.py`
- Modify: `tests/test_translation_harness.py`

- [ ] **Step 1: Thêm test fail**

```python
def test_refine_maps_improved_back(monkeypatch):
    items = [{"block_index": 2, "source": "Hi", "current": "x", "critique": "weak"}]
    monkeypatch.setattr(H, "_refine_call",
                        staticmethod(lambda payload: {"r0": "Xin chào"}))
    out = H._refine(items, "vi", {}, [])
    assert out == {2: "Xin chào"}


def test_refine_empty_returns_empty():
    assert H._refine([], "vi", {}, []) == {}
```

- [ ] **Step 2: Run → FAIL**

Run: `.venv/bin/pytest tests/test_translation_harness.py -k refine -v`

- [ ] **Step 3: Thêm vào class**

```python
    @staticmethod
    def _refine_call(payload: list) -> Dict[str, str]:
        """1 lượt Gemini refine. payload:[{"id","source","current","critique"}] → {id:text}."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {}
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            "Improve each translation using its critique. Preserve meaning, numbers, glossary.\n"
            'Return ONLY JSON {"items":[{"id":"r0","text":"<improved>"},...]}.\n'
            f"Input:\n{json.dumps(payload, ensure_ascii=False)}")
        resp = client.models.generate_content(
            model=TranslationHarness.REFINE_MODEL, contents=prompt,
            config={"response_mime_type": "application/json"})
        return {it["id"]: it["text"] for it in json.loads(resp.text).get("items", [])}

    @staticmethod
    def _refine(items, target_lang, context, glossary) -> Dict[int, str]:
        if not items:
            return {}
        payload = [{"id": f"r{k}", "source": it["source"], "current": it["current"],
                    "critique": it["critique"]} for k, it in enumerate(items)]
        try:
            tmap = TranslationHarness._refine_call(payload)
        except Exception as e:
            logger.warning(f"refine failed: {e}")
            return {}
        return {items[k]["block_index"]: tmap[f"r{k}"]
                for k in range(len(items)) if f"r{k}" in tmap}
```

- [ ] **Step 4: Run → PASS** (9 passed)

Run: `.venv/bin/pytest tests/test_translation_harness.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/services/translation_harness.py tests/test_translation_harness.py
git commit -m "feat(harness): _refine improves low-score blocks in one batch"
```

---

## Task 5: `harmonize_page` (orchestrator)

**Files:**
- Modify: `app/services/translation_harness.py`
- Modify: `tests/test_translation_harness.py`

- [ ] **Step 1: Thêm test fail**

```python
def test_harmonize_selects_winner_and_refines(monkeypatch):
    blocks = [{"text": "Hello", "span_ids": ["s1"]},
              {"text": "World", "span_ids": ["s2"]}]
    monkeypatch.setattr(H, "_generate_candidates",
                        staticmethod(lambda *a: [["Xin chào", "Thế giới"],
                                                 ["Chào", "Quả đất"]]))
    monkeypatch.setattr(H, "_judge", staticmethod(lambda *a: [
        {"best_idx": 0, "score": 95, "critique": "great"},
        {"best_idx": 1, "score": 60, "critique": "improve"}]))   # block 2 thấp → refine
    monkeypatch.setattr(H, "_refine", staticmethod(lambda *a, **k: {1: "Thế giới (đã sửa)"}))
    results, scores = H.harmonize_page(blocks, "vi", {}, [])
    assert results[0] == "Xin chào" and scores[0] == 95
    assert results[1] == "Thế giới (đã sửa)" and scores[1] >= H.SCORE_THRESHOLD


def test_harmonize_returns_none_when_no_candidates(monkeypatch):
    monkeypatch.setattr(H, "_generate_candidates", staticmethod(lambda *a: []))
    assert H.harmonize_page([{"text": "x", "span_ids": ["s1"]}], "vi", {}, []) is None
```

- [ ] **Step 2: Run → FAIL**

Run: `.venv/bin/pytest tests/test_translation_harness.py -k harmonize -v`

- [ ] **Step 3: Thêm `harmonize_page` vào class**

```python
    @staticmethod
    def harmonize_page(blocks, target_lang, context,
                       glossary) -> Optional[Tuple[List[str], List[int]]]:
        """5 bước: candidates → rule-check → judge → refine → (results, scores).
        Trả None khi KHÔNG sinh được ứng viên nào (caller fallback "high")."""
        candidates = TranslationHarness._generate_candidates(blocks, target_lang, context, glossary)
        if not candidates:
            return None
        n = len(candidates)
        valid = []
        for bi, b in enumerate(blocks):
            vs = [ci for ci in range(n)
                  if TranslationHarness._rule_check(
                      b["text"], candidates[ci][bi], glossary, target_lang)[0]]
            valid.append(vs if vs else [0])     # degrade: giữ ứng viên đầu
        judged = TranslationHarness._judge(blocks, candidates, target_lang, context)
        results, scores, refine_items = [], [], []
        for bi, b in enumerate(blocks):
            j = judged[bi]
            idx = j["best_idx"] if j["best_idx"] in valid[bi] else valid[bi][0]
            results.append(candidates[idx][bi])
            scores.append(j["score"])
            if j["score"] < TranslationHarness.SCORE_THRESHOLD:
                refine_items.append({"block_index": bi, "source": b["text"],
                                     "current": results[bi], "critique": j["critique"]})
        if refine_items:
            improved = TranslationHarness._refine(refine_items, target_lang, context, glossary)
            for bi, txt in improved.items():
                if TranslationHarness._rule_check(blocks[bi]["text"], txt, glossary, target_lang)[0]:
                    results[bi] = txt
                    scores[bi] = max(scores[bi], TranslationHarness.SCORE_THRESHOLD)
        return (results, scores)
```

- [ ] **Step 4: Run → PASS** (11 passed)

Run: `.venv/bin/pytest tests/test_translation_harness.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/services/translation_harness.py tests/test_translation_harness.py
git commit -m "feat(harness): harmonize_page orchestrates candidates/judge/refine"
```

---

## Task 6: Tích hợp tier `"max"` vào `translate_page_batch`

**Files:**
- Modify: `app/services/translator_v2.py:20-24` (BATCH_MODELS), `:263-310` (dispatch)
- Modify: `tests/test_translator_v2.py`

- [ ] **Step 1: Thêm test fail**

Thêm vào `tests/test_translator_v2.py` (kiểm tên fixture session `db_session` trong conftest; đổi nếu khác):

```python
def test_translate_batch_max_tier_writes_winner_and_score(db_session, monkeypatch):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    from backend.app.services.translator_v2 import TranslatorV2
    from backend.app.services import translation_harness as TH

    doc_id = "maxdoc"
    db_session.add(DBDocument(id=doc_id, filename="d.pdf", total_pages=1, status="extracted"))
    db_session.add(DBPage(document_id=doc_id, page_num=1, status="raw",
                          original_html='<p><span id="s1">Artificial Intelligence</span></p>'))
    db_session.add(DBTranslation(document_id=doc_id, page_num=1, span_id="s1",
                                 original_text="Artificial Intelligence"))
    db_session.commit()

    # harness trả winner + score (mock — không gọi Gemini)
    monkeypatch.setattr(TH.TranslationHarness, "harmonize_page",
                        staticmethod(lambda blocks, *a: (["Trí tuệ nhân tạo"] * len(blocks),
                                                          [93] * len(blocks))))
    TranslatorV2.translate_page_batch(doc_id, 1, "vi", {"domain": "tech"}, [],
                                      db_session, quality="max")
    row = db_session.query(DBTranslation).filter_by(document_id=doc_id, page_num=1,
                                                     span_id="s1").first()
    assert row.translated_text == "Trí tuệ nhân tạo"
    page = db_session.query(DBPage).filter_by(document_id=doc_id, page_num=1).first()
    assert page.translation_quality and abs(page.translation_quality - 0.93) < 0.01
```

- [ ] **Step 2: Run → FAIL** (nhánh max chưa có → translated_text None)

Run: `.venv/bin/pytest tests/test_translator_v2.py -k max_tier -v`

- [ ] **Step 3: Thêm `"max"` vào BATCH_MODELS**

Tại `app/services/translator_v2.py`, trong dict `BATCH_MODELS` (dòng ~20-24), thêm dòng:

```python
        "max":      "gemini-3.5-flash",
```

- [ ] **Step 4: Thêm nhánh `max` trong `translate_page_batch`**

Tại `app/services/translator_v2.py`, trong `if blocks_to_translate:` (dòng ~263), thay đoạn:

```python
        if blocks_to_translate:
            if is_pytest or not api_key:
```

bằng (chèn nhánh max TRƯỚC nhánh mock, dùng cờ `handled`):

```python
        if blocks_to_translate:
            handled = False
            if quality == "max":
                from backend.app.services.translation_harness import TranslationHarness
                harm = TranslationHarness.harmonize_page(
                    blocks_to_translate, target_lang, context, glossary)
                if harm is not None:
                    results, scores = harm
                    if scores:
                        page.translation_quality = round(sum(scores) / len(scores) / 100.0, 3)
                    for block, translated, score in zip(blocks_to_translate, results, scores):
                        if TranslatorV2.is_decoration(block["text"]):
                            continue
                        TranslatorV2.tm_store(block["text"], target_lang, translated,
                                              db, quality=score / 100.0)
                        if score < TranslationHarness.SCORE_THRESHOLD:
                            page.needs_review = True
                            page.review_reason = f"harness low score {score}"
                        if len(block["span_ids"]) == 1:
                            translations[block["span_ids"][0]] = translated
                        else:
                            parts = Translator.deinterpolate_translation(translated, block["span_ids"])
                            translations.update(parts)
                    handled = True
            if handled:
                pass
            elif is_pytest or not api_key:
```

(Phần `elif is_pytest...` và `else:` phía sau GIỮ NGUYÊN — chỉ đổi `if is_pytest` đầu thành `elif is_pytest`. Khi `quality=="max"` mà harness lỗi/None → `handled=False` → rơi xuống mock/`high` cũ = fail-soft.)

- [ ] **Step 5: Run → PASS**

Run: `.venv/bin/pytest tests/test_translator_v2.py -k max_tier -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/translator_v2.py tests/test_translator_v2.py
git commit -m "feat(translate): wire tier 'max' to TranslationHarness (fail-soft to high)"
```

---

## Task 7: Verify toàn bộ + fallback

**Files:** không sửa code — verify.

- [ ] **Step 1: Test fallback khi harness trả None**

Thêm vào `tests/test_translator_v2.py`:

```python
def test_max_tier_falls_back_when_harness_none(db_session, monkeypatch):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    from backend.app.services.translator_v2 import TranslatorV2
    from backend.app.services import translation_harness as TH

    doc_id = "maxfb"
    db_session.add(DBDocument(id=doc_id, filename="d.pdf", total_pages=1, status="extracted"))
    db_session.add(DBPage(document_id=doc_id, page_num=1, status="raw",
                          original_html='<p><span id="s1">Hello world friend</span></p>'))
    db_session.add(DBTranslation(document_id=doc_id, page_num=1, span_id="s1",
                                 original_text="Hello world friend"))
    db_session.commit()
    monkeypatch.setattr(TH.TranslationHarness, "harmonize_page",
                        staticmethod(lambda *a: None))           # harness "chết"
    res = TranslatorV2.translate_page_batch(doc_id, 1, "vi", {}, [], db_session, quality="max")
    assert res["status"] == "translated"                        # vẫn dịch xong (mock V1)
    row = db_session.query(DBTranslation).filter_by(document_id=doc_id, span_id="s1").first()
    assert row.translated_text                                  # có bản dịch (fallback)
```

- [ ] **Step 2: Run test fallback → PASS**

Run: `.venv/bin/pytest tests/test_translator_v2.py -k "max" -v`
Expected: 2 passed

- [ ] **Step 3: Full suite (không regression)**

Run: `.venv/bin/pytest tests/ -q -p no:cacheprovider --ignore=tests/test_extractor_box.py --ignore=tests/test_overlay.py --ignore=tests/test_blocks_to_page_html.py --ignore=tests/test_services.py --ignore=tests/test_extractor_overhaul.py --ignore=tests/test_extractor_pagemodel.py`
Expected: tất cả PASS (gồm harness + max + fallback).

- [ ] **Step 4: Commit**

```bash
git add tests/test_translator_v2.py
git commit -m "test(harness): max-tier fail-soft fallback to high keeps page translated"
```

---

## Self-Review Notes (đã kiểm)

- **Spec coverage:** §3 components → Task 1-5; §4 rule-check → Task 1; §5 judge/refine → Task 2,4; §6 lưu winner+score+TM+needs_review → Task 6; §7 tích hợp max → Task 6; §8 fail-soft → Task 6 (handled flag) + Task 7. §10 ngoài phạm vi (audit table, UI, multi-provider) không có task — đúng. ✔
- **Type consistency:** `harmonize_page → (List[str], List[int])`; `_judge → [{best_idx,score,critique}]`; `_generate_candidates → List[List[str]]` (candidate = list[str] aligned blocks); `_refine → Dict[int,str]` (block_index→text); `_rule_check → (bool,str)`. Đồng nhất giữa các task. ✔
- **Placeholder scan:** mọi step có code/lệnh thật. ✔
- **Mock không gọi mạng:** test mock ở mức `_judge_call`/`_refine_call`/`_batch_translate_variant`/`harmonize_page` — không chạm Gemini. ✔
- **Lưu ý fixture:** Task 6/7 dùng `db_session` — verify tên trong `tests/conftest.py`, đổi nếu khác.
