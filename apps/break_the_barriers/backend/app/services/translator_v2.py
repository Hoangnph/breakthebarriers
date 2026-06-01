import os
import sys
import json
import hashlib
import logging
from typing import List, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TranslatorV2:
    MODEL = "gemini-2.5-flash"
    TM_QUALITY_THRESHOLD = 0.8

    LANG_NAMES = {
        "vi": "Vietnamese", "en": "English", "zh": "Chinese",
        "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German",
    }

    # ── Translation Memory ────────────────────────────────────────────────

    @staticmethod
    def _tm_hash(source_text: str, target_lang: str) -> str:
        return hashlib.sha256(f"{source_text}|{target_lang}".encode()).hexdigest()

    @staticmethod
    def tm_lookup(source_text: str, target_lang: str, db: Session,
                  quality_threshold: float = None) -> Optional[str]:
        """Return cached translation if quality >= threshold, else None."""
        if quality_threshold is None:
            quality_threshold = TranslatorV2.TM_QUALITY_THRESHOLD
        from backend.app.models_db import DBTranslationMemory
        h = TranslatorV2._tm_hash(source_text, target_lang)
        row = db.query(DBTranslationMemory).filter(DBTranslationMemory.source_hash == h).first()
        if row and row.quality >= quality_threshold:
            row.hit_count += 1
            row.last_used = datetime.now(timezone.utc)
            try:
                db.commit()
            except Exception:
                db.rollback()
            return row.translated
        return None

    @staticmethod
    def tm_store(source_text: str, target_lang: str, translated: str,
                 db: Session, quality: float = 1.0) -> None:
        """Store or update a translation in the translation memory.

        Concurrency-safe: on a unique-violation race (another transaction inserted
        the same source_hash), rolls back and treats it as a no-op — the other
        transaction's value is equally valid.
        """
        from backend.app.models_db import DBTranslationMemory
        h = TranslatorV2._tm_hash(source_text, target_lang)
        row = db.query(DBTranslationMemory).filter(DBTranslationMemory.source_hash == h).first()
        if row:
            row.translated = translated
            row.quality = quality
            row.last_used = datetime.now(timezone.utc)
        else:
            db.add(DBTranslationMemory(
                source_hash=h, source_text=source_text, target_lang=target_lang,
                translated=translated, quality=quality,
            ))
        try:
            db.commit()
        except Exception:
            db.rollback()

    # ── Document Context Extraction ───────────────────────────────────────

    @staticmethod
    def _mock_context(doc_id: str) -> dict:
        return {
            "title": f"Document {doc_id}",
            "author": None,
            "domain": "general",
            "style": "formal_academic",
            "key_terms": [],
        }

    @staticmethod
    def extract_document_context(doc_id: str, sample_html_pages: List[str]) -> dict:
        """
        1 Gemini call to identify document metadata.
        Falls back to mock in pytest or if no API key.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        is_pytest = "pytest" in sys.modules

        if is_pytest or not api_key:
            return TranslatorV2._mock_context(doc_id)

        try:
            from google import genai
            from bs4 import BeautifulSoup

            texts = []
            for html in sample_html_pages[:3]:
                soup = BeautifulSoup(html or "", "html.parser")
                texts.append(soup.get_text(separator=" ", strip=True)[:800])
            sample = "\n---\n".join(texts)

            client = genai.Client(api_key=api_key)
            prompt = (
                "Analyze this PDF document sample. Return ONLY valid JSON, no markdown.\n\n"
                f"Sample:\n{sample}\n\n"
                'JSON schema: {"title":"string","author":"string or null",'
                '"domain":"one of: classical_philosophy|technical|literature|medicine|law|general",'
                '"style":"one of: literary_poetic|formal_academic|conversational|technical_precise",'
                '"key_terms":["up to 15 domain-specific terms"]}'
            )
            resp = client.models.generate_content(
                model=TranslatorV2.MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            result = json.loads(resp.text)
            result.setdefault("author", None)
            result.setdefault("key_terms", [])
            result.setdefault("domain", "general")
            result.setdefault("style", "formal_academic")
            return result
        except Exception as e:
            logger.error(f"Context extraction failed: {e}")
            return TranslatorV2._mock_context(doc_id)

    # ── Glossary Pre-pass ─────────────────────────────────────────────────

    @staticmethod
    def build_glossary_from_context(doc_id: str, target_lang: str, context: dict) -> List[dict]:
        """
        1 Gemini call to generate authoritative term translations.
        Returns list of {source, target}. Empty list in pytest or if no key_terms.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        is_pytest = "pytest" in sys.modules
        key_terms = context.get("key_terms", [])

        if is_pytest or not api_key or not key_terms:
            return []

        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            lang_name = TranslatorV2.LANG_NAMES.get(target_lang, target_lang)
            title = context.get("title", "Unknown")
            author = context.get("author")
            domain = context.get("domain", "general")

            prompt = (
                f"You are establishing translation standards for '{title}'"
                + (f" by {author}" if author else "")
                + f".\nDomain: {domain}. Target language: {lang_name}.\n"
                "Provide authoritative, consistent translations for these key terms.\n"
                "Return ONLY a valid JSON array, no markdown.\n\n"
                f"Terms: {json.dumps(key_terms, ensure_ascii=False)}\n\n"
                'Schema: [{"source": "term", "target": "translation"}, ...]'
            )
            resp = client.models.generate_content(
                model=TranslatorV2.MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            entries = json.loads(resp.text)
            return [e for e in entries if isinstance(e, dict) and "source" in e and "target" in e]
        except Exception as e:
            logger.error(f"Glossary pre-pass failed: {e}")
            return []

    # ── Batch Page Translation ────────────────────────────────────────────

    @staticmethod
    def _format_glossary(glossary: List[dict]) -> str:
        if not glossary:
            return "(none)"
        return "\n".join(f"- {e['source']} → {e['target']}" for e in glossary)

    @staticmethod
    def translate_page_batch(
        doc_id: str,
        page_num: int,
        target_lang: str,
        context: dict,
        glossary: List[dict],
        db: Session,
        quality: str = "balanced",
    ) -> dict:
        """
        Translate all blocks on a page in 1 Gemini call.
        Checks TM first per block. Falls back to V1 line-by-line on JSON failure.
        Updates DBTranslation rows and DBPage.translated_html.
        Returns {"status": "translated"|"failed", "page_num": page_num}.
        """
        from backend.app.models_db import DBPage, DBTranslation, DBDocument
        from backend.app.services.extractor import Extractor
        from backend.app.services.translator import Translator  # V1 fallback

        api_key = os.getenv("GEMINI_API_KEY")
        is_pytest = "pytest" in sys.modules

        page = db.query(DBPage).filter(
            DBPage.document_id == doc_id, DBPage.page_num == page_num
        ).first()
        if not page:
            return {"status": "failed", "page_num": page_num, "reason": "page_not_found"}

        spans = Extractor.extract_spans(page.original_html or "")
        blocks = Translator.reconstruct_context_and_index(spans)

        if not blocks:
            page.status = "translated"
            db.commit()
            return {"status": "translated", "page_num": page_num}

        # Check TM for each block — collect hits and misses
        translations: dict = {}  # span_id → translated text
        blocks_to_translate = []

        for block in blocks:
            cached = TranslatorV2.tm_lookup(block["text"], target_lang, db)
            if cached is not None:
                if len(block["span_ids"]) == 1:
                    translations[block["span_ids"][0]] = cached
                else:
                    parts = Translator.deinterpolate_translation(cached, block["span_ids"])
                    translations.update(parts)
            else:
                blocks_to_translate.append(block)

        # Translate remaining blocks
        if blocks_to_translate:
            if is_pytest or not api_key:
                # Mock: use V1 mock for each block
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
            else:
                batch_result = TranslatorV2._gemini_batch_translate(
                    blocks_to_translate, target_lang, context, glossary, quality
                )
                if batch_result is None:
                    # Full fallback to V1 for this page
                    logger.warning(f"Batch failed for {doc_id} p{page_num} — falling back to V1")
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
                    page.needs_review = True
                    page.review_reason = "batch_failed_v1_fallback"
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

        # Write translations to DB
        for span_id, text in translations.items():
            t_row = db.query(DBTranslation).filter(
                DBTranslation.document_id == doc_id,
                DBTranslation.page_num == page_num,
                DBTranslation.span_id == span_id,
            ).first()
            if t_row:
                t_row.translated_text = text

        # Build translated_html via V1 compiler injection
        from backend.app.services.compiler import Compiler
        all_t = db.query(DBTranslation).filter(
            DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num
        ).all()
        trans_dict = {t.span_id: t.translated_text for t in all_t if t.translated_text}
        if trans_dict:
            try:
                page.translated_html = Compiler.inject_translation(page.original_html, trans_dict)
            except Exception as e:
                logger.error(f"Compiler injection failed for {doc_id} p{page_num}: {e}")
                page.needs_review = True
                page.review_reason = "compile_failed"

        page.status = "translated"
        doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
        all_pages = db.query(DBPage).filter(DBPage.document_id == doc_id).all()
        if all_pages and all(p.status in ["translated", "compiled"] for p in all_pages):
            if doc:
                doc.status = "translated"
        db.commit()
        return {"status": "translated", "page_num": page_num}

    @staticmethod
    def _gemini_batch_translate(
        blocks: List[dict],
        target_lang: str,
        context: dict,
        glossary: List[dict],
        quality: str = "balanced",
    ) -> Optional[tuple]:
        """
        Single Gemini call for a list of text blocks.
        Returns (list of translated strings same order as input, has_missing bool),
        or None on failure.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            lang_name = TranslatorV2.LANG_NAMES.get(target_lang, target_lang)
            title = context.get("title", "Unknown document")
            author = context.get("author")
            domain = context.get("domain", "general")
            style = context.get("style", "formal_academic")
            glossary_str = TranslatorV2._format_glossary(glossary)

            input_json = json.dumps(
                [{"id": f"b{i}", "text": b["text"]} for i, b in enumerate(blocks)],
                ensure_ascii=False
            )

            prompt = (
                f"You are a professional translator for '{title}'"
                + (f" by {author}" if author else "")
                + f".\nDomain: {domain}. Style: {style}. Target: {lang_name}.\n\n"
                f"GLOSSARY (follow exactly):\n{glossary_str}\n\n"
                "RULES:\n"
                "1. Preserve ALL [s:span_id] placeholders in exact positions\n"
                "2. Follow glossary strictly\n"
                "3. Return ONLY valid JSON matching schema below\n"
                "4. If a block is already in the target language, return it unchanged\n"
                + ("5. Prioritize maximum accuracy and natural fluency; double-check terminology against the glossary\n\n"
                   if quality == "high" else "\n")
                + f"Input:\n{input_json}\n\n"
                'Output schema: {"translations":[{"id":"b0","text":"..."},...]}'
            )

            resp = client.models.generate_content(
                model=TranslatorV2.MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
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

        except Exception as e:
            logger.error(f"Gemini batch translate failed: {e}")
            return None
