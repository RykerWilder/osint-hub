"""Data models: Finding (a single result), Job (one tool), Scan (one search)."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = {"done", "error", "timeout", "cancelled"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_scan_id() -> str:
    return secrets.token_hex(5)  # 10 hex characters


def new_job_id() -> str:
    return secrets.token_hex(4)  # 8 hex characters


@dataclass
class Finding:
    label: str
    value: str | None = None
    url: str | None = None
    group: str | None = None

    def key(self) -> tuple:
        return (self.group, self.label, self.value, self.url)

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "url": self.url, "group": self.group}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        return cls(
            label=str(d.get("label", "")),
            value=d.get("value"),
            url=d.get("url"),
            group=d.get("group"),
        )


@dataclass
class Job:
    id: str
    tool: str
    tool_name: str
    status: str = "queued"  # queued | running | done | error | timeout | cancelled
    options: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
    summary: str | None = None
    error: str | None = None
    findings: list[Finding] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    def brief(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "tool_name": self.tool_name,
            "status": self.status,
            "options": self.options,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "error": self.error,
            "findings_count": len(self.findings),
        }

    def to_dict(self, *, logs: int | None = None) -> dict[str, Any]:
        """logs=None -> all logs; logs=N -> only the last N; logs=0 -> none."""
        d = self.brief()
        d["findings"] = [f.to_dict() for f in self.findings]
        if logs is None:
            d["logs"] = list(self.logs)
        else:
            d["logs"] = self.logs[-logs:] if logs > 0 else []
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Job":
        return cls(
            id=d["id"],
            tool=d["tool"],
            tool_name=d.get("tool_name", d["tool"]),
            status=d.get("status", "error"),
            options=d.get("options") or {},
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            summary=d.get("summary"),
            error=d.get("error"),
            findings=[Finding.from_dict(f) for f in d.get("findings", [])],
            logs=list(d.get("logs", [])),
        )


@dataclass
class Scan:
    id: str
    target: str
    type: str
    created_at: str
    status: str = "running"  # running | done | cancelled
    finished_at: str | None = None
    jobs: list[Job] = field(default_factory=list)
    cancel_requested: bool = False
    # Uploaded file to analyse (only for type == "file"). It is not saved with the scan:
    # the temporary file is deleted as soon as the scan ends.
    input_path: Path | None = None

    @property
    def findings_count(self) -> int:
        return sum(len(j.findings) for j in self.jobs)

    def job(self, job_id: str) -> Job | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "type": self.type,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "findings_count": self.findings_count,
            "jobs": [
                {"tool": j.tool, "tool_name": j.tool_name, "status": j.status, "findings_count": len(j.findings)}
                for j in self.jobs
            ],
        }

    def to_dict(self, *, logs: int | None = None) -> dict[str, Any]:
        d = self.summary()
        d["jobs"] = [j.to_dict(logs=logs) for j in self.jobs]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scan":
        return cls(
            id=d["id"],
            target=d["target"],
            type=d["type"],
            created_at=d["created_at"],
            status=d.get("status", "done"),
            finished_at=d.get("finished_at"),
            jobs=[Job.from_dict(j) for j in d.get("jobs", [])],
        )
