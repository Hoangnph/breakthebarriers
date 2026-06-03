"""Dispatch a PageModel to the right renderer by `kind`:
  text          -> TextLayerRenderer (real HTML, no raster)
  image | mixed -> existing render_overlay_html (raster background preserved)
"""
from __future__ import annotations

from backend.app.services.page_model import PageModel
from backend.app.services.text_layer_renderer import render_text_layer
from backend.app.services.overlay_renderer import render_overlay_html


def _model_to_overlay_layout(model: PageModel) -> dict:
    """Adapt PageModel to the dict shape render_overlay_html expects."""
    return {
        "page_w": model.page_w, "page_h": model.page_h,
        "image": (model.background or {}).get("image"),
        "blocks": [
            {"span_id": b.span_id, "bbox": b.bbox,
             "bg": (model.background or {}).get("color", "#ffffff")}
            for b in model.blocks
        ],
    }


def render_page(model: PageModel, translations: dict, image_url_base: str) -> str:
    if model.kind == "text":
        return render_text_layer(model, translations, image_url_base)
    return render_overlay_html(_model_to_overlay_layout(model), translations, image_url_base)
