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
