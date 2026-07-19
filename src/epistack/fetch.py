"""Source fetching — URL → clean text content.

Handles: blog/article (trafilatura), PDF (pymupdf), YouTube (transcript API),
local files (.txt/.md). Returns text + metadata for the extraction pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class FetchResult:
    text: str
    title: str
    url: str
    source_type: str
    char_count: int
    metadata: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return len(self.text.strip()) < 100


async def fetch_source(
    url: str,
    source_type: str = "auto",
    title: str = "",
    timeout: float = 30.0,
    manual_fallback: str | None = None,
) -> FetchResult:
    """Fetch a source and return clean text.

    Args:
        url: URL or local file path
        source_type: "blog", "pdf", "youtube", "local", or "auto" (detect)
        title: Human-readable title (optional, extracted if possible)
        timeout: HTTP request timeout in seconds
        manual_fallback: Path to manually-downloaded file (checked first)
    """
    # Check manual fallback first (Google Drive PDFs, failed fetches, etc.)
    if manual_fallback and Path(manual_fallback).exists():
        log.info("fetch_manual_fallback", path=manual_fallback)
        return _fetch_local(manual_fallback, title or f"Manual: {Path(manual_fallback).stem}")

    if source_type == "auto":
        source_type = _detect_type(url)

    log.info("fetch_start", url=url[:80], source_type=source_type)

    if source_type == "local":
        result = _fetch_local(url, title)
    elif source_type == "youtube" or source_type == "debate_transcript":
        result = await _fetch_youtube(url, title)
    elif source_type == "pdf":
        result = await _fetch_pdf(url, title, timeout)
    else:
        result = await _fetch_web(url, title, timeout)

    log.info("fetch_complete", url=url[:80], chars=result.char_count,
             source_type=result.source_type)
    return result


def _detect_type(url: str) -> str:
    """Auto-detect source type from URL pattern."""
    url_lower = url.lower()

    if url_lower.startswith(("/", ".")) or Path(url).exists():
        return "local"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if url_lower.endswith(".pdf") or "drive.google.com" in url_lower:
        return "pdf"
    return "blog"


def _fetch_local(path: str, title: str) -> FetchResult:
    """Read a local text/markdown file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Local source not found: {path}")

    text = p.read_text(encoding="utf-8")
    return FetchResult(
        text=text,
        title=title or p.stem,
        url=path,
        source_type="local",
        char_count=len(text),
        metadata={"file_path": str(p.absolute())},
    )


async def _fetch_web(url: str, title: str, timeout: float) -> FetchResult:
    """Fetch a web page and extract clean text using trafilatura."""
    import trafilatura

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        response = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (research bot; epistack-adversarial)"
        })
        response.raise_for_status()
        html = response.text

    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )

    if not extracted:
        extracted = trafilatura.extract(html, favor_recall=True) or ""

    # Try to get title from trafilatura metadata
    if not title:
        metadata = trafilatura.extract_metadata(html)
        if metadata and metadata.title:
            title = metadata.title

    return FetchResult(
        text=extracted,
        title=title or url.split("/")[-1],
        url=url,
        source_type="blog",
        char_count=len(extracted),
        metadata={"html_length": len(html)},
    )


async def _fetch_pdf(url: str, title: str, timeout: float) -> FetchResult:
    """Download and extract text from a PDF."""
    import pymupdf

    # Download PDF
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        pdf_bytes = response.content

    # Extract text
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()

    text = "\n\n".join(pages)

    return FetchResult(
        text=text,
        title=title or f"PDF ({len(pages)} pages)",
        url=url,
        source_type="pdf",
        char_count=len(text),
        metadata={"page_count": len(pages), "pdf_size_bytes": len(pdf_bytes)},
    )


async def _fetch_youtube(url: str, title: str) -> FetchResult:
    """Fetch YouTube video transcript."""
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = _extract_youtube_id(url)
    if not video_id:
        raise ValueError(f"Could not extract YouTube video ID from: {url}")

    ytt = YouTubeTranscriptApi()
    transcript = ytt.fetch(video_id)

    # Combine segments into full text with timestamps
    lines = []
    for snippet in transcript.snippets:
        minutes = int(snippet.start // 60)
        seconds = int(snippet.start % 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {snippet.text}")

    text = "\n".join(lines)

    # Also create a plain version (no timestamps) for extraction
    plain_text = " ".join(snippet.text for snippet in transcript.snippets)

    return FetchResult(
        text=plain_text,
        title=title or f"YouTube: {video_id}",
        url=url,
        source_type="youtube",
        char_count=len(plain_text),
        metadata={
            "video_id": video_id,
            "segment_count": len(transcript.snippets),
            "timestamped_text": text,
            "duration_minutes": round(transcript.snippets[-1].start / 60, 1) if transcript.snippets else 0,
        },
    )


def _extract_youtube_id(url: str) -> str | None:
    """Extract video ID from various YouTube URL formats."""
    import re

    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
