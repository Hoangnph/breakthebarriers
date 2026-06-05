"""Resolve a page's background treatment from its #0 eligibility labels.

base-color  -> render on the document base color (drop the text-baked raster);
               kills the ghost on content pages.
keep-raster -> keep the original raster exactly (diagrams/charts/tables).
clean-photo -> ideal: AI removes baked-in text and keeps the photo (Phase 2).
               Phase 1 has no AI, so the renderer treats clean-photo like
               keep-raster (cover stays raster, ghost remains on covers only)."""
from __future__ import annotations


def resolve_background_policy(page_class: str, cover: str) -> str:
    # A front/back cover is a photo/design page, never a content diagram, so it
    # is always background-cleanable — even if the per-figure heuristic was
    # uncertain and labelled the page `preserve`. Cover wins over page_class.
    if cover in ("front", "back"):
        return "clean-photo"
    if page_class == "preserve":
        return "keep-raster"
    if page_class == "regenerable":
        return "base-color"
    if page_class == "text":
        return "base-color"
    return "keep-raster"   # safe default for unknown labels


_VALID_POLICIES = ("base-color", "keep-raster", "clean-photo")


def effective_policy(page_class: str, cover: str, override) -> str:
    """A valid manual override wins; otherwise fall back to the auto policy."""
    if override in _VALID_POLICIES:
        return override
    return resolve_background_policy(page_class, cover)
