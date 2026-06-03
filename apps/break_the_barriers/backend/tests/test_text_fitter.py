from backend.app.services.text_fitter import fit_font_size


def test_short_text_keeps_base_size():
    fs = fit_font_size("Hi", box_w_pt=400, box_h_pt=100, max_size=24, min_size=6)
    assert fs == 24.0


def test_long_text_shrinks_below_base():
    short = fit_font_size("AI", box_w_pt=120, box_h_pt=30, max_size=24, min_size=6)
    long = fit_font_size("HƯỚNG DẪN CÔNG NGHỆ TRÍ TUỆ DÀNH CHO LÃNH ĐẠO DU LỊCH",
                         box_w_pt=120, box_h_pt=30, max_size=24, min_size=6)
    assert long < short


def test_never_below_min():
    fs = fit_font_size("x" * 5000, box_w_pt=20, box_h_pt=10, max_size=24, min_size=8)
    assert fs == 8.0


def test_returns_float_in_range():
    fs = fit_font_size("some heading text", box_w_pt=200, box_h_pt=40,
                       max_size=24, min_size=6)
    assert 6.0 <= fs <= 24.0
