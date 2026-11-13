"""Base classes for the OSINT tools."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from ..errors import ToolError
from ..runner import run_cli

__all__ = ["Tool", "CliTool", "Option", "ToolError"]


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    type: str = "select"  # select | text
    default: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    help: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "choices": [{"value": v, "label": l} for v, l in self.choices],
            "help": self.help,
        }


class Tool:
    id: str = ""
    name: str = ""
    description: str = ""
    accepts: tuple[str, ...] = ()
    homepage: str = ""
    runtime: str = "builtin"  # builtin | cli
    options: tuple[Option, ...] = ()

    def available(self) -> bool:
        return True

    def public(self) -> dict[str, Any]:
        available = self.available()
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "accepts": list(self.accepts),
            "homepage": self.homepage,
            "runtime": self.runtime,
            "available": available,
            "unavailable_reason": None if available else "Not installed in this environment",
            "options": [o.public() for o in self.options],
        }

    def clean_options(self, raw: Any) -> dict[str, str]:
        raw = raw if isinstance(raw, dict) else {}
        out: dict[str, str] = {}
        for opt in self.options:
            val = str(raw.get(opt.key, opt.default))
            if opt.type == "select" and val not in {c[0] for c in opt.choices}:
                raise ValueError(f"Invalid value for \"{opt.label}\" ({self.name}).")
            out[opt.key] = val.strip()[:60]
        return out

    async def run(self, ctx, target: str, options: dict[str, str]) -> None:  # pragma: no cover
        raise NotImplementedError


class CliTool(Tool):
    """A tool that runs an external executable and reads its output line by line."""

    runtime = "cli"
    binary: str = ""

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    # --- to be specialised -------------------------------------------------
    def command(self, ctx, target: str, options: dict[str, str]) -> list[str]:
        raise NotImplementedError

    def env(self, ctx) -> dict[str, str]:
        return {}

    def new_state(self) -> Any:
        return {}

    def parse_line(self, ctx, line: str, state: Any) -> None:
        pass

    async def after(self, ctx, code: int, state: Any, target: str, options: dict[str, str]) -> None:
        n = len(ctx.findings)
        if code != 0 and n == 0:
            raise ToolError(f"{self.name} exited with an error (code {code}). Open the log for details.")
        ctx.set_summary("1 result" if n == 1 else f"{n} results")

    # --- common -----------------------------------------------------------
    async def run(self, ctx, target: str, options: dict[str, str]) -> None:
        binary = shutil.which(self.binary)
        if not binary:
            raise ToolError(f"{self.name} is not installed in this environment.")
        state = self.new_state()
        argv = [binary, *self.command(ctx, target, options)]
        code = await run_cli(
            ctx,
            argv,
            cwd=ctx.workdir,
            env_extra=self.env(ctx),
            on_line=lambda line: self.parse_line(ctx, line, state),
        )
        await self.after(ctx, code, state, target, options)
