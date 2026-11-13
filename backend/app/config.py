"""Settings read from environment variables (see .env.example)."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        value = max(minimum, int(os.getenv(name, default)))
    except ValueError:
        return default
    return min(value, maximum) if maximum else value


@dataclass(frozen=True)
class Settings:
    app_name: str
    data_dir: Path
    tmp_dir: Path
    max_concurrent_jobs: int
    tool_timeout: int
    max_scans: int
    default_phone_region: str
    log_level: str
    max_upload_mb: int = 100
    upload_dir: Path = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.upload_dir is None:
            object.__setattr__(self, "upload_dir", self.tmp_dir / "uploads")


def load_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    tmp_dir = Path(tempfile.gettempdir()) / "osint-jobs"
    return Settings(
        app_name=(os.getenv("APP_NAME") or "osint-hub").strip()[:40] or "osint-hub",
        data_dir=data_dir,
        tmp_dir=tmp_dir,
        max_concurrent_jobs=_int("MAX_CONCURRENT_JOBS", 4),
        tool_timeout=_int("TOOL_TIMEOUT", 900, minimum=10),
        max_scans=_int("MAX_SCANS", 100, minimum=5),
        default_phone_region=(os.getenv("DEFAULT_PHONE_REGION") or "IT").strip().upper()[:2],
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        # 500 MB is the ceiling: nginx accepts at most 512 MB per request.
        max_upload_mb=_int("MAX_UPLOAD_MB", 100, minimum=1, maximum=500),
    )
