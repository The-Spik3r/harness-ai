---
story: STORY-003
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-003-conversation-dedup-key-function.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: 2603805
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-003: dedup_key(user_id, turns): a pure, versioned key over a conversation, with single-turn as the empty-prefix case

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-003-conversation-dedup-key-function.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `2603805`

## Summary

`app/services/duplicate_checker.py` now exports `DedupTurn`, `DEDUP_KEY_VERSION = "v1"` and `dedup_key(user_id, turns)`, written exactly as PRD-009 Section 6.2 specifies. `DedupTurn` is a structural `typing.Protocol` with `role` and `content`. Two private helpers go with them: `_KEYED_ROLES` and `_sha256_json`.

The key is SHA-256 over canonical JSON (`ensure_ascii=False`, `separators=(",", ":")`) of `[version, user_id, hash_prompt(last.content), prefix_hash]`. For a single turn, `prefix_hash` is `""`. Otherwise it is `_sha256_json` over the prefix's `[role, content]` pairs, hashed with `hashlib` directly so it adds no `hash_prompt` call site.

`dedup_key` raises `ValueError` on:
- an empty sequence
- any role outside `system`/`user`/`assistant`; for `tool` the message names PRD-016
- a final turn that is not `user`

The function does no I/O and reads neither the clock nor settings. `check_duplicate` is byte-identical, and nothing in production calls `dedup_key` yet (STORY-006 will).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `DedupTurn`, `DEDUP_KEY_VERSION`, `_KEYED_ROLES`, `_sha256_json`, `dedup_key`, appended after `check_duplicate` | `app/services/duplicate_checker.py` | ✅ |
| 2 | Property, pinned-digest, ValueError, SimpleNamespace and purity tests | `tests/test_dedup_key.py` | ✅ |
| 3 | `hash_prompt` census: `duplicate_checker.py` 1 → 2, cited | `tests/test_pii_dedup_isolation.py` | ✅ |
| 4 | PRD-003 RF-6 source-unmodified guard narrowed to `pattern_detector.py`, cited | `tests/test_pii_dedup_isolation.py` | ✅ |
| 5 | Full suite | none edited | ✅ (see Validation) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Task 1 digest check (`0b206c74…3484652`) | ✅ matches the value computed independently at plan time |
| Frontend lint | n/a (no frontend change; no linter configured) |
| `tests/test_dedup_key.py` | ✅ 25 passed |
| `tests/test_pii_dedup_isolation.py` | ✅ 19 passed (was 2 failed / 18 passed after Task 1, before Tasks 3–4, as the plan predicted) |
| Full suite, run 1 (default Windows encoding) | 1897 passed, 25 skipped, 1 failed. The failure is pre-existing and environmental; see Notes. |
| Full suite, run 2 (`PYTHONUTF8=1`) | 1897 passed, 25 skipped, 1 error. The error was a one-off fixture error in `test_chat_state.py::test_history_off_reads_nothing_on_login`. That test passes alone, and its module passes in full (136 passed). This matches the libSQL dev server's known flakiness under repeated runs. |
| E2E | ✅ 5/5 |

Across the two runs, every test passed at least once, and neither issue involves a file this story touched.

### E2E checklist

- [x] `pytest tests/test_dedup_key.py -q`: 25 passed
- [x] `pytest tests/test_pii_dedup_isolation.py -q`: 19 passed. The census is 2, the RF-6 guard is green on `pattern_detector.py`, and the raw-text spy sequence is unchanged.
- [x] `pytest tests/test_query_outcomes_regression.py tests/test_duplicate_characterization.py -q`: 12 passed (`/query` behaviour unchanged)
- [x] `pytest tests/test_duplicate_checker.py tests/test_query_router.py -q`: 45 passed (`check_duplicate(prompt)` contract untouched)
- [x] `grep -rn "dedup_key(" app/` finds only `app/services/duplicate_checker.py:55: def dedup_key(`

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/duplicate_checker.py` | UPDATE | +31/-1 |
| `tests/test_dedup_key.py` | CREATE | +228 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +17/-3 |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-003-conversation-dedup-key-function.plan.md` | CREATE (archived) | +306 |

## Deviations from Plan

- **Test additions within Task 2's scope.** The multi-turn pinned digest is its own test (`test_key_for_a_fixed_multi_turn_input_is_pinned`), and the role/content-swap case is `test_role_and_content_swap_in_prefix_does_not_collide`. The unknown-role cases also include the empty string `""`. `test_exports_version_v1_and_the_specified_signature` additionally asserts that `DedupTurn` is a class. Every item the plan listed is present.
- **One three-line comment in `dedup_key`.** It explains why `user_id` is inside the key (defence in depth, Section 6.2), as Task 1 allowed. It avoids the text `hash_prompt(` and the words pii, redact and presidio.
- Otherwise the implementation matched the plan.

## PRD-009 Section 6.5 addendum (for review)

Section 6.5 lists six contract tests that PRD-009 deliberately invalidates. This story updated a seventh that the table does not list:

| Test | Pins | Update |
|---|---|---|
| `tests/test_pii_dedup_isolation.py::test_dedup_and_pattern_sources_unmodified_on_this_branch` | PRD-003 RF-6: `git diff merge-base(main)..worktree` is empty for `duplicate_checker.py` and `pattern_detector.py` | The `duplicate_checker.py` parameter is removed, and a comment cites PRD-009 Section 6.5. `pattern_detector.py` stays pinned by source. The RF-6 invariant (dedup never sees masked text) stays pinned behaviourally by `test_duplicate_checker_has_no_redaction_dependency`, the `hash_prompt` census and `test_hash_prompt_only_ever_receives_raw_text`. |

The test was not deleted. Leaving it as it was would have kept the suite red from STORY-003 through STORY-007. Consider adding this row to the PRD table.

## Notes for later stories

- **Pre-existing, environmental:** `tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` fails on this Windows machine under the default cp1252 locale. Its `git show` reader thread cannot decode `tests/reports_fixture.py` (byte `0x9d`), so `_git` returns `None`. It fails identically with this story's changes stashed, and passes under `PYTHONUTF8=1`. It is out of scope here. A fix would be `encoding="utf-8"` on that helper's `subprocess.run`, or running the suite with `PYTHONUTF8=1`.
- **Stale line-number comments (cosmetic, left as planned):** `tests/test_two_instance_smoke.py:91,709` cite `duplicate_checker.py:28`, which is now `:29` after the new import. `tests/test_query_router.py:193` cites `:32` and was already stale. STORY-007 rewrites `check_duplicate` and is the natural place to refresh both.
- **Enforced by tests:** the text `hash_prompt(` may appear only twice in `duplicate_checker.py`. The module source must not contain "pii", "redact" or "presidio" in any case, and that includes comments. Keep both in mind for STORY-006 and STORY-007.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_dedup_key.py` | exports/signature; same inputs → same key; pinned single-turn digest; pinned multi-turn digest; different user_id; single ≠ multi-turn with the same last turn; different prefixes differ; whitespace significant; delimiter injection; role/content swap; non-ASCII as UTF-8 (and ≠ ASCII-escaped); single-turn prefix `""` + last component = `hash_prompt`; multi-turn prefix = SHA-256 of role/content pairs; SimpleNamespace turns; tuple ≡ list; system turn keyed in prefix; empty refused; final assistant/system refused (×2); tool in prefix/final names PRD-016 (×2); unknown roles `function`/`User`/`""` refused (×3); purity (no storage, no clock, no settings) |
| `tests/test_pii_dedup_isolation.py` | census updated to 2 (cited); RF-6 source guard narrowed (cited) |

## Acceptance Criteria

- [x] `duplicate_checker.py` exports `DedupTurn` (Protocol with `role: str`, `content: str`), `DEDUP_KEY_VERSION = "v1"` and `dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str` per Section 6.2. It is pure.
- [x] `ValueError` on an empty sequence, a non-user final turn, or any `tool`/unknown role. The `tool` message names PRD-016.
- [x] Every F3 property has a test in `tests/test_dedup_key.py`, including a hard-coded digest, user_id sensitivity, prefix sensitivity, whitespace, delimiter injection and UTF-8 framing.
- [x] A single turn has prefix component `""`, and its last-turn component equals `hash_prompt(content)`.
- [x] The census is updated to `"app/services/duplicate_checker.py": 2`, with a PRD-009 Section 6.5 comment explaining why the site stays raw-text. No production caller exists. The full suite passes, apart from the environmental failure noted above.
- [x] All tasks completed
- [x] RF-6 guard narrowed with a citation and recorded above as a Section 6.5 addendum
- [x] Follows existing patterns
