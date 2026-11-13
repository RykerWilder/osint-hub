from __future__ import annotations

import asyncio
import hashlib

from ..httpclient import http_get, http_get_json
from . import dnsutil
from .base import Tool


def parse_gravatar_profile(data) -> list[tuple[str, str | None, str | None]]:
    """Extracts (label, value, url) from the Gravatar profile JSON."""
    out: list[tuple[str, str | None, str | None]] = []
    try:
        entry = data["entry"][0]
    except (KeyError, IndexError, TypeError):
        return out
    if entry.get("displayName"):
        out.append(("Display name", entry["displayName"], None))
    if entry.get("preferredUsername"):
        out.append(("Username Gravatar", entry["preferredUsername"], None))
    if entry.get("currentLocation"):
        out.append(("Location", entry["currentLocation"], None))
    if entry.get("aboutMe"):
        out.append(("Bio", str(entry["aboutMe"])[:300], None))
    for acc in entry.get("accounts") or []:
        url = acc.get("url")
        if url:
            out.append((acc.get("name") or acc.get("shortname") or "Linked account", None, url))
    for link in entry.get("urls") or []:
        if link.get("value"):
            out.append((link.get("title") or "Website", None, link["value"]))
    return out


class EmailBasic(Tool):
    id = "email_basic"
    name = "Email: MX & Gravatar"
    description = "Checks the domain's mail servers and looks for a linked Gravatar profile."
    accepts = ("email",)
    homepage = "https://gravatar.com"

    async def run(self, ctx, target, options):
        local, _, domain = target.partition("@")
        digest = hashlib.md5(target.strip().lower().encode()).hexdigest()  # noqa: S324 (required by Gravatar)

        ctx.log(f"Looking up the mail servers of {domain}")
        mx_task = dnsutil.query(dnsutil.new_resolver(), domain, "MX")
        ctx.log("Checking whether a Gravatar profile exists")
        avatar_task = http_get(f"https://www.gravatar.com/avatar/{digest}?d=404&s=1", timeout=10)
        mx, avatar = await asyncio.gather(mx_task, avatar_task, return_exceptions=True)

        if isinstance(mx, Exception):
            ctx.log(f"[!] MX lookup failed: {mx}")
        elif mx == dnsutil.NXDOMAIN:
            ctx.finding("Email domain", value=f"{domain}: does not exist", group="Domain")
        elif isinstance(mx, list):
            ctx.finding("Email domain", value=domain, group="Domain")
            for text in mx:
                host, prio = dnsutil.parse_mx(text)
                ctx.finding(host, value=prio, group="Mail servers (MX)")
            if not mx:
                ctx.log("[!] No MX record: the domain may not receive mail.")
        else:
            ctx.log("[!] MX lookup timed out")

        if isinstance(avatar, Exception):
            ctx.log(f"[!] Gravatar unreachable: {avatar}")
        elif avatar[0] == 200:
            ctx.finding("Gravatar profile", url=f"https://gravatar.com/{digest}", group="Gravatar")
            status, data = await http_get_json(f"https://en.gravatar.com/{digest}.json", timeout=10)
            if status == 200:
                for label, value, url in parse_gravatar_profile(data):
                    ctx.finding(label, value=value, url=url, group="Gravatar")
        else:
            ctx.log("No Gravatar profile for this address.")

        n = len(ctx.findings)
        ctx.set_summary(f"{n} items found" if n != 1 else "1 item found")
