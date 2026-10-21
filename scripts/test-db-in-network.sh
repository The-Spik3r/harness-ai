#!/usr/bin/env bash
# Run the `db` tests from inside the Docker network, not through the host port.
#
# PRD-014 STORY-008, acting on D5. The libSQL stalls (a 21 s `tcp connect
# error`, then `STREAM_EXPIRED` on the reused client) were measured only behind
# Docker Desktop's port forwarding: 2 stall events in 143,604 host calls, 0 in
# 143,461 in-network calls (.agents/spikes/PRD-014-docker-network-stalls.md).
# This script runs `pytest tests/ -m db` in a throwaway container of the
# harness-ai image that reaches harness-libsql-dev by name on a user network.
# The host-side `pytest tests/ -m db` stays supported.
#
# What it does, every step safe to repeat:
#   1. checks harness-libsql-dev is running (it never creates the server);
#   2. creates the network and connects the server to it if either is missing,
#      and leaves both in place: the server keeps its 127.0.0.1:8080 publish;
#   3. builds the image (`docker compose build harness-ai`, layer-cached), so
#      the run tests the current tree -- `--no-build` reuses the last image;
#   4. runs pytest with the three overrides README "Running Tests" explains.
#      It uses `docker run`, because `docker compose run` has no `--network`,
#      and it never passes `.env`.
#
# Three tests are deselected here: scripts/measure_usage_latency.py refuses any
# host but localhost by design, so they fail against `harness-libsql-dev`. The
# host run covers them. They are also listed in `_DB_NODEIDS` in
# tests/conftest.py; rename them in both places.
#
# Usage (from Git Bash on Windows, or any bash):
#
#     scripts/test-db-in-network.sh
#     scripts/test-db-in-network.sh --no-build -x -k audit
#
# Every argument after the optional `--no-build` goes to pytest. Tunables:
# HARNESS_TEST_NETWORK (default harness-test-net) and HARNESS_LIBSQL_CONTAINER
# (default harness-libsql-dev).

set -euo pipefail

# Git Bash would otherwise rewrite container-side paths; a no-op elsewhere.
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

NETWORK="${HARNESS_TEST_NETWORK:-harness-test-net}"
SERVER="${HARNESS_LIBSQL_CONTAINER:-harness-libsql-dev}"

build=1
if [ "${1:-}" = "--no-build" ]; then
  build=0
  shift
fi

if [ "$(docker inspect -f '{{.State.Running}}' "$SERVER" 2>/dev/null)" != "true" ]; then
  echo "test-db-in-network: libSQL dev server container '$SERVER' is not running." >&2
  echo "Start it with: docker start $SERVER" >&2
  echo "(or create it with the docker run command in README.md, Running Tests)" >&2
  exit 2
fi

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create "$NETWORK" >/dev/null
  echo "test-db-in-network: created network $NETWORK"
fi

if ! docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$SERVER" \
    | grep -qxF "$NETWORK"; then
  docker network connect "$NETWORK" "$SERVER"
  echo "test-db-in-network: connected $SERVER to $NETWORK"
fi

if [ "$build" = 1 ]; then
  docker compose build harness-ai
fi
image="$(docker compose config --images harness-ai)"

url="http://$SERVER:8080"
exec docker run --rm --network "$NETWORK" \
  -e HARNESS_TEST_LIBSQL_URL="$url" \
  -e DATABASE_URL="$url" \
  -e TURSO_AUTH_TOKEN= \
  "$image" python -m pytest tests/ -m db -q -p no:cacheprovider \
  --deselect "tests/test_measure_usage_latency.py::test_a_short_run_reports_both_calls_and_cleans_up" \
  --deselect "tests/test_measure_usage_latency.py::test_a_refused_admit_ends_the_run_without_a_report" \
  --deselect "tests/test_measure_usage_latency.py::test_a_changed_statement_count_ends_the_run_without_a_report" \
  "$@"
