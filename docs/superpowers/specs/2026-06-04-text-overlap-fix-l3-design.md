# L3 — Text-overlap fix (available-slot clamp) — Design

Date: 2026-06-04
Branch: `feat/faithful-overlay-translation`
Status: approved (ready for implementation plan)

## Problem

On reconstructed **text-layer** pages, translated Vietnamese text overlaps the
block below it and line alignment breaks. This is a **layout bug, not a
background bug** — regenerating/inpainting the page background does NOT fix it.

### Root cause

In `app/services/text_layer_renderer.py`, each translated block is emitted as an
absolutely-positioned `<div class="tl-text">` with a `width` but **no height
constraint**. The CSS class has `overflow: hidden`, but with auto-height the div
grows to fit its content, so `scrollHeight === clientHeight` always holds.

The client-side fit loop is:

```js
while (d.scrollHeight > d.clientHeight + 1 && g < 40) { /* shrink font */ }
```

Because the condition is never true (auto-height div), **the loop never runs**,
the font never shrinks, and longer Vietnamese text overflows downward into the
next block → overlap.

A second, related inconsistency: `text_fitter.fit_font_size` already allows a
block to grow to `height_growth=1.6×` its bbox height before shrinking the font,
but the renderer reserves no vertical space for that growth and places
neighboring blocks at their original bbox tops — so even the server-side
estimate assumes room that does not exist on the page.

### Why "available-slot" (data-grounded)

Inspecting a real page (`2024-wttc-introduction-to-ai-3.model.json`): body
paragraphs are `h≈52.8 pt` with a consistent `≈13.2 pt` gap below (≈ one line,
~25% slack); headings have large gaps (100+ pt). Vietnamese's extra length
largely fits into this **existing whitespace** if a block may expand into the
gap below it, shrinking the font only when even that gap is insufficient.

## Approach (chosen: B — available-slot clamp)

Bound each text block by its **real vertical slot** — the distance from its top
to the nearest obstacle below it — instead of leaving it unbounded or clamping
it to the original bbox height. Faithful top position is preserved; text grows
into real whitespace; it never overlaps; font shrinks only as a last resort.

Rejected alternatives:
- **A — simple clamp to bbox `h`:** simplest, stops overlap, but ignores the
  free whitespace → single-line blocks and wrapping headings shrink the font
  hard → some unreadably small text.
- **C — full reflow (blocks push each other down):** most readable but breaks
  absolute fidelity, collides with figures, high complexity.

## Components

### 1. `compute_slot_heights` — new pure function

Location: `app/services/text_layer_renderer.py` (pure, unit-testable).

```
compute_slot_heights(blocks, figures, page_h) -> dict[span_id, slot_pt]
```

For each text block `i` with bbox `(l, t, w, h)`:

- **Obstacle below:** another block or figure `j` is an obstacle for `i` when
  - their x-ranges overlap by more than a fraction of the narrower box
    (fractional-overlap threshold, so side-by-side columns do NOT constrain each
    other), **and**
  - `top_j > top_i`.
- `nearest_top = min(top_j over obstacles below)`; if none, `nearest_top =
  page_h`.
- `slot_pt = max(h, nearest_top - top_i)` — the `max(h, …)` guards pre-existing
  overlaps so a slot is never smaller than the original box.

Figures are obstacles (text must not grow over an image) but are not themselves
assigned slots.

### 2. CSS bounds on `.tl-text`

Each block div is emitted with, in addition to its existing `left/top/width`:

- `min-height: {pct(bbox_h, page_h)}%` — box always covers ≥ the original text
  area, so a box fill/scrim still masks the source raster when the translation
  is *shorter* than the source.
- `max-height: {pct(slot_pt, page_h)}%` — combined with the existing
  `overflow: hidden`, the content is clipped at the slot and
  `scrollHeight > clientHeight` becomes true when text exceeds the slot, so the
  client fit loop fires.

Vertical alignment stays top (default), matching the original block top. Box
fill/scrim hugs the content height (≤ max-height), so it does not paint over
empty whitespace.

### 3. Wire into `render_text_layer`

- Compute `slots = compute_slot_heights(model.blocks, model.figures, ph)` once.
- Per block, feed the slot to the server-side fitter so the initial paint is
  already close: `fit_font_size(text, w, slot_pt, max_size=base, min_size=6.0,
  height_growth=1.0)` — `height_growth=1.0` because the slot is now the hard
  ceiling (no extra implied growth).
- Emit `min-height`/`max-height` in the div `style`.
- The client fit loop is unchanged; it now functions because the div is bounded.

### Units

bbox values and `page_w/page_h` are PDF points (PyMuPDF). Slots are computed in
points and converted to percentages via the existing `_pct()` helper, so they
scale with the page transform.

## Out of scope / non-changes

- No DB schema change, no extraction-pipeline change, no `model.json` change.
- `text_fitter.fit_font_size` signature and default `height_growth=1.6` are
  unchanged; only the **call site** passes `height_growth=1.0` with the slot.
- Background regeneration / inpainting (AI background) remains a separate,
  optional enhancement and is explicitly NOT part of this fix.

## Testing (TDD)

Unit-test `compute_slot_heights`:
- single block → slot reaches page bottom (`page_h - top`);
- two vertically-stacked, x-overlapping blocks → upper slot = `top_lower -
  top_upper`, lower slot = `page_h - top_lower`;
- two side-by-side blocks (no x-overlap) → slots independent, each to page
  bottom;
- figure positioned below a block → slot clipped to the figure top;
- pre-existing overlap (`top_j < bottom_i`) → slot = `max(h, …)` guard holds.

Renderer integration: for a 2-block model, assert the emitted HTML contains the
expected `max-height`/`min-height` for each block.

## Files touched

- `app/services/text_layer_renderer.py` — add `compute_slot_heights`; emit
  bounds; pass slot + `height_growth=1.0` to the fitter.
- `tests/` — new tests for `compute_slot_heights` and renderer bounds.
