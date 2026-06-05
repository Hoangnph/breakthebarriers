import types
from PIL import Image
from backend.app.services.image_cleaner import clean_page_background
from backend.app.services.image_cleaner import _gemini_clean_bytes


def _make_png(path):
    Image.new("RGB", (8, 8), (10, 20, 30)).save(path)


def _client_returning(data):
    part = types.SimpleNamespace(inline_data=types.SimpleNamespace(data=data))
    content = types.SimpleNamespace(parts=[part])
    resp = types.SimpleNamespace(candidates=[types.SimpleNamespace(content=content)])
    return types.SimpleNamespace(
        models=types.SimpleNamespace(generate_content=lambda **kw: resp))


def test_writes_cleaned_image_on_success(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    out = tmp_path / "page-1.clean.png"
    ok = clean_page_background(str(src), str(out), client=_client_returning(b"PNGBYTES"))
    assert ok is True
    assert out.read_bytes() == b"PNGBYTES"


def test_returns_false_when_no_image_in_response(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    out = tmp_path / "page-1.clean.png"
    empty = types.SimpleNamespace(content=types.SimpleNamespace(parts=[]))
    client = types.SimpleNamespace(models=types.SimpleNamespace(
        generate_content=lambda **kw: types.SimpleNamespace(candidates=[empty])))
    assert clean_page_background(str(src), str(out), client=client) is False
    assert not out.exists()


def test_returns_false_on_client_error(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    out = tmp_path / "page-1.clean.png"
    def _boom(**kw):
        raise RuntimeError("api down")
    client = types.SimpleNamespace(models=types.SimpleNamespace(generate_content=_boom))
    assert clean_page_background(str(src), str(out), client=client) is False


def test_gemini_clean_bytes_returns_data(tmp_path):
    src = tmp_path / "page-1.png"; _make_png(src)
    data = _gemini_clean_bytes(str(src), client=_client_returning(b"AIBYTES"))
    assert data == b"AIBYTES"


def test_gemini_clean_bytes_none_when_no_image(tmp_path):
    import types
    src = tmp_path / "page-1.png"; _make_png(src)
    empty = types.SimpleNamespace(content=types.SimpleNamespace(parts=[]))
    client = types.SimpleNamespace(models=types.SimpleNamespace(
        generate_content=lambda **kw: types.SimpleNamespace(candidates=[empty])))
    assert _gemini_clean_bytes(str(src), client=client) is None


import numpy as np
from backend.app.services.image_cleaner import build_text_mask, composite_inpaint


def test_build_text_mask_marks_box_and_clears_corner():
    mask = build_text_mask([(40, 40, 20, 20)], 100, 100, dilate=0, feather=0)
    assert mask.shape == (100, 100)
    assert mask[50, 50] == 1.0
    assert mask[0, 0] == 0.0


def test_build_text_mask_dilate_expands():
    base = build_text_mask([(40, 40, 20, 20)], 100, 100, dilate=0, feather=0)
    grown = build_text_mask([(40, 40, 20, 20)], 100, 100, dilate=6, feather=0)
    assert grown.sum() > base.sum()


def test_composite_takes_ai_inside_mask_original_outside():
    original = np.zeros((40, 40, 3), np.uint8); original[:, :, 0] = 255   # BGR blue
    ai = np.zeros((40, 40, 3), np.uint8); ai[:, :, 2] = 255               # BGR red
    mask = build_text_mask([(15, 15, 10, 10)], 40, 40, dilate=0, feather=0)
    out = composite_inpaint(original, ai, mask)
    assert out[20, 20, 2] > 200 and out[20, 20, 0] < 60   # center = red (ai)
    assert out[0, 0, 0] > 200 and out[0, 0, 2] < 60       # corner = blue (original)


import cv2
from backend.app.services.image_cleaner import clean_page_background_inpaint


def _png_bytes(bgr):
    ok, buf = cv2.imencode(".png", bgr)
    return buf.tobytes()


def test_inpaint_composites_ai_only_in_mask(tmp_path):
    src = tmp_path / "page-1.png"
    blue = np.zeros((40, 40, 3), np.uint8); blue[:, :, 0] = 255   # original blue
    cv2.imwrite(str(src), blue)
    red = np.zeros((40, 40, 3), np.uint8); red[:, :, 2] = 255     # AI red
    out = tmp_path / "page-1.clean-inpaint.png"
    ok = clean_page_background_inpaint(
        str(src), str(out), [(15, 15, 10, 10)],
        client=_client_returning(_png_bytes(red)))
    assert ok is True
    res = cv2.imread(str(out))
    assert res[20, 20, 2] > 200      # center = red (AI inpainted)
    assert res[0, 0, 0] > 200        # corner = blue (original preserved)


def test_inpaint_false_when_ai_returns_no_image(tmp_path):
    import types
    src = tmp_path / "page-1.png"
    cv2.imwrite(str(src), np.zeros((10, 10, 3), np.uint8))
    out = tmp_path / "o.png"
    empty = types.SimpleNamespace(content=types.SimpleNamespace(parts=[]))
    client = types.SimpleNamespace(models=types.SimpleNamespace(
        generate_content=lambda **kw: types.SimpleNamespace(candidates=[empty])))
    assert clean_page_background_inpaint(str(src), str(out), [(1, 1, 2, 2)],
                                         client=client) is False
