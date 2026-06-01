import os
import sys
import json
import hashlib
import logging
from typing import List, Dict, Optional
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
                  quality_threshold: float = 0.8) -> Optional[str]:
        """Return cached translation if quality >= threshold, else None."""
        from backend.app.models_db import DBTranslationMemory
        h = TranslatorV2._tm_hash(source_text, target_lang)
        row = db.query(DBTranslationMemory).filter(DBTranslationMemory.source_hash == h).first()
        if row and row.quality >= quality_threshold:
            row.hit_count += 1
            row.last_used = datetime.now(timezone.utc)
            db.commit()
            return row.translated
        return None

    @staticmethod
    def tm_store(source_text: str, target_lang: str, translated: str,
                 db: Session, quality: float = 1.0) -> None:
        """Store or update a translation in the translation memory."""
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
        db.commit()

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
