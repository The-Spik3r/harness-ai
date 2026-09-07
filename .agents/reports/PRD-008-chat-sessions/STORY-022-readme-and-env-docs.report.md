---
story: STORY-022
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-022-readme-and-env-docs.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: 7525223
status: COMPLETE
completed: 2026-09-07
---

# Implementation Report — STORY-022: README and .env, documenting the persistence model the code actually has

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-022-readme-and-env-docs.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `7525223`

## Summary

`README.md` now describes the release PRD-008 actually shipped. Nine edits land the ten acceptance
criteria: the two new settings in the environment table, `session_id` on `POST /query` with both its
refusals, `session_id` in the `GET /audit` shape, a new **What is stored, and who can read it**
subsection carrying the at-rest change, a **Session rail** paragraph in the Chat UI section, the two
new tables in the architecture diagram, and chat sessions in the Roadmap's Shipped list with
multi-turn context below the intended-direction line.

`.env.example` was **not** changed. AC 10 asked that it match `app/config.py` exactly, and it already
did — 18 settings declared, 18 documented, in declaration order, each with a comment, nothing extra.
The plan scoped this as a verification with an explicit instruction not to edit a passing file; the
check was run mechanically in both directions and recorded below rather than performed by eye.

No application code changed. The only file touched outside `README.md` is a stale comment in
`tests/test_two_instance_smoke.py`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Architecture diagram gains the transcript write and both new tables; one Features row | `README.md` | ✅ |
| 2 | **Session rail** paragraph; Known limitations rewritten | `README.md` | ✅ |
| 3 | **What is stored, and who can read it**; four-table correction; two-instance correction | `README.md` | ✅ |
| 4 | `CHAT_HISTORY_ENABLED` and `CHAT_SESSION_LIMIT` rows in the environment table | `README.md` | ✅ |
| 5 | `session_id` on `POST /query`; the 422; a new 403 block | `README.md` | ✅ |
| 6 | `session_id` in the `GET /audit` example and closing paragraph | `README.md` | ✅ |
| 7 | Roadmap **Shipped** gains chat sessions | `README.md` | ✅ |
| 8 | Planned bullet plus `### Multi-turn context` below the line | `README.md` | ✅ |
| 9 | Stale `README.md:456` citation replaced with a section name | `tests/test_two_instance_smoke.py` | ✅ |
| 10 | `.env.example` verified against `app/config.py` — no edit needed | `.env.example` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `tests/test_config.py` | ✅ (36 passed) |
| Full suite `pytest tests/ -q` | ✅ (1680 passed, 2 pre-existing warnings) |
| `tests/test_two_instance_smoke.py` collection after the comment edit | ✅ (10 collected) |
| `.env.example` ↔ `app/config.py` symmetric difference | ✅ (18/18, empty both ways) |
| README JSON blocks parse | ✅ (9/9) |
| README in-page anchors resolve | ✅ (21/21) |
| 403 detail string byte-identical to `app/routers/query.py:15` | ✅ |
| E2E checklist | ✅ (6/6) |

**A note on suite flakiness, recorded rather than hidden.** The full suite was run three times. The
first and third were green at 1680 passed. The second reported one failure
(`test_query_session_id.py::test_a_malformed_session_id_is_a_422_from_validation[not-a-uuid]`) and one
error (`test_pii_redaction_integration.py::test_no_raw_pii_fragment_reaches_openrouter[...]`). Both
passed in isolation immediately afterwards, and the third full run was green with no intervening
change of any kind. This story alters no application code, so it cannot produce a behavioural failure;
the signature matches the known degradation of the local libSQL dev server under repeated whole-suite
runs, whose remedy is restarting the server rather than bisecting. Noted here so that a future reader
who sees it does not go looking for it in this diff.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +61/-8 |
| `tests/test_two_instance_smoke.py` | UPDATE | +4/-2 (comment only) |
| `.env.example` | VERIFIED, unchanged | — |

## Deviations from Plan

Three, all recorded rather than silent.

**1. Task 3 restructured the "Multiple instances" bullet list instead of editing one bullet in place.**
The plan said to correct the "No production two-instance validation yet" bullet and keep the other
two. Once corrected, the fact is no longer an absence, so it no longer belongs under a heading that
reads **What is not included**. Leaving it there would have produced a third bullet contradicting its
own list header and duplicating the two genuine gaps above it. The proof moved up into the section's
prose as its own paragraph, and the bullet list now holds only the two things that really are missing
(no balancer or health-check configuration, no websocket session affinity). The "unblocked, not
delivered" framing was kept, as the plan required.

**2. One factual error was introduced during Task 3 and caught by the plan's own E2E step.**
The first draft of **What is stored, and who can read it** claimed the raw upstream response "is not
stored anywhere". Reading the section back against the Ground Truth table — the plan's E2E item that
exists for exactly this — sent me to `app/services/query_pipeline.py:170-174`, which passes
`openrouter_result.response` (raw, pre-redaction) to `log_query`, and to
`app/services/audit_logger.py:37`, which stores its first 500 characters as `response_preview`. The
raw output *is* stored, in `audit_logs`, exactly as it was before this release. The sentence now says
that no raw model output reaches `chat_messages` and that it survives only as the audit preview this
release did not touch — which is both true and consistent with the existing `GET /audit` paragraph
two sections down. Recorded here because a security claim that overstates what is *not* retained is
the worse direction for this particular error to run.

**3. No tests were written, deliberately.** The command's Phase 4 requires a test per new function;
this story adds no function and no application code. The suite was checked for precedent before
deciding: no test in `tests/` asserts README content, and the only reference to the file was the
comment Task 9 fixed. Inventing a README-grep guard would have introduced a convention the repository
does not have, outside the plan's stated scope. AC 10 is already covered mechanically by the eight
`.env.example` assertions in `tests/test_config.py`, which pass unchanged.

## Findings

**Finding 1 — two README claims were already false before this story, from two different epics.**
Both sat inside sections this story rewrites and were corrected in the same pass:

- `README.md:218` listed "No persisted chat history" as an MVP limitation. PRD-008 removed it.
- `README.md:220` listed "No visible indicator when PII is masked". PRD-004 STORY-009 shipped the
  badge (`chat_ui/chat_ui/copy.py::PII_BADGE_TEMPLATE`, `tests/test_pii_badge.py`). This one had been
  stale for an entire epic, which is the argument for reconciling the README against the code at the
  end of every epic rather than only when a story names the file.

**Finding 2 — `README.md:240` contradicted a test this story depends on.** It said two-instance
operation had no end-to-end proof and was "still outstanding work, not a completed test."
`tests/test_two_instance_smoke.py` — extended by STORY-021, this story's own dependency — starts two
processes against one database and asserts a session written through the first is served by the
second. PRD-008's own Executive Summary already cites that test. Corrected in Task 3.

**Finding 3 — cross-file line-number citations rot silently.**
`tests/test_two_instance_smoke.py:462` cited `README.md:456` for the three-override in-container test
command. Every edit in this story is above that line; the block now starts at `:500`. Nothing fails
when this drifts — no assertion reads it — so it decays invisibly. Task 9 replaced the number with the
section name (*Running Tests*) and recorded why beside it, so the next README edit cannot repeat it.

**Finding 4 — an undocumented behaviour that the PRD does not describe and the code does.**
`ChatState._do_send` appends and persists the user's bubble *before* it lazily creates the session
(`chat_ui/chat_ui/state.py:979-1006`), so on a brand-new chat `session_id` is `""` at that moment and
`_append_and_persist`'s guard skips the write. **The first user turn of a new chat is never
persisted**, and a restored first conversation begins at the assistant's reply — the code says so in
its own comment, the PRD does not mention it, and no acceptance criterion in the epic covers it. It is
now a Known limitation in the README. Whether it should be *fixed* rather than documented is a
question for a follow-up: creating the session before the first append would close it, at the cost of
letting a slow create delay the bubble the user just typed, which is the trade STORY-013 deliberately
made in the other direction.

## Tests Written

None. This story changes documentation and one comment; it adds no function. See Deviation 3 for the
reasoning and the precedent check behind that decision.

## Acceptance Criteria

- [x] Environment table carries `CHAT_HISTORY_ENABLED` and `CHAT_SESSION_LIMIT` with defaults and
      effect, alongside `PII_REDACTION_ENABLED` and `RBAC_ENABLED` — `README.md:316-317`
- [x] `POST /query` documents `session_id` as optional, with the `422` on a malformed value and the
      `403` on a foreign one — `README.md:352`, `README.md:370-376`
- [x] `GET /audit` shows `session_id` in the response shape — `README.md:439`, `README.md:449`
- [x] The persistence section states what is stored: the prompt as typed and the redacted response,
      per session, readable only by the owner; and that `audit_logs` still holds hashes and truncated
      previews, unchanged — `README.md:245-257`
- [x] The same section states what `CHAT_HISTORY_ENABLED=false` does and that it is a supported
      configuration, not a degraded mode — `README.md:253`
- [x] Deletion is documented as removing the transcript and leaving the audit record intact —
      `README.md:255`
- [x] The Chat UI section describes the session rail as it behaves, including creation on the first
      send rather than on page load — `README.md:225`
- [x] Roadmap **Shipped** carries chat sessions; **Planned** carries multi-turn context with the
      duplicate-detection consequence stated, below the intended-direction line — `README.md:569`,
      `README.md:574`, `README.md:582-590`
- [x] The architecture diagram shows both new tables alongside `audit_logs` and `users`, and the
      pipeline line is unchanged — `README.md:99-113`, `README.md:117`
- [x] `.env.example` matches `app/config.py` exactly — verified 18/18 in both directions, unchanged
- [x] All tasks completed
- [x] Full test suite passes (1680)
- [x] No application code changed
- [x] Follows existing patterns
