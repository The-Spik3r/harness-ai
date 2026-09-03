# ---- builder: compiles the static frontend only; this stage is discarded below ----
FROM python:3.11 AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build-time-only placeholders so importing chat_ui.chat_ui (which imports
# app.main, which imports app.config.settings) doesn't fail Pydantic's
# required-field validation. Real secrets come from docker-compose's env_file
# at runtime; none of these ENV values are present in the final stage below.
#
# DATABASE_URL is the local-dev-server scheme rather than a libsql:// URL on
# purpose: app/config.py's _require_token_for_remote_endpoint would demand a
# TURSO_AUTH_TOKEN beside a remote endpoint, and a fake credential baked into an
# image layer is worse than a placeholder host. Nothing ever dials it.
#
# DB_BOOTSTRAP_ENABLED=false is what makes that true, and it is the only
# sanctioned use of the flag (app/config.py:45-58, STORY-008). `reflex export`
# below imports chat_ui.chat_ui, which calls init_db() at import time; without
# this the build would need a live database, which PRD-007 Section 11 forbids.
# Builder stage only -- a running deployment must boot with the reachability
# guard and the schema migration on.
ENV OPENROUTER_API_KEY=build-placeholder \
    ADMIN_TOKEN=build-placeholder \
    DATABASE_URL=http://127.0.0.1:8080 \
    DB_BOOTSTRAP_ENABLED=false

WORKDIR /app/chat_ui
RUN reflex init --no-agents

ARG PORT=8000
RUN REFLEX_API_URL=http://localhost:${PORT} reflex export --loglevel debug --frontend-only --no-zip \
    && mkdir -p /srv \
    && mv .web/build/client/* /srv/ \
    && rm -rf .web

# ---- final: Python + Caddy only, no Node/Bun runtime ----
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        debian-keyring debian-archive-keyring apt-transport-https curl gnupg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
    && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
    && apt-get update && apt-get install -y caddy \
    && apt-get purge -y curl gnupg apt-transport-https && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Presidio's analyzer needs an English spaCy model (PRD-003); it ships separately
# from the `spacy` package in requirements.txt. Baked into the image at build time
# so the container never downloads it at startup. ~425 MB — accepted tradeoff,
# PRD-003 Risk 5. Kept before `COPY . .` so app-code edits don't re-download it.
# The builder stage above deliberately skips this: `reflex export --frontend-only`
# imports app.main but never constructs the analyzer (STORY-011 Task 1 verified).
RUN python -m spacy download en_core_web_lg \
    && rm -rf /root/.cache/pip

COPY . .
COPY --from=builder /srv /srv
COPY Caddyfile /app/Caddyfile

ARG PORT=8000
ENV PORT=${PORT} \
    BACKEND_INTERNAL_PORT=8001 \
    REFLEX_ENV=prod \
    REFLEX_API_URL=http://localhost:${PORT}

# Reflex does not reliably handle SIGTERM for graceful shutdown; match the
# upstream reflex-dev/reflex production-one-port reference Dockerfile's stop signal.
STOPSIGNAL SIGKILL

EXPOSE ${PORT}

# WORKDIR stays /app (not chat_ui/) so `docker-compose run harness-ai pytest
# tests/ ...` keeps working exactly as documented in README.md; the CMD below
# cd's into chat_ui/ itself, since that's where Reflex needs its CWD to be.
CMD caddy start --config /app/Caddyfile --adapter caddyfile \
    && cd chat_ui \
    && exec reflex run --env prod --backend-only \
       --backend-port ${BACKEND_INTERNAL_PORT} --backend-host ${HOST:-0.0.0.0}
