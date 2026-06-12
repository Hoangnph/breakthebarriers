from backend.app.services.background_policy import effective_policy


def test_valid_override_wins():
    assert effective_policy("preserve", "front", "base-color") == "base-color"
    assert effective_policy("text", "none", "keep-raster") == "keep-raster"
    assert effective_policy("regenerable", "none", "clean-photo") == "clean-photo"


def test_none_override_uses_auto():
    assert effective_policy("preserve", "front", None) == "clean-photo"   # auto (cover wins)
    assert effective_policy("text", "none", None) == "base-color"


def test_invalid_override_uses_auto():
    assert effective_policy("preserve", "none", "garbage") == "keep-raster"
    assert effective_policy("text", "none", "") == "base-color"
