---
id: STORY-008
prd: PRD-012
slug: redact-for-policy
title: "redact_for_policy: fence skipping, structure-safe replacement, JSON-aware mode"
type: feature
priority: high
complexity: large
phase: "2 - Primitives"
status: todo
labels: [backend, pii, security]
epic_branch: epic/PRD-012-pii-for-code
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-004, STORY-006, STORY-007]
blocks: [STORY-009, STORY-013]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-008: redact_for_policy: fence skipping, structure-safe replacement, JSON-aware mode

## Description

As an integrating developer, I want redaction under `code` to mask PII in prose without ever breaking a quote, a line, or a JSON document, so that the model reads my code and tool results as valid structure.

## Acceptance Criteria

- [ ] Given `redact_for_policy(text, code_policy)`, when `text` has an email inside a ```` ``` ```` or `~~~` fence and another in prose, then the fenced one is unchanged and the prose one becomes `<EMAIL_ADDRESS>`; an email inside an inline backtick span **is** masked; an unterminated fence skips to end of text.
- [ ] Given a structure-safe policy, when a span covers `"jane@example.com"` including its quotes, or contains a backslash, a backtick or a line break, then every quote, backslash, backtick and line break stays in place, the span is split around them, and runs without an alphanumeric character are left alone (`O'Brien` masks as `<PERSON>'<PERSON>` when `PERSON` is enabled).
- [ ] Given content that is a JSON object or array, when PII sits in a string value or key, then it is replaced inside the quotes; when PII is a number token (`"phone": 4155550134`), then the whole token becomes `"<PHONE_NUMBER>"`; spans over punctuation, `true`/`false`/`null` or whitespace are dropped; and `json.loads(result)` succeeds for every file in `tests/corpora/pii/json/`.
- [ ] Given a stub analyzer that returns a span which would make the result unparseable, when JSON-aware mode runs, then `PiiRedactorError("redaction would produce invalid JSON")` is raised.
- [ ] Given `redact_for_policy(text, chat_policy)`, when it runs, then the result is identical to `redact(text)`, and `redact()` itself is unchanged (characterization green).

## Technical Notes

- Pipeline: blank fences with `strip_fenced_blocks` → analyze the blanked text with `_get_analyzer(policy.entities)` at `policy.threshold` → post-process spans (structure-safe split, JSON clipping) → replace in the **original** text → post-condition. Blanking preserves length, so analyzer offsets index the original (PRD Section 6.5).
- Do the `code` replacement with your own span replacement, not `AnonymizerEngine`. Resolve overlapping spans deterministically (longest first, then earliest start) and document the rule.
- JSON detection: stripped content starts with `{` or `[` **and** `json.loads` accepts it. Locate string and number tokens by offset with a small scanner (PRD Section 8). Do not reserialize, because formatting must survive.
- Returns `RedactionResult(text, entities)` with entities sorted, as `redact()` does. Put the tool-call-argument contract in the docstring, verbatim from PRD Section 6.6: arguments are never passed here, only `content`.
- Tests: `tests/test_pii_structure_safe.py`. Use the corpus from STORY-001 for the JSON cases.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-006, STORY-007
- **Blocks**: STORY-009, STORY-013

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 6.5 (D2), 6.6, 7 (F7), 9.2 (T6), 11 (Functional requirements), 14 (Risks 4, 5)
