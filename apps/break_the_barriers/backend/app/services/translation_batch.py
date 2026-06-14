"""Chế độ dịch SỐ LƯỢNG LỚN qua Gemini Batch API (tier max — giữ nguyên đa ứng
viên của harness). Bất đồng bộ, giảm ~50% chi phí, đổi lấy độ trễ (tối đa 24h).

Thiết kế: vòng batch sinh ỨNG VIÊN (phần lệnh nhiều nhất) chạy bất đồng bộ; khi
xong, judge + refine (ít lệnh) chạy online để chốt bản tốt nhất → vẫn chất lượng
max. Module này lo: ước tính ETA cho khách chọn, dựng request, submit/poll (bọc
SDK), và phân tích kết quả. Gemini-only.
"""
import os
import json
import logging
from typing import List, Dict, Optional

from backend.app.services.translator_v2 import TranslatorV2
from backend.app.services.translation_harness import TranslationHarness

logger = logging.getLogger(__name__)


class BatchTranslator:
    # ước lượng thời gian online (tier max, tuần tự): ~giây mỗi trang
    ONLINE_SEC_PER_PAGE = 12
    # ngưỡng tài liệu "lớn" → khuyến nghị Batch (tiết kiệm + khỏi chờ tương tác)
    LARGE_DOC_PAGES = 25

    # ── ETA / khuyến nghị cho khách hàng ──────────────────────────────────
    @staticmethod
    def _fmt_duration(sec: float) -> str:
        sec = int(sec)
        if sec < 90:
            return f"~{max(sec, 1)} giây"
        if sec < 3600:
            return f"~{round(sec / 60)} phút"
        return f"~{sec / 3600:.1f} giờ"

    @staticmethod
    def estimate(n_pages: int, quality: str = "max") -> dict:
        """Trả ước tính RÕ RÀNG cho cả 2 chế độ để khách chọn."""
        variants = TranslationHarness.MAX_CANDIDATES if quality == "max" else 1
        cand = n_pages * variants
        online_sec = n_pages * BatchTranslator.ONLINE_SEC_PER_PAGE
        large = n_pages >= BatchTranslator.LARGE_DOC_PAGES
        recommended = "batch" if large else "online"
        if large:
            rec = (f"Tài liệu {n_pages} trang khá lớn — nên dùng **Dịch số lượng lớn "
                   f"(Tiết kiệm)**: rẻ hơn ~50% và không phải ngồi chờ; bản dịch "
                   f"thường sẵn sàng sau vài giờ (tối đa 24h).")
        else:
            rec = (f"Tài liệu {n_pages} trang nhỏ — nên dùng **Nhanh (Online)**: "
                   f"xong trong {BatchTranslator._fmt_duration(online_sec)}, xem ngay.")
        return {
            "pages": n_pages,
            "quality": quality,
            "candidate_requests": cand,
            "online": {
                "eta_seconds": online_sec,
                "eta_text": BatchTranslator._fmt_duration(online_sec),
                "cost_note": "Chi phí đầy đủ (giá online).",
            },
            "batch": {
                "eta_text": "Thường vài giờ, tối đa 24h (bất đồng bộ).",
                "cost_note": "Rẻ hơn ~50% so với online.",
            },
            "recommended_mode": recommended,
            "recommendation": rec,
        }

    # ── Dựng request batch (giữ NGUYÊN prompt harness max) ─────────────────
    @staticmethod
    def _variant_prompt(blocks, target_lang, context, glossary, style) -> str:
        """Prompt y hệt TranslationHarness._batch_translate_variant để chất lượng
        khớp tier max."""
        lang_name = TranslatorV2.LANG_NAMES.get(target_lang, target_lang)
        glossary_str = TranslatorV2._format_glossary(glossary)
        style_line = ("Prioritize literal faithfulness to the source meaning.\n"
                      if style == "faithful"
                      else "Prioritize natural fluent phrasing while preserving meaning.\n")
        input_json = json.dumps(
            [{"id": f"b{i}", "text": b["text"]} for i, b in enumerate(blocks)],
            ensure_ascii=False)
        return (
            f"Professional translator. Domain: {context.get('domain', 'general')}. "
            f"Target: {lang_name}.\nGLOSSARY (follow exactly):\n{glossary_str}\n{style_line}"
            'Return ONLY JSON {"translations":[{"id":"b0","text":"..."},...]}.\n'
            f"Input:\n{input_json}")

    @staticmethod
    def build_candidate_requests(pages: List[List[dict]], target_lang: str,
                                 context: dict, glossary: list) -> List[dict]:
        """1 request cho mỗi (trang × variant). key='p{pi}:v{vi}' để map lại."""
        reqs: List[dict] = []
        for pi, blocks in enumerate(pages):
            if not blocks:
                continue
            for vi, (model, temp, style) in enumerate(TranslationHarness.CANDIDATE_VARIANTS):
                reqs.append({
                    "key": f"p{pi}:v{vi}",
                    "model": model,
                    "temperature": temp,
                    "prompt": BatchTranslator._variant_prompt(
                        blocks, target_lang, context, glossary, style),
                })
        return reqs

    @staticmethod
    def parse_batch_results(items: List[dict]) -> Dict[str, List[str]]:
        """[{key, text(JSON)}] → {key: [text theo block]}. Bỏ qua bản hỏng."""
        out: Dict[str, List[str]] = {}
        for it in items:
            key = it.get("key")
            try:
                tr = json.loads(it["text"])["translations"]
                tmap = {t["id"]: t["text"] for t in tr}
                n = len(tmap)
                out[key] = [tmap[f"b{i}"] for i in range(n) if f"b{i}" in tmap]
            except Exception:
                logger.warning(f"batch result parse skip {key}")
                continue
        return out

    # ── Submit / poll: bọc SDK google-genai (mock được trong test) ─────────
    @staticmethod
    def _client():
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY missing")
        from google import genai
        return genai.Client(api_key=api_key)

    @staticmethod
    def submit(requests: List[dict]) -> Optional[str]:
        """Nộp 1 batch job (inline GenerateContentRequest). → tên job."""
        client = BatchTranslator._client()
        inlined = [{
            "key": r["key"],
            "request": {
                "model": r["model"],
                "contents": [{"parts": [{"text": r["prompt"]}], "role": "user"}],
                "generation_config": {
                    "response_mime_type": "application/json",
                    "temperature": r["temperature"],
                },
            },
        } for r in requests]
        job = client.batches.create(src=inlined)
        return getattr(job, "name", None)

    @staticmethod
    def poll(job_name: str) -> str:
        """Trạng thái job: JOB_STATE_PENDING|RUNNING|SUCCEEDED|FAILED|..."""
        client = BatchTranslator._client()
        job = client.batches.get(name=job_name)
        return getattr(job, "state", "JOB_STATE_PENDING")

    @staticmethod
    def fetch_results(job_name: str) -> List[dict]:
        """Job đã SUCCEEDED → [{key, text}] từ inlined_responses (hoặc file)."""
        client = BatchTranslator._client()
        job = client.batches.get(name=job_name)
        dest = getattr(job, "dest", None)
        out: List[dict] = []
        inlined = getattr(dest, "inlined_responses", None) if dest else None
        for r in (inlined or []):
            key = getattr(r, "key", None) or (r.get("key") if isinstance(r, dict) else None)
            resp = getattr(r, "response", None) or (r.get("response") if isinstance(r, dict) else None)
            text = None
            if resp is not None:
                text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None)
            if key and text:
                out.append({"key": key, "text": text})
        return out

    # ── Chốt kết quả: judge+refine online trên candidates batch (giữ max) ──
    @staticmethod
    def finalize(pages: List[List[dict]], parsed: Dict[str, List[str]],
                 target_lang: str, context: dict, glossary: list):
        """parsed (key→[text theo block]) + pages → [(source, translation, score)]
        để lưu TM. Mỗi trang gom ứng viên từ các variant rồi judge+refine online."""
        rows = []
        for pi, blocks in enumerate(pages):
            if not blocks:
                continue
            cands = []
            for vi in range(len(TranslationHarness.CANDIDATE_VARIANTS)):
                c = parsed.get(f"p{pi}:v{vi}")
                # chỉ nhận ứng viên khớp số block của trang
                if c and len(c) == len(blocks):
                    cands.append(c)
            if not cands:
                continue
            harm = TranslationHarness.harmonize_page(
                blocks, target_lang, context, glossary, candidates=cands)
            if harm is None:
                continue
            results, scores = harm
            for b, tr, sc in zip(blocks, results, scores):
                rows.append((b["text"], tr, sc))
        return rows
