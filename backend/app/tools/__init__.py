"""Tool registry.

To add a tool: create a class that extends `Tool` (Python code) or
`CliTool` (external program) and add it to TOOLS below.
The order of this list is the one shown in the interface.
"""
from __future__ import annotations

from .base import CliTool, Option, Tool, ToolError
from .blackbird import Blackbird
from .dns_records import DnsRecords
from .email_basic import EmailBasic
from .exiftool import ExifTool
from .filehash import FileHash
from .holehe import Holehe
from .ignorant import Ignorant
from .ip_lookup import IpLookup
from .maigret import Maigret
from .phoneinfoga import PhoneInfoga
from .theharvester import TheHarvester
from .whois_rdap import WhoisRdap

TOOLS: tuple[Tool, ...] = (
    Maigret(),
    Blackbird(),
    Holehe(),
    EmailBasic(),
    Ignorant(),
    PhoneInfoga(),
    TheHarvester(),
    DnsRecords(),
    WhoisRdap(),
    IpLookup(),
    ExifTool(),
    FileHash(),
)
REGISTRY: dict[str, Tool] = {t.id: t for t in TOOLS}

__all__ = ["TOOLS", "REGISTRY", "Tool", "CliTool", "Option", "ToolError"]
