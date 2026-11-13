from __future__ import annotations

import re

from .base import CliTool, Option

_FOUND = re.compile(r"^\[\+\]\s+(?P<site>.+?):\s+(?P<url>https?://\S+)")
_META = re.compile(r"^[├└]─\s*(?P<text>.+)$")


class Maigret(CliTool):
    id = "maigret"
    name = "Maigret"
    binary = "maigret"
    description = "Searches the username on thousands of sites and extracts data from the profiles."
    accepts = ("username",)
    homepage = "https://github.com/soxoj/maigret"
    options = (
        Option(
            "sites",
            "Sites to check",
            "select",
            "500",
            (
                ("100", "Top 100 (fast)"),
                ("500", "Top 500"),
                ("all", "All (slow)"),
            ),
        ),
    )

    def command(self, ctx, target, options):
        args = [
            target,
            "--no-color",
            "--no-progressbar",
            "--no-recursion",
            "--timeout",
            "20",
            "--folderoutput",
            str(ctx.workdir),
        ]
        args += ["-a"] if options["sites"] == "all" else ["--top-sites", options["sites"]]
        return args

    def new_state(self):
        return {"pending": None, "meta": []}

    def _flush(self, ctx, state):
        pending = state["pending"]
        if pending:
            meta = "; ".join(state["meta"])[:400] or None
            ctx.finding(pending["site"], value=meta, url=pending["url"], group="Profiles")
        state["pending"] = None
        state["meta"] = []

    def parse_line(self, ctx, line, state):
        m = _FOUND.match(line)
        if m:
            self._flush(ctx, state)
            state["pending"] = {"site": m["site"], "url": m["url"]}
            return
        t = _META.match(line)
        if t and state["pending"]:
            state["meta"].append(t["text"])
            return
        if line.startswith("["):
            self._flush(ctx, state)

    async def after(self, ctx, code, state, target, options):
        self._flush(ctx, state)
        await super().after(ctx, code, state, target, options)
        n = len(ctx.findings)
        ctx.set_summary("1 profile found" if n == 1 else f"{n} profiles found")
