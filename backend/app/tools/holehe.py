from __future__ import annotations

import re

from .base import CliTool, Option

# "[+] twitter.com"  (the legend line "[+] Email used, ..." has no domain and is discarded)
_USED = re.compile(r"^\[\+\]\s+(?P<domain>[A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,})\b(?P<rest>.*)$")
_LIMITED = re.compile(r"^\[x\]\s+\S+")
_TOTAL = re.compile(r"(\d+)\s+websites? checked", re.I)


class Holehe(CliTool):
    id = "holehe"
    name = "Holehe"
    binary = "holehe"
    description = "Checks on 100+ sites whether the email is registered."
    accepts = ("email",)
    homepage = "https://github.com/megadose/holehe"
    options = (
        Option(
            "recovery",
            "Password recovery",
            "select",
            "skip",
            (
                ("skip", "Skip (recommended: sends no email to the target)"),
                ("include", "Include (may send reset emails to the target)"),
            ),
        ),
    )

    def command(self, ctx, target, options):
        args = [target, "--only-used", "--no-color", "--no-clear"]
        if options["recovery"] == "skip":
            args.append("-NP")
        return args

    def new_state(self):
        return {"limited": 0, "total": None}

    def parse_line(self, ctx, line, state):
        m = _USED.match(line)
        if m:
            extra = m["rest"].strip(" /-:")
            ctx.finding(
                m["domain"],
                value=extra or None,
                url=f"https://{m['domain']}",
                group="Linked accounts",
            )
            return
        if _LIMITED.match(line):
            state["limited"] += 1
            return
        t = _TOTAL.search(line)
        if t:
            state["total"] = int(t.group(1))

    async def after(self, ctx, code, state, target, options):
        n = len(ctx.findings)
        if code != 0 and n == 0 and state["total"] is None:
            await super().after(ctx, code, state, target, options)
            return
        parts = ["1 service with an account" if n == 1 else f"{n} services with an account"]
        if state["total"]:
            parts.append(f"{state['total']} checked")
        if state["limited"]:
            parts.append(f"{state['limited']} blocked by rate limit")
        ctx.set_summary(", ".join(parts))
