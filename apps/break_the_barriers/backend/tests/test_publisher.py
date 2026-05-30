import os
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


import asyncio
from unittest.mock import MagicMock, AsyncMock


def test_save_cover_file_rejects_non_image(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.services.publisher.COVERS_DIR", str(tmp_path))
    file = MagicMock()
    file.content_type = "application/pdf"
    file.filename = "cover.pdf"
    file.read = AsyncMock(return_value=b"fake")
    with pytest.raises(ValueError, match="image"):
        asyncio.run(
            __import__("backend.app.services.publisher", fromlist=["save_cover_file"]).save_cover_file(file, "doc1", "my-slug")
        )


def test_save_cover_file_rejects_oversized(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.services.publisher.COVERS_DIR", str(tmp_path))
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.filename = "cover.jpg"
    file.read = AsyncMock(return_value=b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="5MB"):
        asyncio.run(
            __import__("backend.app.services.publisher", fromlist=["save_cover_file"]).save_cover_file(file, "doc1", "my-slug")
        )


def test_save_cover_file_saves_and_returns_filename(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.services.publisher.COVERS_DIR", str(tmp_path))
    file = MagicMock()
    file.content_type = "image/png"
    file.filename = "photo.png"
    file.read = AsyncMock(return_value=b"\x89PNG\r\n")
    result = asyncio.run(
        __import__("backend.app.services.publisher", fromlist=["save_cover_file"]).save_cover_file(file, "doc1", "my-slug")
    )
    assert result == "doc1_my-slug.png"
    assert (tmp_path / "doc1_my-slug.png").read_bytes() == b"\x89PNG\r\n"
