---
id: STORY-014
prd: PRD-015
slug: stub-upstream
title: "Scripted stub upstream for E2E runs"
type: technical
priority: high
complexity: medium
phase: "4 - Real clients, deployment, documentation"
status: todo
labels: [tests, tooling, e2e]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-015, STORY-016, STORY-017, STORY-018]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-014: Scripted stub upstream for E2E runs

## Description

As the engineer running the client E2E stories, I want a local upstream that speaks enough Chat Completions to answer from a script, so that real clients can be driven end to end through a live harness on a machine where OpenRouter cannot be reached.

## Acceptance Criteria

- [ ] Given `python scripts/stub_openrouter.py --port 9100 --script <file>`, when the harness runs with `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`, then a `/v1` request is answered with the scripted content, `finish_reason` and `usage`, and the stub logs (ASCII only) each received request's model, message count and parameter keys.
- [ ] Given a script rule matching on the last user message (substring or regex), when a request matches, then its response is used; given no match, then a configurable default; rules can set `delay_seconds` and `fail_status` (e.g. 503, 400) instead of a body.
- [ ] Given the stub's own test, when it runs, then `call_openrouter` against the stub returns the scripted result, a `delay_seconds` rule exceeding `OPENROUTER_TIMEOUT_SECONDS` raises a retryable `OpenRouterError`, and a `fail_status: 400` raises a non-retryable one.
- [ ] Given the stub, when it receives an `Authorization` header, then it never logs the header's value.

## Technical Notes

- `scripts/stub_openrouter.py`: standard library only (`http.server` with `ThreadingHTTPServer`) or Starlette/uvicorn already in `requirements.txt`; no new dependency. Script format JSON (YAML would add nothing the repo needs).
- It is a test tool, not shipped behaviour (PRD Section 7.9). Docstring says so; nothing in `app/` imports it.
- Why it exists: outbound OpenRouter calls fail from the development machine (TLS / 401), so a live `/query` always returns 502; and the Aider story needs a model that answers with a specific edit.
- Scripts for later stories live under `tests/e2e/scripts/` (created here with one example).
- Tests: `tests/test_stub_openrouter.py`, starting the stub on an ephemeral port in a thread; no DB.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-015, STORY-016, STORY-017, STORY-018

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 7.9, 14 (Risk 7), 15 (D10)
