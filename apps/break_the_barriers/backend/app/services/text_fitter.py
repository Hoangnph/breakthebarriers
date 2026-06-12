"""Server-side initial font fit. Replaces the crude `box_w/(0.5*fs)` heuristic
with a width model that ignores Vietnamese combining diacritics (they add no
advance width) and allows the box to grow up to `height_growth` before shrinking.

The renderer additionally emits a client-side shrink-to-fit refinement, but this
deterministic estimate is what makes fitting unit-testable."""
from __future__ import annotations
import math
import unicodedata

# Average glyph advance as a fraction of font size.
_AVG_CHAR_W = 0.52


def _advance_len(text: str) -> int:
    """Count advancing characters: skip Unicode combining marks (Mn)."""
    return sum(1 for ch in text if unicodedata.category(ch) != "Mn") or 1


def fit_font_size(text: str, box_w_pt: float, box_h_pt: float,
                  *, max_size: float = 40.0, min_size: float = 6.0,
                  line_height: float = 1.25, height_growth: float = 1.6) -> float:
    n = _advance_len(text)
    box_w_pt = max(box_w_pt, 1.0)
    box_h_pt = max(box_h_pt, 1.0)
    best = min_size
    fs = min_size
    while fs <= max_size:
        chars_per_line = max(1.0, box_w_pt / (_AVG_CHAR_W * fs))
        lines = math.ceil(n / chars_per_line)
        if lines * fs * line_height <= max(box_h_pt, fs) * height_growth:
            best = fs
        fs += 0.5
    return round(best, 1)
