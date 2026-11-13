from __future__ import annotations

import asyncio
import re
import socket
from typing import Any

from ..errors import ToolError
from ..httpclient import http_get_json
from .base import Tool

_EVENTS = {
    "registration": "Registered",
    "expiration": "Expires",
    "last changed": "Last changed",
    "last update of rdap database": None,  # irrelevant
}
_ROLES = {
    "registrar": "Registrar",
    "registrant": "Registrant",
    "administrative": "Administrative contact",
    "technical": "Technical contact",
    "abuse": "Abuse contact",
}


def _vcard(entity: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for item in entity["vcardArray"][1]:
            name, value = item[0], item[3]
            if isinstance(value, list):
                value = " ".join(str(v) for v in value if v)
            if name in ("fn", "org", "email", "tel") and value and name not in out:
                out[name] = str(value)
    except (KeyError, IndexError, TypeError):
        pass
    return out


def _walk_entities(entities: list[dict[str, Any]] | None):
    for ent in entities or []:
        yield ent
        yield from _walk_entities(ent.get("entities"))


def parse_domain(data: dict[str, Any]) -> list[tuple[str, str | None, str]]:
    """Domain RDAP JSON -> [(label, value, group)]."""
    out: list[tuple[str, str | None, str]] = []
    if data.get("ldhName"):
        out.append(("Domain", str(data["ldhName"]).lower(), "Domain"))
    if data.get("status"):
        out.append(("Status", ", ".join(map(str, data["status"])), "Domain"))
    for ev in data.get("events") or []:
        label = _EVENTS.get(str(ev.get("eventAction", "")).lower())
        if label and ev.get("eventDate"):
            out.append((label, str(ev["eventDate"])[:10], "Dates"))
    for ns in data.get("nameservers") or []:
        if ns.get("ldhName"):
            out.append((str(ns["ldhName"]).lower(), None, "Nameserver"))
    secure = data.get("secureDNS")
    if isinstance(secure, dict) and "delegationSigned" in secure:
        out.append(("DNSSEC", "enabled" if secure["delegationSigned"] else "not enabled", "Domain"))
    for ent in _walk_entities(data.get("entities")):
        roles = [r for r in ent.get("roles", []) if r in _ROLES]
        card = _vcard(ent)
        if not roles or not card:
            continue
        who = card.get("fn") or card.get("org")
        details = ", ".join(v for k, v in card.items() if v != who and k in ("org", "email", "tel"))
        if who:
            out.append((_ROLES[roles[0]], f"{who}" + (f" ({details})" if details else ""), "Contacts"))
    return out


# --- classic WHOIS (port 43), used when the TLD has no RDAP -------------------
def _whois_query(server: str, query: str, timeout: float = 10.0) -> str:
    try:
        with socket.create_connection((server, 43), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(f"{query}\r\n".encode())
            chunks = []
            total = 0
            while total < 200_000:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
    except OSError as exc:
        raise ToolError(f"WHOIS: connection to {server} failed ({exc}).") from exc
    return b"".join(chunks).decode("utf-8", "replace")


def _whois_text(domain: str) -> str:
    tld = domain.rsplit(".", 1)[-1]
    iana = _whois_query("whois.iana.org", tld)
    m = re.search(r"^(?:refer|whois):\s*(\S+)", iana, re.M | re.I)
    if not m:
        raise ToolError("WHOIS: no server found for this domain.")
    server = m.group(1)
    text = _whois_query(server, domain)
    ref = re.search(r"Registrar WHOIS Server:\s*(\S+)", text, re.I)
    if ref and ref.group(1).lower() != server.lower():
        try:
            text = _whois_query(ref.group(1), domain)
        except ToolError:
            pass
    return text


def parse_whois_text(text: str, limit: int = 60) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "%#>" or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not value or len(key) > 40 or key.lower().startswith(("url of the", "terms of use", "for more information")):
            continue
        if (key, value) in seen:
            continue
        seen.add((key, value))
        out.append((key, value[:300]))
        if len(out) >= limit:
            break
    return out


class WhoisRdap(Tool):
    id = "whois"
    name = "WHOIS / RDAP"
    description = "Registrar, registration and expiry dates, nameservers and public contacts."
    accepts = ("domain",)
    homepage = "https://about.rdap.org"

    async def run(self, ctx, target, options):
        ctx.log(f"Querying RDAP for {target}")
        rdap_error: str | None = None
        try:
            status, data = await http_get_json(
                f"https://rdap.org/domain/{target}", timeout=20, headers={"Accept": "application/rdap+json"}
            )
        except ToolError as exc:
            status, data, rdap_error = 0, None, str(exc)

        if status == 200 and isinstance(data, dict):
            for label, value, group in parse_domain(data):
                ctx.finding(label, value=value, group=group)
            n = len(ctx.findings)
            ctx.set_summary(f"{n} items (RDAP)")
            return

        ctx.log(f"[!] RDAP not available ({rdap_error or f'HTTP {status}'}). Trying classic WHOIS.")
        text = await asyncio.to_thread(_whois_text, target)
        pairs = parse_whois_text(text)
        if not pairs:
            raise ToolError("No public WHOIS data for this domain.")
        for key, value in pairs:
            ctx.finding(key, value=value, group="WHOIS")
        ctx.set_summary(f"{len(pairs)} fields (WHOIS)")
