---
story: STORY-014
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-014-chat-usage-limit-bubble.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 59e9fdc
status: COMPLETE
completed: 2026-10-19
---

# Implementation Report: STORY-014, Chat UI usage-limit bubble

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-014-chat-usage-limit-bubble.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `59e9fdc`

## Summary

A send refused by the usage gate now shows a `usage_limit` bubble. It replaces STORY-011's interim arm, which routed the refusal through the internal-error bubble.

- **Dispatcher and drawing.** The bubble is one more `rx.match` arm in `components/chat.py`. `render_usage_limit` draws it the way `render_context_limit` draws its bubble: the `INK_HELD`/`TINT_HELD` pair, a `PAUSED` tag, one sentence and no Retry action.
- **The sentence.** `formatting.format_usage_limit_notice(limit, resets_at)` builds it when the bubble is built, formatting `resets_at` in UTC. The full sentence is stored in the existing `detail` column, and `content` keeps the pipeline's reason.
- **Persistence.** The mappers and `_append_and_persist` already treat every kind alike, so they needed no change. Tests prove the round trip.
- **History.** History exclusion already worked, because `assemble` reads only `assistant` rows. A real-pipeline test proves it from outside.
- **Counter failures.** `UsageLimitError` keeps its existing internal-error route.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Copy: `TAG_USAGE_LIMIT`, the two sentences, `USAGE_LIMIT_NOTICES` | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | `format_usage_limit_notice` | `chat_ui/chat_ui/formatting.py` | ✅ |
| 3 | Replace the interim arm with `kind="usage_limit"`; catch-all comment | `chat_ui/chat_ui/state.py` | ✅ |
| 4 | `render_usage_limit` | `chat_ui/chat_ui/components/bubbles.py` | ✅ |
| 5 | Import and `rx.match` arm above the default; probe lists | `chat_ui/chat_ui/components/chat.py`, `tests/test_chat_components_import.py` | ✅ |
| 6 | Appended copy tests | `tests/test_copy.py` | ✅ |
| 7 | Interim pin replaced; both round-trip parametrizations extended | `tests/test_chat_state.py` | ✅ |
| 8 | Story test file, ACs 1–5 | `tests/test_usage_bubble.py` | ✅ |
| 9 | D4 docstring, `UNANSWERED_KINDS`, `detail` comment | `app/services/chat_history.py`, `tests/test_chat_history.py`, `chat_ui/chat_ui/models.py` | ✅ |
| 10 | Full regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no Node frontend; the Reflex probe in `test_chat_components_import.py` compiles every renderer against a Var) ✅ |
| Baseline of the affected suites before the change | ✅ 287 passed |
| Full suite | ✅ 3707 passed, 27 skipped, 0 failed (296 s) |
| Census guards (`tests/test_untouched_app.py`) | ✅ |
| App builds and serves (`reflex run --env prod`) | ✅ `App running at: http://0.0.0.0:3000/` |
| E2E | ✅ 5/5 |

## End-to-End Checks

All checks ran in a real browser (Chrome DevTools MCP) against `reflex run --env prod` on the dev libSQL container, signed in as a throwaway user `e2e-story014`, which was deactivated afterwards.

| # | Check | Result |
|---|-------|--------|
| 1 | `USAGE_REQUESTS_PER_MINUTE=*=1`, two sends inside a minute. The first is admitted (it reaches upstream, and the TLS failure shows the UPSTREAM bubble). The second shows **one** `PAUSED` bubble reading "You're sending too fast. Wait a minute, then send again.". The bubble has 0 buttons and its tag ink is `#DCB44A` (dark INK_HELD) | ✅ `docs/screenshots/chat-usage-limit.png` |
| 2 | Sign out, sign in. The chat is read back from the database and the same bubble returns with identical text. The restored entry has no `hx-entry` class, so it does not animate | ✅ |
| 3 | `USAGE_DAILY_TOKEN_BUDGET=*=1` with 312 tokens already used today. The send shows "You've reached today's usage limit. You can send again after 00:00 UTC.", and it is restored identically after sign-out/sign-in | ✅ `docs/screenshots/chat-usage-limit-budget-light.png` |
| 4 | After the minute rolled over, a third send was admitted. Its audit row has `message_count=1`, so the refused turn was not resent. The refusal row has `ingress=chat`, `limit_exceeded=requests`, `success=True` (PRD 6.7) | ✅ |
| 5 | Light ground: tag `#7C5E11` on panel `#FAF6EA` (light INK_HELD/TINT_HELD), body text `#14181C`. Readable in both themes | ✅ `docs/screenshots/chat-usage-limit-light.png` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | UPDATE | +28 |
| `chat_ui/chat_ui/formatting.py` | UPDATE | +36 |
| `chat_ui/chat_ui/state.py` | UPDATE | +21/-11 |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | +31 |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | +7/-1 |
| `chat_ui/chat_ui/models.py` | UPDATE | +3 |
| `app/services/chat_history.py` | UPDATE | +6/-5 (docstring) |
| `tests/test_usage_bubble.py` | CREATE | +393 |
| `tests/test_copy.py` | UPDATE | +107 (appended) |
| `tests/test_chat_state.py` | UPDATE | +61/-15 |
| `tests/test_chat_components_import.py` | UPDATE | +5/-2 |
| `tests/test_chat_history.py` | UPDATE | +3 |
| `docs/screenshots/chat-usage-limit{,-light,-budget-light}.png` | CREATE | — |

## Deviations from Plan

1. **`format_usage_limit_notice` treats a timestamp with no timezone as UTC.** The plan only said to parse and format. Without this, `astimezone` would read the audit format minus its `Z` as the server's local time and print the wrong reset hour. `test_the_usage_limit_tokens_notice_formats_the_reset_in_utc` pins it.
2. **E2E 3 could not use "one answered send".** OpenRouter is unreachable from this machine (TLS `CERTIFICATE_VERIFY_FAILED`), so no send can be answered and charged. The startup validator correctly rejects a budget of `*=0`. Instead, today's usage was recorded with `usage_limits.charge("e2e-story014", day, 300, 12, 312)`, the same call a successful send makes, and the app was run with `*=1`. The real-pipeline test in `tests/test_usage_bubble.py` covers the answered-then-refused sequence end to end.
3. **"Reload" in the E2E was done as sign-out then sign-in.** A browser reload keeps Reflex's server-side state, so it would not prove a database restore. Signing out clears the transcript, and signing back in reads the chat from `chat_messages`. The first user bubble of a chat is absent after the restore. That is the documented lazy-create behaviour (`chat_history.py` fact 1), not a regression.
4. **`reflex run` side effects were reverted.** The E2E build rewrote `chat_ui/reflex.lock/package.json` (exact pins became caret ranges) and created `package-lock.json`. Neither belongs to this story, so the first was restored and the second removed before committing.
5. **Unrelated working-tree changes were stashed.** At the start, `pre-prds/README.md` and `pre-prds/PRE-PRD-017-…` were stashed as `stash@{0}` ("pre-prds WIP (stashed during STORY-014 implement)"), with the user's approval, per Phase 2.1. They are restored after the commits.
6. **The Reflex agent skills were not installed.** `chat_ui/AGENTS.md` (a Reflex-managed block) asks for the `reflex-docs`, `setup-python-env` and `reflex-process-management` plugin skills before editing Reflex code. They are not installed on this machine, and installing a third-party plugin was not done without the user's consent. The change only reuses existing `bubbles.py` helpers and `rx.match`, and the subprocess probe and a live prod build both compile it.
7. **The `bubbles.py` module docstring ("The six ledger entries") was left as is.** The plan made this optional, and the count was already stale before this story.

## Design Decisions Carried Out

- **D-A**: the full sentence is stored in `detail`, and `content` holds `result.reason` (`"Usage limit reached"`). No column was added.
- **D-B**: `INK_HELD`/`TINT_HELD`. The renderer's structure test imports `_INK_ON_TINT`, so the bubble and the contrast suite cannot drift apart.
- **D-C**: no Retry action. The renderer has no `_action(`, and a test asserts it.
- **D-D**: the tag is `PAUSED`. This is the one word the plan chose rather than the PRD, and it is pinned in one assertion in `tests/test_copy.py`, so changing it is a one-line decision.
- **D-E**: `USAGE_LIMIT_NOTICES` is indexed, and its keys are pinned to `QueryBlockedUsageLimitResponse.limit`'s literal.
- **D-H**: the interim pin was an `async def`, so the census regex (`^def test_`) never counted it, and deleting it did not trip `test_untouched_app.py`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_usage_bubble.py` (new, 13) | `test_a_refused_send_shows_one_usage_limit_bubble_with_its_sentence[tokens,requests]`, `test_a_reload_restores_the_same_bubble_with_the_same_text[tokens,requests]`, `test_neither_the_bubble_nor_its_user_turn_reaches_the_next_send` (real pipeline and gate, token budget), `test_a_usage_limit_error_shows_the_internal_error_bubble_and_clears_pending`, `test_the_rendered_copy_never_says_rate_limit_quota_sorry_or_oops[tokens,requests]`, `test_the_match_has_a_usage_limit_arm_above_the_default`, `test_the_kind_string_matches_the_bubble_state_builds`, `test_the_usage_limit_bubble_draws_only_contrast_covered_tokens`, `test_the_usage_limit_bubble_writes_no_user_facing_literal`, `test_the_interim_routing_story_011_added_is_gone` |
| `tests/test_copy.py` (+5, appended) | `test_every_usage_limit_string_exists_and_is_not_empty`, `test_the_usage_limit_copy_is_the_wording_the_prd_fixed`, `test_the_usage_limit_copy_names_no_mechanism_and_does_not_apologize`, `test_every_usage_limit_value_has_a_notice_and_nothing_else_does`, `test_the_usage_limit_tokens_notice_formats_the_reset_in_utc` |
| `tests/test_chat_state.py` | `test_chat_state_send_usage_limit_renders_a_usage_limit_bubble[tokens,requests]` (replaces the interim pin); a `usage_limit` case in `test_every_bubble_kind_is_persisted` and in `test_every_bubble_kind_survives_the_round_trip` |
| `tests/test_chat_components_import.py` | `render_usage_limit` and `usage_limit` added to the probe |
| `tests/test_chat_history.py` | `usage_limit` added to `UNANSWERED_KINDS` (parametrized exclusion cases) |

## Acceptance Criteria

- [x] Given a send refused with `limit="tokens"`, when the result arrives, then the thread shows one bubble reading "You've reached today's usage limit. You can send again after 00:00 UTC."; given `limit="requests"`, then it reads "You're sending too fast. Wait a minute, then send again."
- [x] Given either bubble in a saved chat, when the page is reloaded and the chat reopened, then the same bubble is restored with the same text.
- [x] Given a chat containing a usage-limit bubble, when the next send assembles history, then neither the bubble nor the user turn that caused it is sent to the model.
- [x] Given `UsageLimitError` raised during a send, when it is handled, then the thread shows the existing internal-error bubble and `pending` is cleared.
- [x] Given the bubble's rendered copy, when `tests/test_copy.py` and the render-invariant tests run, then the strings contain no "rate limit", "quota exceeded", "sorry" or "oops", and the temporary routing STORY-011 added is gone.
- [x] All tasks completed
- [x] Full suite green
- [x] Follows existing patterns
