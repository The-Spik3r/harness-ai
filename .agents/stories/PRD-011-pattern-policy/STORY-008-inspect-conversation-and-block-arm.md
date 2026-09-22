---
id: STORY-008
prd: PRD-011
slug: inspect-conversation-and-block-arm
title: "inspect() over the conversation; _inspection_target deleted; block arm"
type: feature
priority: high
complexity: large
phase: "3 - The pipeline inspects the conversation"
status: todo
labels: [backend, api, security]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-006]
blocks: [STORY-009, STORY-011]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-008: inspect() over the conversation; _inspection_target deleted; block arm

## Description

As a security admin, I want pattern inspection to run over the whole conversation under the profile's role matrix, so that the provisional "last user turn only" policy is replaced by one that is written down and configurable.

## Acceptance Criteria

- [ ] Given `inspect(messages, profile)` in [app/services/pattern_detector.py](../../../app/services/pattern_detector.py), when it runs, then it walks messages in order, skips any message whose role is absent from the profile's map, walks that profile's lists in declared order and their patterns in declared order, and returns `PatternInspectionResult(block, flags, truncated)`. A `block` action short-circuits the walk; `flag` actions accumulate.
- [ ] Given a conversation with a `tool` flag before a `user` block under the `code` profile, when inspected, then `result.block` is the user hit; given the same conversation under `chat`, then nothing is reported, because `chat` inspects `user` only.
- [ ] Given [app/services/query_pipeline.py](../../../app/services/query_pipeline.py), when it is read, then `_inspection_target` is gone, step 5 calls `inspect(messages, get_profile(profile or settings.PATTERN_PROFILE_DEFAULT))`, and `run_conversation` takes a new trailing keyword `profile: Optional[str] = None`. `run_query`'s signature is unchanged and passes nothing.
- [ ] Given a blocking hit, when the request is refused, then the response is byte-identical to today's — `{"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": ...}` with no role field — the audit row carries `suspicious_pattern`, `success=True`, an explicit `session_id` and a non-NULL `dedup_key`, and `call_openrouter` is never called. `pattern_role` and `pattern_action` land in STORY-009.
- [ ] Given STORY-001's characterization flip set, when the corresponding cases run under the default policy, then exactly those verdicts have flipped and no others; `detect_suspicious_pattern` and `SUSPICIOUS_PATTERNS` are removed, `tests/test_pattern_detector.py` is rewritten around `inspect`, a repository-wide grep for both names returns nothing outside this epic's documentation, and [tests/test_query_outcomes_regression.py](../../../tests/test_query_outcomes_regression.py) passes with no assertion modified.

## Technical Notes

- Step 5 keeps its position exactly: after all three authorization arms and after `check_duplicate`, before redaction (PRD Section 6.1). Inspection runs on **raw** text — redacting first would mean matching against `<PHONE_NUMBER>` instead of what the attacker wrote.
- `run_conversation` gains one keyword-only argument at the end; every existing caller (`run_query`, `ChatState`) passes nothing and gets `PATTERN_PROFILE_DEFAULT`. Do not add a `profile` field to any request schema — the existing unknown-field schema test is what keeps the permissive profile unreachable from a request body (PRD 9.2 T1), so add an assertion there naming this PRD.
- Strip code spans at most twice per message (raw and stripped), not per pattern — reuse STORY-003's helper and cache per message inside the walk (PRD Risk 8).
- `PATTERN_MAX_SCAN_CHARACTERS`: a message longer than the ceiling is truncated for matching only, `result.truncated` is set, and the pipeline emits a `WARNING` naming the user id, the message index and both lengths — never the content. No audit column is added for it (PRD 9.2 T9).
- Removing `detect_suspicious_pattern` outright rather than shimming it is the PRD's decision (Section 10). The grep is part of acceptance because the risk register calls out a caller nobody looked for (PRD Risk 6).
- New tests in `tests/test_query_pipeline_patterns.py` (block arm, check order via spies, profile passthrough) and the rewritten `tests/test_pattern_detector.py` (walk order, short-circuit, role skipping). Preserve the list-order precedence case STORY-001 restated.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-006
- **Blocks**: STORY-009, STORY-011

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 4 (Pipeline), 6.1, 6.4, 6.6, 7 (F5, F6), 9.2 (T1, T9), 10, 11
