# Testing & troubleshooting

Running the test suite against a local libSQL server, reading the `libsql diagnostics` verdicts, and resolving the errors you are most likely to hit.

← Back to the [README](../README.md).

---

## Running Tests

The PII tests load the real `en_core_web_lg` model, so run the `spacy download` step from [Quickstart — Local](../README.md#quickstart--local) first — otherwise the first test run spends several minutes downloading it. The in-container run needs nothing extra (the image already has it).

The suite needs a libSQL server to run against. **No Turso account is required** — the tests use a local server that runs offline, takes no token, and never touches a hosted database:

```bash
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
```

The tests default to `http://127.0.0.1:8080`; set `HARNESS_TEST_LIBSQL_URL` to point them somewhere else if that port is taken (`tests/conftest.py`).

Locally:

```bash
pytest tests/ -v                         # everything (the default); needs the libSQL server
pytest tests/ -m "not db" -v             # the tests that never touch storage; no Docker needed
pytest tests/ -m db -v                   # only the storage tests
pytest tests/ --collect-only -q -m db    # list what counts as a db test
```

About two thirds of the suite never touches storage. Those tests are not `db`: they are not reset, and they cannot reach the server at all, so `-m "not db"` is a fast loop that runs with Docker stopped. A test is `db` when it requests a storage fixture (`temp_db`, `database_url`, `uninitialized_db`, `database_url_factory` or `db_connect`, directly or through another fixture), carries `@pytest.mark.db`, or is listed in `_DB_NODEIDS` in `tests/conftest.py`. The marker is applied at collection, so test files do not declare it. With the server down, a full run stops at the first `db` test with a "libSQL dev server ... is unreachable" message that says how to start it.

**A test failed with "reached storage ... without declaring it".** For example:

```
tests/test_router_extra.py::test_lists_rows reached storage (app/db/database.py:get_connection) without declaring it.
Request temp_db (or database_url / uninitialized_db / database_url_factory / db_connect),
add @pytest.mark.db, or -- for a suite that must not be edited -- add its nodeid to
_DB_NODEIDS in tests/conftest.py.
```

A test that is not `db` tried to open a database connection, and the harness refused before any socket was opened. That is a missing declaration, not a database problem, and it fails the test even if application code catches the error: an `except Exception` cannot catch it, and an access swallowed some other way (or made in a worker thread) fails the test at teardown. Fix it in one of three ways, in this order of preference:

1. Request a storage fixture, usually `temp_db`. This is the right fix for a new test.
2. Add `@pytest.mark.db` when the test reaches storage some other way, for example through the app's lifespan.
3. Add its nodeid, or its module path, to `_DB_NODEIDS` in `tests/conftest.py` when its file must not be edited (the PRD-006 suites that `tests/test_untouched_app.py` pins).

**Reading a `libsql diagnostics` section.** Every `db` test that fails in setup, call or teardown gets one in its failure report. A passing test gets none. The last line always starts with `libsql verdict: `, so `grep "libsql verdict"` over a run's output classifies every failure without a rerun:

```
------------------------------ libsql diagnostics ------------------------------
calls: 212 on 2 clients, 1 connect
slowest: execute 15.047 s (client idle 0.12 s before) -> STREAM_EXPIRED
over 10 s: execute 15.047 s
driver errors: 1 x STREAM_EXPIRED
libsql verdict: likely infrastructure -- execute took 15.05 s and ended in STREAM_EXPIRED
```

| Verdict | What it means | What to do |
|---|---|---|
| `likely infrastructure -- <op> took <s> s and ended in <error>` (`STREAM_EXPIRED`, `tcp connect error`, ...) | The libSQL server stalled or dropped the stream during this test | Rerun the test alone. If it passes, it was not your change. Quote the verdict line wherever you report the flake |
| `likely infrastructure -- <op> took <s> s (no driver error)` | A call took 10 s or more, but the driver reported no error. The failure is probably a timeout downstream of the stall | The same: rerun it alone |
| `no infrastructure signal (<n> calls, slowest <s> s)` | Storage behaved normally | Treat it as a real failure and debug it |
| `no driver calls recorded` | Nothing was recorded: the test failed before any storage call, or `monkeypatch.undo()` removed the recorder | Judge it from the traceback |

The section shows method names, timings and error labels only, never SQL statements, parameters or credentials.

**If `db` tests flake on Docker Desktop.** The stalls behind most infrastructure verdicts were measured only behind Docker Desktop's port forwarding: 0 stall events in-network against 2 on the host, over about 143,000 driver calls each (a small sample). Running `-m db` from a container on the same Docker network as `harness-libsql-dev` avoided them ([spike report](../.agents/spikes/PRD-014-docker-network-stalls.md)). One script does that, from Git Bash on Windows or any bash:

```bash
scripts/test-db-in-network.sh                     # build the image, then run every db test
scripts/test-db-in-network.sh --no-build -x -k audit   # reuse the last image; extra args go to pytest
```

It builds the `harness-ai` image and puts `harness-libsql-dev` on a `harness-test-net` network, which it creates the first time and leaves in place. It then runs `pytest tests/ -m db` in a throwaway container that reaches the server by name, with the same three overrides as the in-container run below. It uses `docker run --network` because `docker compose run` has no `--network`. The server keeps its `127.0.0.1:8080` port, so host-side runs are unaffected. Three things to know about it:

- It tests the code **baked into the image**. After a change, leave out `--no-build`.
- It deselects the three `tests/test_measure_usage_latency.py` tests that write to the database. Their script refuses any host name but localhost, by design, so the host run covers them.
- `docker compose` needs the `.env` from [Quickstart — Docker](../README.md#quickstart--docker) to exist, although the test container never receives it.

The host-side `pytest tests/ -m db` stays supported, with the verdict line to classify its rare stalls.

Inside the Docker container:

```bash
docker-compose run --rm \
  -e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080 \
  -e DATABASE_URL=http://host.docker.internal:8080 \
  -e TURSO_AUTH_TOKEN= \
  harness-ai pytest tests/ -v
```

All three overrides are required, for three different reasons. The container inherits its environment from `.env` through `env_file`, so without them each of these would be the deployment's value rather than a test value:

- `HARNESS_TEST_LIBSQL_URL` points the test fixtures at a server they can actually reach. Inside a container, `127.0.0.1` is the container's own loopback, not your host — without this the run fails immediately with a connection error.
- `DATABASE_URL` overrides the value `env_file: .env` injects into the container. The test suite's own default is applied with `setdefault`, which cannot override a variable the process already inherited, and one test in `tests/test_db.py` calls `monkeypatch.undo()` — which also reverts the autouse fixture that redirects each test at an isolated database. Everything after that line runs against whatever `DATABASE_URL` the container was started with. **Without this override, an in-container test run can reach the database named in your `.env` — including a production one.** Always pass it.
- `TURSO_AUTH_TOKEN=` (deliberately empty) keeps the deployment's real credential out of the test process. `tests/test_config.py` asserts that a local `http://` endpoint is accepted *without* a token and that an `https://` endpoint is rejected *for lacking* one; an inherited token makes both assertions false and produces two failures that have nothing to do with your change.

On Linux, `host.docker.internal` is not resolvable by default; add `--add-host=host.docker.internal:host-gateway` to the command above.

**A known collection error, and when it does *not* apply.** Running `tests/test_pii_badge.py` or `tests/test_success_metadata_footer.py` **on their own** fails at collection with `ModuleNotFoundError: No module named 'chat_ui.chat_ui.models'; 'chat_ui.chat_ui' is not a package`. This is a packaging problem, not a database one, and it does not affect a whole-suite run: collecting the full `tests/` directory imports `chat_ui.chat_ui` as a package first, and both modules then pass. If you need to run either file in isolation, expect this error until the packaging is fixed.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'fastapi'`**
Run `pip install -r requirements.txt`.

**`OPENROUTER_API_KEY not found` on startup**
Copy `.env.example` to `.env` and fill in a real key.

**`DATABASE_URL must name a libSQL endpoint, not a file` at startup**
Your `.env` still carries a `sqlite:` URL from before the Turso migration. `DATABASE_URL` now names a network endpoint (`libsql://...`, `https://...`, or `http://127.0.0.1:8080` for the local dev server), and a file path is rejected rather than quietly created — see the [Environment Variables](configuration.md#environment-variables) table. The full message names the replacement to use.

**`TURSO_AUTH_TOKEN is required when DATABASE_URL names a remote endpoint` at startup**
A `libsql://` or `https://` endpoint needs its token; the check fires before anything is dialled, so this is a configuration error rather than a connection failure. The local `http://` dev server takes no token — leave `TURSO_AUTH_TOKEN` empty for it.

**`DatabaseUnreachableError: Cannot reach the database at <endpoint>`**
The endpoint is not reachable from this host, and the application refuses to start rather than boot into a broken state. There is deliberately no local-file fallback to degrade to. Check `DATABASE_URL`, network reachability, and — if the endpoint answers but the credential is refused — expect `DatabaseAuthError` instead, which means `TURSO_AUTH_TOKEN` is wrong or expired rather than the host being down. The message quotes the driver's own reason at the end.

**Docker container exits immediately**
Check logs with `docker-compose logs harness-ai`. If the traceback ends in `sqlite3.connect` — a call the current code no longer contains — you are running an image built before the Turso migration: `docker-compose up` reuses an existing image rather than rebuilding it. Rebuild with `docker-compose up -d --build`.

**First startup stalls while downloading several hundred MB**
That is spaCy fetching `en_core_web_lg` because it was never installed — Presidio downloads a missing model on first use rather than failing. Run `python -m spacy download en_core_web_lg` up front (see [Quickstart — Local](../README.md#quickstart--local)) to keep it out of the startup path, or set `PII_REDACTION_ENABLED=false` to skip redaction entirely.

**`[x] No compatible package found for '<model>'` and the process exits during startup**
`PII_NLP_MODEL` names a model spaCy cannot resolve, so the automatic download fails and takes the process down with it. Fix the name, or install that model yourself. Because the model is loaded at startup, this kills the boot rather than the first request. Load failures that are not download failures surface instead as `PiiRedactorError: Failed to load Presidio NLP model '<model>'`.

**Model responses contain `<PERSON>` or `<EMAIL_ADDRESS>` where you expected real text**
That is PII redaction working as designed — the threshold (`PII_SCORE_THRESHOLD`, default `0.35`) deliberately favors over-masking. Raise it, or trim `PII_ENTITIES`, if a specific entity type is too aggressive for your use case. Under the `code` profile the equivalents are `PII_SCORE_THRESHOLD_CODE` and `PII_ENTITIES_CODE`, and the response itself is not masked there (see [PII redaction](features.md#pii-redaction)).

**`RbacNotBootstrappedError: RBAC_ENABLED=true but no active users exist` at startup**
Bootstrap at least one user: `python scripts/manage_users.py create-user --user-id <id> --role admin`. This is required even when `ADMIN_TOKEN` is set — break-glass does not satisfy the bootstrap guard (`app/services/authz.py`'s `check_bootstrap()`). To migrate an existing deployment without bootstrapping immediately, set `RBAC_ENABLED=false`.

**`401 Unauthorized` on `/query`, `/audit`, or `/stats`**
The `Authorization: Bearer <token>` header is missing, doesn't match any active user's token, or matches a deactivated user. Issue a token with `python scripts/manage_users.py create-user --user-id <id> --role <admin|auditor|user>`, or confirm `ADMIN_TOKEN` in `.env` matches exactly (it always works as break-glass).

**`403 Forbidden` on `/query`, `/audit`, or `/stats`**
The credential is valid, but the role lacks the permission that endpoint requires — for example, an `auditor` calling `/query`, or a `user` calling `/stats`. This is different from `401`: authentication succeeded, authorization did not. See the role→permission matrix in the Features table above, or `app/services/authz.py`.

**`"reason": "Usage limit reached"` on `POST /query`, or *You've reached today's usage limit* in the chat**
The user is over one of their [usage limits](features.md#usage-limits). `limit` says which — `requests` clears at the next minute, `tokens` at the next 00:00 UTC, both given in `resets_at`. To raise it for one user, `python scripts/manage_users.py set-limits --user-id <id> --token-budget <N>` (or `--requests-per-minute <N>`), which applies to their next request; to raise it for a role, change `USAGE_DAILY_TOKEN_BUDGET` or `USAGE_REQUESTS_PER_MINUTE` and restart. The admin console's Usage page shows who is near their budget.

**`500` on `POST /query` with `Usage admission failed: …`**
The usage gate could not read its counter in the database, so the request was refused without reaching the model — fail closed by design, like the duplicate check. Check the database as for `DatabaseUnreachableError`; see [The database is a hard dependency of every request](deployment.md#the-database-is-a-hard-dependency-of-every-request). Setting `USAGE_LIMITS_ENABLED=false` removes the dependency, and the limits with it.

**`"required_permission": "ingress:break_glass"` when using `ADMIN_TOKEN`**
`BREAK_GLASS_INGRESSES` does not include the ingress you used. Use an admin user's own token from `scripts/manage_users.py` instead, or add `query` or `chat` back to the setting.

---
