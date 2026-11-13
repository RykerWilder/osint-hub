from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter
from pathlib import Path

from .base import CliTool, Option, ToolError

# Passive sources that need no API key (official theHarvester list).
FAST_SOURCES = (
    "crtsh,hackertarget,rapiddns,otx,urlscan,subdomaincenter,certspotter,"
    "waybackarchive,duckduckgo,brave,yahoo"
)

GROUPS = {
    "emails": "Email",
    "hosts": "Host",
    "subdomains": "Host",
    "ips": "IP addresses",
    "asns": "ASN",
    "interesting_urls": "Interesting URLs",
    "urls": "Interesting URLs",
    "linkedin_people": "People (LinkedIn)",
    "linkedin_links": "LinkedIn links",
    "twitter_people": "People (X)",
    "people": "People",
    "trello_urls": "Trello",
    "shodan": "Shodan",
}
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
_HOST_IP = re.compile(r"^(?P<host>[^:\s]+):(?P<ip>[0-9a-fA-F.:]+)$")
MAX_FINDINGS = 3000


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


class TheHarvester(CliTool):
    id = "theharvester"
    name = "theHarvester"
    binary = "theHarvester"
    description = "Collects emails, subdomains, hosts and IPs of a domain from public sources."
    accepts = ("domain",)
    homepage = "https://github.com/laramies/theHarvester"
    options = (
        Option(
            "sources",
            "Sources",
            "select",
            "fast",
            (
                ("fast", "Quick selection (recommended)"),
                ("all", "All passive sources (slower)"),
            ),
            help="Sources that need API keys are skipped when they are not configured.",
        ),
    )

    def command(self, ctx, target, options):
        sources = FAST_SOURCES if options["sources"] == "fast" else "all"
        return ["-d", target, "-b", sources, "-f", str(ctx.workdir / "harvest")]

    def new_state(self):
        return {"lines": []}

    def parse_line(self, ctx, line, state):
        if len(state["lines"]) < 6000:
            state["lines"].append(line)

    # --- reading the JSON report -----------------------------------------
    def _add(self, ctx, group: str, item) -> None:
        if len(ctx.findings) >= MAX_FINDINGS:
            return
        if isinstance(item, dict):
            main = next(
                (item[k] for k in ("host", "hostname", "name", "email", "url", "value", "ip", "asn") if isinstance(item.get(k), str)),
                None,
            )
            rest = [str(v) for k, v in item.items() if isinstance(v, (str, int, float)) and v != main and k not in ("source", "sources")]
            label = main or json.dumps(item, ensure_ascii=False)[:200]
            value = ", ".join(rest)[:300] or None
        else:
            label, value = str(item).strip(), None
        if not label:
            return
        m = _HOST_IP.match(label)
        if m and _is_ip(m["ip"]):
            label, value = m["host"], m["ip"]
        url = label if label.startswith(("http://", "https://")) else None
        ctx.finding(label, value=value, url=url, group=group)

    def _read_json(self, ctx, path: Path) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            ctx.log(f"[!] JSON report not readable: {exc}")
            return False
        if not isinstance(data, dict):
            return False
        for key, value in data.items():
            if isinstance(value, list):
                for item in value:
                    self._add(ctx, GROUPS.get(key, key.replace("_", " ").capitalize()), item)
        return True

    # --- fallback: extraction from the screen output --------------------------
    def _read_stdout(self, ctx, lines: list[str], domain: str) -> None:
        text = "\n".join(lines)
        for email in sorted(set(_EMAIL.findall(text))):
            if email.lower().endswith("." + domain) or email.lower().endswith("@" + domain):
                ctx.finding(email.lower(), group="Email")
        host_re = re.compile(rf"\b((?:[a-z0-9\-]+\.)+{re.escape(domain)})\b", re.I)
        for host in sorted({h.lower() for h in host_re.findall(text)}):
            ctx.finding(host, group="Host")

    async def after(self, ctx, code, state, target, options):
        report = ctx.workdir / "harvest.json"
        got_report = report.exists() and self._read_json(ctx, report)
        if not got_report:
            ctx.log("[i] JSON report not found: extracting the results from the output.")
            self._read_stdout(ctx, state["lines"], target)
        n = len(ctx.findings)
        if code != 0 and n == 0:
            raise ToolError(f"theHarvester exited with an error (code {code}). Open the log for details.")
        if n == 0:
            ctx.set_summary("No results from the sources queried")
            return
        counts = Counter(f.group for f in ctx.findings)
        ctx.set_summary(f"{n} results: " + ", ".join(f"{g.lower()} {c}" for g, c in counts.most_common(4)))
