"""Plain-text (.txt) report generation."""
from __future__ import annotations

import re
from datetime import datetime

from .models import Job, Scan
from .validators import TYPE_META

_TYPE_LABEL = {t["id"]: t["label"] for t in TYPE_META}
_STATUS_LABEL = {
    "done": "done",
    "error": "error",
    "timeout": "timed out",
    "cancelled": "cancelled",
    "running": "running",
    "queued": "queued",
}
LINE = "-" * 64
DOUBLE = "=" * 64


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return iso


def _duration(job: Job) -> str:
    if not job.started_at or not job.finished_at:
        return ""
    try:
        secs = (datetime.fromisoformat(job.finished_at) - datetime.fromisoformat(job.started_at)).total_seconds()
    except ValueError:
        return ""
    return f", {int(secs)} s"


def _job_block(job: Job, index: int | None, include_logs: bool) -> list[str]:
    head = f"{job.tool_name} ({_STATUS_LABEL.get(job.status, job.status)}{_duration(job)})"
    lines = [LINE, f"[{index}] {head}" if index else head, LINE]
    if job.summary:
        lines.append(f"Summary: {job.summary}")
    if job.error:
        lines.append(f"Note: {job.error}")
    if job.findings:
        lines.append("")
    group = object()
    for f in job.findings:
        if f.group != group:
            group = f.group
            if group:
                lines.append(f"  [{group}]")
        label = f.label if len(f.label) >= 24 else f.label.ljust(24)
        text = "  ".join(x for x in (f.value, f.url) if x)
        lines.append(f"    {label} {text}".rstrip())
    if not job.findings:
        lines.append("No results.")
    if include_logs and job.logs:
        lines += ["", "Log:"] + [f"  {l}" for l in job.logs]
    lines.append("")
    return lines


def _header(scan: Scan, app_name: str, jobs: list[Job]) -> list[str]:
    total = sum(len(j.findings) for j in jobs)
    return [
        DOUBLE,
        f"{app_name} - OSINT report",
        DOUBLE,
        f"Target    : {scan.target}",
        f"Type      : {_TYPE_LABEL.get(scan.type, scan.type)}",
        f"Scan ID   : {scan.id}",
        f"Started   : {_fmt_date(scan.created_at)}",
        f"Finished  : {_fmt_date(scan.finished_at)}",
        f"Tools     : {', '.join(j.tool_name for j in jobs)}",
        f"Results   : {total}",
        "",
    ]


_FOOTER = [
    DOUBLE,
    "Data collected from public sources. Always verify the information and use it",
    "only for lawful and proportionate purposes, respecting other people's privacy.",
    DOUBLE,
    "",
]


def render_scan(scan: Scan, app_name: str, *, include_logs: bool = False) -> str:
    lines = _header(scan, app_name, scan.jobs)
    for i, job in enumerate(scan.jobs, 1):
        lines += _job_block(job, i, include_logs)
    return "\n".join(lines + _FOOTER)


def render_job(scan: Scan, job: Job, app_name: str, *, include_logs: bool = False) -> str:
    lines = _header(scan, app_name, [job]) + _job_block(job, None, include_logs)
    return "\n".join(lines + _FOOTER)


def filename(app_name: str, scan: Scan, job: Job | None = None) -> str:
    def slug(s: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:40] or "x"

    parts = [slug(app_name).lower(), scan.type, slug(scan.target)]
    if job:
        parts.append(job.tool)
    parts.append(scan.id)
    return "-".join(parts) + ".txt"
