---
story: STORY-001
prd: PRD-016
slug: action-threat-model-and-adapter-survey
title: Action threat model and adapter survey (OpenCode, Cline, Aider) with SOURCES.md
type: SPIKE
complexity: LOW
epic_branch: epic/PRD-016-action-policy-rules        # all stories commit here, no per-story branch
created: 2026-11-15
---

# Plan: Action threat model and adapter survey (OpenCode, Cline, Aider) with SOURCES.md

## Summary

This story is research. It changes no code under `app/`, `chat_ui/` or `tests/*.py`. It writes two documents and corrects the PRD:

1. `tests/corpora/actions/SOURCES.md` (new directory). For every tool the built-in adapters will map, it records the exact tool name, the exact argument key that carries the target, whether the call can name several targets, whether paths are absolute or relative, the client version and commit, and the schema file URL pinned to that commit. It also states, with a source, whether Aider emits OpenAI `tool_calls`.
2. `.agents/spikes/PRD-016-action-policy-rules/threat-model.md`. It maps T1–T13 (PRD Section 9.2) to the Section 6.3 rules that answer each threat and to the corpus group (synthetic or evasion) that will prove it. Any threat that no rule answers is listed as an open finding.
3. PRD Sections 4 and 15 (plus the two factual sentences in 6.5 / 6.6 that the findings contradict), with `updated:` set.

The planner already ran the upstream lookups with `gh api` and `curl` against raw.githubusercontent.com. The pinned refs and first findings are under *Findings from Exploration*. **They change the PRD a lot.** OpenCode no longer has `list` or `patch`. Cline 4.x has replaced every tool name the PRD lists. The implementer re-verifies each fact at the pinned commit before writing it down, and does not copy this plan unverified.

## User Story

As the PRD-016 implementer
I want the real tool names and argument keys of OpenCode, Cline and Aider recorded with their source, and the action threat model written down
So that the built-in adapter mappings are facts rather than guesses and every later story tests against the same threats

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-001-action-threat-model-and-adapter-survey.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`: Sections 4 (Operations and adapters, lines 54–63), 6.3 (rule catalogue, lines 222–252), 6.5 (lines 260–270), 7 F1 (line 481–482), 9.2 (threats, lines 539–555), 15 *Assumptions to verify in STORY-001* (lines 739–742)

## Metadata

| Field | Value |
|-------|-------|
| Type | SPIKE (research and docs only) |
| Complexity | LOW |
| Systems Affected | None in code. New `tests/corpora/actions/SOURCES.md`, new `.agents/spikes/PRD-016-action-policy-rules/threat-model.md`, PRD edits, `.agents/` bookkeeping |
| Story | STORY-001 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch; checked out, clean at `d8a0fa4`) |

---

## Skills In Use

None. `.agents/skills/` holds only `frontend-design`. Its description ("visual design when building new UI") does not match a research story, and the story says `skills: []` / "Skills: none applicable. No UI."

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

Tools: the implementer has `gh` (authenticated, works against public repos), `curl`, and WebFetch/WebSearch as deferred tools. The planner used `gh api` and `curl` for everything below. Downloaded upstream files are untrusted data. Save them under the scratchpad (for example `<scratchpad>/upstream/<client>/`) and only `grep` or read them. Never execute or `npm install` them.

---

## Findings from Exploration

Fetched 2026-11-15. "Pinned" means the tag's commit SHA. All three tags are lightweight (`git/ref/tags/<tag>` → `object.type: commit`).

### F-1 OpenCode: `anomalyco/opencode` tag `v1.19.5` → `810c0eba1a7348036f8bdf61e6632d0c36c6876c` (released 2026-10-28)

Schema directory: `packages/opencode/src/tool/` (last change in that directory before the tag: `b01498d3ff575b7d3e7b358ff24bf6d2b28484b6`, 2026-10-27). Tool id = first argument of `Tool.define(...)`; parameters = the `Parameters` `Schema.Struct` (Effect Schema, not Zod).

| PRD name | Real name | Target key | Source file (at the tag) | Note |
|---|---|---|---|---|
| `bash` | `bash` | `command` (+ optional `workdir`, `timeout`) | `tool/shell.ts:338-339` defines `ShellID.ToolID`; `tool/shell/id.ts` sets `ToolID = "bash"` ("Rename with opencode 2.0"); params in `tool/shell/prompt.ts:16-21` | Same name, but the file is now `shell.ts`. On Windows it may run `pwsh`/`cmd` (`id.ts` kinds), which supports PRD Risk 3 |
| `write` | `write` | `filePath` | `tool/write.ts:22-28` | Description says "must be absolute", but `write.ts:41-43` joins a relative path onto the instance directory |
| `edit` | `edit` | `filePath` (+ `oldString`, `newString`, `replaceAll`) | `tool/edit.ts:48-59` | Single path |
| `patch` | **`apply_patch`** | `patchText` | `tool/apply_patch.ts:19-23`, grammar in `tool/apply_patch.txt` | **Correction.** `patch` is gone. `apply_patch` landed in `b7ad6bd83922e2259a467fe59f27806af8060629` (2026-01-18, "apply_patch tool for openai models"). The paths sit **inside** `patchText` on `*** Add File: <p>`, `*** Update File: <p>`, `*** Delete File: <p>` and `*** Move to: <p>` lines, and there can be several per call. `registry.ts:297-300` offers `apply_patch` **instead of** `edit`/`write` when the model id contains `gpt-` (not `oss`, not `gpt-4`) |
| `read` | `read` | `filePath` | `tool/read.ts:29,64-69` | "absolute path to the file or directory" |
| `webfetch` | `webfetch` | `url` | `tool/webfetch.ts:14,24-25` | |
| `glob` | `glob` | `pattern` (+ optional `path`) | `tool/glob.ts:11-18` | Target for `fs_read` is `path`, optional, so STORY-004 must decide what an absent `path` means |
| `grep` | `grep` | `pattern` (+ optional `path`, `include`) | `tool/grep.ts:11-21` | Same optional-`path` question |
| `list` | **removed** | — | `tool/ls.ts` deleted by `d2ea6700aa2e6bdf5d04fe70ba893afbb320adbd` (2026-04-15, "Remove dead code and documentation related to the obsolete list tool") | **Correction.** No `list` tool in v1.19.5 |
| (not in PRD) | `lsp` | `filePath` | `tool/lsp.ts:25,37-38` | "absolute or relative path". Read-like |
| (not in PRD) | `websearch`, `task`, `todowrite`, `question`, `skill`, `plan_exit`, `invalid` | — | `tool/registry.ts:100-117` | Record the names. STORY-004 decides between `tool.unknown` and `opaque_tools` |
| MCP | `<sanitize(server)>_<sanitize(tool)>` | tool-specific | `src/mcp/catalog.ts:117-119` (`toolName = sanitize(clientName) + "_" + sanitize(name)`) | A bare `query` never arrives from OpenCode. It arrives as `postgres_query` |

### F-2 Cline: `cline/cline` tag `v4.1.26` → `a459f1d04dea030833b558be645011ab739c463b` (released 2026-10-26)

**Every Cline name in PRD Section 4 is a legacy name in 4.x.** `docs/tools-reference/all-cline-tools.mdx` (section "Legacy Tool Names vs Current Runtime Tools") says: "older docs/examples reference XML-style names like `read_file`, `replace_in_file`, `execute_command` … Current SDK/ClineCore runtime uses the built-in tool names listed above." Names: `sdk/packages/core/src/extensions/tools/constants.ts:12-22`. Schemas: `sdk/packages/core/src/extensions/tools/schemas.ts`. Tool objects: `definitions.ts:275,372,530,576,670,719,789,854,886`.

| Current name | Target location | Schema lines | Several targets per call? |
|---|---|---|---|
| `run_commands` | `commands: string[]` (advertised, `min(1)`). The lenient union also accepts `{command}`, `{cmd}`, a bare string, a string array, and structured `{command, args[]}` | `schemas.ts:133-176` | **Yes**, an array of commands |
| `read_files` | `files: [{path, start_line?, end_line?}]`. The union also accepts `file_paths`, `paths`, and the `file_path`/`filePath` aliases | `schemas.ts:15-105` | **Yes** |
| `editor` | `path` (+ `old_text`, `new_text`, `insert_line`) | `schemas.ts:198-235` | No. Creates the file when missing (a write) |
| `apply_patch` | `input` (patch text, same grammar as OpenCode's), or a bare string | `schemas.ts:238-253` | **Yes**, paths inside the patch text |
| `fetch_web_content` | `requests: [{url, prompt}]` | `schemas.ts:181-195` | **Yes** |
| `search_codebase` | `queries: string[]` (no path) | `schemas.ts:111-125` | n/a |
| `skills`, `ask_question`, `submit_and_exit` | — | `schemas.ts:258-300` | — |
| MCP | `<server>__<tool>`, sanitized, ≤ 64 chars, hashed when longer | `sdk/packages/core/src/extensions/mcp/name-transform.ts` | There is no `use_mcp_tool` / `access_mcp_resource` in 4.x |

Paths: `AbsolutePath` is described as "The absolute path …" (`schemas.ts:15-17`), and `editor.path` likewise. That **contradicts PRD 6.5 item 2** ("Cline's tools send relative paths") for 4.x.

The **legacy** names the PRD lists still exist at the last 3.x tag, `v3.89.2` → `e1bdeeff68e95734901c7a4b3a31753bae54a634`, under `apps/vscode/src/core/prompts/system-prompt/tools/*.ts` (`execute_command.ts`, `write_to_file.ts`, `replace_in_file.ts`, `read_file.ts`, `list_files.ts`, `search_files.ts`, `browser_action.ts`, `use_mcp_tool.ts`, `access_mcp_resource.ts`). Each file has **variants**. The `GENERIC` variant is an XML tool block **in the message text**, not an OpenAI `tool_call`. Native variants (for example `NATIVE_GPT_5` in `execute_command.ts`) send real `tool_calls`, sometimes under different names and keys: `replace_in_file.ts:67-101` has `path` in one variant and `absolutePath` in another. The implementer must record name and key **per variant** and mark which variants are `tool_calls` and which are text.

### F-3 Aider: `Aider-AI/aider` tag `v0.86.0` → `a4be6ccd87ebaa59b361f3f028d116ce1761b626` (2025-08-09; `main` @ `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` is 152 commits ahead)

- `aider/models.py:948-972`: `send_completion(…, functions, …)` sends `tools=[…]` and a forced `tool_choice` **only when `functions is not None`**.
- `aider/coders/base_coder.py:96` sets `functions = None` on the base class. `:1850-1852` reads `tool_calls[0]` back.
- The only coders that set `functions` are `editblock_func_coder.py`, `wholefile_func_coder.py` and `single_wholefile_func_coder.py`. Their `__init__` raises `RuntimeError("Deprecated, needs to be refactored to support get_edits/apply_edits")` (wholefile_func line 47, editblock_func line 61). They are also absent from `aider/coders/__init__.py` `__all__`, and `SingleWholeFileFunctionCoder` is commented out there, so no `--edit-format` selects them.
- `repo.py`, `history.py`, `sendchat.py` and the architect, ask and context coders do not reference `functions` or `tools`.
- Preliminary conclusion: **no reachable Aider mode emits `tool_calls`. "Aider needs no adapter" holds.** The implementer re-checks the same files on `main` @ `5dc9490` and states both refs.

### F-4 Generic SQL tool names (PRD Section 4, "`query`, `execute_sql`, `run_sql`")

- `query`: `modelcontextprotocol/servers-archived` @ `9be4674d1ddf8c469e6461a27a337eeb65f76c2e`, `src/postgres/index.ts:98-118`, key **`sql`**.
- `execute_sql`: `supabase-community/supabase-mcp` @ `9092ab9055509fcdfbedcb75edf02d9412feed37`, `packages/mcp-server-supabase/src/tools/database-operation-tools.ts:201-202`, key **`query`** (plus `project_id`). The same file has `apply_migration` with key `query` at line 193, which is DDL-bearing.
- `run_sql`: no source found yet. The implementer searches (WebSearch / `gh search code "run_sql" --language TypeScript`). If no real server is found, record "no upstream source found" and say which key STORY-004 should assume, or recommend dropping the name.
- Cross-cutting: through OpenCode and Cline these names arrive **prefixed** (`postgres_query`, `supabase__execute_sql`). A bare-name mapping only matches clients that call MCP tools unprefixed, or a deployment's own `tools:`. Record this as a correction to Section 4.

### F-5 Implication for STORY-004 (record it, do not implement it)

STORY-004's Technical Notes model a mapping as `ToolMapping(kind, target)`, with **one** string target key. Four real shapes do not fit that model:

- arrays of targets: Cline `run_commands.commands[]`, `read_files.files[].path`, `fetch_web_content.requests[].url`
- paths embedded in patch text: OpenCode `apply_patch.patchText`, Cline `apply_patch.input`
- a target that may be absent: OpenCode `glob.path`, `grep.path`
- lenient alias unions: Cline accepts `cmd`, `file_paths`, `filePath`, …

`SOURCES.md` gets a section "Implications for STORY-004" that lists these shapes neutrally, so STORY-004's planner can choose (for example a target *path* such as `files[].path`, a `patch` extractor, or treating aliases as malformed). This story does not edit STORY-004. The orchestrator is told (Risk R1).

---

## Patterns to Follow

### Provenance style (SOURCES.md)

```
// SOURCE: tests/corpora/agent_prompts/SOURCES.md:1-25
# Agent-prompt corpus: sources
...
All three were fetched on **2026-09-23**. Each upstream link is pinned to the
commit that last changed the file at that date, not to a branch.
---
## `opencode-anthropic.txt`: OpenCode
- **Agent**: OpenCode, the system prompt it sends to Anthropic models
- **Upstream**: `anomalyco/opencode` (formerly `sst/opencode`, which now
  redirects), `packages/opencode/src/session/prompt/anthropic.txt`
- **Commit**: `87795384de062abad50f86775e4803e4a23d51fc` (2026-02-10)
- **URL**: https://github.com/anomalyco/opencode/blob/87795384.../packages/opencode/src/session/prompt/anthropic.txt
- **License**: MIT
```

Mirror it: an intro paragraph saying what the file backs (PRD-016 F1, STORY-004), the fetch date and the pinning rule, then one `##` section per client with **Upstream / Tag / Commit / License / Schema location**, then the per-tool table. Every URL is a `github.com/<repo>/blob/<full-sha>/<path>#L<a>-L<b>` permalink. Never link to a branch. The file also closes with a "what this shows, and what it does not" section (lines 49–end of the same file), which this survey reuses for the Aider conclusion and its limits.

### Machine-readable table (for STORY-004's parametrized test)

STORY-004 says "`tests/test_action_adapters.py`, parametrized over the `SOURCES.md` entries". Give each client **one** Markdown table with fixed columns, so a later test can parse it without prose heuristics:

`| Client | Tool | Operation kind | Target key | Multi-target | Paths | Version | Commit | Schema |`

`Operation kind` takes one of `shell | sql | fs_write | fs_read | http | none`. `Paths` takes one of `absolute | relative | either | n/a`. Exact casing in backticks.

### Spike document style (threat-model.md)

```
// SOURCE: .agents/spikes/PRD-014-docker-network-stalls.md:1-11
---
prd: PRD-014
story: STORY-006
decision: D5
conclusion: confirmed
date: 2026-10-21
---
# Spike: do the libSQL stalls come from Docker Desktop's port forwarding? (D5)
**Conclusion: confirmed, on thin evidence.** ...
```

Use frontmatter `prd: PRD-016`, `story: STORY-001`, `date: 2026-11-15`, then a bold one-paragraph conclusion (how many threats have a rule, how many are open findings). Then the mapping table, the open findings, and "what this does not cover". Note the path difference: PRD-014 wrote a flat `.agents/spikes/PRD-014-*.md`, while this story's AC fixes `.agents/spikes/PRD-016-action-policy-rules/threat-model.md` (a subdirectory). Follow the AC.

### Provenance test precedent (for context, no test added here)

```
// SOURCE: tests/test_pattern_corpus.py:158-164
sources = _CORPORA / "agent_prompts" / "SOURCES.md"
assert sources.is_file(), "tests/corpora/agent_prompts/SOURCES.md is missing"
provenance = _read(sources)
for path in _PROMPT_FILES:
    assert f"`{path.name}`" in provenance, f"{path.name} has no provenance in SOURCES.md"
```

STORY-017 and STORY-004 will add the actions-corpus equivalent. Put every tool name in backticks so that kind of substring check works.

### Spike plan precedent

`.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-006-docker-network-spike.plan.md:39-58`: a "Findings from Exploration" list of deviations that the report must state, and scratch work kept outside the repo. Same approach here.

Error-handling and naming patterns from `app/` do not apply: no code is written.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/corpora/actions/SOURCES.md` | CREATE (new dir) | Adapter provenance: AC1, AC2, AC3, the SQL-tool keys, multi-target, absolute/relative, "Corrections to PRD Section 4", "Implications for STORY-004" |
| `.agents/spikes/PRD-016-action-policy-rules/threat-model.md` | CREATE (new dir) | T1–T13 → rule(s) → corpus group; open findings (AC4) |
| `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` | UPDATE | AC5: Section 4 adapter bullets (lines 58–59), Section 15 *Assumptions* (lines 739–742) marked verified/corrected with a link to SOURCES.md; the factually wrong sentences at 6.5 item 2/4 (lines 265, 267) and the 6.6 sample comment (line 278) corrected and noted as a deviation; `updated:` |
| `.agents/stories/PRD-016-action-policy-rules/STORY-001-action-threat-model-and-adapter-survey.md` | UPDATE | (done by this plan) `plan`, `status: in-progress`; at implement: `report`, `commit`, `status: done` |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE | Regenerated by `gen_index.py` |
| `.agents/reports/PRD-016-action-policy-rules/STORY-001-action-threat-model-and-adapter-survey.report.md` | CREATE (implement step) | Story report |
| this plan → `.agents/plans/PRD-016-action-policy-rules/completed/` | MOVE (implement step) | Archive, per repo convention |

No `app/`, `chat_ui/` or `tests/*.py` change.

---

## Tasks

Execute in order. Each task is atomic and verifiable. Tasks 1–4 are research. Keep raw downloads in `<scratchpad>/upstream/…`, never in the repo.

### Task 1: Pin and verify OpenCode (AC1)

- **File**: (research), feeds `tests/corpora/actions/SOURCES.md`
- **Action**: RESEARCH
- **Implement**: Re-resolve `v1.19.5`. Check that it is still the latest release with `gh api repos/anomalyco/opencode/releases/latest --jq .tag_name`. If a newer release exists, use it and re-run every check below. Download the files in table F-1 from `https://raw.githubusercontent.com/anomalyco/opencode/<sha>/packages/opencode/src/tool/<file>` and confirm, for each of `bash write edit patch read webfetch glob grep list`, the real id (the `Tool.define` first argument), the target key with exact casing, whether it is optional, and the description's absolute/relative wording against the `execute` code (`write.ts:41-43` pattern). Confirm `list` and `patch` are absent with `gh api "repos/anomalyco/opencode/contents/packages/opencode/src/tool?ref=<sha>"`, and cite the removing/replacing commits (`d2ea670…`, `b7ad6bd…`). Record `apply_patch`'s header grammar (`apply_patch.txt`) and the model-id gate (`registry.ts:297-300`). Record the MCP name rule (`src/mcp/catalog.ts:117-119`).
- **URLs the implementer opens** (permalinks to cite):
  - https://github.com/anomalyco/opencode/tree/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool
  - https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/shell/id.ts
  - https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/shell/prompt.ts
  - https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/apply_patch.ts
  - https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts
  - https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/mcp/catalog.ts
  - https://github.com/anomalyco/opencode/commit/d2ea6700aa2e6bdf5d04fe70ba893afbb320adbd and https://github.com/anomalyco/opencode/commit/b7ad6bd83922e2259a467fe59f27806af8060629
- **Validate**: every one of the 9 PRD names has a row (real name, or "removed"/"renamed") with a `blob/<sha>/…#L` link that opens.

### Task 2: Pin and verify Cline, current and legacy (AC2)

- **File**: (research), feeds `SOURCES.md`
- **Action**: RESEARCH
- **Implement**:
  1. Re-resolve `v4.1.26` (`gh api repos/cline/cline/releases/latest`). Confirm that the **VS Code extension** at that tag runs the SDK tool set, not only the CLI: follow `apps/vscode/src/sdk/cline-session-factory.ts` and `SdkController.ts` to where tools are created (`createDefaultTools` or similar). If the extension still ships the legacy prompt tools, say so, because it changes which set is "current".
  2. Record F-2's table from `constants.ts` + `schemas.ts` (advertised schema **and** the lenient union's accepted aliases) + `definitions.ts`. Record how the tools reach the model: `inputSchema: zodToJsonSchema(...)`, which means native function calling and therefore OpenAI `tool_calls` on an OpenAI-compatible provider. Confirm this by finding the OpenAI-compatible provider handler in `sdk/packages/*` that sends `tools`.
  3. For each PRD-listed legacy name (`execute_command`, `write_to_file`, `replace_in_file`, `read_file`, `list_files`, `search_files`, `browser_action`, `use_mcp_tool`, `access_mcp_resource`), open `apps/vscode/src/core/prompts/system-prompt/tools/<name>.ts` at `v3.89.2` (`e1bdeef…`) and record each **variant**: the `name:` it advertises, the parameter keys (exact casing: `path` vs `absolutePath`), and whether the variant is XML-in-text (GENERIC and similar) or native `tool_calls` (`NATIVE_*`). Find which `ModelFamily` values are native in `apps/vscode/src/shared/prompts.ts` (or wherever `ModelFamily` is defined at that tag).
  4. Record `use_mcp_tool` / `access_mcp_resource` as `tool.unknown` by design (AC2, PRD Out of Scope). Note that 4.x replaces them with `<server>__<tool>` names, which are `tool.unknown` too unless mapped.
- **URLs**:
  - https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/constants.ts
  - https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts
  - https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/definitions.ts
  - https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/mcp/name-transform.ts
  - https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/docs/tools-reference/all-cline-tools.mdx
  - https://github.com/cline/cline/tree/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools
- **Validate**: every one of the 9 PRD Cline names has a row (legacy, per variant) and a "current 4.x equivalent" column; every 4.x tool name has a row.

### Task 3: Aider (AC3)

- **File**: (research), feeds `SOURCES.md`
- **Action**: RESEARCH
- **Implement**: Verify F-3 at `v0.86.0` (`a4be6cc…`) **and** at the current `main` head (re-resolve it; `5dc9490…` at planning time). At both refs: `aider/coders/__init__.py` (which coders are registered), each `*_func_coder.py` `__init__` (the `RuntimeError`), `aider/models.py` `send_completion` (the `tools=` path), and a search for any other non-`None` `functions` assignment. For example, download the `aider/` tree listing with `gh api …/git/trees/<sha>?recursive=1` and grep each `.py` for `functions =` / `tools=`. State the conclusion in one sentence with the citations: no reachable mode emits `tool_calls`, so the PRD assumption is confirmed. If a reachable mode is found on either ref, list its function name and argument keys in a "Mapping for STORY-004" subsection instead.
- **URLs**:
  - https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/models.py#L948-L972
  - https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/__init__.py
  - https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/wholefile_func_coder.py
  - https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/editblock_func_coder.py
  - https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/base_coder.py
- **Validate**: `SOURCES.md` has an *Aider* section with the sentence and at least the `models.py` and `__init__.py` permalinks for both refs.

### Task 4: Generic SQL tool keys (Technical Notes)

- **File**: (research), feeds `SOURCES.md`
- **Action**: RESEARCH
- **Implement**: Verify F-4. Search for a real `run_sql` server (WebSearch "MCP server run_sql tool", `gh search code "\"run_sql\"" --limit 20`). Record each name → key → repo@sha → file#L, including the `query`→`sql` and `execute_sql`→`query` mismatch, which is worth stating plainly: the key is not the tool name. Record `apply_migration` (Supabase) as a DDL-bearing name the PRD does not list. Record the prefixing rule from Tasks 1–2, which means bare names arrive only from clients that do not prefix.
- **Validate**: three rows (`query`, `execute_sql`, `run_sql`), each with a key or an explicit "no upstream source found".

### Task 5: Write `tests/corpora/actions/SOURCES.md`

- **File**: `tests/corpora/actions/SOURCES.md`
- **Action**: CREATE (`mkdir -p tests/corpora/actions`)
- **Implement**: Structure:
  1. `# Action corpus: adapter sources`, then an intro paragraph (what it backs: PRD-016 F1 / STORY-004 built-in mappings, fetch date 2026-11-15, the pin-to-commit rule).
  2. `## OpenCode` (Upstream, Tag, Commit, License MIT, Schema location, then the fixed-column table, then notes: `apply_patch` grammar and model gate, MCP naming, absolute paths with relative accepted).
  3. `## Cline` (4.x current table; 3.x legacy table per variant with an XML/native column; MCP).
  4. `## Aider` (conclusion with citations).
  5. `## Generic SQL tools`.
  6. `## Absolute and relative paths`: one line per client (backs D11 and the README's OpenCode setup step).
  7. `## Tools that name several targets`: OpenCode `apply_patch`; Cline `apply_patch`, `run_commands`, `read_files`, `fetch_web_content` (backs F1 "one `fs_write` per path").
  8. `## Corrections to PRD Section 4`: one bullet per difference: `patch`→`apply_patch`/`patchText`; `list` removed; Cline 4.x renames; Cline legacy variants and their keys; SQL prefixing; `query` key is `sql`.
  9. `## Implications for STORY-004` (F-5, neutral).
  10. `## What this survey shows, and what it does not`: clients change, this is one pinned version each; renamed tools fail closed (Risk 5); Windows `pwsh` shells exist in OpenCode (Risk 3).

  Every tool name and key goes in backticks, with exact casing.
- **Mirror**: `tests/corpora/agent_prompts/SOURCES.md:1-25` and its closing section.
- **Validate**: `grep -c 'blob/[0-9a-f]\{40\}/' tests/corpora/actions/SOURCES.md` ≥ number of table rows; `grep -nE 'github.com/[^ ]*/(blob|tree)/(main|dev|master)/' tests/corpora/actions/SOURCES.md` returns nothing (no branch links); each name in the AC1/AC2 lists appears in backticks (see Validation).

### Task 6: Write the threat model

- **File**: `.agents/spikes/PRD-016-action-policy-rules/threat-model.md`
- **Action**: CREATE (`mkdir -p .agents/spikes/PRD-016-action-policy-rules`)
- **Implement**: Frontmatter as in the pattern. A table with columns `| # | Threat | Rule(s) in 6.3 that answer it | Other mechanism (not a rule) | Proven by (corpus group / test) | Story |`, one row for each of **T1–T13** (PRD lines 543–555). Method:
  - Rules come only from the Section 6.3 catalogue (lines 226–250). Cite rule ids exactly.
  - Corpus group is `synthetic/` or `evasion/` (PRD F12, Section 11 *Corpus criteria*, lines 657–660). When a threat is proven by a unit test rather than a corpus (T4: STORY-003/014 RBAC-off test; T7: STORY-007 failing-file tests; T9: STORY-014 boundary test; T12: STORY-004 over-length test), say so, name the story, and still name the corpus group if one also applies.
  - **Open findings**: a threat whose answer is not a 6.3 rule goes in an `## Open findings` section, as the AC requires ("lists any threat with no rule as an open finding"). Each entry says what answers it instead, or that nothing does. Candidates to evaluate honestly, not pre-decided: T4 (answered by `holds()`/D7, no rule), T7 (startup validation), T9 (`evaluate()` boundary maps to `tool.malformed`, so arguably a rule), T10 (accepted risk, nothing answers it), T11 (reason templates), T12 (`tool.malformed` for length; recursion depth maps to `shell.unclassifiable`), T13 (explicitly "no new mitigation claimed").
  - Add the survey's own new findings as threats or open findings where they apply. For example: paths inside `apply_patch` text (a writer target the adapter must parse, or the write escapes classification); Cline's lenient aliases (a key the mapping does not read); OpenCode's Windows `pwsh` shell (T2/Risk 3); Cline 4.x absolute paths, which mean a Cline deployment needs `workspace.roots` too (6.5 item 4); MCP prefixing defeating the bare SQL names (T3).
- **Mirror**: `.agents/spikes/PRD-014-docker-network-stalls.md:1-11` (frontmatter + bold conclusion).
- **Validate**: `for t in $(seq 1 13); do grep -q "| T$t |" .agents/spikes/PRD-016-action-policy-rules/threat-model.md || echo "missing T$t"; done` prints nothing. Every rule id cited appears in PRD 6.3: extract the backticked ids from the threat model, then `grep -F` each one in PRD lines 222–252. The `## Open findings` section exists.

### Task 7: Apply corrections to the PRD (AC5)

- **File**: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md`
- **Action**: UPDATE
- **Implement**:
  - Section 4 line 58: replace the OpenCode and Cline tool lists with the verified ones (`apply_patch` for `patch`, no `list`, Cline 4.x names, plus the legacy 3.x names if the decision is to keep both), keeping the "verified … recorded in `tests/corpora/actions/SOURCES.md`" clause. Line 59: name the real keys or the prefixing caveat for the SQL names.
  - Section 15 *Assumptions to verify in STORY-001* (lines 739–742): mark each assumption **verified** or **corrected** with a one-line result and a link to `SOURCES.md` and the threat model. Leave the third bullet (sqlglot, STORY-008) unchanged.
  - Sections 6.5 items 2 and 4 (lines 265, 267) and the 6.6 sample comment (line 278) state "Cline's tools send relative paths". If Task 2 confirms 4.x sends absolute paths, correct those sentences. They are outside "Sections 4 and 15", so record this as a deviation in the report and tell the orchestrator. D11's *rule* is unchanged; only the claim about Cline changes.
  - Frontmatter `updated:`. It is already `2026-11-15` (PRD line 9), so "bump" sets the same value. The report says so, so nobody reads it as a skipped step.
  - Do **not** edit STORY-004 or other stories. Implications go in SOURCES.md and the report.
- **Validate**: `git diff --stat .agents/PRDs/PRD-016-action-policy-rules/PRD.md` shows only these hunks. `grep -n "\`patch\`\|\`list\`" PRD.md` no longer shows them as OpenCode tools (unless marked as removed).

### Task 8: Bookkeeping, report, commit (implement.md Phase 5)

- **Files**: report, story frontmatter, plan archive, index
- **Action**: UPDATE/CREATE
- **Implement**: Write the report (`.agents/reports/PRD-016-action-policy-rules/STORY-001-…report.md`, mirroring the PRD-014/PRD-015 reports) with every deviation: the Cline rename, `patch`/`list`, the 6.5 edit, the `updated` no-op, the STORY-004 model mismatch. Move the plan to `.agents/plans/PRD-016-action-policy-rules/completed/`. Set story `status: done`, `report`, `commit`. Regenerate the index with `PYTHONIOENCODING=utf-8 .venv/Scripts/python "<scratchpad>/gen_index.py"` (must print `errors: none`). Stage files explicitly. Commit order per the shared brief (main commit with `commit: pending`, then the `chore(PRD-016): STORY-001 report; update status + index` SHA commit).
- **Validate**: `git show --stat HEAD~1 HEAD` lists only the files in *Files to Change*. `git status` is clean.

---

## End-to-End Tests

No runtime behaviour changes, so the checks are document checks plus the brief's standard validation:

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints `OK` (nothing under `app/` touched)
- [ ] `git diff --name-only d8a0fa4 -- app chat_ui 'tests/*.py'` is empty
- [ ] Full suite per the shared brief (background, `-q -p no:cacheprovider`). Expected unchanged from the epic base, since only `.md` files are added. `tests/test_pattern_corpus.py` discovers only `tests/corpora/agent_prompts/`, so a new `tests/corpora/actions/SOURCES.md` must not be picked up as a sample. Confirm no corpus test globs `tests/corpora/**` (`grep -rn "corpora" tests/*.py`)
- [ ] Every permalink in SOURCES.md resolves: extract the URLs and `curl -s -o /dev/null -w '%{http_code}'` each raw equivalent → `200`

---

## Validation

```bash
cd /g/coding/harness-ai
S=tests/corpora/actions/SOURCES.md
T=.agents/spikes/PRD-016-action-policy-rules/threat-model.md
# AC1: every PRD OpenCode name is accounted for
for n in bash write edit patch read webfetch glob grep list; do grep -q "\`$n\`" $S || echo "OpenCode $n missing"; done
# AC2: every PRD Cline name (incl. MCP) is accounted for, MCP marked tool.unknown
for n in execute_command write_to_file replace_in_file read_file list_files search_files browser_action use_mcp_tool access_mcp_resource; do grep -q "\`$n\`" $S || echo "Cline $n missing"; done
grep -n "tool.unknown" $S
grep -n "^## Corrections to PRD Section 4" $S
# AC3
grep -n "^## Aider" $S; grep -n "tool_calls" $S
# Pinned, not branch
grep -nE '/(blob|tree)/(main|dev|master)/' $S && echo "branch link found"
# AC4
for t in $(seq 1 13); do grep -q "| T$t |" $T || echo "missing T$t"; done
grep -n "^## Open findings" $T
# AC5
git diff .agents/PRDs/PRD-016-action-policy-rules/PRD.md | head -80
grep -n "^updated:" .agents/PRDs/PRD-016-action-policy-rules/PRD.md
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONIOENCODING=utf-8 .venv/Scripts/python "C:/Users/nahue/AppData/Local/Temp/claude/G--coding-harness-ai/20d13059-18e1-4943-818b-68572342f8ca/scratchpad/gen_index.py"
```

Each loop prints nothing on success.

---

## Acceptance Criteria

(Copied from story `STORY-001`, with the check for each one.)

- [ ] **AC1** OpenCode: `SOURCES.md` lists `bash`, `write`, `edit`, `patch`, `read`, `webfetch`, `glob`, `grep`, `list`, each with exact name, target key, version/commit and schema file/URL. Differences go under "Corrections to PRD Section 4" (expected: `patch`→`apply_patch` with `patchText`; `list` removed). *Check*: Task 1 + Validation loop 1 + correction heading grep.
- [ ] **AC2** Cline: the same for `execute_command`, `write_to_file`, `replace_in_file`, `read_file`, `list_files`, `search_files`, `browser_action`, plus `use_mcp_tool`/`access_mcp_resource` recorded as `tool.unknown`. Expected: all are legacy (v3.89.2) names; 4.x equivalents and their array-shaped targets go under Corrections. *Check*: Task 2 + Validation loop 2 + `tool.unknown` grep.
- [ ] **AC3** Aider: a sourced statement on `tool_calls`; expected "no reachable mode, so the assumption is confirmed", cited at `v0.86.0` and `main`. *Check*: Task 3 + `## Aider` grep.
- [ ] **AC4** Threat model: T1–T13 each mapped to 6.3 rule(s) and a corpus group, with an `## Open findings` section for threats without a rule. *Check*: Task 6 + T-loop + rule-id cross-check against PRD 6.3.
- [ ] **AC5** PRD Sections 4 and 15 corrected in the same commit, `updated:` set (already 2026-11-15). *Check*: Task 7 + `git show --stat` of the story commit includes `PRD.md`.
- [ ] Technical Notes covered: exact key casing, multi-target tools, absolute vs relative per client, SQL tool keys (Tasks 1–5)
- [ ] All tasks completed
- [ ] Backend import OK; full suite unchanged (no lint in this repo; see shared brief)
- [ ] No `app/`, `chat_ui/` or `tests/*.py` changes
- [ ] Follows existing patterns (`agent_prompts/SOURCES.md` provenance, PRD-014 spike doc)

---

## Risks and Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **STORY-004's single-key `ToolMapping(kind, target)` does not fit real shapes** (Cline arrays, patch-embedded paths, optional `path`, alias unions) | Recorded neutrally in `SOURCES.md` "Implications for STORY-004" and in the report. This story does not change STORY-004. **The orchestrator decides** whether STORY-004's notes need amending before it is planned |
| R2 | **Which Cline is "current"?** 4.x renamed everything; users on 3.x send legacy names, and its GENERIC variant sends XML in text, not `tool_calls` | Record both, with variant and transport per tool. The PRD correction names 4.x as current and lists legacy native-variant names as candidates. STORY-004 picks which built-ins ship. XML-in-text variants never reach the engine as `tool_calls`, so they need no mapping, and that goes in writing |
| R3 | **Upstream moves after fetch** (a newer tag before implement) | Re-resolve the latest release first (Tasks 1–3). If it changed, use the new tag and note both. Every link is pinned to a full SHA either way |
| R4 | **PRD edits outside Sections 4/15** (6.5 lines 265/267, 6.6 line 278) | Only if Task 2 confirms absolute paths for 4.x. Minimal factual edit, D11 rule unchanged, reported as a deviation |
| R5 | **`run_sql` has no real source** | Record "no upstream source found" with the searches run. Do not invent a key |
| R6 | **"Open finding" wording**: some threats are answered by mechanisms, not 6.3 rules | List them under Open findings with the mechanism and story that answers them, so the AC is met literally and nothing is hidden |
| R7 | **Untrusted downloads** | Scratchpad only, read/grep only, nothing executed, nothing committed |
