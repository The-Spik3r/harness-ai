---
story: STORY-016
prd: PRD-021
slug: streaming-docs
title: Document real-time streaming, grants and progress feedback
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-19
---

# Plan: Document real-time streaming, grants and progress feedback

## Summary

Docs only. Rewrite the buffered-only statements in `docs/features.md` (OpenAI-compatible endpoint, Tool calling, Providers "What it does not do"), add a real-time delivery subsection (visibility matrix, held tool calls, `reasoning_content`, error-after-commit, residual risks, measured costs, verified clients). Add the three settings to `.env.example` and `docs/configuration.md`, an `RBAC_ROLES_FILE` grant example, README edits, and mark PRD-021 delivered in `docs/roadmap.md` with PRD Section 13 as open items. Every number comes from `app/config.py` or a report, never from the PRD alone (sources below).

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-016-streaming-docs.md`
- PRD sections used: 4 (Documentation), 6.4, 6.6, 9.2 (T1, T3, T6, T9, T12), 9.3, 13, 14 (Risks 1, 2, 4)
- Systems affected: `docs/features.md`, `docs/configuration.md`, `docs/roadmap.md`, `docs/api.md`, `README.md`, `.env.example`. No code.

## Design Decisions

none beyond the tasks (not a critical story). Rules for the writer:

**Numbers and defaults, with source** (re-grep before writing):

| Fact | Value | Source |
|---|---|---|
| `STREAMING_ENABLED` | `false` | `app/config.py:393` |
| `STREAM_HOLDBACK_MAX_CHARACTERS` | `400`, valid 100..4000 | `app/config.py:394`, validator `:761-770` |
| `STREAM_COALESCE_MS` | `50`, valid 0..500 | `app/config.py:395`, validator `:774-783` |
| `V1_SSE_KEEPALIVE_SECONDS` | `10`, >0 and <=60 (unchanged) | `app/config.py:388` |
| Gate cost (2000-char reply, 12-char deltas, 50 runs, `scripts/measure_stream_gate_latency.py`) | chat segment p50/p95/max 13.1/16.7/20.1 ms; response p95 530.9 ms vs final pass p95 87.5 ms; code with `PII_CODE_REDACT_OUTPUT` on: 2.1/3.3/3.8 ms, response p95 27.2 ms, final 8.8 ms; the Risk 2 batching fallback (150 ms) was not needed | STORY-008 report, "AC5: latency" table |
| First-content latency | NOT a measured figure: `tests/test_v1_realtime.py:882` asserts p95 <= upstream delay + 0.1 s (20 runs, 30 ms between 8-char upstream pieces, `STREAM_COALESCE_MS=50`, in-process). Document it as a test-enforced bound with those conditions | `tests/test_v1_realtime.py:887-906`; STORY-010 report AC5 |
| Chat batch window | at most 100 ms per `async with self` window | STORY-011 report Summary |

The STORY-008 report states no machine or OS for its numbers: document only what it states; do not invent Python/OS. If a measured, condition-complete figure is wanted, the orchestrator must ask for a rerun of the script.

**Verified clients** (STORY-014/015 reports):
- OpenCode v2.3.2: real time verified end to end (5 passed, live `--run-e2e`, 2026-11-19). Reasoning shows only with `--thinking`; provider config `compatibility.reasoningField: reasoning_content` (opencode.ai/docs/models); OpenCode accepts unknown keys silently, and with `--thinking` it also displayed the stub's reasoning without the key (observation, not asserted).
- Cline 3.0.74: real time verified end to end (5 passed); it displays `reasoning_content` (3 reasoning agent events).
- Both ran against the stub upstream, not a live model; the e2e modules are opt-in (`--run-e2e`).
- Any other client: "not verified" (Risk 4: grant `reasoning:view` only to roles whose client is verified).
- `tests/e2e/test_opencode.py` still pins 2.0.10 and one test of it fails on 2.3.2 (STORY-014 report): never claim 2.0.10 for real time.

**STORY-013 facts**: `GET /audit` fields `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence`, `completion_id`; exact-match `?completion_id=` (1..128 chars, empty is 422, applied after scoping); Register `LIVE` tag on `streamed_realtime` rows. Confirm names and types in `app/models/schemas.py` (`AuditQueryEntry`) and `app/routers/admin.py` before writing.

**Statements to make**:
- Legacy mode (no `PROVIDERS_FILE`) never streams (OD1): real time needs a providers-file model with `capabilities.streaming: true` (`reasoning: true` for reasoning).
- Residual risks: released text cannot be recalled and the `stream_redaction_divergence` column plus a `WARNING` naming user and completion id, never content (T12); reasoning may echo the client's own `system` prompt or a tool result (T3), is redacted under every policy, never persisted, not checked as an answer; a crash mid-stream leaves released text unrecorded, findable through the `INFO` line at commit (T9); usage is estimated when the provider sends none (T6, `usage_estimated`).
- Out of scope, say so: real time on `POST /query`, tools in the chat, per-call early release, reasoning storage.

## Skills In Use

| Skill | Why | Tasks |
|---|---|---|
| none | story `skills: []`; `.agents/skills/` holds only `frontend-design` (UI, not docs) | n/a |

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Section voice | `docs/features.md:253`, `:340` | Bold claim first; every figure followed by its measuring conditions and the script |
| Limitation bullets | `docs/features.md:260`, `:674` | Rewrite the "No real token streaming" / "Streaming is buffered" bullets, do not append |
| Config table row | `docs/configuration.md:60` | `\| NAME \| No \| default \| prose with the startup-error range \|` |
| `.env.example` entry | `.env.example:195-198` | `#` comment line(s) immediately above `NAME=value` |
| Roles example | `docs/features.md:558-563` | JSON restating all three built-in roles plus a custom one |
| Roadmap entry | `docs/roadmap.md:9-18` (Shipped list), `:52-54` | `- [x] [Title](link) - one line`, plus a "Still not covered" tail |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `docs/features.md` | UPDATE | Rewrite `:253`, `:260`, `:515`, `:661`, `:674` (grep "buffered"); new "Real-time delivery" subsection under `### OpenAI-compatible endpoint` |
| `docs/configuration.md` | UPDATE | Three rows after `:60`; amend the `RBAC_ROLES_FILE` row (`:23`) to name the two new grantable permissions |
| `.env.example` | UPDATE | Three variables after `:198`, comment line directly above each |
| `README.md` | UPDATE | `:157` ("`stream: true` is answered after the whole response has been checked"); Chat UI section and the limitation at `:320`; features line; setup steps near `:179`/`:208` |
| `docs/roadmap.md` | UPDATE | Shipped entry, `:52`/`:54` text, Section 13 items |
| `docs/api.md` | UPDATE | `GET /audit` four fields and `?completion_id=`; real-time chunk shapes, `reasoning_content`, error-after-commit |

## Tasks

### Task 1: features.md
- **File**: `docs/features.md`
- **Implement**: (a) Rewrite `:253` into the two delivery modes: buffered (default, today's keep-alives then one chunk) and real time. (b) New subsection: the four-row visibility matrix (PRD 6.4; `STREAMING_ENABLED=false` collapses to row one; a model without `streaming` is delivered buffered for that request and the row says so; no `reasoning` capability means no reasoning whatever the grant); the permissions `stream:realtime` and `reasoning:view` (no built-in role holds them; read regardless of `RBAC_ENABLED`, like `action:*` at `:555`); the settings; the chunk sequence (PRD 6.6: role chunk at commit, `reasoning_content` deltas, content segments, whole tool calls after content, denial notes, finish chunk last, usage chunk, `[DONE]`); verdicts keep their real `400`/`403` before commit; error after commit is one `error` event and no `[DONE]`; a disconnect does not cancel the pipeline (`:338`). (c) Held tool calls: never streamed in pieces, they leave once after the stream ends and the action policy decided (T1); rewrite `:661`, `:674`. (d) Replace the `:260` bullet. (e) `:515`: upstream streaming now exists behind the switch. (f) "What it costs" for real time from the table above, conditions included. (g) Residual risks. (h) Verified clients plus the `--thinking` / `reasoningField` note; link the two Setting-up sections. (i) Audit fields, `?completion_id=`, Register `LIVE`. (j) Chat UI: progress word plus seconds after 300 ms (PRD 7.1, STORY-012 report), live answer with `stream:realtime`, collapsible reasoning block with `reasoning:view`, kept in memory only, chat sends no tool calls. Include the `RBAC_ROLES_FILE` example restating `admin`, `auditor`, `user` plus a role granted `stream:realtime` (and `reasoning:view`).
- **Mirror**: `docs/features.md:253`, `:340`, `:555-563`
- **Validate**: `grep -n "buffered" docs/features.md` leaves only qualified mentions; `tests/test_providers_docs.py`

### Task 2: settings
- **Files**: `.env.example`, `docs/configuration.md`
- **Implement**: `STREAMING_ENABLED=false`, `STREAM_HOLDBACK_MAX_CHARACTERS=400`, `STREAM_COALESCE_MS=50`, each with a `#` comment directly above (regex pinned in `tests/test_config.py`: `^#.+\n{var}=`) stating default, range and effect, and that real time also needs a providers-file model with `streaming: true` and a role granted `stream:realtime`. `docs/configuration.md`: exactly one `| \`NAME\` |` row each (`tests/test_providers_docs.py:66-68`; documented names are cross-checked against `Settings`).
- **Mirror**: `.env.example:195-198`, `docs/configuration.md:60`
- **Validate**: `tests/test_config.py tests/test_providers_docs.py`

### Task 3: README
- **File**: `README.md`
- **Implement**: AC3 text (three variables with defaults, the `RBAC_ROLES_FILE` grant linking the features example, "real time needs a providers-file model with `streaming: true`; legacy mode never streams"). Fix `:157` and `:320`. Keep the `docs/features.md#providers` link (pinned, `tests/test_providers_docs.py:139`).

### Task 4: roadmap
- **File**: `docs/roadmap.md`
- **Implement**: Shipped `[x]` entry "Real-time streaming (PRD-021)" with verified clients; fix `:52` and `:54` ("real streaming (the stream is still buffered)" is no longer true). Add the seven PRD Section 13 items, unchecked: per-call early release, write-ahead audit row (O3), reasoning audit store (O2), progress words for `/v1` via a side channel, streaming on `POST /query`, admin-console grant editor, native-adapter reasoning formats (PRD-022). Copy names from the PRD section.

### Task 5: api.md
- **File**: `docs/api.md`
- **Implement**: `GET /audit` (`:158-233`): four fields and `?completion_id=`; `/v1` section: real-time chunk shapes, `reasoning_content`, error-after-commit. Verify field names against `AuditQueryEntry` first.

## End-to-End Tests

- [ ] No runtime change. `grep -n "STREAM_\|STREAMING_ENABLED" app/config.py` matches every documented default and range.
- [ ] Every internal link added resolves to a real `##`/`###` heading in its target file.
- [ ] No claim of a live-model run: the client runs used the stub upstream.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# Docs-pinning tests (found by grepping tests/ for features.md, README, .env.example, roadmap):
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_providers_docs.py tests/test_config.py tests/test_caddyfile_routes.py
```

`tests/test_providers_docs.py` (configuration.md rows, `.env.example`, features.md `### Providers`, README link) and `tests/test_config.py` (`.env.example` comment-above-variable regexes) pin docs content. `tests/test_caddyfile_routes.py` mentions docs paths. `tests/test_two_instance_smoke.py` also mentions docs: run it only if it is DB-free. No test pins roadmap.md. No `app/` change, so no `test_untouched_app.py`. One pytest at a time.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Proof |
|---|---|---|
| AC1 features.md: no unqualified "buffered"; matrix, permissions, switch, held calls, `reasoning_content`, error-after-commit, residual risks | Task 1 | grep review; `tests/test_providers_docs.py` still green |
| AC2 gate and latency numbers with conditions | Task 1 (f) | numbers diffed against the STORY-008 table and `tests/test_v1_realtime.py:882-906` |
| AC3 three variables with defaults in `.env.example` and README; `RBAC_ROLES_FILE` grants `stream:realtime`; legacy never streams | Tasks 2, 3 | `tests/test_config.py` regexes, `tests/test_providers_docs.py` |
| AC4 roadmap delivered, Section 13 items, verified clients | Task 4 | diff against STORY-014/015 reports |

## Risks / open questions

- STORY-008 numbers have no stated host; STORY-010's first-content figure is a test bound, not a measurement. Tell the orchestrator if a measured value is wanted.
- `docs/configuration.md` rows must name only real `Settings` fields.
- The story's line numbers (`:241,248,476,489`) are stale; use grep.
