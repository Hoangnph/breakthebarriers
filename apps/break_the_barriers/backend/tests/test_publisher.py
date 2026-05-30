import os
import io
import pytest
from backend.app.services.publisher import validate_slug, slug_from_filename


def test_validate_slug_accepts_valid():
    assert validate_slug("clean-code-vi") is True
    assert validate_slug("abc") is True
    assert validate_slug("book123") is True


def test_validate_slug_rejects_invalid():
    assert validate_slug("ab") is False          # too short
    assert validate_slug("UPPER") is False        # uppercase
    assert validate_slug("has space") is False    # space
    assert validate_slug("-leading") is False     # leading dash
    assert validate_slug("trailing-") is False    # trailing dash
    assert validate_slug("under_score") is False  # underscore
    assert validate_slug("a" * 81) is False       # too long


def test_slug_from_filename():
    assert slug_from_filename("Clean Code.pdf") == "clean-code"
    assert slug_from_filename("My_Book_2024.epub") == "my-book-2024"
    assert slug_from_filename("a.pdf") == "a-book"  # too short -> append suffix
