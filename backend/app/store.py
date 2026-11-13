"""Disk persistence: one JSON file per scan."""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from pathlib import Path

from .models import Scan

log = logging.getLogger("osint.store")
_ID = re.compile(r"^[a-f0-9]{10}$")


class Store:
    def __init__(self, data_dir: Path):
        self.dir = data_dir / "scans"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, scan_id: str) -> Path:
        if not _ID.match(scan_id):
            raise ValueError("Invalid scan ID")
        return self.dir / f"{scan_id}.json"

    def save(self, scan: Scan) -> None:
        path = self._path(scan.id)
        tmp = path.with_name(f".{scan.id}.{secrets.token_hex(3)}.tmp")
        tmp.write_text(json.dumps(scan.to_dict(), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def delete(self, scan_id: str) -> None:
        try:
            self._path(scan_id).unlink()
        except FileNotFoundError:
            pass

    def load_all(self) -> list[Scan]:
        scans: list[Scan] = []
        for path in sorted(self.dir.glob("*.json")):
            try:
                scans.append(Scan.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception as exc:  # corrupt file: ignore it without blocking startup
                log.warning("Scan %s is not readable: %s", path.name, exc)
        return scans
