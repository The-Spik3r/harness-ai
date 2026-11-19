---
story: STORY-014
prd: PRD-021
slug: opencode-realtime-e2e
title: OpenCode end-to-end on a real-time stream
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-19
---

# Plan: OpenCode end-to-end on a real-time stream

## Summary

A second opt-in OpenCode module, `tests/e2e/test_opencode_realtime.py`, runs the real OpenCode against a harness with `STREAMING_ENABLED=true`, a file-mode registry (`streaming: true, reasoning: true`; legacy mode never streams, OD1) and an `RBAC_ROLES_FILE` granting `stream:realtime` (and `reasoning:view` to a second role). The stub replies carry STORY-004's `stream` shape so text and `DROP TABLE` arguments arrive fragmented. `_live.Recorder` gets an additive, opt-in capture of the client-facing SSE (with arrival times): the harness-side proof for AC2/AC3. A fast non-e2e test pins the rendered script, registry, roles and SSE helpers. `test_opencode.py` is not touched.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-014-opencode-realtime-e2e.md`
- PRD sections: 6.5, 6.6, F6, F10, Risk 4, user story 5 (D6, D9, D17)
- Systems: tests only (`tests/e2e/`, one fast test). No `app/` change.

## Design Decisions (binding, from the orchestrator)

- Every live test `@pytest.mark.e2e`; reuse `_live.py` / `_opencode.py` helpers and `test_opencode.py` patterns; existing module unchanged.
- Real time proven from the harness side: each audit row has `streamed_realtime is True` and `completion_id` starting `chatcmpl-harness-rt-` (and equal to the SSE chunk `id`, D17); a buffered fallback fails the test.
- Stub replies use `stream: {chunk_chars: 6..8, delay_ms: 60}`; the reasoning reply adds `reasoning` with a nonce sentinel.
- AC2: recorder SSE shows no `tool_calls` delta for the denied call and no argument fragment outside the denial note; one deny `action_decisions` row.
- AC3: sentinel never in a workspace file, assistant `content` (SSE content deltas, OpenCode `text` events) or audit rows. Whether OpenCode displayed it is only observed and printed with `_say`.
- OpenCode version recorded (`opencode --version`: 2.3.2 on this machine).

Deviations to expect (tell the orchestrator):
- `tests/e2e/_live.py` is UPDATED (opt-in Recorder SSE capture, default byte-identical): the recorder keeps no response today (`_live.py:384-406`).
- `test_opencode.py:385` pins `v2.0.10`; installed OpenCode is 2.3.2, so that test likely already fails here. Do not touch it; report its real result; the new module asserts no version.
- `manage_users.py:29` limits `--role` to `admin|auditor|user`: a custom role cannot be created by the CLI. The roles file replaces the matrix wholesale (`authz.py:119-146`), so redefine `user` (realtime only) and `auditor` (query + audit own + both grants) and create users with those roles. Say so in the module docstring.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`).

## Patterns to Follow

| Category | Source | Mirror |
|---|---|---|
| Fixtures (db, users, workspace, stub, harness, recorder, rows, actions, oc_home, runner) | `tests/e2e/test_opencode.py:110-377` | copy the shape (each e2e module owns its fixtures); users via `_live.create_user(run_child, id, role)` (`_live.py:186`) |
| OpenCode env/command | `test_opencode.py:279-306`, `:345-377` | same `_oc_env`, `run_tree`, `--format json` event parsing |
| Pure helpers | `tests/e2e/_opencode.py:52-97` | `render_script`, `opencode_config`; import `HARNESS_MODEL`, `OPENCODE_MODEL`, `DENIAL_NOTE_TEMPLATE`, `policy_yaml`, `repo_root_text`, `CALC_ORIGINAL` from it |
| File-mode registry | `tests/e2e/_local_model.py:109-127`; harness env `test_local_model.py:140-152` | `PROVIDERS_FILE`, `OPENROUTER_API_KEY=""`, no `V1_TOOL_MODELS`/`MODEL_ALLOWLIST`; capabilities `{tools: true, streaming: true, reasoning: true}`; base_url from `stub.base` (check which path prefix the stub serves, `_live.py:241`) |
| Fast script test | `tests/test_e2e_opencode_script.py:30-130` | `parse_script(json.loads(render))`, `select_request(Request.from_body(...))` |
| Denial note | `app/services/tool_release.py:41` | the note quotes the policy `reason` (`action_classifiers/sql.py:239`): assert on fragments, not a raw substring |
| `stream` shape | `scripts/stub_openrouter.py:72-80, 297-318` | `chunk_chars, delay_ms, reasoning, fail_after` on a rule's reply |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `tests/e2e/scripts/opencode_realtime.json` | CREATE | stub script, three scenarios, `@REPO@` / `@SENTINEL@` placeholders |
| `tests/e2e/_opencode_realtime.py` | CREATE | pure helpers (no env, no process, no `app` import) |
| `tests/e2e/_live.py` | UPDATE | `Recorder(..., keep_sse=False)`: opt-in capture of the relayed SSE |
| `tests/e2e/test_opencode_realtime.py` | CREATE | live tests (AC1-AC4) |
| `tests/test_e2e_opencode_realtime_script.py` | CREATE | fast tests of helpers and script |

## Tasks

### Task 1: Recorder SSE capture (`_live.py`)
In `_relay` (`:384-406`), when `recorder.keep_sse`, append `(seconds since request start, payload)` for every `data:` line to `entry["sse"]` (list; `None` when off); constructor arg `keep_sse=False`, documented beside `keep_tool_names`. Relayed bytes and `keepalives` unchanged. Add a unit test to `tests/test_e2e_live.py` if it already tests the recorder.
Validate: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_e2e_live.py`

### Task 2: Script `opencode_realtime.json`
Same vocabulary as `tests/e2e/scripts/opencode.json` (`regex`, `last_role: user`, `advertises`, `tool_calls`) plus `stream`:
1. `E2E-RT-DROP`: one `shell` call, id `call_rt_drop`, arguments `{"command":"sqlite3 app.db \"DROP TABLE users\""}`, short `content` ("Cleaning up the database now.") so text streams before the held call; `stream {chunk_chars: 6, delay_ms: 60}`.
2. `E2E-RT-TEXT`: 3+ sentences containing `E2E-RT-ANSWER`, no call (OpenCode stops on text); `stream {chunk_chars: 7, delay_ms: 60}`.
3. `E2E-RT-REASON`: content containing `E2E-RT-REASONED`; `stream {chunk_chars: 8, delay_ms: 60, reasoning: "Thinking about @SENTINEL@ before answering. It stays private."}`.
`advertises: shell` was written for 2.0.10; if 2.3.2 advertises other names, adapt (`recorder.posts()[i]["tool_names"]`). Same for argument keys.

### Task 3: Helpers `_opencode_realtime.py`
- `render_script(repo_text, sentinel)`: replace both placeholders, `json.loads` check (mirror `_opencode.py:52-61`).
- `registry_yaml(base_url)`: one internal keyless provider, model `HARNESS_MODEL`, capabilities all true (`_local_model.py:109`).
- `roles_json()`: built-in `admin` as literals; `user` = `query:submit, audit:read:own, stream:realtime`; `auditor` = `query:submit, audit:read:own, stream:realtime, reasoning:view`. A fast test ties the literals to `authz.PERMISSION_*`.
- `opencode_config(base_url, token, reasoning_key)`: start from `_opencode.opencode_config` (not edited), add `reasoning: true` and the pinned reasoning field to the model (Task 3b).
- `parse_sse(entry["sse"])` -> chunks `{t, id, content, reasoning, tool_calls, finish_reason, raw}`, `[DONE]` handled.
- `argument_fragments(arguments, size)`: the stub's cuts of the arguments (verify the cutting rule in `scripts/stub_openrouter.py` near `:546-560`).

### Task 3b: Pin OpenCode's reasoning field (finding goes in the report)
STORY-001 left the custom-provider default inconclusive. In 2.3.2 the binary's schema has `Model.ReasoningField` = `reasoning | reasoning_content | reasoning_text` under a model's `compatibility` (`reasoningField` internal, `reasoning_field` in the catalog JSON). Attempts, in order: (1) WebFetch OpenCode's docs (`https://opencode.ai/docs/providers`, `/config`, `/models`) for the user-facing key (older docs: model `interleaved: {"field": "reasoning_content"}`); (2) put the candidate in `OPENCODE_CONFIG_CONTENT`, run `opencode run` once against a stub and see whether the config is rejected (strict schema errors name the key). Use the first accepted key with value `reasoning_content` (O5: the harness emits only that). None accepted: keep the default and say so in docstring and report. Report: key used, docs URL, whether OpenCode displayed reasoning.

### Task 4: Live module `test_opencode_realtime.py`
- Docstring: ACs, scenarios, role trick, run command. `pytestmark = pytest.mark.e2e`; NONCE; recipes as `test_opencode.py:86-94`.
- Users, one per scenario: `text`, `drop` (role `user`), `reason` (role `auditor`).
- Harness env: `child_env(PROVIDERS_FILE, RBAC_ENABLED=true, RBAC_ROLES_FILE, STREAMING_ENABLED=true, V1_ENABLED=true, V1_TOOLS_ENABLED=true, ACTION_POLICY_FILE, OPENROUTER_API_KEY="", USAGE_REQUESTS_PER_MINUTE="*=unlimited")`; files written under `child_cwd` first. `test_real_time_is_on_for_the_harness_child` asserts the env holds `STREAMING_ENABLED == "true"` and that the roles file grants `stream:realtime`.
- `recorder = _live.Recorder(harness.base, keep_tool_names=True, keep_sse=True)`.
- `opencode_runs` fixture: `opencode --version` into `opencode-run.json` and `_say`; provider config (token masked) incl. the reasoning key.
- Shared `_assert_real_time(run, rows)`: per row `streamed_realtime is True`, `completion_id.startswith("chatcmpl-harness-rt-")`; SSE chunk ids equal that `completion_id`; role chunk first, `[DONE]` last; no `harness` key in any chunk. Add the two columns to the report-field tuple.
- **AC1** `test_the_answer_text_streams_in_pieces`: exit 0; `run.texts` has `E2E-RT-ANSWER`; no error events; >= 3 content deltas; first content chunk arrives >= 0.2 s before `[DONE]`; one request; `_assert_real_time`.
- **AC2** `test_a_denied_drop_table_never_leaves_in_pieces`: the existing drop assertions (`test_opencode.py:450-474`: exit 0, `tool_uses == []`, db row survives, git status unchanged, one request); from the SSE: no chunk has `tool_calls`, no `function`/`arguments` key in any payload; remove the exact note (`DENIAL_NOTE_TEMPLATE` with the row's `reason`) from the joined content and assert the remainder holds none of `DROP TABLE`, `sqlite3`, `app.db`, nor any `argument_fragments` piece of length >= 5; the finish chunk is last; one `action_decisions` row `(deny, sql.ddl, shell, call_rt_drop)` joined by `audit_id`; the note reaches OpenCode (`run.texts`, whitespace-normalised); `_assert_real_time`.
- **AC3** `test_reasoning_is_shown_live_and_never_written_down`: sentinel `RSN-<NONCE>`; exit 0. Hard: SSE `reasoning_content` deltas concatenate to include the sentinel (proves grant plus real time, D9); no content delta, no `run.texts` entry, no file under the workspace (walk all bytes), no audit-row JSON contains it; row `reasoning_shown is True`. Observed only: whether the sentinel appears in OpenCode's events or output; `_say` it and store `reasoning_displayed` in `opencode-run.json`.
- Last test `test_zz_every_row_is_v1_code_and_real_time` (mirror `:482-490`).

### Task 5: Fast test `tests/test_e2e_opencode_realtime_script.py`
Style of `tests/test_e2e_opencode_script.py` (env defaults at top). Cover: script parses and triggers select their rules; each rule has `chunk_chars <= 8`, `delay_ms > 0`; `call_rt_drop` arguments cut into >= 4 fragments; sentinel only in `reasoning` and substituted; policy denies the drop (`sql.ddl`); `registry_yaml` via `tests/_providers.providers_file` gives `streaming` and `reasoning` true; `roles_json` through `authz.load()` (monkeypatch `settings.RBAC_ROLES_FILE` and `authz.ROLE_PERMISSIONS` so they restore): `user` holds realtime not reasoning, `auditor` both; `parse_sse` on a synthetic stream; denial template equals `tool_release.DENIAL_NOTE_TEMPLATE`. AC4 default skipping is covered by `tests/test_e2e_marker.py` plus the run below.

## End-to-End Tests (local run is the only proof; CI skips e2e)

```bash
docker run -d --name harness-libsql-e2e021-014 -p 8089:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8089 \
HARNESS_E2E_OPENCODE="$APPDATA/npm/node_modules/@opencode/cli/bin/opencode.exe" \
  PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_opencode_realtime.py -m e2e --run-e2e -v -p no:cacheprovider
docker rm -f harness-libsql-e2e021-014
```
- Run the module once without `--run-e2e`: all tests skip (AC4).
- Run `tests/e2e/test_opencode.py` the same way, sequentially, to show the non-realtime path is intact; report the real result (the pinned-version test is expected to fail on 2.3.2, pre-existing; do not edit it).
- Report outcome, `opencode --version`, the reasoning-field finding and the display observation. If 2.3.2 needs script changes, change only the new script/helpers.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_e2e_opencode_realtime_script.py tests/test_e2e_opencode_script.py tests/test_e2e_live.py tests/test_e2e_marker.py tests/test_untouched_app.py
```
No `app/` change, no renamed tests. One pytest at a time. Leave no container, harness, stub or OpenCode process running.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|---|---|---|
| AC1 text arrives, run completes | 2, 3, 4 | `test_opencode_realtime.py::test_the_answer_text_streams_in_pieces` |
| AC2 denied call, no fragment released | 2, 3, 4 | `::test_a_denied_drop_table_never_leaves_in_pieces` |
| AC3 reasoning recorded, never written | 3, 3b, 4 | `::test_reasoning_is_shown_live_and_never_written_down` |
| AC4 skipped without opt-in | 4 | module `pytestmark`; `tests/test_e2e_marker.py`; the run without `--run-e2e` |
| Script, registry, roles pinned in normal suite | 5 | `tests/test_e2e_opencode_realtime_script.py` |

## Risks

- OpenCode 2.3.2 differs from 2.0.10 (tool names, argument keys, `advertises`): adapt the new script only.
- Silent buffered fallback (registry flag, grant or switch missing): the audit and id assertions make it fail loudly.
- OpenCode may reject an unknown reasoning key and abort every run: probe it in Task 3b first.
- The 0.2 s first-chunk margin is local-only and generous; never run in CI.
