"""Shared DNS queries (dnspython is loaded only when needed)."""
from __future__ import annotations

from ..errors import ToolError

NXDOMAIN = "NXDOMAIN"


def _resolver():
    try:
        import dns.asyncresolver
    except ImportError as exc:  # pragma: no cover
        raise ToolError("The dnspython library is not installed.") from exc
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 6.0
    resolver.timeout = 3.0
    return resolver


async def query(resolver, name: str, rtype: str):
    """Returns a list of records as text, NXDOMAIN, or None on timeout."""
    import dns.exception
    import dns.resolver

    try:
        answer = await resolver.resolve(name, rtype, raise_on_no_answer=True)
    except dns.resolver.NXDOMAIN:
        return NXDOMAIN
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return []
    except dns.exception.Timeout:
        return None
    except dns.exception.DNSException:
        return []
    return [r.to_text() for r in answer]


def new_resolver():
    return _resolver()


def clean_txt(text: str) -> str:
    """'"v=spf1 ..." "more"' -> 'v=spf1 ... more'."""
    return text.replace('" "', "").strip('"')


def parse_mx(text: str) -> tuple[str, str | None]:
    """'10 mail.example.com.' -> ('mail.example.com', 'priority 10')."""
    prio, _, host = text.partition(" ")
    if prio.isdigit() and host:
        return host.rstrip("."), f"priority {prio}"
    return text.rstrip("."), None
