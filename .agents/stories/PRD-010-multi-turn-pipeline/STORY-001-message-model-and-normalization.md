---
id: STORY-001
prd: PRD-010
slug: message-model-and-normalization
title: "Message model, Role type and OpenAI content normalization"
type: feature
priority: high
complexity: medium
phase: "1 - Model, settings, client"
status: done
labels: [backend, models]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-001-message-model-and-normalization.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-001-message-model-and-normalization.report.md
commit: a41155f
depends_on: []
blocks: [STORY-004, STORY-007, STORY-011]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-001: Message model, Role type and OpenAI content normalization

## Description

As a PRD-011/012/014 implementer, I want one internal `Message(role, content: str)` and one normalizer for OpenAI message shapes, so that nothing past the edge ever handles a content-part list or a `None`.

## Acceptance Criteria

- [ ] Given the new [app/models/messages.py](../../../app/models/messages.py), when it is imported, then it exports `Role = Literal["system", "user", "assistant", "tool"]`, a `@dataclass(frozen=True) Message(role: Role, content: str)`, `MessageNormalizationError`, `normalize_message(raw: Mapping[str, Any]) -> Message` and `normalize_messages(raw: Sequence[Mapping[str, Any]]) -> list[Message]`.
- [ ] Given each row of PRD Section 6.2's table, when it is passed to `normalize_message`, then the result matches the table. `"text"` → `"text"`. Two text parts `a`, `b` → `"a\nb"`. An `image_url` part raises. `null` on `assistant` → `""`. `null` on `user`/`system`/`tool` raises. A `tool_calls` key raises. An unknown role such as `"developer"` raises. There is one parametrized test per row in `tests/test_messages.py`.
- [ ] Given `normalize_messages` with an invalid element at index 3, when it raises `MessageNormalizationError`, then the message names the index (`messages[3]`) and the rule that failed, and never echoes the content.
- [ ] Given a `list[Message]` ending in a user turn, when it is passed to `dedup_key(user_id, messages)` from [app/services/duplicate_checker.py](../../../app/services/duplicate_checker.py), then it returns the same key as the equivalent private `_UserTurn` list does today. This proves `Message` structurally satisfies `DedupTurn` with no import in either direction.
- [ ] Given the full test suite, when this story lands, then it is green with **no production caller changed**. `messages.py` is imported only by its tests.

## Technical Notes

- Pure module: no I/O, no `settings`, no pydantic. A frozen dataclass mirrors `_UserTurn` in [app/services/query_pipeline.py](../../../app/services/query_pipeline.py), which STORY-007 deletes in favour of this type.
- `tool` is a valid `Role` on purpose (PRD 6.2). The pipeline refuses it structurally in STORY-007, and PRD-016 lifts that. Do not refuse `tool` in the normalizer; a `tool` message with string content normalizes fine.
- Part joining with `\n` is deliberate: it keeps part boundaries visible to pattern detection. Put that reason in a comment.
- A part is `{"type": "text", "text": str}`. A text part missing `text`, or with a non-str `text`, raises. Non-mapping input raises.
- Do not validate structure across messages here (non-empty, last is user). That belongs to the pipeline (STORY-007), because PRD-014 may want to accept a conversation ending in an assistant prefill later.
- The normalizer has no production HTTP caller in this PRD (PRD 6.2). It ships now because it is the contract PRD-011/012/013 design against.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004, STORY-007, STORY-011

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (Message model), 6.2, 7 (F1), 10, 11
