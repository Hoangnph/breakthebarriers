from backend.app.services.toc_parser import parse_toc_entry, is_toc_page


def test_dotted_entry():
    assert parse_toc_entry("Tiêu đề......3") == ("Tiêu đề", "3")


def test_tab_entry():
    assert parse_toc_entry("Thuật toán : Bộ não của AI\t 8") == ("Thuật toán : Bộ não của AI", "8")


def test_ellipsis_entry():
    assert parse_toc_entry("FOREWORD…… 4") == ("FOREWORD", "4")


def test_sentence_with_trailing_number_is_none():
    assert parse_toc_entry("một sự kiện trong năm 2023.") is None


def test_no_number_is_none():
    assert parse_toc_entry("MỤC LỤC") is None


def test_empty_is_none():
    assert parse_toc_entry("") is None


def test_is_toc_page_true_when_three_plus():
    texts = ["A....1", "B....2", "C....3", "MỤC LỤC", "footer |"]
    assert is_toc_page(texts) is True


def test_is_toc_page_false_for_normal_body():
    texts = ["Một đoạn văn bình thường.", "Đoạn nữa kết thúc 2023.", "MỤC LỤC"]
    assert is_toc_page(texts) is False
