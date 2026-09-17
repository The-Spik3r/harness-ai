---
id: STORY-003
prd: PRD-009
slug: conversation-dedup-key-function
title: "dedup_key(user_id, turns): a pure, versioned key over a conversation, with single-turn as the empty-prefix case"
type: feature
priority: high
complexity: small
phase: "1 - Pin and prepare"
status: done
labels: [backend, security]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-003-conversation-dedup-key-function.plan.md
report: .agents/reports/PRD-009-duplicate-rescoping/STORY-003-conversation-dedup-key-function.report.md
commit: 2603805
depends_on: [STORY-001]
blocks: [STORY-006]
skills: []
created: 2026-09-16
updated: 2026-09-17
---

# STORY-003: dedup_key(user_id, turns): a pure, versioned key over a conversation, with single-turn as the empty-prefix case

## Description

As a PRD-010 implementer, I want one function that defines the duplicate key over a list of turns, so that multi-turn feeds it the real conversation and nobody writes a second definition of "duplicate".

## Acceptance Criteria

- [ ] Given [app/services/duplicate_checker.py](../../../app/services/duplicate_checker.py), when it is read, then it exports `DedupTurn` (a `typing.Protocol` with `role: str` and `content: str`), `DEDUP_KEY_VERSION = "v1"` and `dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str`, implemented as PRD Section 6.2 specifies. It is a pure function: no I/O, no clock, no settings.
- [ ] Given `dedup_key` with an empty sequence, a final turn whose role is not `user`, or any turn with role `tool` (or any role outside `system`/`user`/`assistant`), when it is called, then it raises `ValueError`, and the `tool` message names PRD-016.
- [ ] Given the key properties in PRD Section 7 F3, when `tests/test_dedup_key.py` runs, then each has a test:
  - the same inputs give the same key, including a hard-coded expected hex digest for one fixed input, so a framing change fails loudly
  - different `user_id` → different key
  - `[user(x)]` ≠ `[user(y), assistant(z), user(x)]`, and two different prefixes with the same last turn differ
  - `"hello world"` ≠ `"hello world "`
  - delimiter-injection pairs such as `[user("a\",\"b"), user("c")]` vs `[user("a"), user("b\",\"c")]` do not collide
  - non-ASCII content hashes as UTF-8 (`ensure_ascii=False`)
- [ ] Given a single-turn conversation, when the key is derived, then its prefix component is the empty string `""`, and its last-turn component equals `hash_prompt(content)`, the value `prompt_hash` stores.
- [ ] Given `test_hash_prompt_call_sites_are_exactly_the_three_audited_ones` in [tests/test_pii_dedup_isolation.py](../../../tests/test_pii_dedup_isolation.py), when the new call site is added, then the census is updated to `"app/services/duplicate_checker.py": 2`, with a comment citing PRD-009 Section 6.5 and stating why the new site still only receives raw text. No production caller uses `dedup_key` yet, and the full suite passes.

## Technical Notes

- Canonical JSON framing: `json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")` → `hashlib.sha256(...).hexdigest()`, in a private `_sha256_json`. Hash the prefix directly with `hashlib`, not with `hash_prompt`, so the census stays one new call site (the last turn).
- Test turns can be a local frozen dataclass. The Protocol is structural, which is the point: PRD-010's message model must satisfy it without importing it.
- Add one test that uses `SimpleNamespace(role=..., content=...)`, proving any object with the two attributes works.
- `user_id` goes *inside* the hashed array (defence in depth, PRD Section 6.2). Don't "optimize" it out because the lookup also filters by column.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Key function), 5 (story 5), 6.2, 6.5, 7 (F3), 11
