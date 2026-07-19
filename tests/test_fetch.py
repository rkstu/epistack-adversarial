"""Tests for source fetching."""

import tempfile
from pathlib import Path

import pytest

from epistack.fetch import (
    _detect_type,
    _extract_youtube_id,
    _fetch_local,
    FetchResult,
)


def test_detect_type_youtube():
    assert _detect_type("https://www.youtube.com/watch?v=Y1vaooTKHCM") == "youtube"
    assert _detect_type("https://youtu.be/Y1vaooTKHCM") == "youtube"


def test_detect_type_pdf():
    assert _detect_type("https://example.com/paper.pdf") == "pdf"
    assert _detect_type("https://drive.google.com/file/d/1abc/view") == "pdf"


def test_detect_type_blog():
    assert _detect_type("https://www.astralcodexten.com/p/article") == "blog"
    assert _detect_type("https://michaelweissman.substack.com/p/post") == "blog"


def test_detect_type_local():
    # Create a temp file so Path.exists() returns True
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"test content")
        path = f.name
    assert _detect_type(path) == "local"


def test_extract_youtube_id():
    assert _extract_youtube_id("https://www.youtube.com/watch?v=Y1vaooTKHCM") == "Y1vaooTKHCM"
    assert _extract_youtube_id("https://youtu.be/Y1vaooTKHCM") == "Y1vaooTKHCM"
    assert _extract_youtube_id("https://www.youtube.com/embed/Y1vaooTKHCM") == "Y1vaooTKHCM"
    assert _extract_youtube_id("not a youtube url") is None


def test_fetch_local():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("This is a test document about COVID-19 origins. " * 10)
        path = f.name

    result = _fetch_local(path, "Test Document")
    assert result.source_type == "local"
    assert result.char_count > 100
    assert "COVID-19" in result.text
    assert result.title == "Test Document"


def test_fetch_local_missing_file():
    with pytest.raises(FileNotFoundError):
        _fetch_local("/nonexistent/path/file.txt", "Missing")


def test_fetch_result_is_empty():
    empty = FetchResult(text="   ", title="", url="", source_type="", char_count=3, metadata={})
    assert empty.is_empty

    valid = FetchResult(text="x" * 200, title="", url="", source_type="", char_count=200, metadata={})
    assert not valid.is_empty
