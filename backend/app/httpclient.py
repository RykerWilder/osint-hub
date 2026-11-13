"""Small HTTP client built on the standard library (no extra dependency)."""
from __future__ import annotations

import asyncio
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import ToolError

USER_AGENT = "Mozilla/5.0 (compatible; osint-hub/1.0)"


def _fetch(url: str, timeout: float, headers: dict[str, str] | None, max_bytes: int) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URLs are built by the code)
            return resp.status, resp.read(max_bytes)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(max_bytes)
        except Exception:
            body = b""
        return exc.code, body
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        host = urllib.parse.urlsplit(url).hostname
        reason = getattr(exc, "reason", exc)
        raise ToolError(f"Connection to {host} failed: {reason}") from exc


async def http_get(
    url: str, *, timeout: float = 15, headers: dict[str, str] | None = None, max_bytes: int = 12_000_000
) -> tuple[int, bytes]:
    return await asyncio.to_thread(_fetch, url, timeout, headers, max_bytes)


async def http_get_json(url: str, **kwargs: Any) -> tuple[int, Any]:
    status, body = await http_get(url, **kwargs)
    if not body:
        return status, None
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None
