---
story: STORY-015
prd: PRD-017
slug: success-criteria-suite-and-latency
title: In-process success-criteria suite for tool calling; step 7c latency measured
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: In-process success-criteria suite for tool calling; step 7c latency measured

## Summary

This story adds no application code. It adds one new test file, `tests/test_tool_calling_criteria.py`. The file maps the in-process success criteria to end-to-end tests that drive `/v1/chat/completions` through `TestClient`. The criteria come from the brief (`pre-prds/PRE-PRD-016-tool-calling.md:75-81`) and from PRD-017 Section 11 (`.agents/PRDs/PRD-017-tool-calling/PRD.md:433-458`). Every test runs with `V1_TOOLS_ENABLED=true` (except the flag-off test) and an injected upstream. That upstream is either `app.routers.v1.call_openrouter` replaced by a stub, or the real `call_openrouter` over an `httpx.MockTransport` when bytes on the upstream wire matter.

The file covers five criteria:
1. A `DROP TABLE` (via `shell` + `sqlite3`, via `run_sql` and via MCP `query`) is denied, recorded with the request's `audit_id` (in the table and through `GET /audit/actions?audit_id=`) and reported in the content. This is checked both streamed and non-streamed, and a mixed response releases only the allowed calls.
2. Arguments that look like PII, contain unicode or are escape-heavy stay byte-identical in both directions: client to upstream (history) and upstream to client (JSON body and SSE). Real `code`-profile redaction runs, and the test proves it ran.
3. An OpenCode 2.0 loop runs `npm test`, edits a file and runs `npm test` again. It goes through `/v1` with the real duplicate check and is never held. A byte-identical resend is held.
4. With `evaluate_all` monkeypatched to deny everything, neither response shape carries a call (T1). With the flag off, the full tool request is PRD-015's `tools_not_supported`.
5. A `@pytest.mark.benchmark` test (skipped without `--run-benchmark`) times step 7c (`evaluate_all` + `apply_decisions`) over the PRD-016 synthetic corpus, grouped into responses of at most 8 calls. It prints p50 and p95 for the report and asserts no threshold. This is the PRD-016 STORY-017 precedent.

Fixtures and helpers are imported from `tests/test_v1_tools.py`, `tests/test_query_pipeline_tools.py` and `tests/test_action_corpus.py`, following the repo convention of `from tests.test_x import _helper`. Nothing is duplicated.

## User Story

As a security admin
I want the brief's success criteria proven in the everyday suite, without a real client
So that a regression in any of them fails the build rather than an opt-in E2E run

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-015-success-criteria-suite-and-latency.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Sections 6.4 :201-214, 6.6 :230-261, 9.2 T1/T2 :362-363, 10 :382-431, 11 :433-458)
- Brief: `pre-prds/PRE-PRD-016-tool-calling.md:75-81` ("Success criteria")

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (tests only) |
| Complexity | MEDIUM |
| Systems Affected | `tests/test_tool_calling_criteria.py` (new); no app, script or doc change |
| Story | STORY-015 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | `.agents/skills/` holds only `frontend-design` (UI design), and this story has no UI. The story's `skills: []` agrees | — |

---

## Mapping: criterion → test (the file's spine)

| Source criterion | Test in the new file | Already proven elsewhere (cite in docstring) |
|---|---|---|
| Brief "DROP TABLE is denied, audited, and the agent reports the reason"; PRD 11 "DROP TABLE via bash/sqlite3 and via a mapped SQL tool → no call, `stop`, note, `rule == sql.ddl`, one row with the `audit_id`" | `test_drop_table_is_denied_recorded_with_the_audit_id_and_reported[{shell-sqlite3,run_sql,mcp-query}-{json,sse}]` | `test_v1_tools.py:1255` (shell only, no `/audit/actions` read) |
| PRD 11 "A mixed response keeps the allowed calls in order, drops the denied one, `tool_calls`, one note" | `test_mixed_response_releases_only_the_allowed_calls[json,sse]` | `test_v1_tools.py:983`, `:1217` (two calls, shell deny) |
| Brief "No tool-call argument is modified by any check"; PRD 11 "byte-identical client → upstream and upstream → client, with PII, unicode, escape-heavy"; T2 | `test_history_arguments_reach_the_upstream_byte_identical`, `test_response_arguments_reach_the_client_byte_identical[json,sse]` | `test_query_pipeline_tools.py:406` (pipeline level, history only); `test_v1_tools.py:715` (ASCII, history only) |
| Brief "Running `npm test` twice in one session is not held as a duplicate"; PRD 11 "two requests of one tool loop never share a key; an identical resend does" | `test_npm_test_twice_in_one_session_is_not_held_but_a_resend_is[json,sse]` | `test_query_pipeline_dedup_key.py:322` (pipeline level, `bash`, no `/v1`) |
| T1 "monkeypatched `evaluate_all` returning deny for every call leaves no call in either response shape" | `test_no_call_is_released_when_every_call_is_denied[json,sse]` | `test_query_pipeline_tools.py:912` (pipeline level only) |
| MVP "full suite green with the flag off"; PRD 11 "Flag off: every PRD-015 `tools_not_supported` test passes unchanged" | `test_flag_off_refuses_the_whole_tool_request_as_prd_015[json,sse]` | `test_v1_tools.py:666` (per-key refusals) |
| Quality "Step 7c's added latency measured over the PRD-016 synthetic corpus (p95 < 5 ms, ≤ 8 calls)" | `test_step_7c_latency_over_the_synthetic_corpus` (`benchmark`) | PRD-016 precedent `test_action_corpus.py:889-922` (`evaluate()` only) |

---

## Patterns to Follow

### Importing helpers from another test module (repo convention)
```
# SOURCE: tests/test_query_pipeline_tools.py:50-51
from tests.test_query_pipeline_dedup_key import _log_query_call_sources
from tests.test_query_pipeline_pii_profiles import _SHIPPED_CODE_SETTINGS
# SOURCE: tests/test_action_corpus.py:125
from tests.test_action_adapters import _sources_rows
```
`tests/conftest.py` has no `/v1` fixtures. Shared `/v1` fixtures live in `tests/test_v1_tools.py`, so import from there; do not move anything into conftest.

### `/v1` fixtures and stubs to import (do not copy)
```
# SOURCE: tests/test_v1_tools.py:571-621
_AUTH_USER_ID = "juan@empresa.com" ... _ADMIN_TOKEN = "test-admin-token" ... _PATH = "/v1/chat/completions"
client = TestClient(app, headers=_AUTH_HEADERS)

@pytest.fixture
def temp_db(temp_db):            # conftest's DB + a `user` and an `admin` token
@pytest.fixture(autouse=True)
def _flag_state(monkeypatch):    # V1_TOOLS_ENABLED=False, V1_TOOL_MODELS=""
class _ToolUpstream:             # accepts tools=; returns OpenRouterResult(**result)
def _use(monkeypatch, stub):     # monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
```
Also import `_MODEL`, `_data_events` (:827), `_upstream_over` (:705, the real `call_openrouter` over a transport), `_accumulate` (:1075, the OpenAI SDK stream accumulator), `_decision_table` (:1249), `_only_row` (:637) and `_count_audit_rows` (:632). Import the two fixtures by name, `from tests.test_v1_tools import temp_db, _flag_state  # noqa: F401 (pytest fixtures)`. Pytest registers fixtures found in a module's namespace. The imported `temp_db` still resolves its own `temp_db` parameter to conftest's.

### T1 deny-all monkeypatch (import, do not copy)
```
# SOURCE: tests/test_query_pipeline_tools.py:900-910
def _all_denied(monkeypatch):
    real = action_policy.evaluate_all
    def evaluate_all(calls, identity):
        return tuple(dataclasses.replace(d, decision="deny", rule="tool.unknown", reason="denied for the test")
                     for d in real(calls, identity))
    monkeypatch.setattr(action_policy, "evaluate_all", evaluate_all)
```
This works because the pipeline calls `action_policy.evaluate_all(calls, identity)` through the module (`app/services/query_pipeline.py:17-20, :832`).

### Real `code` redaction (import the fixture)
```
# SOURCE: tests/test_query_pipeline_tools.py:127-134
@pytest.fixture
def _code_policy(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    for name, value in _SHIPPED_CODE_SETTINGS.items(): monkeypatch.setattr(settings, name, value)
    pii_policy.load()
    yield
```
`/v1` always runs `profile="code"` (`app/routers/v1.py:318`).

### The synthetic corpus (import, do not reload)
```
# SOURCE: tests/test_action_corpus.py:141, 174-176, 312-315
_IDENTITIES = MappingProxyType({role: Identity(f"corpus-{role}", role) for role in _ROLES})
_POLICIES = MappingProxyType({"built_in": BUILT_IN_POLICY, "example": _load_example_policy()})
_SYNTHETIC = [_load_case(path) for path in _SYNTHETIC_FILES]   # 75 files today
```

### Benchmark test shape (mirror)
```
# SOURCE: tests/test_action_corpus.py:886-922
_BENCHMARK_ROUNDS = 50
@pytest.mark.benchmark
def test_evaluate_p95_over_the_synthetic_corpus(capsys, record_property):
    """Measured and printed for the story report -- **no threshold asserted**. ..."""
    ... warm-up pass ... time.perf_counter() ...
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]; median = statistics.median(ordered)
    record_property("evaluate_p95_ms", round(p95, 4))
    with capsys.disabled(): print("\n" + line)
```
The skip without `--run-benchmark` is in `tests/conftest.py:166-203`.

### Assertion idioms already used for the wire
```
# SOURCE: tests/test_v1_tools.py:1263-1282  (deny row against the audit row; note == template.format)
(row,) = _decision_table(); audit = _only_row()
assert (row["decision"], row["rule"], row["tool_name"]) == ("deny", "sql.ddl", "shell")
assert row["audit_id"] == audit.id
note = tool_release.DENIAL_NOTE_TEMPLATE.format(name="shell", id="call_1", reason=row["reason"])
# SOURCE: tests/test_v1_tools.py:734-736  (D13: the string, in the raw body)
assert json.dumps(_ARGS) in seen[0].content.decode("utf-8")
```

### Duplicate on `/v1` (expected shape)
```
# SOURCE: tests/test_v1_errors.py:151-165 — a held resend is 400 `duplicate_request`, JSON even when stream=true,
#   harness={"reason": "Duplicate query within 24 hours", "first_query_at": ...}, upstream not called.
```

### Docstring style
Module docstring like `tests/test_v1_tools.py:1-16`: name the story, the PRD sections and decisions, and what layer is driven. Each test docstring names the criterion it proves, for example "Brief success criterion 3; PRD-017 Section 11 (Functional, DROP TABLE); T5", and cites the narrower existing test where one exists.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_tool_calling_criteria.py` | CREATE | The criteria suite plus the benchmark-marked step 7c latency test |
| `.agents/reports/PRD-017-tool-calling/STORY-015-success-criteria-suite-and-latency.report.md` | CREATE (implement) | Records the p50/p95, the exact benchmark command and the targeted test counts |

No app file, script, doc, `tests/conftest.py` or `_DB_NODEIDS` change is needed. Every DB test requests `temp_db`, so the `db` marker is automatic (`tests/conftest.py:101-105, :193-195`). `test_pii_redaction_integration.py`'s census concerns only renamed or removed tests (`:481`, `:525`), and nothing is renamed.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Module skeleton, imports, constants

- **File**: `tests/test_tool_calling_criteria.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: "PRD-017 STORY-015: the brief's success criteria, in process". List the criteria and the table above in short form. State that everything goes through `/v1` with `TestClient`, that the upstream is injected and that the latency test is `benchmark`.
  - Prologue `os.environ.setdefault("OPENROUTER_API_KEY", ...)` / `ADMIN_TOKEN`, as in `tests/test_v1_tools.py:18-21`.
  - Imports. From `tests.test_v1_tools`: `client, temp_db, _flag_state, _ToolUpstream, _use, _upstream_over, _data_events, _accumulate, _decision_table, _only_row, _count_audit_rows, _MODEL, _PATH, _ADMIN_TOKEN`. From `tests.test_query_pipeline_tools`: `_all_denied, _code_policy`. From `tests.test_action_corpus`: `_SYNTHETIC, _POLICIES, _IDENTITIES`.
  - If pytest does not pick up an imported fixture (verify with `--setup-plan` on one test), fall back to a local copy of the 4-line `temp_db` override and the 3-line `_flag_state`. Say so in the report.
  - Constants:
    - `_OPENCODE_TOOLS`: three `{"type":"function","function":{"name": n, "parameters": {"type":"object", ...}}}` entries for `shell` (`command`), `read` (`path`) and `write` (`path`, `content`). These are the OpenCode 2.0 names and keys (`app/services/action_adapters.py:511-530`; `examples/action_policy.yaml:66-80`).
    - `_SYSTEM = {"role":"system","content":"You are OpenCode..."}` (short).
    - `_EXAMPLE_POLICY_FILE = <repo>/examples/action_policy.yaml`.
  - Helper `_with_flag(monkeypatch)` sets `V1_TOOLS_ENABLED=True`, or each test does it inline as the existing tests do. Pick one form and use it everywhere.
  - Helper `_body(messages, **extra)` returns `{"model": _MODEL, "messages": messages, "tools": _OPENCODE_TOOLS, **extra}`.
  - Helper `_content(response, stream)`: the message content (JSON), or the concatenated deltas' content (SSE), as at `tests/test_v1_tools.py:1275-1280`.
  - Helper `_released(response, stream)`: the list of `(id, name, arguments)`. For JSON it reads `choices[0].message.tool_calls or []`. For SSE it collects every delta's `tool_calls` entries.
- **Mirror**: `tests/test_v1_tools.py:1-66, 571-645`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py --collect-only -q` collects without error.

### Task 2: DROP TABLE denied, audited with the audit_id, reported (criterion 3)

- **File**: `tests/test_tool_calling_criteria.py`
- **Action**: UPDATE
- **Implement**:
  - `_DROP_CALLS` has three entries, all under the built-in policy:
    - `"shell-sqlite3"`: `ToolCallSpec("call_d", "shell", json.dumps({"command": 'sqlite3 app.db "DROP TABLE users"'}))`
    - `"run_sql"`: `ToolCallSpec("call_d", "run_sql", '{"query":"DROP TABLE users"}')`
    - `"mcp-query"`: `ToolCallSpec("call_d", "query", '{"sql":"DROP TABLE users"}')`
    - The built-in map has `run_sql`/`execute_sql`/`apply_migration` reading `query`, and `query` reading `sql` (`app/services/action_adapters.py:584-589`). `examples/action_policy.yaml:80` maps `run_sql` too. All three were checked during planning: they evaluate to `deny`/`sql.ddl` for role `user`.
  - `test_drop_table_is_denied_recorded_with_the_audit_id_and_reported`, parametrized over the three calls × `stream` ∈ {False, True}:
    - Upstream: `_use(monkeypatch, _ToolUpstream(response="", tool_calls=(call,), finish_reason="tool_calls"))`.
    - Request: `[{"role":"user","content":"drop the users table"}]`.
    - Assert status 200. `(row,) = _decision_table()` has `decision == "deny"`, `rule == "sql.ddl"`, `tool_name == call.name` and `audit_id == _only_row().id`.
    - Assert the content equals `DENIAL_NOTE_TEMPLATE.format(name=call.name, id="call_d", reason=row["reason"])` and the reason appears in it.
    - JSON: `tool_calls is None`, `finish_reason == "stop"`, `harness.actions == [{tool_call_id, tool_name, decision: "deny", rule: "sql.ddl", reason: row["reason"]}]`.
    - SSE: `'"tool_calls"' not in response.text`, the last finish is `"stop"`, `response.text` ends with `data: [DONE]` (the stream did not fault) and no chunk has a `harness` key.
    - Both: `call.arguments` (raw and `json.dumps`-escaped) and `"arguments"` are not in `response.text`. The note names `DROP` only through `row["reason"]`, so assert that `response.text` stripped of the note does not contain `"DROP TABLE"`.
    - Audit API: `client.get(f"/audit/actions?audit_id={audit_id}", headers={"Authorization": f"Bearer {_ADMIN_TOKEN}"})` returns one entry with that `audit_id`, `decision == "deny"` and `rule == "sql.ddl"`. This is STORY-013's filter, end to end. Check the entry keys with `tests/test_admin_actions.py:261-275` / `_entries`.
    - Docstring: brief criterion 3; PRD 11 Functional (DROP TABLE line). Cite `test_v1_tools.py::test_drop_table_via_shell_is_denied_and_recorded_with_the_audit_id`, which covers shell only.
  - `test_mixed_response_releases_only_the_allowed_calls[json,sse]`:
    - Upstream text `"Reading."` with calls `read{"path":"src/a.py"}` (`call_r`), `run_sql` DROP (`call_d`) and `write{"path":"src/b.py","content":"x"}` (`call_w`). Check that `write` relative is allowed under the built-in policy (`fs.write_in_workspace`, verified in planning).
    - Assert the released calls are `[("call_r", ...), ("call_w", ...)]` in model order, with arguments equal. Content is `"Reading.\n\n" + note(call_d)` with one note. Finish is `tool_calls`. The rows are `[allow, deny, allow]`, all with the same `audit_id`. JSON: `harness.actions` ids in model order.
    - Cite `test_v1_tools.py:983`, `:1217`.
- **Mirror**: `tests/test_v1_tools.py:1254-1282, 983-1003, 1217-1234`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -k "drop_table or mixed" -q`

### Task 3: No argument modified by any check, both directions, both wire shapes (criterion 4, T2)

- **File**: `tests/test_tool_calling_criteria.py`
- **Action**: UPDATE
- **Implement**:
  - `_TRICKY` has three `ToolCallSpec`s. Every string must be valid JSON (an unparseable one is `tool.malformed`, so it would be denied and never released) and must be allowed under the built-in policy.
    - PII: `write` with `{"path":"notes/ops.md","content":"mail ops@example.org, call +1 212 555 0100, card 4111 1111 1111 1111, SSN 078-05-1120"}`.
    - Unicode, raw UTF-8 and literal `\uXXXX` escapes side by side, so a re-dump would rewrite one into the other: `read` with `'{"path":"src/café ☃ 日本 😀 \u202e.ts", "alt":"caf\\u00e9"}'`.
    - Escape-heavy and whitespace-odd: `write` with `'{"path": "src/a.py" ,"content":"C:\\\\tmp\\\\a.txt \\"q\\" \\n\\t \\\\u0041 \\/ end"}'`. Build these with explicit Python literals and print them in a REPL once to confirm each is the intended JSON text and `json.loads`-valid.
  - Module-level guard `_assert_allowed(calls)`: `action_policy.evaluate_all(tuple(ToolCall(c.id, c.name, c.arguments) for c in calls), Identity(_AUTH_USER_ID, "user"))` must all be `allow`, so that a policy change fails loudly here and not as a confusing release diff. Call it inside each test; importing `_AUTH_USER_ID` is fine.
  - Wire encodings. Each layer is plain JSON with `ensure_ascii=False`:
    - httpx 0.28.1 `json=` for the upstream request (`app/services/openrouter_client.py:270`)
    - Starlette `JSONResponse` for the JSON body (`app/routers/v1.py:185`)
    - pydantic `model_dump_json` for SSE (`app/services/v1_sse.py:43`)
    - The raw-substring needle is therefore `json.dumps(args, ensure_ascii=False)`. Confirm per layer when implementing. If a layer escapes differently (for example `\u2028`), keep the decoded-string equality as the proof, use that layer's encoder for the needle and record it in the report. Never weaken the decoded equality.
  - `test_history_arguments_reach_the_upstream_byte_identical(temp_db, monkeypatch, _code_policy)`:
    - Flag on. A `seen` list with a capturing `httpx.MockTransport` returns a text answer (`tests/test_v1_tools.py:695-702` `_capturing_transport`; import it). `monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(transport))`.
    - Messages: user, then an assistant turn with the three `_TRICKY` calls in the OpenAI wire shape (`content: None`), then three `tool` turns. One tool turn is `"mailed ops@example.org"`.
    - Assert `payload["messages"][1]["tool_calls"][i]["function"]["arguments"] == _TRICKY[i].arguments` for each i, and `.encode("utf-8")` equal. Assert the needle is in `seen[0].content.decode("utf-8")`.
    - Assert `payload["messages"][2..4]` carry the right `tool_call_id`. Assert the email tool turn reached the upstream as `"mailed <EMAIL_ADDRESS>"`, which proves redaction ran in this very request while the same email inside the arguments did not change (D13).
  - `test_response_arguments_reach_the_client_byte_identical[json,sse](temp_db, monkeypatch)`:
    - Flag on. The transport returns a 200 whose body bytes are written explicitly: `content=json.dumps(body, ensure_ascii=True).encode()`, so the upstream sends `\u`-escaped JSON and the harness must still hand the client the same decoded string. The body is `{"choices":[{"message":{"content":null,"tool_calls":[{"id","type":"function","function":{"name","arguments"}} ...]},"finish_reason":"tool_calls"}],"model":_MODEL,"usage":{"total_tokens":12}}`.
    - Route it through `_upstream_over(transport)`. `tools=` is sent because the body has `tools`, so D18 parses the calls.
    - JSON: `[c["function"]["arguments"] for c in message["tool_calls"]] == [c.arguments for c in _TRICKY]`, ids and order equal, needle in `response.text`.
    - SSE: `_released(response, True)` equals the same tuples. `_accumulate(_data_events(response.text))` (the OpenAI SDK) yields the same `arguments`. Each needle is in `response.text`.
    - Plain `/v1` requests (no `_code_policy`) still run `code` redaction with the defaults. Arguments are never handed to it (`app/services/query_pipeline.py:723, 852`; PRD 6.5).
    - Docstring: cite the STORY-001 note. "Not modified" is a harness property: the harness forwards exactly what it received in each direction. Client re-stringification (Cline) is out of scope.
- **Mirror**: `tests/test_v1_tools.py:695-738, 1150-1173`; `tests/test_query_pipeline_tools.py:406-425`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -k byte_identical -q`

### Task 4: `npm test` twice in one session is not a duplicate; a resend is (criterion 5)

- **File**: `tests/test_tool_calling_criteria.py`
- **Action**: UPDATE
- **Implement**:
  - Example policy, which is what an OpenCode deployment runs: `monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(_EXAMPLE_POLICY_FILE)); action_config.load()`. conftest's `_default_action_policy` restores `_policy` afterwards (`tests/conftest.py:714-726`). The built-in policy denies `npm test` as `shell.unlisted` (verified in planning). The example allowlists it (`examples/action_policy.yaml:52`), and `write`/`read` of `src/math.js` are allowed there (verified).
  - `_ScriptedUpstream`: a list of `OpenRouterResult` kwargs, popped in order. It records `messages` per call, accepts `params=`/`tools=` keyword-only like `_ToolUpstream` and fails loudly if called more times than scripted. The script mirrors `tests/e2e/scripts/tool_loop.json` (STORY-014), with calls carrying distinct ids:
    1. shell `{"command":"npm test"}`
    2. write `{"path":"src/math.js","content":"export const add = (a, b) => a + b;\n"}`
    3. shell `{"command":"npm test"}`
    4. text `"Done: npm test passes."` with `finish_reason` `"stop"`
  - `test_npm_test_twice_in_one_session_is_not_held_but_a_resend_is[json,sse]`. The parameter is the resend's `stream`; the loop is always JSON.
    - Flag on. `messages = [_SYSTEM, {"role":"user","content":"run the tests, fix the failure, run them again"}]`. Send four requests in a loop.
    - On each request, assert 200 and that the body is not an error. If calls were released, append `{"role":"assistant","content": message["content"], "tool_calls": message["tool_calls"]}` exactly as the response gave it (a real client loop), then a `tool` turn answering each call. The outputs are `"1 failing"`, `"ok"` and `"2 passing"`.
    - Keep a deep copy of each request body. Assert the released `tool_calls` came back with `decision == "allow"` in `harness.actions`.
    - After the loop: 4 audit rows with 4 distinct `dedup_key`s (`get_audit_log`). The stub was called 4 times. The two `npm test` requests (bodies 2 and 4, i.e. index 1 and index 3) differ in key even though the same command was called in both.
    - Resend: `json` param resends body 4 verbatim (the byte-identical resend). `sse` param resends body 4 with `"stream": true` added: `stream` is not in the key (the key covers the user id and the messages, PRD 6.4), as `tests/test_v1_errors.py:151-165` already shows (a plain first request, then a streamed one, held). In both cases the answer is `400` JSON with `error.code == "duplicate_request"` (never a committed stream), the stub is not called a 5th time, and the newest row's `dedup_key` equals row 4's.
    - No `dedup_key` or `find_duplicate*` monkeypatch anywhere: real dedup.
    - Docstring: brief criterion 5; PRD 6.4 "Why npm test twice is not a duplicate"; PRD 11 Functional dedup line. Cite `test_query_pipeline_dedup_key.py::test_npm_test_twice_is_not_held_but_a_resend_is` (pipeline, `bash`). Usage limits: 5 requests ≪ 60/min (`app/config.py:355`).
- **Mirror**: `tests/test_query_pipeline_dedup_key.py:322-336`; `tests/test_dedup_key.py:393-402`; `tests/test_v1_errors.py:151-165`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -k npm -q`

### Task 5: T1 (deny-all leaves no call) and flag off is PRD-015

- **File**: `tests/test_tool_calling_criteria.py`
- **Action**: UPDATE
- **Implement**:
  - `test_no_call_is_released_when_every_call_is_denied[json,sse](temp_db, monkeypatch)`:
    - Flag on, `_all_denied(monkeypatch)`. Upstream returns `read{"path":"src/a.py"}` and `write{"path":"src/b.py","content":"x"}`, which the real engine would allow.
    - JSON: `tool_calls is None`, finish `stop`, content is the two notes joined by `"\n\n"` ("denied for the test"), `harness.actions` decisions `["deny","deny"]`.
    - SSE: `'"tool_calls"' not in response.text`, last finish `stop`, `[DONE]` present.
    - Both: neither arguments string (raw or JSON-escaped) nor `'"arguments"'` is in `response.text`. Two `deny` rows with the request's `audit_id`.
    - Docstring: PRD 9.2 T1 (the test it names), MVP.
  - `test_flag_off_refuses_the_whole_tool_request_as_prd_015[json,sse](temp_db, monkeypatch)`:
    - Flag left off (autouse `_flag_state`). POST the full OpenCode request: `tools`, `tool_choice: "auto"`, history with assistant `tool_calls` and a `tool` turn, `stream` per param.
    - Assert the result equals `400`, `{"error": {"message": "tools: tool calling is not supported (PRD-017)", "type": "invalid_request_error", "param": "tools", "code": "tools_not_supported", "harness": None}}`, `x-should-retry: false`, no audit row and the stub not called.
    - Import `_FLAG_OFF_REFUSALS["tools-and-tool-turn"]`'s expectation or `_error` from `tests/test_v1_tools.py:644-659` rather than retyping the message.
    - Docstring: D10; PRD 11 Functional first line; cite `test_v1_tools.py::test_flag_off_refusals_are_prd_015_exactly` for the per-key matrix.
- **Mirror**: `tests/test_v1_tools.py:665-676, 879-921`; `tests/test_query_pipeline_tools.py:900-925`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -k "denied or flag_off" -q`

### Task 6: Step 7c latency over the synthetic corpus (benchmark-marked)

- **File**: `tests/test_tool_calling_criteria.py`
- **Action**: UPDATE
- **Implement**: `@pytest.mark.benchmark def test_step_7c_latency_over_the_synthetic_corpus(capsys, record_property)`. No DB.
  - Build responses: group `_SYNTHETIC` by `case.policy` (a response is decided under one policy, as `evaluate_all` resolves it once, `app/services/action_policy.py:348-361`). Chunk each group in file order into responses of at most `_MAX_CALLS_PER_RESPONSE = 8` calls. Each call gets a unique id `f"{case.path.stem}"`.
  - Keep both forms per response, as the pipeline has them: `specs: tuple[ToolCallSpec, ...]`, and the identity `_IDENTITIES["user"]`. Every case names `user`, and `dba` needs the corpus RBAC matrix (`tests/test_action_corpus.py:179-182`), which this file does not apply.
  - Timed region per response, exactly step 7c's body (`app/services/query_pipeline.py:828-836`):
    ```
    calls = tuple(ToolCall(c.id, c.name, c.arguments) for c in specs)
    decisions = action_policy.evaluate_all(calls, identity, policy)
    tool_release.apply_decisions(specs, decisions)
    ```
    `policy` is passed explicitly (an additive parameter, `action_policy.py:348-353`) because the corpus spans two policies. The pipeline's `get_policy()` lookup is a module-global read; say so in the docstring.
  - One warm-up pass, then `_BENCHMARK_ROUNDS = 50` timed passes. Report nearest-rank p95, `statistics.median`, min and max in ms. Also print the response count and the call count, and the p95 for full 8-call responses only. That is the PRD's bound, so report the worst case separately from the short tail chunks.
  - `record_property("step_7c_p95_ms", ...)`. Print one line `STORY-015 step 7c over {n} responses ({m} calls, <= 8 per response) x 50 rounds: min / p50 / p95 / max; 8-call p95 ...` under `capsys.disabled()`.
  - **No threshold asserted**. Use the precedent's docstring reason (`tests/test_action_corpus.py:891-899`): a wall-clock gate is flaky. The report states the verdict against the 5 ms target.
  - **Why a benchmark test and not a `scripts/measure_*_latency.py`**: the existing scripts measure I/O paths end to end. `measure_v1_latency.py:1-40` covers HTTP, the real app, the stub on loopback and libSQL rows. `measure_usage_latency.py` covers DB statements, and `measure_pii_latency.py` the Presidio analyzer. Step 7c is pure CPU over a corpus whose loader lives in `tests/test_action_corpus.py`. A script would have to re-implement or import a test module. The PRD-016 STORY-017 measurement of `evaluate()` p95 (report: 0.4151 ms) used exactly this benchmark-test form, so no reusable script fits. This is the story's "if a reusable one fits" clause. Record the deviation in the report.
  - Command for the report: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -m benchmark --run-benchmark -s -q -p no:cacheprovider`
- **Mirror**: `tests/test_action_corpus.py:884-922`
- **Validate**: without the flag the test is reported as skipped. With the command above it prints the line, and that line goes into the report.

### Task 7: Targeted run, report

- Targeted run, one pytest call in the foreground: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py tests/test_v1_tools.py -q -p no:cacheprovider`. `test_v1_tools.py` is included because its helpers are now imported and must still collect and pass unchanged; nothing in it is edited. Then run the benchmark command separately. Record exact counts.
- `.venv/Scripts/python -c "from app.main import app; print('OK')"`.
- Do not run `test_untouched_app.py` (no app file is touched) or `test_pii_redaction_integration.py` (no rename). Full suite: deferred to orchestrator (user decision).
- Report: the criterion-to-test table with pass status, the p50/p95 line (all responses and 8-call responses) with a verdict against p95 < 5 ms, the benchmark command, the fixture-import outcome, and any wire-encoding finding from Task 3.

---

## End-to-End Tests

- [ ] `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -q`: every non-benchmark test passes, and the benchmark test is skipped.
- [ ] `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -m benchmark --run-benchmark -s -q -p no:cacheprovider`: prints the step 7c p50/p95 line.
- [ ] `tests/test_v1_tools.py` still passes unedited (its helpers are imported).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py tests/test_v1_tools.py -q -p no:cacheprovider
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -m benchmark --run-benchmark -s -q -p no:cacheprovider
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| An imported fixture (`temp_db` override, autouse `_flag_state`) is not picked up, or the override resolves wrongly | Check with `--setup-plan` on one DB test. The fallback is a local copy of the two short fixtures, recorded in the report |
| A tricky argument is not valid JSON, or the policy denies it, so it is not released and the "byte-identical" diff misleads | The `_assert_allowed` guard runs before each wire assertion. Strings are built from explicit literals and checked once in a REPL |
| The wire needle differs per encoder (`ensure_ascii`, `\u2028`, `/` escaping) | The decoded-string equality is the proof. The needle uses each layer's actual encoder (httpx 0.28.1, Starlette, pydantic), confirmed while implementing. Findings go in the report |
| `npm test` is denied under the built-in policy (`shell.unlisted`, verified), which would make the loop unrealistic | The loop loads `examples/action_policy.yaml` (allowlists `npm test`), the policy the docs give OpenCode deployments. conftest restores the policy |
| The `sse` resend is not byte-identical (it adds `stream`) | The `json` variant is the literal byte-identical resend. The `sse` variant only adds the wire form of the held verdict, and `stream` is outside the key (`test_v1_errors.py:151-165`) |
| Duplicate holds between requests of one test (the same prompt sent twice) | Every test sends distinct conversations; the only identical body is the deliberate resend |
| Benchmark noise on a loaded Windows machine | No threshold asserted. 50 rounds, warm-up, nearest-rank p95 and the max all reported, as in the precedent |
| Overlap with existing per-story tests | Each new test is the end-to-end `/v1` form of a criterion and cites the narrower existing test. No existing test is edited or removed |

## Acceptance Criteria

(Copied from story `STORY-015`)

- [ ] Given a new `tests/test_tool_calling_criteria.py` driving `/v1` through `TestClient` with `V1_TOOLS_ENABLED=true` and an injected upstream, when it runs, then: a model `DROP TABLE` (via `bash` `sqlite3` and via a mapped SQL tool) is denied, recorded with the request's `audit_id`, and the response's content carries the reason, streamed and not; a mixed response releases only the allowed calls. (Task 2. OpenCode 2.0 names the tool `shell`, and `bash` and `shell` share one mapping, `action_adapters.py:515-516`. The existing `bash` test is cited.)
- [ ] Given PII-looking, unicode and escape-heavy arguments, when sent in history and returned by the upstream, then they are byte-identical at the upstream and at the client (non-streamed and streamed). (Task 3)
- [ ] Given one session that runs `npm test`, edits a file and runs `npm test` again, when every request of the loop is sent, then none is held as a duplicate; a byte-identical resend of one request is. (Task 4)
- [ ] Given `evaluate_all` monkeypatched to deny everything, when any tool response is produced, then neither response shape contains a call (T1); with the flag off, the PRD-015 `tools_not_supported` behaviour holds. (Task 5)
- [ ] Given the PRD-016 synthetic corpus, when step 7c is timed per response of ≤ 8 calls, then p50/p95 are recorded in the report (target p95 < 5 ms). (Task 6. A benchmark-marked test, because no `measure_*` script fits; deviation recorded)
- [ ] All tasks completed; `from app.main import app` imports; targeted tests pass; follows existing patterns
