"""Media loading, validation, and content-type resolution.

Handles the three input sources the app supports:

* a direct upload (raw bytes + filename),
* a local file path, and
* a remote URL (downloaded with a streaming, size-capped GET).

It maps each sample to a BytePlus ``ContentTypeV2`` (IMAGE or VIDEO) and enforces
the documented format and size limits before anything is sent to the API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Supported formats and per-type size caps, per the BytePlus deepfake docs.
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
VIDEO_EXTS = {"mp4", "avi"}

IMAGE_MAX_BYTES = 10 * 1024 * 1024   # 10 MB per image
VIDEO_MAX_BYTES = 50 * 1024 * 1024   # 50 MB per video

# Content-type sniffing by leading magic bytes, used when the extension is
# missing or unreliable (e.g. a URL with no file suffix).
_MAGIC = [
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"RIFF", "webp_or_avi"),  # RIFF container -> disambiguated below
]


class MediaError(ValueError):
    """Raised when a sample is an unsupported format or exceeds the size limit."""


@dataclass
class Media:
    """A validated sample ready to submit for detection."""

    data: bytes
    ext: str            # normalized extension without a dot, e.g. "png"
    kind: str           # "image" or "video"
    source: str         # short description of where it came from (for the UI)

    @property
    def size(self) -> int:
        return len(self.data)


def _ext_from_name(name: str) -> str:
    ext = Path(name).suffix.lower().lstrip(".")
    if ext == "jpe":
        ext = "jpeg"
    return ext


def _sniff_ext(data: bytes) -> str:
    for magic, ext in _MAGIC:
        if data.startswith(magic):
            if ext == "webp_or_avi":
                # RIFF....WEBP for images; AVI uses 'AVI ' at offset 8.
                if len(data) >= 12 and data[8:12] == b"WEBP":
                    return "webp"
                if len(data) >= 12 and data[8:11] == b"AVI":
                    return "avi"
                return ""
            return ext
    # ISO base media (mp4): 'ftyp' box at offset 4.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "mp4"
    return ""


def _kind_for_ext(ext: str) -> str:
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    raise MediaError(
        f"Unsupported format {ext or '(unknown)'!r}. "
        f"Supported: images {sorted(IMAGE_EXTS)}, videos {sorted(VIDEO_EXTS)}."
    )


def _validate_size(kind: str, size: int) -> None:
    cap = IMAGE_MAX_BYTES if kind == "image" else VIDEO_MAX_BYTES
    if size > cap:
        raise MediaError(
            f"{kind.capitalize()} is {size / 1024 / 1024:.1f} MB, "
            f"which exceeds the {cap // 1024 // 1024} MB limit."
        )
    if size == 0:
        raise MediaError("Sample is empty (0 bytes).")


def from_bytes(data: bytes, filename: str = "", *, source: str = "upload") -> Media:
    """Build a validated ``Media`` from raw bytes and an optional filename."""
    ext = _ext_from_name(filename) if filename else ""
    if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
        sniffed = _sniff_ext(data)
        if sniffed:
            ext = sniffed
    kind = _kind_for_ext(ext)
    _validate_size(kind, len(data))
    label = source if not filename else f"{source}: {os.path.basename(filename)}"
    return Media(data=data, ext=ext, kind=kind, source=label)


def from_path(path: str | os.PathLike) -> Media:
    """Load and validate a local file."""
    p = Path(path)
    if not p.is_file():
        raise MediaError(f"File not found: {p}")
    data = p.read_bytes()
    return from_bytes(data, p.name, source="file")


def from_url(url: str, *, timeout: float = 30.0, max_bytes: int | None = None) -> Media:
    """Download a remote image/video and validate it.

    The download is streamed and capped so a malicious or mistaken URL cannot
    exhaust memory. ``max_bytes`` defaults to the video limit (the larger cap).
    """
    import requests  # imported lazily so core detection works without it

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise MediaError(f"URL must be http(s), got scheme {parsed.scheme!r}.")

    cap = max_bytes if max_bytes is not None else VIDEO_MAX_BYTES
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        raise MediaError(f"Failed to download {url}: {exc}") from exc

    chunks = bytearray()
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        chunks.extend(chunk)
        if len(chunks) > cap:
            raise MediaError(
                f"Remote file exceeds the {cap // 1024 // 1024} MB limit."
            )
    data = bytes(chunks)

    # Prefer the URL path for the extension; fall back to the Content-Type header.
    filename = os.path.basename(parsed.path)
    if _ext_from_name(filename) not in IMAGE_EXTS | VIDEO_EXTS:
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        ext = {
            "image/jpeg": "jpeg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "video/mp4": "mp4",
            "video/x-msvideo": "avi",
            "video/avi": "avi",
        }.get(ctype, "")
        filename = f"download.{ext}" if ext else filename

    media = from_bytes(data, filename, source="url")
    return media
