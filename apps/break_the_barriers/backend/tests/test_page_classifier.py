from backend.app.services.page_classifier import classify_kind


def test_text_page():
    blocks = [[0, i * 20, 400, 15] for i in range(20)]
    assert classify_kind(595, 842, blocks, []) == "text"


def test_image_page_full_bleed():
    figures = [[0, 0, 595, 842]]
    blocks = [[40, 700, 120, 18]]
    assert classify_kind(595, 842, blocks, figures) == "image"


def test_mixed_page():
    figures = [[0, 0, 595, 300]]
    blocks = [[40, 320 + i * 20, 500, 15] for i in range(12)]
    assert classify_kind(595, 842, blocks, figures) == "mixed"


def test_empty_page_defaults_mixed():
    assert classify_kind(595, 842, [], []) == "mixed"
