"""Phone number helpers (python-phonenumbers, all offline)."""
from __future__ import annotations

from .errors import ToolError


def _lib():
    try:
        import phonenumbers
    except ImportError as exc:  # pragma: no cover - the library is a dependency
        raise ToolError("The phonenumbers library is not installed.") from exc
    return phonenumbers


def parse(target: str):
    """The target is already in E.164 format (+12025550143): converts it to a PhoneNumber object."""
    pn = _lib()
    try:
        return pn.parse(target, None)
    except pn.NumberParseException as exc:
        raise ToolError(f"Cannot parse the number: {exc}") from exc


def split_country(target: str) -> tuple[str, str]:
    """('39', '3331234567'): country calling code and national number, as the tools expect."""
    number = parse(target)
    national = str(number.national_number)
    if number.italian_leading_zero:
        national = "0" * (number.number_of_leading_zeros or 1) + national
    return str(number.country_code), national


_KIND_LABELS = (
    ("FIXED_LINE", "Landline"),
    ("MOBILE", "Mobile"),
    ("FIXED_LINE_OR_MOBILE", "Landline or mobile"),
    ("TOLL_FREE", "Toll-free"),
    ("PREMIUM_RATE", "Premium rate"),
    ("SHARED_COST", "Shared cost"),
    ("VOIP", "VoIP"),
    ("PERSONAL_NUMBER", "Personal number"),
    ("PAGER", "Pager"),
    ("UAN", "Universal access number"),
    ("VOICEMAIL", "Voicemail"),
)


def offline_details(target: str) -> list[tuple[str, str, str]]:
    """Data that can be derived without network: [(group, label, value)]."""
    pn = _lib()
    from phonenumbers import PhoneNumberFormat, carrier, geocoder, timezone

    number = parse(target)
    rows: list[tuple[str, str, str]] = []
    rows.append(("Offline data", "Valid", "yes" if pn.is_valid_number(number) else "no"))
    rows.append(("Offline data", "International format", pn.format_number(number, PhoneNumberFormat.INTERNATIONAL)))
    rows.append(("Offline data", "National format", pn.format_number(number, PhoneNumberFormat.NATIONAL)))
    kinds = {getattr(pn.PhoneNumberType, attr): label for attr, label in _KIND_LABELS}
    kind = kinds.get(pn.number_type(number))
    if kind:
        rows.append(("Offline data", "Line type", kind))
    country = pn.region_code_for_number(number)
    if country:
        name = geocoder.country_name_for_number(number, "en") or country
        rows.append(("Offline data", "Country", f"{name} ({country}, +{number.country_code})"))
    area = geocoder.description_for_number(number, "en")
    if area:
        rows.append(("Offline data", "Area", area))
    op = carrier.name_for_number(number, "en")
    if op:
        rows.append(("Offline data", "Original carrier", op))
    zones = [z for z in timezone.time_zones_for_number(number) if z != "Etc/Unknown"]
    if zones:
        rows.append(("Offline data", "Time zone", ", ".join(zones)))
    return rows
