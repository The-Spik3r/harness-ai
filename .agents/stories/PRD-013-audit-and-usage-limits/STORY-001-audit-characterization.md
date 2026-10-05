---
id: STORY-001
prd: PRD-013
slug: audit-characterization
title: "Characterize today's audit row per arm and the client's usage parsing"
type: technical
priority: high
complexity: small
phase: "1 - The row"
status: todo
labels: [backend, audit, tests]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-002, STORY-003, STORY-005]
skills: []
created: 2026-10-04
updated: 2026-10-04
---

# STORY-001: Characterize today's audit row per arm and the client's usage parsing

## Description

As the PRD-013 implementer, I want today's audit row on every pipeline arm and today's `usage` parsing pinned by tests, so that the stories that add fields can show they removed or changed none.

## Acceptance Criteria

- [ ] Given untouched code on `main`, when `tests/test_audit_characterization.py` runs, then it is green and asserts the full `AuditLog` row written by each arm of `run_conversation`: the three authorization arms, context limit, duplicate, pattern block, pattern flag, redaction limit, input-redaction error, upstream error, output-redaction error and success.
- [ ] Given a three-message conversation, when the success arm writes its row, then the test asserts `prompt_hash == hash_prompt(messages[-1].content)` and `prompt_preview` is the first 500 characters of the last user turn, not of the system turn.
- [ ] Given two conversations that differ only in an earlier turn, when both are run, then the test asserts their rows carry different `dedup_key` values and the same `prompt_hash`.
- [ ] Given a stub HTTP client returning `usage` with `total_tokens`, `prompt_tokens` and `completion_tokens`, and one returning only `total_tokens`, when `call_openrouter` runs, then the test pins that `tokens_used` equals `total_tokens` in both cases and that a missing `total_tokens` raises `OpenRouterError`.
- [ ] Given the story's diff, when it is reviewed, then it contains test files only and no file under `app/` or `chat_ui/` changed.

## Technical Notes

- This is the PRD-009 STORY-001 / PRD-012 STORY-002 pattern: green on untouched code first. Later stories may add assertions for new fields and may not change or delete one written here.
- Assert rows by reading them back through `get_audit_log` on the `temp_db` fixture, not by spying on `log_query`, so the writer and the mapper are both covered.
- The second and third criteria are PRD Section 6.4's correction to the brief: the preview and the full-conversation hash already exist. This story is where they are pinned.
- `tests/test_pii_characterization.py` and `tests/test_query_pipeline_pii_profiles.py` show how the arms are forced (stub `call_openrouter`, patched `redact`).
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-003, STORY-005

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.4, 7 (F1), 11 (Quality indicators), 12 (Phase 1)
