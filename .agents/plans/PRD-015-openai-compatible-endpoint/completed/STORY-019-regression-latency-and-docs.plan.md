---
story: STORY-019
prd: PRD-015
slug: regression-latency-and-docs
title: "Regression sweep, translation latency, README API reference and per-client setup, .env.example"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-30
---

# Plan: Regression sweep, translation latency, README API reference and per-client setup, .env.example

## Summary

The last story of PRD-015. Nothing under `app/` changes. It adds one measurement script, `scripts/measure_v1_latency.py` (modelled line for line on `scripts/measure_usage_latency.py`), which sends the same one-turn conversation through `POST /query` and `POST /v1/chat/completions` on an in-process `TestClient(app)`. The real `call_openrouter` reaches the real stub upstream (`scripts/stub_openrouter.make_server`) over loopback HTTP, and audit rows go to the local libSQL server. It reports p50/p95 for each arm, the end-to-end added p95, and the translation-only p95 (`translate_request` + `translate_result` + JSON encoding). A miss is printed as a miss. A test module mirrors `tests/test_measure_usage_latency.py`. Then the README is rewritten to describe `/v1` as shipped: Features, API Reference, per-client setup built from the settings STORIES 015–017 proved, what `/v1` does not do, and the stale "reachable by tests only" / "PRD-014 will add" sentences. `.env.example` gets the three new settings. The full regression sweep runs twice (Docker-free `-m "not db"`, then everything against libSQL), and the PRD, pre-PRD milestones and board are closed.

## User Story

As a platform operator and integrating developer
I want the README to describe `/v1` as shipped (how to point each client at it, what each error means, what it does not do) and the existing behaviour proven unchanged
So that I can adopt it from the documentation alone

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-019-regression-latency-and-docs.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 7.5, 7.7, 9.3, 10, 11 Quality indicators, 12 Phase 4, 13)
- Evidence for the per-client settings: the STORY-015, -016, -017 and -018 reports in `.agents/reports/PRD-015-openai-compatible-endpoint/`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (docs + measurement + regression; no `app/` change) |
| Complexity | MEDIUM |
| Systems Affected | `scripts/`, `tests/`, `README.md`, `.env.example`, `tests/conftest.py` (`_DB_NODEIDS`), `scripts/test-db-in-network.sh`, `pre-prds/README.md`, PRD frontmatter + board |
| Story | STORY-019 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

Dependencies STORY-008, -015, -016, -017 and -018 are all `done` (verified).

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story has no UI change (story Technical Notes: "Skills: none applicable") | — |

---

## Patterns to Follow

### Script bootstrap (env before the first `app.` import, local-only guard)
```python
# SOURCE: scripts/measure_usage_latency.py:73-125
_DEFAULT_ENDPOINT = "http://127.0.0.1:8080"

def _database_url(argv): ...   # --database-url, else HARNESS_TEST_LIBSQL_URL, else the dev server

def _bootstrap_environment(argv=None) -> str:
    endpoint = _database_url(argv)
    os.environ["DATABASE_URL"] = endpoint
    os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
    os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")
    return endpoint

_ENDPOINT = _bootstrap_environment()
if __name__ == "__main__":
    _guard_local(_ENDPOINT, "--allow-remote-database" in sys.argv[1:])

from app.db import database  # noqa: E402
```

### Samples / nearest-rank p95 (copy, do not re-derive)
```python
# SOURCE: scripts/measure_usage_latency.py:182-218
class Samples:
    def summary(self) -> tuple[float, float, float]:
        ordered = sorted(self.values)
        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
        return min(ordered), statistics.median(ordered), p95

def _timed(work):
    started = time.perf_counter()
    result = work()
    return result, (time.perf_counter() - started) * 1000
```

### A run that would measure the wrong thing exits 1, no report
```python
# SOURCE: scripts/measure_usage_latency.py:338-363
class NotAdmitted(RuntimeError): ...
...
    except NotAdmitted as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        # cleanup always runs
```

### Stub upstream in-process, port 0
```python
# SOURCE: scripts/stub_openrouter.py:351-371
server = make_server(parse_script({"default": {"content": "...", "usage": {...}}}))  # port 0
host, port = server.server_address[:2]   # serve_forever on a daemon thread
```

### Booting the app in-process, real auth
```python
# SOURCE: tests/test_v1_router.py:29-37
from fastapi.testclient import TestClient
from app.db.database import insert_user
from app.db.models import User
from app.main import app
from app.services.identity import hash_token
```
User creation and the per-user rate override: `scripts/manage_users.py:65-82` (`issue_token` + `insert_user(User(...))`), `app/db/database.py:1627` (`set_user_limits(..., requests_per_minute=...)`), `app/db/database.py:1600` (`deactivate_user`).

### Settings read per call (lets the script point at a port-0 stub after import)
```python
# SOURCE: app/services/openrouter_client.py:173
url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
# SOURCE: app/services/pii_redactor.py:149
if not settings.PII_REDACTION_ENABLED:
```

### Tests for a spike script
```python
# SOURCE: tests/test_measure_usage_latency.py:20-31, 44-58, 61-71, 117-127
_saved_database_url = os.environ.get("DATABASE_URL")
import scripts.measure_usage_latency as bench  # noqa: E402
# ...restore DATABASE_URL...
def test_importing_the_script_opens_no_connection(): ...   # fresh interpreter, database._client is None
@pytest.mark.parametrize("n, expected_p95", [(20, 19), (50, 48), (1, 1)])
def test_p95_is_nearest_rank(n, expected_p95): ...
def test_a_short_run_reports_both_calls_and_cleans_up(capsys):
    assert bench.main(["--runs", "3"]) == 0
```

### A db test with no storage fixture is listed twice
```python
# SOURCE: tests/conftest.py:114-125 (_DB_NODEIDS) and scripts/test-db-in-network.sh:22-27, 81-83 (--deselect)
# "They are also listed in `_DB_NODEIDS` in tests/conftest.py; rename them in both places."
# tests/test_db_in_network_script.py pins that every deselected id exists and is a db test.
```

### README voice for a measured cost
```markdown
<!-- SOURCE: README.md:377 (Usage limits, "What it costs") -->
Measured against the local libSQL dev server on the same host, 50 runs each: **`admit` about 8.5 ms ...**
The script is `scripts/measure_usage_latency.py`: `python scripts/measure_usage_latency.py --runs 50` ...
```

### `.env.example` entry shape (comment line(s) directly above `VAR=default`)
```bash
# SOURCE: .env.example:75-77 and tests/test_config.py:64-68 (regex (?m)^#.+\nVAR=)
# Seconds to wait for the upstream provider before giving up; must be > 0.
# Replaces the old hard-coded 30s, too short for a long conversation
OPENROUTER_TIMEOUT_SECONDS=120.0
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/measure_v1_latency.py` | CREATE | `/query` vs `/v1` end-to-end and translation-only p50/p95 against the stub upstream; records, asserts nothing |
| `tests/test_measure_v1_latency.py` | CREATE | Tests the parts the numbers depend on, as `tests/test_measure_usage_latency.py` does |
| `tests/conftest.py` | UPDATE | Add the new in-process db tests to `_DB_NODEIDS` |
| `scripts/test-db-in-network.sh` | UPDATE | Deselect the same tests (the script refuses a non-localhost host); "Three" → the new count |
| `.env.example` | UPDATE | `OPENROUTER_BASE_URL` (with the T10 rule), `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS` |
| `tests/test_config.py` | UPDATE | One new test: the three vars present with a comment line, in `Settings` field order (adds a pin; changes no existing assertion) |
| `README.md` | UPDATE | Features, Pattern policy, PII redaction, Usage limits, Environment Variables, API Reference, Running Tests, Roadmap, ToC |
| `pre-prds/README.md` | UPDATE | Milestone 1 reached |
| `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` | UPDATE | Frontmatter `status`, `updated` |
| `.agents/PRDs/PRD-015-openai-compatible-endpoint/index.md` | UPDATE | Regenerated: 19/19, PRD status |
| `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-019-regression-latency-and-docs.md` | UPDATE | `plan`, `status` (this `/plan` run); `report`/`commit` at `/implement` |

No file under `app/` changes. If the sweep finds a regression, that is a finding to report and stop on, not something to fix inside this story.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Baseline the sweep before touching anything

- **File**: none (record output for the report)
- **Action**: RUN
- **Implement**:
  1. Docker stopped (or `harness-libsql-*` containers stopped): `pytest tests/ -m "not db" -q`. This is the AC 1 Docker-free leg.
  2. Start a throwaway libSQL container and run the full suite with `HARNESS_TEST_LIBSQL_URL` pointing at it. Use the recipe in the user's memory notes: throwaway container, keep-awake for the long run, `PYTHONPATH` from Git Bash, ASCII-only output. Record the pass/fail counts and the libSQL verdict line for any failing `db` test.
  3. Separately record the named suites by file: `tests/test_query_outcomes_regression.py`, `tests/test_chat_outcomes_regression.py`, the console suites (`tests/test_admin_*.py`, `tests/test_register.py`, `tests/test_usage_view.py`, `tests/test_reports_*.py`), and `tests/test_v1_query_isolation.py`.
  4. `git diff main --stat -- tests/` and `git log main..HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_v1_query_isolation.py tests/test_admin_*.py`. Show that **no pre-existing assertion changed** on the epic branch except STORY-008's two in `tests/test_pattern_profiles.py` (`test_built_in_matrix_cell[code-assistant-flag]`, `test_the_matrix_has_no_cells_beyond_section_6_4`, per the STORY-008 report "AC 5" table). Any other changed pre-existing assertion is a finding for the report.
- **Validate**: both runs green, or every failure classified (storage flake via the verdict line, versus real) before going on. A real regression stops the story.

### Task 2: `scripts/measure_v1_latency.py`

- **File**: `scripts/measure_v1_latency.py`
- **Action**: CREATE
- **Mirror**: `scripts/measure_usage_latency.py` in full: module docstring (what is timed, why nothing is asserted, what it writes, usage), bootstrap, `_guard_local`, `Samples`, `_timed`, `_report`, `_measure_command`, `_build_parser`, `main`. Copy `Samples`/`_timed` with a "copied from" comment, as that script does from `measure_history_latency.py`.
- **Implement**:
  - **Bootstrap** (before any `app.` import): `DATABASE_URL` as in the mirror. `OPENROUTER_API_KEY`/`ADMIN_TOKEN` `setdefault` to stub values. Pre-import side effects are limited to `os.environ`: no socket, no thread, no DB.
  - **Stub upstream**, started in `_measure_command`: `make_server(parse_script({...}), port=0)` on a daemon thread. The default reply is fixed content with `usage` `{prompt_tokens: 12, completion_tokens: 5}` and `finish_reason: "stop"`. After it is bound, set `settings.OPENROUTER_BASE_URL = f"http://127.0.0.1:{port}/v1"`. The client reads it per call (`openrouter_client.py:173`), so assignment after import is enough. A comment says why it is not set in the bootstrap: importing must start nothing. Pass `log=io.StringIO()` so the stub's per-request stderr lines do not interleave with the report. `shutdown()` + `server_close()` in `finally`.
  - **PII**: `--pii {off,on}`, default `off`, assigned to `settings.PII_REDACTION_ENABLED` (read per call, `pii_redactor.py:149`). The reason goes in the docstring and the report: `/query` runs `chat` (Presidio NER on the prompt) and `/v1` runs `code` (pattern recognizers only). With PII on, the delta measures the profile difference and comes out negative, which says nothing about translation. `--pii on` is kept for anyone who wants the real-deployment figure.
  - **Bench identity**: `user_id = f"{args.user_id}-{uuid4().hex[:8]}"` (default prefix `story019-bench`), role `user`, created via `issue_token()` + `insert_user(User(...))` (mirror `manage_users.py:65-82`). Then `set_user_limits(user_id, requests_per_minute=10**9)`, so 2 × (runs + warm-up) requests inside one minute are never rate-refused. Budget stays the role's: 17 tokens a request cannot reach `*=1000000`.
  - **Model**: `settings.model_allowlist_list[0]`, so a developer `.env` with a different allowlist still gets admitted requests. Recorded in the report.
  - **Same conversation, never a duplicate**: one user turn, `f"Summarise the release notes, run {nonce}-{i}-{arm}"`. Nonce per process, `i` per run, `arm` in `{query, v1}`. Dedup is per user and crosses ingresses (memory: cross-ingress dedup), so each request must differ. A comment states that the varying suffix is the same length on both arms.
  - **Arms** (in-process `with TestClient(app) as client:` so the lifespan runs, bearer = the bench token):
    - `query`: `POST /query` `{"prompt": text, "model": model}`. An admitted run is `200` with the success body (`status` field per `QuerySuccessResponse`; check `app/models/schemas.py` for the exact discriminator).
    - `v1`: `POST /v1/chat/completions` `{"model": model, "messages": [{"role": "user", "content": text}]}`, non-streamed. Admitted = `200` and `object == "chat.completion"`.
    - Anything else (a block, a 5xx) raises `NotAnswered` with the status and the `reason`/`error.code` only, never content. The run exits 1 without a report, mirroring `NotAdmitted`.
  - **Order**: one discarded warm-up per arm (analyzer build, first connection, route import). Then `--runs` iterations, **interleaved** `query, v1` with the order alternated each iteration (`i % 2`), so drift (DB cache, thermal) hits both arms equally.
  - **Translation-only arm** (the PRD's "for translation"): time `translate_request(ChatCompletionRequest.model_validate(body))` + `translate_result(<the last real QuerySuccessResponse>, <a matching OpenRouterResult>, created)` + `ChatCompletion.model_dump_json()`, `--runs` times, in-process with no I/O. Check the exact `translate_result` signature at `app/services/v1_translate.py:368` and the router's use at `app/routers/v1.py:226`. Build the inputs once from a captured real result.
  - **Report** (mirror `_report`, ASCII only):
    ```
    --- PRD-015 STORY-019 /v1 translation latency ---
      endpoint / stub / host / python / runs / model / pii
      arm          n   min ms   p50 ms   p95 ms
      query       50 ...
      v1          50 ...
      translate   50 ...
      added p95, end to end (v1 p95 - query p95) : X.XX ms
      translation p95                            : Y.YY ms
      PRD-015 target (Section 11): translation p95 < 10 ms -> MET | MISSED
      end-to-end added p95 vs 10 ms              -> within | over
    ```
    Both verdict lines always print, and neither is an exit code: the script asserts nothing (mirror docstring). A negative delta prints as negative.
  - **Cleanup** (`finally`, unless `--keep`): `deactivate_user(user_id)`, and print the bench user id and the count of audit rows it wrote (`list_audit_logs(user_id=...)`). Audit rows are not deleted: `audit_logs` is the evidentiary log and has no delete path. The guard keeps the script on a local DB, and the docstring says the rows stay.
  - **CLI**: `--runs` (default 50, `< 1` → exit 1 with the mirror's message), `--database-url`, `--user-id`, `--pii`, `--keep`, `--allow-remote-database`.
- **Validate**: `python scripts/measure_v1_latency.py --runs 3` against the throwaway libSQL prints the report and exits 0; `python -c "import scripts.measure_v1_latency"` starts no server and opens no connection.

### Task 3: `tests/test_measure_v1_latency.py`

- **File**: `tests/test_measure_v1_latency.py`
- **Action**: CREATE
- **Mirror**: `tests/test_measure_usage_latency.py` (module docstring, the `DATABASE_URL` save/restore around the import, test names and shapes).
- **Implement**:
  - `test_importing_the_script_opens_no_connection`: fresh interpreter; `database._client is None`, `pii_redactor._analyzer is None`, and no non-main thread alive (`threading.active_count() == 1`), which shows no stub was started at import.
  - `test_p95_is_nearest_rank`: same parametrization.
  - `test_the_guard_passes_a_local_endpoint`, `test_the_guard_refuses_a_remote_endpoint_unless_allowed`, `test_run_as_a_program_a_remote_endpoint_is_refused_before_settings_load`: same as the mirror.
  - `test_zero_runs_is_refused`.
  - Pure report tests (no DB): build `Samples` by hand and call `_report(...)`. Translation p95 9.99 → `MET`; 10.0 → `MISSED`. A negative end-to-end delta prints with its sign. This pins "a miss is recorded as such, not hidden" (AC 2).
  - **db** (in-process `bench.main`): `test_a_short_run_reports_every_arm_and_deactivates_the_bench_user`: `--runs 3` → exit 0; `query`, `v1`, `translate` rows with `n == 3`; both verdict lines present; the bench user is inactive afterwards; it wrote exactly 2 × (3 + 1) audit rows, half `ingress='query'` and half `ingress='v1'`.
  - **db**: `test_a_blocked_request_ends_the_run_without_a_report`: monkeypatch the bench's prompt builder to return the same text every run, so the second request is a duplicate → exit 1, the reason on stderr, no `p95 ms` on stdout, and the stub server shut down (its port closed).
- **Validate**: `pytest tests/test_measure_v1_latency.py -v` (db tests against the throwaway libSQL); `pytest tests/test_measure_v1_latency.py -m "not db" -v` with Docker stopped.

### Task 4: Register the in-process db tests

- **Files**: `tests/conftest.py`, `scripts/test-db-in-network.sh`
- **Action**: UPDATE
- **Implement**: add the two db nodeids to `_DB_NODEIDS` under a `# In-process bench.main() for /v1 latency ...` comment. Add matching `--deselect` lines to the in-network script and update its "Three tests are deselected" comment to name both scripts and the new count. Also update README `README.md:929` ("the three `tests/test_measure_usage_latency.py` tests") in Task 7.
- **Validate**: `pytest tests/test_db_in_network_script.py tests/test_conftest_fixtures.py -q`; `pytest tests/test_measure_v1_latency.py -m "not db" --collect-only -q` lists none of the db ones.

### Task 5: Take the measurement

- **File**: none (numbers go into Task 7 and the report)
- **Action**: RUN
- **Implement**: `python scripts/measure_v1_latency.py --runs 50` against the local libSQL (throwaway container, keep-awake on). Record the full report verbatim, including host, python, PII mode and model. If time allows, also run `--pii on` once for context. The README quotes the `off` figures as the overhead and may mention the `on` figure as "the profile difference, not translation".
- **Validate**: exit 0, 50 samples per arm. A `MISSED` is kept and written up as a miss. Do not rerun until it passes.

### Task 6: `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: in `Settings` field order (`app/config.py:240` for `OPENROUTER_BASE_URL`, `:364`/`:368` for the `V1_*` pair), each with comment line(s) directly above:
  - `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`: "Upstream base; /chat/completions is appended. Must be https://, or http:// only on 127.0.0.1/localhost/::1 (the E2E stub). Whoever controls this host receives OPENROUTER_API_KEY (PRD-015 T10), so treat it like the key." Place it beside `OPENROUTER_API_KEY`/`OPENROUTER_TIMEOUT_SECONDS`, wherever field order allows.
  - `V1_ENABLED=true`: "Mount the OpenAI-compatible /v1 routes; false makes /v1/* a 404 and leaves /query unchanged."
  - `V1_SSE_KEEPALIVE_SECONDS=10`: "Seconds between ': keep-alive' lines while a stream: true request waits on the pipeline; > 0 and <= 60."
  - Update the `ADMIN_TOKEN` comment at `.env.example:27` only if it says "will"; check it.
- **Mirror**: `.env.example:75-77`; `tests/test_config.py:64-77`.
- **Validate**: Task 6b's test.

### Task 6b: Pin it

- **File**: `tests/test_config.py`
- **Action**: UPDATE (new test only)
- **Implement**: `test_env_example_documents_the_v1_vars_with_a_comment_in_field_order`, the two existing RBAC tests' pattern merged into one. Also assert the `OPENROUTER_BASE_URL` comment block mentions `loopback`/`127.0.0.1` and `OPENROUTER_API_KEY`, which is the T10 note.
- **Validate**: `pytest tests/test_config.py -q`

### Task 7: README

- **File**: `README.md`
- **Action**: UPDATE
- **Implement** (by section; keep the README's voice: bold lead sentence, plain statements, measured numbers with the command that produced them):
  1. **Features table** (`README.md:148-162`): add an **OpenAI-compatible endpoint** row: `POST /v1/chat/completions` and `GET /v1/models`, one base URL for the OpenAI SDKs, Aider and Continue, `code` profile, every verdict an ordinary 400/403, buffered streaming, link to the new section. Amend **Single entry point** (`/query` *and* `/v1`), **Prompt-injection blocking** (the `assistant` flag), and **PII redaction** ("A `code` profile for coding agents" → reached through `/v1`).
  2. **New section `### OpenAI-compatible endpoint`** under Features, after Usage limits. Move and rewrite the current Roadmap section (`README.md:1030-1045`):
     - What it is (translation layer, no second pipeline, `profile="code"`, `ingress="v1"`). "The full design is in [PRD-015](.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md)", with the one-time note that earlier documents and code comments call it "PRD-014".
     - **Per-client setup**, only from what the E2E reports proved, each with its pinned version:
       - *OpenAI Python SDK* (`openai==3.40.0`, `requirements-e2e.txt`): `OpenAI(base_url="http://localhost:8000/v1", api_key=<harness token>)` / `OPENAI_BASE_URL`+`OPENAI_API_KEY`; default `max_retries` is fine (non-retryable errors carry `x-should-retry: false`, which 3.40.0 honours); streaming + `stream_options={"include_usage": True}`; `harness` via `model_extra`.
       - *Aider* (`aider-chat==0.86.2`): `OPENAI_API_BASE` + `OPENAI_API_KEY`; **`--model openai/openai/gpt-4o`** (litellm strips one `openai/`). Plain `openai/gpt-4o` arrives as `gpt-4o`, which Aider knows, so it sends a trailing `system` reminder that `/v1` refuses with 400 `invalid_messages`. Aider loads `.aider.model.settings.yml` from `HOME` on its own. litellm retries a 403 (~9 times, each one a row). No `tools` are sent in this mode.
       - *Continue* (`@continuedev/cli` 1.5.47): the `config.yaml` block from PRD Section 10 (`provider: openai`, `model` verbatim, `apiBase`, `apiKey`); `cn` **needs `--exclude "*"`**, because without it every prompt is 400 `tools_not_supported`, and `--readonly` is not enough. `cn` loads a `.env` from its cwd. The VS Code extension's Chat mode is not verified (state it).
       - Optional `X-Harness-Device` header (≤128 printable chars).
     - **Operating it**: Caddy routes `/v1/*` (STORY-018); keep-alives every `V1_SSE_KEEPALIVE_SECONDS` arrive through Caddy's `encode gzip` (measured 10/20/30 s). A streamed request queued behind `PIPELINE_MAX_WORKERS` gets no bytes until a worker frees, the same exposure as `/query` (STORY-018 finding). `V1_ENABLED=false` turns it off.
     - **What `/v1` does not do**, a plain list: no tool calling (`tools`/`tool_choice`/`functions` → 400 `tools_not_supported`; `tool` turns refused); no real token streaming (`stream: true` is buffered: the whole response is checked, then sent as one content chunk); no BYOK (`openrouter_api_key` is an ignored unknown key); no model aliasing (`model` must exactly match `MODEL_ALLOWLIST`); `GET /v1/models` lists `MODEL_ALLOWLIST` even for an `admin`, whose wildcard it cannot enumerate; `ADMIN_TOKEN` is never accepted; `n>1`, `logprobs`, `json_object`/`json_schema`, audio/image → 400 `unsupported_parameter`/`invalid_messages`; ignored params (e.g. `seed`) are answered and their names recorded in `ignored_params`; shape refusals write no audit row (T9).
     - **What it costs**: the Task 5 numbers in the Usage-limits voice. Translation p95 against the 10 ms target with **met/missed** stated, end-to-end added p95, PII mode, host, and the command `python scripts/measure_v1_latency.py --runs 50`.
  3. **Pattern policy** (`README.md:227-237`): `code` row → `assistant` **flag**. Replace the "`assistant` is not inspected" bullet with a two-profile statement: not inspected under `chat`, flagged under `code` (D9, PRD Section 7.8 rationale: an injection written into a caller-supplied `assistant` turn is recorded, not blocked, because real history quotes such phrases). Rewrite "In this release the flag is reachable by tests only": the `tool` flag is still unreachable (the pipeline refuses `tool` turns until tool calling, PRE-PRD-016); `code` *is* reachable through `/v1`. Fix the PRD numbers: "Action policy rules (PRD-015)" → the PRE-PRD-015 brief, "tool calling ships (PRD-016)" → PRE-PRD-016, the endpoint "(PRD-014)" → link to the new section.
  4. **PII redaction** (`README.md:290-310`): "the server chooses the profile" → `/v1` runs `code`. Replace "In this release `code` is reached by direct call only" with the shipped state. Add the rollout note pointing at [PRD-012 D5-placeholders](.agents/PRDs/PRD-012-pii-for-code/decisions/D5-placeholders.md) (fixed placeholders in files an agent reads). Same PRD-number fix for tool calling.
  5. **Usage limits** (`README.md:375`) and **Environment Variables** `ADMIN_TOKEN` row (`:577`): "the OpenAI-compatible endpoint PRD-014 will add" → link to the shipped section. Add a sentence that `/v1` answers a usage limit with 403 `usage_limit_exceeded` (never 429), next to the existing `/query` sentence.
  6. **Environment Variables table**: rows for `OPENROUTER_BASE_URL` (with the T10 sentence), `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, in the `.env.example` order.
  7. **API Reference** (after `GET /stats`, `README.md:826`): `### POST /v1/chat/completions — success` (PRD 7.4 body, `X-Harness-Audit-Id`), `— streamed` (PRD 7.6 event sequence: keep-alive, content chunk, finish chunk, usage chunk with `include_usage`, `[DONE]`; the post-commit error event; no audit-id header), `— errors`: **one table with every row of PRD Section 7.5** (status, `type`, `code`, retried?) plus one example error body with `harness` and the `x-should-retry: false` rule. Then `GET /v1/models` and `GET /v1/models/{id}` (404 `model_not_found`). Check each code against `app/services/v1_translate.py`/`app/routers/v1.py` rather than the PRD alone. If the shipped code differs from the PRD, the README describes the code and the difference goes in the report.
  8. **Running Tests**: a short "Client E2E (opt-in)" paragraph: `pip install -r requirements-e2e.txt`, `HARNESS_E2E_LIBSQL_URL=... pytest tests/e2e -m e2e --run-e2e -v`, `HARNESS_E2E_AIDER` / `HARNESS_E2E_CONTINUE` for the two optional clients (check exact env names in `tests/e2e/test_aider.py` / `test_continue.py`). Update `:929` for the new deselected tests.
  9. **Roadmap**: add `- [x] [OpenAI-compatible endpoint](#openai-compatible-endpoint) — ...` to Shipped, remove it from Planned, delete the old Roadmap subsection (now under Features). Fix "The only ingress that exists today is `POST /query`" (`:1028`), and the MCP section's first sentence if it reads as future. Optionally add a Planned line for tool calling (Milestone 2).
  10. **Table of Contents** (`README.md:23-45`): add the new section and API Reference entries; anchors must resolve.
  11. Sweep: `grep -n -i "PRD-014\|will add\|reachable by tests only\|direct call only\|no HTTP ingress" README.md`. Every remaining hit is either the one intentional "called PRD-014" note or a PRD-014 test-suite reference (`.agents/spikes/PRD-014-...`, which is correct).
- **Validate**: the grep above; a Markdown anchor check (every `](#...)` in README matches a heading slug; a throwaway one-liner script in the scratchpad, not committed); `pytest tests/test_config.py -q`.

### Task 8: Close the PRD

- **Files**: `pre-prds/README.md`, `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md`, `index.md`, the story file
- **Action**: UPDATE
- **Implement**: `pre-prds/README.md:34`: Milestone 1 marked reached (2026-10-30, PRD-015, with the note that it is called PRD-014 there). PRD frontmatter `status: draft` → `done` (check how PRD-013's frontmatter says it; use the same word), `updated`. Regenerate `index.md`: 19/19, 100%, board status. Story frontmatter `status: done`, `report`, `commit` at the end of `/implement`.
- **Validate**: `grep -n '^status' .agents/PRDs/PRD-01[3-5]*/PRD.md` is consistent.

### Task 9: Final sweep

- **File**: none
- **Action**: RUN
- **Implement**: repeat Task 1 steps 1–2 on the finished tree (new tests included). Record counts in the report next to the baseline.
- **Validate**: green; new tests are `db`/not-`db` as intended (`-m "not db"` with Docker stopped collects and passes the pure ones).

---

## End-to-End Tests

- [ ] `python scripts/measure_v1_latency.py --runs 50` against local libSQL → exit 0, report with three arms, both verdict lines; figures copied verbatim into the README and the report
- [ ] `python scripts/measure_v1_latency.py --database-url https://example.turso.io` → exit 1, "Refusing to write to a non-local database", no traceback
- [ ] After a run: `scripts/manage_users.py list-users` shows the `story019-bench-*` user inactive; its audit rows are `ingress='query'`/`profile='chat'` and `ingress='v1'`/`profile='code'`, `streamed=False`, `success=True`
- [ ] Copy-paste check of the README's OpenAI SDK snippet against a running harness on the stub (`OPENROUTER_BASE_URL=http://127.0.0.1:<port>/v1`): non-streamed and streamed answers come back. The Aider/Continue snippets are not rerun; they are the STORY-016/017 commands, quoted from their reports
- [ ] `curl -s -H "Authorization: Bearer <token>" localhost:8000/v1/models` matches the README example's shape

---

## Validation

```bash
pytest tests/ -m "not db" -q                                     # Docker stopped
HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:<port> pytest tests/ -q  # throwaway libSQL
pytest tests/test_measure_v1_latency.py tests/test_config.py tests/test_db_in_network_script.py -v
python scripts/measure_v1_latency.py --runs 50
grep -n -i "PRD-014\|will add\|reachable by tests only\|direct call only" README.md
```

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| End-to-end delta is dominated by libSQL/stub jitter (two ~8 ms round trips per request, README:377), so a 50-sample p95 difference is noisy and can go either way | Interleaved, alternating arm order; translation-only arm measured with no I/O; README reports both and says which one the PRD target is on |
| Profile difference (`chat` NER vs `code` patterns) swamps translation | `--pii off` default, documented; `--pii on` available |
| Repeated prompt becomes a duplicate (cross-ingress dedup) or hits the 60/min rate | Per-request nonce suffix; per-user `requests_per_minute` override |
| Developer `.env` (PORT, allowlist, base URL) leaks into the bench (memory: `.env` PORT override, `DATABASE_URL` leak at collection) | Base URL assigned after the stub binds; model taken from the loaded allowlist; `DATABASE_URL` saved/restored around the test import, as the mirror does |
| Audit rows left behind | Local-only guard; deactivated, nonce-suffixed bench user; docstring states it |
| README describes the PRD instead of the code | Task 7.7 checks every code/status against `v1_translate.py`/`v1.py`; differences go in the report |
| Docker Desktop dies on host sleep mid-sweep | Keep-awake + throwaway container recipe from the memory notes; rerun only the affected `db` subset, classified by the verdict line |

---

## Acceptance Criteria

(Copied from story `STORY-019`)

- [ ] Given the full suite (`-m "not db"` without Docker, then with the libSQL container), when it runs, then the `/query` outcome regression, chat UI regression, console suites and `tests/test_v1_query_isolation.py` pass with no pre-existing assertion changed except those listed in STORY-008's report.
- [ ] Given a measurement script run against the stub upstream (50 runs, the same conversation via `/query` and via `/v1`), when it reports, then `/v1`'s added p95 overhead is recorded in the README; under 10 ms meets the PRD target, and a miss is recorded as such, not hidden.
- [ ] Given the README, when it is read, then "OpenAI-compatible endpoint" has moved from Roadmap > Planned to Features; the API Reference has `POST /v1/chat/completions` (success, streamed, every error code in PRD Section 7.5), `GET /v1/models`; per-client setup for the OpenAI SDK, Aider and Continue uses the settings proven in STORIES 015–017; and the "what `/v1` does not do" list (tools, real streaming, BYOK, aliasing, the admin wildcard in `/v1/models`) is stated plainly.
- [ ] Given the README sections that say `code` or the `assistant`/`tool` flag are "reachable by tests only" or that `/v1` "will" exist (Pattern policy, PII redaction, Usage limits), when read, then they describe the shipped state, including `assistant: flag` (D9).
- [ ] Given `.env.example`, when read, then `OPENROUTER_BASE_URL`, `V1_ENABLED` and `V1_SSE_KEEPALIVE_SECONDS` are present with defaults and one-line explanations, and `OPENROUTER_BASE_URL` notes the T10 rule.
- [ ] All tasks completed
- [ ] Backend server starts without error (`TestClient(app)` lifespan in the bench and the suite)
- [ ] Follows existing patterns (`measure_usage_latency.py`, its test, `_DB_NODEIDS` + in-network deselect pairing)
