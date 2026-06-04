"""Resolve a page's background treatment from its #0 eligibility labels.

base-color  -> render on the document base color (drop the text-baked raster);
               kills the ghost on content pages.
keep-raster -> keep the original raster exactly (diagrams/charts/tables).
clean-photo -> ideal: AI removes baked-in text and keeps the photo (Phase 2).
               Phase 1 has no AI, so the renderer treats clean-photo like
               keep-raster (cover stays raster, ghost remains on covers only)."""
from __future__ import annotations


def resolve_background_policy(page_class: str, cover: str) -> str:
    if page_class == "preserve":
        return "keep-raster"
    if page_class == "regenerable":
        if cover in ("front", "back"):
            return "clean-photo"
        return "base-color"
    if page_class == "text":
        return "base-color"
    return "keep-raster"   # safe default for unknown labels
