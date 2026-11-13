# osint-hub: OSINT tools in a single interface

A web app that puts multiple OSINT tools in one place.

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

## .txt reports

- **Download report .txt** (sidebar of a search): all tools in one file.
- **Download .txt** at the top of each tool's results: that tool only.
- Through the API, adding `?logs=1` also includes the full log.

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