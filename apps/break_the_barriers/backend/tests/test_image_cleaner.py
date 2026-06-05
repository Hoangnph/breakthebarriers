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
