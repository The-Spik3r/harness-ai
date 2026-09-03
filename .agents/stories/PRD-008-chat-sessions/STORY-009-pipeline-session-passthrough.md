---
id: STORY-009
prd: PRD-008
slug: pipeline-session-passthrough
title: "run_query threads session_id to all seven log_query call sites, blocked and failed included"
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline and API"
status: todo
labels: [backend, pipeline, audit]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-008]
blocks: [STORY-010, STORY-013]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-009: run_query threads session_id to all seven log_query call sites, blocked and failed included

## Description

As a compliance admin, I want the conversation named on **every** audit row a send can produce, so that the rows missing from a session's history are not exactly the interesting ones — the blocked, the denied and the failed.

## Acceptance Criteria

- [ ] Given [app/services/query_pipeline.py](../../../app/services/query_pipeline.py), when `run_query` is read, then it accepts `session_id: Optional[str] = None`.
- [ ] Given the module, when `grep -n "log_query(" app/services/query_pipeline.py` is run, then it reports **seven** call sites and every one of them passes `session_id`. Six are in `run_query`; the seventh is in `_deny`, which serves the three authorization arms.
- [ ] Given a duplicate-blocked send, when the audit row is read, then it carries the `session_id` — the case that matters most, because a held turn is the one a user will ask about.
- [ ] Given a pattern-blocked send, a permission-denied send, a model-not-permitted send and a BYOK-denied send, when each audit row is read, then all four carry the `session_id`.
- [ ] Given a `PiiRedactorError` on the input side, a `PiiRedactorError` on the output side and an `OpenRouterError`, when each failure row is written, then all three carry the `session_id`.
- [ ] Given a successful send, when the row is read, then it carries the `session_id` alongside the `audit_id` the UI already shows in its footer.
- [ ] Given `run_query(...)` called without `session_id`, when the row is written, then it is `NULL` and every other field is identical to the current release — asserted against [tests/test_query_pipeline_authorization.py](../../../tests/test_query_pipeline_authorization.py) and [tests/test_integration.py](../../../tests/test_integration.py) passing unmodified.
- [ ] Given `_deny`, when its signature is read, then it takes `session_id` explicitly rather than closing over it — the helper is called from three arms and a captured variable is how one of them silently stops passing it.

## Technical Notes

- File: [app/services/query_pipeline.py](../../../app/services/query_pipeline.py) only. `call_openrouter` is not touched, and its `prompt: str` signature is not touched.
- The seven call sites, for the plan's checklist: `_deny` (line ~34), duplicate-blocked (~72), pattern-blocked (~86), input `PiiRedactorError` (~101), `OpenRouterError` (~115), output `PiiRedactorError` (~128), success (~144).
- **Write the test per arm, not per function.** Seven call sites and one forgotten `session_id=` is the defect this story is most likely to ship, and it is invisible in the success path — which is the path everyone tests first.
- PRD Section 4 states the requirement as a scope item: "passes it through to `log_query(...)` on **every** logging path — including the three denial arms and the three failure arms."
- This story does not validate the id and does not check ownership. `run_query` receives whatever it is given; the 403 lives at the router boundary and is [[STORY-010]]. Keeping validation out of the pipeline keeps the in-process caller ([chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py)) and the HTTP caller on the same code path, which is what PRD-002 established when `ChatState` began calling `run_query(...)` directly.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: STORY-010, STORY-013

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Pipeline & API), Section 6 (send path), Section 11, Section 12 Phase 2
