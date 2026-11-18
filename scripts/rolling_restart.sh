#!/usr/bin/env bash
# Rolling restart of the two-instance stack (docker-compose.lb.yml), one
# instance at a time, without dropping a request the balancer already routed.
#
# PRD-019 STORY-009, acting on F6 and D4. Per instance, in order:
#   1. every OTHER instance must answer /ready 200, else refuse (never drain
#      the last healthy instance);
#   2. touch the drain file inside the container: /ready turns 503, so the
#      balancer's active health check (Caddyfile `health_interval`) stops
#      routing new requests to it, while requests in flight keep running;
#   3. wait until its own /ready answers 503;
#   4. sleep health_interval * 2 + DRAIN_SECONDS: two probe intervals for the
#      balancer to notice, then the longest an upstream call may run;
#   5. recreate it (`up -d --force-recreate --no-deps`) and wait for /ready 200.
# Before anything starts, every instance must be ready (refusal, exit 2).
#
# Usage, from the repo root or anywhere:
#
#     docker compose -f docker-compose.lb.yml build     # the script never builds
#     scripts/rolling_restart.sh [-f docker-compose.lb.yml]
#
# `up --force-recreate` reuses the existing image: build first to ship new code.
#
# Tunables (environment):
#   DRAIN_SECONDS             the drain window. Default OPENROUTER_TIMEOUT_SECONDS
#                             + 10. That value is read from your shell, else from
#                             inside the first instance (`.env` reaches the
#                             containers through env_file, not your shell), else
#                             120 (the app default). Fractions round up.
#   POLL_SECONDS (2)          pause between /ready probes
#   DRAIN_WAIT_SECONDS (30)   how long /ready may take to turn 503
#   READY_TIMEOUT_SECONDS (180)  how long a replacement may take to turn 200
#                             (boot loads spaCy; the image start period is 60 s)
#
# The health interval is parsed from deploy/lb/Caddyfile, never restated here.
# The script prints service names and status codes only, never compose output
# (`docker compose config` prints .env secrets).
#
# Exit codes: 0 done; 1 usage or configuration; 2 refused (an instance is not
# ready); 3 drain never took effect (undone, nothing recreated); 4 a replacement
# never became ready (the other instance was never touched and still serves).
#
# Not handled here (PRD-018 D11): the audit journal. Recreating a container
# keeps the audit volume, and the new process replays what is left.
# Residual race: an instance can die between the readiness check and the drain
# touch; the balancer's passive health covers that window.

set -euo pipefail

# Git Bash would otherwise rewrite container-side paths; a no-op elsewhere.
export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CADDYFILE="$ROOT/deploy/lb/Caddyfile"

SERVICES=(harness-a harness-b)

FILE="$ROOT/docker-compose.lb.yml"
POLL_SECONDS="${POLL_SECONDS:-2}"
DRAIN_WAIT_SECONDS="${DRAIN_WAIT_SECONDS:-30}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-180}"

# Inside the container; urllib turns a 503 into HTTPError, whose code we print.
READY_PROBE='import os, urllib.request as r, urllib.error as e
try:
    print(r.urlopen("http://127.0.0.1:%s/ready" % os.environ["PORT"], timeout=3).status)
except e.HTTPError as x:
    print(x.code)'

log() { echo "rolling_restart: $*" >&2; }
die() { local rc=$1; shift; log "$*"; exit "$rc"; }

usage() {
    echo "usage: scripts/rolling_restart.sh [-f COMPOSE_FILE]" >&2
    exit 1
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -f) [ $# -ge 2 ] || usage; FILE="$2"; shift 2 ;;
            -h|--help) usage ;;
            *) log "unknown argument: $1"; usage ;;
        esac
    done
    COMPOSE=(docker compose -f "$FILE")
}

# Whole seconds, from the one `health_interval <N>s` line of the balancer config.
read_health_interval() {
    local found
    found="$(sed -n -E 's/^[[:space:]]*health_interval[[:space:]]+([0-9]+)s[[:space:]]*\r?$/\1/p' "$CADDYFILE")"
    if [ -z "$found" ] || [ "$(printf '%s\n' "$found" | wc -l)" -ne 1 ]; then
        die 1 "$CADDYFILE must hold exactly one 'health_interval <N>s' line"
    fi
    HEALTH_INTERVAL="$found"
}

# HTTP code of the instance's own /ready; 000 when exec fails (container down).
ready_status() {
    local svc=$1 code
    code=$("${COMPOSE[@]}" exec -T "$svc" python -c "$READY_PROBE" 2>/dev/null) || code=000
    code="${code//$'\r'/}"
    case "$code" in
        [0-9][0-9][0-9]) echo "$code" ;;
        *) echo 000 ;;
    esac
}

# Round a non-negative decimal up to an integer (bash arithmetic is integer only).
round_up() {
    local v=$1 whole frac
    [[ "$v" =~ ^[0-9]+(\.[0-9]+)?$ ]] || return 1
    whole="${v%%.*}"
    if [[ "$v" == *.* ]]; then
        frac="${v#*.}"
        if [[ "$frac" =~ [1-9] ]]; then whole=$((10#$whole + 1)); fi
    fi
    echo $((10#$whole))
}

compute_drain_seconds() {
    if [ -n "${DRAIN_SECONDS:-}" ]; then
        DRAIN="$(round_up "$DRAIN_SECONDS")" || die 1 "DRAIN_SECONDS must be a number, got '$DRAIN_SECONDS'"
        return
    fi
    local timeout="${OPENROUTER_TIMEOUT_SECONDS:-}"
    if [ -z "$timeout" ]; then
        # .env reaches the containers via env_file, not this shell: ask the first one.
        timeout=$("${COMPOSE[@]}" exec -T "${SERVICES[0]}" python -c \
            "import os;print(os.environ.get('OPENROUTER_TIMEOUT_SECONDS',''))" 2>/dev/null) || timeout=""
        timeout="${timeout//$'\r'/}"
    fi
    timeout="${timeout:-120}"   # the app/config.py default
    timeout="$(round_up "$timeout")" || die 1 "OPENROUTER_TIMEOUT_SECONDS must be a number, got '$timeout'"
    DRAIN=$((timeout + 10))
}

# Poll <svc> /ready until it equals <code> or <timeout> seconds pass.
wait_ready_code() {
    local svc=$1 want=$2 timeout=$3 last=000 deadline
    deadline=$((SECONDS + timeout))
    while :; do
        last="$(ready_status "$svc")"
        [ "$last" = "$want" ] && return 0
        [ "$SECONDS" -ge "$deadline" ] && break
        sleep "$POLL_SECONDS"
    done
    log "timed out after ${timeout}s waiting for $svc /ready to be $want (last code $last)"
    return 1
}

# Never drain the last healthy instance: every OTHER service must be 200 now.
require_others_ready() {
    local svc=$1 other code
    for other in "${SERVICES[@]}"; do
        [ "$other" = "$svc" ] && continue
        code="$(ready_status "$other")"
        [ "$code" = "200" ] || die 2 "refusing to drain $svc: $other is not ready ($code)"
    done
}

drain_file_undo() {
    "${COMPOSE[@]}" exec -T "$1" sh -c 'rm -f "${DRAIN_FILE:-/tmp/harness-drain}"' >/dev/null 2>&1 || true
}

main() {
    parse_args "$@"
    read_health_interval

    local svc code
    for svc in "${SERVICES[@]}"; do
        code="$(ready_status "$svc")"
        [ "$code" = "200" ] || die 2 "refusing to start: $svc is not ready ($code)"
    done
    compute_drain_seconds
    log "health_interval ${HEALTH_INTERVAL}s, drain window ${DRAIN}s"

    for svc in "${SERVICES[@]}"; do
        require_others_ready "$svc"
        log "draining $svc"
        "${COMPOSE[@]}" exec -T "$svc" sh -c 'touch "${DRAIN_FILE:-/tmp/harness-drain}"' >/dev/null
        if ! wait_ready_code "$svc" 503 "$DRAIN_WAIT_SECONDS"; then
            drain_file_undo "$svc"
            die 3 "drain of $svc did not take effect; undone, nothing recreated"
        fi
        sleep $((HEALTH_INTERVAL * 2 + DRAIN))
        log "recreating $svc"
        "${COMPOSE[@]}" up -d --force-recreate --no-deps "$svc" >/dev/null
        wait_ready_code "$svc" 200 "$READY_TIMEOUT_SECONDS" \
            || die 4 "$svc never became ready; the other instance was not touched"
        log "restarted $svc"
    done
    log "done"
}

main "$@"
