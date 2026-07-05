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
ENV OPENROUTER_API_KEY=build-placeholder \
    ADMIN_TOKEN=build-placeholder \
    DATABASE_URL=sqlite:///:memory:

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
