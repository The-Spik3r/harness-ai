---
story: STORY-014
prd: PRD-020
slug: local-model-e2e
title: Opt-in end-to-end run against a real local OpenAI-compatible server
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Opt-in end-to-end run against a real local OpenAI-compatible server

## Summary

One opt-in E2E module drives a real harness subprocess (file-mode registry, keyless `local` provider) against the user's LM Studio-style server at `http://localhost:1235/v1`, model `google/gemma-4-e4b`: a `/query` answer, an OpenAI-SDK `/v1` call (streamed to the client, buffered by the harness) and one forced `/v1` tool call released through the action policy. A small helper module holds the pure parts (env resolution, reachability probe, server-facts probe, registry YAML) so they get ordinary unit tests that run in the default suite. The module writes `local-model-run.json` (server facts + whether `usage` was real or estimated) for the implementer's report.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-014-local-model-e2e.md` (ACs amended: `ollama` -> `local`, Ollama defaults -> LM Studio ones; see Design Decisions)
- PRD sections used: Section 8 (E2E row), Section 11 (E2E bullet), Section 15 (not verified: server shapes), D16, D5, D7, D8, F1
- Systems affected: tests only (`tests/e2e/`, one unit test file); no `app/` change

## Design Decisions

- **Env vars (binding)**: `HARNESS_E2E_LOCAL_BASE_URL` (default `http://localhost:1235/v1`) and `HARNESS_E2E_LOCAL_MODEL` (default `google/gemma-4-e4b`). Defaults are the documented example, never the only option. The old Ollama default `http://127.0.0.1:11434/v1` is dropped.
- **Provider named `local`** in the written registry: keyless (no `key_env`), `trust: internal`, `usage_missing: estimate`, `timeout_seconds: 300` (cold model load), `models: [{id: <model>, capabilities: {tools: true, streaming: true}}]`, `default_model: <model>`. No `pii: relaxed` (the story names only trust and estimate; not needed). Every AC row check is `provider == 'local'`, `provider_trust == 'internal'`. **Amend the story AC text** (AC1 "default Ollama ... `provider='ollama'`" -> LM Studio defaults and `provider='local'`; AC5 "server version / model digest" -> "what the server exposes") and note the amendment in the report.
- **Skips, never failures** (AC4): a module-scoped fixture `local_server` does the probe and `pytest.skip`s with a reason naming what is missing: `--run-e2e` absent (existing conftest skip, `tests/conftest.py:193-216`); server unreachable (`GET {base_url}/models` connect/timeout error: name the URL and the env var); model absent (id not in `/models` `data[].id`: name the model, the env var and the ids that are listed). `harness` depends on `local_server` as its FIRST argument so the skip happens before any child starts. A missing `HARNESS_E2E_LIBSQL_URL` stays what every other E2E does (`_live.resolve_e2e_db_url` fails with the docker recipe, `tests/e2e/_live.py:155-162`): it is an environment error of the harness, not of the model server.
- **Small-model tool call, not flaky-by-design**: ONE trivial tool `read` (param `filePath`, the name/param the built-in action mapping already knows, rule `fs.read` -> allow, `app/services/action_config.py:292`), `tool_choice` forcing it (`{"type":"function","function":{"name":"read"}}`; the harness forwards it with tools, `app/services/v1_translate.py:432-471`), `temperature: 0`, `max_tokens: 128`, non-streamed. **Fail only on harness errors**: a non-2xx from the harness, a malformed/missing audit row, a missing action-decision row for a call the response did carry. **`pytest.skip("model returned no tool call")`** when the 200 response has no `tool_calls` (the model declined; the harness did nothing wrong). If the server rejects the forced `tool_choice` (a 4xx whose audit `error_message` names it), the implementer retries once WITHOUT `tool_choice` and records the server quirk in the report (PRD risk 2: quirks go to docs, not code); same skip rule applies.
- **Usage recorded, not asserted real**: the row's `usage_estimated` and the SDK/`/query` usage are recorded as `usage_reported: "real" | "estimated"`. The assertions hold either way (`tokens_used > 0`).
- **Server facts** (AC5), best effort, never failing a test, each in a try/except: root = `base_url` minus the trailing `/v1`. (1) `GET {root}/api/version` (Ollama: `version`); if 200 also `GET {root}/api/tags` and take the entry whose `name`/`model` equals the model: `digest`. (2) else `GET {root}/api/v0/models` (LM Studio: the entry with `id == model`: `arch`, `quantization`, `compatibility_type`, `state`, `max_context_length`; no digest, no version). (3) else the literal `"not exposed"`. Orchestrator verified this server is LM Studio (`/api/version` is "Unexpected endpoint"; `/v1/models` lists `google/gemma-4-e4b` and an embedding model).
- **Keys never leak**: keyless provider, `OPENROUTER_API_KEY` not set in the child env (file mode does not need it, `app/config.py:762`); the harness token is never printed; `rows.json`-style output keeps the `_REPORT_FIELDS` allowlist (no prompt, no answer).
- **Memory**: no parallel pytest; the live run is the new test files only.

---

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no `chat_ui/` change).

---

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Opt-in marker | `tests/conftest.py:170-174,186,193-216`; `pytestmark = pytest.mark.e2e` as `tests/e2e/test_openai_sdk.py:44` | `--run-e2e` skip; no new option or marker |
| Fixtures | `tests/e2e/test_openai_sdk.py:80-139` | `e2e_db_url`, `child_cwd`, `child_env`, `run_child`, `users`, `harness` (all module-scoped, children only touch storage) |
| Rows/actions | `tests/e2e/test_opencode.py:100-102,223-262` | `_REPORT_FIELDS`, `rows()`, `actions()` via `_live.dump_rows` / `_live.dump_action_decisions` (`_live.py:196-210`) |
| Run nonce / row deltas | `test_openai_sdk.py:57,177-194` | `NONCE` in every prompt (duplicate checker), `new_rows(label)` deltas |
| Registry YAML | `tests/_providers.py:21-26` (`write_registry`), PRD F1 `ollama` block | write `providers.yaml` under `child_cwd`; pass `PROVIDERS_FILE=<path>` to the child (the harness is a subprocess, so `providers_file(...)` itself, which loads in-process, is used only in the unit test) |
| Harness env | `test_opencode.py:195-209` | `RBAC_ENABLED`, `V1_ENABLED`, `V1_TOOLS_ENABLED=true`, `USAGE_REQUESTS_PER_MINUTE="*=unlimited"`; NOT `MODEL_ALLOWLIST`/`V1_TOOL_MODELS` (a set `V1_TOOL_MODELS` with a file is a startup error, `app/config.py:780`) |
| /query call | `tests/e2e/docker_smoke_probe.py:40-41,186-192` | `POST /query {"prompt", "model"}` with `Authorization: Bearer <token>` -> `response` |
| Unit tests with a tiny server | `tests/e2e/_live.py:374-428` (`ThreadingHTTPServer` on port 0) | free port, daemon thread, shutdown in `finally` |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e/_local_model.py` | CREATE | Pure/helper side: `local_config()` (env + defaults), `probe(base_url, model, get=httpx.get)` returning `(ok, reason)`, `server_facts(base_url, model)`, `registry_yaml(model, base_url)`, constants |
| `tests/e2e/test_local_model.py` | CREATE | The opt-in E2E (3 live tests + facts record) |
| `tests/test_local_model_e2e_helpers.py` | CREATE | Default-suite unit tests of the helpers (no `--run-e2e`, no model server) |
| `.agents/stories/PRD-020-provider-registry/STORY-014-local-model-e2e.md` | UPDATE | AC text amended (see above); frontmatter plan/status |
| `.agents/PRDs/PRD-020-provider-registry/index.md` | UPDATE | regenerated |
| `.agents/reports/PRD-020-provider-registry/STORY-014-local-model-e2e.report.md` | CREATE (implementer) | live-run facts (AC5) |

---

## Tasks

Execute in order.

### Task 1: Helper module

- **File**: `tests/e2e/_local_model.py`
- **Action**: CREATE
- **Implement**: constants `ENV_BASE_URL`, `ENV_MODEL`, `DEFAULT_BASE_URL`, `DEFAULT_MODEL`, `PROVIDER = "local"`. `probe` GETs `{base_url}/models` (timeout 5 s, catches `httpx.HTTPError`), returns `(False, "<what is missing>")` for unreachable (name URL + `ENV_BASE_URL`), non-200, or model not listed (name model, `ENV_MODEL`, and the listed ids); `(True, "")` otherwise. `server_facts` follows the Design Decisions order and returns a JSON-able dict `{"server": "ollama"|"lm-studio"|"not exposed", "version", "digest", "model_info": {...}}`; every request in try/except, a malformed body is "not exposed", never raises. `registry_yaml` returns the YAML text of the Design Decisions block (single `local` provider, `version: 1`).
- **Mirror**: `tests/e2e/_live.py` (module docstring style, no fixtures in the helper file); `examples`/PRD F1 YAML keys exactly (`strict_yaml` refuses unknown keys, `app/services/provider_registry.py:67-73`).
- **Validate**: Task 2.

### Task 2: Unit tests of the helpers (run in the default suite)

- **File**: `tests/test_local_model_e2e_helpers.py`
- **Action**: CREATE
- **Implement**: (a) `registry_yaml` loads through `tests/_providers.providers_file(tmp_path, ..., monkeypatch=monkeypatch)`: provider `local`, `trust == "internal"`, `usage_missing == "estimate"`, keyless (`api_key_for("local") is None`), model catalogued, `default_model` set; (b) `probe` against an in-process `ThreadingHTTPServer` on a free port: listed model -> ok; model missing -> reason names the model and the env var; closed port -> reason names the URL; (c) `server_facts` against the same tiny server serving `/api/v0/models` -> `lm-studio` + `quantization`, and serving nothing -> `"not exposed"`; (d) `local_config()` defaults equal the two documented values and honour env overrides (`monkeypatch.setenv`). No `db` fixtures, so it is not a `db` test.
- **Mirror**: `tests/_providers.py:29-46`; server thread pattern `tests/e2e/_live.py:453-465`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_local_model_e2e_helpers.py`

### Task 3: The E2E module

- **File**: `tests/e2e/test_local_model.py`
- **Action**: CREATE
- **Implement**: docstring in the house style (ACs, how to run, what is recorded). Fixtures: `local_server` (probe, skip with reason; yields config + facts), `e2e_db_url`, `child_cwd`, `child_env`, `run_child`, `users` (`main`), `registry_path` (write `registry_yaml` under `child_cwd`), `harness(local_server, users, registry_path, ...)` with env `PROVIDERS_FILE`, `RBAC_ENABLED=true`, `V1_ENABLED=true`, `V1_TOOLS_ENABLED=true`, `USAGE_REQUESTS_PER_MINUTE="*=unlimited"`, `OPENROUTER_API_KEY=""`; `rows`/`actions` as the precedents, plus a `run_facts` dict fixture written to `child_cwd/local-model-run.json` (+ a terminal line with the path) at teardown. Tests:
  1. `test_query_is_answered_and_the_row_names_local` (AC1): `POST /query` with a nonce prompt, `model` = env model, `max_tokens` not sent; 200, non-empty `response`; one new row: `provider == "local"`, `provider_trust == "internal"`, `success`, `model_used == model`, `tokens_used > 0`; record `usage_estimated`.
  2. `test_sdk_v1_streamed_to_client_is_answered_and_the_row_names_local` (AC2): `openai.OpenAI(base_url=f"{harness.base}/v1", api_key=token)`, `stream=True`, `stream_options={"include_usage": True}`, `temperature=0`, `max_tokens=64`; reassembled text non-empty; one row: `ingress == "v1"`, `streamed is True`, `provider == "local"`, `success`; record usage real/estimated from `row["usage_estimated"]`.
  3. `test_v1_tool_call_is_released_through_the_action_policy` (AC3): as Design Decisions. Asserts: 200; skip when no `tool_calls`; `tool_calls[0].function.name == "read"`; row `has_tool_calls is True`, `provider == "local"`; one new `actions` row for the call: `tool_name == "read"`, `decision == "allow"`, `rule == "fs.read"`, `audit_id == row["id"]`, `tool_call_id == tool_call.id`.
  4. `test_zz_facts_recorded`: writes the facts (server facts, usage real/estimated per test, rows count) into `run_facts` and asserts the dict has the keys the report needs (so AC5 cannot silently omit one).
- **Mirror**: `test_openai_sdk.py:80-194` (fixtures), `:243-250` (row/audit-id relation), `test_opencode.py:430-445` (action rows joined by `audit_id`).
- **Validate**: Task 5 live run.

### Task 4: Story/AC text and static checks

- Edit the story ACs 1 and 5 as in Design Decisions (done by the planner; implementer keeps them).
- `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 5: The live run (AC5 evidence)

The server at `localhost:1235` is up now. Start the throwaway libSQL, run ONLY the new files in ONE pytest process (no parallel pytest; the user's machine is memory limited while a model is loaded), then remove it:

```bash
docker run -d --name harness-libsql-e2e020-014 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 PYTHONUTF8=1 .venv/Scripts/python -m pytest -p no:cacheprovider \
  tests/e2e/test_local_model.py tests/test_local_model_e2e_helpers.py -m "e2e or not e2e" --run-e2e -v -s
docker rm -f harness-libsql-e2e020-014
```

(`-m` can be left out: it is only there to say both files run.) Optional defaults check: unset `HARNESS_E2E_LOCAL_*` for the run, so the defaults are exercised. Also run once WITHOUT `--run-e2e` (the e2e tests report skipped) and once with `HARNESS_E2E_LOCAL_MODEL=no-such-model` (skipped with the model reason). Capture `local-model-run.json` into the report: server (LM Studio), the `/api/v0/models` fields, `usage_estimated` per path, the tool-call outcome (called / skipped), and any forced-`tool_choice` quirk. If the live run fails for a harness reason, fix the cause (do not weaken an assertion), and report plainly.

---

## End-to-End Tests

- [ ] `/query` answered by the real model, row `provider='local'` (AC1)
- [ ] OpenAI SDK `stream=True` answered, row `ingress='v1'`, `streamed`, `provider='local'` (AC2)
- [ ] forced `read` tool call released, one `action_decisions` allow/`fs.read` row joined by `audit_id` (AC3)
- [ ] no `--run-e2e` / unreachable / model missing -> skipped with a reason (AC4; unit tests for probe, plus the two manual variants in Task 5)
- [ ] `local-model-run.json` + report hold server facts and usage real/estimated (AC5)

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# default-suite part (no live server needed), then the live run of Task 5; one pytest at a time
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_local_model_e2e_helpers.py tests/test_e2e_live.py
```

`tests/test_e2e_live.py` is included because `_live.py` is imported, not edited (no change expected; run only to prove it). `test_untouched_app.py` is not needed: nothing under `app/` changes. No test is renamed or removed.

---

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 `/query` answered, row `provider='local'` (amended) | 1, 3 | `tests/e2e/test_local_model.py::test_query_is_answered_and_the_row_names_local` |
| AC2 `/v1` via OpenAI SDK (streamed-to-client, buffered) | 3 | `...::test_sdk_v1_streamed_to_client_is_answered_and_the_row_names_local` |
| AC3 tool call released through the action policy and recorded | 3 | `...::test_v1_tool_call_is_released_through_the_action_policy` |
| AC4 skipped, never failed, reason names what is missing | 1, 2, 3 | `tests/test_local_model_e2e_helpers.py` probe tests; `local_server` fixture; Task 5 manual variants |
| AC5 report records server facts + usage real/estimated | 1, 3, 5 | `...::test_zz_facts_recorded` + the report from `local-model-run.json` |

## Open risks

- LM Studio may reject forced `tool_choice` or return `arguments` as an object: handled by the one retry/skip rule and recorded (PRD risk 2); the harness error path is the thing under test, so a harness-side failure is a real finding.
- `trust: internal` on the hostname `localhost` is a loopback host (`app/config.py:97`), so no D7 warning/refusal expected; verify in the live run.
- A role/RBAC default may hide the model from a plain `user`; if `/v1/models` or the call 403s, create the user with the role the registry allows rather than loosening the registry.
- Model latency: first request loads the model; per-request client timeout 300 s, harness `timeout_seconds: 300`.
