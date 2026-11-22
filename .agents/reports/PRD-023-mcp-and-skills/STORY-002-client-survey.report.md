---
story: STORY-002
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-002-client-survey.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: 4bff962
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report — STORY-002: Client survey (spike)

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-002-client-survey.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `4bff962`

## Summary

Research only. `tests/corpora/mcp/SOURCES.md` gains `## Clients` and `## Servers` (63 pinned `/blob/<40-hex>/` links in the file; none on `main` or `latest`). Evidence is labelled **source** (client code at a pinned commit) or **observed** (the installed client against a throwaway logging listener and a fake OpenAI-compatible provider, in the scratchpad, not committed). Observed runs: OpenCode 2.3.2 and Cline CLI 3.0.74, each with a normal answer, `401` once and `401` always (OpenCode also with `oauth: false` and with `codemode` unset), plus long and odd tool names. Dummy token `test-token` only; every child killed as a tree; `tasklist` shows no `opencode`, `cline`, `node` or listener left.

## Findings (what the orchestrator needs)

| Question | Answer |
|---|---|
| Revision sent | Both: `initialize` with `protocolVersion: 2025-11-25`, **observed**. No `server/discover`. OpenCode's default `protocol` is `legacy`; `auto` / `2026-07-28` exist and are opt-in (not observed) |
| SDK pins (STORY-001 asked) | **Cline 3.0.74 and 4.1.27: confirmed** `@modelcontextprotocol/sdk ^1.29.0` (installed 1.32.2, `LATEST_PROTOCOL_VERSION = 2025-11-25`). **OpenCode 2.3.2: refuted.** It uses the v2 TS SDK `@modelcontextprotocol/client` **2.4.0** (patched; `LATEST = 2025-11-25`); OpenCode 2.0.10 uses `2.0.0`. STORY-001's "v1.29.x for both" holds only for Cline and for OpenCode 1.x |
| Static `Authorization` vs OAuth on `401` | Both CLIs send the static header on every request and, after a `401`, send **nothing more** (no `/.well-known/*`, no retry within the run): observed. Source agrees (OpenCode: "A connection never starts a login"; Cline: no provider unless tokens are stored, and a rejected static header is reported as such). **Cline 4.x (VS Code) is source-only**: it always builds an OAuth provider, so a `401` may start discovery; not observed, safe default is `404` on `/.well-known/oauth-*` |
| `Origin` | **Neither CLI sends it** (observed). Cline 4.x not observed |
| Model-facing prefix for server `harness` | OpenCode `harness_<id>` (observed, with `codemode: false`); Cline `harness__<id>` (observed; 4.x same rule, source) |
| Longest unchanged id | OpenCode: no cap and no hash (111 chars preserved, observed). Cline: 55-character id with `harness` (observed: 55 unchanged, 56 hashed as `<sanitized[:55]>_<sha1(raw)[:8]>`); invalid characters collapse as runs |
| `v1_aliases.prefixes: ["harness_", "harness__"]` | **Right, with conditions.** Both prefixes are needed. The overlap resolves (server ids `[a-z0-9][a-z0-9-]{0,31}`: `_x__y` is not a `<server>__<tool>`). But Cline hashes names over 55 chars or with invalid characters, so STORY-016 also needs a reverse map from the clients' transform to the tool id for the visible tools; test vectors are in `## Clients` |
| `codemode` | OpenCode 2.x defaults MCP tools to CodeMode (`execute`), observed: with the key unset `tools[]` had `execute` and no `harness_*`. `codemode: false` is required for direct tools. OpenCode also appends `?codemode=false` to non-loopback URLs when the key is unset: `/mcp` must ignore unknown query parameters |
| Fields read | Both: first `tools/list` page only (no `nextCursor`), so return everything in one page. OpenCode drops a tool whose `inputSchema.type` is not `object`, needs `capabilities.tools`, reads `title`, `outputSchema`, `annotations`, `_meta`, `serverInfo.title` and **`instructions`** (injected into the prompt). Cline 3.0.74 reads `name`, `description`, `inputSchema`, `_meta` only (4.x adds `annotations`); no `instructions` read in source |
| Transport gotcha | Cline needs `"type": "streamableHttp"`; without it a URL entry is **SSE** (observed: only a `GET`, no tool). OpenCode's key is `disabled`, not `enabled`; config lives under `mcp.servers.<name>` |
| GitHub MCP `v2.2.0` (`67d4dc48`) | `create_branch` (`owner`,`repo`,`branch` required; `from_branch`), `push_files` (`owner`,`repo`,`branch`,`files`,`message`; **`files[]` = `{path, content}` both required, no other property**), `create_pull_request` (`owner`,`repo`,`title`,`head`,`base` required; `body`,`draft`,`maintainer_can_modify`,`reviewers[]`). Toolsets `repos` and `pull_requests`; `--read-only` skips them. Snapshots carry `x-mcp-header` on `owner`/`repo`, `icons` as `data:` URIs, `_meta.ui` and a `oneOf` `outputSchema` |

## Tasks Completed

| # | Task | File | Status |
|---|---|---|---|
| 1 | Pin sources (OpenCode 2.3.2 and 2.0.10, Cline `cli-v3.0.74` and `v4.1.27`, github-mcp-server `v2.2.0`) | `tests/corpora/mcp/SOURCES.md` | done |
| 2 | OpenCode source survey | same | done |
| 3 | Cline source survey (3.0.74 tag found: `cli-v3.0.74` = `071e1b25`) | same | done |
| 4 | Observed runs, both clients | scratchpad only | done (4.x source-only) |
| 5 | GitHub MCP tool shapes | same | done |
| 6 | `## Clients`, verdict, `## Servers`; resolved the "Not verified here" bullet of STORY-001 | same | done |
| 7 | Report, story, index | this report | done |

## Validation Results

| Check | Result |
|---|---|
| `git status --short` | only `tests/corpora/mcp/SOURCES.md`, this report, the plan move, the story and the index; no `app/`, `tests/*.py` or `requirements` change |
| `grep -c "blob/[0-9a-f]{40}"` on SOURCES.md | 63; a script found no undefined reference, no unpinned GitHub blob URL and no `main`/`latest` |
| Leftover processes | none (`tasklist`: no `opencode`, `cline`, `node`, listener or provider) |
| Backend import | `.venv/Scripts/python -c "from app.main import app; print('OK')"` (no app change; run as the brief asks) |
| Tests | none (spike) |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|---|---|
| `tests/corpora/mcp/SOURCES.md` | UPDATE (`## Clients`, `## Servers`, link references; one "Not verified here" bullet resolved) |
| `.agents/reports/PRD-023-mcp-and-skills/STORY-002-client-survey.report.md` | CREATE |
| `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-002-client-survey.plan.md` | CREATE (archived plan) |
| story + index | UPDATE |

## Deviations from Plan

- The orchestrator's brief expected OpenCode on the TS SDK v1.29.x; at 2.3.2 it is `@modelcontextprotocol/client` 2.4.0. Recorded as a refutation, not hidden.
- The plan's OpenCode key `enabled` does not exist at 2.3.2 (`disabled`); config nesting is `mcp.servers.<name>`. The plan's `opencode mcp list` run was not used: the repository's own E2E notes say only `run --standalone` and `--version` are safe (other commands start the background service), so the observed run is `run --standalone` against a fake provider.
- Cline 4.x was not run (VS Code GUI): source-only, marked "not verified" where it matters.
- Plan Task 2 listed `mcp/pool.ts`; it only matters for `pool: true`, so it was not read in depth.

## Tests Written

None (spike).

## Acceptance Criteria

- [x] AC1: OpenCode config (`type: remote`, `url`, `headers`, `codemode: false`), no OAuth discovery on `401` (source and observed), prefix `harness_` and sanitizing rule (observed), in `## Clients`
- [x] AC2: Cline 3.0.74 and 4.x config, naming/sanitizing/64-character hashing for `harness`, OAuth behaviour (3.0.74 observed; 4.x source-only), in `## Clients`
- [x] AC3: alias verdict, fields each client needs and `Origin` (none sent by either CLI), in `## Clients` and the table above
- [x] AC4: GitHub `create_branch`, `push_files` (`files[].path`), `create_pull_request` at `67d4dc48`, in `## Servers`

## Proposed PRD amendments

1. **6.8 / `v1_aliases`**: keep `prefixes: ["harness_", "harness__"]`; add that a `/v1` alias lookup also tries a per-request reverse map of the Cline name transform (`sha1(raw)[:8]`, 55-character base), because Cline hashes ids over 55 characters or with characters outside `[a-zA-Z0-9_-]`.
2. **6.2 / 9.1**: `/mcp` ignores unknown query parameters (OpenCode's `?codemode=false`); `404` on `/.well-known/oauth-*`; `405` on `GET /mcp`; one-page `tools/list`; `inputSchema.type: "object"`; `capabilities.tools` declared.
3. **Client docs (STORY-020)**: `codemode: false` is required for OpenCode direct tools; `"type": "streamableHttp"` is required for Cline; name the server `harness` or set `prefixes`.
4. **Section 15, Clients**: replace "OpenCode 2.0.10" with 2.3.2 as the surveyed version; OpenCode's SDK is the v2 client, Cline's the v1 line.
