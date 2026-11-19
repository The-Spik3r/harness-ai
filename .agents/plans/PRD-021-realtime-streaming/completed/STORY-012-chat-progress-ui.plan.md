---
story: STORY-012
prd: PRD-021
slug: chat-progress-ui
title: Progress line, live answer and reasoning block in the chat UI
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-19
---

# Plan: Progress line, live answer and reasoning block in the chat UI

## Summary

STORY-011 left seven live vars on `ChatState` (`state.py:243-252`). This story renders them. `copy.py` gets the progress vocabulary. A pure `progress.py` turns `(stage, phase, action)` into one word. A computed var feeds the pending entry, whose evidence line becomes `word · N s`. When `live_text` is non-empty the entry also shows the live answer, and when `live_reasoning` is non-empty a live reasoning block. The seconds counter and the 300 ms no-flicker rule run **in the browser** (an `add_hooks` interval, no server ticker). The success bubble gets an in-memory `reasoning` field (never stored) so the block can stay collapsed under the final answer.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-012-chat-progress-ui.md` (AC text lives there)
- PRD sections used: 6.7, 7.1, D8, D19, T4 (9.2), T3 (labelling)
- Systems affected: `chat_ui/` only. No `app/` file changes (guard tests unaffected).

## Design Decisions

- **The UI never reads grants (binding 1).** Components test only `live_text != ""` and `reasoning != ""` / `live_reasoning != ""`. Nothing under `components/` imports `authz`, `holds` or names a permission. A test greps `components/*.py` for those names.
- **Reasoning after the answer without persisting it (binding 2).** `ChatMessage` gains `reasoning: str = ""` and `reasoning_open: bool = False` (UI only). `_do_send` fills `reasoning` from `live_reasoning` at the success bubble (`state.py` ~1406), read under `async with self` before `_append_and_persist` clears it (`:1044-1047`). `_to_stored_message` (`:93`) builds `StoredMessage` field by field and `StoredMessage` has no column for it, so **do not add it there**; the exclusion is the test. `_to_chat_message` (`:~141`) does not set it, so a restore gives `""`. Error bubbles never set it. The guard at `tests/test_chat_state.py:2452` (`stored - ChatMessage.model_fields`) is unaffected by new bubble-only fields.
- **Client-side timing, no new server deltas (binding 3).** Verified in reflex 0.9.6.post1: `Component.add_hooks()` returns JS inserted in the component function, deduplicated per page (`reflex_base/components/component.py:884-913`, collected via `_get_added_hooks` `:2093-2125` and `_get_all_hooks` `:2148`); `add_custom_code()` (`:915`) puts module-level JS in the page; `add_imports()` (`:~860-883`) adds `useEffect`. So one hook, `useEffect(() => { const id = setInterval(hxProgressTick, 100); return () => clearInterval(id) }, [])`, runs for the page's life and costs no websocket traffic. `hxProgressTick` queries `[data-hx-progress]` and is a no-op when the pending entry is absent. `rx.moment` (`reflex_components_moment`) is rejected: it needs an npm package, a new dependency. A server ticker is not used.
  - The word span is **JS-owned**: React renders it with a constant initial child (`PENDING_INDICATOR_TEXT`) and never re-renders its children, so `textContent` set by JS is not clobbered. React only updates the attributes `data-word` (target word) and `data-since` (`progress_since`) and, on the wrapper, `data-sent-at` (`progress_sent_at`).
  - 300 ms rule: when `data-word` differs from the shown word, the tick records the target and the time it was first seen; it shows the word once the target is unchanged for 300 ms, and drops the pending change if the target moves again. A sub-300 ms stage is never shown.
  - Seconds: shown as `· N s`, updated only when N changes (once a second).
  - **Deviation to report:** the epoch values are used as **change keys** (a new `data-sent-at` resets the client clock; a new `data-since` restarts the 300 ms timer), and elapsed is measured with `performance.now()` from the first tick that saw the key. Subtracting a server epoch from `Date.now()` is wrong under client clock skew (negative or minutes-off seconds). Error is at most one render lag (<~150 ms). The orchestrator may overrule; the alternative is `Date.now()/1000 - sent_at` with a clamp at 0.
  - The tick function is one JS string constant (`PROGRESS_TICK_JS`), written against a tiny interface (`now`, elements), so a test runs it under `node` (present locally; skip if absent) with fake elements and a fake clock.
- **Accessibility (binding 4).** The `aria-live="polite"` region wraps only the word span (`aria_atomic`), never the seconds span. The seconds span is a sibling, `aria-hidden="true"`. The reasoning toggle is `rx.el.button` (`type="button"`, `aria_expanded`, `aria_controls`), covered by the global `:focus-visible` rule (`theme.py:291-295`). Collapsed by default after the answer. While streaming the live block is always open (no toggle there: one job per element). At 360 px: the progress row wraps (`flex_wrap="wrap"`), `overflow_wrap="anywhere"`, `min_width="0"`, `max_width="100%"` on the block.
- **Which word shows.** `progress.progress_word(stage, phase, action)` is pure: a late stage (`evaluating_actions`, `masking_output`) wins when set; otherwise the phase word if a phase is set; otherwise the stage word; otherwise `waiting`. This relies on STORY-006 emitting `waiting` on entering step 7; the implementer confirms by reading the `_scripted_phases` helper and `app/services/delivery.py` `phase_of`. `ChatState.progress_word` is a computed var over `progress_stage/phase/action`; it changes only when a batch changes them, so it adds no deltas beyond STORY-011's.
- **T4 / copy (binding 5).** All strings in `copy.py`, English, keyed by event name: `PROGRESS_STAGE_WORDS` and `PROGRESS_PHASE_WORDS` dicts (`"waiting": PENDING_INDICATOR_TEXT`), `PROGRESS_PREPARING_TEMPLATE = "Preparing an action: {kind}"`, `PROGRESS_KIND_WORDS` (`shell` run a command, `sql` query a database, `fs_write` edit a file, `fs_read` read a file, `http` make a web request), `PROGRESS_KIND_FALLBACK = "use a tool"`, `PROGRESS_ELAPSED_TEMPLATE = "{n} s"`, `REASONING_LABEL = "Model reasoning — not checked as an answer"`, `REASONING_NOT_SAVED = "Not saved with the chat"`, `REASONING_SHOW`/`REASONING_HIDE` toggle labels. The model's raw tool name never reaches a word: the action is `PhaseEvent.action_kind`, a closed `OperationKind` (`app/services/action_classifiers/__init__.py:31`), and an unknown value falls to `use a tool`.
- **Reasoning toggle on the bubble** is a user event, `ChatState.toggle_reasoning(index)`, flipping `messages[index].reasoning_open` (rare, user-initiated; not churn). Implementer verifies against reflex source that an attribute set on a pydantic item of a state list marks the var dirty (`reflex/istate` mutable proxy); if not, replace the item (`self.messages[i] = msg.model_copy(update=...)`).

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`) | End-user-side words, active voice, one job per element, floor: 360 px, visible focus, reduced motion, no new animation | Tasks 1, 4, 5 |
| reflex-docs (chat_ui/AGENTS.md) | Reflex APIs are checked against the installed source, not memory (cited above); not installed as a skill here | Tasks 3-5 |

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Copy | `copy.py:1-9`, `:75-78` | one file, English, voice rule; tag/constant naming |
| Pending slot | `bubbles.py:509-517` (`render_pending_indicator`) and `components/chat.py:57` | keep the no-arg signature, `_entry(None, _rail(pulse=True), _tag(PENDING_TAG), ...)` |
| Prose / data face | `bubbles.py:61-71` (`_prose`), `:74-83` (`_evidence`) | live text via `_prose`, reasoning in `_evidence`-style data face |
| Real button | `bubbles.py:86-` (`_action`) | `rx.el.button`, `type="button"` |
| Pulse | `bubbles.py:516`, `theme.py:315-324` | reuse `hx-pulse`; reduced-motion block already stops it; add no keyframe |
| Pure helper outside state | `live_batch.py` (no Reflex import) | `progress.py` the same way |
| State tests | `tests/test_chat_state_streaming.py:130-175, 289-316` | `_install`, `_scripted_phases`, `_send`, `temp_db`, `_record_batches` |
| Component probe | `tests/test_chat_components_import.py:55-110` | subprocess with `PYTHONPATH=chat_ui`, `message_var = ChatState.messages[0]` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | progress vocabulary, reasoning labels |
| `chat_ui/chat_ui/progress.py` | CREATE | pure `progress_word`, `PROGRESS_TICK_JS`, no Reflex import |
| `chat_ui/chat_ui/models.py` | UPDATE | `ChatMessage.reasoning`, `.reasoning_open` (comment: in-memory, D8) |
| `chat_ui/chat_ui/state.py` | UPDATE | `progress_word` var, fill `reasoning` at the success bubble, `toggle_reasoning`; leave `_to_stored_message` untouched (add a comment there naming D8) |
| `chat_ui/chat_ui/components/progress_line.py` | CREATE | `ProgressLine` component (hooks), `render_reasoning_block` |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | pending entry content; reasoning block under `render_assistant` |
| `tests/test_chat_progress_ui.py` | CREATE | all new tests |
| `tests/test_chat_components_import.py` | UPDATE | add `render_reasoning_block` to the renderer list only if it takes `message_var` (comment citing PRD-021 STORY-012) |

## Tasks

### Task 1: Copy constants
- **File**: `chat_ui/chat_ui/copy.py`. **Action**: UPDATE, after `PENDING_TAG` (`:78`).
- **Implement**: the constants listed under T4 above. Stage and phase dicts are keyed by the exact `StageName` / `PhaseName` literals (`app/services/delivery.py:35-48`).
- **Validate**: Task 6 enumeration test.

### Task 2: Pure word function and tick script
- **File**: `chat_ui/chat_ui/progress.py`. **Action**: CREATE.
- **Implement**: `progress_word(stage, phase, action) -> str` per the precedence rule; `preparing_action` uses `PROGRESS_PREPARING_TEMPLATE.format(kind=PROGRESS_KIND_WORDS.get(action, PROGRESS_KIND_FALLBACK))`. `PROGRESS_TICK_JS` defines `hxProgressTick()` (see Design). `from .copy import ...` only.
- **Mirror**: `live_batch.py:1-40` (module docstring citing PRD-021 decisions, no I/O).

### Task 3: Model and state
- **Files**: `models.py`, `state.py`. **Action**: UPDATE.
- **Implement**: the two fields; `@rx.var progress_word` beside `has_messages` (`:312`); at the success bubble (`:1406`) read `live_reasoning` under `async with self` just before building and pass `reasoning=`; `toggle_reasoning` as `@rx.event`. Do not touch `_clear_live` (still seven vars) or `_to_stored_message`'s argument list.
- **Mirror**: `state.py:312-316` (computed var), `:345-357` (event handlers).

### Task 4: ProgressLine component
- **File**: `chat_ui/chat_ui/components/progress_line.py`. **Action**: CREATE.
- **Implement**: `class ProgressLine(rx.el.Div)` with `add_imports` (`useEffect` from `react`), `add_custom_code` (`PROGRESS_TICK_JS`), `add_hooks` (the interval effect). `create` renders: wrapper `data-hx-progress`, `data-sent-at`, `data-since`, `data-word` bound to `ChatState` vars; word span `aria-live="polite"` with child `PENDING_INDICATOR_TEXT` and class `hx-pulse` (the only motion); seconds span `aria-hidden`, empty initially. Then `render_reasoning_block(reasoning, open_, on_toggle=None)`: label + `Not saved with the chat` in the data face; the body uses `white-space: pre-wrap`, and `max_height` with scroll so a long thought cannot push the answer off a 360 px screen; the button only when `on_toggle` is given.
- **Mirror**: `bubbles.py:61-83`, `:86-`. Verify attribute names (`custom_attrs` for `data-*`, `aria_live`) against `reflex_components_core/el/elements/base.py`.

### Task 5: Wire the entries
- **File**: `components/bubbles.py`. **Action**: UPDATE.
- **Implement**: `render_pending_indicator()` keeps its signature, tag `PENDING_TAG`, rail pulse. Content: `rx.cond(ChatState.live_reasoning != "", live reasoning block)`, `rx.cond(ChatState.live_text != "", _prose(ChatState.live_text))`, then `ProgressLine`. In `render_assistant` (`:177`), add `rx.cond(message.reasoning != "", render_reasoning_block(..., on_toggle=ChatState.toggle_reasoning(index)))`; `rx.foreach` in `components/chat.py:50` must pass the index (`lambda m, i`), check the `message_bubble` dispatch signature (`chat.py:~30`) and keep the other renderers' signature.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_components_import.py tests/test_chat_ui_startup_guard.py`

### Task 6: Tests (`tests/test_chat_progress_ui.py`)
- Copy (T4): `STAGE_NAMES`/`PHASE_NAMES` from `app.services.delivery` each map to a `copy.py` constant (a stage with no copy fails); `get_args(OperationKind)` each has a kind word; `waiting` is `PENDING_INDICATOR_TEXT`; every string in the dicts and the two labels is ASCII-or-the-em-dash English and is a module-level constant; `progress_word("", "preparing_action", "bogus")` gives `use a tool`, and a raw tool name never appears.
- Word: precedence cases; the seven words in the PRD table render exactly.
- Reasoning (D8): drive `_do_send` with `sink.reasoning("secret thought")` (pattern `test_chat_state_streaming.py:289`): `state.messages[-1].reasoning == "secret thought"`, `_live == _LIVE_DEFAULTS`, **the text is in no persisted column** (`dataclasses.asdict` of every `chat_messages` row, and a `SELECT *` over the table, stringified), `_to_stored_message` output has no `reasoning` key, restore (`_to_chat_message`/switch session) gives `reasoning == ""`, the D16 fault bubble (`upstream_error`) has `reasoning == ""`.
- Components: no `authz`/`holds`/`permission`/`stream:realtime` names in `components/` (regex); render probe (subprocess, as `tests/test_chat_components_import.py`) asserts the pending entry still has tag `SENDING`, the `aria-live` element's children do not include the elapsed span, the live `_prose` has `white-space: pre-wrap`, no new `@keyframes` or `animation` in `theme.GLOBAL_CSS` beyond today's.
- JS (node, skip if absent): fake clock: a word that changes at t=0 and again at t=200 ms is never shown; one stable for 300 ms is shown; seconds go 0,1,2 on a 1 s clock; a new `data-sent-at` resets to 0; `aria-live` node's text changes only on a word change.
- Server churn: reuse `_record_batches`; a 1 s send makes no more deltas than `test_two_hundred_tokens...` (`:217`) allows, i.e. nothing in this story adds an `async with self`.

## End-to-End Tests

- [ ] Real app (reflex run, per the `reflex-process-management` skill if installed): send a prompt on a file-mode streaming registry with both grants; watch word and seconds advance, live text grow in the pending slot, final bubble replace it with the reasoning block collapsed; reload the session, no block. With no grants: the same screen with `Waiting on the model · N s` only. At 360 px, no horizontal scroll; Tab reaches the toggle, focus ring visible; reduced motion stops the pulse.
- [ ] If a real run is not possible in the environment, say so in the report; the node and probe tests carry AC2.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_progress_ui.py tests/test_chat_components_import.py tests/test_chat_ui_startup_guard.py tests/test_chat_state_streaming.py tests/test_chat_state.py -k "not slow"
```

`tests/test_chat_state.py` is the existing test of the module changed; if it is slow, run `-k "stored or restore or message or transcript"`. No `app/` file is touched, so `test_untouched_app.py` is not required. No test is renamed.

## Acceptance Criteria → Tasks → Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 copy vocabulary + T4 | 1, 2 | `test_chat_progress_ui.py` enumeration tests |
| AC2 word + seconds, 300 ms, aria-live | 2, 4 | node tick tests, render probe, word precedence |
| AC3 live entry in the pending slot, SENDING, `_prose` | 5 | render probe, `test_chat_components_import.py` |
| AC4 reasoning block, collapsed after, not restored | 3, 4, 5 | reasoning (D8) tests |
| AC5 focus, `hx-pulse` only, 360 px | 4, 5 | CSS diff test, e2e manual |

## Risks

- Clock skew: handled by anchoring to first sight (decision above).
- Hook placement: hooks run at page level, not inside the `rx.cond`; the tick must be a no-op without the element (tested).
- A server `progress_since` change that does not change the word (same word, new stage) restarts nothing visible; the tick keys on the word.
