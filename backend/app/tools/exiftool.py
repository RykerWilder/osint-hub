from __future__ import annotations

import json
import re
import shutil

from ..errors import ToolError
from ..runner import run_capture
from .base import Tool

MAX_TAGS = 2500

# Tags that do not describe the file but its trip through the server (temporary path, access dates).
_SKIP = {
    "SourceFile",
    "System:Directory",
    "System:FileName",
    "System:FilePermissions",
    "System:FileAccessDate",
    "System:FileInodeChangeDate",
    "ExifTool:ExifToolVersion",
}

# (label, tags in order of preference). The tag name is compared without the group prefix.
_HIGHLIGHTS = (
    ("Device", None),  # Make + Model, built separately
    ("Lens", ("LensModel", "LensID", "LensInfo", "Lens")),
    ("Serial number", ("SerialNumber", "InternalSerialNumber", "BodySerialNumber", "CameraSerialNumber", "ImageUniqueID")),
    ("Declared owner", ("OwnerName", "CameraOwnerName")),
    ("Created", ("DateTimeOriginal", "CreateDate", "DateCreated", "MediaCreateDate", "CreationDate")),
    ("Last modified", ("ModifyDate", "MetadataDate", "LastModifiedDate")),
    ("Software", ("Software", "CreatorTool", "Producer", "Creator", "Application")),
    ("Author", ("Artist", "Author", "By-line", "XPAuthor", "Creator")),
    ("Last saved by", ("LastModifiedBy", "LastSavedBy")),
    ("Organization", ("Company", "Manager", "Organization")),
    ("Title", ("Title", "ObjectName", "Headline", "XPTitle")),
    ("Copyright", ("Copyright", "Rights")),
    ("Dimensions", ("ImageSize",)),
)
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
_BINARY = re.compile(r"Binary data (\d+) bytes")


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return " ".join(str(value).split())


def _coord(value, negative_letters: str) -> float | None:
    m = _NUMBER.search(str(value))
    if not m:
        return None
    number = float(m.group(0))
    if any(ch in str(value).upper() for ch in negative_letters) and number > 0:
        number = -number
    return number


def extract_gps(tags: dict) -> tuple[float, float] | None:
    """Latitude and longitude in decimal degrees, if present."""
    lat = lon = None
    if "Composite:GPSLatitude" in tags and "Composite:GPSLongitude" in tags:
        lat = _coord(tags["Composite:GPSLatitude"], "S")
        lon = _coord(tags["Composite:GPSLongitude"], "W")
    elif "Composite:GPSPosition" in tags:
        nums = _NUMBER.findall(str(tags["Composite:GPSPosition"]))
        if len(nums) >= 2:
            lat, lon = float(nums[0]), float(nums[1])
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return lat, lon


def build_highlights(tags: dict) -> list[tuple[str, str, str | None]]:
    """[(label, value, url)] with the most useful details for an investigation, in order of importance."""
    by_name: dict[str, str] = {}
    for key, value in tags.items():
        by_name.setdefault(key.split(":", 1)[-1], _fmt(value))
    out: list[tuple[str, str, str | None]] = []

    gps = extract_gps(tags)
    if gps:
        lat, lon = gps
        out.append(
            (
                "GPS position",
                f"{lat:.6f}, {lon:.6f}",
                f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=17/{lat:.6f}/{lon:.6f}",
            )
        )
        alt = by_name.get("GPSAltitude")
        if alt:
            out.append(("GPS altitude", alt, None))

    ftype, mime = by_name.get("FileType"), by_name.get("MIMEType")
    if ftype or mime:
        out.append(("File type", " · ".join(x for x in (ftype, mime) if x), None))

    for label, names in _HIGHLIGHTS:
        if names is None:
            device = " ".join(x for x in (by_name.get("Make"), by_name.get("Model")) if x)
            if device:
                out.append((label, device, None))
            continue
        value = next((by_name[n] for n in names if by_name.get(n)), None)
        if value:
            out.append((label, value, None))

    for label, names in (("Embedded thumbnail", ("ThumbnailImage", "PreviewImage", "ThumbnailTIFF")),):
        for n in names:
            raw = by_name.get(n)
            if raw:
                size = _BINARY.search(raw)
                out.append((label, f"yes ({int(size.group(1)):,} bytes)" if size else "yes", None))
                break
    return out


class ExifTool(Tool):
    id = "exiftool"
    name = "ExifTool"
    runtime = "cli"
    description = "Extracts all metadata: EXIF, GPS, XMP, IPTC, MakerNotes, PDF, Office, audio and video."
    accepts = ("file",)
    homepage = "https://exiftool.org"

    def available(self) -> bool:
        return shutil.which("exiftool") is not None

    async def run(self, ctx, target, options):
        path = ctx.input_path
        if path is None or not path.is_file():
            raise ToolError("The file to analyse was not found.")
        binary = shutil.which("exiftool")
        if not binary:
            raise ToolError("ExifTool is not installed in this environment.")

        argv = [
            binary,
            "-json",
            "-a",  # duplicate tags too
            "-u",  # unknown tags too
            "-G1",  # group name (IFD0, ExifIFD, GPS, XMP-dc, ...)
            "-ee",  # embedded data (video tracks, nested documents)
            "-sep", ", ",
            "-c", "%+.6f",  # GPS coordinates in decimal degrees
            "-api", "RequestAll=2",
            str(path),
        ]
        code, out, err = await run_capture(ctx, argv, cwd=ctx.workdir)
        for line in err.splitlines()[:20]:
            if line.strip():
                ctx.log(line.strip())
        try:
            data = json.loads(out.decode("utf-8", "replace"))
            tags = data[0]
            if not isinstance(tags, dict):
                raise ValueError
        except (ValueError, IndexError, KeyError):
            raise ToolError("ExifTool returned no readable metadata for this file.")

        # On the server the file has a neutral name and its own access dates: drop those tags and show the original name.
        tags = {k: v for k, v in tags.items() if k not in _SKIP}
        ctx.finding("File name", value=target, group="Highlights")
        for label, value, url in build_highlights(tags):
            ctx.finding(label, value=value, url=url, group="Highlights")

        count = 0
        for key, value in tags.items():
            if count >= MAX_TAGS:
                ctx.log(f"[!] Too many tags: showing the first {MAX_TAGS}. The file has more (typical of videos with -ee).")
                break
            group, name = key.split(":", 1) if ":" in key else ("Other", key)
            if ctx.finding(name, value=_fmt(value), group=group):
                count += 1

        gps = "with GPS position" if extract_gps(tags) else "no GPS position"
        warning = tags.get("ExifTool:Error")
        ctx.set_summary(f"{count} tags, {gps}" if not warning else f"Read error: {_fmt(warning)[:120]}")
        if code != 0 and count == 0:
            raise ToolError(f"ExifTool exited with an error (code {code}). Open the log for details.")
