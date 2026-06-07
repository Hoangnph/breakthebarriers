from backend.app.services.figure_grouper import cluster_figures


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
