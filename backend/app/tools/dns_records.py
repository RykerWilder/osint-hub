from __future__ import annotations

import asyncio

from ..errors import ToolError
from . import dnsutil
from .base import Tool

RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "SOA", "CAA", "CNAME")


class DnsRecords(Tool):
    id = "dns"
    name = "DNS records"
    description = "Reads A, AAAA, MX, NS, TXT, SOA, CAA records and the SPF and DMARC policies."
    accepts = ("domain",)
    homepage = "https://dnspython.org"

    async def run(self, ctx, target, options):
        resolver = dnsutil.new_resolver()
        names = [(target, rtype) for rtype in RECORD_TYPES] + [(f"_dmarc.{target}", "TXT")]
        ctx.log(f"Querying the DNS of {target} ({len(names)} queries)")
        results = await asyncio.gather(*(dnsutil.query(resolver, n, t) for n, t in names))

        if any(r == dnsutil.NXDOMAIN for r in results[:2]):
            raise ToolError("The domain does not exist (NXDOMAIN).")

        timeouts = 0
        for (name, rtype), records in zip(names, results):
            if records is None:
                timeouts += 1
                ctx.log(f"[!] Timeout on {rtype} {name}")
                continue
            if records == dnsutil.NXDOMAIN:
                continue
            for text in records:
                if name.startswith("_dmarc."):
                    ctx.finding("DMARC", value=dnsutil.clean_txt(text), group="Email policy")
                elif rtype == "MX":
                    host, prio = dnsutil.parse_mx(text)
                    ctx.finding(host, value=prio, group="MX")
                elif rtype == "TXT":
                    value = dnsutil.clean_txt(text)
                    if value.lower().startswith("v=spf1"):
                        ctx.finding("SPF", value=value, group="Email policy")
                    else:
                        ctx.finding("TXT", value=value, group="TXT")
                elif rtype in ("NS", "CNAME"):
                    ctx.finding(text.rstrip("."), group=rtype)
                else:
                    ctx.finding(rtype, value=text.rstrip("."), group=rtype)

        n = len(ctx.findings)
        if n == 0 and timeouts:
            raise ToolError("No answer from the DNS: check the container's network connection.")
        ctx.set_summary(f"{n} records found" if n != 1 else "1 record found")
