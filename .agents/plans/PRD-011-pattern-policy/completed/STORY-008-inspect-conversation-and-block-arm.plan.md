---
story: STORY-008
prd: PRD-011
slug: inspect-conversation-and-block-arm
title: "inspect() over the conversation; _inspection_target deleted; block arm"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-23
---

# Plan: inspect() over the conversation; _inspection_target deleted; block arm

## Summary

This is the first story in PRD-011 that changes a request-path verdict. Today step 5 of `run_conversation` is `detect_suspicious_pattern(_inspection_target(messages))` (`app/services/query_pipeline.py:243-258`): a substring scan over the last user turn only. This story does four things:

1. It adds `inspect(messages, profile, *, max_scan_characters=None) -> PatternInspectionResult` to the pure `pattern_detector` module. The function walks the conversation under a profile's role matrix, using the compiled lists `pattern_config` already builds.
2. It deletes `_inspection_target`, `detect_suspicious_pattern`, `SUSPICIOUS_PATTERNS` and `PatternDetectionResult` outright. There is no shim, per PRD Section 10.
3. It makes step 5 call `inspect(messages, get_profile(...))`, with the profile chosen by a new keyword-only `profile=None` on `run_conversation`.
4. It rewrites every test that named the old API. The rewrite keeps the old tests' assertions, and every changed assertion carries a comment citing PRD-011.

The block arm's body, position, audit row and `success=True` are byte-identical to today's. `pattern_role` and `pattern_action` are STORY-009's, and so is the flag arm. This story computes flags but does not act on them. Under every reachable ingress that is unobservable: `chat` has no flag cell, and `_validate_conversation` still rejects `tool` turns.

## User Story

As a security admin
I want pattern inspection to run over the whole conversation under the profile's role matrix
So that the provisional "last user turn only" policy is replaced by one that is written down and configurable

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-008-inspect-conversation-and-block-arm.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md`, Sections 4 (Pipeline), 6.1, 6.4, 6.6, 7 (F5, F6), 9.2 (T1, T9), 10, 11
- Predecessors:
  - STORY-001: the characterization corpus and `PRD_011_FLIP_CASES` (`tests/test_pattern_characterization.py`)
  - STORY-003: `strip_code_spans`
  - STORY-005 and STORY-006: `PatternList`, `Profile`, `get_profile`, `BUILT_IN_POLICY`
- The STORY-006 report and plan (Risk R-3) hand this story one decision: `pattern_detector` cannot import `Action` or `Profile` from `pattern_config`, because `pattern_config` imports `pattern_detector`. This plan resolves it with structural typing (D-A below).

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH (the new code is small; about 12 test files must be edited without changing a pinned assertion) |
| Systems Affected | `app/services/pattern_detector.py`, `app/services/query_pipeline.py`, docstrings in `pattern_config.py` and `chat_history.py`, about 12 test modules |
| Story | STORY-008 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| *(none)* | `.agents/skills/` contains only `frontend-design`, which covers visual UI design. This story touches no UI. The story's own `skills: []` and PRD Section 15 agree. | — |

---

## Design Decisions

| # | Decision | Why |
|---|----------|-----|
| D-A | **`inspect()` types its inputs structurally.** Three private `typing.Protocol`s in `pattern_detector`: `_Turn(role, content)`, `_InspectedList(name, scope, patterns, compiled)` and `_InspectedProfile(lists, roles)`. There is no `app` import, not even under `TYPE_CHECKING`. | `pattern_config` imports `pattern_detector`, so the reverse import is a cycle. `tests/test_pattern_matching.py:304-324` also forbids any `from app` line in this module. The precedent is `DedupTurn(Protocol)` at `app/services/duplicate_checker.py:42-44`, which is also how `Message` satisfies a type without an import in either direction. `PatternHit.action` is typed `str`, with a comment pointing at `pattern_config.Action` as its vocabulary. |
| D-B | **`PatternInspectionResult(block: Optional[PatternHit] = None, flags: tuple[PatternHit, ...] = (), truncated: tuple[int, ...] = ())`**, all frozen. `truncated` holds the **message indices** that were cut. | The story asks for `truncated` to be "set". The pipeline's WARNING needs the index and both lengths. With the index, the pipeline reads `len(messages[i].content)` and the ceiling it passed in, so the result carries no content-derived numbers. An empty tuple is falsy, so `if result.truncated:` reads naturally. |
| D-C | **The scan ceiling is a keyword-only parameter**, `max_scan_characters: Optional[int] = None` (None means no ceiling). The pipeline passes `settings.PATTERN_MAX_SCAN_CHARACTERS`, **read per call**. | The detector must not read `settings` (purity test). PRD Section 10's `inspect(messages, profile)` stays callable as written. The per-call read mirrors `_context_limit_exceeded` (`query_pipeline.py:82-86`), so `monkeypatch.setattr(settings, ...)` works in tests. |
| D-D | **Walk semantics.** For each message in order: skip it if `message.role not in profile.roles`. Otherwise truncate the text for matching when it exceeds the ceiling, and record the index. Build at most two variants lazily: raw text, and `strip_code_spans(raw)` on the first `outside_code` list. Then walk `profile.lists` in declared order and each list's `(pattern, compiled)` pairs in declared order. A hit whose role action is `block` returns immediately. A `flag` hit is appended, and the walk continues. | This is AC 1 and PRD F5. Truncation comes before stripping, so stripping is bounded too. The lazy cache enforces the "strip at most once per message" budget (PRD Risk 8, STORY-003 docstring `pattern_detector.py:211-216`). Every flag hit is kept in walk order. STORY-009 records `flags[0]` (PRD 6.7). |
| D-E | **Resolve the profile at step 5, not step 0**, with `profile if profile is not None else settings.PATTERN_PROFILE_DEFAULT`. | The story's AC 3 wording is literal. Every arm before step 5 that writes a row returns, so an unknown profile, which is a call-site bug raising `PatternConfigError`, writes no row on the pass path. `is not None` rather than `or`: `profile=""` is a bug and should raise, not silently become the default. |
| D-F | **`profile` is keyword-only** (`*, profile: Optional[str] = None` after `session_id`). | Story Technical Notes: "gains one keyword-only argument at the end". A positional sixth-from-last argument is how a caller silently passes the wrong thing. |
| D-G | **Flags are computed and not acted on in this story.** A comment at step 5 names STORY-009 as the owner of the flag arm. | STORY-009's AC owns it. Reachability: `chat` is `{user: block}`, and `_validate_conversation` rejects every `tool` turn (`query_pipeline.py:56-57`). So no reachable request produces a flag before STORY-009, or until PRD-016 even then. |
| D-H | **The first logger in `query_pipeline`**: `logger = logging.getLogger(__name__)`. The WARNING reads `"pattern scan truncated: user_id=%s message_index=%d length=%d scanned=%d"`. | Mirrors `app/services/reports.py:41,53,323` (lazy `%` args). The content is never interpolated (PRD T9). No audit column is added. |
| D-I | **The old verdict corpus stays as a historical record.** `_CASES` in the characterization module keeps its pre-PRD-011 verdicts. Its assertion is rewritten in place so the new policy's verdict is `after` for every flip row and `today` for every other row. A new test asserts the set of changed texts is exactly `PRD_011_FLIP_CASES`. | This is AC 5, and STORY-001's instruction to rewrite in place rather than delete. `tests/test_pattern_config.py:57,191-211` imports `_CASES` and `PRD_011_FLIP_CASES` in exactly this `(text, today)` / `(text, today, after)` shape, and `test_every_flip_case_is_a_pinned_case` depends on `_CASES` holding the *today* value. |
| D-J | **The grep scope for AC 5** is `app/ chat_ui/ tests/ scripts/ README.md docs/ examples/`. `.agents/` and `pre-prds/` are epic and historical documentation, and `graphify-out/` is generated output. `_inspection_target` is added to the grep even though the AC names only the two symbols. | The story says "outside this epic's documentation", and PRD Risk 6 asks for a repo-wide search for a caller nobody looked for. `graphify-out/` is regenerated rather than hand-edited, so it is called out in the report rather than patched. |

---

## Patterns to Follow

### Structural typing instead of an import (D-A)
```python
# SOURCE: app/services/duplicate_checker.py:42-44
class DedupTurn(Protocol):
    role: str
    content: str
```

### The per-message walk to mirror: the local stand-in STORY-005 wrote for this function
```python
# SOURCE: tests/test_pattern_config.py:171-188
    profile = get_policy().profiles["chat"]
    variants = {"everywhere": text, "outside_code": strip_code_spans(text)}

    for pattern_list in profile.lists:
        subject = variants[pattern_list.scope]
        for pattern, compiled in zip(pattern_list.patterns, pattern_list.compiled):
            if compiled.search(subject):
                return pattern
    return None
```

### Settings read per call, never captured at import
```python
# SOURCE: app/services/query_pipeline.py:91-97
    message_count = len(messages)
    if message_count > settings.CONTEXT_MAX_MESSAGES:
        return "messages", settings.CONTEXT_MAX_MESSAGES, message_count
```

### The block arm, which must stay byte-identical except for its source
```python
# SOURCE: app/services/query_pipeline.py:243-258
    pattern_result = detect_suspicious_pattern(_inspection_target(messages))
    if pattern_result.is_suspicious:
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            suspicious_pattern=pattern_result.pattern,
            success=True,
            session_id=session_id,
            dedup_key=key,
        )
        return QueryBlockedSuspiciousResponse(
            reason="Suspicious pattern detected",
            pattern=pattern_result.pattern,
        )
```

### Logging a WARNING
```python
# SOURCE: app/services/reports.py:53, 323
logger = logging.getLogger(__name__)
...
logger.warning("reports: skipping %s: %s", path, exc)
# test: tests/test_reports_service.py:155-160
with caplog.at_level(logging.WARNING, logger="app.services.reports"):
```

### Order spies patched on the pipeline module, delegating to the real callable
```python
# SOURCE: tests/test_query_pipeline_multiturn.py:137-178
    real_detect = query_pipeline.detect_suspicious_pattern
    def _spy_detect(text):
        trace.append("pattern")
        return real_detect(text)
    monkeypatch.setattr(query_pipeline, "detect_suspicious_pattern", _spy_detect)
```

### Pipeline test shape (direct `run_conversation`, `temp_db`, injected upstream)
```python
# SOURCE: tests/test_query_pipeline_context_limit.py:40-90
_JUAN = Identity(user_id="juan@empresa.com", role="user")
def _fail_if_called(*args, **kwargs):
    raise AssertionError("this collaborator should not have been called")
result = query_pipeline.run_conversation(
    identity=_JUAN, messages=messages, device=None, model="gpt-4",
    openrouter_api_key=None, call_openrouter=_fail_if_called,
)
```

### A deliberately superseded pre-epic test is recorded, not silently deleted
```python
# SOURCE: tests/test_pii_redaction_integration.py:279-283, 401-421, 424-446
_PRE_EPIC_UNTOUCHED_TESTS = [ "tests/test_admin_auth.py", "tests/test_pattern_detector.py", ... ]
_DELIBERATELY_SUPERSEDED_TESTS = { "tests/test_chat_state.py": {...}, ... }
# Each entry is preceded by a comment block naming the PRD/story and the replacement test.
```

---

## Known Traps (from exploration; each one is addressed by a task)

| # | Trap | Where | Task |
|---|------|-------|------|
| T-1 | `tests/test_pattern_detector.py` is **byte-pinned**. The pin is `git diff merge-base(main, HEAD) -- path` must be empty. | `tests/test_pii_redaction_integration.py:279-283, 334-343` | 9 |
| T-2 | A census fails if any `def test_*` present at `merge-base(main, HEAD)` disappears, unless it is listed in `_DELIBERATELY_SUPERSEDED_TESTS`. Local `main` is currently at `51e794f` (PRD-009), so the PRD-010 test files are *not* yet at the base. That changes when PRD-010 merges, so the entries are added regardless. | `tests/test_pii_redaction_integration.py:401-446` | 9 |
| T-3 | `test_run_conversation_signature_matches_the_prd` pins the exact parameter list. | `tests/test_query_pipeline_run_conversation.py:68-77` | 5 |
| T-4 | `test_run_query_delegates_...` pins the forwarded kwargs exactly. `run_query` must **not** forward `profile`. | `tests/test_query_pipeline_run_conversation.py:91-109` | 4 |
| T-5 | Four spies monkeypatch `query_pipeline.detect_suspicious_pattern` with a one-string signature. | `test_query_pipeline_multiturn.py:137,159-161,175,535-541`; `test_pii_dedup_isolation.py:275-297`; `test_query_router.py:357-371` | 5, 7 |
| T-6 | The PRD says no assertion may change in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`, yet the first two import or patch the removed names. Only the *instrument* changes (import source, spy target), never an `assert`. | PRD Section 11, Quality indicators | 7 |
| T-7 | The purity test forbids any `from app` import in `pattern_detector`. | `tests/test_pattern_matching.py:304-324` | 1 |
| T-8 | Another purity test forbids the substrings `pii`, `redact` and `presidio` anywhere in `pattern_detector`'s source, **including docstrings and comments**. | `tests/test_pii_dedup_isolation.py:207-215` | 1 |
| T-9 | The stdlib `inspect` name collides. `query_pipeline` does not use stdlib `inspect`, so a module-level `inspect` import is safe there. Test modules that `import inspect` must reference the detector as `pattern_detector.inspect` or `query_pipeline.inspect`, never `from ... import inspect`. | `test_query_pipeline_run_conversation.py`, `test_pii_dedup_isolation.py`, `test_pattern_matching.py:27` | 5, 6, 7 |
| T-10 | Two tests' docstrings say "this test is expected to flip: rewrite it to assert the injection is caught, **do not delete it**." | `test_query_pipeline_multiturn.py:511-562`; `test_query_pipeline_run_conversation.py:240-254` | 5 |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pattern_detector.py` | UPDATE | Remove `SUSPICIOUS_PATTERNS`, `PatternDetectionResult` and `detect_suspicious_pattern`. Add the Protocols, `PatternHit`, `PatternInspectionResult` and `inspect()`. Update the module and `strip_code_spans` docstrings. |
| `app/services/query_pipeline.py` | UPDATE | Delete `_inspection_target`. Add a `logger`. Import `inspect`, `get_profile` and `settings`, which is already imported. Rewrite step 5. Add keyword-only `profile` to `run_conversation`. |
| `app/services/pattern_config.py` | UPDATE (docstrings only) | `_build_built_in` and the `Action` comment reference the deleted constant and a future STORY-008. Reword them to the past tense. |
| `app/services/chat_history.py` | UPDATE (docstring only) | Line 87 names `query_pipeline._inspection_target`. Reword it to "the pipeline inspects every `user` turn". |
| `tests/test_pattern_detector.py` | UPDATE (rewrite) | Keep the four function names. Rewrite each around `inspect`, and add walk-order, short-circuit and role-skipping tests (AC 1, AC 2). |
| `tests/test_pattern_characterization.py` | UPDATE | Swap the instrument to `inspect` under the default profile. Rewrite the assertion in place (D-I). Add an exact-flip-set test. Retarget the coverage test to the built-in patterns. |
| `tests/test_pattern_matching.py` | UPDATE | Delete `test_the_pre_prd_011_api_is_untouched_by_this_story`. Its own docstring says to delete it (added in this epic, so no census entry is needed). Update the imports, module docstring and comment. |
| `tests/test_pattern_config.py` | UPDATE | Drop the `SUSPICIOUS_PATTERNS` import. Rewrite `test_built_in_lists_hold_exactly_todays_seven_patterns` against the literal seven, as its docstring says. Make `_verdict` delegate to `inspect`. |
| `tests/test_query_pipeline_patterns.py` | CREATE | Block arm, check order via spies, profile passthrough, scan-ceiling WARNING, byte-identical body. |
| `tests/test_query_pipeline_multiturn.py` | UPDATE | Order spy moves to `inspect`. Flip the provisional-policy test into "earlier user turn is blocked". Replace the marker test with a deletion test. Add `profile` to `_FORBIDDEN_BODY_FIELDS`. |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE | Signature pin gains keyword-only `profile`. Replace the `_inspection_target` test and flip the lighter provisional test. |
| `tests/test_pii_dedup_isolation.py` | UPDATE | `SUSPICIOUS_PATTERNS` becomes a local literal. The spy moves to `inspect` and the label to `"inspect"`, with a PRD-011 comment. |
| `tests/test_query_router.py` | UPDATE (instrument only) | Spy on `query_pipeline.inspect` and record the inspected contents. `seen_pattern == [_PII_PROMPT]` is **unchanged**. |
| `tests/test_integration.py` | UPDATE (instrument only) | The import becomes a local tuple of the seven built-in patterns. The parametrized assertions are **unchanged**. |
| `tests/test_duplicate_scope.py` | UPDATE (instrument only) | `_PATTERN = SUSPICIOUS_PATTERNS[0]` becomes the literal `"ignore previous instructions"`. |
| `tests/test_pii_redaction_integration.py` | UPDATE | Remove `test_pattern_detector.py` from `_PRE_EPIC_UNTOUCHED_TESTS`, with a citing comment. Add census entries for superseded functions (T-2). |
| `tests/test_chat_history.py` | UPDATE (docstring only) | Line 353 names `_inspection_target`. |

**Not touched:** `app/models/schemas.py` (no `profile` field, per story Technical Notes and T1), `app/routers/query.py`, `chat_ui/chat_ui/state.py` (both pass nothing and get the default), `tests/test_query_outcomes_regression.py`, `tests/test_chat_outcomes_regression.py`, `tests/test_history_off_integration.py`, the audit schema (STORY-009), README (STORY-013).

---

## Tasks

Execute in order. Each task is atomic and verifiable. The libSQL dev server must be up for any DB-backed test (`temp_db`). If mass fixture errors appear, restart the container rather than bisecting the code.

### Task 1: `inspect()` and its result types in `pattern_detector`

- **File**: `app/services/pattern_detector.py`
- **Action**: UPDATE
- **Implement**:
  - Delete `SUSPICIOUS_PATTERNS`, `PatternDetectionResult` and `detect_suspicious_pattern` (lines 26-48), and the `List` import if it becomes unused. Keep `Optional`. Import `Mapping`, `Protocol`, `Sequence`.
  - Add the Protocols (D-A), each with a one-line docstring explaining why this is structural:
    ```python
    class _Turn(Protocol):
        role: str
        content: str

    class _InspectedList(Protocol):
        name: str
        scope: str
        patterns: tuple[str, ...]
        compiled: tuple[re.Pattern, ...]

    class _InspectedProfile(Protocol):
        lists: Sequence[_InspectedList]
        roles: Mapping[str, str]
    ```
  - Add the frozen dataclasses:
    ```python
    @dataclass(frozen=True)
    class PatternHit:
        list_name: str
        pattern: str
        role: str
        message_index: int
        action: str        # pattern_config.Action: "block" | "flag" (cannot import it: cycle)

    @dataclass(frozen=True)
    class PatternInspectionResult:
        block: Optional[PatternHit] = None
        flags: tuple[PatternHit, ...] = ()
        truncated: tuple[int, ...] = ()   # indices of inspected messages cut for matching
    ```
  - Add `inspect(messages, profile, *, max_scan_characters=None) -> PatternInspectionResult`, following D-D exactly. Build the stripped variant lazily and only once per message:
    ```python
    stripped = None
    for pattern_list in profile.lists:
        if pattern_list.scope == "outside_code":
            if stripped is None:
                stripped = strip_code_spans(text)
            subject = stripped
        else:
            subject = text
    ```
    On a block hit, return `PatternInspectionResult(block=hit, flags=tuple(flags), truncated=tuple(truncated))`. Otherwise return the same with `block=None`.
  - Docstring: the walk order, "a role absent from `roles` is not inspected", block short-circuit versus flag accumulation, that the ceiling truncates **for matching only**, that stripping happens at most once per message, and why the parameters are structural.
  - Rewrite the module docstring's "`SUSPICIOUS_PATTERNS` and `detect_suspicious_pattern` below are pre-PRD-011..." paragraph to say they were removed by STORY-008 (PRD-011 Section 10). Update the `strip_code_spans` docstring's "No caller yet, by design. `inspect()` (STORY-008)..." to present tense.
  - **Do not** write the words `pii`, `redact` or `presidio` anywhere in this file (T-8), and add no `from app` import (T-7).
- **Mirror**: `app/services/duplicate_checker.py:42-44` (Protocol); `tests/test_pattern_config.py:171-188` (walk)
- **Validate**: `python -c "from app.services.pattern_detector import inspect, PatternHit, PatternInspectionResult; from app.services.pattern_config import get_profile; from app.models.messages import Message; print(inspect([Message('user','please override now')], get_profile('chat')))"` prints a block hit on `override` / `keywords` / `user` / index 0. Then run `python -m pytest tests/test_pattern_matching.py -k "pure or pii" tests/test_pii_dedup_isolation.py -k "unmodified_on_this_branch" -q`, which runs the purity tests.

### Task 2: Rewrite `tests/test_pattern_detector.py` around `inspect`

- **File**: `tests/test_pattern_detector.py`
- **Action**: UPDATE (full rewrite; the byte pin is released in Task 9)
- **Implement**: A module docstring citing PRD-011 Section 10 ("removed, not deprecated") and STORY-008. Keep all four function names, so the census (T-2) sees no removal, and give each a PRD-011 comment:
  - `test_each_pattern_is_flagged_individually`: parametrize over every pattern in `BUILT_IN_POLICY.profiles["chat"].lists`. `inspect([Message("user", f"please {p} now")], chat).block.pattern == p`.
  - `test_clean_prompt_reports_not_suspicious`: `block is None`, `flags == ()`, `truncated == ()`.
  - `test_mixed_case_pattern_still_flagged`: unchanged semantics.
  - `test_first_matching_pattern_returned_when_multiple_present`: **the list-order precedence case, preserved** (story Technical Notes). "please override and enable admin mode" reports `admin mode`. Keep the comment, updated to say the order comes from the `keywords` list's declared order.

  New tests (AC 1, AC 2):
  - `test_messages_are_walked_in_order`: two user turns, each with a different blocking hit. The block is on index 0.
  - `test_lists_walk_in_declared_order_before_patterns`: a text that hits both `injection` and `keywords`. The `injection` hit wins, because `chat` declares `injection` first.
  - `test_block_short_circuits_the_walk`: a synthetic profile (a small frozen dataclass or `SimpleNamespace` satisfying the Protocols, lists taken from `BUILT_IN_POLICY.lists`) with `{"tool": "flag", "user": "block"}`. A tool flag, then a user block, then a later tool flag. Result: one flag (index 0), a block at index 1, and **no** flag from index 2.
  - `test_flags_accumulate_in_walk_order`: two tool turns under `code`. Two flags in order, `block is None`.
  - `test_tool_flag_then_user_block_under_code_reports_the_user_block` (AC 2): `result.block.role == "user"`, `result.block.action == "block"`, and the tool flag is in `flags`.
  - `test_same_conversation_under_chat_reports_nothing` (AC 2): the same messages under `chat` give `block is None and flags == ()`.
  - `test_roles_absent_from_the_map_are_not_inspected`: `system`, `assistant` and `tool` turns carrying an injection under `chat` report nothing.
  - `test_outside_code_list_ignores_a_fenced_hit_and_everywhere_does_not`: a fenced ```` ```override``` ```` gives no hit. A fenced `ignore previous instructions` still blocks (T6).
  - `test_code_spans_are_stripped_at_most_once_per_message`: monkeypatch `pattern_detector.strip_code_spans` with a counting wrapper. One message under `chat`, which has one `outside_code` list, gives exactly 1 call. A message whose role is not inspected gives 0 calls.
  - `test_scan_ceiling_truncates_for_matching_and_records_the_index`: `max_scan_characters=10`, with the pattern placed after character 10. No hit, `truncated == (0,)`. With the ceiling unset, the hit is found and `truncated == ()`. A short message is not recorded.
  - `test_hit_carries_list_role_index_and_action`: all five `PatternHit` fields.
- **Mirror**: `tests/test_pattern_profiles.py` (imports and profile access); `tests/test_pattern_config.py:171-188`
- **Validate**: `python -m pytest tests/test_pattern_detector.py -v`, all green.

### Task 3: Rewrite the characterization instrument (AC 5, the flip set)

- **File**: `tests/test_pattern_characterization.py`
- **Action**: UPDATE
- **Implement** (D-I):
  - Change the import to `inspect` from `pattern_detector`, plus `get_profile` and `Message`, and read `settings.PATTERN_PROFILE_DEFAULT` for the profile name, which is the "default policy" the AC names.
  - Update the module docstring. `_CASES` is now the **frozen record** of the removed detector's verdicts. STORY-008 swapped the instrument, and the assertion now reads the new policy.
  - Rename `test_todays_verdict` to `test_verdict_under_the_default_policy` (it was added in this epic, so no census entry is needed). The body is `expected = _FLIPS.get(text, today)`. Assert `result.block.pattern if result.block else None == expected`, and `result.flags == ()` (chat has no flag cell). Keep the "both fields agree" spirit: `(result.block is not None) is (expected is not None)`. Add a comment citing PRD-011 Section 11 *Refinement*.
  - Add `test_exactly_the_flip_set_changed`: `{text for text, today in _CASES if verdict(text) != today} == {text for text, _, _ in PRD_011_FLIP_CASES}`.
  - Keep `test_every_flip_case_is_a_pinned_case` unchanged.
  - Rename `test_every_suspicious_pattern_is_covered` to `test_every_built_in_pattern_is_covered`. It iterates the patterns of the built-in `chat` profile's lists.
  - Remove the "Predicted, not observed" hedge on the fenced row now that it is observed. Keep the row.
- **Validate**: `python -m pytest tests/test_pattern_characterization.py -v`. Every row is green and the flip-set test passes. If the flip-set test reports an extra text, **stop**: that is an unplanned verdict change (AC 5), not a test to adjust.

### Task 4: `run_conversation` step 5 and the `profile` keyword

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: add `import logging`. Replace line 28 with `from app.services.pattern_detector import inspect` and add `from app.services.pattern_config import get_profile`. Add `logger = logging.getLogger(__name__)` after the imports.
  - Delete `_inspection_target` (lines 62-69).
  - Signature: after `session_id: Optional[str] = None,` add `*,` and `profile: Optional[str] = None,` (D-F).
  - Replace step 5 (lines 243-258). Keep every `log_query` argument and the response exactly as they are:
    ```python
    # Step 5: patterns, over the whole conversation under the profile's role
    # matrix (PRD-011 Sections 6.1, 6.4, F5). Position unchanged: after every
    # authorization arm and the duplicate check, before redaction -- the raw
    # text is inspected, never the masked one. `profile` is chosen by the call
    # site, never by a request field (PRD-011 D2, T1).
    profile_name = profile if profile is not None else settings.PATTERN_PROFILE_DEFAULT
    scan_ceiling = settings.PATTERN_MAX_SCAN_CHARACTERS
    inspection = inspect(messages, get_profile(profile_name), max_scan_characters=scan_ceiling)
    for index in inspection.truncated:
        # PRD-011 T9: user id, index and both lengths -- never the content.
        logger.warning(
            "pattern scan truncated: user_id=%s message_index=%d length=%d scanned=%d",
            identity.user_id, index, len(messages[index].content), scan_ceiling,
        )
    if inspection.block is not None:
        log_query(..., suspicious_pattern=inspection.block.pattern, success=True,
                  session_id=session_id, dedup_key=key)
        return QueryBlockedSuspiciousResponse(
            reason="Suspicious pattern detected",
            pattern=inspection.block.pattern,
        )
    # inspection.flags: the flag arm (audit, then continue) is STORY-009's.
    # Unreachable until then -- `chat` has no flag cell and step 0 refuses
    # every `tool` turn (PRD-016).
    ```
  - `run_query`: **unchanged** (T-4). It passes nothing.
  - Update the `_validate_conversation` and `InvalidConversationError` docstrings only where they cite `_inspection_target`, if they do.
- **Mirror**: `query_pipeline.py:82-97` (per-call settings reads)
- **Validate**: `python -c "import app.services.query_pipeline as q, inspect as i; print(i.signature(q.run_conversation))"` shows `..., session_id=None, *, profile=None`. `python -c "import app.services.query_pipeline as q; assert not hasattr(q, '_inspection_target')"`.

### Task 5: Fix the PRD-010 pipeline tests that named the old step 5

- **Files**: `tests/test_query_pipeline_multiturn.py`, `tests/test_query_pipeline_run_conversation.py`
- **Action**: UPDATE
- **Implement**:
  - `test_query_pipeline_multiturn.py`:
    - `_install_order_spies` (123-178): `real_inspect = query_pipeline.inspect`, then `_spy_inspect(messages, profile, **kwargs)` appends `"pattern"` and delegates. Patch `"inspect"`. Keep the `"pattern"` label and `_PRD_ORDER` unchanged. Add a comment: PRD-011 STORY-008 swapped the collaborator and the position is unchanged.
    - `test_provisional_policy_inspects_last_user_turn_only` (511-562): **rewrite, do not delete** (T-10). Rename it to `test_an_injection_in_an_earlier_user_turn_is_blocked`. Same three messages, `call_openrouter=_fail_if_called`. It is now `QueryBlockedSuspiciousResponse` with `pattern == "ignore previous instructions"`, one row with `suspicious_pattern` set. The spy records each inspected message list, and the assertion is that the inspector saw all three messages (`[m.content for m in seen[0]]`). Docstring: PRD-011 closes D6/T2 here. `test_the_same_injection_as_the_last_turn_is_blocked` stays as is.
    - `test_inspection_target_still_carries_its_provisional_marker` (587-594) becomes `test_inspection_target_is_deleted`: `assert not hasattr(query_pipeline, "_inspection_target")`. Mirror `test_user_turn_is_deleted` (`run_conversation.py:64-65`).
    - `_FORBIDDEN_BODY_FIELDS` (602): add `"profile"`, with a comment naming PRD-011 Section 6.6 / T1 and story Technical Notes ("the permissive profile is unreachable from a request body"). Update the offender message so it mentions profile.
  - `test_query_pipeline_run_conversation.py`:
    - `test_run_conversation_signature_matches_the_prd` (68-77): append `"profile"` to the list. Assert `default is None` and `kind is inspect.Parameter.KEYWORD_ONLY`. Add a PRD-011 comment.
    - `test_inspection_target_is_marked_provisional_and_returns_the_last_user_turn` (231-237) becomes `test_inspection_target_is_deleted_and_every_user_turn_is_inspected`: a `hasattr` check plus a direct `run_conversation` on `[user injection, assistant, user clean]` that blocks.
    - `test_provisional_policy_inspects_last_user_turn_only` (240-254): rewrite as the lighter flip. Rename it to `test_an_earlier_user_turn_injection_is_now_blocked`; it asserts `QueryBlockedSuspiciousResponse`.
    - Module docstring line 5: replace the `_inspection_target` mention.
  - Record every renamed or removed function name above in Task 9's census list.
- **Validate**: `python -m pytest tests/test_query_pipeline_multiturn.py tests/test_query_pipeline_run_conversation.py -v`, all green.

### Task 6: `tests/test_query_pipeline_patterns.py`, the new block-arm suite

- **File**: `tests/test_query_pipeline_patterns.py`
- **Action**: CREATE
- **Implement**: A module docstring scoped to STORY-008's ACs, noting that STORY-009 extends this file with the flag arm. Import `app.services.query_pipeline as query_pipeline` (no bare `inspect` import; T-9). Local `_JUAN`, `_fail_if_called`, `_Upstream`, `_count_audit_rows`, `_last_audit_entry` (mirror `test_query_pipeline_context_limit.py:40-70`). Tests:
  - `test_block_body_is_byte_identical_to_today`: `result.model_dump() == {"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": "ignore previous instructions"}` and `"role" not in` the dump (AC 4, D7).
  - `test_block_writes_one_audited_row_and_never_calls_upstream`: `call_openrouter=_fail_if_called`. Exactly one new row with `suspicious_pattern` set, `success is True`, `session_id == _SESSION_ID` (passed explicitly), and `dedup_key == dedup_key(_JUAN.user_id, messages)` (non-NULL).
  - `test_pattern_check_runs_after_duplicate_and_before_redaction`: spies on `check_duplicate`, `inspect` and `redact` (a clean pass, so redact runs). The trace is `["duplicate", "pattern", "redact", ...]`. A second case: a duplicate conversation never reaches `inspect`.
  - `test_denied_caller_never_reaches_inspection`: `_DENIED` identity with `inspect` patched to `_fail_if_called`, which gives a forbidden response.
  - `test_inspection_sees_raw_text_not_redacted`: a prompt with an email. The spy records `messages[-1].content == raw`.
  - `test_omitted_profile_runs_pattern_profile_default`: spy on `query_pipeline.get_profile`, recording the name. No `profile` gives `["chat"]`. With `monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "code")`, the same call gives `["code"]`, read per call.
  - `test_profile_code_is_passed_through`: `profile="code"`, `get_profile` sees `"code"`. Behavioural proof: `"please override now"` **passes** under `code` (no `keywords` list) and **blocks** under the default. Use `_Upstream` for the pass.
  - `test_run_query_passes_no_profile`: `run_query` with a spied `get_profile` sees `settings.PATTERN_PROFILE_DEFAULT`.
  - `test_unknown_profile_raises_config_error_and_writes_no_row`: `profile="nope"` raises `PatternConfigError`, and the row count is unchanged.
  - `test_profile_is_keyword_only`: passing it positionally raises `TypeError`.
  - `test_over_ceiling_message_warns_without_content`: `monkeypatch.setattr(settings, "PATTERN_MAX_SCAN_CHARACTERS", 20)`, with a user turn of 40 chars whose injection sits after char 20. The result passes (upstream called: truncated for matching only). Use `caplog.at_level(logging.WARNING, logger="app.services.query_pipeline")`. Exactly one record containing `user_id=juan@empresa.com`, `message_index=0`, `length=40` and `scanned=20`, and **not** containing any substring of the message text.
  - `test_upstream_still_receives_the_full_message_when_truncated`: `_Upstream` captures the messages, and the last content length is 40.
- **Mirror**: `tests/test_query_pipeline_context_limit.py`; `tests/test_query_pipeline_multiturn.py:123-178`; `tests/test_reports_service.py:155-160`
- **Validate**: `python -m pytest tests/test_query_pipeline_patterns.py -v`, all green.

### Task 7: Swap the instrument in the pre-epic suites (no assertion changes)

- **Files**: `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_pii_dedup_isolation.py`, `tests/test_duplicate_scope.py`
- **Action**: UPDATE
- **Implement**: Every edit carries `# PRD-011 STORY-008: detect_suspicious_pattern removed (PRD Section 10); ...`.
  - `test_query_router.py:357-371`: `real_inspect = query_pipeline.inspect`, then `_spy_pattern(messages, profile, **kwargs)` does `seen_pattern.extend(m.content for m in messages)` and delegates. Patch `"inspect"`. **Line 380's `assert seen_pattern == [_PII_PROMPT]` is not edited** (T-6); a single-turn `/query` produces exactly one content.
  - `test_integration.py:15, 99`: replace the import with a module-level `_BUILT_IN_PATTERNS = ("ignore previous instructions", "forget everything", "show system prompt", "reveal password", "execute code", "admin mode", "override")` and parametrize over it. The body assertions are unchanged. It is a literal, not derived from `BUILT_IN_POLICY`, so the test pins the default policy rather than echoing it.
  - `test_duplicate_scope.py:62, 75`: `_PATTERN = "ignore previous instructions"`.
  - `test_pii_dedup_isolation.py`:
    - `:30` and `:249`: the same local literal tuple.
    - `:275-297`: the spy becomes `_spy_pattern(messages, profile, **kwargs)`, appending `("inspect", messages[-1].content)`, and patches `"inspect"`.
    - `:312`: the expected label becomes `"inspect"`, with a citing comment (this file is not in the PRD's no-change list; the label renames the collaborator, and the position assertion is untouched).
    - `:195`: reword the comment.
- **Validate**: `python -m pytest tests/test_query_router.py tests/test_integration.py tests/test_pii_dedup_isolation.py tests/test_duplicate_scope.py -q`, all green. Then `git diff -U0 tests/test_query_router.py tests/test_integration.py | grep '^[-+].*assert'` must print nothing (T-6).

### Task 8: The remaining references and docstrings

- **Files**: `tests/test_pattern_matching.py`, `tests/test_pattern_config.py`, `app/services/pattern_config.py`, `app/services/chat_history.py`, `tests/test_chat_history.py`
- **Action**: UPDATE
- **Implement**:
  - `test_pattern_matching.py`: delete `test_the_pre_prd_011_api_is_untouched_by_this_story` (331-345) and leave a one-line comment in its place citing PRD-011 Section 10 (its own docstring asks for this). Drop `SUSPICIOUS_PATTERNS` and `detect_suspicious_pattern` from the imports (29, 32). Reword the module docstring at line 12 and the comment at 353. The purity test stays and must pass.
  - `test_pattern_config.py`: drop the import at `:46`. Rewrite `test_built_in_lists_hold_exactly_todays_seven_patterns` (118-132) against the literal seven, as its docstring says. `_verdict` (171-188) becomes `inspect([Message("user", text)], get_policy().profiles["chat"])`, returning the block pattern or None. Its docstring loses "a local stand-in for STORY-008's".
  - `pattern_config.py:88-92, 179-190, 25-27, 31-32`: the past tense. "STORY-008 deleted that constant", "`PatternHit.action` carries the same two values and is typed `str` in `pattern_detector` because of the import cycle".
  - `chat_history.py:87` and `test_chat_history.py:353`: "would blank `query_pipeline._inspection_target`, which inspects the last user turn" becomes "would give the pattern inspection an empty `user` turn".
- **Validate**: `python -m pytest tests/test_pattern_matching.py tests/test_pattern_config.py tests/test_pattern_profiles.py tests/test_chat_history.py -q`, all green.

### Task 9: Release the byte pin and record the superseded tests

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**:
  - Remove `"tests/test_pattern_detector.py"` from `_PRE_EPIC_UNTOUCHED_TESTS` (279-283). Add a comment block in the file's established style (see the PRD-010 STORY-003 paragraph at 270-278): PRD-011 Section 10 removes `detect_suspicious_pattern` outright and STORY-008 rewrites that file around `inspect()`. The file moves from layer 1 (byte pin) to layer 2 (census). Its four function names are kept, so the census still holds it.
  - Add `_DELIBERATELY_SUPERSEDED_TESTS` entries, each preceded by a comment naming PRD-011 STORY-008 and the replacement:
    - `"tests/test_query_pipeline_multiturn.py": {"test_provisional_policy_inspects_last_user_turn_only", "test_inspection_target_still_carries_its_provisional_marker"}`
    - `"tests/test_query_pipeline_run_conversation.py": {"test_inspection_target_is_marked_provisional_and_returns_the_last_user_turn", "test_provisional_policy_inspects_last_user_turn_only"}`

    These are harmless today, because the files are not at `merge-base(main, HEAD) = 51e794f`. They become required once PRD-010 is on `main` (T-2). State that in the comment.
- **Validate**: `python -m pytest tests/test_pii_redaction_integration.py -q`, all green. The byte pin no longer lists the rewritten file, and the census reports nothing missing.

### Task 10: The repository-wide grep (AC 5, PRD Risk 6)

- **Action**: VERIFY
- **Implement**: `git grep -nE "detect_suspicious_pattern|SUSPICIOUS_PATTERNS|_inspection_target|PatternDetectionResult" -- app chat_ui tests scripts README.md docs examples`. It must print nothing. Also run it without the pathspec and confirm every remaining hit is under `.agents/`, `pre-prds/` or `graphify-out/` (D-J). List the `graphify-out/` hits in the report as "generated; stale until the next graphify run", and do not hand-edit them.
- **Validate**: The first command exits 1 with empty output.

### Task 11: Full suite

- **Action**: VERIFY
- **Implement**: Run the full suite. In particular, confirm `tests/test_query_outcomes_regression.py`, `tests/test_chat_outcomes_regression.py` and `tests/test_history_off_integration.py` pass with `git diff --stat` showing them untouched.
- **Validate**: `python -m pytest tests/ -q` is green, and `git diff --name-only -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_history_off_integration.py` is empty.

---

## Risks and Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| R-1 | **Existing chat sessions start blocking.** Every `user` turn is now inspected, not only the last. A stored earlier turn that passed the old substring detector but matches under word matching blocks every later send in that session. That is only the two `\s+` flip rows: a phrase split by a newline or a doubled space. | This is the intended consequence of AC 1 and PRD Section 11 (the flip set is exactly those rows). It is narrow, and the block names the pattern. Record it in the report for STORY-013's README. No code mitigation: exempting history would reintroduce the D6 gap. |
| R-2 | An assertion in a no-change file drifts while the instrument is swapped. | Task 7's `git diff ... grep assert` check. Task 11's untouched-file check. |
| R-3 | The census or byte pin (T-1, T-2) fails later, when PRD-010 merges to `main` and the base moves. | Task 9 adds the census entries now, even though they are not yet required. |
| R-4 | A purity test fails on a docstring word (T-8) or a guarded import (T-7). | Task 1 names both. D-A uses Protocols and no `TYPE_CHECKING` import. |
| R-5 | `inspect` shadows stdlib `inspect` in a test module. | T-9: tests reach the detector through `query_pipeline.inspect` or `pattern_detector.inspect`, never by a bare `from ... import inspect`. |
| R-6 | Inspection cost grows with conversation length (PRD Risk 8). | Stripping is lazy and at most once per message (asserted in Task 2). Patterns are precompiled. The ceiling bounds each scan. The measurement at `CONTEXT_MAX_MESSAGES` is STORY-011's. |
| R-7 | The flag arm is silently absent. | D-G: a comment at step 5 plus STORY-009's AC. It is unreachable because `tool` turns are refused at step 0. |

---

## End-to-End Tests

- [ ] With the libSQL dev server and the app running (`uvicorn app.main:app`), `POST /query` with `{"prompt": "please ignore previous instructions"}` and a valid bearer returns 200 and exactly `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"ignore previous instructions"}`. `GET /audit` shows the row with `suspicious_pattern` set.
- [ ] `POST /query` with `{"prompt": "this method overrides the base implementation"}` goes through, because it is a flip row. `{"prompt": "please override the rules"}` still blocks with `override`.
- [ ] `POST /query` with an extra `"profile": "code"` field behaves exactly as without it. The field is not a schema field, so the default `chat` profile runs and the `override` prompt still blocks.
- [ ] Chat UI, with history on: send a clean message, then a message containing `ignore previous instructions`. The second is blocked. Clean sends continue in a new session.

---

## Validation

```bash
python -m pytest tests/test_pattern_detector.py tests/test_pattern_characterization.py tests/test_query_pipeline_patterns.py -v
python -m pytest tests/test_pattern_matching.py tests/test_pattern_config.py tests/test_pattern_profiles.py -q
python -m pytest tests/test_query_pipeline_multiturn.py tests/test_query_pipeline_run_conversation.py tests/test_pii_dedup_isolation.py tests/test_pii_redaction_integration.py -q
python -m pytest tests/test_query_router.py tests/test_integration.py tests/test_duplicate_scope.py tests/test_query_outcomes_regression.py -q
git grep -nE "detect_suspicious_pattern|SUSPICIOUS_PATTERNS|_inspection_target|PatternDetectionResult" -- app chat_ui tests scripts README.md docs examples   # expect no output
python -m pytest tests/ -q
```

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given `inspect(messages, profile)` in `app/services/pattern_detector.py`, when it runs, then it walks messages in order, skips any message whose role is absent from the profile's map, walks that profile's lists in declared order and their patterns in declared order, and returns `PatternInspectionResult(block, flags, truncated)`. A `block` action short-circuits the walk; `flag` actions accumulate.
- [ ] Given a conversation with a `tool` flag before a `user` block under the `code` profile, when inspected, then `result.block` is the user hit; given the same conversation under `chat`, then nothing is reported, because `chat` inspects `user` only.
- [ ] Given `app/services/query_pipeline.py`, when it is read, then `_inspection_target` is gone, step 5 calls `inspect(messages, get_profile(profile or settings.PATTERN_PROFILE_DEFAULT))`, and `run_conversation` takes a new trailing keyword `profile: Optional[str] = None`. `run_query`'s signature is unchanged and passes nothing.
- [ ] Given a blocking hit, when the request is refused, then the response is byte-identical to today's (`{"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": ...}`, with no role field), the audit row carries `suspicious_pattern`, `success=True`, an explicit `session_id` and a non-NULL `dedup_key`, and `call_openrouter` is never called.
- [ ] Given STORY-001's characterization flip set, when the corresponding cases run under the default policy, then exactly those verdicts have flipped and no others. `detect_suspicious_pattern` and `SUSPICIOUS_PATTERNS` are removed, `tests/test_pattern_detector.py` is rewritten around `inspect`, a repository-wide grep for both names returns nothing outside this epic's documentation, and `tests/test_query_outcomes_regression.py` passes with no assertion modified.
- [ ] All tasks completed
- [ ] Full `pytest tests/` green
- [ ] No assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`, and every modified pre-existing test carries a comment citing PRD-011
- [ ] Follows existing patterns (Protocol typing, per-call settings reads, explicit `session_id` / `dedup_key` on every `log_query` arm)
