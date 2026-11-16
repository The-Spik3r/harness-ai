---
story: STORY-018
prd: PRD-017
slug: docs-and-promotion
title: README, docs/features.md, docs/roadmap.md, .env.example; brief promotion verified
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: README, docs/features.md, docs/roadmap.md, .env.example; brief promotion verified

## Summary

Document tool calling on `/v1` as **shipped behind `V1_TOOLS_ENABLED` (default off)**. The docs describe what was built, including every amendment made during the run (PRD 6.3 rule 4, D8's mark-failed step, Section 10's text-only rule, STORY-003's `null` handling, the flag-on legacy-API message), not the original PRD text where it changed. The work: a new `### Tool calling` section in `docs/features.md` (flag, `V1_TOOL_MODELS`, setup order, the Section 6.5 table, denial note, `finish_reason`, `harness.actions`, buffered deltas, dedup rule, limits, and per-client setup for OpenCode 2.0.10 and Cline CLI 3.0.74 taken from the verified E2E runs); the stale "not yet called" text in `features.md`, `README.md`, `docs/roadmap.md`, `docs/api.md`, `docs/configuration.md`, `docs/deployment.md` and `.env.example` reworded; two settings added to `.env.example` (plus two presence tests, the PRD-016 STORY-020 precedent); the brief promotion verified (already done at PRD creation, no drift found) and Milestone 2 marked reached. A scratchpad link-and-anchor checker compares every changed doc against HEAD. No file under `app/` or `chat_ui/` changes.

## User Story

As a platform operator
I want tool calling documented as shipped — how to turn it on, how to set up OpenCode and Cline, what a denial looks like and what is not covered
So that I can enable it safely.

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-018-docs-and-promotion.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Sections 4 Documentation, 6.3, 6.4, 6.5, 6.6, 6.7, 9.2, 9.3, 10, 15 D1–D19)
- Survey: `.agents/spikes/PRD-017-tool-calling/client-survey.md`, `tests/corpora/actions/SOURCES.md` (*OpenCode 2.x*, *Cline CLI 3.0.74*)
- E2E (the only source for client setup): `tests/e2e/test_opencode.py`, `tests/e2e/_opencode.py`, `tests/e2e/test_cline.py`, `tests/e2e/_cline.py`, `tests/e2e/cline/action_policy.yaml`, `tests/e2e/cline/package.json`, reports STORY-016 / STORY-017
- Precedent: PRD-016 STORY-020 (`.agents/plans/PRD-016-action-policy-rules/completed/STORY-020-docs-and-promotion.plan.md`, report `f4cf292`)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (docs; one small test addition) |
| Complexity | LOW (story: small) |
| Systems Affected | `README.md`, `docs/features.md`, `docs/roadmap.md`, `docs/api.md`, `docs/configuration.md`, `docs/deployment.md`, `.env.example`, `pre-prds/README.md`, `tests/test_config.py`; `.agents/` bookkeeping |
| Story | STORY-018 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

Dependencies: STORY-013, 015, 016, 017 are all `done` (index: 17/18).

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | `.agents/skills/` holds only `frontend-design`; the story has `skills: []` and no UI ("Skills: none applicable. No UI."). The Actions view copy was STORY-013's. | — |

---

## Facts the docs must carry (each traced to code or a report)

Write from this list, not from the PRD's original text. Where the PRD was amended, the amended rule is the one listed.

| # | Fact | Source |
|---|---|---|
| F1 | `V1_TOOLS_ENABLED` (default `false`): off is PRD-015 byte for byte; `tools` / `tool_choice` / tool turns are `400 tools_not_supported`, *tool calling is not supported (PRD-017)* | `app/config.py:376-384`, `app/services/v1_translate.py:121-124,145-147` |
| F2 | `functions` / `function_call` refused whatever the flag; flag on, the message is *the deprecated function-calling API is not supported; use tools* | `v1_translate.py:150-153` |
| F3 | `V1_TOOL_MODELS` (default empty = no extra restriction): exact, comma list; each entry must be in `MODEL_ALLOWLIST` (startup error naming it); when set it applies to **every** caller, `admin` and RBAC-off included (admin's any-model allowance does not reach `tools` requests); unlisted model → `400 tools_not_supported`, `param: "tools"`, *model is not enabled for tool calling (V1_TOOL_MODELS)* | `app/config.py:386-392,682-707`, `v1_translate.py:155,517` |
| F4 | Settings are read at startup like every setting (configuration.md:3): changing the flag needs a restart. "Per request" in the PRD means the router reads `settings` per request, which is how tests flip it | `docs/configuration.md:3`, PRD 6.7 |
| F5 | Order: set `ACTION_POLICY_FILE` (workspace roots, `shell.allow`, `tools:` for the client) **before** turning the flag on; the built-in policy denies every dangerous class and has an empty workspace root list and empty `shell.allow` (T9, Risk 4/6) | PRD 9.2 T9, `features.md:277,279` |
| F6 | Shape rules at the edge (`400 invalid_messages`, `param: messages[i]`): last turn `user` or `tool`; a `tool` turn answers an id of the nearest preceding assistant `tool_calls` turn with only `tool` turns between; an id answered once per assistant turn (providers reuse `call_0`); **the conversation contains at least one `user` turn** (rule 4, amended). Not required: every call answered | PRD 6.3 (amended), STORY-005 report |
| F7 | Malformed `tools` item / `tool_choice` / `parallel_tool_calls` → `400 invalid_parameter` naming e.g. `tools[2].function.name`; `tool_choice` naming a function not in `tools` → `invalid_parameter`, `param: tool_choice`. `tools`, `tool_choice` (`none`/`auto`/`required`/`{type:function,...}`) and `parallel_tool_calls` are forwarded upstream as sent | PRD 10 table, STORY-008 report |
| F8 | `tool_calls: null` on any role and `tool_call_id: null` on a non-tool role count as absent; `tool_calls: []` on an assistant turn is accepted | STORY-003 deviation, PRD 6.2 |
| F9 | Section 6.5 table, as built: context limit counts `tool` content **and** `len(arguments)` of history calls (D12); dedup prefix; patterns inspect `tool` content under `code` (`flag`), never arguments; PII input redacts `tool` content (prose only) under `code`, never arguments; the PII size limit (`PII_MAX_CHARACTERS_CODE`) counts content only; action policy evaluates every response call; PII output never touches calls; audit `prompt` is the final turn, user or tool (D7) | PRD 6.5, STORY-007 report |
| F10 | Release: `allow` and `flag` calls released in model order, unmodified (byte-identical arguments); `deny` dropped and replaced by a note appended to content after output redaction, separated by a blank line: `[harness] tool call {name} ({id}) was denied: {reason}` (name/id cut to 64 chars; reason is PRD-016's fixed safe reason) | `app/services/tool_release.py:39-45`, PRD 6.6 |
| F11 | `finish_reason`: `tool_calls` when ≥1 call released; `stop` when the upstream reported calls and none survived; otherwise the upstream's. `content: null` when calls are released and there is no text and no note. All denied: `tool_calls: null` (key kept). **Text-only responses (flag on or off) carry neither `tool_calls` nor `harness.actions`** — the body is PRD-015's byte for byte (Section 10 amendment, STORY-011 DD-1) | PRD 10 (amended), STORY-011 report |
| F12 | `harness.actions`: one `{tool_call_id, tool_name, decision, rule, reason}` per evaluated call, released or not, in model order, non-streamed body only | STORY-011 report, PRD 6.6 |
| F13 | Streamed (`stream: true`): still buffered; after keep-alives: role chunk (`content` or `null`), one chunk per released call carrying its whole `arguments`, finish chunk, usage chunk if `include_usage`, `[DONE]`. No `harness` object in chunks. Verified with the OpenAI Python SDK accumulator in-process and by both clients (every E2E request was streamed) | STORY-012, 015, 016, 017 reports |
| F14 | Dedup over tool loops: anchor is the last user turn, never a tool turn; every other turn goes into the prefix hash with the anchor position marked; each loop step carries a longer prefix, so `npm test` twice in a session is not held; a byte-identical resend (auto-retry) still is; tool-free keys unchanged (pinned), so the upgrade resets no 24-hour window | PRD 6.4, STORY-006 report |
| F15 | Audit: every row of a loop is `ingress=v1`, `profile=code`, one `conversation_key`; `has_tool_calls=1` when the request carried an assistant `tool_calls` or `tool` turn, or the upstream response carried calls (before release) (D19); one `action_decisions` row per evaluated call with the request's `audit_id`; `GET /audit/actions?audit_id=<id>` lists one request's decisions | D19, STORY-013, STORY-016/017 reports |
| F16 | Fail closed (D8 amended): if recording the decisions fails, the response is `500 internal_error` (retryable), nothing released (non-streamed body; streamed `error` event); the request's row is marked `success=0`, `error_message='action audit failed'` (best effort) so the retry is not held as a duplicate; if that also fails, an `ERROR` log says so and the 24-hour window holds the retry | PRD D8 (amended), STORY-010 report |
| F17 | Limits / not covered: harness never executes tools; history calls are not re-evaluated (T3); `tools[].description` / schemas not inspected (T7); arguments not pattern-inspected or redacted (D13); `functions` refused; MCP payloads not classified (and OpenCode 2.x calls MCP tools inside `execute`, which is `tool.unknown`); streaming is buffered; no tool calling on `/query` or in the chat UI (D17), where an upstream `tool_calls` reply stays an upstream error (D18); non-text tool results not accepted; no capability field on `GET /v1/models` (D16) | PRD 4 Out of Scope, 9.2, 9.4, SOURCES.md |
| F18 | Step 7c latency: p95 2.93 ms over all responses (≤ 8 calls), 2.97 ms over 8-call responses, target < 5 ms; `pytest tests/test_tool_calling_criteria.py -m benchmark --run-benchmark` (check the exact test id/marker in the file before quoting the command) | STORY-015 report:44-52 |
| F19 | OpenCode 2.0.10 (verified, STORY-016): provider `@ai-sdk/openai-compatible`, `options.baseURL = <harness>/v1`, `options.apiKey = <harness token>`, model `harness/openai/gpt-4o` (`<provider id>/<model id>`; the model id keeps its slash and must be in `MODEL_ALLOWLIST`, and in `V1_TOOL_MODELS` when set), `agent.title.disable: true`; passed as `OPENCODE_CONFIG_CONTENT`; `OPENCODE_DISABLE_MODELS_FETCH=1`, `OPENCODE_DISABLE_AUTOUPDATE=1`; `opencode run --standalone --auto --format json -m harness/openai/gpt-4o "<prompt>"`; stdin closed. Policy: `workspace.roots: [<repo absolute path>]`, `shell.allow: [python -m unittest]`, built-in `tools:` (which covers 2.0's `shell`, `read`, `write`, `edit` with `filePath|path`, `patch`) | `tests/e2e/_opencode.py:64-97`, `test_opencode.py:21-33,350-352`, STORY-016 report |
| F20 | OpenCode pitfalls: `opencode run` reads a non-TTY stdin and waits for EOF (close it); it takes its working directory from `PWD`, not the process cwd (a stale `PWD` made `shell` run in the wrong checkout); it sends `store` (recorded in `ignored_params` on every row); it asks for a session title without `tools` unless `agent.title.disable`; tools advertised include `execute` (CodeMode, always `tool.unknown` → denied, never list it in `opaque_tools`), `question`, `skill`, `subagent`, `websearch` (unmapped → denied); `patch` replaces `edit`/`write` for `gpt-` models other than `gpt-4*`/`oss`, so `tools:` must map `patch` | STORY-016 report findings, SOURCES.md *OpenCode 2.x* |
| F21 | Cline CLI 3.0.74 (verified, STORY-017): installed locally and pinned, never globally (`npm install --prefix <dir> --save-exact cline@3.0.74`); `cline auth --data-dir <ABSOLUTE dir> --provider openai-compatible --apikey <harness token> --modelid openai/gpt-4o --baseurl <harness>/v1`, then `cline --data-dir <same dir> --yolo --json -c <repo> -P openai-compatible -m openai/gpt-4o "<prompt>"`; stdin closed; `PWD` set to the repo. `--yolo` advertises `read_files`, `run_commands`, `editor`, `submit_and_exit`; requests carry `tool_choice: "auto"` | `tests/e2e/_cline.py:87-103`, `test_cline.py:21-41`, STORY-017 report |
| F22 | Cline policy: its own `tools:` (the sample maps OpenCode and SQL only, and `tools:` replaces the mapping wholesale), its own `shell.allow`, `workspace.roots`, and **`opaque_tools: {submit_and_exit: allow}`** (Cline's loop ends only on that call; denied, Cline asks again forever). Working template: `tests/e2e/cline/action_policy.yaml` (its `apply_patch` reads `input` only) | `tests/e2e/cline/action_policy.yaml:17-40` |
| F23 | Cline pitfalls: a relative `--data-dir` silently falls back to api.openai.com with no key; `-t` is not honoured (984 requests in 60 s with `-t 10`), the loop ends only on `submit_and_exit`, so bound the process yourself; Cline fetches feature flags from its own service at startup (outbound traffic the harness does not see; no request content; no known switch) | STORY-017 plan/report, story Technical Notes, `_cline.py:39-42,87-96` |
| F24 | Both E2E runs: the scripted multi-file task completed, the scripted `sqlite3 app.db "DROP TABLE users"` was denied `sql.ddl`, the client executed nothing and printed the harness note, every decision joined by `audit_id`. Run against the stub upstream (D15); a live-model run is optional, not a gate | STORY-016/017 reports |

---

## Patterns to Follow

### Section structure and tone (features.md)
```
// SOURCE: docs/features.md:226-230
### Action policy rules

**Status: built and tested, and not yet called by `/v1`.** Tool calling on [`/v1`](roadmap.md#openai-compatible-endpoint) is PRD-017; ...

**What it is.** A pure function, `action_policy.evaluate(tool_call, identity)`, that answers *allow*, *flag* or *deny* ...
```
Bold lead-in sentence per paragraph, plain statements, limits "stated plainly", a closing "The full design is in [PRD-0NN](...)" line (`features.md:307`). Tables for matrices (`features.md:72-75,142-145`).

### README: short section that links to features.md
```
// SOURCE: README.md:171-179
## Action policy rules

**Status: built and tested, not yet called by `/v1`.** ... Full reference: **[Action policy rules](docs/features.md#action-policy-rules)**.

To use it once something calls it:

1. Copy [`examples/action_policy.yaml`](examples/action_policy.yaml), set `workspace.roots` ...
```

### .env.example block
```
// SOURCE: .env.example:182-190
# OpenAI-compatible endpoint (PRD-015; README, "OpenAI-compatible endpoint")

# Mount POST /v1/chat/completions and GET /v1/models (true/false). false makes
# /v1/* a 404 and leaves /query and the chat UI exactly as they are
V1_ENABLED=true
```
One comment paragraph above each variable, `(true/false)` for booleans, the shipped default as the value, Settings field order (`app/config.py`: `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, `V1_TOOLS_ENABLED`, `V1_TOOL_MODELS`, then `ACTION_*`).

### .env.example presence tests
```
// SOURCE: tests/test_config.py:1392-1409
def test_env_example_documents_the_action_policy_vars_with_a_comment():
    """PRD-016 STORY-020 AC 3: all three present, each with a comment line above."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in _ACTION_VARS:
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_action_policy_defaults_match_settings():
    """The documented values are the defaults, and the vars follow Settings order."""
    ...
    positions = [text.index(f"{var}=") for var in _ACTION_VARS]
    assert positions == sorted(positions)
```
`_env_example_value` helper: `tests/test_config.py:878`.

### Roadmap Shipped entries
```
// SOURCE: docs/roadmap.md:21-22
- [x] [OpenAI-compatible endpoint](#openai-compatible-endpoint) — `POST /v1/chat/completions` and `GET /v1/models` for ...
- [x] [Audit fields and usage limits](features.md#usage-limits) — per-user token budget ...
```

### Milestone line
```
// SOURCE: pre-prds/README.md:34-35
- **Milestone 1** — PRD-014 done: ... **Reached 2026-10-30**: the brief became [PRD-015](...), whose 19 stories are done and merged to `main` (PR #20); ...
- **PRD-016 done** (reached 2026-11-15): ... built (20 stories) and merged to `main` (PR #21), ...
```

### Error / message style
No new runtime messages. Quote the existing ones verbatim (F1–F3, F10).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docs/features.md` | UPDATE | New `### Tool calling` section (with `#### Setting up OpenCode` / `#### Setting up Cline`); Action policy rules status, tool names, audit, Actions view, "Where this is going" reworded; pattern/PII `tool` cells reachable |
| `README.md` | UPDATE | Features table row; new short `## Tool calling` section + TOC; Action policy section/row status; Roadmap summary; one sentence under Architecture |
| `docs/roadmap.md` | UPDATE | Shipped items (tool calling; action policy ticked); "Not yet" paragraph (line 52) and "Built"/"What PRD-017 adds" (78-80) rewritten; line 82 and MCP bullet (62) de-staled |
| `docs/api.md` | UPDATE | `ingress` (`:195`) and `has_tool_calls` (`:200`) rows; no `/v1` section exists to update (checked) |
| `docs/configuration.md` | UPDATE | Two rows (`V1_TOOLS_ENABLED`, `V1_TOOL_MODELS`); `ACTION_POLICY_FILE` row (`:51`) and `ADMIN_TOKEN` row (`:14`) de-staled |
| `docs/deployment.md` | UPDATE | `action_decisions` paragraph (`:23`) now written when the flag is on |
| `.env.example` | UPDATE | `V1_TOOLS_ENABLED=false`, `V1_TOOL_MODELS=` with comments; action-policy header (`:193`) reworded |
| `pre-prds/README.md` | UPDATE | Milestone 2 marked reached (`:36`) |
| `pre-prds/PRE-PRD-016-tool-calling.md` | VERIFY only | `status: promoted`, `prd:` correct (checked during planning; no drift) |
| `tests/test_config.py` | UPDATE | Two `.env.example` presence/default tests for the tool vars; the STORY-002 section comment (`:1412-1414`) updated (comment only) |
| `.agents/…` | UPDATE | Plan archive, report, story frontmatter, PRD `status: done`, index regenerated |

Not changed: `app/`, `chat_ui/` (the stale comment `app/config.py:394-395` "Nothing reads these yet" is code; leave it, note in the report), `SECURITY.md` and `docs/testing.md` (no tool-calling claim; checked), `tests/e2e/scripts/README.md` (its stale PRD-015 numbering was left deliberately by STORY-016).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Baseline the link checker (before any edit)

- **File**: scratchpad only, `C:\Users\nahue\AppData\Local\Temp\claude\3538ad6943244944\07c1d677-d9dc-4535-8925-6e718a3d991a\scratchpad\linkcheck018.py` (not committed). No docs link test exists in `tests/` (checked: no slug/anchor checker over `*.md`).
- **Implement**: the PRD-016 STORY-020 Task 10 checker, with `FILES = ["README.md", "docs/features.md", "docs/roadmap.md", "docs/configuration.md", "docs/api.md", "docs/deployment.md", "pre-prds/README.md", "pre-prds/PRE-PRD-016-tool-calling.md"]`. For each file: strip fenced blocks, find every `[text](target)`, skip `http(s):`/`mailto:`, resolve the path part relative to the file (a directory counts as existing), and for `#anchor` on a `.md` target check a heading whose GitHub slug equals it (slug: lowercase, drop backticks, drop chars other than `\w`, `-`, space; spaces → `-`; link text inside headings unwrapped). Run once against `git show HEAD:<file>` (baseline) and once against the working tree; print NEW failures (current − baseline), remaining pre-existing ones, and the fixed count. Open files with `encoding="utf-8"` (cp1252 trap). Run from the repo root with `.venv/Scripts/python -I <script>`.
- **Validate**: run it now; record the baseline count in the report.

### Task 2: `.env.example` — two settings and the action-policy header

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: after `V1_SSE_KEEPALIVE_SECONDS=10` (`:190`), still inside the `# OpenAI-compatible endpoint` block, add:
  - A sub-header line in the house style, e.g. `# Tool calling on /v1 (PRD-017; docs/features.md, "Tool calling"). Configure ACTION_POLICY_FILE first`.
  - `V1_TOOLS_ENABLED=false` with a comment: `(true/false)`; false keeps PRD-015's `tools_not_supported` refusal byte for byte; true admits `tools`, `tool_choice`, `parallel_tool_calls` and tool turns, and every tool call the model returns is decided by the action policy before the client sees it; `functions`/`function_call` are refused either way.
  - `V1_TOOL_MODELS=` with a comment: comma list of models a `tools` request may name, exact match; empty = no extra restriction; every entry must also be in `MODEL_ALLOWLIST` (startup error otherwise); when set it applies to every caller, admin included.
  - Reword `:192-193` to `# Action policy rules (PRD-016; docs/features.md, "Action policy rules")` / `# Decides every /v1 tool call when V1_TOOLS_ENABLED=true (PRD-017)`.
- **Mirror**: `.env.example:182-190`
- **Validate**: Task 3's tests.

### Task 3: `.env.example` presence tests

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append to the PRD-017 STORY-002 section, after `test_v1_tool_models_blank_parses_to_no_restriction`)
- **Implement**:
  - Update the section comment `:1412-1414` (comment only, no assertion): STORY-008/010 read them now; the `.env.example` tests are STORY-018's (the last two of this section).
  - `_TOOL_VARS = ("V1_TOOLS_ENABLED", "V1_TOOL_MODELS")`.
  - `test_env_example_documents_the_tool_vars_with_a_comment()` — docstring `PRD-017 STORY-018 AC 4: both present, each with a comment line above.`; the same regex as `:1397`.
  - `test_env_example_tool_defaults_match_settings()` — `V1_TOOLS_ENABLED` value equals `str(default).lower()` (`"false"`), `V1_TOOL_MODELS` value equals `""`; positions follow Settings order **and** both sit after `V1_SSE_KEEPALIVE_SECONDS=` and before `ACTION_POLICY_FILE=` (Settings order, `app/config.py:369-403`).
- **Mirror**: `tests/test_config.py:1392-1409`, `:1311-1328`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q -p no:cacheprovider` (all pass; the existing `_V1_VARS` / `_ACTION_VARS` order tests must stay green).

### Task 4: `docs/features.md` — new `### Tool calling` section

- **File**: `docs/features.md`
- **Action**: UPDATE — insert after the Action policy rules section (before the closing `---` at `:309`), so it reads after the engine it calls.
- **Implement** (bold-lead paragraphs; every claim from the Facts table):
  1. **Status** (one paragraph): shipped behind `V1_TOOLS_ENABLED`, default off; off is PRD-015 byte for byte (F1); every tool call a model returns is decided by the [action policy](#action-policy-rules) after the model answered and before any byte leaves the harness; the harness never executes a tool.
  2. **Turning it on, in this order** (numbered list): (1) write an `ACTION_POLICY_FILE` with `workspace.roots`, `shell.allow` and the client's `tools:` (F5, F22); (2) grant `action:*` permissions only if needed; (3) optionally set `V1_TOOL_MODELS` (F3); (4) set `V1_TOOLS_ENABLED=true` and restart (F4). Say why the order matters (T9: with the built-in policy and no roots, every absolute write and every Cline shell call is denied — safe, but an agent stalls).
  3. **What is accepted** (F6, F7, F8): the four shape rules, with the 4th marked as the user-turn rule; refusals table (Section 10's table, with the flag-on legacy message F2 and the `V1_TOOL_MODELS` message F3). All 400s before the pipeline, no audit row.
  4. **What each check does with tool content**: the Section 6.5 table as built (F9), then the D13 sentence (arguments are the model's proposal; the action policy classifies them; pattern-inspecting them would flag every agent that writes "ignore" into a file).
  5. **What the client receives** (F10, F11): release rule, the note template verbatim, `finish_reason` rule, `content: null`, all-denied `tool_calls: null`, and the text-only rule (no `tool_calls`/`harness.actions` keys on a response with no evaluated calls). A trimmed JSON example of a denied `DROP TABLE` response (PRD Section 10's, with `"tool_calls": null` and `harness.actions`; keep it consistent with F11).
  6. **`harness.actions`** (F12).
  7. **Streaming** (F13): the chunk sequence (short code block), no `harness` in chunks, verified by the OpenAI SDK accumulator and both clients.
  8. **Tool loops and the duplicate check** (F14), linking [Duplicate detection scope](#duplicate-detection-scope).
  9. **What the audit records** (F15), linking [`GET /audit/actions`](api.md#get-auditactions-requires-auditreadall-or-auditreadown) and its `?audit_id=`; **fail closed** (F16).
  10. **What it does not cover** (F17), bulleted, stated plainly.
  11. **What it costs** (F18).
  12. `#### Setting up OpenCode` (F19, F20): a JSON config block (exactly `_opencode.opencode_config`'s shape with `<harness>` and `<harness token>` placeholders), the run command, a policy YAML snippet (`workspace.roots`, `shell.allow`), then pitfalls as bullets. Say the E2E passed the config as `OPENCODE_CONFIG_CONTENT`; do not claim a config-file location was verified.
  13. `#### Setting up Cline` (F21, F22, F23): install command (local, pinned), the `auth` and run commands, a pointer to [`tests/e2e/cline/action_policy.yaml`](../tests/e2e/cline/action_policy.yaml) as the working template plus a short snippet with `opaque_tools: {submit_and_exit: allow}`, then pitfalls.
  14. **Evidence** (F24), and a closing line: *The full design is in [PRD-017](../.agents/PRDs/PRD-017-tool-calling/PRD.md).*
- **Mirror**: `docs/features.md:226-307`
- **Validate**: Task 10 link check; `grep -n "#tool-calling" README.md docs/*.md` targets resolve.

### Task 5: `docs/features.md` — de-stale existing text

- **File**: `docs/features.md`
- **Action**: UPDATE
- **Implement**:
  - `:3` — unchanged, but Task 6 must add the README Features row the sentence promises.
  - `:82` — replace "the engine ... is built, and PRD-017 is what will call it" and the "**In this release the flag is reachable by tests only:** ..." sentence: the flag is reachable through `/v1` when `V1_TOOLS_ENABLED=true` (tool turns admitted under `code`); `POST /query` and the chat never send tool turns (D17).
  - `:151` — `tool` under `code` is reachable through `/v1` with the flag on (no longer "tested at the function level only").
  - `:153` — `chat`'s `tool` cell stays unreachable: `POST /query` and the chat UI never send tool turns (D17).
  - `:228` — Status: built, and called by `/v1` for every tool call when `V1_TOOLS_ENABLED=true` (see [Tool calling](#tool-calling)); with the flag off live traffic writes no decision row. Remove "Everything below describes the engine as it will behave once something calls it."
  - `:277` — keep; add "the [Tool calling](#tool-calling) setup sections show the verified policies".
  - `:279` (orchestrator note STORY-001) — Tool names: OpenCode v1.19.5 **and 2.0.10** (`shell`, `patch`, and `path` as well as `filePath` on `read`/`write`/`edit`), OpenCode 2.x's CodeMode `execute` is deliberately unmapped (`tool.unknown`, always denied; never list it in `opaque_tools`; OpenCode 2.x calls MCP tools inside it by default), Cline 4.x names (also what the Cline CLI 3.0.74 sends), and the `--yolo` preset's four tools; keep the rest. Mention `submit_and_exit` needs `opaque_tools` for Cline.
  - `:297` — `audit_id` is the request's `audit_logs.id` (null only for a decision recorded outside a request), no longer "null until PRD-017 wires it".
  - `:299` — "The empty state names PRD-017." → the empty state says decisions are recorded only while `V1_TOOLS_ENABLED=true` (STORY-013's copy, `chat_ui/chat_ui/admin_copy.py`).
  - `:305` — "Where this is going" → "**How `/v1` calls it.**" one paragraph pointing at [Tool calling](#tool-calling) (D1/D2 in one line).
- **Validate**: `grep -n -E "not yet called|PRD-017 is what will|reachable by tests only|tested at the function level only|null until PRD-017|names PRD-017" docs/features.md` → no hits.

### Task 6: `README.md` — proportionate changes

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**:
  - Features table: `:156` OpenAI-compatible endpoint row — add "OpenCode and Cline in agent mode once tool calling is turned on" with a link to `docs/features.md#tool-calling`; add a new **Tool calling** row after it (one or two sentences: off by default; every call decided before release; denied calls dropped with a note; link). `:162` Action policy row: replace "**not yet called by `/v1`** (PRD-017)" with "decides every `/v1` tool call when `V1_TOOLS_ENABLED=true`".
  - New `## Tool calling` section before `## Action policy rules` (and a TOC entry at `:30`): status sentence; the four-step enable order; then **OpenCode** and **Cline** as two compact blocks (OpenCode: the provider JSON and the `run` command; Cline: install, `auth`, run, and "use `tests/e2e/cline/action_policy.yaml` as the policy template; it lists `submit_and_exit` in `opaque_tools`"), each ending with "Pitfalls and details: [Setting up OpenCode](docs/features.md#setting-up-opencode)" / "[Setting up Cline](docs/features.md#setting-up-cline)". Keep it under ~35 lines; detail lives in features.md (PRD-016 STORY-020 Q1 precedent).
  - `:173-179` Action policy section: status → called by `/v1` when the flag is on; "To use it once something calls it:" → "To use it:"; step 1 also names `V1_TOOLS_ENABLED`; step 3 points at the Cline template.
  - `:145` (after the Architecture diagram) — one sentence: on `/v1` with tool calling on, every tool call in the response is decided by the action policy after the token charge and before the audit row and the response (step 7c), linking `docs/features.md#tool-calling`. Do not redraw the diagram.
  - `:339-343` Roadmap: Shipped adds "tool calling on `/v1` (OpenCode and Cline in agent mode)" and drops "(the engine and its audit; not yet called by `/v1`)"; Planned drops "tool calling on `/v1` (PRD-017), which is what calls the action policy,".
  - `:328` Documentation table: features row lists "tool calling" too.
- **Validate**: `grep -n -E "not yet called|PRD-017" README.md` → only intentional mentions; Task 10.

### Task 7: `docs/roadmap.md`

- **File**: `docs/roadmap.md`
- **Action**: UPDATE
- **Implement**:
  - Shipped list (`:22`): add `- [x] [Tool calling on /v1](features.md#tool-calling) — OpenCode and Cline in agent mode; every tool call decided by the action policy before the client sees it; off by default (V1_TOOLS_ENABLED)` and move the Action policy item from Planned (`:37`) to Shipped as `- [x] [Action policy rules](#action-policy-rules) — ... decided on every /v1 tool call (PRD-016, PRD-017)` (default; see Q2).
  - `:21` OpenAI-compatible endpoint item: add OpenCode and Cline (with tool calling).
  - `:52` "Not yet" → "**Tool calling (PRD-017).**" With `V1_TOOLS_ENABLED=true`, `tools`, `tool_choice`, `parallel_tool_calls`, assistant `tool_calls` and `tool` turns are accepted and every call is decided before release; off (the default) keeps the refusal. Link [Tool calling](features.md#tool-calling). Still not: `functions`/`function_call`, real streaming.
  - `:50` Settings sentence: add `V1_TOOLS_ENABLED`, `V1_TOOL_MODELS`.
  - `:62` MCP bullet "Tool-call auditing ... needs a schema addition": now exists for `/v1` tool calls (`action_decisions`, linked by `audit_id`); MCP `tools/call` would reuse it.
  - `:78` "**Built (PRD-016), not yet called.**" → "**Built (PRD-016), called by `/v1` (PRD-017).**" keep the catalogue sentence.
  - `:80` "What PRD-017 adds" → past tense, what shipped: accepted under the flag; each `tool_call` evaluated after the model answered and before the response leaves; a denied call dropped and replaced by a note, the others released (`finish_reason` rule); each decision linked to its `audit_id` (`GET /audit/actions?audit_id=`); fail closed; the Actions view's empty state reworded. Remove "Until then the checkbox above stays unticked."
  - `:82` "these rules are what will stop the model acting on it" → "are what stop the model acting on it".
- **Validate**: `grep -n -E "not yet called|Not yet|stays unticked|- \[ \] \[Action policy" docs/roadmap.md` → no hits.

### Task 8: `docs/api.md`, `docs/configuration.md`, `docs/deployment.md`

- **Files / Implement**:
  - `docs/api.md:195` `ingress` row: drop "once it exists" (v1 exists since PRD-015). `:200` `has_tool_calls`: D19 definition (request carried an assistant `tool_calls` or `tool` turn, or the upstream response carried calls before release); `false` with `V1_TOOLS_ENABLED=false`. The rest of `api.md` was checked: no `/v1` section, no `finish_reason`/`harness.actions`/refusal text exists to update; STORY-013's `?audit_id=` and stats edits stand.
  - `docs/configuration.md`: two rows inserted before `ACTION_POLICY_FILE` (`:51`), Settings order: `V1_TOOLS_ENABLED` (No, `false`, F1/F2, link features `#tool-calling`, "configure `ACTION_POLICY_FILE` first") and `V1_TOOL_MODELS` (No, empty, F3). `:51` "Built and tested, not yet called by `/v1` (PRD-017)" → "Decides every `/v1` tool call when `V1_TOOLS_ENABLED=true`". `:14` "the OpenAI-compatible endpoint PRD-014 will add" → "the OpenAI-compatible endpoint (PRD-015)".
  - `docs/deployment.md:23`: "nothing writes it yet ... empty until PRD-017" → written for every `/v1` tool call while `V1_TOOLS_ENABLED=true` (empty with the flag off); `audit_id` links each row to its request's `audit_logs` row (no foreign key); keep the T10 preview warning verbatim.
- **Validate**: `grep -rn -E "not yet called|until tool calling exists|once it exists|nothing writes it yet|PRD-014 will add" docs` → no hits.

### Task 9: Promotion verified, Milestone 2

- **Files**: `pre-prds/PRE-PRD-016-tool-calling.md` (verify), `pre-prds/README.md` (update)
- **Implement**: Verified at planning: brief frontmatter `status: promoted`, `prd: .agents/PRDs/PRD-017-tool-calling/PRD.md` (`PRE-PRD-016-tool-calling.md:5-6`); hand-off note `:59` links PRD-017; track row `pre-prds/README.md:22` links PRD-017 and says `promoted`. Re-check at implement time; fix only if drifted. Update `pre-prds/README.md:36` to: `- **Milestone 2** — PRD-017 done (brief 016): drop-in for OpenCode and Cline in agent mode. **Reached 2026-11-16**: the brief became [PRD-017](../.agents/PRDs/PRD-017-tool-calling/PRD.md), whose 18 stories are done on `epic/PRD-017-tool-calling` (not yet merged to `main`); OpenCode 2.0.10 and the Cline CLI 3.0.74 each completed the scripted E2E task with a denied `DROP TABLE`. See [Tool calling](../docs/features.md#tool-calling).` Also `:35` PRD-016 line: "not yet called by `/v1`; PRD-017 wires it" → "called by `/v1` since PRD-017".
- **Validate**: Task 10.

### Task 10: Link and anchor check

- Run the Task 1 script. **Zero NEW failures**; new anchors `#tool-calling`, `#setting-up-opencode`, `#setting-up-cline` (features.md) resolve from README, roadmap and pre-prds. Pre-existing failures (if any) go in the report, not fixed unless in a line this story edits.

### Task 11: Targeted validation (not the full suite)

- `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q -p no:cacheprovider` — record counts.
- `.venv/Scripts/python -c "from app.main import app; print('OK')"`.
- `git diff --stat` — only the files in *Files to Change* plus `.agents/` bookkeeping; nothing under `app/` or `chat_ui/`; under `tests/` only `tests/test_config.py`.
- `git diff -- tests/test_config.py | grep '^-' | grep -v '^---'` — only the section-comment lines removed (no assertion).
- Report: "Full suite: deferred to orchestrator (user decision)".

### Task 12: Bookkeeping (implement.md Phase 5)

- Commit 1 `docs(PRD-017): STORY-018 tool calling documented as shipped; client setup; Milestone 2` — the files above, the archived plan, the report with `commit: pending`. Stage explicitly.
- Commit 2 `chore(PRD-017): STORY-018 report; update status + index` — SHA into report and story, story `status: done`, `report:` path, **PRD `status: done`** and `updated: 2026-11-16` (PRD-016 STORY-020 precedent, its chore commit), regenerate the index (`PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-017`, `errors: none`).

---

## Orchestrator-note coverage checklist

| Note | Where it lands |
|---|---|
| STORY-017 plan: Cline auth/run with absolute `--data-dir`, relative falls back to api.openai.com, `-t` not honoured / `submit_and_exit`, feature-flag fetch, `opaque_tools: {submit_and_exit: allow}`, own `tools:`/`shell.allow` | features.md `#### Setting up Cline` (Task 4.13); README Cline block (Task 6); features `:279` (Task 5) |
| STORY-016: `@ai-sdk/openai-compatible` + `options.baseURL`, `OPENCODE_CONFIG_CONTENT`, `agent.title.disable`, `OPENCODE_DISABLE_MODELS_FETCH=1`, `run --standalone`, stdin closed, `PWD`, `store` → `ignored_params` | features.md `#### Setting up OpenCode` (Task 4.12); README OpenCode block |
| STORY-001: features `:279` tool names (2.0.10 `shell`, `patch`, `path`; `execute` always denied; Cline CLI 3.0.74 setup) | Task 5 (`:279`) + Task 4.13 |
| Report deviations: STORY-003 null handling; STORY-005 rule 4; STORY-010 mark-failed (D8); STORY-011 text-only rule; STORY-013 api.md edits; STORY-015 latency; STORY-016 PWD finding; STORY-017 `apply_patch` reads `input` in the Cline template | Facts F8, F6, F16, F11, Task 8, F18, F20, F22 |
| api.md: anything else stale | Task 8 (`:195`, `:200`; no `/v1` section exists) |
| Pre-PRD promotion verified; Milestone 2 | Task 9 |
| Relative-link check | Tasks 1, 10 |
| README proportionate, links to features.md | Task 6 |

---

## End-to-End Tests

- [ ] Link checker: 0 new failures against the HEAD baseline (Task 10).
- [ ] `tests/test_config.py` green, including the two new `.env.example` tests.
- [ ] Every command and config in the two setup sections matches `tests/e2e/_opencode.py` / `_cline.py` / `test_opencode.py:352` / `tests/e2e/cline/action_policy.yaml` token for token (read side by side; placeholders only for the token, base URL and paths).
- [ ] The denial-note text in the docs equals `tool_release.DENIAL_NOTE_TEMPLATE` (`app/services/tool_release.py:41`); the refusal strings equal `v1_translate.py:146,152,155`.
- No live E2E rerun: the docs quote the recorded runs (STORY-016/017 reports).

## Validation

```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q -p no:cacheprovider
.venv/Scripts/python -c "from app.main import app; print('OK')"
.venv/Scripts/python -I "C:/Users/nahue/AppData/Local/Temp/claude/3538ad6943244944/07c1d677-d9dc-4535-8925-6e718a3d991a/scratchpad/linkcheck018.py"
grep -rn -E "not yet called|until tool calling exists|reachable by tests only|stays unticked" README.md docs .env.example
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-017   # errors: none
```

## Risks

| Risk | Mitigation |
|---|---|
| Docs restate the original PRD where it was amended | Write from the Facts table; F6, F8, F11, F16 name the amendments explicitly |
| Client setup drifts from what ran | Copy from `_opencode.py` / `_cline.py` / the policy template; E2E checklist item compares side by side |
| Claiming hot reload of the flag | F4: settings are read at startup; say "restart" |
| Over-claiming protection (history calls, schemas, MCP inside `execute`) | "What it does not cover" list (F17) mirrors PRD 9.2/9.4 and SOURCES.md |
| README bloat | README section ≤ ~35 lines, links to features.md anchors |
| Link checker flags pre-existing breakage | Baseline comparison; only new failures fixed |
| `.env.example` placement breaks an existing order test | New vars between `V1_SSE_KEEPALIVE_SECONDS` and `ACTION_POLICY_FILE` = Settings order; run `tests/test_config.py` |

## Open questions for the orchestrator (defaults applied if unanswered)

1. `docs/configuration.md` still has no rows for `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, `OPENROUTER_BASE_URL` (pre-existing gap recorded by PRD-016 STORY-020). Default: add only the two tool rows; note the gap again.
2. Roadmap: the AC says "the Action policy checkbox is ticked". Default: move it to *Shipped* as `[x]` (as PRD-016 STORY-020 moved the endpoint), rather than ticking it in place under *Planned*.
3. `.env.example` presence tests in `tests/test_config.py` (PRD-016 STORY-020 Q4 precedent). Default: yes.
4. PRD `status: draft` → `done` in the chore commit (PRD-016 precedent). Default: yes.
5. Milestone 2 wording says "not yet merged to `main`" (true today; the merge is the orchestrator's). Default: as written.

## Acceptance Criteria

(Copied from story `STORY-018`)

- [ ] Given `docs/features.md`, when read, then a *Tool calling* section describes the flag, `V1_TOOL_MODELS`, the order of steps (configure `ACTION_POLICY_FILE` first), what each check does with tool content (PRD-017 Section 6.5), the denial note and `finish_reason` rule, `harness.actions`, the buffered tool-call deltas, the dedup rule for tool loops, and the limits (no execution, history calls not re-evaluated, tool schemas not inspected, `functions` refused); the *Action policy rules* section no longer says nothing calls the engine. — Tasks 4, 5
- [ ] Given the README and `docs/features.md`, when read, then they give per-client setup for OpenCode and Cline (provider config, model name, workspace root and `shell.allow`, the Cline `tools:` mapping) taken from the E2E runs. — Tasks 4.12, 4.13, 6
- [ ] Given `docs/roadmap.md`, when read, then the *OpenAI-compatible endpoint* "Not yet" paragraph and the *Action policy rules* "What PRD-017 adds" paragraph describe what shipped, and the Action policy checkbox is ticked. — Task 7
- [ ] Given `.env.example`, when read, then `V1_TOOLS_ENABLED` and `V1_TOOL_MODELS` are present with comments in the existing style. — Tasks 2, 3
- [ ] Given `pre-prds/PRE-PRD-016-tool-calling.md` and `pre-prds/README.md`, when checked, then the brief is `status: promoted` with `prd:` pointing at this PRD, the track table links PRD-017, and Milestone 2 is marked reached; every relative link in the changed docs resolves. — Tasks 9, 10
- [ ] All tasks completed
- [ ] Backend imports (`from app.main import app`)
- [ ] Follows existing patterns (PRD-016 STORY-020 structure and tone)
