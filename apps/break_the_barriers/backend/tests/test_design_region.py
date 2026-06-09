from backend.app.services.design_region import infer_figure_align
from backend.app.services.design_region import detect_design_regions, Region


def test_align_center_symmetric_margins():
    # p7-like figure on a 595-wide page: left 158 ≈ right 155 → center
    assert infer_figure_align([158, 53, 282, 273], 595) == "center"


def test_align_left_when_left_margin_small():
    assert infer_figure_align([40, 0, 200, 100], 595) == "left"


def test_align_right_when_pushed_right():
    # left 355 >> right 40 → right
    assert infer_figure_align([355, 0, 200, 100], 595) == "right"


def test_align_left_when_no_page_width():
    assert infer_figure_align([10, 0, 50, 50], 0) == "left"


def test_figure_align_roundtrip():
    from backend.app.services.page_model import PageModel, Figure
    pm = PageModel(page_w=1, page_h=1, kind="text", background={},
                   blocks=[], figures=[Figure(bbox=[1, 2, 3, 4], img="a.png", align="center")])
    pm2 = PageModel.from_json(pm.to_json())
    assert pm2.figures[0].align == "center"


def test_figure_align_defaults_left_on_old_json():
    import json
    from backend.app.services.page_model import PageModel
    j = json.dumps({"page_w": 1, "page_h": 1, "kind": "text", "background": {},
                    "blocks": [], "figures": [{"bbox": [1, 2, 3, 4], "img": "a.png"}]})
    assert PageModel.from_json(j).figures[0].align == "left"


def test_detect_chat_region_groups_icons_and_text():
    # 3 avatar icons spanning a tall band + 2 body blocks interleaved → 1 region
    figs = [[71, 90, 31, 31], [493, 338, 31, 31], [66, 595, 31, 31]]
    blocks = [("s1", [120, 100, 300, 20]), ("s2", [120, 400, 300, 20])]
    regs = detect_design_regions(figs, blocks, 595, 842)
    assert len(regs) == 1
    assert regs[0].figure_idx == {0, 1, 2}
    assert {"s1", "s2"} <= regs[0].block_ids
    # union bbox covers from top icon to bottom icon (with padding)
    assert regs[0].bbox[1] <= 90 and regs[0].bbox[1] + regs[0].bbox[3] >= 626


def test_no_region_on_plain_text_page():
    blocks = [("s1", [120, 100, 300, 20]), ("s2", [120, 200, 300, 20])]
    assert detect_design_regions([], blocks, 595, 842) == []


def test_no_region_with_single_icon():
    figs = [[71, 90, 31, 31]]
    assert detect_design_regions(figs, [("s1", [120, 300, 300, 20])], 595, 842) == []


def test_no_region_when_icons_span_too_short():
    # two icons very close together (span ~51 pt << 0.2*842) → not a design band
    figs = [[71, 90, 31, 31], [71, 110, 31, 31]]
    assert detect_design_regions(figs, [("s1", [120, 95, 300, 20])], 595, 842) == []
