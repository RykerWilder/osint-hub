"""Core tests with fake CLI tools (no network, no external library)."""
import asyncio
from pathlib import Path

import pytest

from app import phoneutil
from app.config import Settings, load_settings
from app.manager import ScanManager
from app.models import Scan
from app.report import filename, render_job, render_scan
from app.store import Store
from app.tools import REGISTRY
from app.tools.blackbird import parse_found_line
from app.tools.email_basic import parse_gravatar_profile
from app.tools.exiftool import build_highlights, extract_gps
from app.tools.filehash import analyze, detect_signature, entropy, png_trailing
from app.tools.ip_lookup import parse_ipwho, parse_rdap_ip
from app.tools.whois_rdap import parse_domain, parse_whois_text
from app.validators import clean_filename, normalize_target, safe_extension


def make_manager(tmp_path: Path, **kw) -> ScanManager:
    settings = Settings(
        app_name="Test",
        data_dir=tmp_path / "data",
        tmp_dir=tmp_path / "tmp",
        max_concurrent_jobs=kw.get("jobs", 4),
        tool_timeout=kw.get("timeout", 30),
        max_scans=kw.get("max_scans", 100),
        default_phone_region="IT",
        log_level="INFO",
    )
    return ScanManager(settings, Store(settings.data_dir))


async def wait_done(scan: Scan, timeout: float = 20):
    async def loop():
        while scan.status == "running":
            await asyncio.sleep(0.05)

    await asyncio.wait_for(loop(), timeout)


def make_upload(tmp_path: Path, name: str, data: bytes) -> Path:
    """Like the API does: a dedicated folder per file, which the manager deletes when the scan ends."""
    folder = tmp_path / "uploads" / name.replace(".", "_")
    folder.mkdir(parents=True)
    path = folder / ("upload." + name.rsplit(".", 1)[-1])
    path.write_bytes(data)
    return path


# ------------------------------------------------------------------ validazione
@pytest.mark.parametrize(
    "type_,raw,expected",
    [
        ("username", "@mario.rossi", "mario.rossi"),
        ("email", " Mario.Rossi@Esempio.IT ", "mario.rossi@esempio.it"),
        ("domain", "https://WWW.Esempio.it/path?q=1", "www.esempio.it"),
        ("domain", "bücher.de", "xn--bcher-kva.de"),
        ("ip", "[2001:4860:4860::8888]", "2001:4860:4860::8888"),
        ("phone", "+39 333 123-4567", "+393331234567"),
        ("phone", "0039 333 1234567", "+393331234567"),
    ],
)
def test_normalize_ok(type_, raw, expected):
    assert normalize_target(type_, raw) == expected


@pytest.mark.parametrize(
    "type_,raw",
    [
        ("username", "-rf"),
        ("username", "a b"),
        ("username", "x;ls"),
        ("email", "no-at-sign"),
        ("email", "-x@evil.com"),
        ("domain", "not a domain"),
        ("domain", "localhost"),
        ("ip", "10.0.0.1"),
        ("ip", "127.0.0.1"),
        ("ip", "999.1.1.1"),
        ("phone", "abc"),
        ("phone", "12"),
        ("phone", "333 123 4567"),  # no prefix and no default country
        ("username", ""),
        ("file", "x"),
    ],
)
def test_normalize_rejects(type_, raw):
    with pytest.raises(ValueError):
        normalize_target(type_, raw)


def test_phone_default_region():
    pytest.importorskip("phonenumbers")
    assert normalize_target("phone", "333 123 4567", region="IT") == "+393331234567"
    assert normalize_target("phone", "+44 20 7946 0018", region="IT") == "+442079460018"
    with pytest.raises(ValueError):
        normalize_target("phone", "1", region="IT")


def test_phoneutil_with_library():
    pytest.importorskip("phonenumbers")
    assert phoneutil.split_country("+393331234567") == ("39", "3331234567")
    assert phoneutil.split_country("+33679368229") == ("33", "679368229")
    rows = {label: value for _, label, value in phoneutil.offline_details("+393331234567")}
    assert rows["International format"] == "+39 333 123 4567"
    assert rows["Line type"] == "Mobile"


def test_filename_helpers():
    assert clean_filename("../../etc/passwd") == "passwd"
    assert clean_filename("C:\\Users\\x\\foto.JPG") == "foto.JPG"
    assert clean_filename("a\nb\x00.txt") == "ab.txt"
    assert clean_filename("") == "file" and clean_filename("...") == "file" and clean_filename(None) == "file"
    assert len(clean_filename("x" * 500)) == 120
    assert safe_extension("foto.JPG") == "jpg"
    assert safe_extension("archivio.tar.gz") == "gz"
    assert safe_extension("senza") == "" and safe_extension("x.e x") == "" and safe_extension("x.èé") == ""


def test_upload_limit_is_capped(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "9999")
    assert load_settings().max_upload_mb == 500
    monkeypatch.setenv("MAX_UPLOAD_MB", "abc")
    assert load_settings().max_upload_mb == 100


# ------------------------------------------------------------------ username / email scans
def test_username_scan_end_to_end(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("mario", "username", ["maigret", "blackbird"], {})
        q_scan = m.subscribe(scan.id)
        await wait_done(scan)
        events = []
        while not q_scan.empty():
            events.append(q_scan.get_nowait())
        return m, scan, events

    m, scan, events = asyncio.run(go())
    assert scan.status == "done"
    maigret, blackbird = scan.jobs
    assert maigret.status == "done"
    assert [f.label for f in maigret.findings] == ["GitHub", "Reddit"]
    assert maigret.findings[0].value == "uid: 31013580; fullname: Mario Rossi; image: https://avatars.example/x.png"
    assert maigret.findings[0].url == "https://github.com/mario"
    assert not any("40%" in l for l in maigret.logs)  # no progress bar in the logs

    assert blackbird.status == "done"
    # banner, negative lines, errors and duplicates do not become results
    assert [f.label for f in blackbird.findings] == ["GitHub", "Reddit", "Keybase"]
    assert blackbird.findings[2].url == "https://keybase.io/mario"
    assert blackbird.summary == "3 accounts found"
    assert "--no-nsfw" in blackbird.logs[0] and "--no-update" in blackbird.logs[0]

    assert {"job", "finding", "log", "scan", "end"} <= {e[0] for e in events}
    # persistence: a new manager reads the scan back
    m2 = make_manager(tmp_path)
    asyncio.run(m2.load())
    again = m2.get(scan.id)
    assert again and again.findings_count == 5 and again.status == "done"


def test_blackbird_email_and_options(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("a@b.it", "email", ["blackbird"], {"blackbird": {"nsfw": "include", "update": "update"}})
        await wait_done(scan)
        return scan

    job = asyncio.run(go()).jobs[0]
    assert job.status == "done"
    assert "--email a@b.it" in job.logs[0]
    assert "--no-nsfw" not in job.logs[0] and "--no-update" not in job.logs[0]
    assert job.findings[0].url == "https://github.com/a@b.it"


@pytest.mark.parametrize(
    "line,expected",
    [
        ("[+] [GitHub] https://github.com/mario", ("GitHub", "https://github.com/mario")),
        ("✔️ [Keybase] https://keybase.io/mario", ("Keybase", "https://keybase.io/mario")),
        ("[+] https://www.example.org/u/mario", ("example.org", "https://www.example.org/u/mario")),
        ("Found: https://mastodon.social/@mario", ("mastodon.social", "https://mastodon.social/@mario")),
        ("[-] [Twitter] https://twitter.com/mario not found", None),
        ("[!] [Facebook] error: timeout https://facebook.com/x", None),
        ("Visit https://github.com/p1ngul1n0/blackbird for updates", None),
        ("[+] found 3 results", None),  # no URL
        ("Searching 600 sites", None),
    ],
)
def test_blackbird_line_parser(line, expected):
    assert parse_found_line(line) == expected


def test_holehe_filters_legend_and_progress(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("a@b.it", "email", ["holehe"], {"holehe": {"recovery": "skip"}})
        await wait_done(scan)
        return scan

    scan = asyncio.run(go())
    job = scan.jobs[0]
    assert [f.label for f in job.findings] == ["twitter.com", "github.com"]
    assert job.summary == "2 services with an account, 120 checked, 1 blocked by rate limit"
    assert any("-NP" in l for l in job.logs[:1])  # default option: no password recovery
    assert not any("%|" in l for l in job.logs)


def test_theharvester_reads_json(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("esempio.it", "domain", ["theharvester"], {})
        await wait_done(scan)
        return scan

    job = asyncio.run(go()).jobs[0]
    assert job.status == "done"
    by_group = {}
    for f in job.findings:
        by_group.setdefault(f.group, []).append(f)
    assert [f.label for f in by_group["Email"]] == ["info@esempio.it", "press@esempio.it"]
    host = next(f for f in by_group["Host"] if f.label == "www.esempio.it")
    assert host.value == "93.184.216.34"
    assert by_group["Interesting URLs"][0].url == "https://esempio.it/admin"
    assert job.summary.startswith("7 results")


# ------------------------------------------------------------------ phone
def test_ignorant_end_to_end(tmp_path, monkeypatch):
    # The prefix comes from python-phonenumbers (not installed in this test environment).
    monkeypatch.setattr(phoneutil, "split_country", lambda target: ("39", target[3:]))

    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("+393331234567", "phone", ["ignorant"], {})
        await wait_done(scan)
        return scan

    job = asyncio.run(go()).jobs[0]
    assert job.status == "done", job.error
    assert [f.label for f in job.findings] == ["amazon.com", "snapchat.com"]
    assert job.findings[0].url == "https://amazon.com"
    assert job.findings[0].value == "registration found (login)"
    assert job.summary == "2 services with an account, 3 checked, 1 blocked by rate limit, 1 with errors"
    assert any("39 3331234567" in l for l in job.logs[:1])


def test_phoneinfoga_parses_scanners(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("+393331234567", "phone", ["phoneinfoga"], {})
        await wait_done(scan)
        return scan

    job = asyncio.run(go()).jobs[0]
    assert job.status == "done", job.error
    local = {f.label: f.value for f in job.findings if f.group == "Local"}
    assert local == {
        "Raw local": "3331234567",
        "Local": "333 123 4567",
        "E164": "+393331234567",
        "International": "393331234567",
        "Country": "IT",
    }
    dorks = [f for f in job.findings if f.group == "Google searches"]
    assert [f.label for f in dorks] == ["Social networks", "Social networks", "Reputation and spam"]
    assert dorks[0].value == 'site:facebook.com intext:"+393331234567"'
    assert dorks[0].url.startswith("https://www.google.com/search?q=")
    assert not any(f.label.lower().startswith(("running", "scanner")) for f in job.findings)
    assert job.summary == "9 results from PhoneInfoga, 3 web searches ready to open"


# ------------------------------------------------------------------ errors, cancellation, timeout
def test_tool_error_and_cancel(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        bad = await m.create_scan("boom", "username", ["blackbird"], {})
        await wait_done(bad)
        slow = await m.create_scan("slow", "username", ["blackbird", "maigret"], {})
        await asyncio.sleep(0.6)
        await m.cancel_scan(slow)
        await wait_done(slow)
        return bad, slow

    bad, slow = asyncio.run(go())
    assert bad.jobs[0].status == "error"
    assert "code 2" in bad.jobs[0].error
    assert slow.status == "cancelled"
    assert {j.status for j in slow.jobs} <= {"cancelled", "done"}
    assert slow.jobs[0].status == "cancelled"


def test_timeout_keeps_partial_results(tmp_path):
    async def go():
        m = make_manager(tmp_path, timeout=2)
        scan = await m.create_scan("slow", "username", ["blackbird"], {})
        await wait_done(scan)
        return scan

    job = asyncio.run(go()).jobs[0]
    assert job.status == "timeout"
    assert [f.label for f in job.findings] == ["GitHub"]
    assert "partial" in job.summary


def test_unknown_option_rejected(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        await m.create_scan("mario", "username", ["blackbird"], {"blackbird": {"nsfw": "1; rm -rf /"}})

    with pytest.raises(ValueError):
        asyncio.run(go())


def test_delete_and_prune(tmp_path):
    async def go():
        m = make_manager(tmp_path, max_scans=5)
        first = await m.create_scan("u0", "username", ["blackbird"], {})
        await wait_done(first)
        for i in range(1, 7):
            s = await m.create_scan(f"u{i}", "username", ["blackbird"], {})
            await wait_done(s)
        await m.delete_scan(s)
        return m, first, s

    m, first, last = asyncio.run(go())
    assert m.get(first.id) is None  # the oldest one was removed by the limit
    assert m.get(last.id) is None
    assert len(m.scans) <= 5
    assert not (tmp_path / "data" / "scans" / f"{last.id}.json").exists()


# ------------------------------------------------------------------ file
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def test_file_scan_extracts_metadata_and_removes_upload(tmp_path):
    path = make_upload(tmp_path, "foto.jpg", JPEG + b"DATI-NASCOSTI")

    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("foto.jpg", "file", ["exiftool", "filehash"], {}, input_path=path)
        await wait_done(scan)
        return scan

    scan = asyncio.run(go())
    exif, fh = scan.jobs
    assert exif.status == "done", exif.error
    top = {f.label: f for f in exif.findings if f.group == "Highlights"}
    assert top["File name"].value == "foto.jpg"
    assert top["Device"].value == "Apple iPhone 13"
    assert top["GPS position"].value == "41.890251, 12.492373"
    assert top["GPS position"].url == "https://www.openstreetmap.org/?mlat=41.890251&mlon=12.492373#map=17/41.890251/12.492373"
    assert top["File type"].value == "JPEG · image/jpeg"
    assert top["Serial number"].value == "F2LXXXX"
    assert top["Embedded thumbnail"].value == "yes (4,381 bytes)"
    labels = {(f.group, f.label) for f in exif.findings}
    assert ("XMP-dc", "Subject") in labels
    assert not any(l in {"SourceFile", "FileName", "Directory", "ExifToolVersion", "FileAccessDate"} for _, l in labels)
    assert next(f for f in exif.findings if f.label == "Subject").value == "roma, viaggio"
    assert exif.summary == "18 tags, with GPS position"
    assert any("fake warning" in l for l in exif.logs)

    assert fh.status == "done"
    rows = {f.label: f.value for f in fh.findings}
    assert len(rows["SHA-256"]) == 64 and len(rows["MD5"]) == 32
    assert rows["Format detected from signature"] == "JPEG"
    assert "13 bytes" in rows["Data after the end of the image"]
    assert fh.summary == "1 anomaly to check"
    # the uploaded file does not stay on disk
    assert not path.exists() and not path.parent.exists()


def test_file_scan_without_upload_and_unreadable(tmp_path):
    path = make_upload(tmp_path, "x.bad", b"\x00\x01\x02")

    async def go():
        m = make_manager(tmp_path)
        missing = await m.create_scan("a.jpg", "file", ["exiftool", "filehash"], {})
        await wait_done(missing)
        bad = await m.create_scan("x.bad", "file", ["exiftool"], {}, input_path=path)
        await wait_done(bad)
        return missing, bad

    missing, bad = asyncio.run(go())
    assert [j.status for j in missing.jobs] == ["error", "error"]
    assert "not found" in missing.jobs[0].error
    assert bad.jobs[0].status == "done"
    assert bad.jobs[0].summary == "Read error: Unknown file type"


def test_file_deleted_when_scan_is_deleted_or_cancelled(tmp_path):
    p1 = make_upload(tmp_path, "uno.jpg", JPEG)
    p2 = make_upload(tmp_path, "due.jpg", JPEG)

    async def go():
        m = make_manager(tmp_path)
        s1 = await m.create_scan("uno.jpg", "file", ["filehash"], {}, input_path=p1)
        await m.delete_scan(s1)
        s2 = await m.create_scan("due.jpg", "file", ["exiftool", "filehash"], {}, input_path=p2)
        await m.cancel_scan(s2)
        await wait_done(s2)
        return s2

    asyncio.run(go())
    assert not p1.parent.exists() and not p2.parent.exists()


def test_startup_clears_stale_uploads(tmp_path):
    stale = tmp_path / "tmp" / "uploads" / "avanzo"
    stale.mkdir(parents=True)
    (stale / "upload.jpg").write_bytes(b"x")
    asyncio.run(make_manager(tmp_path).load())
    assert not stale.exists()


def test_filehash_analysis():
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR" + b"\x00" * 13 + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    assert detect_signature(png)[0] == "PNG"
    assert detect_signature(b"\x00\x00\x00\x18ftypheic")[0].startswith("MP4 / MOV")
    assert detect_signature(b"hello") is None
    assert entropy(b"") == 0 and entropy(b"aaaa") == 0 and abs(entropy(bytes(range(256))) - 8) < 1e-9


def test_filehash_flags_extension_mismatch_and_png_trailer(tmp_path):
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR" + b"\x00" * 13 + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    clean = tmp_path / "a.png"
    clean.write_bytes(png)
    assert png_trailing(clean, clean.stat().st_size) == 0
    labels = [r[0] for r in analyze(clean, "a.png")]
    assert not any(l.startswith(("Warning", "Data after")) for l in labels)

    dirty = tmp_path / "b.bin"
    dirty.write_bytes(png + b"HIDDEN")
    assert png_trailing(dirty, dirty.stat().st_size) == 6
    rows = {r[0]: r[1] for r in analyze(dirty, "foto.jpg")}
    assert ".jpg" in rows["Warning: extension mismatch"] and "PNG" in rows["Warning: extension mismatch"]
    assert "6 bytes" in rows["Data after the end of the image"]
    # an empty or text file raises no errors
    empty = tmp_path / "e.txt"
    empty.write_bytes(b"")
    assert any(r[0] == "SHA-256" for r in analyze(empty, "e.txt"))


def test_exiftool_helpers():
    tags = {"Composite:GPSLatitude": "+41.5", "Composite:GPSLongitude": "-12.25", "IFD0:Make": "Canon"}
    assert extract_gps(tags) == (41.5, -12.25)
    assert extract_gps({"Composite:GPSLatitude": "41.5 S", "Composite:GPSLongitude": "12.2 W"}) == (-41.5, -12.2)
    assert extract_gps({"Composite:GPSPosition": "+10.1, +20.2"}) == (10.1, 20.2)
    assert extract_gps({"Composite:GPSLatitude": "+0", "Composite:GPSLongitude": "+0"}) is None
    assert extract_gps({"Composite:GPSLatitude": "+95", "Composite:GPSLongitude": "+10"}) is None
    assert extract_gps({}) is None
    labels = [h[0] for h in build_highlights(tags)]
    assert labels[0] == "GPS position" and "Device" in labels


# ------------------------------------------------------------------ report
def test_report_text(tmp_path):
    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("mario", "username", ["maigret", "blackbird"], {})
        await wait_done(scan)
        return scan

    scan = asyncio.run(go())
    txt = render_scan(scan, "Test")
    assert "Test - OSINT report" in txt
    assert "Target    : mario" in txt
    assert "https://github.com/mario" in txt
    assert "Results   : 5" in txt
    one = render_job(scan, scan.jobs[1], "Test", include_logs=True)
    assert "Blackbird" in one and "Maigret" not in one and "Log:" in one
    assert filename("Test", scan, scan.jobs[0]).startswith("test-username-mario-maigret-")


def test_file_report_uses_original_name(tmp_path):
    path = make_upload(tmp_path, "relazione finale.pdf", b"%PDF-1.4\n")

    async def go():
        m = make_manager(tmp_path)
        scan = await m.create_scan("relazione finale.pdf", "file", ["filehash"], {}, input_path=path)
        await wait_done(scan)
        return scan

    scan = asyncio.run(go())
    txt = render_scan(scan, "Test")
    assert "Type      : File" in txt and "Target    : relazione finale.pdf" in txt and "SHA-256" in txt
    assert filename("Test", scan).startswith("test-file-relazione-finale.pdf-")


def test_registry_shape():
    ids = list(REGISTRY)
    assert ids[:6] == ["maigret", "blackbird", "holehe", "email_basic", "ignorant", "phoneinfoga"]
    assert "sherlock" not in REGISTRY and "subdomains" not in REGISTRY and "phone" not in REGISTRY
    for tool in REGISTRY.values():
        pub = tool.public()
        assert pub["accepts"] and pub["description"]
    for t in ("username", "email", "domain", "ip", "phone", "file"):
        assert any(t in tool.accepts for tool in REGISTRY.values())
    # no obvious duplicate: a single tool for every "username only" purpose
    assert [t.id for t in REGISTRY.values() if t.accepts == ("username",)] == ["maigret"]


# ------------------------------------------------------------------ built-in tool parsers
def test_parse_rdap_domain():
    data = {
        "ldhName": "ESEMPIO.IT",
        "status": ["client transfer prohibited"],
        "events": [
            {"eventAction": "registration", "eventDate": "2001-05-04T10:00:00Z"},
            {"eventAction": "expiration", "eventDate": "2027-05-04T10:00:00Z"},
            {"eventAction": "last update of RDAP database", "eventDate": "2026-11-12T00:00:00Z"},
        ],
        "nameservers": [{"ldhName": "NS1.EXAMPLE.NET"}],
        "secureDNS": {"delegationSigned": True},
        "entities": [
            {
                "roles": ["registrar"],
                "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "Registrar Srl"], ["email", {}, "text", "abuse@reg.it"]]],
                "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["fn", {}, "text", "Abuse Team"]]]}],
            }
        ],
    }
    rows = {(label, group): value for label, value, group in parse_domain(data)}
    assert rows[("Domain", "Domain")] == "esempio.it"
    assert rows[("Registered", "Dates")] == "2001-05-04"
    assert ("Last changed", "Dates") not in rows
    assert ("ns1.example.net", "Nameserver") in rows
    assert rows[("DNSSEC", "Domain")] == "enabled"
    assert rows[("Registrar", "Contacts")] == "Registrar Srl (abuse@reg.it)"
    assert rows[("Abuse contact", "Contacts")] == "Abuse Team"


def test_parse_whois_text():
    text = "% comment\nDomain: esempio.it\nStatus: ok\nStatus: ok\n\nCreated: 2001-01-01\n>>> end\n"
    assert parse_whois_text(text) == [("Domain", "esempio.it"), ("Status", "ok"), ("Created", "2001-01-01")]


def test_parse_ip_data():
    geo = {
        "city": "Milano", "region": "Lombardia", "country": "Italia",
        "latitude": 45.46, "longitude": 9.19,
        "connection": {"asn": 3269, "org": "Telecom Italia", "isp": "TIM", "domain": "tim.it"},
        "timezone": {"id": "Europe/Rome"},
    }
    rows = {label: (value, url) for label, value, url, _ in parse_ipwho(geo)}
    assert rows["Approximate location"][0] == "Milano, Lombardia, Italia"
    assert rows["ASN"][0] == "AS3269"
    assert "openstreetmap.org" in rows["Coordinates"][1]
    rdap = {"name": "TIM-NET", "startAddress": "1.0.0.0", "endAddress": "1.0.0.255", "cidr0_cidrs": [{"v4prefix": "1.0.0.0", "length": 24}], "country": "IT"}
    got = {l: v for l, v, _ in parse_rdap_ip(rdap)}
    assert got["CIDR"] == "1.0.0.0/24" and got["Range"] == "1.0.0.0 - 1.0.0.255"


def test_parse_gravatar():
    data = {"entry": [{"displayName": "Mario", "accounts": [{"name": "GitHub", "url": "https://github.com/mario"}], "urls": [{"title": "Blog", "value": "https://m.it"}]}]}
    got = parse_gravatar_profile(data)
    assert ("Display name", "Mario", None) in got
    assert ("GitHub", None, "https://github.com/mario") in got
    assert parse_gravatar_profile({}) == []
