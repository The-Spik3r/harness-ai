---
id: STORY-001
prd: PRD-015
slug: query-error-body-characterization
title: "Characterize /query's error bodies and the upstream request body before /v1 exists"
type: technical
priority: high
complexity: small
phase: "1 - Foundations"
status: in-progress
labels: [backend, tests, characterization]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: .agents/plans/PRD-015-openai-compatible-endpoint/STORY-001-query-error-body-characterization.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-002, STORY-006, STORY-010]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-001: Characterize /query's error bodies and the upstream request body before /v1 exists

## Description

As a maintainer, I want `/query`'s error responses and the exact body sent upstream pinned on untouched code, so that the `/v1` exception handlers and the parameter work later in this epic provably change neither.

## Acceptance Criteria

- [ ] Given untouched `main`, when `tests/test_v1_query_isolation.py` runs, then it pins the full status and JSON body of `POST /query` for: no bearer (401), invalid bearer (401), identity without `query:submit` (403), a body failing validation (422: missing `prompt`, and a malformed `session_id`), `DuplicateCheckError` (500), `PiiRedactorError` (500) and `OpenRouterError` (502), and it passes.
- [ ] Given a `/query` success and a `run_conversation` call with all four `GenerationParams` set, when the upstream request is captured with an `httpx.MockTransport`, then the test pins the URL (`https://openrouter.ai/api/v1/chat/completions`) and that the JSON body's keys are exactly `model`, `messages` and the set parameters.
- [ ] Given the new tests, when the whole suite runs, then no existing assertion is changed and the new tests are green without any production change.
- [ ] Given `-m "not db"`, when it runs, then the tests that need no storage still run without Docker, and the ones that do carry the `db` marker.

## Technical Notes

- Bodies are compared as whole dicts, not field by field: the point is that a handler registered later cannot add, rename or reshape anything. The 422 body is FastAPI's `{"detail": [...]}`; pin it as returned today, including `loc` and `type`.
- PRD Section 6.3 / Risk 4: STORY-010 registers app-wide handlers that must delegate outside `/v1/`. This file is what they are checked against; STORY-010 adds the `/v1` half, so the module is named for both halves now.
- The upstream-body assertion is the PRD Section 9.2 T5 baseline ("no key outside `model`, `messages` and the four fields"). PRD-010 STORY-003 characterized the payload already (`tests/test_openrouter_client.py` and `tests/test_audit_characterization.py` each define `_API_URL`); reuse that helper rather than writing a third.
- Use the `temp_db` fixture and the `call_openrouter` monkeypatch pattern from `tests/test_query_router.py`.
- ASCII-only test output (cp1252 console).
- Skills: none applicable. No UI surface.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-006, STORY-010

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 6.3, 7.5 (isolation), 9.2 (T5), 11 (Quality indicators), 14 (Risk 4)
