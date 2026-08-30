---
story: STORY-005
prd: PRD-006
slug: filter-and-sort-vars
title: "Client-side filter and sort as computed vars over the loaded rows"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-30
---

# Plan: `visible_rows` — filter and sort as computed vars over the rows already in state

## Summary

Add the register's filter and sort **state** to `AdminState`, and the one computed var that derives the displayed rows from it. Four new plain vars — `selected_verdicts: list[str]`, `search: str`, `sort_key: str`, `sort_descending: bool` — plus `visible_rows`, an `@rx.var` that reads `self.rows` and those four and returns a filtered, sorted `list[AuditRow]`. The var touches no database function and awaits nothing: [[STORY-004]] already put the whole 100-row window in state, so narrowing it is a pure list comprehension over data the session holds. The filtering predicate and the sort key table live as **module-level pure functions** in `admin_state.py` (PRD Section 6's file tree assigns "gate, reads, filters, sort" to this module), so they are unit-testable without a Reflex state instance, while the getter itself reads all five state vars **directly in its own body** so Reflex's auto-dependency tracker sees every one of them. The verdict vocabulary is imported from [[STORY-002]]'s `admin_formatting.py` (`VERDICTS`) rather than re-declared, and the verdict sort order is derived from that same tuple. Every new var defaults to a falsy value, which is not incidental: `sign_out()` is `reset()`, and `tests/test_admin_state.py:244-256` asserts every declared var restores to a falsy default — so the register's "timestamp, newest first" default is encoded as *the loaded order*, reached with `sort_key == ""`, not as a truthy default on a flag. Four small event handlers (`set_search`, `toggle_verdict`, `sort_by`, `clear_filters`) mutate this state; the **controls** that call them are [[STORY-013]], the no-matches empty state is [[STORY-014]], and the tests are [[STORY-006]].

## User Story

As a compliance admin
I want to narrow the register to one verdict or one user and to reorder it
So that investigating a specific report does not mean re-reading the whole window (PRD Section 5, stories 4 and 5).

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-005-filter-and-sort-vars.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (register, three states), Section 5 (stories 4 and 5), Section 6 ("filtering as a computed var"), Section 6.1 (the wireframe these vars feed), Section 7, Section 12 Phase 1, Risk 5

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/admin_state.py` (UPDATE — the only file). No `app/` change, no new module, no component, no test file (that is STORY-006). |
| Story | STORY-005 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

**Dependency check**: `depends_on: [STORY-004]` — `status: done` on this branch at `e8c331e`. `AdminState.rows` is populated with `list[AuditRow]` in `list_audit_logs`' returned order (newest first), and `admin_formatting.VERDICTS` exists. Working tree is clean on `epic/PRD-006-admin-console`. Cleared to proceed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (**NOT INSTALLED** — substituted, see below) | `chat_ui/AGENTS.md` mandates it for any Reflex API. This story uses two: the `@rx.var` computed-var decorator, and its dependency-tracking rules — which decide whether `visible_rows` re-evaluates when `search` changes. | Task 1, Task 3 |
| `reflex-process-management` (**NOT INSTALLED**) | Mandated for any compile/run/reload cycle. This story renders nothing and starts no server; validation is import + a direct drive of the var against a constructed state. | none |
| `.agents/skills/frontend-design` | Read in full. Scanned and found **not binding on this story**: it governs visual direction, typography and copy, and this story emits no user-facing string and no component. Its rules land in [[STORY-013]] (the controls) and [[STORY-014]] (the empty-state copy), both of which consume these vars. Recorded so a later reader knows it was checked rather than skipped. | none |

**Skill availability and the substitution.** `reflex-docs` and `reflex-process-management` ship in the `reflex-dev/agent-skills` Claude Code *plugin*, which is not installed in this environment — `~/.claude/plugins` is absent and `.agents/skills/` holds only `frontend-design`. This is the same gap STORY-001 through STORY-004 recorded; it is a tooling gap, not a decision to work from memory. `chat_ui/AGENTS.md`'s rule is *"rather than relying on memory"*, so every Reflex API below was verified against two sources before being written into a task: the **installed** `reflex==0.9.6.post1` source (`site-packages/reflex_base/vars/base.py`), which is the pinned version itself and therefore stronger evidence than any prose, and current Reflex documentation (context7 `/websites/reflex_dev`, `docs/vars/computed-vars`).

What was verified for **this** story:

1. **`rx.var` is `computed_var`**, and its signature in the pinned version is `computed_var(fget=None, initial_value=Unset, cache=True, deps=None, auto_deps=True, interval=None, backend=None, **kwargs)` (`reflex_base/vars/base.py:2854-2864`). The two defaults that matter here are `cache=True` and `auto_deps=True`.
2. **Cached by default.** Docs, verbatim: *"By default, computed variables are cached, meaning they only recompute when their dependent state variables change."* So `visible_rows` re-evaluates on a change to a tracked dependency and is otherwise served from cache — the exact behaviour Risk 5 needs. `cache=False` must **not** be passed: it would re-run the comprehension on every state update on the page, including a `loading` flip.
3. **Auto-dependency tracking reads the getter's bytecode.** `ComputedVar._deps` (`reflex_base/vars/base.py:2527-2576`) delegates to `DependencyTracker`, whose docstring is explicit: *"Save references to attributes accessed on `self` or other fetched states. Recursively called when the function makes a method call on `self` or define comprehensions or nested functions that may reference `self`."* Two consequences bind Task 3: (a) a dependency is only seen if it is reached from the getter as an attribute of `self` — a **module-level free function** that receives plain lists is invisible to the tracker, which is exactly why the getter must load `self.rows`, `self.selected_verdicts`, `self.search`, `self.sort_key` and `self.sort_descending` in its own body and pass them down as arguments; (b) tracking failure is **not** an exception — the `except` arm at `:2570-2576` emits a `console.warn` and falls back to *no* dependencies, which would silently produce a var that never updates. Task 4 asserts the tracked set rather than trusting it.
4. **A computed var cannot be assigned.** Docs, verbatim: *"Computed vars are defined using the `@rx.var` decorator and automatically update based on changes to other vars; they cannot be set directly by event handlers."* So `visible_rows` is derived only; the four mutating handlers write the plain vars beneath it.
5. **`AsyncComputedVar` exists** for coroutine getters (`reflex_base/vars/base.py:2897-2900`). Deliberately **not** used: an `async` getter would be the shape a database-backed filter takes, and AC 2 forbids a database read here. A synchronous getter makes "no database read" true by construction — there is nothing to await.

---

## Patterns to Follow

### The one computed var already on this codebase

```python
# SOURCE: chat_ui/chat_ui/state.py:33-36
    @rx.var
    def has_messages(self) -> bool:
        return len(self.messages) > 0
```

Bare `@rx.var` (no parentheses, no kwargs), an annotated return type, and a body that reads state off `self` and computes nothing else. `visible_rows` is the same shape with a longer body.

### The plain-setter convention: explicit handlers, not the implicit ones

```python
# SOURCE: chat_ui/chat_ui/admin_state.py:145-147
    @rx.event
    def set_token_input(self, text: str):
        self.token_input = text
```

Reflex 0.9.6 would auto-generate `set_<var>` handlers (`reflex/state.py:1172-1177`, gated on `state_auto_setters`), but both `ChatState` and `AdminState` declare theirs explicitly. Follow the file, not the framework default — `set_search` is written out.

### Compute-once, and where a string coercion belongs

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:1-10 (module docstring)
"""...component functions receive Reflex Vars (JS references), not concrete
values, so Python control flow (`if`, `try`, datetime math) cannot be applied
to them. ... Components read fields; they do not compute."""
```

The story's fourth technical note is this rule applied to one field: `audit_id` is an `int` on `AuditRow` (`admin_models.py:32`), and matching it against free text needs `str(...)`. That coercion happens inside the var, in Python, never in a component against a Var.

### The verdict vocabulary — imported, never re-declared

```python
# SOURCE: chat_ui/chat_ui/admin_formatting.py:42-46
VERDICT_CLEARED = "cleared"
VERDICT_HELD = "held"
VERDICT_DENIED = "denied"
VERDICT_FAULT = "fault"
VERDICTS = (VERDICT_CLEARED, VERDICT_HELD, VERDICT_DENIED, VERDICT_FAULT)
```

The comment above them states the reason: *"they are the `rx.match` keys and the filter values downstream, so they are constants rather than inline literals in three components."* This story is the downstream. `admin_state.py` already imports from this module (`from .admin_formatting import format_refreshed_at, to_audit_row`); `VERDICTS` joins that import.

### The falsy-default invariant that constrains every new var

```python
# SOURCE: tests/test_admin_state.py:244-256
def test_sign_out_clears_every_declared_var(configured_token):
    """The guarantee has to hold for fields that do not exist yet: STORY-004 and
    STORY-005 add more, and a field cleared nowhere is the one that survives a
    sign-out unnoticed."""
    ...
    for name in AdminState.base_vars:
        value = getattr(state, name)
        assert value in ("", 0, False, None) or value == [], (name, value)
```

This test names this story and is already green; it must stay green. It is why `sort_descending` cannot default to `True` and `sort_key` cannot default to `"timestamp"` — see Risk 1 for how the default ordering is expressed instead.

### The comment register to match

`admin_state.py` explains *why* a structure is load-bearing, at the site, in prose (see its module docstring and the `_READS` block at `:82-110`). New code here follows that register — a comment where a later edit could silently remove a requirement, and nowhere else.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | The four filter/sort vars, the sort-key constants and rank table, the two pure helpers, `visible_rows` + `filters_active`, and the four mutating handlers |

Nothing else. No file under `app/` is read differently or written; no new module; `admin_formatting.py` is imported from, not edited; `tests/` is [[STORY-006]].

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Import `VERDICTS`, and declare the sort vocabulary as module constants

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**:
  1. Extend the existing import to `from .admin_formatting import VERDICTS, format_refreshed_at, to_audit_row`. Do **not** re-declare the four verdict strings (story technical note 2).
  2. Below `REGISTER_ROW_LIMIT`, add the sort vocabulary and the rank table:
     ```python
     # The three orderings the register offers (PRD-006 Section 6.1's controls,
     # built in STORY-013). Values, not copy — they are the `sort_key` the
     # controls write and the keys `_SORT_RANKS` dispatches on, so they are
     # constants here rather than string literals in a component.
     SORT_TIMESTAMP = "timestamp"
     SORT_USER = "user"
     SORT_VERDICT = "verdict"
     SORT_KEYS = (SORT_TIMESTAMP, SORT_USER, SORT_VERDICT)

     # Each key's rank function takes (position in the loaded list, row) and
     # returns a sort key. The position is the first argument for one reason:
     # `list_audit_logs` already returns ORDER BY timestamp DESC
     # (app/db/database.py:128), so a row's index *is* its recency rank, and it
     # is available on every row — unlike `timestamp_absolute`, which
     # `_format_timestamps` sets to the absent mark when the column is NULL or
     # unparseable (admin_formatting.py:167-176). Sorting on that string would
     # sink every unparseable row to one end of the register on a filter the
     # admin did not ask for. Sorting on the index reproduces the database's
     # own ordering exactly, including its ties.
     #
     # The verdict rank is the NEGATED index into VERDICTS, so the natural
     # order runs fault -> denied -> held -> cleared: the exceptions the
     # register exists to surface come first, which is the same statement the
     # stamp margin makes (PRD-006 Section 6.1, "Signature"). An unrecognised
     # verdict — including AuditRow's "" default — ranks 1 and sorts last,
     # rather than raising ValueError out of `.index()` into a page render.
     _SORT_RANKS = {
         SORT_TIMESTAMP: lambda index, row: index,
         SORT_USER: lambda index, row: row.user_id.casefold(),
         SORT_VERDICT: lambda index, row: (
             -VERDICTS.index(row.verdict) if row.verdict in VERDICTS else 1
         ),
     }
     ```
- **Mirror**: `chat_ui/chat_ui/admin_state.py:82-110` (`_READS` — a module-level dispatch table with the reason for its existence stated above it) and `admin_formatting.py:42-46` (the verdict constants and why they are constants)
- **Validate**:
  ```bash
  python -c "import chat_ui.chat_ui.admin_state as m; assert m.SORT_KEYS == ('timestamp','user','verdict'); assert set(m._SORT_RANKS) == set(m.SORT_KEYS); print('ok')"
  grep -n '"cleared"\|"held"\|"denied"\|"fault"' chat_ui/chat_ui/admin_state.py   # no output — no re-declared verdict string
  ```

### Task 2: Add the two pure helpers, `_matches` / `filter_rows` and `sort_rows`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: module-level functions, directly below the sort table and above `class AdminState`. Pure: they take lists and plain values, touch no state and no database, and are importable and testable without constructing a state.
  ```python
  def _matches(row: AuditRow, verdicts: list[str], needle: str) -> bool:
      """Whether one row survives both filters.

      Two properties are requirements rather than choices:

      An **empty** verdict selection passes every row. "No verdict filter" and
      "no rows" are opposite statements, and reading the empty list as the
      second is the bug that makes an untouched register render blank
      (PRD-006 Section 4's three states, and STORY-014's whole distinction).

      The free text matches `audit_id` **as a string**. It is an int on
      AuditRow, and the register's join back to the chat is a user quoting
      "#127" out of the success footer (PRD-004 STORY-010) — so the coercion
      happens here, in Python, not in a component against a Var.
      """
      if verdicts and row.verdict not in verdicts:
          return False
      if not needle:
          return True
      return any(
          needle in field
          for field in (
              row.user_id.casefold(),
              row.model_used.casefold(),
              str(row.audit_id),
          )
      )


  def filter_rows(
      rows: list[AuditRow], verdicts: list[str], search: str
  ) -> list[AuditRow]:
      """The rows passing the verdict selection AND the free text.

      The two filters compose as AND, never OR: an admin who has selected
      *denied* and typed a user is asking for that user's denied rows, and an
      OR would widen the register at the exact moment they are narrowing it
      (PRD-006 Section 5, story 4 — "denied plus a.torres narrows 100 rows to
      2").

      The needle is case-folded and stripped **once** here rather than per row:
      the comparison is case-insensitive (AC 3), and a hundred rows times three
      fields is three hundred `.casefold()` calls that would otherwise be four
      hundred.
      """
      needle = search.strip().casefold()
      if not verdicts and not needle:
          # The common case, and it returns a copy rather than `rows` itself:
          # the caller sorts this list, and sorting the state's own list in
          # place would mutate `rows` from inside a computed var.
          return list(rows)
      return [row for row in rows if _matches(row, verdicts, needle)]


  def sort_rows(
      rows: list[AuditRow], sort_key: str, descending: bool
  ) -> list[AuditRow]:
      """The rows in the requested order; the loaded order when none is set.

      `sorted` rather than `list.sort`, because the argument may be the state's
      own row list and a computed var must not mutate what it reads.

      An empty or unrecognised `sort_key` falls back to SORT_TIMESTAMP, whose
      rank is the position in `rows` — so the default is the order
      `list_audit_logs` returned, newest first, and `sort_key == ""` and
      `sort_key == "timestamp"` are the same register (AC 5). That equivalence
      is what lets `sort_key` default to the empty string, which is what
      `sign_out()`'s reset() requires of every declared var.

      The sort is stable and there is no explicit tiebreak, deliberately: rows
      arrive in timestamp order, so two rows with the same user or the same
      verdict keep their relative recency inside the group for free.
      """
      rank = _SORT_RANKS.get(sort_key, _SORT_RANKS[SORT_TIMESTAMP])
      # enumerate first, sort the (index, row) pairs on the rank, drop the
      # index. The index has to reach the key function, and `sorted(rows, ...)`
      # cannot supply it.
      return [
          row
          for _, row in sorted(
              enumerate(rows),
              key=lambda pair: rank(pair[0], pair[1]),
              reverse=descending,
          )
      ]
  ```
  Points the implementation must not drift on:
  - `if verdicts and row.verdict not in verdicts: return False` — the `verdicts and` guard is AC 6 and must not be simplified to `row.verdict not in verdicts`.
  - `row.model_used` and `row.user_id` are always `str` on `AuditRow` (`_text()` substitutes the absent mark for NULL), so `.casefold()` cannot hit `None`.
  - Neither function imports or calls anything from `app.db.database`. AC 2's "no database read" is true because there is nothing here that could perform one.
- **Mirror**: `chat_ui/chat_ui/admin_formatting.py:130-176` (`_text`, `_parse_pii_entities`, `_truncate_device` — small module-level pure helpers with the degradation rule stated in the docstring)
- **Validate**:
  ```bash
  python -c "
  from chat_ui.chat_ui.admin_state import filter_rows, sort_rows
  from chat_ui.chat_ui.admin_models import AuditRow
  rows=[AuditRow(audit_id=127,user_id='A.Torres',verdict='denied',model_used='gpt-4'),
        AuditRow(audit_id=1270,user_id='m.silva',verdict='cleared',model_used='GPT-4')]
  assert [r.audit_id for r in filter_rows(rows,[],'127')]==[127,1270]   # substring, both
  assert [r.audit_id for r in filter_rows(rows,['denied'],'a.torres')]==[127]  # AND
  assert len(filter_rows(rows,[],''))==2 and len(filter_rows(rows,[],'  '))==2
  assert filter_rows(rows,[],'') is not rows
  assert [r.audit_id for r in sort_rows(rows,'',False)]==[127,1270]
  assert [r.audit_id for r in sort_rows(rows,'timestamp',False)]==[127,1270]
  assert [r.audit_id for r in sort_rows(rows,'timestamp',True)]==[1270,127]
  assert [r.audit_id for r in sort_rows(rows,'verdict',False)]==[127,1270]  # denied before cleared
  assert [r.audit_id for r in sort_rows(rows,'user',False)]==[127,1270]     # a.torres before m.silva, casefolded
  assert [r.audit_id for r in sort_rows(rows,'nonsense',False)]==[127,1270] # unknown key degrades
  print('ok')"
  ```

### Task 3: Declare the four filter vars and the two computed vars on `AdminState`

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: a new `# --- Filter and sort ---` block after the `# --- The record ---` block (after `error: str = ""`, `admin_state.py:143`), then the computed vars after it.
  ```python
      # --- Filter and sort --------------------------------------------------
      # Plain state vars, all four. PRD-006 Section 6: "the visible rows are an
      # rx.var over the loaded rows plus the filter state, so filtering never
      # re-reads the database" — these are that filter state, and `visible_rows`
      # below is that var. STORY-013 builds the controls that write them.
      #
      # Every default here is falsy, and that is a requirement rather than a
      # coincidence: sign_out() is reset(), and tests/test_admin_state.py:244
      # asserts every declared var restores to a falsy default, so a filter left
      # standing after a sign-out is caught. It is also why the register's
      # "timestamp, newest first" default is carried by sort_key == "" (which
      # sort_rows reads as the loaded order) rather than by a truthy default.
      selected_verdicts: list[str] = []
      search: str = ""
      sort_key: str = ""
      sort_descending: bool = False

      @rx.var
      def visible_rows(self) -> list[AuditRow]:
          """The rows the register renders: `rows` narrowed, then ordered.

          Two properties are load bearing.

          **No database read.** This is a synchronous getter over data already
          in state; it imports nothing from `app.db.database` and awaits
          nothing, so PRD-006 Section 6's "filtering never re-reads the
          database" is true by construction rather than by discipline. An async
          getter would be the shape a database-backed filter takes — Reflex
          supports one (AsyncComputedVar) and it is deliberately not used here.

          **All five dependencies are read off `self` in this body.** Reflex's
          auto-dependency tracker disassembles this function and records the
          attributes it loads from `self` (ComputedVar._deps); a module-level
          helper handed plain lists is invisible to it. Moving any of these
          five loads down into `filter_rows`/`sort_rows` would leave a var that
          silently stops updating — and the tracker's failure mode is a
          console.warn and an empty dependency set, not an exception. Keep the
          loads here; keep the logic there.
          """
          return sort_rows(
              filter_rows(self.rows, self.selected_verdicts, self.search),
              self.sort_key,
              self.sort_descending,
          )

      @rx.var
      def filters_active(self) -> bool:
          """Whether anything is narrowing the register right now.

          Sort is excluded: reordering the register does not remove a row, so
          an "active filter" that a clear action would undo is the verdict
          selection and the text, and only those. STORY-014's no-matches state
          is exactly `filters_active and not visible_rows`, and STORY-013's
          clear control shows against this.
          """
          return bool(self.selected_verdicts) or bool(self.search.strip())
  ```
  Points the implementation must not drift on:
  - Bare `@rx.var`, matching `state.py:33`. Do **not** pass `cache=False` — the caching default is what keeps Risk 5's per-keystroke re-evaluation off every unrelated state update, and `cache=False` additionally forbids dependency tracking (`reflex_base/vars/base.py:2890-2892`).
  - Do **not** pass `deps=[...]` while `auto_deps` stays on unless Task 4 shows a dependency is missed; explicit deps that drift from the body are worse than none.
  - Return type annotation `list[AuditRow]` is required — it is how Reflex types the Var the components will bind to.
- **Mirror**: `chat_ui/chat_ui/state.py:33-36` (`has_messages` — the codebase's only other computed var) and `chat_ui/chat_ui/admin_state.py:126-143` (the commented field block it sits beside)
- **Validate**:
  ```bash
  python -c "
  from chat_ui.chat_ui.admin_state import AdminState
  for n in ('selected_verdicts','search','sort_key','sort_descending'):
      assert n in AdminState.base_vars, n
  for n in ('visible_rows','filters_active'):
      assert n in AdminState.computed_vars, n
  print('ok')"
  grep -n "async def visible_rows\|cache=False" chat_ui/chat_ui/admin_state.py   # no output
  ```

### Task 4: Prove the auto-dependency set is what the AC needs

- **File**: none (verification)
- **Action**: verification only
- **Implement**: this is the step that catches the silent failure described in Task 3's docstring. `ComputedVar._deps` warns and returns an empty set when tracking fails, so a `visible_rows` that never updates would pass every other check in this plan. Read the tracked dependencies directly off the class and assert all five names are present.
- **Validate**:
  ```bash
  python -c "
  from chat_ui.chat_ui.admin_state import AdminState
  cv = AdminState.computed_vars['visible_rows']
  deps = cv._deps(objclass=AdminState)
  tracked = deps[AdminState.get_full_name()]
  for n in ('rows','selected_verdicts','search','sort_key','sort_descending'):
      assert n in tracked, (n, tracked)
  print('tracked:', sorted(tracked))"
  ```
  If any name is missing, the fix is to keep the `self.X` load in the getter body — not to reach for `deps=[...]` — and only if that fails do you add `deps=['rows','selected_verdicts','search','sort_key','sort_descending']` with `auto_deps=False`, recording why in the plan's report.

### Task 5: Add the four mutating handlers

- **File**: `chat_ui/chat_ui/admin_state.py`
- **Action**: UPDATE
- **Implement**: after `set_token_input` (`admin_state.py:145-147`), following its `@rx.event` shape. These are **state**, not controls — [[STORY-013]] is explicit that "no filtering logic belongs in the component", so the toggle and the direction flip live here.
  ```python
      @rx.event
      def set_search(self, text: str):
          self.search = text

      @rx.event
      def toggle_verdict(self, verdict: str):
          """Adds or removes one verdict from the selection.

          Reassigns the list rather than mutating it in place: Reflex marks a
          var dirty on assignment, and an in-place `.append()` on a list var can
          leave `visible_rows` serving its cached value.
          """
          if verdict in self.selected_verdicts:
              self.selected_verdicts = [
                  v for v in self.selected_verdicts if v != verdict
              ]
          else:
              self.selected_verdicts = [*self.selected_verdicts, verdict]

      @rx.event
      def sort_by(self, key: str):
          """Chooses an ordering, or reverses the one already chosen.

          Named `sort_by` rather than `set_sort_key` on purpose: the latter is
          the name Reflex would give the plain setter for `sort_key`, and this
          handler does more than set it — a reader who called it expecting a
          setter would not expect the direction to flip.
          """
          if key == self.sort_key:
              self.sort_descending = not self.sort_descending
              return
          self.sort_key = key
          # A newly chosen column starts in its natural order — newest first for
          # timestamp, A-Z for user, exceptions first for verdict.
          self.sort_descending = False

      @rx.event
      def clear_filters(self):
          """Restores the full window. Clears the filters only — not the sort,
          and never the rows: STORY-014's no-matches state offers this action,
          and an admin clearing a filter is not asking for a reload.
          """
          self.selected_verdicts = []
          self.search = ""
  ```
  **Scope note, stated rather than assumed.** The story assigns the *controls* to STORY-013 and the *state* here. These four handlers are state — STORY-013 AC 5 ("a clear action resets all filters") and AC 6 ("the active sort is visibly indicated; timestamp descending remains the default") both require a handler that STORY-013 forbids itself from writing logic for. They are therefore built here, and STORY-013 binds components to them.
- **Mirror**: `chat_ui/chat_ui/admin_state.py:145-147` (`set_token_input`)
- **Validate**:
  ```bash
  python -c "
  from chat_ui.chat_ui.admin_state import AdminState
  for h in ('set_search','toggle_verdict','sort_by','clear_filters'):
      assert h in AdminState.event_handlers, h
  print('ok')"
  ```

### Task 6: Drive the state directly and assert every AC

- **File**: `<scratchpad>/drive_visible_rows.py` (scratchpad only — the committed test file is [[STORY-006]])
- **Action**: CREATE (not committed)
- **Implement**: build an `AdminState(_reflex_internal_init=True)` the way `tests/test_admin_state.py:52-53` does, assign a hand-built `rows` list covering all four verdicts and at least the `a.torres` / `denied` / `#127` combination the ACs name, and assert:
  1. `visible_rows == rows` with every filter var at its default (AC 5's default ordering, and AC 6's empty selection passing everything).
  2. Setting `search = "127"` isolates the row whose `audit_id` is 127 (AC 3), and `search = "A.TORRES"` matches `a.torres` (case-insensitive), as does a model-name search against `model_used`.
  3. `selected_verdicts = ["denied"]` plus `search = "a.torres"` composes as AND and yields strictly fewer rows than either alone (AC 4).
  4. `selected_verdicts = []` with rows loaded yields all rows, not none (AC 6).
  5. `sort_by("user")`, `sort_by("verdict")` and `sort_by("timestamp")` each change the order; a second `sort_by` with the same key flips `sort_descending`; `sort_key = ""` and `sort_key = "timestamp"` produce identical lists (AC 5).
  6. **No database read**: patch every one of the ten functions in the `chat_ui.chat_ui.admin_state` namespace to raise, then evaluate `visible_rows` under every filter combination — nothing raises (AC 2). This is the assertion that actually proves AC 2; reading the source does not.
  7. `sign_out()` restores all four filter vars to their defaults alongside `rows` (AC 7), reusing the `_populate`-then-`base_vars` shape of `tests/test_admin_state.py:244-256`.
  8. `visible_rows` returns a new list and `state.rows` is unchanged in both order and identity after sorting and filtering.
- **Mirror**: `tests/test_admin_state.py:52-95` (the `_state`, `_authenticate`, `_sign_out`, `_populate` helpers)
- **Validate**: `python <scratchpad>/drive_visible_rows.py` → all assertions pass

### Task 7: Confirm nothing else moved

- **File**: none (verification)
- **Action**: verification only
- **Implement**: run the full suite. `tests/test_admin_state.py:244-256` is the one already-green test this story can break — four new vars must all restore to falsy defaults under `reset()`. Confirm `app/` and `admin_formatting.py` are untouched.
- **Validate**:
  ```bash
  python -m pytest tests/ -q
  git diff main --stat -- app/                                   # empty
  git diff --stat -- chat_ui/chat_ui/admin_formatting.py         # empty
  git diff --name-only                                           # only chat_ui/chat_ui/admin_state.py
  ```

---

## End-to-End Tests

- [ ] Seed or point at `harness_ai.db`, authenticate an `AdminState` with the configured token, `await load()`, then read `visible_rows` with defaults → identical list to `state.rows`, same order, newest first.
- [ ] Set `search` to the `audit_id` of a known row → `visible_rows` narrows to the rows whose id contains that text, including that row (the PRD Section 5 story-5 loop: a user quotes `#127` from the chat footer, the admin types `127`).
- [ ] Set `selected_verdicts = ["denied"]` and `search` to a user who has a denied row → `len(visible_rows)` is the intersection, strictly ≤ either filter alone.
- [ ] Set `selected_verdicts = []` with a hundred rows loaded → `len(visible_rows) == len(rows)`; the empty selection is not an empty register.
- [ ] Call `sort_by("verdict")` → the denied and fault rows lead; call it again → `sort_descending` is True and cleared rows lead.
- [ ] Time a `visible_rows` evaluation over a full 100-row window under a 3-character search — it must be sub-millisecond (Risk 5's premise: the mitigation is that the data is in state, and there is no per-keystroke round trip to measure).
- [ ] With every `app/db/database.py` read patched to raise, evaluate `visible_rows` under a filter → no exception, proving the var performs no read.
- [ ] `sign_out()` after filtering → `selected_verdicts == []`, `search == ""`, `sort_key == ""`, `sort_descending is False`, and `rows == []`.

---

## Validation

```bash
python -c "import chat_ui.chat_ui.admin_state as m; assert set(m._SORT_RANKS) == set(m.SORT_KEYS); print('ok')"
grep -n "from app.db.database import" -A 20 chat_ui/chat_ui/admin_state.py | grep -c "insert_audit_log"   # 0 — the read-only import survives
grep -n "cache=False\|async def visible_rows" chat_ui/chat_ui/admin_state.py                              # no output
grep -n '"cleared"\|"held"\|"denied"\|"fault"' chat_ui/chat_ui/admin_state.py                             # no output — VERDICTS imported, not re-declared
python <scratchpad>/drive_visible_rows.py          # every AC assertion passes, including the no-read proof
python -m pytest tests/ -q                         # full suite; test_sign_out_clears_every_declared_var still green
git diff main --stat -- app/                       # must be empty
```

No frontend lint step applies (`chat_ui` is Reflex/Python, no JS package) and no server start is needed — this story adds no route, component or FastAPI wiring.

---

## Risks + Mitigations

**1. A truthy default breaks the sign-out invariant.** The obvious spelling of "default to timestamp, newest first" is `sort_key: str = "timestamp"` and `sort_descending: bool = True` — and both would fail `tests/test_admin_state.py:244-256`, which asserts every declared var resets to a falsy value. *Mitigation*: the default ordering is expressed as the **absence** of a choice. `sort_key = ""` falls through `_SORT_RANKS.get(...)` to `SORT_TIMESTAMP`, whose rank is the row's position in the loaded list, which is already `ORDER BY timestamp DESC`. So `""` and `"timestamp"` render the same register, every default stays falsy, and AC 5's "the default is the order `list_audit_logs` returned" is literally true. Written down here because a later reader will see `sort_key: str = ""` and reach for the "obvious" fix.

**2. Auto-dependency tracking fails silently.** `ComputedVar._deps` catches every exception from `DependencyTracker`, emits a `console.warn` and returns **no** dependencies — a `visible_rows` that computes correctly once and then never updates. Nothing in a diff shows this, and a filter that does nothing looks like a broken component. *Mitigation*: all five `self.X` loads stay in the getter's own body (the tracker follows `self` attribute access, `self`-method calls and comprehensions, but not a free function's arguments), and Task 4 asserts the tracked set by name rather than trusting it.

**3. Mutating the state's own row list from inside a computed var.** `list.sort()` or a `.append()` on `self.rows` inside `visible_rows` would rewrite the source of truth as a side effect of rendering. *Mitigation*: `filter_rows` returns `list(rows)` even on the no-filter path, and `sort_rows` uses `sorted(...)`, never `.sort()`. Task 6 assertion 8 checks `state.rows` is unchanged in order and identity after both.

**4. An in-place list mutation misses the dirty mark.** `self.selected_verdicts.append(v)` is the natural way to write `toggle_verdict`, and Reflex marks vars dirty on assignment. *Mitigation*: `toggle_verdict` rebuilds and reassigns the list; the reason is stated in its docstring so the "simplification" is not made later.

**5. Every keystroke re-evaluates the var over the full row list** (PRD Risk 5, verbatim). *Mitigation*: unchanged from the PRD, and deliberately not pre-optimized — 100 rows is the hard ceiling (`REGISTER_ROW_LIMIT`, and `list_audit_logs` is the only listing query), the data is already in state, and `@rx.var`'s default `cache=True` means the var recomputes only when one of its five dependencies actually changes, not on every state update on the page. If it proves heavy in practice the fix is debouncing the input in [[STORY-013]] — "a UI-local change requiring nothing under `app/`". A database-side filter is explicitly out of scope (PRD Section 4).

**6. The empty verdict selection read as "no rows".** `row.verdict not in []` is `True` for every row, so a naive predicate that drops the `if verdicts and` guard empties the register the moment the page loads — and it would read as "nothing recorded", the exact misreading PRD Section 4 and [[STORY-014]] forbid. *Mitigation*: AC 6 is its own assertion in Task 2's inline check and Task 6 assertion 4, not a property inferred from the others.

**7. Substring matching on `audit_id` over-matches.** Typing `127` also matches `#1270` and `#3127`. *Mitigation*: accepted, and it is the right behaviour for a free-text field — the AC says `127` "isolates the row whose `audit_id` is 127" in a hundred-row window where a second id containing `127` is unlikely, and an exact-match-only rule would break the same field's use for partial user and model names. Recorded so it is not later "fixed" into an equality test that stops matching `a.tor`.

**8. Scope creep into STORY-013.** The four mutating handlers could be read as controls work. *Mitigation*: stated explicitly in Task 5 rather than left implicit — STORY-013's own technical note says "no filtering logic belongs in the component", so the toggle, the direction flip and the clear must live in state, and this is the state story. No component, no copy string and no theme token is added here.

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `AdminState`, when the filter state is inspected, then it holds a verdict multi-select (`selected_verdicts`), a free-text `search` and a `sort_key` / `sort_descending` pair — all plain state vars.
- [ ] Given `visible_rows`, when it is defined, then it is a computed var over `rows` plus the filter and sort state, and evaluating it performs **no** database read.
- [ ] Given a free-text value, when it is applied, then it matches case-insensitively against `user_id`, `model_used` and `audit_id`, and typing `127` isolates the row whose `audit_id` is 127 (PRD Section 5, story 5).
- [ ] Given a verdict multi-select with `denied` selected and the text `a.torres`, when both are applied, then the two filters compose as AND and the row count narrows accordingly.
- [ ] Given `sort_key` set to timestamp, user, or verdict, when the register reads `visible_rows`, then the ordering changes and the default is timestamp, newest first — the order `list_audit_logs` returned.
- [ ] Given an empty verdict selection, when `visible_rows` is evaluated, then all rows pass the verdict filter — an empty selection means "no verdict filter", not "no rows".
- [ ] Given the filter and sort state, when `sign_out()` runs, then they are reset along with the rows.
- [ ] All tasks completed
- [ ] Frontend lint passes (N/A — no JS package in `chat_ui`)
- [ ] Backend server starts without error (`python -c "import app.main"` and `python -c "import chat_ui.chat_ui.admin_state"` both clean)
- [ ] Follows existing patterns (`state.py:33-36`'s bare `@rx.var`, `admin_state.py:145-147`'s explicit setter, `admin_formatting.py`'s module-level pure helpers, `_READS`' dispatch-table-with-a-reason)
