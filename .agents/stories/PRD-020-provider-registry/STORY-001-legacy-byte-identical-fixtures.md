---
id: STORY-001
prd: PRD-020
slug: legacy-byte-identical-fixtures
title: Record the legacy byte-identical fixtures before any refactor
type: technical
priority: high
complexity: medium
phase: "1 - Registry and legacy equivalence"
status: done
labels: [testing, backend]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-001-legacy-byte-identical-fixtures.plan.md
report: .agents/reports/PRD-020-provider-registry/STORY-001-legacy-byte-identical-fixtures.report.md
commit: 130bbee
depends_on: []
blocks: [STORY-005]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-001: Record the legacy byte-identical fixtures before any refactor

## Description

As a maintainer of the harness, I want the upstream payload, headers, error strings, `/v1/models` bodies and `/query` verdicts recorded as fixtures against the unchanged code, so that every later PRD-020 story can prove legacy mode is still today byte for byte.

## Acceptance Criteria

- [ ] Given the unchanged `call_openrouter` and a capturing fake transport, when a text request and a tool request are sent, then `tests/fixtures/prd020_legacy/` holds the exact upstream JSON payload and the relevant headers (`Authorization: Bearer <test key>`, `Content-Type`, path `/chat/completions`) for each, and a test replays the request and asserts equality with the recorded files.
- [ ] Given the stub or a fake transport answering 503, 429, a malformed body, a body without `usage`, and no configured key, when `call_openrouter` is called, then the recorded `OpenRouterError` string, `upstream_status` and `retryable` for each case are asserted against fixtures.
- [ ] Given the default `MODEL_ALLOWLIST`, when `GET /v1/models` and `GET /v1/models/{id}` are called as admin and as user, then the four response bodies equal the recorded fixtures byte for byte.
- [ ] Given `/query` with an allowed model, a not-allowed model and a BYOK key without `query:byok`, when each is sent, then the success body and the `query:model:<m>` and `query:byok` blocked bodies equal the recorded fixtures.
- [ ] Given the fixtures, when volatile fields (ids, timestamps, `created`, audit ids) are normalized, then the normalization is documented in a `README.md` beside the fixtures, `git diff main -- app/` is empty for this story, and the README states that later stories must keep the suite green without editing a fixture.

## Technical Notes

- Record against unchanged code, as the first commit of the epic: no `app/` change is allowed in this story. A later story that needs a fixture edited has found a legacy regression, not a stale fixture.
- The payload is built at `app/services/openrouter_client.py:240-263` (headers `:241-244`, params `:252-258`, tools `:259-263`); the URL is read per call at `:268`; error strings at `:272-278` (`OpenRouter request failed: ...`), `:283-288` (unexpected shape), `:302` (no text content) and `:311-316` (missing `usage`); the missing-key message is at `:235-239`.
- `GET /v1/models` and `GET /v1/models/{id}` are at `app/routers/v1.py:448-458` and `:461-475`; `owned_by` comes from `_model_entry` at `:420-423`. `/query` verdicts: `authorize_model` arm `app/services/query_pipeline.py:404-413`, BYOK arm `:415-423`.
- Existing patterns to reuse: `tests/test_openrouter_client.py` and `tests/test_stub_openrouter.py` (the stub runs in a thread on an ephemeral port and `settings.OPENROUTER_BASE_URL` is monkeypatched); `tests/conftest.py:92` sets `OPENROUTER_API_KEY=test-key`. Normalize ids/timestamps by regex before comparing; keep the key a fixed test value so the Bearer header is recordable.
- Fixtures are plain `.json` / `.txt` files under `tests/fixtures/prd020_legacy/`; the replay test lives in `tests/test_prd020_legacy_fixtures.py`. The test must run in the default (non-`--run-e2e`) suite.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4, 6.2, 11, 12 Phase 1; decisions D1; risk 1
