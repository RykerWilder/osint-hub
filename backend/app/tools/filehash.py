from __future__ import annotations

import asyncio
import hashlib
import math
from collections import Counter
from pathlib import Path

from ..errors import ToolError
from .base import Tool

CHUNK = 1024 * 1024

# (leading signature, offset, format name, compatible extensions)
_JPEG = {"jpg", "jpeg", "jpe", "jfif"}
_TIFF = {"tif", "tiff", "dng", "nef", "cr2", "arw", "orf", "rw2", "pef", "srw", "raf"}
_ZIP = {"zip", "docx", "xlsx", "pptx", "odt", "ods", "odp", "apk", "jar", "epub", "kmz", "xpi", "aar"}
_OLE = {"doc", "xls", "ppt", "msg", "vsd", "pub"}
_ISO_BMFF = {"mp4", "m4a", "m4v", "mov", "3gp", "3g2", "heic", "heif", "avif", "cr3", "f4v"}
_RIFF = {"webp", "wav", "avi"}
_MKV = {"mkv", "webm", "mka"}
_SIGNATURES: tuple[tuple[bytes, int, str, set[str]], ...] = (
    (b"\xff\xd8\xff", 0, "JPEG", _JPEG),
    (b"\x89PNG\r\n\x1a\n", 0, "PNG", {"png"}),
    (b"GIF87a", 0, "GIF", {"gif"}),
    (b"GIF89a", 0, "GIF", {"gif"}),
    (b"%PDF-", 0, "PDF", {"pdf"}),
    (b"PK\x03\x04", 0, "ZIP / Office Open XML / ODF / APK", _ZIP),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, "OLE2 document (legacy Office)", _OLE),
    (b"\x7fELF", 0, "ELF executable", {"", "elf", "so", "bin", "o"}),
    (b"MZ", 0, "Windows executable (PE)", {"exe", "dll", "sys", "scr", "ocx"}),
    (b"\x1f\x8b", 0, "GZIP", {"gz", "tgz"}),
    (b"Rar!\x1a\x07", 0, "RAR", {"rar"}),
    (b"7z\xbc\xaf\x27\x1c", 0, "7-Zip", {"7z"}),
    (b"ID3", 0, "MP3 (ID3 tag)", {"mp3"}),
    (b"OggS", 0, "Ogg", {"ogg", "oga", "ogv", "opus"}),
    (b"fLaC", 0, "FLAC", {"flac"}),
    (b"BM", 0, "BMP", {"bmp", "dib"}),
    (b"II*\x00", 0, "TIFF", _TIFF),
    (b"MM\x00*", 0, "TIFF", _TIFF),
    (b"SQLite format 3\x00", 0, "SQLite database", {"db", "sqlite", "sqlite3"}),
    (b"\x1a\x45\xdf\xa3", 0, "Matroska / WebM", _MKV),
    (b"RIFF", 0, "RIFF (WebP, WAV or AVI)", _RIFF),
    (b"ftyp", 4, "MP4 / MOV / HEIC container", _ISO_BMFF),
)


def detect_signature(head: bytes) -> tuple[str, set[str]] | None:
    for magic, offset, name, exts in _SIGNATURES:
        if head[offset : offset + len(magic)] == magic:
            return name, exts
    return None


def entropy(data: bytes) -> float:
    """Shannon entropy in bits per byte (0-8)."""
    if not data:
        return 0.0
    total = len(data)
    return -sum(n / total * math.log2(n / total) for n in Counter(data).values())


def png_trailing(path: Path, size: int) -> int:
    """Bytes after the IEND chunk of a PNG (0 if the file ends normally)."""
    with open(path, "rb") as fh:
        fh.seek(8)
        pos = 8
        while pos + 12 <= size:
            header = fh.read(8)
            if len(header) < 8:
                break
            length = int.from_bytes(header[:4], "big")
            pos += 12 + length
            if header[4:8] == b"IEND":
                return max(0, size - pos)
            fh.seek(pos)
    return 0


def jpeg_trailing(path: Path, size: int) -> int:
    """Bytes after the last end-of-image marker (FF D9) of a JPEG."""
    window = min(size, 8 * 1024 * 1024)
    with open(path, "rb") as fh:
        fh.seek(size - window)
        tail = fh.read(window)
    idx = tail.rfind(b"\xff\xd9")
    return 0 if idx < 0 else window - (idx + 2)


def human_size(n: int) -> str:
    value = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} bytes"  # pragma: no cover


def analyze(path: Path, display_name: str) -> list[tuple[str, str, str | None, str]]:
    """Computes everything in a worker thread. Returns [(label, value, url, group)]."""
    size = path.stat().st_size
    md5, sha1, sha256 = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
    head = b""
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            if not head:
                head = chunk
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)

    rows: list[tuple[str, str, str | None, str]] = [
        ("MD5", md5.hexdigest(), None, "Fingerprints"),
        ("SHA-1", sha1.hexdigest(), None, "Fingerprints"),
        ("SHA-256", sha256.hexdigest(), None, "Fingerprints"),
        (
            "Look up on VirusTotal",
            "hash lookup: the file is not uploaded",
            f"https://www.virustotal.com/gui/file/{sha256.hexdigest()}",
            "Fingerprints",
        ),
        ("Dimensione", f"{human_size(size)} ({size:,} bytes)", None, "Structure"),
    ]

    detected = detect_signature(head)
    ext = Path(display_name).suffix.lower().lstrip(".")
    if detected:
        name, allowed = detected
        rows.append(("Format detected from signature", name, None, "Structure"))
        if ext not in allowed:
            rows.append(
                (
                    "Warning: extension mismatch",
                    f"the name ends in \".{ext}\" but the content is {name}" if ext else f"the name has no extension but the content is {name}",
                    None,
                    "Structure",
                )
            )
    else:
        rows.append(("Format detected from signature", "not recognised (text, rare format or raw data)", None, "Structure"))

    if head:
        value = entropy(head)
        hint = " · probably compressed or encrypted" if value >= 7.5 else ""
        rows.append(("Entropy (first MB)", f"{value:.2f} / 8{hint}", None, "Structure"))

    trailing = 0
    if detected and detected[0] == "PNG":
        trailing = png_trailing(path, size)
    elif detected and detected[0] == "JPEG":
        trailing = jpeg_trailing(path, size)
    if trailing > 0:
        rows.append(
            (
                "Data after the end of the image",
                f"{human_size(trailing)} appended at the end: may be an embedded video, a signature or hidden content",
                None,
                "Structure",
            )
        )
    return rows


class FileHash(Tool):
    id = "filehash"
    name = "Hashes & signature"
    description = "Computes MD5, SHA-1 and SHA-256, checks the real format and looks for hidden data appended to the file."
    accepts = ("file",)
    homepage = ""

    async def run(self, ctx, target, options):
        path = ctx.input_path
        if path is None or not path.is_file():
            raise ToolError("The file to analyse was not found.")
        rows = await asyncio.to_thread(analyze, path, target)
        for label, value, url, group in rows:
            ctx.finding(label, value=value, url=url, group=group)
        warnings = sum(1 for label, *_ in rows if label.startswith(("Warning", "Data after")))
        ctx.set_summary("No anomalies" if not warnings else f"{warnings} anomaly to check" if warnings == 1 else f"{warnings} anomalies to check")
