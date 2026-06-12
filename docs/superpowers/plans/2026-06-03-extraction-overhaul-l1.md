# Extraction Overhaul (L1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PyMuPDF the primary page-text source (complete coverage incl. tables-of-contents over images), tag blocks with docling semantic roles, and drop decorative noise — so translations are complete and free of junk fragments.

**Architecture:** Per page, PyMuPDF `get_text("dict")` yields all text blocks (bbox+font, reusing SP-A's `aggregate_font`/`detect_align`); a SemanticTagger assigns roles from the best-overlapping docling item; the extractor builds spans/HTML/layout/model from these blocks (docling still supplies figures+raster). Content/decoration classification is folded into the batch-translate call, with a deterministic `is_decoration` rule fallback for pytest/no-key.

**Tech Stack:** Python 3.12, PyMuPDF (`fitz`), docling, SQLAlchemy, pytest. Paths relative to `apps/break_the_barriers/backend/` unless noted. Git root: `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`.

---

## File Structure

| File | Responsibility | New? |
|---|---|---|
| `app/services/pdf_text_extractor.py` | PyMuPDF → grouped text blocks (`blocks_from_pymupdf_dict` pure + `extract_text_blocks` I/O) | Create |
| `app/services/semantic_tagger.py` | Assign semantic role per block from docling labels (`label_to_role` + `tag_blocks`) | Create |
| `app/services/translator_v2.py` | `is_decoration` fallback; `_gemini_batch_translate` returns `is_content`; `translate_page_batch` drops decoration | Modify |
| `app/services/extractor.py` | `_blocks_to_page_html` builder; wire PyMuPDF path into `extract_pdf_to_html` with docling-only degrade | Modify |
| `tests/test_pdf_text_extractor.py` … `tests/test_extractor_overhaul.py` | Unit + integration | Create |

Existing `_items_to_page_html`, `extract_page_fonts` are kept (used by fallback + existing tests).

---

## Task 1: PdfTextExtractor

**Files:**
- Create: `app/services/pdf_text_extractor.py`
- Test: `tests/test_pdf_text_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pdf_text_extractor.py
from backend.app.services.pdf_text_extractor import blocks_from_pymupdf_dict
from backend.app.services.page_model import FontSpec


def _span(text, size=11, flags=0, color=0, font="Helvetica"):
    return {"text": text, "size": size, "flags": flags, "color": color, "font": font}


def test_groups_block_lines_into_one_block():
    raw = {"blocks": [
        {"type": 0, "bbox": [72, 40, 272, 64], "lines": [
            {"bbox": [72, 40, 272, 52], "spans": [_span("Brief history of")]},
            {"bbox": [72, 52, 272, 64], "spans": [_span("Artificial Intelligence")]},
        ]},
    ]}
    blocks = blocks_from_pymupdf_dict(raw)
    assert len(blocks) == 1
    assert blocks[0]["text"] == "Brief history of Artificial Intelligence"
    assert blocks[0]["bbox"] == [72, 40, 200, 24]   # [l, t, w, h]
    assert isinstance(blocks[0]["font"], FontSpec)


def test_skips_image_blocks_and_empty_text():
    raw = {"blocks": [
        {"type": 1, "bbox": [0, 0, 100, 100]},                      # image block
        {"type": 0, "bbox": [0, 0, 10, 10], "lines": [
            {"bbox": [0, 0, 10, 10], "spans": [_span("   ")]}]},     # whitespace only
        {"type": 0, "bbox": [0, 0, 50, 12], "lines": [
            {"bbox": [0, 0, 50, 12], "spans": [_span("206.")]}]},    # kept (filtering is later)
    ]}
    blocks = blocks_from_pymupdf_dict(raw)
    assert [b["text"] for b in blocks] == ["206."]


def test_bold_span_yields_weight_700():
    raw = {"blocks": [{"type": 0, "bbox": [0, 0, 80, 20], "lines": [
        {"bbox": [0, 0, 80, 20], "spans": [_span("CONTENTS", size=24, flags=16, font="Helvetica-Bold")]}]}]}
    blocks = blocks_from_pymupdf_dict(raw)
    assert blocks[0]["font"].weight == 700
    assert blocks[0]["font"].size == 24.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pdf_text_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/pdf_text_extractor.py
"""Primary page-text source. PyMuPDF extracts ALL text (complete coverage,
including text rendered over images that docling misses). Each PyMuPDF text
block becomes one logical block with bbox + aggregated font."""
from __future__ import annotations
import logging
from typing import List, Dict

from backend.app.services.typography_extractor import aggregate_font, detect_align

logger = logging.getLogger(__name__)


def blocks_from_pymupdf_dict(raw: dict) -> List[Dict]:
    """Group a PyMuPDF `page.get_text('dict')` structure into logical text blocks.

    Returns a list of {"text", "bbox":[l,t,w,h] top-left points, "font": FontSpec}.
    Image blocks (type != 0) and whitespace-only blocks are skipped. No decoration
    filtering here — that happens at translate time."""
    out: List[Dict] = []
    for blk in raw.get("blocks", []):
        if blk.get("type", 0) != 0:
            continue
        span_dicts = []
        line_texts = []
        line_lefts = []
        for line in blk.get("lines", []):
            lb = line.get("bbox")
            if lb:
                line_lefts.append(lb[0])
            parts = []
            for sp in line.get("spans", []):
                parts.append(sp.get("text", ""))
                span_dicts.append({
                    "size": sp.get("size", 0), "flags": sp.get("flags", 0),
                    "color": sp.get("color", 0), "font": sp.get("font", ""),
                })
            line_texts.append("".join(parts))
        text = " ".join(t for t in line_texts).strip()
        if not text or not span_dicts:
            continue
        x0, y0, x1, y1 = blk["bbox"]
        bbox = [x0, y0, x1 - x0, y1 - y0]
        font = aggregate_font(span_dicts, align=detect_align(line_lefts, x0, x1 - x0))
        out.append({"text": text, "bbox": bbox, "font": font})
    return out


def extract_text_blocks(pdf_path: str, page_no: int) -> List[Dict]:
    """Thin PyMuPDF I/O wrapper around blocks_from_pymupdf_dict.
    Returns [] on any failure so the caller can fall back to docling."""
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not installed; cannot extract text blocks")
        return []
    try:
        doc = fitz.open(pdf_path)
        raw = doc[page_no - 1].get_text("dict")
        doc.close()
        return blocks_from_pymupdf_dict(raw)
    except Exception as e:
        logger.warning(f"extract_text_blocks failed for {pdf_path} p{page_no}: {e}")
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pdf_text_extractor.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/pdf_text_extractor.py apps/break_the_barriers/backend/tests/test_pdf_text_extractor.py
git commit -m "feat(sp-a.1): PdfTextExtractor (PyMuPDF blocks as primary text source)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: SemanticTagger

**Files:**
- Create: `app/services/semantic_tagger.py`
- Test: `tests/test_semantic_tagger.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_semantic_tagger.py
from backend.app.services.semantic_tagger import label_to_role, tag_blocks


def test_label_to_role():
    assert label_to_role("section_header") == "heading"
    assert label_to_role("list_item") == "list"
    assert label_to_role("table") == "table"
    assert label_to_role("caption") == "caption"
    assert label_to_role("text") == "body"
    assert label_to_role(None) == "body"


def test_tag_blocks_assigns_role_from_overlap():
    blocks = [{"text": "T", "bbox": [10, 10, 100, 20]},
              {"text": "B", "bbox": [10, 200, 100, 20]}]
    docling_items = [
        {"label": "section_header", "bbox": [10, 10, 100, 20]},   # overlaps block 0
        {"label": "picture", "bbox": [10, 500, 100, 20]},         # overlaps nothing here
    ]
    tagged = tag_blocks(blocks, docling_items)
    assert tagged[0]["role"] == "heading"
    assert tagged[1]["role"] == "body"   # no overlap -> default body


def test_tag_blocks_no_items_all_body():
    blocks = [{"text": "x", "bbox": [0, 0, 10, 10]}]
    assert tag_blocks(blocks, [])[0]["role"] == "body"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_semantic_tagger.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/semantic_tagger.py
"""Assign a semantic role to each PyMuPDF text block by overlapping it with the
best-matching docling item (which carries the semantic label)."""
from __future__ import annotations
from typing import List, Dict

from backend.app.services.typography_extractor import iou

_LABEL_ROLE = {
    "section_header": "heading", "title": "heading",
    "list_item": "list", "table": "table", "caption": "caption",
}


def label_to_role(label) -> str:
    return _LABEL_ROLE.get(str(label or "").lower(), "body")


def tag_blocks(blocks: List[Dict], docling_items: List[Dict],
               iou_threshold: float = 0.1) -> List[Dict]:
    """For each block, pick the docling item with highest IoU >= threshold and use
    its role; otherwise 'body'. docling_items: [{"label", "bbox":[l,t,w,h]}].
    Mutates blocks in place (adds 'role') and returns them."""
    for b in blocks:
        best_role = "body"
        best_iou = iou_threshold
        for it in docling_items:
            bb = it.get("bbox")
            if not bb:
                continue
            ov = iou(b["bbox"], bb)
            if ov >= best_iou:
                best_iou = ov
                best_role = label_to_role(it.get("label"))
        b["role"] = best_role
    return blocks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_semantic_tagger.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/semantic_tagger.py apps/break_the_barriers/backend/tests/test_semantic_tagger.py
git commit -m "feat(sp-a.1): SemanticTagger assigns roles from docling overlap

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: ContentClassifier (is_decoration + batch-translate is_content + drop)

**Files:**
- Modify: `app/services/translator_v2.py`
- Test: `tests/test_content_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_content_classifier.py
from backend.app.services.translator_v2 import TranslatorV2


def test_is_decoration_true_for_noise():
    for s in ["206.", "LC88.01", "/0/0/", "85:1254:20", "PO52.06", "14.687.", "|", "2"]:
        assert TranslatorV2.is_decoration(s) is True, s


def test_is_decoration_false_for_content():
    for s in ["FOREWORD", "CONTENTS", "Brief history of Artificial Intelligence (AI)",
              "Algorithms : The Brains of AI", "World Travel & Tourism Council"]:
        assert TranslatorV2.is_decoration(s) is False, s


def test_translate_page_batch_drops_decoration(db_session, monkeypatch):
    # Seed a page with one content span and one decoration span.
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    html = ('<!DOCTYPE html><html><body>'
            '<p><span id="s1">Algorithms : The Brains of AI</span></p>'
            '<p><span id="s2">206.</span></p></body></html>')
    db_session.add(DBDocument(id="cc_doc", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.add(DBPage(document_id="cc_doc", page_num=1, original_html=html, status="extracted"))
    db_session.add(DBTranslation(document_id="cc_doc", page_num=1, span_id="s1", original_text="Algorithms : The Brains of AI"))
    db_session.add(DBTranslation(document_id="cc_doc", page_num=1, span_id="s2", original_text="206."))
    db_session.commit()

    # pytest path uses the mock translator + is_decoration fallback (no API).
    res = TranslatorV2.translate_page_batch("cc_doc", 1, "vi", {"title": "t"}, [], db_session)
    assert res["status"] == "translated"
    rows = {t.span_id: t.translated_text for t in db_session.query(DBTranslation)
            .filter(DBTranslation.document_id == "cc_doc").all()}
    assert rows["s1"]            # content translated
    assert not rows["s2"]        # decoration left untranslated (dropped)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_content_classifier.py -v`
Expected: FAIL (`is_decoration` missing; decoration not dropped).

- [ ] **Step 3a: Add `is_decoration` to `TranslatorV2`**

Add `import re` at the top of `translator_v2.py` if not present, and add this staticmethod inside the `TranslatorV2` class (e.g. just after the `LANG_NAMES` dict):

```python
    @staticmethod
    def is_decoration(text: str) -> bool:
        """Deterministic fallback classifier: True if a fragment is decorative
        noise (numbers/codes from image design) rather than real content.
        Content has at least one word of >=4 letters; otherwise digit-heavy or
        letterless short fragments are decoration."""
        t = (text or "").strip()
        if not t:
            return True
        longest_word = max((len(w) for w in re.findall(r"[A-Za-zÀ-ỹ]+", t)), default=0)
        if longest_word >= 4:
            return False
        letters = sum(c.isalpha() for c in t)
        digits = sum(c.isdigit() for c in t)
        nonspace = sum(1 for c in t if not c.isspace()) or 1
        return (digits / nonspace >= 0.3) or (letters == 0)
```

- [ ] **Step 3b: Make the mock path in `translate_page_batch` drop decoration**

In `translate_page_batch`, the `is_pytest or not api_key` branch loops `for block in blocks_to_translate:` and stores a mock translation. Wrap the store so decoration blocks are skipped. Change that loop body from:

```python
                for block in blocks_to_translate:
                    translated = Translator.translate_text_agentic(
                        block["text"], target_lang=target_lang, quality=quality
                    )
                    TranslatorV2.tm_store(block["text"], target_lang, translated, db)
                    if len(block["span_ids"]) == 1:
                        translations[block["span_ids"][0]] = translated
                    else:
                        parts = Translator.deinterpolate_translation(translated, block["span_ids"])
                        translations.update(parts)
```

to:

```python
                for block in blocks_to_translate:
                    if TranslatorV2.is_decoration(block["text"]):
                        continue   # drop decorative noise — no translation written
                    translated = Translator.translate_text_agentic(
                        block["text"], target_lang=target_lang, quality=quality
                    )
                    TranslatorV2.tm_store(block["text"], target_lang, translated, db)
                    if len(block["span_ids"]) == 1:
                        translations[block["span_ids"][0]] = translated
                    else:
                        parts = Translator.deinterpolate_translation(translated, block["span_ids"])
                        translations.update(parts)
```

- [ ] **Step 3c: Make `_gemini_batch_translate` return per-block content flags**

In `_gemini_batch_translate`, change the output schema line and parsing. Replace the prompt's output-schema string:

```python
                'Output schema: {"translations":[{"id":"b0","text":"..."},...]}'
```

with:

```python
                'Each item also needs "is_content": false for decorative noise '
                '(page numbers, codes, stray symbols) and true for real content.\n'
                'Output schema: {"translations":[{"id":"b0","text":"...","is_content":true},...]}'
```

Then change the parse/return block from:

```python
            data = json.loads(resp.text)
            translated_map = {item["id"]: item["text"] for item in data["translations"]}
            result = []
            has_missing = False
            for i in range(len(blocks)):
                key = f"b{i}"
                if key in translated_map:
                    result.append(translated_map[key])
                else:
                    result.append(blocks[i]["text"])
                    has_missing = True
            return (result, has_missing)
```

to:

```python
            data = json.loads(resp.text)
            translated_map = {item["id"]: item["text"] for item in data["translations"]}
            content_map = {item["id"]: item.get("is_content", True) for item in data["translations"]}
            result = []
            content_flags = []
            has_missing = False
            for i in range(len(blocks)):
                key = f"b{i}"
                if key in translated_map:
                    result.append(translated_map[key])
                    content_flags.append(bool(content_map.get(key, True)))
                else:
                    result.append(blocks[i]["text"])
                    content_flags.append(not TranslatorV2.is_decoration(blocks[i]["text"]))
                    has_missing = True
            return (result, has_missing, content_flags)
```

- [ ] **Step 3d: Consume the new return shape in `translate_page_batch`**

In `translate_page_batch`, the real-API branch currently does `batch_result = TranslatorV2._gemini_batch_translate(...)`, then `batch_translations, has_missing = batch_result`, then `for block, translated in zip(blocks_to_translate, batch_translations):` stores each. Update unpacking and skip decoration. Change:

```python
                else:
                    batch_translations, has_missing = batch_result
                    if has_missing:
                        page.needs_review = True
                        page.review_reason = "batch_missing_blocks"
                    for block, translated in zip(blocks_to_translate, batch_translations):
                        TranslatorV2.tm_store(block["text"], target_lang, translated, db)
                        if len(block["span_ids"]) == 1:
                            translations[block["span_ids"][0]] = translated
                        else:
                            parts = Translator.deinterpolate_translation(translated, block["span_ids"])
                            translations.update(parts)
```

to:

```python
                else:
                    batch_translations, has_missing, content_flags = batch_result
                    if has_missing:
                        page.needs_review = True
                        page.review_reason = "batch_missing_blocks"
                    for block, translated, is_content in zip(blocks_to_translate, batch_translations, content_flags):
                        if not is_content:
                            continue   # drop decorative noise
                        TranslatorV2.tm_store(block["text"], target_lang, translated, db)
                        if len(block["span_ids"]) == 1:
                            translations[block["span_ids"][0]] = translated
                        else:
                            parts = Translator.deinterpolate_translation(translated, block["span_ids"])
                            translations.update(parts)
```

Note: `_gemini_batch_translate` now returns a 3-tuple. The earlier `if batch_result is None:` guard is unchanged (None still means total failure → V1 fallback).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_content_classifier.py tests/test_translator_v2.py -v`
Expected: PASS. If any existing `test_translator_v2.py` test asserts the 2-tuple return of `_gemini_batch_translate`, update that assertion to the 3-tuple `(result, has_missing, content_flags)` — search: `grep -n "_gemini_batch_translate" tests/test_translator_v2.py`.

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/translator_v2.py apps/break_the_barriers/backend/tests/test_content_classifier.py apps/break_the_barriers/backend/tests/test_translator_v2.py
git commit -m "feat(sp-a.1): content/decoration classification folded into batch-translate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `_blocks_to_page_html` builder

**Files:**
- Modify: `app/services/extractor.py` (add staticmethod to `DoclingExtractor`)
- Test: `tests/test_blocks_to_page_html.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_blocks_to_page_html.py
from backend.app.services.extractor import DoclingExtractor
from backend.app.services.page_model import FontSpec


def _fs():
    return FontSpec(11, 400, False, "#111", "left", "sans")


def test_builds_html_and_blocks_with_roles():
    tagged = [
        {"text": "CONTENTS", "bbox": [10, 10, 100, 20], "font": _fs(), "role": "heading"},
        {"text": "Foreword", "bbox": [10, 40, 100, 12], "font": _fs(), "role": "list"},
        {"text": "Intro", "bbox": [10, 55, 100, 12], "font": _fs(), "role": "list"},
        {"text": "Body text here", "bbox": [10, 80, 100, 12], "font": _fs(), "role": "body"},
    ]
    html, blocks = DoclingExtractor._blocks_to_page_html(tagged, page_no=1)
    assert '<h2><span id="s1">CONTENTS</span></h2>' in html
    assert '<ul>' in html and '<li><span id="s2">Foreword</span></li>' in html
    assert '<p><span id="s4">Body text here</span></p>' in html
    # parallel blocks carry span_id + bbox + font + role, in order
    assert [b["span_id"] for b in blocks] == ["s1", "s2", "s3", "s4"]
    assert blocks[0]["role"] == "heading"
    assert blocks[0]["bbox"] == [10, 10, 100, 20]
    assert blocks[0]["font"] is tagged[0]["font"]


def test_escapes_text():
    tagged = [{"text": "A & B <c>", "bbox": [0, 0, 1, 1], "font": _fs(), "role": "body"}]
    html, _ = DoclingExtractor._blocks_to_page_html(tagged, page_no=1)
    assert "A &amp; B &lt;c&gt;" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_blocks_to_page_html.py -v`
Expected: FAIL with `AttributeError: ... has no attribute '_blocks_to_page_html'`.

- [ ] **Step 3: Add the builder to `DoclingExtractor`**

In `app/services/extractor.py`, add this staticmethod to `DoclingExtractor` (next to `_items_to_page_html`). `html_lib` is already imported at the top of the file.

```python
    @staticmethod
    def _blocks_to_page_html(tagged_blocks, page_no):
        """Build semantic HTML + a parallel block list from PyMuPDF tagged blocks.
        Mirrors _items_to_page_html's output shape but sourced from PyMuPDF:
        each returned block carries span_id, bbox, font (FontSpec), role."""
        parts = []
        blocks = []
        open_list = False
        for i, b in enumerate(tagged_blocks, start=1):
            sid = f"s{i}"
            blocks.append({"span_id": sid, "bbox": b["bbox"],
                           "font": b.get("font"), "role": b.get("role", "body")})
            span = f'<span id="{sid}">{html_lib.escape(b["text"])}</span>'
            role = b.get("role", "body")
            if role == "list":
                if not open_list:
                    parts.append("<ul>")
                    open_list = True
                parts.append(f"<li>{span}</li>")
                continue
            if open_list:
                parts.append("</ul>")
                open_list = False
            if role == "heading":
                parts.append(f"<h2>{span}</h2>")
            else:
                parts.append(f"<p>{span}</p>")
        if open_list:
            parts.append("</ul>")
        html = (
            f"<!DOCTYPE html>\n<html>\n<head>\n"
            f'<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"<style>\n{_DOCLING_RESPONSIVE_CSS}\n</style>\n"
            f"</head>\n<body>\n"
            + "\n".join(parts)
            + "\n</body>\n</html>"
        )
        return html, blocks
```

> `_DOCLING_RESPONSIVE_CSS` is the module-level CSS constant already used by `_items_to_page_html`. Confirm its name by reading the top of `extractor.py`; if different, use the same constant `_items_to_page_html` uses.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_blocks_to_page_html.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/extractor.py apps/break_the_barriers/backend/tests/test_blocks_to_page_html.py
git commit -m "feat(sp-a.1): _blocks_to_page_html builds HTML+blocks from PyMuPDF blocks

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Wire PyMuPDF path into `extract_pdf_to_html`

**Files:**
- Modify: `app/services/extractor.py` (`DoclingExtractor.extract_pdf_to_html`, the per-page loop ~lines 313-393)
- Test: `tests/test_extractor_overhaul.py`

- [ ] **Step 1: Write the failing integration test**

```python
# tests/test_extractor_overhaul.py
import os
import glob
import json
import pytest

_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
       "assets", "books", "2024-wttc-introduction-to-ai.pdf"))


@pytest.mark.skipif(not os.path.exists(_PDF), reason="sample PDF not available")
def test_pymupdf_text_source_captures_toc_and_keeps_noise_as_blocks(tmp_path):
    from backend.app.services.extractor import DoclingExtractor
    out = str(tmp_path / "out")
    DoclingExtractor.extract_pdf_to_html(_PDF, out, "ov")
    # Page 2 is the CONTENTS page.
    html_p2 = open(os.path.join(out, "ov-2.html"), encoding="utf-8").read()
    # PyMuPDF now captures the table-of-contents text docling missed:
    assert "FOREWORD" in html_p2 or "Foreword" in html_p2
    assert "Algorithms" in html_p2
    # Model sidecar exists and references the same spans.
    model = json.load(open(os.path.join(out, "ov-2.model.json"), encoding="utf-8"))
    assert model["blocks"], "no blocks in model"
    assert any(b.get("font") for b in model["blocks"])  # fonts carried from PyMuPDF
```

- [ ] **Step 2: Run to verify it fails (or skips without the PDF)**

Run: `.venv/bin/pytest tests/test_extractor_overhaul.py -v`
Expected: FAIL (page 2 html lacks "Algorithms" because docling-sourced) — runs real docling, ~2-3 min. If it SKIPS, the PDF is missing; STOP and report NEEDS_CONTEXT.

- [ ] **Step 3: Rewire the per-page loop**

In `extract_pdf_to_html`, the per-page loop currently begins:

```python
        for page_no in sorted(pages_items.keys()):
            page_item = doc.pages.get(page_no)
            page_size = page_item.size if page_item else None
            page_html, blocks, fig_boxes = cls._items_to_page_html(pages_items[page_no], page_no, page_size)
```

Replace that 4th line with a PyMuPDF-primary build that degrades to docling. Insert the imports at the top of `extract_pdf_to_html` (with the other local imports) is not needed — import inline:

```python
        for page_no in sorted(pages_items.keys()):
            page_item = doc.pages.get(page_no)
            page_size = page_item.size if page_item else None

            # Always derive docling figure boxes + semantic items for tagging.
            _docling_html, _docling_blocks, fig_boxes = cls._items_to_page_html(
                pages_items[page_no], page_no, page_size)

            # PyMuPDF is the primary text source (complete coverage). Build the
            # docling item list (label + bbox top-left points) for role tagging.
            from backend.app.services.pdf_text_extractor import extract_text_blocks
            from backend.app.services.semantic_tagger import tag_blocks
            from docling_core.types.doc import CoordOrigin

            page_h_pt = getattr(page_size, "height", None)
            docling_items = []
            if page_h_pt is not None:
                for item, _lvl in pages_items[page_no]:
                    prov = getattr(item, "prov", None)
                    if not prov:
                        continue
                    bb = prov[0].bbox
                    tl = bb if bb.coord_origin == CoordOrigin.TOPLEFT else bb.to_top_left_origin(page_height=page_h_pt)
                    docling_items.append({
                        "label": str(getattr(item, "label", "text")),
                        "bbox": [tl.l, min(tl.t, tl.b), tl.r - tl.l, abs(tl.b - tl.t)],
                    })

            pm_blocks = extract_text_blocks(str(pdf_path), page_no)
            if pm_blocks:
                tagged = tag_blocks(pm_blocks, docling_items)
                page_html, blocks = cls._blocks_to_page_html(tagged, page_no)
            else:
                # Degrade: PyMuPDF produced nothing -> docling-only path.
                page_html, blocks = _docling_html, _docling_blocks
```

- [ ] **Step 4: Use block-carried fonts when building the model**

Later in the same loop, the SP-A PageModel block computes `fonts = extract_page_fonts(...)` and builds `model_blocks` with `font=fonts.get(b["span_id"])` and `role="body"`. Update it to prefer the font/role already on the block (PyMuPDF path carries them; docling fallback does not). Replace:

```python
            fonts = {}
            try:
                fonts = extract_page_fonts(str(pdf_path), page_no, blocks)
            except Exception as e:
                logger.warning(f"Font extraction failed p{page_no}: {e}")
```

with:

```python
            # PyMuPDF path already carries per-block font; only call the
            # bbox-matching font extractor for the docling fallback path.
            fonts = {}
            if blocks and not blocks[0].get("font"):
                try:
                    fonts = extract_page_fonts(str(pdf_path), page_no, blocks)
                except Exception as e:
                    logger.warning(f"Font extraction failed p{page_no}: {e}")
```

and replace the `model_blocks = [...]` comprehension:

```python
            model_blocks = [
                Block(span_id=b["span_id"], role="body", bbox=b["bbox"],
                      text="", font=fonts.get(b["span_id"]))
                for b in blocks
            ]
```

with:

```python
            model_blocks = [
                Block(span_id=b["span_id"], role=b.get("role", "body"), bbox=b["bbox"],
                      text="", font=b.get("font") or fonts.get(b["span_id"]))
                for b in blocks
            ]
```

> Note: the `bg` sampling loop (`for blk in blocks: ... blk["bg"] = sample_bg_color(...)`) and `bg_color = blocks[0].get("bg", ...)` continue to work — blocks still have `bbox`, and `.get("bg")` is added by that loop. No change needed there.

- [ ] **Step 5: Run the integration test + full regression on extractor-touching tests**

Run: `.venv/bin/pytest tests/test_extractor_overhaul.py tests/test_overlay.py tests/test_services.py tests/test_extractor_pagemodel.py -v`
Expected: `test_pymupdf_text_source_captures_toc_and_keeps_noise_as_blocks` PASS; existing extractor tests still PASS (they target `_items_to_page_html`/`extract_page_fonts`, which are untouched). Real docling runs — be patient (~3 min).

- [ ] **Step 6: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/services/extractor.py apps/break_the_barriers/backend/tests/test_extractor_overhaul.py
git commit -m "feat(sp-a.1): extract_pdf_to_html uses PyMuPDF text + docling roles

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Full verification + real-document check

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass (docling integration tests are slow, ~5 min total).

- [ ] **Step 2: Real-document spot check**

Re-extract the WTTC PDF to a temp dir and confirm page 2 now has the table-of-contents text as spans and decoration is recognizable:

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/backend
PYTHONPATH=/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers \
  .venv/bin/python -c "
from backend.app.services.extractor import DoclingExtractor
DoclingExtractor.extract_pdf_to_html('/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf','/tmp/ov_check','ov')
import re
h=open('/tmp/ov_check/ov-2.html',encoding='utf-8').read()
print('has FOREWORD:', 'FOREWORD' in h or 'Foreword' in h)
print('has Algorithms:', 'Algorithms' in h)
from backend.app.services.translator_v2 import TranslatorV2
print('206. decoration:', TranslatorV2.is_decoration('206.'))
"
```
Expected: `has FOREWORD: True`, `has Algorithms: True`, `206. decoration: True`.

- [ ] **Step 3: Note for the user**

Report that to see it in the running app, the document must be **re-extracted** (old rows predate this change) and then re-translated. Decoration is dropped at translate time; with a real Gemini key the LLM `is_content` flag also applies. Image/mixed pages still overlay on the raster (opaque-box quality is **L2**, a separate spec).

---

## Self-Review notes

- **Spec coverage:** PdfTextExtractor §4.1 → Task 1; SemanticTagger §4.2 → Task 2; ContentClassifier §4.3 (LLM `is_content` folded into batch-translate + `is_decoration` fallback + TM gated to content) → Task 3; Pipeline rewire §4.4 → Tasks 4-5; degrade paths (PyMuPDF empty→docling-only; docling lvl) → Task 5 Step 3; testing §7 → per-task unit + Task 5/6 integration. Reading view + layout/model span-id consistency preserved (same `s1..` numbering, same CSS constant).
- **Placeholder scan:** none — every code step has complete code.
- **Type consistency:** block dict shape `{"text","bbox","font"(FontSpec)}` (Task 1) → `+"role"` (Task 2) → consumed by `_blocks_to_page_html` (Task 4) producing `{"span_id","bbox","font","role"}` → consumed in `extract_pdf_to_html` model build (Task 5). `_gemini_batch_translate` 3-tuple `(result, has_missing, content_flags)` defined in Task 3 Step 3c and consumed in 3d. `is_decoration` defined 3a, used in 3b/3c and Task 6.
- **Known follow-ups (not L1):** decoration blocks still appear as spans in the reading-view HTML (only excluded from overlay/translation) — acceptable cosmetic; full span-level removal would need extraction-time classification (an extra call we intentionally avoided). Raster-page render quality (opaque boxes/fit) is **L2**.
```
