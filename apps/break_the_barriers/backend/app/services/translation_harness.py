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
