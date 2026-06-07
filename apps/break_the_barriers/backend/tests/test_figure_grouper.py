from PIL import Image
from backend.app.services.figure_grouper import (
    cluster_figures, group_merge_bbox, plan_merge_groups, crop_group_region)


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


def test_group_merge_bbox_extends_down_to_caption_block():
    members = [[143, 153, 91, 100], [358, 153, 91, 100]]
    bb = group_merge_bbox(members, [[221, 288, 154, 12]])
    assert bb[0] == 143 and bb[1] == 153
    assert 253 < bb[1] + bb[3] <= 288


def test_group_merge_bbox_default_extension_without_block():
    bb = group_merge_bbox([[100, 100, 80, 100]], [])
    assert abs((bb[1] + bb[3]) - (200 + 0.35 * 100)) < 0.01


def test_plan_merge_groups_merges_clean_cluster():
    fig_bboxes = [[143, 153, 91, 100], [249, 153, 91, 100], [358, 153, 91, 100]]
    plans = plan_merge_groups(fig_bboxes, [[221, 288, 154, 12]])
    assert len(plans) == 1
    assert plans[0]["members"] == [0, 1, 2]
    assert plans[0]["bbox"][0] == 143 and plans[0]["bbox"][1] == 153


def test_plan_merge_groups_merges_distinct_image_row():
    # two distinct images side by side, no text between → still merged (one crop)
    plans = plan_merge_groups([[40, 40, 80, 80], [140, 40, 80, 80]], [])
    assert len(plans) == 1 and plans[0]["members"] == [0, 1]


def test_plan_merge_groups_skips_when_unrelated_body_text_inside():
    # a body paragraph sits between the two figures (inside the union, outside both)
    fig_bboxes = [[40, 40, 60, 200], [300, 40, 60, 200]]
    body = [[120, 100, 160, 20]]   # center (200,110) inside union, outside figures
    assert plan_merge_groups(fig_bboxes, body) == []


def test_crop_group_region_scales_to_raster_pixels(tmp_path):
    src = tmp_path / "page.png"
    Image.new("RGB", (600, 800), (10, 20, 30)).save(src)
    crop = crop_group_region(Image.open(src), [10, 20, 30, 40], 300.0, 400.0)
    assert crop.size == (60, 80)
