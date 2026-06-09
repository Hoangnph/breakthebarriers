from backend.app.services.design_region import infer_figure_align


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
