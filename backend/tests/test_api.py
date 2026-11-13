"""Tests of the HTTP API with a real uvicorn server and fake CLI tools."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = _free_port()
    tmp = tmp_path_factory.mktemp("tmp")
    env = {
        **os.environ,
        "DATA_DIR": str(tmp_path_factory.mktemp("data")),
        "TMPDIR": str(tmp),  # the server puts uploaded files and work folders here
        "APP_NAME": "Prova",
        "LOG_LEVEL": "WARNING",
        "MAX_UPLOAD_MB": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("the server does not start")
    yield base, tmp
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def api(server):
    return server[0]


def uploaded_files(server):
    root = server[1] / "osint-jobs" / "uploads"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_tools_and_validation(api):
    server = api
    status, _, body = call(server, "GET", "/api/tools")
    data = json.loads(body)
    assert status == 200 and data["app"]["name"] == "Prova"
    assert [t["id"] for t in data["types"]] == ["username", "email", "phone", "domain", "ip", "file"]
    assert data["limits"] == {"max_upload_mb": 1}
    tools = {t["id"]: t for t in data["tools"]}
    assert tools["blackbird"]["available"] is True  # fake, on the tests' PATH
    assert tools["blackbird"]["options"][0]["choices"][0]["value"] == "exclude"
    assert tools["exiftool"]["accepts"] == ["file"] and tools["ignorant"]["accepts"] == ["phone"]
    assert "sherlock" not in tools

    assert call(server, "POST", "/api/scans", {"type": "nope", "target": "x"})[0] == 422
    assert call(server, "POST", "/api/scans", {"type": "username", "target": "-rf"})[0] == 422
    status, _, body = call(server, "POST", "/api/scans", {"type": "username", "target": "ok", "tools": ["holehe"]})
    assert status == 422 and "does not handle" in json.loads(body)["detail"]
    assert call(server, "POST", "/api/scans", {"type": "username", "target": "ok", "tools": []})[0] == 422
    assert call(server, "POST", "/api/scans", {"type": "file", "target": "x.jpg"})[0] == 422  # i file si caricano
    assert call(server, "POST", "/api/scans", {"type": "phone", "target": "333 123 4567"})[0] == 422
    assert call(server, "GET", "/api/scans/zzzz")[0] == 404
    assert call(server, "GET", "/api/scans/../../etc/passwd")[0] == 404


def read_sse(base, scan_id):
    events = []
    with urllib.request.urlopen(base + f"/api/scans/{scan_id}/events", timeout=30) as r:
        assert r.headers["Content-Type"].startswith("text/event-stream")
        name = None
        for raw in r:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: ") and name:
                events.append((name, json.loads(line[6:])))
                if name == "end":
                    break
    return events


def test_scan_flow_sse_and_reports(api):
    server = api
    status, _, body = call(server, "POST", "/api/scans", {"type": "username", "target": "@mario", "tools": ["maigret", "blackbird"]})
    assert status == 201
    scan = json.loads(body)
    assert scan["target"] == "mario" and scan["status"] == "running"

    events = read_sse(server, scan["id"])
    names = [n for n, _ in events]
    assert names[0] == "snapshot" and names[-1] == "end"
    assert "scan" in names
    snapshot_or_live = [d["finding"]["label"] for n, d in events if n == "finding"]
    final = json.loads(call(server, "GET", f"/api/scans/{scan['id']}")[2])
    assert final["status"] == "done" and final["findings_count"] == 5
    assert len(snapshot_or_live) <= 5

    # a connection to a finished scan receives a full snapshot + end
    again = read_sse(server, scan["id"])
    assert [n for n, _ in again] == ["snapshot", "end"]
    assert again[0][1]["findings_count"] == 5

    status, headers, body = call(server, "GET", f"/api/scans/{scan['id']}/report.txt")
    assert status == 200
    assert headers["Content-Type"].startswith("text/plain")
    assert "attachment" in headers["Content-Disposition"] and ".txt" in headers["Content-Disposition"]
    text = body.decode()
    assert "Prova - OSINT report" in text and "https://github.com/mario" in text

    job_id = final["jobs"][0]["id"]
    status, _, body = call(server, "GET", f"/api/scans/{scan['id']}/jobs/{job_id}/report.txt")
    assert status == 200 and "Maigret" in body.decode() and "Blackbird" not in body.decode()
    assert call(server, "GET", f"/api/scans/{scan['id']}/jobs/deadbeef/report.txt")[0] == 404

    listing = json.loads(call(server, "GET", "/api/scans")[2])
    assert listing[0]["id"] == scan["id"] and "jobs" in listing[0] and "logs" not in listing[0]["jobs"][0]

    assert call(server, "DELETE", f"/api/scans/{scan['id']}")[0] == 204
    assert call(server, "GET", f"/api/scans/{scan['id']}")[0] == 404


def test_cancel_over_http(api):
    server = api
    status, _, body = call(server, "POST", "/api/scans", {"type": "username", "target": "slow", "tools": ["blackbird"]})
    scan = json.loads(body)
    time.sleep(0.6)
    assert call(server, "POST", f"/api/scans/{scan['id']}/cancel")[0] == 200
    events = read_sse(server, scan["id"])
    final = json.loads(call(server, "GET", f"/api/scans/{scan['id']}")[2])
    assert final["status"] == "cancelled" and final["jobs"][0]["status"] == "cancelled"
    assert events[-1][0] == "end"


def upload(base, query, data, content_type="application/octet-stream"):
    req = urllib.request.Request(base + "/api/scans/file" + query, data=data, method="POST", headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def test_file_upload_flow(server):
    base = server[0]
    status, scan = upload(base, "?filename=C%3A%5Cfoto%20di%20prova.jpg&modified=1620000000000", JPEG)
    assert status == 201
    assert scan["type"] == "file" and scan["target"] == "foto di prova.jpg"
    assert [j["tool"] for j in scan["jobs"]] == ["exiftool", "filehash"]

    read_sse(base, scan["id"])
    final = json.loads(call(base, "GET", f"/api/scans/{scan['id']}")[2])
    assert final["status"] == "done", final
    exif = {f["label"]: f for j in final["jobs"] if j["tool"] == "exiftool" for f in j["findings"]}
    assert exif["GPS position"]["url"].startswith("https://www.openstreetmap.org/")
    # the original modification time (sent by the browser) reaches the metadata
    assert exif["FileModifyDate"]["value"].startswith("2021:05:03")
    assert uploaded_files(server) == []  # the file has already been deleted by the server

    status, _, body = call(base, "GET", f"/api/scans/{scan['id']}/report.txt")
    text = body.decode()
    assert status == 200 and "Target    : foto di prova.jpg" in text and "GPS position" in text
    assert call(base, "DELETE", f"/api/scans/{scan['id']}")[0] == 204


def test_file_upload_validation(server):
    base = server[0]
    status, body = upload(base, "?filename=x.jpg", b"")
    assert status == 422 and "empty" in body["detail"]

    status, body = upload(base, "?filename=grande.bin", b"\x00" * (1024 * 1024 + 10))
    assert status == 413 and "1 MB" in body["detail"]

    status, body = upload(base, "?filename=x.jpg&tools=holehe", JPEG)
    assert status == 422 and "does not handle" in body["detail"]

    status, body = upload(base, "?filename=x.jpg&tools=filehash", JPEG)
    assert status == 201 and [j["tool"] for j in body["jobs"]] == ["filehash"]
    read_sse(base, body["id"])

    # no leftover file, neither after errors nor after a finished scan
    assert uploaded_files(server) == []
    # the file name cannot escape from the dedicated folder
    status, body = upload(base, "?filename=..%2F..%2Fpasswd&tools=filehash", JPEG)
    assert status == 201 and body["target"] == "passwd"
    read_sse(base, body["id"])
    assert uploaded_files(server) == []
