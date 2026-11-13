from __future__ import annotations

import json

from .. import phoneutil
from .base import CliTool


class Ignorant(CliTool):
    """Checks whether a number is registered on Amazon, Instagram, Snapchat and other services.

    It does not run the `ignorant` command but the small `ignorant-check` script, which uses the
    library modules and prints one JSON object per line: the result does not depend on a text format.
    """

    id = "ignorant"
    name = "Ignorant"
    binary = "ignorant-check"
    description = "Checks whether the number is registered on Amazon, Instagram, Snapchat and other services."
    accepts = ("phone",)
    homepage = "https://github.com/megadose/ignorant"

    def command(self, ctx, target, options):
        country, national = phoneutil.split_country(target)
        return [country, national]

    def new_state(self):
        return {"checked": 0, "limited": [], "errors": 0}

    def parse_line(self, ctx, line, state):
        if not line.startswith("{"):
            return
        try:
            row = json.loads(line)
        except ValueError:
            return
        if not isinstance(row, dict):
            return
        if row.get("error"):
            state["errors"] += 1
            return
        if "done" in row:
            return
        state["checked"] += 1
        if row.get("rateLimit") or row.get("rateLitmit"):
            state["limited"].append(str(row.get("name") or row.get("domain") or "?"))
            return
        if row.get("exists"):
            domain = str(row.get("domain") or row.get("name") or "").strip()
            method = str(row.get("method") or "").strip()
            ctx.finding(
                domain or "Service",
                value=f"registration found ({method})" if method else "registration found",
                url=f"https://{domain}" if "." in domain else None,
                group="Linked accounts",
            )

    async def after(self, ctx, code, state, target, options):
        if code != 0 and state["checked"] == 0:
            await super().after(ctx, code, state, target, options)
            return
        n = len(ctx.findings)
        parts = ["1 service with an account" if n == 1 else f"{n} services with an account", f"{state['checked']} checked"]
        if state["limited"]:
            parts.append(f"{len(state['limited'])} blocked by rate limit")
            ctx.log("[i] Some services limited the requests: try again later or from another IP address.")
        if state["errors"]:
            parts.append(f"{state['errors']} with errors")
        ctx.set_summary(", ".join(parts))
