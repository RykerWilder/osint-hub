"""Validation and normalisation of the target.

The target ends up as an argument of external processes: here we reject any value that
could be read as an option (starts with "-") or that contains unexpected characters.
Processes are launched without a shell anyway.
"""
from __future__ import annotations

import ipaddress
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

TYPE_META = [
    {"id": "username", "label": "Username", "placeholder": "e.g. john.doe"},
    {"id": "email", "label": "Email", "placeholder": "name@example.com"},
    {"id": "phone", "label": "Phone", "placeholder": "+1 202 555 0143"},
    {"id": "domain", "label": "Domain", "placeholder": "example.com"},
    {"id": "ip", "label": "IP", "placeholder": "8.8.8.8"},
    {"id": "file", "label": "File", "placeholder": "Drop a file here"},
]
TYPES = tuple(t["id"] for t in TYPE_META)

_USERNAME = re.compile(r"^(?!-)[\w.\-]{1,64}$")
_EMAIL = re.compile(r"^(?!-)[A-Za-z0-9._%+\-]{1,64}@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z][A-Za-z0-9\-]{1,62}$")
_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9\-]{1,62}$")
_PHONE = re.compile(r"^\+?[\d\s().\-]{5,30}$")


def _idna(host: str) -> str:
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Invalid domain.") from exc


def normalize_domain(raw: str) -> str:
    s = raw.strip().lower()
    if "://" in s:
        s = urlsplit(s).hostname or ""
    else:
        s = re.split(r"[/?#]", s, maxsplit=1)[0]
        s = s.split("@")[-1]
        s = s.split(":")[0]
    s = _idna(s.rstrip("."))
    if not _DOMAIN.match(s):
        raise ValueError("Invalid domain. Example: example.com")
    return s


def normalize_phone(raw: str, region: str | None = None) -> str:
    """Returns the number in E.164 format (+12025550143).

    Without an international prefix a `region` (e.g. "US") is needed, resolved with python-phonenumbers.
    """
    if not _PHONE.match(raw):
        raise ValueError("Invalid phone number. Example: +1 202 555 0143")
    digits = re.sub(r"\D", "", raw)
    e164: str | None = None
    if raw.startswith("+"):
        e164 = "+" + digits
    elif digits.startswith("00"):
        e164 = "+" + digits[2:]
    elif region:
        try:
            import phonenumbers

            number = phonenumbers.parse(digits, region)
            e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        except ImportError:  # pragma: no cover - the library is a dependency
            e164 = None
        except phonenumbers.NumberParseException:
            raise ValueError("Invalid phone number for the default country. Add the international prefix (e.g. +1).")
    if e164 is None:
        raise ValueError("Add the international prefix, for example +1 202 555 0143.")
    if not 6 <= len(e164) - 1 <= 15:
        raise ValueError("The number must have between 6 and 15 digits, prefix included.")
    return e164


def normalize_target(type_: str, raw: str, *, region: str | None = None) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Enter a value to search.")
    if len(raw) > 300:
        raise ValueError("Value too long.")

    if type_ == "username":
        s = raw.lstrip("@")
        if not _USERNAME.match(s):
            raise ValueError("Invalid username: use letters, numbers, dots, hyphens or underscores (max 64).")
        return s

    if type_ == "email":
        s = raw.lower().removeprefix("mailto:")
        local, _, domain = s.rpartition("@")
        s = f"{local}@{_idna(domain)}" if local else s
        if not _EMAIL.match(s):
            raise ValueError("Invalid email address.")
        return s

    if type_ == "domain":
        return normalize_domain(raw)

    if type_ == "ip":
        s = raw.strip("[]")
        try:
            ip = ipaddress.ip_address(s)
        except ValueError as exc:
            raise ValueError("Invalid IP address.") from exc
        if not ip.is_global:
            raise ValueError("Private or reserved address: it has no public data to look up.")
        return str(ip)

    if type_ == "phone":
        return normalize_phone(raw, region)

    raise ValueError("Unsupported data type.")


# ---------------------------------------------------------------- uploaded files
def clean_filename(raw: str | None) -> str:
    """Name to show to the user: no path and no control characters."""
    name = PurePosixPath((raw or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    return name.strip(" .")[:120] or "file"


def safe_extension(name: str) -> str:
    """Short ASCII extension (e.g. 'jpg'), used for the temporary file on the server."""
    ext = PurePosixPath(name).suffix.lower().lstrip(".")
    return ext if re.fullmatch(r"[a-z0-9]{1,10}", ext) else ""
