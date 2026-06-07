from backend.app.services.figure_grouper import cluster_figures, decide_mode, group_merge_bbox


def test_three_same_row_figures_cluster():
    bboxes = [[143, 153, 91, 100], [249, 153, 91, 100], [358, 153, 91, 100]]
    assert cluster_figures(bboxes) == [[0, 1, 2]]


def test_far_apart_figures_do_not_cluster():
    bboxes = [[40, 40, 80, 80], [400, 600, 80, 80]]
    assert cluster_figures(bboxes) == []


def test_two_by_two_grid_clusters():
    bboxes = [[40, 40, 80, 80], [140, 40, 80, 80],
              [40, 140, 80, 80], [140, 140, 80, 80]]
    assert cluster_figures(bboxes) == [[0, 1, 2, 3]]


def test_decide_mode_merge_when_inside_one_pdf_image():
    assert decide_mode([143, 153, 306, 100], [(129, 140, 467, 285)]) == "merge"


def test_decide_mode_grid_when_not_in_one_image():
    assert decide_mode([40, 40, 400, 80],
                       [(40, 40, 120, 120), (300, 40, 380, 120)]) == "grid"


def test_group_merge_bbox_extends_down_to_caption_block():
    members = [[143, 153, 91, 100], [358, 153, 91, 100]]
    bb = group_merge_bbox(members, [[221, 288, 154, 12]])
    assert bb[0] == 143 and bb[1] == 153
    assert 253 < bb[1] + bb[3] <= 288


def test_group_merge_bbox_default_extension_without_block():
    bb = group_merge_bbox([[100, 100, 80, 100]], [])
    assert abs((bb[1] + bb[3]) - (200 + 0.35 * 100)) < 0.01
