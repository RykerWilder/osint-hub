# osint-hub: OSINT tools in a single interface

A dark, console-style web interface that brings together Maigret, Blackbird, Holehe, Ignorant, PhoneInfoga, theHarvester, ExifTool and other tools for public sources. Type a piece of data (username, email, phone, domain or IP) or drop a file: the right tools start together, results stream in real time and, at the end, you download them as a `.txt` file.

- **Backend**: Python 3.14, Starlette + uvicorn, streamed results (SSE)
- **Frontend**: React 19 + Tailwind CSS 4 (Vite), IBM Plex fonts, minimal animations in plain CSS, respects the system "reduce motion" setting
- **Everything in Docker**: one command starts frontend and backend, nothing to install on your computer

## Quick start

```bash
docker compose up -d --build
```

Then open **http://localhost:8080**. The first build takes a few minutes (it downloads and installs the tools); later builds are almost instant.

To stop everything: `docker compose down` (the history stays in the `osint-data` volume; to delete it too: `docker compose down -v`).

## Included tools

Each tool does something different. Where two tools overlap (Maigret and Blackbird, Holehe and Blackbird) you can switch off the one you do not need.

| Data | Tool | What it does |
|---|---|---|
| Username | **Maigret** | Searches the username on thousands of sites and extracts data from the profiles it finds |
| Username, Email | **Blackbird** | Searches a username or email on 600+ platforms (WhatsMyName list) |
| Email | **Holehe** | Checks on 100+ sites whether the email is registered |
| Email | **Email: MX & Gravatar** | The domain's mail servers and a linked Gravatar profile |
| Phone | **Ignorant** | Checks whether the number is registered on Amazon, Instagram, Snapchat and other services |
| Phone | **PhoneInfoga** | Country, formats, carrier and targeted web searches; includes the offline number analysis |
| Domain | **theHarvester** | Emails, subdomains, hosts and IPs from public sources (including public certificates) |
| Domain | **DNS records** | A, AAAA, MX, NS, TXT, SOA, CAA, SPF, DMARC |
| Domain | **WHOIS / RDAP** | Registrar, dates, nameservers, public contacts |
| IP | **Geolocation & network** | Approximate location, ASN, provider, reverse DNS, RDAP |
| File | **ExifTool** | All metadata: EXIF, GPS, XMP, IPTC, MakerNotes, PDF, Office, audio, video |
| File | **Hashes & signature** | MD5, SHA-1, SHA-256, real format (from the magic bytes) and data hidden at the end of the file |

Tools that are not installed show up as "not installed" and do not block the others.

### Removed on purpose

- **Sherlock**: Maigret searches usernames on more sites and also extracts profile data, so Sherlock was redundant.
- **Subdomains (crt.sh)**: theHarvester already queries public certificates among its sources.
- **Number analysis (offline)**: PhoneInfoga performs the same local analysis; phone numbers now have a single tool.

### The "File" section

Pick **File** in the command bar, then drop a file anywhere on the page (it works from any screen) or click to choose one. The file is sent to the backend, analysed by **ExifTool** and **Hashes & signature**, and **deleted right away**: it is not kept in the history or in the volume. Only the results stay in the history.

The key metadata (GPS position with a map link, device, creation date, software, author...) appears in a "Highlights" block; everything else is grouped by category and can be filtered.

The size limit is `MAX_UPLOAD_MB` (100 MB by default, maximum 500).

### Notes on individual tools

- **Blackbird** is installed from source. It does not ship the WhatsMyName site list: it downloads it on the first search (a few seconds) and reuses it afterwards. The list lives inside the container, so it is downloaded again after a rebuild.
- **PhoneInfoga** works out of the box with its local scanner. For carrier and line type you need a free key from [numverify.com](https://numverify.com): put it in `NUMVERIFY_API_KEY` in the `.env` file. The Docker build downloads the right binary for your CPU (Intel/AMD or ARM, including Apple Silicon).
- **Ignorant** queries the services where the number asks for a registration. If a service limits the requests a warning appears: change network (IP) or try again later.
- **Holehe** has "Password recovery" off by default, so it does not send reset emails to the target.

## Settings (optional)

Copy `.env.example` to `.env` and change the values:

| Variable | Default | Meaning |
|---|---|---|
| `APP_NAME` | `osint-hub` | Name shown in the interface and in reports |
| `WEB_PORT` | `8080` | Interface port |
| `BIND_ADDRESS` | `127.0.0.1` | `127.0.0.1` = this computer only, `0.0.0.0` = local network |
| `MAX_CONCURRENT_JOBS` | `4` | Tools that can run together |
| `TOOL_TIMEOUT` | `900` | Maximum seconds per tool (partial results are kept) |
| `MAX_SCANS` | `100` | Searches kept in the history |
| `DEFAULT_PHONE_REGION` | `IT` | Country used for numbers without an international prefix (e.g. `US`, `GB`) |
| `MAX_UPLOAD_MB` | `100` | Maximum size of an uploaded file (maximum 500) |
| `NUMVERIFY_API_KEY` | empty | Numverify key for PhoneInfoga (carrier and line type) |

After a change: `docker compose up -d --build`.

> **Do not expose the interface to the Internet.** It has no login: by default it only listens on `127.0.0.1`. If you need remote access, put it behind a VPN or a reverse proxy with authentication.

### API keys for theHarvester (optional)

Many theHarvester sources (Shodan, Hunter, SecurityTrails, VirusTotal...) only work with a key. Create an `api-keys.yaml` file (format described in the [theHarvester wiki](https://github.com/laramies/theHarvester/wiki)), then uncomment this line in `docker-compose.yml`:

```yaml
- ./api-keys.yaml:/home/app/.theHarvester/api-keys.yaml:ro
```

### Pinning tool versions

```bash
docker compose build \
  --build-arg THEHARVESTER_REF=<tag-or-branch> \
  --build-arg BLACKBIRD_REF=<tag-or-branch> \
  --build-arg PHONEINFOGA_VERSION=v2.11.0 \
  backend
```

If installing theHarvester or Blackbird fails during the build, the build goes on and the tool shows up as "not installed" in the interface (the error is in the build log). PhoneInfoga is different: a failed download stops the build with a clear error, so it never silently goes missing.

## The interface

- **Start page**: one large prompt. Pick the data type with the chips (or just type: it is detected as you type), choose the tools under it and press Enter or **Run**. The **Options** of the tools open below without moving the prompt. Press `/` anywhere to jump to the prompt. Drop a file anywhere on the page to analyse it.
- **While a search is open** the prompt moves to the top and stays there for the next one; when a search finishes, the input (or the chosen file) is cleared. The type selector is the tag on the left of the prompt.
- **Results**: a sidebar with the state of the search (progress, time, **Stop**, **Download report .txt**) and the list of tools, and next to it the results of the selected tool, with a filter for long lists and the raw log. Arrow keys move between tools.
- **History** (top right) lists every saved search, with delete. **New search** goes back to the start page.

## .txt reports

- **Download report .txt** (sidebar of a search): all tools in one file.
- **Download .txt** at the top of each tool's results: that tool only.
- Through the API, adding `?logs=1` also includes the full log.

## Local development (without Docker)

```bash
# Backend (Python 3.12+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=./data uvicorn app.main:app --reload --port 8000

# Frontend (Node 22+), in another terminal
cd frontend
npm install
npm run dev        # http://localhost:5173, /api calls go to the backend
```

The built-in tools (DNS, WHOIS, IP, email MX/Gravatar, file hashes) work right away. The others need their programs on your `PATH`: for example `pipx install maigret holehe ignorant`, Blackbird and theHarvester from source, the PhoneInfoga binary and ExifTool (`apt install libimage-exiftool-perl`). For Ignorant the backend uses the `backend/wrappers/ignorant-check` script (it needs a Python with `ignorant`, `httpx` and `trio`).

Backend tests (they use fake tools, no network): `cd backend && pip install pytest && pytest`.

## Adding a tool

1. Create `backend/app/tools/my_tool.py` with a class that extends `Tool` (Python code) or `CliTool` (external program: just give the command and how to read its output lines). Tools for files declare `accepts = ("file",)` and get the file path in `ctx.input_path`.
2. Add it to the `TOOLS` list in `backend/app/tools/__init__.py`.
3. If it is an external program, install it in `backend/Dockerfile`.

The interface picks it up on its own: name, description, accepted data types and options are read from the API.

## How it is built

```
docker-compose.yml        starts backend and frontend
backend/
  app/main.py             REST API + live events (SSE) + file upload + report downloads
  app/manager.py          asynchronous tool execution, cancellation, persistence
  app/runner.py           launching external programs (no shell) and reading their output
  app/validators.py       validation of the entered data (phone numbers too, E.164 format)
  app/tools/              one file per tool
  wrappers/               small launcher scripts for Blackbird and Ignorant
  tests/                  tests with fake tools
frontend/
  src/                    React + Tailwind (App, components, event logic)
  nginx.conf              serves the interface and forwards /api to the backend
```

Security notes: the entered data is validated and passed to programs as arguments (never through a shell); uploaded files are read with a size limit, analysed in a temporary folder and deleted when the work is done (even if the search is cancelled or deleted); the backend container runs without privileges.

## Responsible use

These tools query public sources, but collecting and cross-referencing data about a person can break the law (GDPR and local rules) or violate their privacy. Use them only for a lawful and proportionate purpose: checking your own online exposure, authorised security work, journalism, research. File metadata (GPS position, author, device) is personal data too: only analyse files you have the right to examine.
