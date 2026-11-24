---
story: STORY-001
prd: PRD-023
slug: mcp-protocol-spike
title: Spike — verify the MCP protocol facts and re-check the PRD's code evidence against main
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: MCP protocol spike

## Summary

Research only. The implementer reads the published MCP spec (pinned), writes `tests/corpora/mcp/SOURCES.md` (protocol section only) and the story report with the code re-check and proposed PRD amendments. No application code, tests or requirements change.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-001-mcp-protocol-spike.md`
- PRD sections used: 6.1, 9.1, 9.2 (T9-T12), 12 Phase 1, 15 (Facts to verify, Evidence, D17, O7, O11)
- Systems affected: none (corpus and report only)

## Design Decisions

- Deliverables exactly: `tests/corpora/mcp/SOURCES.md` (new; a `## Protocol` section only; STORY-002/003 append client and SDK sections), the report, and a PRD-amendment list (section + replacement text) in the report.
- Every link pinned to a revision directory (`/specification/<rev>/...`) or a commit SHA of `modelcontextprotocol/modelcontextprotocol`; never `latest`, `draft` or a branch. Record the fetch date.
- Each verify item ends as `resolved: <fact> (<pinned source>)` or `limitation: <statement> (safe default)`. Unverified means "not verified" plus the safe default, never fact.
- Do not survey clients (STORY-002) or pin the SDK (STORY-003). The 9.1 check "both clients accept a static Authorization header" is carried as `limitation: not verified here (STORY-002)`.
- SOURCES.md layout mirrors `tests/corpora/actions/SOURCES.md:1-30` (fetch date, pinned-link rule, one table per topic).

## HEADLINE FINDING (seen while planning; confirm first)

`https://modelcontextprotocol.io/specification/versioning` (fetched 2026-11-22) says the **current revision is `2026-07-28`**, not `2025-11-25` as PRD 6.1 and D17 assume. Its changelog (`/specification/2026-07-28/changelog`) reports: no `initialize` / `notifications/initialized` handshake (per-request `_meta` `io.modelcontextprotocol/protocolVersion` and `clientCapabilities`); a mandatory `server/discover` RPC; **`Mcp-Session-Id` and protocol sessions removed**; `ping` removed; `UnsupportedProtocolVersionError` (code -32022); `Mcp-Method` / `Mcp-Name` required headers on POST; server-to-client requests replaced by Multi Round-Trip Requests (`resultType: "input_required"` with `inputRequests`); `resultType` required on every result; `ttlMs` / `cacheScope` on list results; Roots, Sampling, Logging and HTTP+SSE deprecated; `Last-Event-ID` resumability removed; unknown-resource code now -32602. Handshake revisions are `2025-11-25` and earlier. The implementer reads these pages in full and settles what the harness supports northbound and southbound (amendments below). It is a finding for the orchestrator, not a design decision for the spike.

## Skills In Use

`.agents/skills/` holds only `frontend-design` (no UI here). None apply.

## Tasks

### Task 1: Pin the spec revisions
- Read `/specification/versioning`, then each revision's index and changelog: `2026-07-28`, `2025-11-25`, `2025-06-18`, `2025-03-26`. Resolve each revision to a commit SHA in `modelcontextprotocol/modelcontextprotocol` (`gh api` on tags or on commits touching `docs/specification/<rev>`) and pin links to it.
- Output: supported revision strings for D17, each revision's status (Final/Current/Draft), the negotiation rule per revision (handshake for `2025-11-25` and earlier; per-request for `2026-07-28`) and what a server answers to an unknown version.

### Task 2: Verify each protocol fact (note per revision where it differs)
| # | Fact | Where to look |
|---|---|---|
| 1 | Supported revision strings (D17) | `versioning`, each `changelog` |
| 2 | Batching removed in `2025-06-18` (and absent later) | `2025-06-18/changelog`, `basic/index` |
| 3 | Exact `Mcp-Session-Id` and `MCP-Protocol-Version` spellings; `Mcp-Method` / `Mcp-Name` (2026-07-28); header case rule | `basic/transports` (<= 2025-11-25), `basic/transports/streamable-http` (2026-07-28) |
| 4 | Expired session gives 404; does 404 mean not processed (T10) | `basic/transports`, "Session Management" |
| 5 | A stateless server may omit the session header | same section; 2026-07-28 removes sessions |
| 6 | `InitializeResult.instructions` (since which revision); the 2026-07-28 equivalent | `basic/lifecycle`, schema |
| 7 | Tool-name charset and length guidance (O7: are `__` and `-` allowed) | `server/tools`, "Tool Names" (check each revision) |
| 8 | Unknown-tool error code (-32602) and protocol error vs `isError` split | `server/tools`, "Error Handling" |
| 9 | `Origin` validation requirement and the 403 wording (T11) | `basic/transports`, "Security Warning" |
| 10 | `notifications/cancelled` is the cancellation method; its status in 2026-07-28 | `basic/utilities/cancellation` |
| 11 | T12: sampling / roots / elicitation per revision; treatment of a client that declares no capabilities; MRTR `input_required` from an upstream tool call and what the harness must do with it | `client/*`, `basic/patterns/mrtr`, lifecycle capabilities |
| 12 | 9.1: spec-following client behaviour on `401` without `resource_metadata` | `basic/authorization` |
| 13 | Tool `annotations` are hints, content block types, `resource_link` | `server/tools`, schema |
| 14 | `tools/list` pagination, `listChanged`, `ttlMs` / `cacheScope` | `server/tools`, changelog |
| 15 | Streamable HTTP POST: JSON or SSE answer, `Accept` rule, 202 for notifications, JSON-only server allowed | streamable-http section |
- Confirm or correct T10, T11, T12. T10 in particular: under `2026-07-28` no unknown-session reply exists, so "the single safe retry is re-initialize" holds only for handshake revisions; elsewhere any post-forward failure is "may have run".
- Fetch the `.md` variant of each page and quote the normative sentence (MUST/SHOULD); cross-check names against `schema/<rev>/schema.ts` at the pinned commit. WebFetch summarizes through a model, so do not rely on a paraphrase.

### Task 3: Code re-check (re-open every cited line before writing it)
Unchanged since `2253871` (`git diff 2253871 HEAD` is empty for these files, so the PRD numbers still hold): `action_policy.py:262-345` evaluate, `:348` evaluate_all; `action_adapters.py:440` map_tool_call (`:449` prefixed-names note), `:509` BUILT_IN_TOOLS (`query` `:584`, `execute_sql` `:585`); `action_config.py:276` rules (25, verified), `:457`/`:482` validators, `:724` BUILT_IN_POLICY, `:834` `_FILE_SECTIONS`; `action_classifiers/__init__.py:31,46,91`; `tool_release.py:41`; `pattern_config.py:246-250`; `pii_policy.py:131`; `tests/corpora/actions/SOURCES.md:80,112-113,160,222,248`.

Divergences (the report lists each as current file:line, what changed, consequence, STORY):

| Item | Today | Change | Consequence |
|---|---|---|---|
| `action_audit.record` | `app/services/action_audit.py:214-221`: `record(decisions, identity, audit_ref=None, session_id=None)` (PRD: `:95`, `audit_id=`) | `AuditRef` (`audit_logger.py:20`) replaces `audit_id`; keyed rows `"<write_id>:<i>"`; builder `decision_rows` `:195`, `_row_of` `:164` | STORY-008 extends this signature and builder (`mcp=`); PRD 6.9/F10 text with `audit_id=` is stale |
| O8 / journal | docstring `action_audit.py:232-242`; journal branch `:259-270` | a pre-execution write passes no `audit_ref`: commits or raises, never journals; with none, a fresh batch hex is minted and `audit_id` is NULL (`:251-253`) | STORY-013 writes pre-forward without a ref; STORY-008 keeps and tests that path; T9's "when it lands" is now "has landed" |
| Added columns | `app/db/models.py:480` `ACTION_DECISIONS_ADDED_COLUMNS = {"write_id": "TEXT"}` (comment `:473` calls it the fourth mapping); applied `database.py:1502`, helper `:1508`; DDL `models.py:449`; `ActionDecisionRow` `:706` | already exists | STORY-008 extends the mapping, `ActionDecisionRow`, `_insert_action_decision_rows` (`database.py:3404`) and `insert_action_decisions` (`:3459`); D21/6.9 "fourth mapping" becomes "extend"; `tests/test_db_resilience_write_id.py:302-307` iterates it; the unique `write_id` index (`models.py:499`) must run after the added-columns pass |
| Step 7c | `query_pipeline.py:1622-1650` (`evaluate_all` `:1643`, `apply_decisions` `:1645`); PRD `:813-840` | file grew; 2b/2c now `:697`/`:722`, 2d `:792` | STORY-016 hooks here |
| Record-after-row | `query_pipeline.py:1778-1834` (`journal_decisions` `:1778-1787`, `ActionAuditError` `:1789-1799`, `record(... audit_ref=)` `:1810-1834`) | PRD-018 journal: a journaled row (`audit_id` None) skips `record` | STORY-016 correlation reads rows written here; unlinked gateway rows have `audit_id` NULL by design |
| Decision sites | exactly one: `query_pipeline.py:1643`. Buffered `/v1` and PRD-021 real-time both reach it; real-time only renders its result (`v1_sse.py:182-200` "Tool calls come only from the Tail", `:296-310`; `routers/v1.py:434-445` `_realtime_tail` reads `pipeline.result().tool_outcome`) | PRD-021 adds no second decision site | STORY-016 changes one place; test both delivery modes |
| authz | `authz.py:33` `ACTION_PERMISSIONS` (6), `:50` `STREAM_PERMISSIONS`, `:59` `_KNOWN_PERMISSIONS`, matrix `:71-95`, `authorize` `:178`, `holds` `:191` (PRD `:29-48`, `:155`, `:168`) | PRD-021 added a second permission group | STORY-004 adds `mcp:connect` and dynamic `skill:<id>` as a third group; `load()`'s unknown-permission check (`:143`) needs a pattern rule for `skill:<id>` |
| Docs | `docs/features.md` MCP-prefix notes `:745,848,896` (PRD `:484-488,536`); schemas-uninspected `:846` (PRD `:486`); roadmap item `docs/roadmap.md:69-77`; websocket affinity shipped (`:36`) | | PRD 6.2 D3's `roadmap.md:33` rationale is stale; STORY-021 edits the right lines |
| requirements | `anthropic==2.11.0` added (PRD-022); still no `mcp`; `sqlglot==30.27.0` precedent stays | | STORY-003's dependency diff is against today's file |
- Also confirm: `usage_limits.admit(identity, charges_budget)` `usage_limits.py:139` (D13); `/audit/actions` `routers/admin.py:153` (STORY-017); `tool.opaque` already in `RuleId` (`action_classifiers/__init__.py:76`).
- PRD-022 note: provider-chain attempt rows precede step 7 (`query_pipeline.py:1189`), so an alias decision is made once, on the answering attempt.

### Task 4: Write `tests/corpora/mcp/SOURCES.md`
A `## Protocol` section: revision table, the 15-fact table (fact, result, `resolved`/`limitation`, pinned link), per-revision differences, confirmed T10/T11/T12 verdicts. No client or SDK sections.
- Validate: only `/specification/20..` or `blob/<40-hex>` links; no `latest`, `draft` or branch in any URL.

### Task 5: Write the report and amendments
Report path and template per `.agents/commands/implement.md` (check it). Contents: fact table, code re-check table with each consequence mapped to a STORY, the amendments.

## Proposed PRD amendments the report must carry (confirm or refine after Task 2)
1. **6.1, D17, 15 Facts**: replace "`2025-06-18` plus `2025-11-25`, `2025-03-26`" with the verified set, including `2026-07-28` (or state why it is unsupported) and exact strings.
2. **6.2 D3 / F1 (STORY-011)**: for handshake revisions `initialize`, `notifications/initialized` and `ping` are answered statelessly and no `Mcp-Session-Id` is issued; if `2026-07-28` is supported also `server/discover`, per-request `_meta` version, `Mcp-Method` / `Mcp-Name` checks and `UnsupportedProtocolVersionError`.
3. **T10**: the re-initialize retry applies to handshake revisions only; under `2026-07-28` every post-forward failure is "may have run".
4. **T12**: an upstream `resultType: "input_required"` (MRTR) is refused, recorded as a stated outcome, never answered (the harness declares no capabilities).
5. **6.9, D21, F10**: "extend `ACTION_DECISIONS_ADDED_COLUMNS`", not "fourth mapping"; `record(decisions, identity, audit_ref=None, session_id=None, mcp=None)`; the pre-forward write passes no `audit_ref` (O8).
6. **T9 / Dependencies**: PRD-018 has landed. **9.1**: `holds()` is `authz.py:191`. **6.2**: drop the `roadmap.md:33` rationale. **Evidence list**: renumber per Task 3.
7. **O7**: set from the verified tool-name guidance (charset, length, whether `__` and `-` fit).

## Files to Change
| File | Action | Purpose |
|---|---|---|
| `tests/corpora/mcp/SOURCES.md` | CREATE | protocol facts, pinned |
| report file (path per implement.md) | CREATE | re-check and amendments |
| story file | UPDATE | `plan`/`status` done by the planner; `report`, `commit`, done by the implementer |

## Validation
```bash
git status --short   # only the files above; no app/, tests/*.py or requirements change
.venv/Scripts/python -c "from app.main import app; print('OK')"
```
No pytest run: no code or test is touched.

## Acceptance Criteria -> Tasks -> Proof
| AC | Task(s) | Proof |
|---|---|---|
| AC1 protocol facts pinned | 1, 2, 4 | SOURCES.md fact table |
| AC2 code re-check with consequences | 3, 5 | report re-check table |
| AC3 every verify resolved or limitation; T10/T11/T12 confirmed or corrected | 2, 4, 5 | SOURCES.md + report |
| AC4 no app code; amendments proposed | 5 | `git status` + report amendments |

## Risks
- The headline finding may reshape the epic (a hand-written stateless northbound; which `mcp` SDK version speaks `2026-07-28` southbound, a STORY-003 question). Report it at once; do not choose the design.
- WebFetch paraphrases: quote normative wording from the `.md` pages.
