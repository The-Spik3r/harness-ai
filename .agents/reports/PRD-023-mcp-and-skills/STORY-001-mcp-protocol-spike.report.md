---
story: STORY-001
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-001-mcp-protocol-spike.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report — STORY-001: MCP protocol spike

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-001-mcp-protocol-spike.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `pending` (filled by the follow-up chore commit)

## Summary

Research only. `tests/corpora/mcp/SOURCES.md` (new, `## Protocol` section) records 15 protocol facts, the revision table, the per-revision differences, and verdicts on T10/T11/T12. Every link is pinned to a 40-hex commit that a release tag resolves to (fetched 2026-11-22). No application code, test or requirement changed.

## Headline finding (confirmed from normative pages)

| Planner claim (from the changelog summary) | Verdict | Normative wording and source |
|---|---|---|
| Current revision is `2026-07-28` | **Confirmed** | "The **current** protocol version is **2026-07-28**" (versioning page at `main@862397c`; tag `2026-07-28` -> `5f5440bb`). Handshake revisions are `2025-11-25` and earlier |
| No `initialize` handshake | **Confirmed** | "There is no negotiation handshake. Every request carries its protocol version" (`2026-07-28/basic/versioning.mdx`) |
| `server/discover` RPC | **Confirmed** | "Servers **MUST** implement `server/discover`." Clients MAY call it first |
| No sessions | **Confirmed** | Changelog: "Remove protocol-level sessions and the `Mcp-Session-Id` header". A modern-only server given such a header "**SHOULD** ... ignore it, and do not mint or echo session IDs" |
| No `ping` | **Confirmed** | Changelog: "Remove `ping`, `logging/setLevel`, and `notifications/roots/list_changed`" |
| `Mcp-Method` / `Mcp-Name` required headers | **Confirmed** | "`Mcp-Method` ... All requests; `Mcp-Name` ... `tools/call`, `resources/read`, `prompts/get`. These headers are **REQUIRED** for compliance." A mismatch or a missing header -> `400` + `HeaderMismatch` (`-32020`) |
| `input_required` multi round-trip results | **Confirmed** | `InputRequiredResult` (`resultType: "input_required"`); applies to `tools/call`; "Servers **MUST NOT** send an `inputRequests` that the client has not declared support for" |
| (extra) `resultType` on every result, `ttlMs`/`cacheScope` on `tools/list`, no `Last-Event-ID`, `UnsupportedProtocolVersionError` `-32022`, GET stream gone | Confirmed | changelog items 8, 9, minor 5, 12 |

Statuses: `2026-07-28` Current; `2025-03-26`, `2025-06-18`, `2025-11-25` Final by the page's definition (it does not label each); a `draft` directory exists (not read). `2024-11-05` is out of scope.

## Facts needed for the northbound decision (not a decision)

- **(a) Handshake revisions only** (`2025-03-26` / `2025-06-18` / `2025-11-25`): stateless is spec-legal (session id is `MAY`, fact 5). Answer `initialize` (newest supported version, fact 1), `notifications/initialized` (202), `ping` ({}); `405` on `GET`/`DELETE`. To refuse `2026-07-28` so a dual-era client falls back: a `4xx` "without a recognized modern error body" (spec matrix). Returning `UnsupportedProtocolVersionError` listing legacy versions to a modern-only client has unverified outcome (that client has no `initialize` path). Plain `400` + `-32600` body is the safe default.
- **(b) Also serve `2026-07-28`**: add `server/discover`, per-request `_meta` version/capability parsing, the three headers + `HeaderMismatch`, `UnsupportedProtocolVersionError`, `resultType` and `ttlMs`/`cacheScope` on results, no `ping`. The spec allows one endpoint for both eras: "A request carrying modern per-request `_meta` is served statelessly ... An `initialize` request selects legacy semantics".
- **Which revision OpenCode and Cline most likely speak: legacy (`<= 2025-11-25`).** Both depend on the TypeScript `@modelcontextprotocol/sdk` v1 line: OpenCode `1.29.0` (`packages/opencode/package.json` at `810c0eba1a73`), Cline `^1.29.0` (`sdk/packages/core/package.json` at `a459f1d04dea`). That SDK's `SUPPORTED_PROTOCOL_VERSIONS` is `2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05, 2024-10-07` (`src/types.ts:4-6` at tag `v1.29.0` = `e12cbd70`; same at `1.32.2` = `3b73021a`). The v2 TS SDK (`v2.4.0` = `951fe560`) speaks both eras, but its client default is the legacy handshake unless `versionNegotiation` is `auto` or pinned (`docs/protocol-versions.md`). Python SDK `v1.30.0` (`8c2fa6ea`) is legacy-only; `v2.3.0` (`2118f14f`) carries `2026-07-28` types (dual-era; STORY-003 to confirm). **Not verified end to end**: STORY-002 must confirm with the clients' actual connect behaviour and static-`Authorization` support (fact 12).

## Code re-check (every line re-opened today on `20181cb`)

Unchanged since `2253871` (`git diff 2253871 HEAD` empty for these files; lines re-read): `action_policy.py:262` evaluate, `:348` evaluate_all; `action_adapters.py:440`, `:449`, `:509`, `:584-585`; `action_config.py:276`, `:457`, `:482`, `:724`, `:834`; `action_classifiers/__init__.py:31,46,76,91` (`tool.opaque` is in `RuleId` at `:76`); `tool_release.py:41`; `pattern_config.py:246-250`; `pii_policy.py:131`; `tests/corpora/actions/SOURCES.md:80,112,113,160,222,248`. Also confirmed: `usage_limits.admit(identity, charges_budget)` `usage_limits.py:139` (D13); `GET /audit/actions` `routers/admin.py:153` (STORY-017).

| Item | Today (file:line) | Differs from the PRD | Consequence | STORY |
|---|---|---|---|---|
| `action_audit.record` | `action_audit.py:214-221`: `record(decisions, identity, audit_ref=None, session_id=None)`; `decision_rows` `:195`, `_row_of` `:164`; `AuditRef` `audit_logger.py:20` | PRD cites `:95` and `audit_id=` | PRD 6.9/F10 text with `audit_id=` is stale. Extend with `mcp=None`; keyed rows `"<write_id>:<i>"` | 008 |
| O8 / journal | docstring `action_audit.py:232-243`; no-ref path `:251-253` (fresh `write_id`, `audit_id` NULL, `insert_action_decisions`); journal branch `:259-271` | "when PRD-018 lands" -> has landed | The pre-forward gateway write calls `record()` **without** `audit_ref`: it commits or raises, never journals. Confirmed (T9, D9) | 008, 013 |
| Added columns | `models.py:480` `ACTION_DECISIONS_ADDED_COLUMNS = {"write_id": "TEXT"}` (comment `:473`); applied `database.py:1502`, helper `:1508`; DDL `models.py:449`; `ActionDecisionRow` `:706`; unique `write_id` index `models.py:499` | D21/6.9 say "add a fourth mapping" | Extend the existing mapping, `ActionDecisionRow`, `_insert_action_decision_rows` (`database.py:3404`) and `insert_action_decisions` (`:3459`); `tests/test_db_resilience_write_id.py:302-307` iterates the mapping; the unique index must run after the added-columns pass | 008 |
| Step 7c | `query_pipeline.py:1622` (comment), `evaluate_all` `:1643`, `apply_decisions` `:1645`; steps 2b/2c/2d at `:697`/`:722`/`:792` | PRD `:813-840`; file grew | Hook point moved | 016 |
| Record-after-row | `query_pipeline.py:1778` (`journal_decisions=`), `AuditUnavailableError` handler `:1789`, `record(... audit_ref=)` `:1810` | PRD-018 journal: a journaled row (`audit_id` None) skips `record` | Correlation reads rows written here; unlinked gateway rows have `audit_id` NULL by design | 016 |
| Decision sites | exactly one call: `query_pipeline.py:1643` (grep of `app/` finds no other `evaluate_all(`/`action_policy.evaluate(` caller). Real-time `/v1` only renders: `v1_sse.py:194` ("Tool calls come only from the `Tail`"), `:295-298`; `routers/v1.py:433-445` `_realtime_tail` reads `pipeline.result().tool_outcome` | PRD-021 added no second site | One place to change; test buffered and real-time delivery | 016 |
| authz | `authz.py:33` `ACTION_PERMISSIONS` (6), `:50` `PERMISSION_REASONING_VIEW`, `:59` `_KNOWN_PERMISSIONS`, `:143` unknown-permission check, `:178` `authorize`, `:191` `holds` (matrix block `:71-95` not re-read line by line) | PRD-021 added `STREAM_PERMISSIONS` as a second group | Add `mcp:connect` and dynamic `skill:<id>` as a third group; `load()`'s check needs a pattern rule for `skill:<id>` | 004 |
| Docs | `docs/features.md:745,846,848,896`; roadmap MCP item `docs/roadmap.md:69-71`; websocket affinity shipped `:36`; `:33` is "Retry and circuit breaker", shipped | PRD cites `features.md:484-488,536`, `roadmap.md:33` | D3's `roadmap.md:33` rationale is stale; STORY-021 edits the right lines | 021 |
| requirements | `requirements.txt:16` `sqlglot==30.27.0`, `:17` `anthropic==2.11.0`; no `mcp` | `anthropic` added by PRD-022 | STORY-003's dependency diff is against today's file | 003 |
| PRD-022 | provider-chain attempt rows precede step 7 (`query_pipeline.py:1189`) | new | An alias decision is made once, on the answering attempt | 016 |

## Proposed PRD amendments (section and replacement text)

1. **6.1, D17, Section 15 Facts**: replace "`2025-06-18` plus `2025-11-25`, `2025-03-26`" with: "Supported revision strings: `2025-03-26`, `2025-06-18`, `2025-11-25` (handshake). The current revision is `2026-07-28` (per-request, no handshake): <supported / refused, per the orchestrator's decision>. On an `initialize` with an unknown version the server answers the newest supported handshake version." Fix "newest supported" wording accordingly.
2. **6.2 D3 / F1 (STORY-011)**: add "For handshake revisions `initialize`, `notifications/initialized` and `ping` are answered statelessly and no `Mcp-Session-Id` is issued (`MAY`, spec). A request with a modern `_meta` is <served: `server/discover`, `Mcp-Method`/`Mcp-Name` checks, `HeaderMismatch` `-32020`, `UnsupportedProtocolVersionError` `-32022`, `resultType`, `ttlMs`/`cacheScope`> / <refused with a plain `400` so a dual-era client falls back>." Header names are compared case-insensitively.
3. **T10**: replace the last sentence with: "Under the handshake revisions an unknown-session `404` obliges the client to re-initialize, but the spec does not say the request was not processed; the harness re-initializes for the next call and never replays a forwarded `tools/call`. Under `2026-07-28` there are no sessions: every post-forward failure is 'may have run'."
4. **T12**: add "Under `2026-07-28` an upstream may answer `tools/call` with `resultType: "input_required"` (MRTR). The harness declares no capabilities, so it refuses the result as a stated outcome; it never answers it (a retry is a new request) and never relays it northbound."
5. **6.9, D21, F10**: "extend `ACTION_DECISIONS_ADDED_COLUMNS` (it exists, `models.py:480`)", not "a fourth mapping"; signature `record(decisions, identity, audit_ref=None, session_id=None, mcp=None)`; the pre-forward write passes no `audit_ref` (O8), and `record_outcome` stays best effort.
6. **T9 / Dependencies**: PRD-018 has landed. **9.1**: `holds()` is `authz.py:191`. **6.2**: drop the `roadmap.md:33` rationale. **Evidence list**: renumber per the table above.
7. **O7**: set from the verified guidance: names "SHOULD" be 1-128 characters from `[A-Za-z0-9_.-]`; `__` and `-` are allowed, `.` is too (all SHOULD). Keep `<server>__<tool>`; add that a name over 64 characters is truncated and hashed by Cline (`tests/corpora/actions/SOURCES.md:160`), so cap server ids at 32 and warn/refuse a tool name that makes the combined name exceed 64 (client limit, STORY-002 to confirm).
8. **T11**: keep; note the spec requires only "present and invalid -> 403" (`2025-11-25`, `2026-07-28`), the PRD is stricter and compatible. **9.1** "static `Authorization` header" stays a stated limitation until STORY-002.

## Verify items: resolved or limitation

Resolved with a pinned source: 1, 2, 3, 5, 6, 7 (spec), 8, 9, 10, 13, 14, 15; T11, T12. Limitations (safe default given in SOURCES.md): **4** (the spec does not say a 404 means "not processed": never replay `tools/call`), **7** (client name limits: STORY-002), **12** (client behaviour on a 401 without metadata: STORY-002).

## Tasks Completed

| # | Task | File | Status |
|---|---|---|---|
| 1 | Pin revisions to commits | `tests/corpora/mcp/SOURCES.md` | done |
| 2 | Verify the 15 facts | `tests/corpora/mcp/SOURCES.md` | done |
| 3 | Code re-check | this report | done |
| 4 | Write SOURCES.md; every URL matches `/blob/<40-hex>/` (checked with grep) | `tests/corpora/mcp/SOURCES.md` | done |
| 5 | Report and amendments | this report | done |

## Validation Results

| Check | Result |
|---|---|
| `git status --short` | only `.agents/` files and `tests/corpora/mcp/SOURCES.md`; no `app/`, `tests/*.py` or `requirements` change |
| Backend import | `.venv/Scripts/python -c "from app.main import app; print('OK')"` |
| Tests | none (spike) |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Plan Task 3 says `v1_sse.py:182-200` and `:296-310`; the cited text is at `v1_sse.py:194` and `:295-298`. Corrected above.
- The plan did not list the TS/Python SDK pins; they were read only to answer the orchestrator's "which revision do OpenCode/Cline speak" question and are not an SDK pin (STORY-003) or a client survey (STORY-002).

## Acceptance Criteria

- [x] AC1: `tests/corpora/mcp/SOURCES.md` records the facts with pinned links (revisions, batching, header spellings, 404 rule, stateless header, `instructions`, tool names, unknown-tool code, `Origin`, `notifications/cancelled`)
- [x] AC2: code re-check with every divergence and its consequence (table above)
- [x] AC3: every verify item resolved or a stated limitation; T10 corrected, T11 confirmed, T12 confirmed with an MRTR addition
- [x] AC4: no application code changed; amendments proposed above
