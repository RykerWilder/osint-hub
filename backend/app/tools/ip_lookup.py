from __future__ import annotations

import asyncio
import socket
from typing import Any

from ..errors import ToolError
from ..httpclient import http_get_json
from .base import Tool
from .whois_rdap import _vcard, _walk_entities


def parse_ipwho(data: dict[str, Any]) -> list[tuple[str, str | None, str | None, str]]:
    """ipwho.is JSON -> [(label, value, url, group)]."""
    out: list[tuple[str, str | None, str | None, str]] = []
    place = ", ".join(str(data[k]) for k in ("city", "region", "country") if data.get(k))
    if place:
        out.append(("Approximate location", place, None, "Geolocation"))
    lat, lon = data.get("latitude"), data.get("longitude")
    if lat is not None and lon is not None:
        out.append(
            (
                "Coordinates",
                f"{lat}, {lon}",
                f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=9/{lat}/{lon}",
                "Geolocation",
            )
        )
    if data.get("postal"):
        out.append(("Postal code", str(data["postal"]), None, "Geolocation"))
    tz = data.get("timezone") or {}
    if tz.get("id"):
        out.append(("Time zone", str(tz["id"]), None, "Geolocation"))
    conn = data.get("connection") or {}
    if conn.get("asn"):
        out.append(("ASN", f"AS{conn['asn']}", None, "Network"))
    for key, label in (("org", "Organization"), ("isp", "Provider"), ("domain", "Domain")):
        if conn.get(key):
            out.append((label, str(conn[key]), None, "Network"))
    return out


def parse_rdap_ip(data: dict[str, Any]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    if data.get("name"):
        out.append(("Network name", str(data["name"]), "Allocation"))
    if data.get("startAddress") and data.get("endAddress"):
        out.append(("Range", f"{data['startAddress']} - {data['endAddress']}", "Allocation"))
    cidrs = [f"{c.get('v4prefix') or c.get('v6prefix')}/{c.get('length')}" for c in data.get("cidr0_cidrs") or [] if c.get("length") is not None]
    if cidrs:
        out.append(("CIDR", ", ".join(cidrs), "Allocation"))
    if data.get("country"):
        out.append(("Registration country", str(data["country"]), "Allocation"))
    for ent in _walk_entities(data.get("entities")):
        card = _vcard(ent)
        who = card.get("fn") or card.get("org")
        if who and ent.get("roles"):
            out.append((str(ent["roles"][0]).capitalize(), who, "Contacts"))
    return out


class IpLookup(Tool):
    id = "ip"
    name = "Geolocation & network"
    description = "Approximate location, ASN, provider, reverse DNS and RDAP allocation."
    accepts = ("ip",)
    homepage = "https://ipwho.is"

    async def run(self, ctx, target, options):
        ctx.log(f"Looking up public information about {target}")
        geo_task = http_get_json(f"https://ipwho.is/{target}", timeout=15)
        rdap_task = http_get_json(f"https://rdap.org/ip/{target}", timeout=20, headers={"Accept": "application/rdap+json"})
        rdns_task = asyncio.to_thread(socket.gethostbyaddr, target)
        geo, rdap, rdns = await asyncio.gather(geo_task, rdap_task, rdns_task, return_exceptions=True)

        if isinstance(rdns, tuple):
            ctx.finding("Reverse DNS", value=rdns[0], group="Network")
        else:
            ctx.log("No reverse DNS record.")

        if isinstance(geo, tuple) and geo[0] == 200 and isinstance(geo[1], dict) and geo[1].get("success", True):
            for label, value, url, group in parse_ipwho(geo[1]):
                ctx.finding(label, value=value, url=url, group=group)
        else:
            reason = geo if isinstance(geo, Exception) else "invalid response"
            ctx.log(f"[!] Geolocation not available: {reason}")

        if isinstance(rdap, tuple) and rdap[0] == 200 and isinstance(rdap[1], dict):
            for label, value, group in parse_rdap_ip(rdap[1]):
                ctx.finding(label, value=value, group=group)
        else:
            reason = rdap if isinstance(rdap, Exception) else "invalid response"
            ctx.log(f"[!] RDAP not available: {reason}")

        n = len(ctx.findings)
        if n == 0:
            raise ToolError("No data available: check the container's network connection.")
        ctx.set_summary(f"{n} items found" if n != 1 else "1 item found")
