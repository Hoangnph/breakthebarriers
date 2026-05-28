import logging
from dataclasses import dataclass
from typing import Optional
from backend.app.config import GEMINI_PRICE_PER_1M_TOKENS

logger = logging.getLogger(__name__)

AVG_SPANS_PER_PAGE = 40
AVG_TOKENS_PER_SPAN = 25
QUALITY_MULTIPLIERS = {"fast": 1, "balanced": 2, "high": 3}
SECS_PER_SPAN = {"fast": 0.5, "balanced": 1.0, "high": 2.0}

_TIER_TABLE = [
    # (tier, lo, hi, processing_path, recommended_quality)
    ("S",  0,   50,  "asyncio", "high"),
    ("M",  50,  200, "asyncio", "balanced"),
    ("L",  200, 500, "celery",  "fast"),
    ("XL", 500, 10_000_000, "celery", "fast"),
]


@dataclass
class VolumeProfile:
    tier: str
    page_count: int
    estimated_spans: int
    estimated_tokens: int
    estimated_cost_usd: float
    recommended_quality: str
    processing_path: str
    estimated_duration_min: int


class VolumeDetector:
    @staticmethod
    def detect(page_count: int, quality_override: Optional[str] = None) -> VolumeProfile:
        tier = "XL"
        processing_path = "celery"
        recommended_quality = "fast"

        for t, lo, hi, path, quality in _TIER_TABLE:
            if lo <= page_count < hi:
                tier, processing_path, recommended_quality = t, path, quality
                break

        effective_quality = quality_override or recommended_quality
        multiplier = QUALITY_MULTIPLIERS.get(effective_quality, 3)

        estimated_spans = page_count * AVG_SPANS_PER_PAGE
        estimated_tokens = estimated_spans * AVG_TOKENS_PER_SPAN * multiplier
        estimated_cost_usd = round(
            (estimated_tokens / 1_000_000) * GEMINI_PRICE_PER_1M_TOKENS, 4
        )
        secs = SECS_PER_SPAN.get(effective_quality, 2.0)
        estimated_duration_min = max(1, int(estimated_spans * secs / 60))

        return VolumeProfile(
            tier=tier,
            page_count=page_count,
            estimated_spans=estimated_spans,
            estimated_tokens=estimated_tokens,
            estimated_cost_usd=estimated_cost_usd,
            recommended_quality=recommended_quality,
            processing_path=processing_path,
            estimated_duration_min=estimated_duration_min,
        )
