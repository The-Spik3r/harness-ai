---
id: STORY-008
prd: PRD-022
slug: anthropic-primary-end-to-end
title: Anthropic as a primary through the pipeline — dropped params, cache tokens on the row, /v1 tool loop
type: feature
priority: high
complexity: medium
phase: "2 - Anthropic native adapter"
status: todo
labels: [backend, pipeline, v1, anthropic]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-003, STORY-007]
blocks: [STORY-017]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-008: Anthropic as a primary through the pipeline

## Description

As an operator, I want a catalogue model on a `type: anthropic` provider to work as an ordinary primary on `/query`, `/v1` (buffered and real-time) and the chat UI, so that Phase 2 is usable before any chain exists.

## Acceptance Criteria

- [ ] Given a `/v1` tool-calling conversation routed to an anthropic catalogue model (stub in Messages mode), when it runs a full tool loop (call → tool result → answer), then the client sees OpenAI-shaped `tool_calls` with canonical `arguments`, the action policy (`evaluate_all`, step 7c) decides them exactly as for OpenRouter, and PRD-017's tool-loop assertions pass
- [ ] Given a request with `temperature` to a model without `sampling_params`, when answered, then the success row's `ignored_params` includes `temperature@<provider name>` alongside whatever the `/v1` edge already recorded
- [ ] Given an Anthropic answer with cache usage, when the success row is written, then `cache_read_tokens` / `cache_write_tokens` are set, prompt tokens include both, and `charge()` receives the full prompt total (spy)
- [ ] Given a refusal (`stop_reason: refusal`), when answered, then `/v1` returns `finish_reason: "content_filter"`, one row `success=1`, `attempt=1`
- [ ] Given a realtime-streamed `/v1` request to an anthropic model with `reasoning` on and a caller holding `reasoning:view`, when streamed, then reasoning reaches the client through PRD-021's gates; without the grant it does not; the row's `reasoning_shown` matches

## Technical Notes

- Pipeline step 7: `app/services/query_pipeline.py:1001-1206`; `ignored_params` flows from the `/v1` edge (`v1_translate.py`) into `run_conversation`; append the adapter's dropped names for the success row only.
- Write the tests as integration tests against the stub (see existing PRD-017/PRD-020 `/v1` stub tests for the harness fixture), not against the real API.
- No chain here: `attempt=1` always.

## Dependencies

- **Blocked by**: STORY-003, STORY-007
- **Blocks**: STORY-017

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.5, 6.6, Phase 2 validation, User story 3 and 5
