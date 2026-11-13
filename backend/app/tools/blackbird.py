from __future__ import annotations

import re
from urllib.parse import urlsplit

from .base import CliTool, Option

_URL = re.compile(r"https?://[^\s\"'<>)\]]+")
_BRACKET = re.compile(r"\[([^\]]{2,60})\]")
# Lines that report a found account: [+], ✔, "found"... Negative lines are discarded.
_POSITIVE = re.compile(r"^\s*(?:\[\+\]|\[✔\]|[✔✓]️?|\+\s)|\bfound\b", re.I)
_NEGATIVE = re.compile(r"^\s*(?:\[-\]|\[x\]|\[!\]|[✘✗❌])|not found|no results|error|timeout|timed out|failed|rate.?limit", re.I)
# Addresses that appear in the program's own messages (banner, updates, ads): they are not results.
_NOISE_HOSTS = ("p1ngul1n0", "blackbird-osint", "sherlockeye", "cutt.ly", "whatsmyname", "gitbook.io", "buymeacoffee")


def parse_found_line(line: str) -> tuple[str, str] | None:
    """Extracts (site, url) from a Blackbird line that reports a found account, otherwise None."""
    if _NEGATIVE.search(line) or not _POSITIVE.search(line):
        return None
    m = _URL.search(line)
    if not m:
        return None
    url = m.group(0).rstrip(".,;")
    host = (urlsplit(url).hostname or "").lower()
    if not host or any(n in url.lower() for n in _NOISE_HOSTS):
        return None
    site = next((b for b in _BRACKET.findall(line) if b.strip() not in {"+", "-", "x", "!", "i", "*", "✔"}), None)
    if not site:
        site = host.removeprefix("www.")
    return site.strip(), url


class Blackbird(CliTool):
    id = "blackbird"
    name = "Blackbird"
    binary = "blackbird"
    description = "Searches a username or email on 600+ platforms (WhatsMyName list)."
    accepts = ("username", "email")
    homepage = "https://github.com/p1ngul1n0/blackbird"
    options = (
        Option(
            "nsfw",
            "Adult sites",
            "select",
            "exclude",
            (("exclude", "Exclude"), ("include", "Include")),
        ),
        Option(
            "update",
            "Site list",
            "select",
            "keep",
            (
                ("keep", "Use the downloaded list (faster)"),
                ("update", "Check for a newer list before searching"),
            ),
        ),
    )

    def command(self, ctx, target, options):
        args = ["--email" if "@" in target else "--username", target, "--timeout", "20"]
        if options["nsfw"] == "exclude":
            args.append("--no-nsfw")
        if options["update"] == "keep":
            args.append("--no-update")
        return args

    def parse_line(self, ctx, line, state):
        found = parse_found_line(line)
        if found:
            site, url = found
            ctx.finding(site, url=url, group="Accounts found")

    async def after(self, ctx, code, state, target, options):
        await super().after(ctx, code, state, target, options)
        n = len(ctx.findings)
        ctx.set_summary("1 account found" if n == 1 else f"{n} accounts found")
