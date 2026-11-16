---
story: STORY-001
prd: PRD-017
slug: client-survey
title: "Client survey: OpenCode 2.0.10 and Cline request/response shapes; PRD-016 mappings re-verified"
type: SPIKE
complexity: MEDIUM
epic_branch: epic/PRD-017-tool-calling        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: Client survey: OpenCode 2.0.10 and Cline request/response shapes; PRD-016 mappings re-verified

## Summary

This story is mostly research. It produces three things:

1. **`tests/corpora/actions/SOURCES.md` updated.** It gains a new `## OpenCode 2.x` section (OpenCode 2.0.10, the version installed on the dev machine) and a `### Cline CLI 3.0.74` subsection. Both use the provenance format PRD-016 used: client, version, commit, schema location. A new *Differences from the PRD-016 survey* section says what changed since OpenCode v1.19.5 and Cline 4.1.26.
2. **A new spike note, `.agents/spikes/PRD-017-tool-calling/client-survey.md`.** For each client it gives the top-level request keys sent with tools on, how history `tool_calls` and `tool` turns are written, and how streamed `tool_calls` deltas are read. It also says how STORY-017 drives Cline headlessly against a custom base URL.
3. **Data corrections to the built-in mapping, with tests.** The planner's exploration already shows that **OpenCode drifted a lot in 2.0**: `bash` became `shell`, `apply_patch` became `patch`, `task` became `subagent`, and `read`, `write` and `edit` now take `path` instead of `filePath`. There is also a new CodeMode `execute` tool. The fixes are data in `BUILT_IN_TOOLS`, plus adapter cases and synthetic corpus files. v1.19.5's names stay as candidates, because v1.19.5 is the release from 2026-10-28 and is still supported.

**Deviation from the story text (follows the code).** The story says the mapping lives in `app/services/action_config.py`, but the data is `BUILT_IN_TOOLS` in `app/services/action_adapters.py:509-578`. `action_config` imports it (`action_config.py:55`) and puts it into the policy unchanged (`action_config.py:474-478`, `:724-731`). The correction is made in `action_adapters.py`. `action_config.py` is not edited. Report this to the orchestrator.

No request-path code changes: nothing in `v1_translate`, `openrouter_client`, `query_pipeline` or the stub.

## User Story

As the PRD-017 implementer
I want to know exactly what OpenCode 2.0.10 and the current Cline send and expect on a tool-calling `/v1` request
So that the request translator accepts their shapes and the action policy's built-in mappings name their real tools

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-001-client-survey.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md`: Sections 8 (Clients, line ~185), 12 Phase 1, 14 Risks 3 and 7, 6.6 (buffered SSE: one complete fragment per index)
- Prior survey: `tests/corpora/actions/SOURCES.md`, `.agents/spikes/PRD-016-action-policy-rules/threat-model.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | SPIKE (research, docs, mapping data and its tests) |
| Complexity | MEDIUM |
| Systems Affected | `tests/corpora/actions/` (SOURCES.md, synthetic corpus), `app/services/action_adapters.py` (`BUILT_IN_TOOLS` data only), `tests/test_action_adapters.py`, `tests/test_action_corpus.py`, `.gitignore`, `.agents/spikes/PRD-017-tool-calling/` |
| Story | STORY-001 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` contains only `frontend-design`. Its description is about UI work, and this story has no UI. The story frontmatter's `skills: []` agrees. **No skill applies.**

---

## Findings from Exploration (planner, 2026-11-15). Re-verify each one; do not copy unverified

### Pinned refs

| Client | Version | How pinned | Ref |
|---|---|---|---|
| OpenCode | 2.0.10 | `C:/Users/nahue/AppData/Roaming/npm/node_modules/@opencode/cli/package.json` → `"version": "2.0.10"` | tag `v2.0.10` = `b8cedc1a7a5e2916bbb65dc1d4b620729c261638` (`git ls-remote --tags https://github.com/anomalyco/opencode`). Neighbours: v2.0.9 `6608799d`, v2.0.11 `9eb6902a` |
| Cline CLI | 3.0.74 (npm `latest`, published 2026-10-26; nightly `3.0.73-nightly.…`) | `npm view cline` | npm has no `gitHead`. `apps/cli/package.json` at tag `v4.1.26` (`a459f1d04dea030833b558be645011ab739c463b`, **the same commit PRD-016 surveyed**) says `"name": "@cline/cli", "version": "3.0.74"`. The npm deps `@cline/core` / `@cline/llms` `0.2.0` match `sdk/packages/{core,llms}/package.json` at that tag |

### OpenCode 2.0.10: where the tool definitions are

The npm package has **no JS source**. `@opencode/cli/bin/opencode.exe` (201,061,416 bytes) is a Bun single-file executable whose bundle is embedded as text. The same file is under `node_modules/@opencode/cli-windows-x64/bin/opencode.exe`: hard-link count 2, and the sha256 prefix `0c621cb01093d575aed7` matches. **Read the installed binary as ground truth, and the upstream source at `b8cedc1a` for line-cited links.**

- **Installed binary.** Each tool is a plugin `{id:"opencode.tool.<x>", …}` that registers `tool.transform((f)=>f.add({name:<var>, options:{codemode:!1}, …, input:<schema>}))`. Planner offsets (decimal bytes): question 147930531, patch 148475077, edit 148481789, glob 148485496, grep 148488256, read 148501112, shell 148513097, skill 148516854, subagent 148519778, webfetch 148613555, websearch 148615482, write 148618500. The CodeMode `execute` tool is built at 147645227 (`Td=(e,n)=>({name:"execute",…,input:Kp`, with `Kp=o({code:t})` at 147637362), and the tool snapshot that decides what is advertised is at 147652690. The method: `grep -a -b -o 'id:"opencode\.tool\.[a-z_]*"'`, then read about 1.5 KB before and 6 KB after each offset with a small `python -I` window reader kept in the scratchpad. Never execute anything from the bundle.
- **Upstream source at `b8cedc1a`** (`gh api "repos/anomalyco/opencode/git/trees/b8cedc1a…?recursive=1"`): `packages/core/src/tool/plugin/{shell,read,write,edit,patch,glob,grep,webfetch,websearch,subagent,skill,question}.ts`, `packages/core/src/tool/patch.txt`, `packages/core/src/vcs/patch.ts` (patch parser: confirm the header grammar), `packages/core/src/tool/mcp.ts`, `packages/core/src/codemode/tool.ts` and `packages/codemode/src/{codemode.ts,tool.ts}` (`execute`), `packages/core/src/tool.ts` / `packages/core/src/tool/runtime.ts` (registry and snapshot: find the file that holds `codemode===!1` filtering and `exposedToolName`).

What the planner read in the binary:

| v2.0.10 tool | Keys (advertised schema) | v1.19.5 equivalent | Drift |
|---|---|---|---|
| `shell` | `command`, `workdir?`, `timeout?`, `background?` | `bash` (`command`) | **renamed** |
| `read` | `path` ("File or directory to read"), `offset?`, `limit?` | `read` (`filePath`) | **key renamed**; it now also lists directories |
| `write` | `path`, `content` | `write` (`filePath`) | **key renamed** |
| `edit` | `path`, `oldString`, `newString`, `replaceAll?` | `edit` (`filePath`) | **key renamed** |
| `patch` | `patchText` | `apply_patch` (`patchText`) | **renamed**. The gpt- rule is still there: `patch` is advertised instead of `edit`/`write` when the model id contains `gpt-` and contains neither `oss` nor `gpt-4` (offset ~148478894). The bundle has `*** Add File:`, `*** Update File:`, `*** Delete File:`, `*** Move to:`, `*** Begin Patch` / `*** End Patch`, plus a new **`*** Environment ID:`** string (offset ~94944916). Find out what it does in `vcs/patch.ts` |
| `glob` | `pattern`, `path?`, `hidden?`, `limit?` | same | none for the target keys |
| `grep` | `pattern`, `path?`, `include?`, … | same | none for the target keys |
| `webfetch` | `url`, `format`, `timeout?` | same | none |
| `websearch` | `query` | same | none (`none` row) |
| `subagent` | `description`, `prompt`, `model?`, `sessionID?`, `background?` | `task` | **renamed** (`none` row) |
| `skill` | `id` | `skill` | key changed, still `none` |
| `question` | `questions[]` | same | none |
| `execute` (CodeMode) | `code` (JavaScript) | — | **new**. Advertised whenever at least one registered tool has `codemode !== false` and `execute` is not permission-denied. The `opencode` namespace tools (`session_rename`, `session_move`, `models`, offsets 148492470-148493673) are `codemode:!0`, so `execute` is probably advertised in every session. Confirm with a live capture. Its description says `fetch` is available inside the code, and **MCP tools are `codemode` by default** (offset 147912996), so they are called inside `execute.code` and do not arrive as their own `tool_calls` |
| — | — | `lsp`, `todowrite`, `plan_exit`, `invalid`, `list` | **gone from the direct tool set** (`todowrite`, `plan_exit`: 0 occurrences in the bundle; no `opencode.tool.lsp`). Confirm in source |

MCP naming when a server sets `codemode: false`: the exposed name is `${namespace.replaceAll(".","_")}_${sanitized name}`, with namespace `sanitize(server)` (offsets 147645227 region `ti=`, 161283546 `exposedToolName`). That is the same `<server>_<tool>` shape as v1.19.5.

### OpenCode 2.0.10: request shape (upstream `packages/ai/src/protocols/openai-chat.ts` at `b8cedc1a`, 1,207 lines; `openai-compatible-chat.ts` reuses it end to end)

- Body fields `:136-150`: `model`, `messages`, `tools`, `tool_choice`, `stream: Literal(true)`, `stream_options {include_usage}`, `store`, `prompt_cache_key`, `reasoning_effort`, `tool_stream`, `max_completion_tokens` / `max_tokens`, `temperature`, `top_p`, … **There is no `parallel_tool_calls`.**
- Body build `:760-790`: **`tools: []` is sent when the history has tool calls but no tool is active.** `tool_choice` is sent only with active tools. `stream` is always `true`. `stream_options` is sent only when the provider supports usage in streaming. `tool_stream` is zai-only.
- Assistant lowering `:425-431`: `content` is the joined text, or **`null` when there is no text and there are tool calls**, or `""` when there is neither. `tool_calls` is present only when there are calls. It can also carry `reasoning_details`, `cache_control` and a reasoning field.
- Tool lowering `:436-462`: `{role:"tool", tool_call_id, content: <string>, cache_control?}`. Text parts are joined with `\n`. File parts of a tool result go into a separate message (read `:462+`).
- Stream parsing `:970-1010+`: tool deltas are accumulated per index. **Content or tool deltas after a `finish_reason` are an error** ("OpenAI Chat received content after the finish reason"), so the finish chunk must come last (PRD 6.6 already does this). Read to the end of the function to confirm that one complete `arguments` fragment per index is accepted.
- A real recorded tool loop: `packages/ai/test/fixtures/recordings/openai-compatible-chat/groq-llama-3-3-70b-drives-a-tool-loop.json` (11 fixtures in that directory).
- Config without touching the user's home: the binary reads `OPENCODE_CONFIG_CONTENT`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DB`, `OPENCODE_TEST_HOME` and `OPENCODE_DISABLE_PROJECT_CONFIG`. Provider config is in `packages/core/src/v1/config/provider.ts` and `packages/ai/src/providers/openai-compatible.ts`.

### Cline CLI 3.0.74

- `npm view cline@3.0.74`: `bin: {cline: "bin/cline"}`, postinstall `node ./postinstall.mjs || true`, `optionalDependencies` `@cline/cli-windows-x64@3.0.74` (a compiled binary, `bin/cline.exe`, 143 MB). Apache-2.0.
- README (`npm view cline@3.0.74 readme`): there is a headless mode: `--json` (NDJSON, non-interactive, needs a prompt argument or stdin), `-y/--yolo` (skips approvals, enables `submit_and_exit`, disables spawn/team tools), `-c/--cwd`, `-P/--provider`, `-m/--model`, `-k/--key`, `-t/--timeout`, and `--data-dir <path>` ("isolated local state … enables sandbox mode automatically"). `cline auth --provider <id> --apikey … --modelid … --baseurl <url>`.
- `apps/cli/src/commands/auth.ts` at `a459f1d0`: `-b, --baseurl <url>` (`:91`). A base URL is accepted only for `BUILT_IN_PROVIDER.OPENAI_COMPATIBLE` or `OPENAI_NATIVE` (`:151-155`). `sdk/packages/llms/src/providers/ids.ts:18-19`: `OPENAI_COMPATIBLE = "openai-compatible"`, `OPENAI_NATIVE = "openai-native"`, and `openai` is an alias of `openai-compatible` (`:85`).
- **The tool names should be unchanged.** The CLI is built from the same commit as the PRD-016 survey, and `sdk/packages/core/src/extensions/tools/constants.ts:12-22` lists the same nine names. Still read `apps/cli/src/runtime/tools.ts` for extra CLI tools (`sdk/packages/core/src/extensions/tools/team/{spawn-agent-tool,team-tools}.ts`, disabled under `--yolo`), and grep the installed `cline.exe` bundle for the nine names.
- Request shape: `sdk/packages/llms/src/providers/vendors/openai-compatible.ts` and **`openai-compatible.wire.test.ts`** (a wire-level test), `sdk/packages/llms/src/providers/ai-sdk.ts:867-887`, and `@ai-sdk/openai-compatible` `^3.0.67` (`sdk/packages/llms/package.json`). Pin the exact version from the lockfile at the tag.

### Repository coupling (what a mapping change breaks)

- `tests/test_action_adapters.py:59-76` parses every SOURCES.md table whose header starts `| Client | Tool | Operation kind | Target key |`. `:95-100` pins **41 rows, 16 OpenCode, 9 Cline 4.x, 12 Cline 3.x**. `:108-124` checks each row against `BUILT_IN_TOOLS`. `:127-129` checks that the mapped names equal `BUILT_IN_TOOLS` and pins **24**. `:148-207` requires a `_REALISTIC` sample for every mapped `(client, tool, key)`.
- `tests/test_action_corpus.py:145`: `_CLIENTS = ("OpenCode", "Cline 4.x", "Cline 3.x", "MCP")` is a closed vocabulary, read at `:265`. `:512-525`: every non-`tool.unknown` synthetic file's `(client, tool)` must be a SOURCES.md row.
- `tests/test_action_config.py:1118-1128`: `examples/action_policy.yaml` loads with **7** tools. **This story does not touch it** (see Risks).
- `docs/features.md:279` lists the OpenCode v1.19.5 names. That is a docs hand-off to STORY-018, not edited here.
- No test pins a `policy_digest()` value (`tests/test_action_config.py:361`, `:629`, `:678` only compare digests).

---

## Patterns to Follow

### SOURCES.md provenance header and table (parsed by the test, so keep the header byte-exact)
```
// SOURCE: tests/corpora/actions/SOURCES.md:33-43
## OpenCode

- **Upstream**: `anomalyco/opencode` (formerly `sst/opencode`), `packages/opencode/src/tool/`
- **Tag**: `v1.19.5` (2026-10-28), the latest release on 2026-11-15
- **Commit**: `810c0eba1a7348036f8bdf61e6632d0c36c6876c` (lightweight tag on a commit). ...
- **License**: MIT
- **Schema location**: the tool id is the first argument of `Tool.define(...)`. ...

| Client | Tool | Operation kind | Target key | Multi-target | Paths | Version | Commit | Schema |
|---|---|---|---|---|---|---|---|---|
| OpenCode | `bash` | `shell` | `command` | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba…/packages/opencode/src/tool/shell/prompt.ts#L15-L23 |
```

### Mapping data: one key, two spellings (the alternatives grammar)
```
// SOURCE: app/services/action_adapters.py:555-558
        # Native GPT-5 / next-gen variants send `absolutePath`, the GENERIC
        # spec (also native for gemini3 and xs) sends `path`.
        "write_to_file": ToolMapping("fs_write", "absolutePath|path"),
        "replace_in_file": ToolMapping("fs_write", "absolutePath|path"),
```
```
// SOURCE: app/services/action_adapters.py:515-517
        # Shared name: OpenCode sends `patchText`, Cline 4.x and 3.x send
        # `input`. One fs_write per header (S1); both keys present is Malformed.
        "apply_patch": ToolMapping("fs_write", "patchText|input", format="patch"),
```

### Error handling (the adapter fails closed; messages name the key path, never a value)
```
// SOURCE: app/services/action_adapters.py:375-380
    present = [key for key in groups if key in obj]
    if len(present) > 1:
        # Which spelling the executor prefers when it gets two is not
        # documented, so neither choice is safe (S2, orchestrator decision).
        names = " and ".join(f"'{prefix}{key}'" for key in present)
        raise _MalformedArguments(f"more than one spelling of the target is present: {names}")
```

### Tests: SOURCES-driven parametrization and realistic samples
```
// SOURCE: tests/test_action_adapters.py:95-100, 148-152
def test_sources_parser_reads_every_row():
    # 16 OpenCode + 9 Cline 4.x + 12 Cline 3.x + 4 SQL; a broken parser fails here.
    assert len(_ROWS) == 41
    ...
_REALISTIC = {
    ("OpenCode", "bash", "command"): (
        {"command": "ls -la", "description": "List files", "timeout": 1000},
        ("ls -la",),
    ),
```

### Synthetic corpus file
```
// SOURCE: tests/corpora/actions/synthetic/ordinary-opencode-write-relative.yaml
# Ordinary work: a relative write. OpenCode `write` (SOURCES.md: OpenCode v1.19.5; target `filePath`).
tool_call:
  name: write
  arguments: '{"filePath":"src/a.ts","content":"x"}'
policy: built_in
client: OpenCode
category: ordinary
expect: {user: allow, dba: allow, admin: allow}
rule: fs.write_in_workspace
note: 'A relative path that stays below the working directory is inside the workspace.'
```

### Spike note frontmatter
```
// SOURCE: .agents/spikes/PRD-016-action-policy-rules/threat-model.md:1-6
---
prd: PRD-016
story: STORY-001
date: 2026-11-15
conclusion: 8 of 13 threats answered by a Section 6.3 rule; ...
---
```

### Recording proxy (names only, never content)
```
// SOURCE: tests/e2e/_live.py:270-282
def request_shape(body: dict) -> dict:
    """What `Recorder` keeps of one request: names, roles and the model. Never content."""
    ...
        **{key: _shape(body[key]) if key in body else "absent" for key in ("tools", "tool_choice", "functions")},
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.agents/spikes/PRD-017-tool-calling/client-survey.md` | CREATE | AC2, AC4: request shapes per client, delta expectations, the Cline headless method, hand-offs |
| `tests/corpora/actions/SOURCES.md` | UPDATE | AC1: `## OpenCode 2.x` section and table, `### Cline CLI 3.0.74` subsection, *Differences from the PRD-016 survey*, updated *What this survey shows* |
| `app/services/action_adapters.py` | UPDATE | AC3: `BUILT_IN_TOOLS` data only (lines 503-578): add `shell` and `patch`; `read`/`write`/`edit` targets become `filePath\|path`; comments cite PRD-017 STORY-001 |
| `tests/test_action_adapters.py` | UPDATE | AC3: counts (each edit commented with PRD-017 STORY-001), `_REALISTIC` entries for the new rows, new focused cases |
| `tests/test_action_corpus.py` | UPDATE | Add `"OpenCode 2.x"` to `_CLIENTS` (`:145`) and to the docstring's `client:` vocabulary (`:18`) |
| `tests/corpora/actions/synthetic/ordinary-opencode2-*.yaml`, `rule-opencode2-*.yaml` | CREATE | AC3: synthetic cases for the 2.x shapes (about 5 files) |
| `.gitignore` | UPDATE | Add `tests/e2e/.clients/` (the Cline install dir) |

Not changed: `app/services/action_config.py` (it holds no tool data; see Summary), `examples/action_policy.yaml`, `docs/features.md`, README, every request-path module.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Pin the versions and refs

- **File**: none (notes for Tasks 7 and 10)
- **Action**: verify
- **Implement**:
  - `opencode --version` → `2.0.10`. Record the sha256 of `C:/Users/nahue/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe`. `git ls-remote --tags https://github.com/anomalyco/opencode | grep v2.0.10` → `b8cedc1a7a5e2916bbb65dc1d4b620729c261638`. Record the tag date from `gh api repos/anomalyco/opencode/git/commits/b8cedc1a…`, and whether v2.0.11 (`9eb6902a`) exists. It does: so 2.0.10 is **not** the latest, and the note must say so.
  - `npm view cline dist-tags version time --json` → pin **`cline@3.0.74`**. Confirm `apps/cli/package.json` at `a459f1d0` says `3.0.74`, and record that npm carries no `gitHead`, so the pin to `a459f1d0` rests on that manifest plus the matching `@cline/*@0.2.0` deps.
  - **Do not** upgrade or reinstall OpenCode.
- **Validate**: each ref written in the note resolves: `gh api repos/<owner>/<repo>/commits/<sha> --jq .sha`.

### Task 2: Read OpenCode 2.0.10's tool schemas

- **File**: none (data for Task 7)
- **Action**: read
- **Implement**:
  - For each of `shell, read, write, edit, patch, glob, grep, webfetch, websearch, subagent, skill, question`, read `packages/core/src/tool/plugin/<x>.ts` at `b8cedc1a` (`gh api "repos/anomalyco/opencode/contents/<path>?ref=b8cedc1a…" --jq .content | base64 -d` into a new scratchpad directory). Record the advertised name, the parameter struct and its line range, and how the executor resolves a relative `path`: absolute vs relative, for the *Absolute and relative paths* section.
  - Cross-check every name and key against the installed binary (offsets above). **A disagreement means the binary wins.** Record it.
  - Read the patch plugin and `packages/core/src/vcs/patch.ts`. Confirm the header grammar, what `*** Environment ID:` is, and whether one patch can target another environment or root. Confirm the gpt- rule and its line.
  - Find the registry/snapshot file (the one with the `codemode===!1` split and `exposedToolName`). Record exactly when `execute` is advertised, what `code` can reach (`fetch`, `tools.<ns>.<name>`), and that MCP tools default to CodeMode.
  - Confirm that `lsp`, `todowrite`, `plan_exit`, `invalid` and `list` are absent from the direct tool set.
- **Validate**: every 2.x table row gets a commit-pinned URL with `#Lx-Ly` that opens on the parameter struct.

### Task 3: Read OpenCode 2.0.10's request and stream shapes

- **File**: none (data for Task 10)
- **Action**: read
- **Implement**: read `packages/ai/src/protocols/openai-chat.ts` at `b8cedc1a` end to end. Cite: body fields (`:136-150`), body build (`:755-790`, including `tools: []` with history), assistant lowering (`:425-431`), tool lowering (`:436-470`), the delta accumulator (`:970+`: does one complete `arguments` fragment per index finish a call, and what happens to `finish_reason: "tool_calls"`?), and the late-content error. Read the recorded `groq-llama-3-3-70b-drives-a-tool-loop.json` fixture for a real request/response pair, keys only. Read `packages/ai/src/providers/openai-compatible.ts` and `packages/core/src/v1/config/provider.ts` for how a custom OpenAI-compatible base URL is configured, and which config env vars isolate a run from the user's home (`OPENCODE_CONFIG_CONTENT`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DB`, `OPENCODE_TEST_HOME`).
- **Validate**: each claim in the note's OpenCode section has a `file#Lx-Ly` link at `b8cedc1a`.

### Task 4: Install Cline CLI locally (git-ignored, pinned, never global)

- **File**: `.gitignore`
- **Action**: UPDATE, then a local install
- **Implement**:
  - Append `tests/e2e/.clients/` to `.gitignore` (after the existing entries; one-line comment: `# PRD-017 STORY-001: pinned client installs for the E2E (never npm -g)`).
  - From the repo root (Git Bash): `npm install --prefix tests/e2e/.clients/cline --save-exact --no-audit --no-fund cline@3.0.74`
  - Verify: `tests/e2e/.clients/cline/node_modules/.bin/cline --version` (→ `3.0.74`), `… cline --help`, `… cline auth --help`. Record whether `--data-dir` is a global option that `auth` honours, or whether `CLINE_DATA_DIR` is needed for `auth`. **Never run `cline auth` without `--data-dir` / `CLINE_DATA_DIR`** pointing under `tests/e2e/.clients/cline-data/`, so the user's `~/.cline` is never written.
  - `git status --porcelain` must not list anything under `tests/e2e/.clients/`.
- **Validate**: `git check-ignore tests/e2e/.clients/cline/package.json` prints the path.

### Task 5: Read Cline's tool set and request shapes

- **File**: none (data for Tasks 7 and 10)
- **Action**: read
- **Implement**:
  - `apps/cli/src/runtime/tools.ts` at `a459f1d0`: which tools the CLI advertises in `--yolo --json` act mode (the nine SDK names, plus or minus `submit_and_exit`, spawn and team tools). Grep the installed `@cline/cli-windows-x64` `cline.exe` bundle for the nine names and the `inputSchema` keys (`commands`, `files`, `requests`, `input`, `path`), the same way as the OpenCode binary. Any drift from SOURCES.md's Cline 4.x table is a finding.
  - `sdk/packages/llms/src/providers/vendors/openai-compatible.ts`, `openai-compatible.wire.test.ts`, `ai-sdk.ts:867-887`. Pin the exact `@ai-sdk/openai-compatible` version from the lockfile at `a459f1d0`. `npm pack @ai-sdk/openai-compatible@<that version>` into a **new, empty scratchpad directory**, extract it, and read its chat message conversion (assistant `content` with tool calls: `null` or `""`, text parts, `tool_call_id`), its request body keys (`tools`, `tool_choice`, `parallel_tool_calls`?, `stream_options`), and its stream parser (incremental vs one complete fragment per index). Read only; never run anything from it.
- **Validate**: each claim in the note's Cline section has a pinned link or a `package@version:path:line` citation.

### Task 6: Live capture, time-boxed to about 45 minutes and optional

- **File**: a throwaway responder in the scratchpad only (never committed)
- **Action**: run
- **Implement**: if the source reading leaves a point open (OpenCode: is `execute` always advertised, and does `stream_options` reach a custom provider; Cline: whether headless mode works at all), write a small `http.server` responder in the scratchpad. It serves `/v1/models` and `/v1/chat/completions` on 127.0.0.1. It records **names only**, in the spirit of `tests/e2e/_live.py:262-282`: top-level keys, `stream_options` keys, `tools[].function.name`, per-message role, key set, and `content` *type* (null, `""`, str, list). It never records values. It answers the first request with one SSE `tool_calls` chunk, one complete fragment for a harmless `read` (OpenCode) or `read_files` (Cline) of a file inside a throwaway temp directory, then a finish chunk with `finish_reason: "tool_calls"`, then `[DONE]`. It answers the second request with plain text. The stub cannot reply with tool calls yet (that is STORY-014), so the stub is not used.
  - OpenCode: run with a throwaway project dir as cwd, `OPENCODE_CONFIG_CONTENT` (custom openai-compatible provider at the responder's base URL, dummy key), and `OPENCODE_DB` / `OPENCODE_CONFIG_DIR` / `OPENCODE_TEST_HOME` under the scratchpad. **Do not edit `~/.config/opencode` or any home file.** Use the non-interactive `opencode run "<prompt>"` form; confirm its flags with `opencode run --help`.
  - Cline: `cline --data-dir <scratch>/cline-data auth --provider openai-compatible --apikey dummy --modelid test-model --baseurl http://127.0.0.1:<port>/v1`, then `cline --data-dir <scratch>/cline-data --yolo --json -c <tmpdir> -P openai-compatible -m test-model -t 120 "<prompt>"`.
  - If a client cannot be run in the time box, say so in the note, and say which claims rest on source alone.
- **Validate**: the recorded shapes (names only) go into the note. No dummy key, prompt or file content is written anywhere in the repo.

### Task 7: Update `tests/corpora/actions/SOURCES.md`

- **File**: `tests/corpora/actions/SOURCES.md`
- **Action**: UPDATE
- **Implement**:
  - In the intro (`:12-15`), add a sentence saying that PRD-017 STORY-001 re-surveyed OpenCode 2.0.10 and Cline CLI 3.0.74 on 2026-11-15, by the same method, also reading the installed binaries.
  - Add a new **`## OpenCode 2.x`** section after the OpenCode section (`:33-75`). Give its provenance block: upstream `anomalyco/opencode` `packages/core/src/tool/plugin/`, tag `v2.0.10`, commit `b8cedc1a…`, license, schema location (`{id:"opencode.tool.<x>"}` plugin, `tool.transform(... add({name, input}))`), the installed binary path and sha256, and the note that v2.0.11 exists. Then a table with the **byte-exact header**, client cell **`OpenCode 2.x`**, one row per direct tool: mapped `shell`, `read`, `write`, `edit`, `patch`, `glob`, `grep`, `webfetch`, and `none` for `websearch`, `subagent`, `skill`, `question`, `execute`. **Adjust the rows to what Task 2 verified.** Then notes: renames and removals; `execute`/CodeMode (MCP tools hidden inside `code`, `fetch` available, so `execute` must stay `tool.unknown` and must **never** go into `opaque_tools`); MCP naming with `codemode: false`; the gpt- `patch` rule; `*** Environment ID:`; `shell` on Windows (PowerShell/cmd text, PRD-016 Risk 3, if still true).
  - Add a **`### Cline CLI 3.0.74`** subsection under Cline. Give its provenance (npm `cline@3.0.74`, `apps/cli` at `a459f1d0`, deps `@cline/*@0.2.0`) and the result of Task 5. If the CLI advertises the same nine names, write that in prose, **not as new table rows**: duplicate `Cline 4.x` rows would change no mapping and would only inflate the counts. If the CLI advertises extra names (spawn/team) in the mode STORY-017 uses, add them as `none` rows to the Cline 4.x table with Version `cli 3.0.74`.
  - Add **`## Differences from the PRD-016 survey`**: one row per drift (old name/key → new name/key, the version that introduced it, evidence link), then "Cline: no drift" or the drift Task 5 found.
  - Extend *Absolute and relative paths* (`:203-212`) and *Tools that name several targets* (`:214-227`) with the OpenCode 2.x lines (`patch` multi-target, `read` of a directory).
  - Update *What this survey shows, and what it does not* (`:260-266`): the pinned versions now include OpenCode 2.0.10 and Cline CLI 3.0.74, and `execute.code` is not inspected.
- **Mirror**: `tests/corpora/actions/SOURCES.md:33-75` (provenance + table + notes), `:229-241` (corrections list).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_adapters.py -k sources -q` (it fails until Tasks 8 and 9; that is expected here).

### Task 8: Correct `BUILT_IN_TOOLS` as data

- **File**: `app/services/action_adapters.py`
- **Action**: UPDATE (lines 503-578 only; no logic change)
- **Implement** (adjust to Task 2's verified facts):
  - Change the OpenCode block header comment to `OpenCode v1.19.5 (810c0eba) and 2.0.10 (b8cedc1a; PRD-017 STORY-001)`.
  - `"write"`, `"edit"`, `"read"`: `ToolMapping(<kind>, "filePath|path")`. Comment: 2.0 renamed the key, v1.19.5 still sends `filePath`, and both present is Malformed (S2).
  - Add `"shell": ToolMapping("shell", "command")`. Comment: v2.0 renamed `bash`. `bash` is kept for v1.19.5.
  - Add `"patch": ToolMapping("fs_write", "patchText", format="patch")`. Comment: v2.0 renamed `apply_patch` and kept the gpt- rule. `apply_patch` is kept for v1.19.5 and for Cline.
  - Keep `bash`, `apply_patch` and `lsp` (still-supported v1.19.5).
  - **Do not** map `execute`, `subagent` or any other `none` row.
  - Update the module docstring line 18 only if it names versions (it does not).
- **Mirror**: `app/services/action_adapters.py:555-558` (two spellings), `:515-517` (shared patch name).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 9: Adapter tests

- **File**: `tests/test_action_adapters.py`
- **Action**: UPDATE
- **Implement**:
  - `:95-100`: new row totals (planner estimate: 41 + 13 = 54, and `count("OpenCode 2.x") == 13`; use the verified numbers). Update the comment, and add `# PRD-017 STORY-001: OpenCode 2.0.10 rows added (SOURCES.md "OpenCode 2.x")`.
  - `:127-129`: `len(BUILT_IN_TOOLS) == 26` (24 + `shell` + `patch`), with a PRD-017 STORY-001 comment.
  - `_REALISTIC`: one entry per new mapped 2.x row, with sibling keys copied from the 2.x schema, e.g. `("OpenCode 2.x", "shell", "command"): ({"command": "npm test", "workdir": "/work", "timeout": 120000}, ("npm test",))`, `("OpenCode 2.x", "edit", "path"): ({"path": "/work/a.ts", "oldString": "1", "newString": "2"}, ("/work/a.ts",))`, `("OpenCode 2.x", "patch", "patchText (in patch text)"): ({"patchText": _PATCH}, _PATCH_TARGETS)`, plus `read`, `write`, `glob`, `grep` and `webfetch`.
  - New focused tests, near the existing alias tests: `edit` / `write` / `read` with **both** `filePath` and `path` → `Malformed` ("more than one spelling"); `read` with `path` naming a directory → one `fs_read`; `execute` with `{"code": "await fetch('https://x')"}` → `Unknown()` (comment: CodeMode, never opaque); `subagent` → `Unknown()`. Use the existing `_map` / `_args` helpers.
  - Do not rename or remove any test (if one must go, register it in `_DELIBERATELY_SUPERSEDED_TESTS`, `tests/test_pii_redaction_integration.py:476`).
- **Mirror**: `tests/test_action_adapters.py:148-215`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_adapters.py -q`

### Task 10: Synthetic corpus cases and the client vocabulary

- **Files**: `tests/test_action_corpus.py`, `tests/corpora/actions/synthetic/*.yaml`
- **Action**: UPDATE + CREATE
- **Implement**:
  - `tests/test_action_corpus.py:145`: `_CLIENTS = ("OpenCode", "OpenCode 2.x", "Cline 4.x", "Cline 3.x", "MCP")` with a `# PRD-017 STORY-001` comment, and the docstring vocabulary at `:18`.
  - New files, all `policy: built_in` (the example policy does not map the 2.x names), each with a header comment citing `SOURCES.md: OpenCode 2.0.10`. Work out each expected decision from the built-in policy with the sibling v1.19.5 file as the reference, and run them:
    - `ordinary-opencode2-write-relative.yaml`: `write {"path":"src/a.ts","content":"x"}` → allow, `fs.write_in_workspace` (mirror of `ordinary-opencode-write-relative.yaml`).
    - `ordinary-opencode2-edit-relative.yaml`: `edit {"path":"src/a.ts","oldString":"a","newString":"b"}` → allow.
    - `ordinary-opencode2-patch.yaml`: `patch` with a relative `*** Add File:` header → allow, `fs.write_in_workspace`.
    - `rule-opencode2-shell-unlisted.yaml` (or whichever rule the built-in policy actually yields for `shell {"command":"npm test"}`; with `shell.allow` empty, mirror the existing built-in shell file).
    - `rule-opencode2-execute-unknown.yaml`: `execute {"code":"..."}` → deny, `tool.unknown`, note: CodeMode code can `fetch` and call MCP tools, so it is never classified.
  - Shape findings for STORY-008 (`tools: []` with history, no `parallel_tool_calls`) are **not** corpus cases. They go in the spike note.
- **Mirror**: `tests/corpora/actions/synthetic/ordinary-opencode-write-relative.yaml`, `ordinary-opencode-npm-test.yaml`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_corpus.py -q` (DB-backed: needs `harness-libsql-dev` on :8080)

### Task 11: Write the spike note

- **File**: `.agents/spikes/PRD-017-tool-calling/client-survey.md`
- **Action**: CREATE
- **Implement**: frontmatter `prd: PRD-017`, `story: STORY-001`, `date: 2026-11-15`, `conclusion:` (one line: what drifted, what each client sends, how Cline runs headless). Sections:
  1. **Conclusion** (bold first sentence, as in `threat-model.md:8-10`).
  2. **Method**: sources read, binaries grepped, live capture done or not, and what rests on source alone.
  3. **OpenCode 2.0.10 request**: a table of top-level keys with tools on (`tools`, `tool_choice`, `parallel_tool_calls` absent, `stream` always true, `stream_options` conditional, plus `store`, `prompt_cache_key`, `reasoning_effort`, `max_tokens`/`max_completion_tokens`, `temperature`, `top_p`, `tool_stream`), with links.
  4. **OpenCode history**: assistant `content` null / `""` / text, `tool_calls`, extra assistant keys (`reasoning_details`, `cache_control`, reasoning field), `tool` turns (`tool_call_id`, string content, `cache_control`), file parts.
  5. **OpenCode stream expectations**: per-index accumulation, one complete fragment accepted (verified or not), error on content after the finish reason.
  6. The same three for **Cline CLI 3.0.74** (via `@ai-sdk/openai-compatible@<pinned>`).
  7. **Mapping drift and corrections**: a summary that points to SOURCES.md, with the `BUILT_IN_TOOLS` diff in words. If nothing drifted for Cline, say so explicitly (AC3).
  8. **Driving Cline headlessly (STORY-017)**: the exact install command (Task 4), `auth` with `--baseurl` under `--data-dir`, and the `--yolo --json -c -P -m -t` run, with what was verified live. If it is impossible, the fallback: replay recorded request shapes through the in-process client. Say what that cannot prove: that the agent loop really executes tools, reads the denial note, continues after a dropped call, and accepts one-fragment deltas.
  9. **Hand-offs** (each names the story):
     - STORY-008: accept `tools: []` with tool history; OpenCode sends no `parallel_tool_calls`; the extra top-level keys; `cache_control` / `reasoning_*` on messages.
     - STORY-003/008: assistant `content: null`.
     - STORY-012: finish chunk last.
     - STORY-016: tool names `shell`/`patch`, the gpt- rule, `execute` always advertised, so the E2E policy file maps `shell`/`patch` and leaves `execute` unknown; config isolation env vars.
     - STORY-017: Cline as above.
     - STORY-018: `docs/features.md:279` and `examples/action_policy.yaml` still name v1.19.5's tools only.
- **Validate**: every link is pinned to a SHA or `package@version`. No value from a live capture appears (names only).

### Task 12: Targeted validation

- **Action**: run
- **Implement**: a single pytest call: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_adapters.py tests/test_action_corpus.py tests/test_action_config.py tests/test_action_secrets.py tests/test_action_policy.py tests/test_untouched_app.py -q`, plus `.venv/Scripts/python -c "from app.main import app; print('OK')"`. Record the exact pass/fail/skip counts. **Full suite: deferred to the orchestrator (user decision).**
- **Validate**: all green. `git status --porcelain` shows only the files in *Files to Change* (plus the plan, the story and the index).

---

## End-to-End Tests

- [ ] `tests/e2e/.clients/cline/node_modules/.bin/cline --version` prints `3.0.74`, and the directory is git-ignored
- [ ] (Optional, Task 6) OpenCode 2.0.10 and Cline 3.0.74 each make two requests to the scratchpad responder (first with `tools`, second with an assistant `tool_calls` turn and a `tool` turn), and the recorded names-only shapes match the note
- [ ] No home-directory config was written (`~/.cline`, `~/.config/opencode` unchanged; every run used `--data-dir` / `OPENCODE_*` env pointing under the scratchpad or `tests/e2e/.clients/`)

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_adapters.py tests/test_action_corpus.py tests/test_action_config.py tests/test_action_secrets.py tests/test_action_policy.py tests/test_untouched_app.py -q
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-017   # must print: errors: none
git check-ignore tests/e2e/.clients/cline/package.json
```

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| The binary and the upstream tag disagree (a build from an untagged commit) | The binary is ground truth (Task 2). Record any difference. Cite binary offsets where the source differs |
| `filePath\|path` on `read` / `write` / `edit` widens what is accepted | It accepts only what a supported OpenCode version sends. Both keys present is still Malformed. Cline 4.x `editor` (`path`) is a different name, so nothing collides |
| `execute` (CodeMode) is advertised in every OpenCode 2.0 session, and models may route MCP calls and `fetch` through it | It stays `tool.unknown` (deny) in the built-in policy. The note tells STORY-016/018 to warn operators never to put it in `opaque_tools`. Classifying `code` is future work, not this story |
| `examples/action_policy.yaml` maps only v1.19.5 names, so under the sample policy every OpenCode 2.0 edit or shell call is denied | Out of this story's AC (the sample is not the built-in mapping, and its 7-tool count is pinned by `tests/test_action_config.py:1128`). Flag it to the orchestrator as a hand-off: STORY-016's policy file and STORY-018's docs. **Open question below** |
| Cline headless needs auth state, which normally lives in `~/.cline` | Always `--data-dir` (or `CLINE_DATA_DIR`) under the git-ignored dir or the scratchpad. Task 4 verifies before any `auth` call |
| Live capture executes a model-proposed tool on the dev machine | Scripted calls are a harmless `read` inside a throwaway temp dir only |
| A Cline postinstall script runs during `npm install` | It is the package's own platform-binary linker (`node ./postinstall.mjs \|\| true`). It installs into the ignored prefix, never globally |

## Open Questions for the Orchestrator

1. **The story names `action_config.py`, but the data is in `action_adapters.BUILT_IN_TOOLS`.** The plan edits `action_adapters.py` (data only). Confirm.
2. **`examples/action_policy.yaml`** (7 tools, v1.19.5 names): leave it for STORY-016/018 (plan default), or update it here to add `shell` and `patch` and use `filePath|path`, which changes the pinned count to 9?
3. Should the SOURCES.md client cell be `OpenCode 2.x`, which adds it to the corpus `_CLIENTS` vocabulary? That is the plan default, mirroring `Cline 4.x` / `Cline 3.x`.

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given OpenCode 2.0.10 (installed on the dev machine) and the Cline CLI at a pinned version, when their tool schemas are read from the installed package or the pinned source, then `tests/corpora/actions/SOURCES.md` records, per client: version, every tool name, each tool's target argument key(s) and shape, and the source location, and says where they differ from PRD-016's survey (OpenCode v1.19.5, Cline 4.1.26). (Tasks 1, 2, 4, 5, 7)
- [ ] Given each client's request to an OpenAI-compatible provider, when inspected (source, or a recording proxy run against the stub), then a new spike note `.agents/spikes/PRD-017-tool-calling/client-survey.md` lists the top-level keys it sends with tools on (`tools`, `tool_choice`, `parallel_tool_calls`, `stream`, `stream_options`, anything else), how it writes assistant `tool_calls` and `tool` turns in history (content `null` vs `""`, text parts, `tool_call_id`), and whether it expects incremental `tool_calls` deltas or accepts one complete fragment per index. (Tasks 3, 5, 6, 11)
- [ ] Given a tool whose name or argument key drifted since PRD-016, when the survey finds it, then the built-in mapping is corrected as data (old names kept as candidates where a still-supported version uses them), and `tests/test_action_adapters.py` / the synthetic corpus gain a case for the new shape; if nothing drifted, the note says so. (Tasks 8, 9, 10; OpenCode drifted, and Cline's result is stated either way)
- [ ] Given Cline, when the note is written, then it states how STORY-017 will drive it headlessly against a custom base URL (CLI flags, config file, environment), or, if that is impossible, the fallback (replaying Cline's recorded request shapes) and what that cannot prove. (Tasks 4, 6, 11)
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Targeted tests green. Full suite deferred to the orchestrator
- [ ] Follows existing patterns (SOURCES.md provenance format, `ToolMapping` alternatives, corpus file format)
