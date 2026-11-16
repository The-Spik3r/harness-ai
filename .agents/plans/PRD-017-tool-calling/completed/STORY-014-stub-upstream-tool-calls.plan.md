---
story: STORY-014
prd: PRD-017
slug: stub-upstream-tool-calls
title: "Stub upstream: scripted tool_calls replies, rules matching on any last turn"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: Stub upstream: scripted tool_calls replies, rules matching on any last turn

## Summary

`scripts/stub_openrouter.py` (stdlib only, a test tool) learns three things. (1) A reply may carry
`tool_calls: [{"id"?, "name", "arguments"}]`; the body then has `content: null` unless the script
sets `content`, every call gets `type: "function"`, an omitted id is generated as `call_<n>` from a
per-server counter, and `finish_reason` defaults to `"tool_calls"`. (2) A rule may name `role`
(closed vocabulary `system|user|assistant|tool`) so `contains` / `regex` test the **last message of
that role**, `last_role` to require the conversation to end on a given role, and two optional
content-independent qualifiers that make a whole agent loop scriptable deterministically:
`after_call` (the last assistant turn called a tool of this name) and `advertises` (the request's
`tools` list offers a function of this name, so one script can branch between OpenCode and Cline
and end Cline's loop with `submit_and_exit`). A rule without any of these keeps today's behaviour
exactly (last `user` message, `""` when there is none). (3) The log line gains two counts,
`tools=<n> calls=<n>`, appended after `delay=` so every existing assertion still holds; it still
never prints content, arguments, tool names or headers. A new `tests/e2e/scripts/tool_loop.json`
(read, edit, `npm test`, final text) is driven through the real `call_openrouter(..., tools=...)`
on a loopback stub, which proves the replies pass STORY-004's parsing rules.

**Streaming: not needed, confirmed.** `call_openrouter` never sends `stream` upstream: the payload is
`model`, `messages`, the set `GenerationParams` fields and the `ToolParams` fields only
(`app/services/openrouter_client.py:245-262`), and it reads one JSON body (`:280-288`). The `/v1`
router reaches it through `_UpstreamCall.__call__` (`app/routers/v1.py:146-150`), and SSE to the
client is built from the buffered result (PRD-015 D8, PRD-017 PRD.md:28, :102). So the stub keeps
answering non-streamed JSON only; a `stream` key in a request body is just another parameter key
in the log.

## User Story

As the E2E author
I want the stub upstream to answer with scripted tool calls and to choose its reply from the latest tool result
So that a multi-step agent loop can be scripted without a real model

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-014-stub-upstream-tool-calls.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Section 4 "Stub upstream" :86-87, F9 :334-335, D15 :527)
- Client facts: `.agents/spikes/PRD-017-tool-calling/client-survey.md` (:63-65 history shapes, :71 Cline never stops on its own, :107-108 tool names)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `scripts/stub_openrouter.py`, `tests/test_stub_openrouter.py`, `tests/e2e/scripts/` |
| Story | STORY-014 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI visual design); this story has no UI, and the story's `skills: []` agrees | — |

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| NAMING | `scripts/stub_openrouter.py:61-66` | Closed key vocabularies as module `frozenset`s (`_REPLY_KEYS`, `_BODY_KEYS`, `_MATCHER_KEYS`, `_RULE_KEYS`) |
| SCHEMAS | `scripts/stub_openrouter.py:79-98` | Frozen dataclasses `Reply` / `Rule`; `Rule.matches` |
| ERRORS | `scripts/stub_openrouter.py:146-200` | `ScriptError(f"{where}: <field> must be ..., got {value!r}")` at load time, `where` = `rules[i]` / `default` |
| SELECT | `scripts/stub_openrouter.py:106-120` | `Script.select(subject, hits)` — first match wins, `times` checked/charged under the caller's `hits` |
| SUBJECT | `scripts/stub_openrouter.py:237-251` | `_last_user_text`: string content, or a parts list joined from text parts, else `""` |
| SERVER STATE | `scripts/stub_openrouter.py:351-370` | Per-server state bound on a handler subclass (`ids`, `hits`, `hits_lock`) |
| LOG | `scripts/stub_openrouter.py:316-320` | One ASCII line, `ascii()` on untrusted values, names only |
| UPSTREAM RULES | `app/services/openrouter_client.py:147-185` | `id` non-empty string, `type` absent/null/`"function"`, `function.name` non-empty, `arguments` a string, ids unique per response |
| CONTENT NULL | `app/services/openrouter_client.py:290-297` | `content: null` beside calls becomes `""`; calls parsed only when `tools=` was sent (D18) |
| TESTS | `tests/test_stub_openrouter.py:61-90` | `stub` fixture (thread, ephemeral port, `settings.OPENROUTER_BASE_URL` monkeypatched), `_call`, `_lines` |
| TEST VALIDATION | `tests/test_stub_openrouter.py:345-374` | Parametrized `(script, names)` rejection table |

### Naming
```
// SOURCE: scripts/stub_openrouter.py:61-66
_SCRIPT_KEYS = frozenset({"rules", "default"})
_REPLY_KEYS = frozenset({"content", "finish_reason", "usage", "delay_seconds", "fail_status"})
_BODY_KEYS = frozenset({"content", "finish_reason", "usage"})
_MATCHER_KEYS = frozenset({"contains", "regex"})
_RULE_KEYS = frozenset({"times"})  # rule only: `default` rejects it as unknown
```

### Error Handling
```
// SOURCE: scripts/stub_openrouter.py:186-188
    times = raw.get("times")
    if "times" in raw and not (_is_count(times) and times >= 1):
        raise ScriptError(f"{where}: times must be an integer >= 1, got {times!r}")
```

### Tests
```
// SOURCE: tests/test_stub_openrouter.py:83-86
def _call(*contents, roles=None, **kwargs):
    roles = roles or ["user"] * len(contents)
    kwargs.setdefault("api_key", _SECRET)
    return call_openrouter([Message(r, c) for r, c in zip(roles, contents)], **kwargs)
```

---

## Design

### Script format additions

Reply (rule and `default`):

| Key | Meaning |
|-----|---------|
| `tool_calls` | Non-empty list of `{"name": str (non-empty), "arguments": str, "id"?: str (non-empty)}`. No other keys. `arguments` must be a **string** (D13: the stub, like the upstream, emits a string; an object is refused, never serialized — mirrors `openrouter_client.py:178-180`). Explicit ids must be unique within the reply and must not look like a generated id (`call_<digits>`), so a generated id can never collide with a scripted one. `tool_calls` is a body key: `fail_status` rejects it like `content`. |
| `content` | Unchanged for replies without `tool_calls` (default `""`). With `tool_calls` it defaults to **`null`**; a string is allowed (text beside calls, which `call_openrouter` accepts). |
| `finish_reason` | Defaults to `"tool_calls"` when the reply has `tool_calls`, else `"stop"` as today. An explicit value (string or `null`) wins. |

Rule-only qualifiers (all optional, all ANDed with the one `contains`/`regex` matcher; `default`
rejects them as unknown, like `times`):

| Key | Meaning |
|-----|---------|
| `role` | `system` / `user` / `assistant` / `tool`. `contains`/`regex` test the content of the **last message of that role** (string, or text parts joined, as `_last_user_text` does; an assistant turn with `content: null` reads as `""`). If the request has no message of that role, the rule does not match. Without `role`: today's subject (last `user` message, `""` when none) — byte-for-byte today's behaviour. |
| `last_role` | Same vocabulary. The rule matches only if `messages[-1].role` equals it. |
| `after_call` | Non-empty string. The rule matches only if the **last `assistant` message** carries a `tool_calls` entry whose `function.name` equals it. Content- and id-independent: clients generate/rewrite ids and re-stringify arguments (survey :104), and tool-result text is client-specific (survey :43, :65), so "what did I just call" is the stable loop state. |
| `advertises` | Non-empty string. The rule matches only if the request's `tools` list has an entry whose `function.name` equals it. Lets one script serve OpenCode (`read`/`edit`/`shell`) and Cline (`read_files`/`editor`/`run_commands`/`submit_and_exit`, survey :58), and makes "end Cline's loop with `submit_and_exit`" a rule (survey :71). |

`contains`/`regex` stays mandatory (exactly one; the existing rejection test for a matcher-less
rule, `tests/test_stub_openrouter.py:349`, keeps passing). `{"regex": ""}` is the documented
"any content" matcher for a rule that only needs qualifiers.

Ending a loop: OpenCode stops on a text reply (a reply without `tool_calls`, `finish_reason:
"stop"`); Cline needs a `submit_and_exit` call (gate it with `advertises: "submit_and_exit"`),
and STORY-017 should still pass `-t` as a safety net. The README says so.

### Code shape (in `scripts/stub_openrouter.py`)

- New constants: `_ROLES = frozenset({"system", "user", "assistant", "tool"})`,
  `_TOOL_CALL_KEYS = frozenset({"id", "name", "arguments"})`, `_QUALIFIER_KEYS =
  frozenset({"role", "last_role", "after_call", "advertises"})` (rule only, merged into the rule's
  allowed keys next to `_RULE_KEYS`), `tool_calls` added to `_REPLY_KEYS` and `_BODY_KEYS`,
  `_GENERATED_ID = re.compile(r"call_\d+")` (fullmatch).
- `@dataclass(frozen=True) class ScriptedCall: name: str; arguments: str; id: Optional[str] = None`.
- `Reply` gains `tool_calls: tuple = ()`; `content` becomes `Optional[str]` (default `""` stays).
- `Rule` gains `role`, `last_role`, `after_call`, `advertises` (all `Optional[str] = None`).
- `@dataclass(frozen=True) class Request: messages: tuple; tool_names: frozenset` with a
  `from_body(body)` constructor — the parsed view a rule is tested against. `Rule.matches` takes a
  `Request`; the subject helper `_last_text(messages, role) -> Optional[str]` generalizes
  `_last_user_text` (kept as a thin wrapper or replaced; `_last_user_text` is private and not used by
  the tests).
- `Script.select(subject, hits=None)` **keeps its signature** (an existing test calls it with a
  string, `tests/test_stub_openrouter.py:264-269`) and delegates to a new
  `Script.select_request(request, hits=None)` with `Request(messages=({"role": "user", "content":
  subject},), tool_names=frozenset())`. The handler calls `select_request`.
- `_parse_reply`: `tool_calls` validation (list, non-empty, each an object with known keys only,
  `name` non-empty str, `arguments` str, optional `id` non-empty str, not `call_<digits>`, unique),
  content default `None` and finish_reason default `"tool_calls"` when calls are present. Error text
  names `{where}.tool_calls[{i}].<field>` and the rule, never echoes `arguments`.
- `_parse_rule`: validate `role` / `last_role` against `_ROLES`, `after_call` / `advertises` as
  non-empty strings.
- Handler: per-server `call_ids = itertools.count(1)` bound in `make_server` next to `ids`; the
  message built as `{"role": "assistant", "content": reply.content}` plus, only when the reply has
  calls, `"tool_calls": [{"id": c.id or f"call_{next(call_ids)}", "type": "function",
  "function": {"name": c.name, "arguments": c.arguments}}]`. A reply without calls produces the
  same body as today (no `tool_calls` key). Ids are generated per answer, so a `times`-less rule
  answering twice yields fresh ids.
- Log line: `... rule={label} delay={d:g} tools={n} calls={m} -> {status}` where `n` is
  `len(body["tools"])` when it is a list (else 0) and `m` the reply's call count (0 on
  `fail_status`). Counts only. Existing assertions checked against this: `"model='m' messages=1
  params=[] rule=0"` (:423) is a prefix that still appears contiguously; `endswith("-> 200")`
  (:125, :225); `split(" rule=")` (:153, :247); `params=[...]` (:124, :126) — all unchanged.
- Module docstring: script format extended (tool_calls, the four qualifiers, how to end a loop,
  log counts). Mention that the stub never streams because `call_openrouter` never asks it to.
- `tools` is not validated (story note); malformed entries are simply not counted as names.

### Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/stub_openrouter.py` | UPDATE | Reply `tool_calls`, rule qualifiers, `Request` view, id generation, log counts, docstring |
| `tests/e2e/scripts/tool_loop.json` | CREATE | Example tool loop: read → edit → `npm test` → final text (AC 4) |
| `tests/test_stub_openrouter.py` | UPDATE | New tests appended; **no existing assertion, test name or table row edited** (AC 3). New rejection cases go in a new parametrized test, not the existing table |
| `tests/e2e/scripts/README.md` | UPDATE | Format table rows for the new keys, `tool_loop.json` paragraph, how to end a loop per client |

No `app/` file changes (so `test_untouched_app.py` is not required); `example.json` is left as is
(its test `:377-385` stays green).

### `tool_loop.json` (shape; exact text decided at implement)

Generic tool names (`read`, `edit`, `shell`, OpenCode 2.0's per survey :107, `path` argument key),
sequenced by `after_call` so the reply never depends on client-written tool text:

1. `{"regex": "TOOL-LOOP", "last_role": "user", "tool_calls": [{"name": "read", "arguments": "{\"path\":\"src/math.js\"}"}]}`
2. `{"role": "tool", "last_role": "tool", "after_call": "read", "contains": "function add", "tool_calls": [{"name": "edit", "arguments": "{\"path\":\"src/math.js\",...}"}]}`
3. `{"role": "tool", "last_role": "tool", "after_call": "edit", "regex": "", "tool_calls": [{"name": "shell", "arguments": "{\"command\":\"npm test\"}"}]}`
4. `{"role": "tool", "last_role": "tool", "after_call": "shell", "contains": "passing", "content": "Done: ...", "finish_reason": "stop"}`
5. `{"role": "tool", "last_role": "tool", "after_call": "shell", "regex": "", "content": "The tests failed; stopping."}` (failure branch, still ends the loop)
- `default`: a fixed text reply naming no rule matched (ends any loop).
- At least one call has an explicit id and one omits it, so both paths are exercised.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Reply `tool_calls` parsing and body
- **File**: `scripts/stub_openrouter.py`
- **Action**: UPDATE
- **Implement**: constants, `ScriptedCall`, `Reply.tool_calls`, `_parse_reply` validation and the content/finish_reason defaults; `tool_calls` in `_BODY_KEYS` so `fail_status` rejects it; per-server `call_ids`; body built with `tool_calls` only when present.
- **Mirror**: `scripts/stub_openrouter.py:146-173` (reply parsing), `:327-343` (body), `:358-369` (per-server state)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_stub_openrouter.py -q` stays green (no behaviour change for existing scripts)

### Task 2: Rule qualifiers and the `Request` view
- **File**: `scripts/stub_openrouter.py`
- **Action**: UPDATE
- **Implement**: `Request.from_body`, `_last_text(messages, role)`, `Rule` fields + `matches(request)`, `_parse_rule` validation, `Script.select_request`, `Script.select(subject, hits)` delegating. Handler uses `Request.from_body(body)`.
- **Mirror**: `:106-120`, `:176-200`, `:237-251`
- **Validate**: existing tests green, in particular `test_a_rule_without_times_is_never_capped` and `test_only_the_last_user_message_is_matched`

### Task 3: Log counts and docstring
- **File**: `scripts/stub_openrouter.py`
- **Action**: UPDATE
- **Implement**: append `tools={n} calls={m}` before ` -> {status}`; rewrite the docstring's format section; keep stdlib-only imports.
- **Mirror**: `:316-320`, `:1-46`
- **Validate**: existing log tests green (`:109-137`, `:277-296`, `:402-427`)

### Task 4: Example script
- **File**: `tests/e2e/scripts/tool_loop.json`
- **Action**: CREATE
- **Implement**: as in Design; loads with `load_script`.
- **Validate**: `.venv/Scripts/python -c "from scripts.stub_openrouter import load_script; load_script('tests/e2e/scripts/tool_loop.json'); print('OK')"`

### Task 5: Tests (appended, existing ones untouched)
- **File**: `tests/test_stub_openrouter.py`
- **Action**: UPDATE (new sections after the existing ones; update the module docstring's AC map only by adding a PRD-017 STORY-014 block, leaving the PRD-015 lines as they are)
- **Implement** (each through the `stub` fixture and the real `call_openrouter`, which needs `tools=ToolParams(tools=[...])` per D18):
  - `test_tool_calls_reply_parses_through_call_openrouter` — AC 1's exact reply `{"name": "bash", "arguments": "{\"command\":\"npm test\"}"}`: `result.tool_calls[0].name == "bash"`, `arguments` byte-identical, id `call_1`, `finish_reason == "tool_calls"`, `response == ""`.
  - `test_tool_calls_body_has_content_null_type_function_and_string_arguments` — raw `httpx.post`: `content is None`, `type == "function"`, `isinstance(arguments, str)`, a script `finish_reason` override wins, explicit `content` is kept.
  - `test_generated_ids_are_unique_across_answers_and_explicit_ids_are_kept` — two calls in one reply plus a second answer: ids `call_1, call_2, call_3`, an explicit id passes through.
  - `test_role_tool_matches_the_last_tool_message` — history `user, assistant(tool_calls), tool(A), assistant(tool_calls), tool(B)` built with `Message(..., tool_calls=(ToolCallSpec(...),), tool_call_id=...)`; a rule on B's content answers, a rule on A's only does not.
  - `test_role_without_a_message_of_that_role_does_not_match` and `test_last_role_requires_the_final_turn`.
  - `test_after_call_and_advertises_qualify_a_rule` — different tool names in the last assistant turn / in `tools`, and the request with no `tools`.
  - `test_rules_without_role_keep_matching_the_last_user_message` — a `role`-less rule still matches the last user message when the conversation ends on a tool turn (back-compat, AC 2).
  - `test_tool_loop_script_runs_read_edit_test_then_final_text` — loads `tool_loop.json` into the fixture, drives the four steps through `call_openrouter(..., tools=...)`, appending each released call as an assistant `Message` with `ToolCallSpec`s and a scripted `tool` result (with client-style ids, e.g. `"toolu_x"`, to show matching is id-independent); asserts the call names `read, edit, shell` in order, every `ToolCallSpec` passes (non-empty unique ids), `finish_reason` `tool_calls` then `stop`, the final text; also the failure branch.
  - `test_tool_loop_log_names_counts_never_arguments_or_tool_content` — the loop's log: ASCII, contains `tools=<n>` and `calls=1`, and none of the arguments strings, tool names (`npm test`, `src/math.js`), tool-result content, or `_SECRET`.
  - `test_bad_tool_scripts_are_rejected_naming_the_field` — new parametrized table: `tool_calls: []`, not a list, call not an object, unknown call key, empty/missing name, `arguments` as an object, empty id, `call_7` id, duplicate ids, `tool_calls` with `fail_status`, `role: "robot"`, `last_role: 3`, `after_call: ""`, `advertises: 1`, `default` with `role` (unknown key).
  - `test_the_tool_loop_script_loads` — has tool replies, an `after_call` rule, a `role: "tool"` rule, an explicit id and an omitted one.
- **Mirror**: `tests/test_stub_openrouter.py:61-90, 98-137, 345-374`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_stub_openrouter.py -q` (no `db` marker; runs without Docker)

### Task 6: README
- **File**: `tests/e2e/scripts/README.md`
- **Action**: UPDATE
- **Implement**: add `tool_loop.json` to the opening list with one paragraph; format table rows for `tool_calls`, `role`, `last_role`, `after_call`, `advertises`; the `contains`/`regex` row says "against the last message of `role` (default `user`)"; a "Scripting an agent loop" paragraph (sequence on `after_call`, end OpenCode with text and Cline with `submit_and_exit` gated by `advertises`, Cline `-t`; tool content reaches the stub after the harness's pattern and PII steps, D13, so match on markers that are not PII); the log line now ends `tools=<n> calls=<n>`.
- **Validate**: read-through; no code depends on it.

---

## End-to-End Tests

- [ ] `python scripts/stub_openrouter.py --port 0 --script tests/e2e/scripts/tool_loop.json` starts and prints `listening on` (the existing CLI test pattern; optional manual check)
- [ ] The tool-loop test above runs the whole loop over a real loopback socket through `call_openrouter`
- [ ] The full harness round trip (`/v1` with `V1_TOOLS_ENABLED=true` on the stub) is STORY-015/016's, not this story's

---

## Validation

```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_stub_openrouter.py -q
.venv/Scripts/python -c "from app.main import app; print('OK')"
.venv/Scripts/python -c "import ast,sys; t=ast.parse(open('scripts/stub_openrouter.py',encoding='utf-8').read()); print(sorted({(n.module if isinstance(n,ast.ImportFrom) else a.name).split('.')[0] for n in ast.walk(t) if isinstance(n,(ast.Import,ast.ImportFrom)) for a in (n.names if isinstance(n,ast.Import) else [n])}))"   # stdlib only
```

Full suite: deferred to orchestrator. No `app/` change, so `test_untouched_app.py` is not needed;
no existing test is renamed or removed, so `test_pii_redaction_integration.py` is not needed.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Changing the log line breaks an existing assertion | Counts are appended between `delay=` and ` -> `; every existing substring/suffix check re-read above (:123-126, :153, :225, :247, :296, :423) |
| `Script.select(str)` is called by an existing test | Signature kept; it delegates through a one-user-message `Request` |
| A non-tool reply's body changes | `tool_calls` key added only when the reply has calls; `content` default for non-tool replies stays `""` |
| Generated id collides with a scripted one | Scripted ids matching `call_<digits>` are rejected at load |
| Tool content the stub matches on has been redacted/blocked by the harness (D13: `tool` content gets patterns and PII) | Documented in README; `after_call` sequencing avoids depending on content; STORY-016 picks non-PII markers |
| Cline never stops (survey :71) | `advertises: "submit_and_exit"` rule + `-t` documented; the default reply is text so OpenCode stops |
| Scope creep into STORY-016/017 | Only the generic example script here; the client scripts are theirs |

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] AC 1 — tool_calls reply: valid Chat Completions body, `content: null`, `call_<n>` ids when omitted, `finish_reason: "tool_calls"` unless set; `call_openrouter` parses it. *Covered by* `test_tool_calls_reply_parses_through_call_openrouter`, `test_tool_calls_body_has_content_null_type_function_and_string_arguments`, `test_generated_ids_are_unique_across_answers_and_explicit_ids_are_kept`.
- [ ] AC 2 — `role: "tool"` (and `last_role`) match the last message of that role; role-less rules keep the last-user behaviour; existing scripts still work. *Covered by* the role / last_role / back-compat tests, the unchanged existing suite, and `example.json`'s existing load test.
- [ ] AC 3 — log names only model, message count, parameter keys and the rule (plus counts); never content, arguments or headers; existing assertions unchanged. *Covered by* `test_tool_loop_log_names_counts_never_arguments_or_tool_content` and the untouched existing tests (diff shows only additions in `tests/test_stub_openrouter.py`).
- [ ] AC 4 — one example tool-loop script (read → edit → `npm test` → final text) used by the stub's tests. *Covered by* `tests/e2e/scripts/tool_loop.json`, `test_tool_loop_script_runs_read_edit_test_then_final_text`, `test_the_tool_loop_script_loads`.
- [ ] All tasks completed
- [ ] `from app.main import app` imports OK
- [ ] `scripts/stub_openrouter.py` imports only the standard library; nothing under `app/` mentions it
- [ ] Follows existing patterns
