---
id: STORY-006
prd: PRD-022
slug: stub-anthropic-mode-and-faults
title: Stub upstream — Anthropic Messages mode (JSON + SSE) and scripted faults
type: technical
priority: high
complexity: medium
phase: "2 - Anthropic native adapter"
status: in-progress
labels: [testing, stub, e2e]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/STORY-006-stub-anthropic-mode-and-faults.plan.md
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-007]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-006: Stub upstream — Anthropic Messages mode and scripted faults

## Description

As a test author, I want the stub upstream to speak the Anthropic Messages API and to fail on command, so that the adapter, the chain and the breaker are tested end to end without a real provider.

## Acceptance Criteria

- [ ] Given the stub, when it receives `POST /v1/messages` (with `x-api-key` and `anthropic-version` headers), then it answers a Messages JSON body built from the same script rules (text, tool calls as `tool_use` blocks, usage incl. `cache_creation_input_tokens`/`cache_read_input_tokens`, `stop_reason`); `"stream": true` answers the Messages SSE event sequence STORY-001 recorded (`message_start`, `content_block_start/delta/stop` with `text_delta` / `input_json_delta` / `thinking_delta`, `message_delta`, `message_stop`)
- [ ] Given a script rule, when it declares a fault, then the stub produces it on either endpoint: `timeout` (holds the response past the client timeout), `status: 503`, `status: 429` with `retry_after`, `status: 401`, `status: 400`, a malformed body, and an Anthropic `stop_reason: refusal`; Chat Completions faults keep their existing shapes
- [ ] Given a script rule with a hit count (existing matcher), when faults are scripted for the first N hits only, then hit N+1 answers normally (needed for breaker probes); the per-endpoint hit counter is readable by tests
- [ ] Given the existing stub tests, when run, then they pass unchanged; new tests in `tests/test_stub_openrouter.py` (or a sibling) cover the Messages mode and each fault, and the stub still never logs prompt text

## Technical Notes

- `scripts/stub_openrouter.py` (770 lines): `Request.from_body` `:168`, `Rule.matches` `:227`, `_parse_reply` `:353`, `_send_sse` `:522`, `do_POST` `:618`, `make_server` `:709`. Reuse the script format; add fields rather than a second script language. Check which faults (status replies, redirects `:510`) already exist before adding.
- The script schema is validated (`parse_script` `:442`): new keys go through the same validation with errors naming the rule index.
- The SSE event names come from STORY-001's report; the property test in STORY-007 replays every script through both `complete()` and `stream()`.
- Orchestrator decision (STORY-001 findings): the SDK sends `Authorization: Bearer <key>` and `anthropic-version`; the stub's Messages mode must accept the Bearer header (it may accept `x-api-key` too). Use the SSE event names recorded in the STORY-001 report.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 4 (Stub and E2E), F11
