from backend.app.services.page_model import FontSpec, Block, Figure
from backend.app.services.text_layer_renderer import compute_slot_heights


def _blk(span_id, l, t, w, h):
    return Block(span_id=span_id, role="body", bbox=[l, t, w, h], text="x",
                 font=FontSpec(11, 400, False, "#000", "left", "sans"))


def _fig(l, t, w, h):
    return Figure(bbox=[l, t, w, h], img="f.png")


def test_single_block_slot_reaches_page_bottom():
    slots = compute_slot_heights([_blk("s1", 72, 100, 200, 50)], [], page_h=842.0)
    assert slots["s1"] == 742.0  # 842 - 100


def test_stacked_blocks_clip_to_next_top():
    blocks = [_blk("s1", 72, 100, 200, 50), _blk("s2", 72, 200, 200, 50)]
    slots = compute_slot_heights(blocks, [], page_h=842.0)
    assert slots["s1"] == 100.0   # 200 - 100 (next block top)
    assert slots["s2"] == 642.0   # 842 - 200 (page bottom)


def test_side_by_side_blocks_do_not_constrain_each_other():
    # b1 left column (50..250), b2 right column (300..500): no x-overlap.
    blocks = [_blk("s1", 50, 100, 200, 50), _blk("s2", 300, 300, 200, 50)]
    slots = compute_slot_heights(blocks, [], page_h=842.0)
    assert slots["s1"] == 742.0   # not clipped by b2 (different column)
    assert slots["s2"] == 542.0   # 842 - 300


def test_figure_below_clips_slot():
    block = _blk("s1", 72, 100, 200, 50)
    fig = _fig(72, 300, 200, 150)
    slots = compute_slot_heights([block], [fig], page_h=842.0)
    assert slots["s1"] == 200.0   # 300 (figure top) - 100


def test_preexisting_overlap_keeps_original_height():
    # b2 top (150) sits inside b1 (100..200): slot must not drop below b1's height.
    blocks = [_blk("s1", 72, 100, 200, 100), _blk("s2", 72, 150, 200, 50)]
    slots = compute_slot_heights(blocks, [], page_h=842.0)
    assert slots["s1"] == 100.0   # max(h=100, 150-100=50) == 100


def test_overlap_frac_threshold_is_configurable():
    # b2 overlaps b1's x-range by 40px out of b1 width 200 = 0.20 fraction.
    b1 = _blk("s1", 0, 100, 200, 50)
    b2 = _blk("s2", 160, 200, 200, 50)  # x 160..360 vs 0..200 -> overlap 40 (0.20)
    # At default 0.25: below threshold -> not an obstacle -> slot to page bottom.
    assert compute_slot_heights([b1, b2], [], page_h=842.0)["s1"] == 742.0
    # At 0.15: above threshold -> b2 is an obstacle -> slot clipped to b2 top (200).
    assert compute_slot_heights([b1, b2], [], page_h=842.0, overlap_frac=0.15)["s1"] == 100.0
