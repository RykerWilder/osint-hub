"""HTTP API (Starlette): tools, scans, live events (SSE) and TXT reports."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from . import report
from .config import load_settings
from .manager import ScanManager
from .models import now_iso
from .store import Store
from .tools import REGISTRY, TOOLS
from .validators import TYPE_META, TYPES, clean_filename, normalize_target, safe_extension

SCAN_ID = re.compile(r"^[a-f0-9]{10}$")
JOB_ID = re.compile(r"^[a-f0-9]{8}$")
SNAPSHOT_LOG_LINES = 500


@asynccontextmanager
async def lifespan(app: Starlette):
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    manager = ScanManager(settings, Store(settings.data_dir))
    await manager.load()
    app.state.settings = settings
    app.state.manager = manager
    yield
    await manager.shutdown()


# ---------------------------------------------------------------- helpers
def _manager(request: Request) -> ScanManager:
    return request.app.state.manager


def _scan_or_404(request: Request, scan_id: str):
    scan = _manager(request).get(scan_id) if SCAN_ID.match(scan_id) else None
    if scan is None:
        raise HTTPException(404, "Scan not found.")
    return scan


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "The request body is not valid JSON.")
    if not isinstance(body, dict):
        raise HTTPException(400, "The request body must be a JSON object.")
    return body


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _select_tools(type_: str, requested: Any) -> list[str]:
    """Tools to run: the requested ones (validated) or all the available ones for the type."""
    candidates = [t for t in TOOLS if type_ in t.accepts]
    if requested is None:
        selected = [t.id for t in candidates if t.available()]
    else:
        if not isinstance(requested, list) or not all(isinstance(x, str) for x in requested):
            raise HTTPException(422, "Invalid tool list.")
        selected = []
        for tid in dict.fromkeys(requested):
            tool = REGISTRY.get(tid)
            if tool is None or type_ not in tool.accepts:
                raise HTTPException(422, f"The tool \"{tid}\" does not handle this data type.")
            if not tool.available():
                raise HTTPException(422, f"{tool.name} is not installed in this environment.")
            selected.append(tid)
    if not selected:
        raise HTTPException(422, "Select at least one tool.")
    return selected


def _txt_response(text: str, name: str) -> Response:
    return PlainTextResponse(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------- endpoints
async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


async def tools_list(request: Request) -> Response:
    return JSONResponse(
        {
            "app": {"name": request.app.state.settings.app_name},
            "limits": {"max_upload_mb": request.app.state.settings.max_upload_mb},
            "types": TYPE_META,
            "tools": [t.public() for t in TOOLS],
        }
    )


async def scans_list(request: Request) -> Response:
    return JSONResponse([s.summary() for s in _manager(request).list()])


async def scans_create(request: Request) -> Response:
    body = await _json_body(request)
    type_ = body.get("type")
    if type_ not in TYPES:
        raise HTTPException(422, "Unsupported data type.")
    if type_ == "file":
        raise HTTPException(422, "To analyse a file use the upload endpoint (POST /api/scans/file).")
    try:
        target = normalize_target(type_, str(body.get("target", "")), region=request.app.state.settings.default_phone_region)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    selected = _select_tools(type_, body.get("tools"))
    options = body.get("options")
    try:
        scan = await _manager(request).create_scan(target, type_, selected, options if isinstance(options, dict) else {})
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return JSONResponse(scan.to_dict(logs=0), status_code=201)


async def scans_upload(request: Request) -> Response:
    """Analyse a file: the request body is the file itself (no multipart).

    Query: filename (original name), modified (original modification time, ms), tools (comma-separated ids).
    """
    settings = request.app.state.settings
    limit = settings.max_upload_mb * 1024 * 1024
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, f"File too large: the limit is {settings.max_upload_mb} MB.")

    name = clean_filename(request.query_params.get("filename"))
    tools_param = request.query_params.get("tools")
    requested = [t for t in tools_param.split(",") if t] if tools_param else None
    selected = _select_tools("file", requested)

    folder = settings.upload_dir / secrets.token_hex(8)
    folder.mkdir(parents=True, exist_ok=True)
    ext = safe_extension(name)
    path = folder / (f"upload.{ext}" if ext else "upload")
    try:
        size = 0
        with open(path, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File too large: the limit is {settings.max_upload_mb} MB.")
                await asyncio.to_thread(fh.write, chunk)
        if size == 0:
            raise HTTPException(422, "The file is empty.")
        modified = request.query_params.get("modified", "")
        if modified.isdigit():  # the original modification time stays visible in the file metadata
            secs = int(modified) / 1000
            if 0 < secs < time.time() + 86400:
                os.utime(path, (secs, secs))
        scan = await _manager(request).create_scan(name, "file", selected, {}, input_path=path)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return JSONResponse(scan.to_dict(logs=0), status_code=201)


async def scan_detail(request: Request) -> Response:
    scan = _scan_or_404(request, request.path_params["scan_id"])
    if request.method == "DELETE":
        await _manager(request).delete_scan(scan)
        return Response(status_code=204)
    return JSONResponse(scan.to_dict(logs=SNAPSHOT_LOG_LINES))


async def scan_cancel(request: Request) -> Response:
    scan = _scan_or_404(request, request.path_params["scan_id"])
    await _manager(request).cancel_scan(scan)
    return JSONResponse({"ok": True})


async def scan_events(request: Request) -> Response:
    scan = _scan_or_404(request, request.path_params["scan_id"])
    manager = _manager(request)
    queue = manager.subscribe(scan.id)  # before the snapshot: no event is lost

    async def stream():
        try:
            snapshot = scan.to_dict(logs=SNAPSHOT_LOG_LINES)
            snapshot["server_time"] = now_iso()  # lets the browser correct the clock offset
            yield "retry: 3000\n\n"
            yield _sse("snapshot", snapshot)
            if scan.status != "running":
                yield _sse("end", {})
                return
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse(event, data)
                if event == "end":
                    return
        finally:
            manager.unsubscribe(scan.id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def scan_report(request: Request) -> Response:
    scan = _scan_or_404(request, request.path_params["scan_id"])
    name = request.app.state.settings.app_name
    logs = request.query_params.get("logs") == "1"
    return _txt_response(report.render_scan(scan, name, include_logs=logs), report.filename(name, scan))


async def job_report(request: Request) -> Response:
    scan = _scan_or_404(request, request.path_params["scan_id"])
    job_id = request.path_params["job_id"]
    job = scan.job(job_id) if JOB_ID.match(job_id) else None
    if job is None:
        raise HTTPException(404, "Tool not found in this scan.")
    name = request.app.state.settings.app_name
    logs = request.query_params.get("logs") == "1"
    return _txt_response(report.render_job(scan, job, name, include_logs=logs), report.filename(name, scan, job))


async def http_error(request: Request, exc: HTTPException) -> Response:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


routes = [
    Route("/api/health", health),
    Route("/api/tools", tools_list),
    Route("/api/scans", scans_list, methods=["GET"]),
    Route("/api/scans", scans_create, methods=["POST"]),
    Route("/api/scans/file", scans_upload, methods=["POST"]),
    Route("/api/scans/{scan_id}", scan_detail, methods=["GET", "DELETE"]),
    Route("/api/scans/{scan_id}/cancel", scan_cancel, methods=["POST"]),
    Route("/api/scans/{scan_id}/events", scan_events),
    Route("/api/scans/{scan_id}/report.txt", scan_report),
    Route("/api/scans/{scan_id}/jobs/{job_id}/report.txt", job_report),
]

app = Starlette(routes=routes, lifespan=lifespan, exception_handlers={HTTPException: http_error})
