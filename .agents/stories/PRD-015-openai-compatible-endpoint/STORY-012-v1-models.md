---
id: STORY-012
prd: PRD-015
slug: v1-models
title: "GET /v1/models and /v1/models/{id} from MODEL_ALLOWLIST"
type: feature
priority: medium
complexity: small
phase: "2 - Non-streaming endpoint"
status: todo
labels: [backend, api]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-004, STORY-009, STORY-010]
blocks: [STORY-015]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-012: GET /v1/models and /v1/models/{id} from MODEL_ALLOWLIST

## Description

As an integrating developer, I want my client to discover the models I may use, so that its model picker shows only names the harness will accept.

## Acceptance Criteria

- [ ] Given a `user`-role token and the default `MODEL_ALLOWLIST`, when `GET /v1/models` is sent, then 200 with `object: "list"` and one entry per allowlisted model in configured order, each `{"id", "object": "model", "created": 0, "owned_by"}` with `owned_by` the prefix before `/` or `harness`.
- [ ] Given an `admin`-role user token, when the list is requested, then it returns the same entries (the wildcard cannot be enumerated; documented in STORY-019).
- [ ] Given `GET /v1/models/openai%2Fgpt-4o` (and the unencoded `/v1/models/openai/gpt-4o`), when sent, then 200 with that entry; given a name not in the list, then 404 `model_not_found` with `x-should-retry: false`.
- [ ] Given `ADMIN_TOKEN`, no bearer, or an identity without `query:submit`, when either route is called, then 403 `break_glass_not_permitted`, 401 `invalid_api_key` or 403 `permission_denied` respectively, in the error shape; no route writes an audit row.

## Technical Notes

- In `app/routers/v1.py`. Break-glass refusal is router-level here because no pipeline runs (PRD Section 7.2): check `identity.break_glass`, which only `resolve(ADMIN_TOKEN)` sets.
- Model ids contain `/`; use a `{model_id:path}` path parameter.
- Read `settings.model_allowlist_list` per request (tests monkeypatch it).
- `/v1/models` is not audited (PRD Section 7.7): it reveals only configuration the caller is already held to.
- Tests: `tests/test_v1_models.py`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-004, STORY-009, STORY-010
- **Blocks**: STORY-015

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 7.2, 7.7, 10, 15 (D4)
