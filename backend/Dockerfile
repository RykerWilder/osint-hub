# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 - install the OSINT tools, each one in its own virtual environment
# (so the dependencies of one tool never conflict with another's)
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl build-essential pkg-config libxml2-dev libxslt1-dev libffi-dev libcairo2-dev \
 && rm -rf /var/lib/apt/lists/* \
 && pip install uv

# Maigret, Holehe and Ignorant: Python 3.12 managed by uv (best compatibility)
RUN uv python install 3.12
RUN uv venv --python 3.12 /opt/venvs/maigret  && uv pip install --python /opt/venvs/maigret/bin/python maigret
RUN uv venv --python 3.12 /opt/venvs/holehe   && uv pip install --python /opt/venvs/holehe/bin/python holehe
RUN uv venv --python 3.12 /opt/venvs/ignorant && uv pip install --python /opt/venvs/ignorant/bin/python ignorant

# Blackbird: installed from source (clone + dependencies in a dedicated environment).
# To pin a version: docker compose build --build-arg BLACKBIRD_REF=<tag>
# If the install fails the build goes on and the tool shows up as "not installed" in the UI.
# Note: the repository does not contain the WhatsMyName site list (data/wmn-data.json); Blackbird
# downloads it on its first run. The wrapper in backend/wrappers/blackbird takes care of that.
ARG BLACKBIRD_REF=""
RUN mkdir -p /opt/blackbird \
 && ( git clone --depth 1 ${BLACKBIRD_REF:+--branch ${BLACKBIRD_REF}} https://github.com/p1ngul1n0/blackbird.git /opt/blackbird \
      && uv venv --python 3.12 /opt/blackbird/.venv \
      && uv pip install --python /opt/blackbird/.venv/bin/python -r /opt/blackbird/requirements.txt \
      && mkdir -p /opt/blackbird/data /opt/blackbird/logs /opt/blackbird/results \
      && rm -rf /opt/blackbird/.git ) \
 || echo ">>> WARNING: Blackbird was not installed (see the error above)."

# PhoneInfoga: official release binary, picked by CPU architecture.
# (The project's install script asks questions on ARM machines such as Apple Silicon, so it cannot be used here.)
# To pin a version: docker compose build --build-arg PHONEINFOGA_VERSION=v2.11.0 backend
ARG PHONEINFOGA_VERSION=""
RUN set -eux; \
    case "$(uname -m)" in \
      x86_64|amd64)  PI_ARCH=x86_64 ;; \
      aarch64|arm64) PI_ARCH=arm64 ;; \
      *) echo "PhoneInfoga: unsupported architecture $(uname -m)"; exit 1 ;; \
    esac; \
    if [ -n "${PHONEINFOGA_VERSION}" ]; then \
      PI_URL="https://github.com/sundowndev/phoneinfoga/releases/download/${PHONEINFOGA_VERSION}/phoneinfoga_Linux_${PI_ARCH}.tar.gz"; \
    else \
      PI_URL="https://github.com/sundowndev/phoneinfoga/releases/latest/download/phoneinfoga_Linux_${PI_ARCH}.tar.gz"; \
    fi; \
    mkdir -p /opt/phoneinfoga; \
    curl -fsSL --retry 3 -o /tmp/phoneinfoga.tar.gz "$PI_URL"; \
    tar -xzf /tmp/phoneinfoga.tar.gz -C /opt/phoneinfoga; \
    rm -f /tmp/phoneinfoga.tar.gz; \
    chmod 755 /opt/phoneinfoga/phoneinfoga; \
    /opt/phoneinfoga/phoneinfoga version

# theHarvester: official source install with uv (needs Python 3.14).
# To pin a version: docker compose build --build-arg THEHARVESTER_REF=<tag>
# If the install fails the build goes on and the tool shows up as "not installed" in the UI.
ARG THEHARVESTER_REF=""
RUN mkdir -p /opt/theharvester \
 && ( git clone --depth 1 ${THEHARVESTER_REF:+--branch ${THEHARVESTER_REF}} https://github.com/laramies/theHarvester.git /opt/theharvester \
      && cd /opt/theharvester \
      && UV_PYTHON_DOWNLOADS=never uv sync --no-dev \
      && rm -rf .git ) \
 || echo ">>> WARNING: theHarvester was not installed (see the error above)."

# Informational check: every tool should at least start
RUN for t in maigret holehe; do \
      /opt/venvs/$t/bin/$t --help >/dev/null 2>&1 && echo "ok: $t" || echo ">>> WARNING: $t does not start"; \
    done; \
    /opt/venvs/ignorant/bin/python -c "import ignorant.modules, httpx, trio, anyio" >/dev/null 2>&1 && echo "ok: ignorant" || echo ">>> WARNING: ignorant does not start"; \
    /opt/blackbird/.venv/bin/python /opt/blackbird/blackbird.py --help >/dev/null 2>&1 && echo "ok: blackbird" || echo ">>> WARNING: blackbird does not start"; \
    /opt/theharvester/.venv/bin/theHarvester -h >/dev/null 2>&1 && echo "ok: theHarvester" || echo ">>> WARNING: theHarvester does not start"

# ---------------------------------------------------------------------------
# Stage 2 - final image
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    HOME=/home/app \
    PATH="/opt/bin:${PATH}"

# libimage-exiftool-perl: ExifTool for the "File" section; libcairo2: required by Maigret for its reports.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libxml2 libxslt1.1 libcairo2 ca-certificates libimage-exiftool-perl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app \
 && mkdir -p /data /opt/bin \
 && chown app:app /data

COPY --from=builder /opt/uv-python /opt/uv-python
COPY --from=builder /opt/venvs /opt/venvs
COPY --from=builder /opt/theharvester /opt/theharvester
COPY --from=builder /opt/phoneinfoga /opt/phoneinfoga
# Blackbird writes its data and results in its own folder: it must belong to the user running the service.
COPY --from=builder --chown=app:app /opt/blackbird /opt/blackbird
COPY wrappers /opt/wrappers
# Execute permission and Unix line endings, even if the project was extracted on Windows.
RUN sed -i 's/\r$//' /opt/wrappers/* && chmod 755 /opt/wrappers/*

# A tool appears in /opt/bin only if it was really installed: the UI then shows "not installed"
# instead of an error halfway through a scan.
RUN ln -s /opt/venvs/maigret/bin/maigret   /opt/bin/maigret \
 && ln -s /opt/venvs/holehe/bin/holehe     /opt/bin/holehe \
 && ln -s /opt/theharvester/.venv/bin/theHarvester /opt/bin/theHarvester \
 && { [ -x /opt/phoneinfoga/phoneinfoga ] && ln -s /opt/phoneinfoga/phoneinfoga /opt/bin/phoneinfoga || echo ">>> PhoneInfoga missing"; } \
 && { [ -f /opt/blackbird/blackbird.py ] && [ -x /opt/blackbird/.venv/bin/python ] && ln -s /opt/wrappers/blackbird /opt/bin/blackbird || echo ">>> Blackbird missing"; } \
 && { [ -x /opt/venvs/ignorant/bin/python ] && ln -s /opt/wrappers/ignorant-check /opt/bin/ignorant-check || echo ">>> Ignorant missing"; }

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=4s --start-period=10s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
