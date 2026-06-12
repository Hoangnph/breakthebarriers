"""Heuristic photo-vs-diagram classifier for cropped 'picture' figures (#0).

Deterministic, offline (OpenCV/numpy). Each of four cues votes 'photo' or
'diagram'; the signed margin decides, with an ambiguous band returning
'uncertain' (which callers treat as preserve). An AI vision fallback is declared
as a Protocol only — it is NOT used at extraction time (reserved for #2/#3)."""
from __future__ import annotations
from typing import Protocol, Tuple
import numpy as np
import cv2

# Cue thresholds (clear margins; tuned against synthetic extremes).
_COLOR_RATIO_HI = 0.20      # unique-color ratio: above → photo
_COLOR_RATIO_LO = 0.05      # below → diagram
_SAT_HI = 0.25              # mean saturation [0,1]: above → photo
_SAT_LO = 0.10              # below → diagram
_WHITE_HI = 0.45            # near-white fraction: above → diagram
_WHITE_LO = 0.10            # below → photo
_LINES_HI = 4               # # long straight lines: >= → diagram, 0 → photo


class PictureVisionClassifier(Protocol):
    """AI fallback contract (reserved for #2/#3; not used at extraction)."""
    def classify(self, crop_bgr: np.ndarray) -> str: ...   # "photo" | "diagram"


def _features(img: np.ndarray) -> dict:
    h, w = img.shape[:2]
    scale = 256.0 / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                         interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    n = max(1, h * w)
    # unique quantised colors (4 bits/channel)
    q = (img >> 4).astype(np.uint16)
    codes = (q[..., 0].astype(np.uint32) << 8) | (q[..., 1].astype(np.uint32) << 4) | q[..., 2]
    color_ratio = np.unique(codes).size / n
    # mean saturation
    sat_mean = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].mean() / 255.0
    # near-white fraction
    white_frac = float((img.min(axis=2) > 230).sum()) / n
    # long straight lines
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=200,
                            minLineLength=int(min(h, w) * 0.3), maxLineGap=5)
    n_lines = 0 if lines is None else len(lines)
    return {"color_ratio": color_ratio, "sat_mean": sat_mean,
            "white_frac": white_frac, "n_lines": n_lines}


def classify_picture(img_bgr: np.ndarray) -> Tuple[str, float]:
    """Return (label, confidence) with label in {photo, diagram, uncertain}."""
    f = _features(img_bgr)
    photo = diagram = 0
    if f["color_ratio"] > _COLOR_RATIO_HI: photo += 1
    elif f["color_ratio"] < _COLOR_RATIO_LO: diagram += 1
    if f["sat_mean"] > _SAT_HI: photo += 1
    elif f["sat_mean"] < _SAT_LO: diagram += 1
    if f["white_frac"] > _WHITE_HI: diagram += 1
    elif f["white_frac"] < _WHITE_LO: photo += 1
    if f["n_lines"] >= _LINES_HI: diagram += 1
    elif f["n_lines"] == 0: photo += 1
    margin = photo - diagram
    conf = abs(margin) / 4.0
    if margin >= 2:
        return "photo", conf
    if margin <= -2:
        return "diagram", conf
    return "uncertain", conf


def classify_picture_file(path: str) -> Tuple[str, float]:
    """Load an image file and classify it; missing/unreadable → ('uncertain', 0.0)."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return "uncertain", 0.0
    return classify_picture(img)
