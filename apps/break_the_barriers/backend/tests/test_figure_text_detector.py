import cv2
import numpy as np
from backend.app.services.figure_text_detector import detect_text_boxes


def _text_png(path, word="FOREWORD"):
    img = np.full((140, 600, 3), 255, np.uint8)            # white bg
    cv2.putText(img, word, (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 5)
    cv2.imwrite(str(path), img)


def test_detects_text_returns_boxes(tmp_path):
    p = tmp_path / "banner.png"; _text_png(p)
    boxes = detect_text_boxes(str(p))
    assert len(boxes) >= 1
    l, t, w, h = boxes[0]
    assert w > 0 and h > 0


def test_blank_image_no_boxes(tmp_path):
    p = tmp_path / "blank.png"
    cv2.imwrite(str(p), np.full((140, 600, 3), 255, np.uint8))
    assert detect_text_boxes(str(p)) == []


def test_missing_path_no_boxes(tmp_path):
    assert detect_text_boxes(str(tmp_path / "nope.png")) == []
