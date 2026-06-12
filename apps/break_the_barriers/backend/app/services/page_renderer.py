"""Dispatch a PageModel to the unified text-layer renderer for ALL kinds:
text (no raster), image/mixed (raster background + per-block fill/scrim boxes).
The legacy render_overlay_html remains in overlay_renderer.py for the
layout_json fallback path used when a page has no PageModel."""
from __future__ import annotations

from backend.app.services.page_model import PageModel
from backend.app.services.text_layer_renderer import render_text_layer


def render_page(model: PageModel, translations: dict, image_url_base: str) -> str:
    return render_text_layer(model, translations, image_url_base)
