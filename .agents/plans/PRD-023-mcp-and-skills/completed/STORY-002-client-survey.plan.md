---
story: STORY-002
prd: PRD-023
slug: client-survey
title: "Spike — survey OpenCode and the Cline CLI as remote Streamable HTTP MCP clients"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: Client survey (spike)

## Summary

Research only. Append `## Clients` and `## Servers` to `tests/corpora/mcp/SOURCES.md` (235 lines; STORY-001's `## Protocol` ends with `### Not verified here` at :195 and a block of link references after it, so add the new sections after the last link reference, not in the middle) and write the report. No application code, no tests, nothing from the scratchpad committed. Evidence has two kinds, both recorded and labelled: **source** (client code at a pinned tag/commit) and **observed** (the installed client run against a throwaway localhost listener in the scratchpad). A client that cannot be driven headlessly is recorded as "source-only: <why>".

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-002-client-survey.md` (AC1-AC4 live there)
- PRD sections used: §6.1 (+ STORY-001 amendment), §6.8, §9.1, §14 R2, §15 "Facts to verify" (Clients, Servers)
- Feeds: STORY-016 (`v1_aliases`), STORY-020 (client docs), STORY-011 (northbound `initialize` / `tools/list` fields)

## Design Decisions (binding, from the orchestrator)

- Deliverables are exactly: the two sections in `tests/corpora/mcp/SOURCES.md` plus the report. The listener lives in the scratchpad and is not committed.
- Per client record: exact config; the `protocolVersion` sent in `initialize`; whether `Origin` is sent; the model-facing tool-name prefix for a server named `harness` (sanitizing + 64-char truncation/hash rule); which `initialize` / `tools/list` fields it reads.
- The listener logs method, path, headers and body of every request and answers `401` once, to see whether the client starts OAuth discovery (`/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`) despite a static `Authorization`. After that it serves a minimal `initialize` / `tools/list` so the client completes.
- Confirm or refute `v1_aliases.prefixes: ["harness_", "harness__"]`; state, per client, the longest `<server>__<tool>` that survives unchanged.
- STORY-001 found both clients on TS `@modelcontextprotocol/sdk` v1.29.x (tops out at `2025-11-25`): confirm from source at the **installed** versions.
- Pin every link to a 40-hex commit (never branch or `latest`). Anything unverified is written "not verified" with the safe default.

## Skills In Use

None. `.agents/skills/` holds only `frontend-design`, which does not apply.

## Reconnaissance already done (verify, do not trust)

| Item | Found on 2026-11-22 |
|---|---|
| OpenCode | `where opencode` gives `C:\Users\nahue\AppData\Roaming\npm\opencode.cmd` (shim to `node_modules\@opencode\cli\bin\opencode.exe`). `opencode --version` = `v2.3.2` (`opencode2` shim prints the same). Tag `v2.3.2` = commit `c0ad18b402eb2827fc1ee71c171b1177b3fc02d1` (`anomalyco/opencode`). PRD-021 pinned `v2.0.10` = `b8cedc1a7a5e2916bbb65dc1d4b620729c261638` (`tests/corpora/actions/SOURCES.md:112`). The releases API names `v1.19.6` as latest while `v2.x` tags exist: record both, pin by tag |
| OpenCode MCP code at `v2.3.2` | `packages/core/src/mcp/{client,connection,oauth,pool,index,instructions}.ts`, `packages/core/src/config/plugin/mcp.ts`, `packages/core/src/tool/mcp.ts`, `packages/core/src/plugin/mcp-codemode-defaults.ts`, `packages/cli/src/commands/handlers/mcp/*`. The CLI has `opencode mcp list\|add\|auth\|logout` |
| Cline CLI | `where cline` finds nothing. The pinned local install is `tests/e2e/.clients/cline` (git-ignored): `node_modules/@cline/cli-windows-x64/bin/cline.exe`, `--version` = `3.0.74`; `@cline/core\|sdk\|shared\|agents\|llms` = `0.2.0`; `node_modules/@cline/core/package.json:59` depends on `@modelcontextprotocol/sdk ^1.29.0`. Driver: `tests/e2e/_cline.py:76-110` (`cline_executable`, `auth_command`, `run_command`, `--data-dir` must be absolute). `cline mcp` exists (`install\|add`, `uninstall\|remove`, ...) |
| Cline 4.x | Tag `v4.1.26` = `a459f1d04dea030833b558be645011ab739c463b` (already pinned, actions SOURCES:160). `v4.1.27` is now the latest release (2026-11-21): resolve its commit. MCP code: `apps/vscode/src/services/mcp/{McpHub,StreamableHttpReconnectHandler,McpOAuthManager}.ts`, `apps/cli/src/commands/mcp.ts`, `apps/cli/src/wizards/mcp/*`, `sdk/packages/core/src/extensions/mcp/{name-transform,tools}.ts` |
| Cline 3.0.74 source | Not matched to a tag yet (tags like `sdk/shared/v0.2.0` exist, plus `v3.32.6-cli` and older `-cli` tags). Try `npm view cline@3.0.74 gitHead repository`. If none, say so and use `v4.1.26` for source and the installed `node_modules/@cline/*` files as ground truth |
| GitHub MCP server | `github/github-mcp-server` latest `v2.2.0` = `67d4dc489700ec955ad255d098396dd86c729523` (also `v2.1.0`, `v2.0.3`) |
| Isolation recipe | `tests/e2e/test_opencode.py:35-37,279-284` redirects `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_*`, `TEMP` and injects config via `OPENCODE_CONFIG_CONTENT`. The user's `~/.config/opencode/opencode.json` holds an LM Studio provider: do not touch it. `~/.cline` does not exist: use `--data-dir` / `--config` in a scratchpad directory |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/corpora/mcp/SOURCES.md` | UPDATE | Append `## Clients` and `## Servers` (+ pinned link references). Rewrite the "Not verified here" bullet at :196-198 that this story resolves into a one-line pointer |
| `.agents/reports/PRD-023-mcp-and-skills/STORY-002-client-survey.report.md` | CREATE | Report, same layout as STORY-001's (`.agents/reports/PRD-023-mcp-and-skills/STORY-001-mcp-protocol-spike.report.md`) |
| scratchpad `listener.py` | CREATE (not committed) | Logging HTTP listener |

## Tasks

### Task 1: Pin sources
- Resolve with `gh api repos/<r>/git/ref/tags/<t>` (dereference annotated tags) the 40-hex commits for: OpenCode `v2.3.2` (and `v2.0.10` as a second row), Cline `v4.1.26` / `v4.1.27` plus the 3.0.74 source, `github-mcp-server v2.2.0`. Record version, tag, commit, date, licence, as `tests/corpora/actions/SOURCES.md:80-112` does.
- **Validate**: every commit is 40 hex; each cited path opens via `gh api repos/<r>/contents/<path>?ref=<sha>`.

### Task 2: Source survey, OpenCode (AC1)
- At the pin read: `config/plugin/mcp.ts` (config schema: `type: remote`, `url`, `headers`, `oauth`, `enabled`, `timeout`, and the real CodeMode key, expected `codemode`); `mcp/client.ts` + `connection.ts` (Streamable HTTP vs SSE fallback, `requestInit.headers`, `authProvider`); `mcp/oauth.ts` (does discovery start only on `UnauthorizedError`, or always; does a configured `Authorization` header or `oauth: false` suppress it); `tool/mcp.ts:16-45` and `mcp-codemode-defaults.ts` (name = `sanitize(server)_sanitize(tool)`, default of `codemode`, the `execute` path); `mcp/instructions.ts` (is `InitializeResult.instructions` consumed).
- Work out the longest `<server>_<tool>` left unchanged. If OpenCode has no cap of its own, say the cap is the model provider's and cite whether OpenCode truncates.
- Confirm the SDK pin from `package.json` / lockfile at the commit, then the SDK's `LATEST_PROTOCOL_VERSION` at that version (expect `2025-11-25`).
- Cross-check strings in the installed `opencode.exe` (Bun bundle, searchable as in actions SOURCES:106). Run nothing from it except `--version` and Task 4.

### Task 3: Source survey, Cline (AC2)
- Cline 4.x: `McpHub.ts` (settings JSON shape `cline_mcp_settings.json`: `type: "streamableHttp"`, `url`, `headers`, `disabled`, `timeout`, `autoApprove`; SSE fallback; whether `Origin` is set), `McpOAuthManager.ts`, `StreamableHttpReconnectHandler.ts`, SDK `mcp/name-transform.ts:20-35` (raw `<server>__<tool>`; charset `[a-zA-Z0-9_-]`; 64 cap; 8-char SHA-1 suffix; exact truncation length) and `mcp/tools.ts:21-30`. State the longest tool part that survives with `harness__` (64 minus 9 = 55 if the rule is as actions SOURCES:160 says; verify).
- Cline CLI 3.0.74: read the installed bundle under `tests/e2e/.clients/cline/node_modules/@cline/{core,sdk}` (settings location under `--config` / `--data-dir`, schema, transport, headers, OAuth, naming). The `0mcp0` scheme (actions SOURCES:222) belongs to the old 3.x extension: say whether this CLI uses it.
- Fields read from `initialize` and `tools/list`: `serverInfo`, `capabilities.tools`, `instructions`, `tools[].name|description|inputSchema|annotations|title|outputSchema`, `nextCursor`, `listChanged`.

### Task 4: Observed run (both clients, where feasible)
- Scratchpad listener on a free port, 127.0.0.1, logging method, path, all headers and body of every request. Scripted: (a) first `POST` returns `401` with `WWW-Authenticate: Bearer realm="harness"` (no `resource_metadata`), then (b) `initialize` (echo the client's `protocolVersion`), `notifications/initialized` (202), `tools/list` with one tool `postgres-staging__query`. Log any `GET /.well-known/*`, `/register`, `/authorize`. Second pass: `401` always, to see whether the client loops on discovery or gives up.
- OpenCode: isolated env per `tests/e2e/test_opencode.py:279-284`; `OPENCODE_CONFIG_CONTENT` with `mcp.harness = {type: "remote", url, headers: {Authorization: "Bearer <dummy>"}, codemode: false}` (use the real key found in Task 2); run `opencode mcp list` (connects and reports status) and, if that does not show the model-facing name, `opencode run` against the e2e stub provider (`tests/e2e/_live.py`) and read `tools[]` in the request. That name is the ground truth for `harness_...`.
- Cline: `cline.exe --data-dir <abs scratch> --config <abs scratch>` with a settings file naming the Streamable HTTP server; drive a run as `tests/e2e/_cline.py:89-110` does against the stub provider and read `tools[]`.
- Never `npm -g`, never touch `~/.cline` or the user's OpenCode config. Stop every child as a tree (`taskkill /T`) and leave no listener.
- If a client will not connect headlessly, record "source-only: <why>".
- **Validate**: per client the log shows `protocolVersion`, `Authorization`, `Origin` (present/absent), `MCP-Protocol-Version`, `Mcp-Session-Id` handling, `User-Agent`, and the well-known probes (yes/no). Paste redacted excerpts only; the token is a dummy.

### Task 5: GitHub MCP server (AC4)
- At `v2.2.0` (`67d4dc48...`) read the tool definitions under `pkg/github/` for `create_branch`, `push_files` (`files[].path`, `content`), `create_pull_request`, and `pkg/github/__toolsnaps__/*.snap` if present (exact JSON input schemas). Record names, `required`, argument names and types; note toolset and `--read-only` gating, and any name change against the PRD text. No engine decisions.

### Task 6: Write the sections and the verdict (AC1-AC4)
- `## Clients`: one table (client, version / tag / commit, config, transport, `protocolVersion` sent, `Origin`, OAuth on 401, prefix for `harness`, longest unchanged name, fields read), each cell tagged `source` or `observed`; then notes, including the `codemode` finding (OpenCode 2.x defaults MCP tools to CodeMode: actions SOURCES:113).
- Verdict on `v1_aliases.prefixes: ["harness_", "harness__"]` (PRD §6.6/§6.8). Check the overlap: a Cline name `harness__x__y` also starts with `harness_`, so state how the "two prefixes resolve -> `tool.malformed`" rule behaves (the `harness_` remainder `_x__y` must not resolve as `<server>__<tool>`; confirm), and give STORY-016 the limits to test.
- `## Servers`: the GitHub table with pinned link references.
- **Validate**: `grep -nE "blob/[0-9a-f]{40}" tests/corpora/mcp/SOURCES.md` covers every new link; no `main` / `latest` in any URL; a "Not verified" list covers anything unobserved.

### Task 7: Report, story, index
- Write the report; set story `report:`; leave `status` / `commit` for the implementer's close-out (implement.md). Regenerate the index.

## End-to-End Tests

None (spike, no application code). The Task 4 runs are the empirical checks.

## Validation

```bash
git status --short   # only SOURCES.md, the report, story, index, plan
grep -cE "blob/[0-9a-f]{40}" tests/corpora/mcp/SOURCES.md
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-023   # errors: none
tasklist | findstr /i "opencode cline node"   # no leftover child or listener
```
No pytest: no test or app file changes.

## Acceptance Criteria -> Tasks -> Evidence

| AC | Task(s) | Evidence |
|----|---------|----------|
| AC1 OpenCode config, OAuth on 401, prefix | 1, 2, 4, 6 | `## Clients` OpenCode rows (source + observed `tools[]` name) |
| AC2 Cline 3.0.74 + 4.x config, naming/hash, OAuth | 1, 3, 4, 6 | `## Clients` Cline rows |
| AC3 alias verdict, fields, `Origin` | 2, 3, 4, 6 | report + verdict paragraph |
| AC4 GitHub tools | 1, 5, 6 | `## Servers` with `files[].path` |

## Risks

- A client may not connect to a hand-rolled server without a real LLM turn: use `opencode mcp list` and a stub provider; fall back to source-only.
- The 3.0.74 source tag may not exist publicly: say so, use the installed bundle.
- Overlapping prefixes (`harness_` vs `harness__`) are a design hazard for PRD §6.8: flag to the orchestrator if confirmed.
- OpenCode "latest" API (`v1.19.6`) disagrees with the `v2.x` tags: pin by tag, record both.
