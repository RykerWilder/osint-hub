"""Scan management: asynchronous execution, live events, persistence."""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .config import Settings
from .errors import ToolError
from .models import TERMINAL_STATUSES, Finding, Job, Scan, new_job_id, new_scan_id, now_iso
from .store import Store
from .tools import REGISTRY

log = logging.getLogger("osint.manager")

MAX_LOG_LINES = 3000
MAX_LINE_LENGTH = 600


class JobContext:
    """What a tool sees while it runs: log, results, temporary folder."""

    def __init__(self, manager: "ScanManager", scan: Scan, job: Job, workdir: Path):
        self._manager = manager
        self._scan = scan
        self.job = job
        self.workdir = workdir
        self.input_path: Path | None = scan.input_path  # uploaded file (only "file" scans)
        self.settings: Settings = manager.settings
        self._seen: set[tuple] = {f.key() for f in job.findings}

    @property
    def findings(self) -> list[Finding]:
        return self.job.findings

    def log(self, line: str) -> None:
        line = str(line)[:MAX_LINE_LENGTH]
        logs = self.job.logs
        logs.append(line)
        if len(logs) > MAX_LOG_LINES + 500:
            del logs[:500]
        self._manager.emit(self._scan, "log", {"job": self.job.id, "line": line})

    def finding(self, label: str, *, value: str | None = None, url: str | None = None, group: str | None = None) -> bool:
        label = str(label).strip()[:300]
        if not label:
            return False
        if url is not None and not str(url).strip().lower().startswith(("http://", "https://")):
            url = None  # web links only: no javascript:, data: and the like
        f = Finding(
            label=label,
            value=(str(value).strip()[:600] or None) if value is not None else None,
            url=(str(url).strip()[:1000] or None) if url is not None else None,
            group=group,
        )
        if f.key() in self._seen:
            return False
        self._seen.add(f.key())
        self.job.findings.append(f)
        self._manager.emit(self._scan, "finding", {"job": self.job.id, "finding": f.to_dict()})
        return True

    def set_summary(self, text: str) -> None:
        self.job.summary = text


class ScanManager:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.scans: dict[str, Scan] = {}
        self._tasks: dict[str, list[asyncio.Task]] = {}
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._sem = asyncio.Semaphore(settings.max_concurrent_jobs)
        self._background: set[asyncio.Task] = set()
        self._closing = False
        settings.tmp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ start / stop
    async def load(self) -> None:
        # Uploaded files do not survive a restart: delete any that are left.
        await asyncio.to_thread(shutil.rmtree, self.settings.upload_dir, True)
        for scan in await asyncio.to_thread(self.store.load_all):
            # Scans left "running" by a previous restart: close them.
            for job in scan.jobs:
                if job.status not in TERMINAL_STATUSES:
                    job.status = "error"
                    job.error = "Interrupted by a service restart."
                    job.finished_at = job.finished_at or now_iso()
            if scan.status == "running":
                scan.status = "done"
                scan.finished_at = scan.finished_at or now_iso()
            self.scans[scan.id] = scan
        log.info("Loaded %d scans from disk", len(self.scans))

    async def shutdown(self) -> None:
        self._closing = True
        tasks = [t for ts in self._tasks.values() for t in ts]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for scan in self.scans.values():
            self._discard_input(scan)

    # ------------------------------------------------------------------ events
    def subscribe(self, scan_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(scan_id, set()).add(q)
        return q

    def unsubscribe(self, scan_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(scan_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subs.pop(scan_id, None)

    def emit(self, scan: Scan, event: str, data: dict[str, Any]) -> None:
        for q in self._subs.get(scan.id, ()):
            q.put_nowait((event, data))

    # ------------------------------------------------------------------ API
    def get(self, scan_id: str) -> Scan | None:
        return self.scans.get(scan_id)

    def list(self) -> list[Scan]:
        return sorted(self.scans.values(), key=lambda s: s.created_at, reverse=True)

    async def create_scan(
        self,
        target: str,
        type_: str,
        tool_ids: list[str],
        options: dict[str, Any],
        *,
        input_path: Path | None = None,
    ) -> Scan:
        """Creates the scan and starts the tools.

        `input_path` is the uploaded file ("file" type): from now on the manager owns it
        and deletes it when the scan ends. If this function raises, the file stays with the caller.
        """
        jobs: list[Job] = []
        for tid in tool_ids:
            tool = REGISTRY[tid]
            opts = tool.clean_options((options or {}).get(tid))  # ValueError -> 422 in the API layer
            jobs.append(Job(id=new_job_id(), tool=tid, tool_name=tool.name, options=opts))
        scan = Scan(id=new_scan_id(), target=target, type=type_, created_at=now_iso(), jobs=jobs, input_path=input_path)
        self.scans[scan.id] = scan
        await self._persist(scan)
        await self._prune()
        tasks = []
        for job in jobs:
            task = asyncio.create_task(self._run_job(scan, job))
            task.add_done_callback(lambda _t, s=scan, j=job: self._job_task_done(s, j))
            tasks.append(task)
        self._tasks[scan.id] = tasks
        return scan

    async def cancel_scan(self, scan: Scan) -> None:
        if scan.status != "running":
            return
        scan.cancel_requested = True
        for task in self._tasks.get(scan.id, []):
            task.cancel()

    async def delete_scan(self, scan: Scan) -> None:
        await self.cancel_scan(scan)
        tasks = self._tasks.get(scan.id, [])
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.scans.pop(scan.id, None)
        self._tasks.pop(scan.id, None)
        self._discard_input(scan)
        self.emit(scan, "end", {})
        await asyncio.to_thread(self.store.delete, scan.id)

    # ------------------------------------------------------------------ internals
    def _discard_input(self, scan: Scan) -> None:
        """Deletes the uploaded file (and its dedicated folder) as soon as it is no longer needed."""
        path, scan.input_path = scan.input_path, None
        if path is not None:
            shutil.rmtree(path.parent, ignore_errors=True)

    async def _persist(self, scan: Scan) -> None:
        try:
            await asyncio.to_thread(self.store.save, scan)
        except Exception:
            log.exception("Saving scan %s failed", scan.id)

    async def _prune(self) -> None:
        excess = len(self.scans) - self.settings.max_scans
        if excess <= 0:
            return
        old = [s for s in sorted(self.scans.values(), key=lambda s: s.created_at) if s.status != "running"][:excess]
        for scan in old:
            self.scans.pop(scan.id, None)
            await asyncio.to_thread(self.store.delete, scan.id)

    def _job_task_done(self, scan: Scan, job: Job) -> None:
        """Safety net: a task cancelled before it even starts does not run its own `except`,
        so the tool would stay "queued" and the scan "running" forever."""
        if job.status in TERMINAL_STATUSES or self._closing:
            return
        job.status = "cancelled"
        job.finished_at = job.finished_at or now_iso()
        job.summary = job.summary or "Stopped"
        self.emit(scan, "job", job.brief())
        follow_up = asyncio.get_running_loop().create_task(self._after_job(scan))
        self._background.add(follow_up)
        follow_up.add_done_callback(self._background.discard)

    def _set_status(self, scan: Scan, job: Job, status: str) -> None:
        job.status = status
        self.emit(scan, "job", job.brief())

    async def _run_job(self, scan: Scan, job: Job) -> None:
        tool = REGISTRY[job.tool]
        workdir: Path | None = None
        ctx: JobContext | None = None
        try:
            async with self._sem:
                job.started_at = now_iso()
                self._set_status(scan, job, "running")
                workdir = Path(tempfile.mkdtemp(prefix=f"{job.id}-", dir=self.settings.tmp_dir))
                ctx = JobContext(self, scan, job, workdir)
                await asyncio.wait_for(tool.run(ctx, scan.target, job.options), timeout=self.settings.tool_timeout)
                job.status = "done"
        except TimeoutError:
            job.status = "timeout"
            job.error = "Time limit exceeded: showing the results collected so far."
            job.summary = job.summary or f"Stopped on timeout, {len(job.findings)} partial results"
            if ctx:
                ctx.log("[!] " + job.error)
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.summary = job.summary or "Stopped"
        except ToolError as exc:
            job.status = "error"
            job.error = str(exc)
            if ctx:
                ctx.log("[!] " + job.error)
        except Exception as exc:  # unexpected tool error
            log.exception("Unexpected error in %s", job.tool)
            job.status = "error"
            job.error = f"Internal error: {exc}"
            if ctx:
                ctx.log("[!] " + job.error)
        finally:
            job.finished_at = now_iso()
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)
            self.emit(scan, "job", job.brief())
        await self._after_job(scan)

    async def _after_job(self, scan: Scan) -> None:
        if self.scans.get(scan.id) is not scan:  # deleted in the meantime
            return
        if scan.status != "running" or any(j.status not in TERMINAL_STATUSES for j in scan.jobs):
            return
        scan.status = "cancelled" if scan.cancel_requested else "done"
        scan.finished_at = now_iso()
        self._discard_input(scan)
        self.emit(scan, "scan", {"status": scan.status, "finished_at": scan.finished_at})
        await self._persist(scan)
        self.emit(scan, "end", {})
        self._tasks.pop(scan.id, None)
