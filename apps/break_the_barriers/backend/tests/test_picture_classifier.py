import numpy as np
import cv2
from backend.app.services.picture_classifier import classify_picture


def test_black_lines_on_white_is_diagram():
    img = np.full((256, 256, 3), 255, np.uint8)        # white background
    for y in (40, 90, 140, 190):                       # many long straight lines
        cv2.line(img, (10, y), (245, y), (0, 0, 0), 2)
    cv2.rectangle(img, (20, 20), (230, 230), (0, 0, 0), 2)
    label, conf = classify_picture(img)
    assert label == "diagram"
    assert 0.0 <= conf <= 1.0


def test_colorful_noise_is_photo():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)   # many colors, high saturation
    label, _ = classify_picture(img)
    assert label == "photo"


def test_flat_gray_block_is_uncertain():
    img = np.full((256, 256, 3), 128, np.uint8)        # flat gray: mixed evidence
    label, _ = classify_picture(img)
    assert label == "uncertain"
