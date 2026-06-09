from backend.app.services.toc_parser import parse_toc_entry, is_toc_page, extract_toc_entries, map_entry_to_page


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


def test_extract_accepts_dots_and_spaces_skips_plain_lines():
    entries = extract_toc_entries([
        "Algorithms : The Brains of AI    8",
        "FOREWORD....3",
        "Body text with no trailing number",
        "Sub item ……  7",
    ])
    assert entries == [("Algorithms : The Brains of AI", "8"),
                       ("FOREWORD", "3"), ("Sub item", "7")]


def test_map_matches_heading_case_insensitive():
    assert map_entry_to_page("Algorithms : The Brains of AI",
                             [(8, "ALGORITHMS : THE BRAINS OF AI")]) == 8


def test_map_two_way_prefix():
    assert map_entry_to_page("Generative AI",
                             [(24, "GENERATIVE AI : MAKING THINGS UP")]) == 24


def test_map_falls_back_to_printed_number():
    assert map_entry_to_page("Nope", [(8, "Something else")], printed_num="12") == 12


def test_map_returns_none_when_no_match_no_number():
    assert map_entry_to_page("Nope", [(8, "Something else")]) is None


def test_extract_splits_merged_block_into_multiple_entries():
    # A single block that merged several TOC lines (dotted leaders) → one entry each.
    entries = extract_toc_entries(
        ["QUIZ.................34 ANNEX : AI TERMINOLOGY.........35 ENDNOTES....42"])
    assert entries == [("QUIZ", "34"),
                       ("ANNEX : AI TERMINOLOGY", "35"),
                       ("ENDNOTES", "42")]
