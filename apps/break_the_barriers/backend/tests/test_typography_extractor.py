from backend.app.services.typography_extractor import (
    classify_font_family, int_color_to_hex, is_bold, is_italic, iou, aggregate_font,
)
from backend.app.services.page_model import FontSpec


def test_classify_font_family():
    assert classify_font_family("Courier New") == "mono"
    assert classify_font_family("JetBrainsMono-Regular") == "mono"
    assert classify_font_family("TimesNewRomanPSMT") == "serif"
    assert classify_font_family("Georgia") == "serif"
    assert classify_font_family("Helvetica-Bold") == "sans"
    assert classify_font_family("ArialMT") == "sans"
    assert classify_font_family("") == "sans"  # default


def test_int_color_to_hex():
    assert int_color_to_hex(0) == "#000000"
    assert int_color_to_hex(0xFFFFFF) == "#ffffff"
    assert int_color_to_hex(0x1A1A1A) == "#1a1a1a"


def test_bold_italic_flags():
    assert is_bold(16) is True
    assert is_bold(0) is False
    assert is_italic(2) is True
    assert is_italic(0) is False


def test_iou():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [100, 100, 10, 10]) == 0.0
    assert round(iou([0, 0, 10, 10], [5, 0, 10, 10]), 3) == round(50 / 150, 3)


def test_aggregate_font_picks_dominant():
    spans = [
        {"size": 24.0, "flags": 16, "color": 0x1A1A1A, "font": "Helvetica-Bold"},
        {"size": 24.0, "flags": 16, "color": 0x1A1A1A, "font": "Helvetica-Bold"},
        {"size": 11.0, "flags": 0,  "color": 0x000000, "font": "Helvetica"},
    ]
    fs = aggregate_font(spans, align="center")
    assert isinstance(fs, FontSpec)
    assert fs.size == 24.0
    assert fs.weight == 700
    assert fs.italic is False
    assert fs.color == "#1a1a1a"
    assert fs.align == "center"
    assert fs.family_class == "sans"


def test_aggregate_font_empty_returns_none():
    assert aggregate_font([], align="left") is None
