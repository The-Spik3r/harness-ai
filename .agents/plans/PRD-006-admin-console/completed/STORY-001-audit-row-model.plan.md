---
story: STORY-001
prd: PRD-006
slug: audit-row-model
title: "AuditRow and SummaryFigure models — a projection with no preview fields"
type: technical
complexity: LOW
epic_branch: epic/PRD-006-admin-console
created: 2026-08-28
---

# Plan: AuditRow and SummaryFigure models — a projection with no preview fields

## Summary

Create `chat_ui/chat_ui/admin_models.py` holding two typed models — `AuditRow`, the register's row projection, and `SummaryFigure`, the tally sheet's figure — plus `tests/test_admin_models.py` asserting the Risk 2 mitigation (neither preview field exists) and that every field is defaulted. Both models subclass `pydantic.BaseModel` exactly as `chat_ui/chat_ui/models.py:4` `ChatMessage` does; every displayed value is a plain, pre-formatted field so components read rather than compute (PRD Section 6, "derived-once row model"). This story defines the models only — populating them is STORY-002 / STORY-004. No file under `app/` is touched.

## User Story

As an integrating developer
I want the register's row model to be an explicit projection of `AuditLog` that has no field for either preview
So that `prompt_preview` and `response_preview` are dropped at the boundary rather than being one binding away from the screen (PRD Section 6, Risk 2).

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-001-audit-row-model.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 6, Section 9, Section 10 (projection table), Section 12 Phase 1, Risk 2

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/` (new module), `tests/` (new test file) |
| Story | STORY-001 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (**NOT AVAILABLE** — see below) | `chat_ui/AGENTS.md` mandates it for any Reflex API: `rx.Base` field defaults and `rx.foreach` Var access over a typed model list | Task 1 |
| `.agents/skills/frontend-design` | Read; governs visual/structural decisions only. This story renders nothing, so no rule binds any task below. | none |

**Skill availability — resolved by direct verification.** The `reflex-docs` skill ships in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed in this environment (`~/.claude/plugins` absent; `.agents/skills/` contains only `frontend-design`). Every prior plan in this repo hit the same gap and resolved it the same way — see `.agents/plans/PRD-002-reflex-chat-ui/completed/STORY-004-chat-ui-components.plan.md:44`. Per that precedent, the Reflex API claims below were verified **against the installed `reflex==0.9.6.post1` package**, not from memory:

| Claim | How verified | Result |
|---|---|---|
| `rx.Base` exists in this Reflex version | `python -c "import reflex as rx; rx.Base"` | **AttributeError: No reflex attribute Base** — `rx.Base` does **not** exist in `reflex==0.9.6.post1` |
| What the shipped code uses instead | `chat_ui/chat_ui/models.py:1-4` | `import pydantic` / `class ChatMessage(pydantic.BaseModel)` |
| Pydantic major version in play | `python -c "import pydantic; print(pydantic.VERSION)"` | `2.13.4` (Reflex 0.9.x is pydantic-v2 based; the old pydantic-v1 `rx.Base` shim is gone) |
| All-defaulted model constructs bare; list default not shared between instances | ran a scratch model with `str`/`int`/`list[str]`/`bool` defaults | `M()` succeeds; mutating one instance's list does not affect the next `M()` |
| Field absence is introspectable | `Model.model_fields` (pydantic v2) + `hasattr` | both report absent fields correctly — usable for the Risk 2 test |

**Consequence for AC 1 and AC 3**: the story and PRD say `AuditRow(rx.Base)` / `SummaryFigure(rx.Base)`. That name does not exist in the pinned Reflex. The implementation subclasses `pydantic.BaseModel`, which is what `rx.Base` *was* an alias for and what the analogous `ChatMessage` already uses in production under `rx.foreach` — the intent of the AC ("a typed Reflex-renderable model with the same subclassing convention as `ChatMessage`") is met exactly; only the literal class name in the AC text is stale. `/implement` must not "fix" this by importing `rx.Base`; it will fail at import time.

---

## Patterns to Follow

### Naming — typed model, all fields defaulted
```python
# SOURCE: chat_ui/chat_ui/models.py:1-21
import pydantic


class ChatMessage(pydantic.BaseModel):
    """Typed chat message model carrying kind discriminator and metadata."""

    kind: str
    content: str
    prompt: str = ""
    model_used: str = ""
    tokens_used: int = 0
    audit_id: int = 0
    pii_redacted: bool = False
    pii_entities: list[str] = []
    pattern: str = ""
    first_query_at: str = ""
    # Humanized duplicate copy, precomputed in the backend: component
    # functions only ever see Vars, so datetime math cannot run at render.
    duplicate_relative_info: str = ""
    duplicate_release_info: str = ""
    detail: str = ""
```
Two conventions to carry over verbatim: a class docstring saying *why* the type exists, and an inline comment on any field that is a pre-formatted string because render time cannot compute it.

### The source row being projected
```python
# SOURCE: app/db/models.py:38-56
@dataclass
class AuditLog:
    timestamp: str
    user_id: str
    prompt_hash: str
    device: Optional[str] = None
    prompt_preview: Optional[str] = None       # <-- dropped at the boundary
    response_hash: Optional[str] = None
    response_preview: Optional[str] = None     # <-- dropped at the boundary
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    was_duplicate_blocked: bool = False
    suspicious_pattern: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    pii_entities: Optional[str] = None         # TEXT, not a list — parsed in STORY-002
    id: Optional[int] = None
```

### Why derived values are pre-formatted strings
```python
# SOURCE: chat_ui/chat_ui/formatting.py:1-8
"""Pure-Python formatting helpers for chat_ui bubbles.

These run in the backend when a message is built, never at component render
time: component functions receive Reflex Vars (JS references), not concrete
values, so Python control flow (`if`, `try`, datetime math) cannot be applied
to them. Anything needing real Python is computed here and stored on the
ChatMessage as a plain string field.
"""
```

### Tests — absence assertions
```python
# SOURCE: tests/test_audit_router.py:184-185
        assert "prompt_preview" not in entry
        assert "response_preview" not in entry
```

### Tests — import preamble for a chat_ui-importing test
```python
# SOURCE: tests/test_contrast.py:9-14  (file shape: tests/test_pii_badge.py:1-40)
import sys
from pathlib import Path

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui import theme
```
(`tests/test_pii_badge.py:5` additionally appends `.../chat_ui`; `tests/test_contrast.py` does not, and passes. Follow `test_contrast.py` — repo-root insert only — since this module imports nothing through the inner package's own namespace.)

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_models.py` | CREATE | `AuditRow` + `SummaryFigure`, the console's two typed models |
| `tests/test_admin_models.py` | CREATE | Risk 2 absence assertions + all-fields-defaulted assertions |

Nothing else. No `app/` file, no existing `chat_ui/` file, no `requirements.txt` entry (PRD Section 8: "No new dependencies in either `requirements.txt`").

---

## Design Decisions

These bind STORY-002 / 004 / 011 / 015, so they are settled here rather than left to the implementer.

**1. Field types on `AuditRow` are display types, not source types.**
PRD Section 6: "`AuditRow` carries the verdict, the relative time and the formatted device string as plain fields, computed in `admin_formatting.py`. Components read fields; they do not compute." So anything whose source is `Optional[...]` and needs an em-dash placeholder in the register (`model_used`, `tokens_used`, `error_message`, `suspicious_pattern`, `device`) is typed **`str`** here, defaulting to `""`, with STORY-002 supplying the placeholder text from `admin_copy`. `tokens_used: str` in particular is deliberate — `Optional[int]` would force an `rx.cond` over `None` at render, the thing Section 6 forbids.

**2. `audit_id` stays `int`.**
Fixed by STORY-005, verbatim: "`audit_id` is an int on `AuditRow`; matching it against free text needs a string coercion — do it in the var, not in the component." So `audit_id: int = 0`, and both the `#3180` rendering and the free-text coercion live downstream.

**3. `pii_indicator` is `bool`, and the split flags are kept alongside it.**
Section 10: "combined PII indicator, split on disclosure". `rx.cond` over a bool Var is legitimate at render (a Var operation, not Python control flow), so the in-row badge needs no pre-formatted string. `pii_detected_input` / `pii_detected_output` are retained as separate bools for STORY-012's disclosure, exactly as the story's AC 1 field list requires.

**4. `verdict` defaults to `""`, not `"cleared"`.**
Every field must have a default (AC 4), but defaulting a *verdict* to `cleared` would make an unpopulated row assert that it passed — the one false statement this model must not be able to make. `""` is inert. STORY-011's `rx.match` over `verdict` therefore needs a default arm; that is flagged forward rather than papered over here.

**5. `SummaryFigure` gets `items` beyond the four named fields.**
AC 3 says "at minimum `label`, `value`, `scope`, and an optional `share`" and gives the reason: "so the summary renders figures rather than ad-hoc tuples". Three of STORY-015's nine figures (`top_models`, `top_users`, `top_pii_entities`) are ranked lists, and with only a scalar `value` they would be exactly the ad-hoc tuples the AC refuses. `items: list[str] = []` (pre-formatted rank lines, empty for scalar figures) closes that. `value` is `str` for the same placeholder reason as decision 1 — it must carry both `3,180` and a percentage.
**Not added**: an `indent` flag. Section 6.1's indentation of the blocked counts beneath the total is layout STORY-015 expresses structurally; it is not a property of a figure.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 0: Create the epic branch

- **Action**: BRANCH
- **Implement**: The story's `epic_branch` is `epic/PRD-006-admin-console` and it does not exist yet (`git branch -a` lists only PRD-001…004). Create it **from `epic/PRD-004-chat-ui-redesign`, not from `main`** — verified: `git ls-tree main --name-only chat_ui/chat_ui/` shows `main` has no `theme.py`, no `models.py` and no `formatting.py`, so PRD-004 is unmerged and a branch off `main` would have no `ChatMessage` to mirror, no theme tokens for Phase 2, and no PII columns. The two untracked PRD-006 doc directories carry across the checkout unchanged.
  ```bash
  git checkout -b epic/PRD-006-admin-console epic/PRD-004-chat-ui-redesign
  ```
- **Validate**: `git branch --show-current` → `epic/PRD-006-admin-console`; `git status --porcelain` still lists only the two untracked `.agents/**/PRD-006*` directories.
- **Note for AC 5**: read the footnote in Acceptance Criteria before running the `git diff main` check — the literal form of that AC does not hold on this branch point, and the honest equivalent is given there.

### Task 1: Create `admin_models.py` with `AuditRow` and `SummaryFigure`

- **File**: `chat_ui/chat_ui/admin_models.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring, in the voice of `formatting.py:1-8`, stating (a) that this is a **projection** of `AuditLog` and (b) that the two preview fields are absent **by policy**, citing PRD Risk 2 verbatim — *"the row model (`AuditRow`) is a deliberate projection that has no field for either preview"* — and that they must not be added "for completeness".
  - `import pydantic` — **not** `import reflex as rx`. `rx.Base` does not exist in `reflex==0.9.6.post1` (verified above).
  - `class AuditRow(pydantic.BaseModel)` with exactly these 16 fields, every one defaulted, in this order:

    | Field | Type | Default | Source / note |
    |---|---|---|---|
    | `audit_id` | `int` | `0` | `AuditLog.id`; int per STORY-005 |
    | `timestamp_absolute` | `str` | `""` | `AuditLog.timestamp` |
    | `timestamp_relative` | `str` | `""` | pre-formatted "2m ago" (STORY-002) |
    | `user_id` | `str` | `""` | |
    | `verdict` | `str` | `""` | one of `cleared`/`held`/`denied`/`fault`; see decision 4 |
    | `model_used` | `str` | `""` | placeholder-formatted |
    | `tokens_used` | `str` | `""` | **string**, see decision 1 |
    | `pii_indicator` | `bool` | `False` | `pii_detected_input or pii_detected_output` |
    | `device_short` | `str` | `""` | truncated in-row |
    | `device_full` | `str` | `""` | full User-Agent, disclosure only |
    | `prompt_hash` | `str` | `""` | disclosure only |
    | `error_message` | `str` | `""` | disclosure only; not projected by `/audit` at all |
    | `pii_entities` | `list[str]` | `[]` | parsed from `AuditLog.pii_entities` TEXT in STORY-002 |
    | `pii_detected_input` | `bool` | `False` | split on disclosure |
    | `pii_detected_output` | `bool` | `False` | split on disclosure |
    | `suspicious_pattern` | `str` | `""` | the real pattern, not `/audit`'s flattened bool |

  - Inline comments in the `ChatMessage:17-19` style on `timestamp_relative`, `tokens_used`, `model_used` and `device_short` — one comment covering the group is enough — recording that these are pre-formatted in `admin_formatting.py` because component functions receive Vars, not values.
  - `class SummaryFigure(pydantic.BaseModel)` with `label: str = ""`, `value: str = ""`, `scope: str = ""`, `share: str = ""`, `items: list[str] = []`; a comment on `share` that its placeholder form comes from `format_share` (STORY-002) so a zero total never raises, and a comment on `items` naming the three ranked figures it exists for.
- **Mirror**: `chat_ui/chat_ui/models.py:1-21` — same import, same subclassing, same all-defaulted convention, same why-comment habit.
- **Do NOT**: add `prompt_preview`, `response_preview`, `response_hash`, or any `raw_*` field; import `reflex`; import from `app/`; add a validator or a `Config`/`model_config` block (neither `ChatMessage` nor anything downstream needs one).
- **Validate**:
  ```bash
  python -c "from chat_ui.chat_ui.admin_models import AuditRow, SummaryFigure; r=AuditRow(); f=SummaryFigure(); print(sorted(AuditRow.model_fields)); print(sorted(SummaryFigure.model_fields)); assert not hasattr(r,'prompt_preview') and not hasattr(r,'response_preview')"
  ```
  → prints the 16 and 5 field names, constructs both bare, exits 0.

### Task 2: Create `tests/test_admin_models.py`

- **File**: `tests/test_admin_models.py`
- **Action**: CREATE
- **Implement**: Module docstring in `test_contrast.py:1-7`'s voice — one paragraph saying the absence of the preview fields *is* the mitigation, so this file is what fails if someone adds them back. Then the `sys.path` preamble with the verbatim "Repo root, not `chat_ui/`" comment, then:
  1. `test_audit_row_has_no_preview_fields` — the Risk 2 guard. Assert on **both** introspection surfaces, because they fail differently: `"prompt_preview" not in AuditRow.model_fields` / `"response_preview" not in AuditRow.model_fields` (catches a declared field) **and** `not hasattr(AuditRow(), "prompt_preview")` / `... "response_preview"` (catches one attached outside the field machinery). Also assert no field name contains `"preview"` at all, so `response_preview_hash` or similar cannot slip in.
  2. `test_audit_row_carries_every_rendered_field` — assert `set(AuditRow.model_fields)` **equals** the exact 16-name set from AC 1, not a subset: it then fails both on a missing field and on an unplanned addition.
  3. `test_audit_row_constructs_with_no_arguments` — `AuditRow()` does not raise, and each field equals its declared type's zero (`0`/`""`/`False`/`[]`); assert appending to one instance's `pii_entities` leaves a fresh `AuditRow().pii_entities` empty.
  4. `test_audit_row_types` — spot-assert the two decisions downstream depends on: `AuditRow().audit_id` is an `int`, `AuditRow().tokens_used` is a `str`. A regression here silently breaks STORY-005's coercion or STORY-011's render.
  5. `test_summary_figure_fields_and_defaults` — `{"label","value","scope","share","items"} == set(SummaryFigure.model_fields)`, `SummaryFigure()` constructs bare, and a populated figure round-trips its values.
  6. `test_audit_row_populated_from_audit_log_drops_previews` — construct a real `AuditLog` (import from `app.db.models`, read-only) with `prompt_preview="raw prompt text"` / `response_preview="raw response text"`, hand-build the `AuditRow` from its fields as STORY-002 will, and assert neither raw string appears anywhere in `str(AuditRow(...).model_dump())`. The boundary assertion in miniature; STORY-006 repeats it against the real `to_audit_row`.
- **Mirror**: `tests/test_pii_badge.py:1-40` for file shape and plain `assert` style; `tests/test_audit_router.py:184-185` for the absence-assert idiom; `tests/test_contrast.py:1-14` for the docstring + path comment.
- **Validate**: `python -m pytest tests/test_admin_models.py -v` → all pass.

### Task 3: Prove nothing else moved

- **File**: none (verification only)
- **Action**: VERIFY
- **Implement**: Run the full suite and the diff checks. This story's whole risk is scope leak, so it is checked rather than assumed.
- **Validate**:
  ```bash
  python -m pytest tests/ -q
  git diff epic/PRD-004-chat-ui-redesign --stat -- app/     # must print nothing
  git status --porcelain                                     # only the two new files + the .agents/ docs
  ```

---

## End-to-End Tests

This story ships no rendered surface, so the E2E checks are import- and boundary-level:

- [ ] `python -c "import chat_ui.chat_ui.admin_models"` from the repo root — imports clean, pulling in neither `reflex` nor any `app` module.
- [ ] `python -m pytest tests/test_admin_models.py -v` — every test above passes.
- [ ] `python -m pytest tests/ -q` — full suite green, with the eight files PRD Section 15 pins (`test_admin_auth.py`, `test_audit_router.py`, `test_stats_router.py`, `test_db.py`, `test_route_reservations.py`, `test_chat_state.py`, `test_copy.py`, `test_contrast.py`) passing **unmodified**.
- [ ] `git diff epic/PRD-004-chat-ui-redesign --stat -- app/` prints nothing.
- [ ] Grep proof of the mitigation: `grep -n "preview" chat_ui/chat_ui/admin_models.py` returns only the docstring/comment lines explaining the absence — never a field declaration.

---

## Validation

```bash
python -m pytest tests/test_admin_models.py -v
python -m pytest tests/ -q
python -c "from chat_ui.chat_ui.admin_models import AuditRow, SummaryFigure; AuditRow(); SummaryFigure()"
git diff epic/PRD-004-chat-ui-redesign --stat -- app/
```

No `npm run lint` — `chat_ui` is Reflex/Python and this repo has no JS package. No Reflex compile/run cycle either, since no component or route changes; the `reflex-process-management` skill therefore does not apply to this story.

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given `chat_ui/chat_ui/admin_models.py`, when it is created, then it defines `AuditRow` carrying every field the register renders: `audit_id`, `timestamp_absolute`, `timestamp_relative`, `user_id`, `verdict`, `model_used`, `tokens_used`, `pii_indicator`, `device_short`, `device_full`, `prompt_hash`, `error_message`, `pii_entities`, `pii_detected_input`, `pii_detected_output`, `suspicious_pattern`. *(Base class is `pydantic.BaseModel`, not `rx.Base` — see Skills In Use: `rx.Base` does not exist in `reflex==0.9.6.post1`, and `ChatMessage` uses `pydantic.BaseModel` for the same reason.)*
- [ ] Given `AuditRow`, when its fields are inspected, then it has **no** `prompt_preview` and **no** `response_preview` attribute, and a test asserts both are absent (Risk 2 mitigation).
- [ ] Given `admin_models.py`, when it is read, then it also defines `SummaryFigure` with `label`, `value`, `scope` and an optional `share` (plus `items` for the three ranked figures), so the summary renders figures rather than ad-hoc tuples.
- [ ] Given every field on both models, when constructed with no arguments, then each has a default, so a partially-populated row never raises at render time.
- [ ] Given `app/`, when the diff is inspected, then no file under it is modified. **Footnote — this AC's literal form cannot hold at this branch point.** `git diff main --stat -- app/` already reports `app/db/database.py` and `app/db/models.py` as changed, because those are **PRD-004's** committed changes and PRD-004 is not yet merged to `main` (verified: `main` has no `chat_ui/chat_ui/theme.py`). The honest equivalent, and the check to run, is `git diff epic/PRD-004-chat-ui-redesign --stat -- app/` → empty: nothing under `app/` moves *because of PRD-006*. Once PRD-004 merges to `main`, the literal `git diff main` form becomes valid again and STORY-020 should use it.
- [ ] All tasks completed
- [ ] Full test suite passes; the eight PRD Section 15 test files pass unmodified
- [ ] Follows existing patterns (`chat_ui/chat_ui/models.py`, `tests/test_contrast.py`)

---

## Risks + Mitigations (this story)

| Risk | Mitigation |
|---|---|
| `/implement` "corrects" `pydantic.BaseModel` back to `rx.Base` because the story text says so | Skills In Use records the verified `AttributeError`, and Task 1 forbids it explicitly. Import fails loudly if it happens anyway. |
| Preview fields added later "for completeness" | Test 1 asserts absence on two introspection surfaces plus a no-`"preview"`-substring check; the module docstring states the policy at the point of temptation. |
| Field set drifts from what STORY-011 renders | Test 2 is an exact set equality, so both a missing and an extra field fail. |
| `tokens_used` retyped `int` by a later refactor | Test 4 pins it as `str`; decision 1 records why. |
| Branching from `main` instead of the PRD-004 epic | Task 0 states the verification (`main` lacks `theme.py`) and the correct base. |

---

## Notes Forward

- **STORY-002** owns `to_audit_row(log, now)`, the placeholder text for the empty `str` fields, and parsing `AuditLog.pii_entities` (TEXT) into `list[str]` — match `app/routers/admin.py`'s existing parse rather than inventing a second format.
- **STORY-011**'s `rx.match` over `verdict` needs a **default arm**, because `verdict` defaults to `""` (decision 4).
- **STORY-015** renders `SummaryFigure.items` for `top_models` / `top_users` / `top_pii_entities`, and expresses the blocked-count indentation as layout — there is deliberately no `indent` field (decision 5).
