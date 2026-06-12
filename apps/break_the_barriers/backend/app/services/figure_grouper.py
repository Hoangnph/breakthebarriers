"""Group figures that a PDF split into several crops back into a faithful unit.

Pure geometry helpers (cluster, decide mode, merged bbox) + a raster crop. bbox is
[x0, y0, w, h] for figures/blocks; PDF embedded-image bbox is (x0, y0, x1, y1)."""
from __future__ import annotations
from typing import List


def _inflate(bbox, frac: float):
    x0, y0, w, h = bbox
    dx, dy = w * frac, h * frac
    return (x0 - dx, y0 - dy, x0 + w + dx, y0 + h + dy)


def _intersects(a, b) -> bool:   # a, b = (x0, y0, x1, y1)
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def cluster_figures(bboxes: List[list], inflate: float = 0.3) -> List[List[int]]:
    """Cluster figures whose bboxes (each inflated by `inflate`) intersect, by
    transitive closure. Returns sorted index lists for clusters of >= 2 figures."""
    n = len(bboxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    inf = [_inflate(b, inflate) for b in bboxes]
    for i in range(n):
        for j in range(i + 1, n):
            if _intersects(inf[i], inf[j]):
                parent[find(i)] = find(j)
    groups: dict = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for g in groups.values() if len(g) >= 2]


_ICON_MAX_FRAC = 0.15       # icon = small in BOTH dimensions
_REGION_MAX_BLOCKS = 2      # content-region = overlaps more text blocks than this
_MIN_BODY_H = 20.0          # a stray block this tall is multi-line body (protect it)


def _center_in(cx, cy, bbox) -> bool:
    x0, y0, w, h = bbox
    return x0 <= cx <= x0 + w and y0 <= cy <= y0 + h


def _is_image_like(fig_bbox, page_w: float, page_h: float, block_bboxes) -> bool:
    """A figure worth grouping: not a tiny icon, not a text-heavy content region.
    (Banners are excluded upstream — they are consumed as title overlays.)"""
    x0, y0, w, h = fig_bbox
    if page_w and page_h and w < _ICON_MAX_FRAC * page_w and h < _ICON_MAX_FRAC * page_h:
        return False
    n = sum(1 for b in block_bboxes
            if _center_in(b[0] + b[2] / 2, b[1] + b[3] / 2, fig_bbox))
    return n <= _REGION_MAX_BLOCKS


def _has_stray_text(union_bbox, member_bboxes, block_bboxes) -> bool:
    """True if MULTI-LINE body text sits inside the cluster's union region but
    outside every member figure — merging would bake a real paragraph, so don't.
    One-line labels (e.g. a diagram caption) are fine to bake and do not block."""
    for b in block_bboxes:
        if b[3] < _MIN_BODY_H:        # one-line label → ok to bake
            continue
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        if _center_in(cx, cy, union_bbox) and not any(
                _center_in(cx, cy, m) for m in member_bboxes):
            return True
    return False


def group_merge_bbox(member_bboxes, block_bboxes,
                     default_frac: float = 0.35, cap_frac: float = 0.5):
    """Union of the members, extended downward to capture a baked caption strip:
    down to just above the nearest text block below (x-overlapping), capped at
    +cap_frac of group height; if none, +default_frac. Returns [x0, y0, w, h]."""
    x0 = min(b[0] for b in member_bboxes)
    y0 = min(b[1] for b in member_bboxes)
    x1 = max(b[0] + b[2] for b in member_bboxes)
    y1 = max(b[1] + b[3] for b in member_bboxes)
    gh = y1 - y0
    belows = [b[1] for b in block_bboxes
              if b[1] >= y1 and x0 <= (b[0] + b[2] / 2) <= x1]
    if belows:
        new_y1 = max(y1, min(min(belows), y1 + cap_frac * gh) - 2.0)
    else:
        new_y1 = y1 + default_frac * gh
    return [x0, y0, x1 - x0, new_y1 - y0]


def plan_merge_groups(fig_bboxes, block_bboxes, page_w: float, page_h: float):
    """Cluster the IMAGE-LIKE figures (skip icons and content regions) and merge each
    cluster into one crop, EXCEPT clusters whose union holds multi-line body text.
    Returns {"members": [original idx...], "bbox": merged_bbox} per merged cluster."""
    elig = [i for i, fb in enumerate(fig_bboxes)
            if _is_image_like(fb, page_w, page_h, block_bboxes)]
    elig_bboxes = [fig_bboxes[i] for i in elig]
    out = []
    for local in cluster_figures(elig_bboxes):
        members = [elig[k] for k in local]
        mb = [fig_bboxes[i] for i in members]
        x0 = min(b[0] for b in mb); y0 = min(b[1] for b in mb)
        x1 = max(b[0] + b[2] for b in mb); y1 = max(b[1] + b[3] for b in mb)
        if _has_stray_text([x0, y0, x1 - x0, y1 - y0], mb, block_bboxes):
            continue
        out.append({"members": members,
                    "bbox": group_merge_bbox(mb, block_bboxes)})
    return out


def crop_group_region(img, bbox, page_w: float, page_h: float):
    """Crop region `bbox` (page units) from a PIL raster `img`, scaling page→pixels."""
    sx, sy = img.width / page_w, img.height / page_h
    x0, y0, w, h = bbox
    box = (int(x0 * sx), int(y0 * sy), int((x0 + w) * sx), int((y0 + h) * sy))
    return img.crop(box)
