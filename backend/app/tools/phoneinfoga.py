from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlsplit

from .. import phoneutil
from ..errors import ToolError
from .base import CliTool

_SCANNER = re.compile(r"^Results for (\w+)", re.I)
_SECTION = re.compile(r"^([A-Za-z][A-Za-z ]{1,40}):$")
_KEYVAL = re.compile(r"^([A-Za-z][A-Za-z0-9 /_.\-]{0,40}):\s+(\S.*)$")
_URL = re.compile(r"https?://\S+")
_SKIP_PREFIXES = ("running scan", "error", "warning", "scanner", "scan ", "failed", "no result")

SCANNER_LABELS = {
    "local": "Local",
    "numverify": "Numverify",
    "googlesearch": "Google searches",
    "googlecse": "Google CSE",
    "ovh": "OVH",
}
SECTION_LABELS = {
    "social media": "Social networks",
    "disposable providers": "Disposable numbers",
    "reputation": "Reputation and spam",
    "individuals": "People",
    "general": "General search",
}


def _dork(url: str) -> str | None:
    """The Google search text contained in the link (q parameter)."""
    q = parse_qs(urlsplit(url).query).get("q")
    return q[0][:300] if q else None


class PhoneInfoga(CliTool):
    id = "phoneinfoga"
    name = "PhoneInfoga"
    binary = "phoneinfoga"
    description = "Analyses the number (country, formats, carrier) and prepares targeted web searches."
    accepts = ("phone",)
    homepage = "https://github.com/sundowndev/phoneinfoga"

    def command(self, ctx, target, options):
        return ["scan", "-n", target]

    def new_state(self):
        return {"scanner": None, "section": None, "dorks": 0}

    def parse_line(self, ctx, line, state):
        m = _SCANNER.match(line)
        if m:
            state["scanner"] = m.group(1).lower()
            state["section"] = None
            return
        scanner = state["scanner"]
        if not scanner:
            return
        group = SCANNER_LABELS.get(scanner, scanner)

        m = _SECTION.match(line)
        if m:
            state["section"] = m.group(1).strip()
            return

        url = _URL.search(line)
        if url:
            link = url.group(0)
            section = state["section"] or "Link"
            label = SECTION_LABELS.get(section.lower(), section)
            ctx.finding(label, value=_dork(link), url=link, group=group)
            state["dorks"] += 1
            return

        m = _KEYVAL.match(line)
        if m and not line.lower().startswith(_SKIP_PREFIXES):
            ctx.finding(m.group(1).strip(), value=m.group(2).strip(), group=group)

    async def after(self, ctx, code, state, target, options):
        n_cli = len(ctx.findings)
        if code != 0 and n_cli == 0:
            await super().after(ctx, code, state, target, options)
            return
        # PhoneInfoga finds little offline: add line type, area, original carrier and time zone.
        try:
            for group, label, value in phoneutil.offline_details(target):
                ctx.finding(label, value=value, group=group)
        except ToolError as exc:
            ctx.log(f"[!] Offline data not available: {exc}")
        parts = [f"{n_cli} results from PhoneInfoga"]
        if state["dorks"]:
            parts.append(f"{state['dorks']} web searches ready to open")
        ctx.set_summary(", ".join(parts))
        if not os.environ.get("NUMVERIFY_API_KEY"):
            ctx.log("[i] Numverify (carrier and line type) needs a key: set NUMVERIFY_API_KEY in the .env file.")
