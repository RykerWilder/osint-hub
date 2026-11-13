"""Running command-line tools with streamed output."""
from __future__ import annotations

import asyncio
import codecs
import os
import re
import shlex
import signal
from pathlib import Path
from typing import Callable

from .errors import ToolError

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
_PROGRESS = re.compile(r"\d{1,3}%\||it/s\]|s/it\]|[█▉▊▋▌▍▎▏]")  # progress bars (tqdm and similar)


def clean_line(raw: str) -> str:
    return _ANSI.sub("", raw).strip()


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """Stops the process and all of its children (dedicated process group)."""
    if proc.returncode is not None:
        return
    for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            await asyncio.wait_for(proc.wait(), wait)
            return
        except TimeoutError:
            continue


async def run_cli(
    ctx,
    argv: list[str],
    *,
    cwd: Path,
    on_line: Callable[[str], None],
    env_extra: dict[str, str] | None = None,
) -> int:
    """Runs `argv` (no shell), forwarding every line to ctx.log and on_line.

    Returns the exit code. If the task is cancelled or times out,
    the process (and its children) is terminated.
    """
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
        "TERM": "dumb",
        **(env_extra or {}),
    }
    ctx.log("$ " + " ".join(shlex.quote(a) for a in argv))
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    buf = ""
    last = None

    def emit(raw: str) -> None:
        nonlocal last
        line = clean_line(raw)
        if not line or line == last or _PROGRESS.search(line):
            return
        last = line
        ctx.log(line)
        on_line(line)

    try:
        assert proc.stdout is not None
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            buf += decoder.decode(chunk)
            *parts, buf = re.split(r"[\r\n]+", buf)
            for part in parts:
                emit(part)
        buf += decoder.decode(b"", final=True)
        if buf:
            emit(buf)
        return await proc.wait()
    finally:
        await _terminate(proc)


async def _drain(stream: asyncio.StreamReader, limit: int, *, strict: bool) -> bytes:
    """Reads the whole stream. Beyond `limit` bytes: error (strict) or the rest is discarded."""
    buf = bytearray()
    while chunk := await stream.read(65536):
        if len(buf) + len(chunk) > limit:
            if strict:
                raise ToolError("The tool output is too large to be processed.")
            continue
        buf += chunk
    return bytes(buf)


async def run_capture(
    ctx,
    argv: list[str],
    *,
    cwd: Path,
    env_extra: dict[str, str] | None = None,
    max_bytes: int = 40 * 1024 * 1024,
) -> tuple[int, bytes, str]:
    """Runs `argv` (no shell) and returns (code, stdout, stderr).

    For tools that produce a single document (e.g. JSON) instead of log lines.
    Like run_cli, it terminates the process and its children if the task is cancelled.
    """
    env = {**os.environ, "NO_COLOR": "1", "TERM": "dumb", **(env_extra or {})}
    ctx.log("$ " + " ".join(shlex.quote(a) for a in argv))
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
    )
    try:
        assert proc.stdout is not None and proc.stderr is not None
        out, err = await asyncio.gather(
            _drain(proc.stdout, max_bytes, strict=True),
            _drain(proc.stderr, 1024 * 1024, strict=False),
        )
        code = await proc.wait()
        return code, out, err.decode("utf-8", "replace")
    finally:
        await _terminate(proc)
