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
