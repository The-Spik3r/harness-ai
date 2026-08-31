---
story: STORY-018
prd: PRD-006
slug: render-invariant-tests
title: "Render invariant tests: no previews in output, no tint or stray colour on the console"
type: technical
complexity: MEDIUM
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Render invariant tests: no previews in output, no tint or stray colour on the console

## Summary

Two invariants that a review would have to catch by eye — the previews never
reaching the screen (Risk 2) and the console never painting outside its four
verdict inks (Risk 6) — become assertions over what the browser actually
receives. Everything shipped so far checks these **per component**:
`tests/test_register.py` collects the hexes in `str(register())`,
`tests/test_summary.py` does the same for the sheet, and
`tests/test_admin_palette.py` greps the admin modules for `TINT_` and the two
chat-only inks. None of them renders a *page*, and none has ever put a row from
a real database in front of a real component. This story closes both gaps with
one new file, `tests/test_render_invariants.py`, which seeds a temporary SQLite
database with rows carrying sentinel previews, drives `AdminState.authenticate()`
and `AdminState.load()` for real, and then inspects the two things that together
*are* the rendered output: the compiled page template from
`admin_page(register(), ...)` / `admin_page(summary(), ...)`, and the JSON state
payload the frontend binds into it. Neither sentinel may appear in either. Two
smaller edits follow: `tests/test_admin_palette.py` gains the hard-coded-hex
guard AC 5 asks for, globbed over every admin module rather than written per
file, and `tests/test_contrast.py` gains the exhaustive ink x ground matrix AC 6
asks for. No application file changes — this is a test-only story.

## User Story

As an integrating developer
I want the unrendered previews and the no-cards palette asserted by tests
So that both fail a test run rather than a review (PRD Risks 2 and 6).

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-018-render-invariant-tests.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only — no file under `app/` or `chat_ui/` changes |
| Story | STORY-018 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design | The palette refusal this story enforces *is* the skill's "spend your boldness in one place" applied to PRD Section 6.1: four verdict inks, no tint, no accent. The allowed set is derived from `theme.py` by name so the guard tracks the direction rather than a snapshot of it. | Task 1, Task 2, Task 3 |
| reflex-docs | `AdminState.dict()`, `str(component)` and `rx.el.style` are Reflex APIs the probe depends on; `chat_ui/AGENTS.md` requires each to be verified against the skill rather than recalled. Their behaviour is confirmed by prototype (see Risks), but the doc check still stands before writing the file. | Task 1 |
| reflex-process-management | Not needed, and named so the omission is deliberate. Nothing here runs or restarts the app; the probe imports the modules in a subprocess and never starts a server. | — |

Story frontmatter carries `skills: []`; the two above are pulled in because
`chat_ui/AGENTS.md` and PRD Section 6.1 name them for exactly this material.

---

## Patterns to Follow

### The subprocess probe — how every admin component test reaches rendered output

```python
# SOURCE: tests/test_register.py:59-72, 316-341
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

@pytest.fixture(scope="module")
def probe():
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
        },
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"register probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])
```

The subprocess is not ceremony: the admin modules import each other as
`chat_ui.components...`, which resolves only under the `chat_ui/` PYTHONPATH,
and putting the inner package on `sys.path` in-process breaks every other test
module. Same fixture shape, same env defaults, one JSON object on the last
stdout line.

### The allowed colour set — derived from theme.py, never copied

```python
# SOURCE: tests/test_register.py:162-183
VERDICT_INKS = {
    "INK_CLEAR": theme.INK_CLEAR,
    "INK_HELD": theme.INK_HELD,
    "INK_DENIED": theme.INK_DENIED,
    "INK_FAULT": theme.INK_FAULT,
}
ALLOWED_COLOURS = {value.upper() for value in VERDICT_INKS.values()} | {
    theme.PAPER.upper(), theme.CARD.upper(), theme.INK.upper(),
    theme.MUTE.upper(), theme.RULE.upper(), theme.RULE_SOFT.upper(),
    theme.SPINE.upper(), theme.HOVER.upper(),
}
```

Story Technical Note: "Collect the allowed colour set from `theme.py` by name,
not by copying hex literals into the test." That is exactly this block, and the
new file imports the same names rather than restating the values.

### Seeding a database for a test

```python
# SOURCE: tests/test_db.py:31-36
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
```

In the probe this becomes `tempfile.mkdtemp()` plus a direct
`settings.DATABASE_URL = ...` assignment, because the subprocess has no
`tmp_path` and no `monkeypatch` — and it is a throwaway process, so there is
nothing to restore.

### Driving the state handlers directly

```python
# SOURCE: tests/test_admin_state.py:114-130
def _state() -> AdminState:
    return AdminState(_reflex_internal_init=True)

def _authenticate(state: AdminState, token: str):
    state.token_input = token
    return type(state).event_handlers["authenticate"].fn(state)

async def _load(state: AdminState):
    return await type(state).event_handlers["load"].fn(state)
```

### The contrast helper this story extends rather than duplicates

```python
# SOURCE: tests/test_contrast.py:33-37, 71-84
def contrast(fg: str, bg: str) -> float: ...

_INK_ON_HOVER = [("INK_CLEAR", theme.INK_CLEAR), ...]

@pytest.mark.parametrize("name,ink", _INK_ON_HOVER)
def test_verdict_ink_is_readable_on_the_row_hover(name, ink):
    assert contrast(ink, theme.HOVER) >= AA_NORMAL, name
```

Story Technical Note: "Extend `tests/test_contrast.py` rather than duplicating
its `contrast()` helper." Task 3 adds one parametrized matrix to this file and
touches nothing above it.

### Note on the two precedents the story names

`tests/test_pii_badge.py` and `tests/test_success_metadata_footer.py` are cited
in the story as "the existing precedent for asserting over a rendered Reflex
component". They are not — both assert over `copy` constants and `ChatMessage`
fields, and neither renders anything. The real precedent for reaching rendered
output is the subprocess probe in `tests/test_register.py`,
`tests/test_summary.py` and `tests/test_admin_shell.py`, and the story's actual
instruction — "reuse that approach rather than inventing a second one" — is
honoured by using it. Recorded here so the discrepancy is a decision rather than
an oversight.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_render_invariants.py` | CREATE | The seeded-database, whole-page probe: AC 1, AC 2, AC 3, AC 4 |
| `tests/test_admin_palette.py` | UPDATE | AC 5: a hard-coded hex in any admin module fails, with a self-test proving the guard bites |
| `tests/test_contrast.py` | UPDATE | AC 6: every ink x ground pairing the console introduced clears `AA_NORMAL` |

Nothing under `app/` and nothing under `chat_ui/` is touched — which is also
what STORY-020 will assert.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `tests/test_render_invariants.py` — the seeded whole-console probe

- **File**: `tests/test_render_invariants.py`
- **Action**: CREATE
- **Implement**:

  A module docstring stating what "rendered output" means here and why, in the
  house style of `tests/test_register.py`'s: a Reflex page compiles to a
  *template* that references state vars plus a *payload* the frontend binds into
  it, so a string search of the template alone would find no seeded value at all
  and would pass vacuously. The assertion is therefore over both halves, and the
  positive controls below are what keep it honest.

  One module-scoped `probe` fixture, shaped exactly like
  `tests/test_register.py`'s, running `_CHECK_SCRIPT` in a subprocess with
  `cwd=chat_ui/`, `PYTHONPATH=[chat_ui, repo root]`, and the `ADMIN_TOKEN` /
  `OPENROUTER_API_KEY` defaults. The script:

  1. `settings.DATABASE_URL = f"sqlite:///{tempfile.mkdtemp()}/console.db"`,
     then `init_db()`.
  2. `insert_audit_log(...)` for **four** rows, one per verdict — a cleared row,
     a `was_duplicate_blocked=True` row, a `suspicious_pattern="ignore previous"`
     row, and a `success=False, error_message=...` row — so every `rx.match` arm
     has real data behind it. Every row carries a distinct sentinel in both
     preview columns (`SENTINEL-PROMPT-<n>-b3f19a`, `SENTINEL-RESPONSE-<n>-7c02de`)
     and a recognisable `user_id` (`a.torres`) that serves as the positive
     control.
  3. Build `AdminState(_reflex_internal_init=True)`, set `token_input` to
     `settings.ADMIN_TOKEN`, call the `authenticate` handler, then
     `asyncio.run(...)` the `load` handler.
  4. Emit, as JSON:
     - `payload`: `json.dumps(state.dict(), default=str)` — the state as the
       frontend receives it, computed vars included.
     - `register_page` / `summary_page`: `str(admin_page(register(), VIEW_REGISTER))`
       and `str(admin_page(summary(), VIEW_SUMMARY))`, with the two view
       constants imported from `admin_shell`, never retyped.
     - `stylesheet`: `str(rx.el.style(theme.GLOBAL_CSS))`, so the test can strip
       the shared stylesheet from a page and prove the strip happened.
     - `row_fields`: the `AuditRow` field names, from `AuditRow.__fields__`.
     - `row_count`, `verdicts`: `len(state.rows)` and the four derived verdicts,
       as the probe's own positive control.

  Then the tests:

  - **AC 1 — the previews are nowhere.** Parametrized over the eight sentinels x
    three surfaces (`payload`, `register_page`, `summary_page`): the sentinel
    appears in none of them.
  - **AC 1 positive control (non-vacuity).** `row_count == 4`, the four verdicts
    are `{cleared, held, denied, fault}`, `"a.torres" in payload`, and
    `"visible_rows" in payload`. Without these, the sentinel assertions would
    pass on an empty state and prove nothing. This is the single most important
    test in the file and its docstring should say so.
  - **AC 2 — the boundary.** `"prompt_preview" not in row_fields` and
    `"response_preview" not in row_fields`, plus the complementary claim that
    the fields the register *does* read (`verdict`, `user_id`, `audit_id`, ...)
    are all present — a projection that dropped everything would also pass the
    negative.
  - **AC 3 — no tint.** For each of the five `TINT_*` tokens, its value appears
    in neither page. Read `getattr(theme, name)` by name, not by literal.
  - **AC 4 — the palette.** For each page: strip `probe["stylesheet"]` from the
    page string (asserting the strip shortened it, so a changed stylesheet
    representation fails loudly instead of silently disarming the test), collect
    every `#RRGGBB` with `re.findall(r"#[0-9a-fA-F]{6}\b", ...)`, and assert the
    set is a subset of `ALLOWED_COLOURS` — the four verdict inks plus `PAPER`,
    `CARD`, `INK`, `MUTE`, `RULE`, `RULE_SOFT`, `SPINE`, `HOVER`, all read from
    `theme.py` by name.
  - **AC 4 — `INK_UPSTREAM`, and the one exception.** `theme.INK_UPSTREAM` does
    not appear in either stylesheet-stripped page; and, as a pinned exception, it
    *does* appear in `probe["stylesheet"]` — the global `:focus-visible` outline
    `tests/test_admin_palette.py`'s docstring records for this story. The
    exception is asserted rather than merely excluded, so removing the focus ring
    fails here, and an admin component adopting the blue also fails here.
  - **AC 4 — `INK_SELF`.** Asserted **by name over the admin sources**, not by
    value: `theme.INK_SELF == theme.INK == "#14181C"`, so no hex search can tell
    them apart. `tests/test_admin_palette.py::test_no_admin_module_references_a_chat_only_ink`
    already carries this claim; this file adds a one-line test asserting the two
    tokens share a value and pointing at the palette test as the guard, so the
    reason a value-based check is impossible is recorded where someone would
    otherwise try to add one.

- **Mirror**: `tests/test_register.py:56-72` (module layout and the probe
  fixture), `tests/test_register.py:316-341` (subprocess env),
  `tests/test_db.py:31-36` (seeding), `tests/test_admin_state.py:114-130`
  (driving the handlers).
- **Validate**: `python -m pytest tests/test_render_invariants.py -q`

### Task 2: the hard-coded-hex guard in `tests/test_admin_palette.py` (AC 5)

- **File**: `tests/test_admin_palette.py`
- **Action**: UPDATE
- **Implement**:

  `register.py` and `summary.py` each carry a `test_no_literal_hex_colour` over
  their own source, and `admin_shell.py` carries one too — but `admin_state.py`,
  `admin_copy.py`, `admin_formatting.py` and `admin_models.py` carry none, and a
  file added tomorrow carries none by default. AC 5 says "any admin component",
  so the guard belongs on the glob that already defines what an admin module is.

  Add to the existing `ADMIN_MODULE_PATTERNS` section:

  - `test_no_admin_module_writes_a_literal_hex` — parametrized over
    `_admin_modules()`, asserting `_literal_hexes(source)` is empty, with the
    failure message naming the file and the offending hexes. Parametrized per
    module, not one aggregate assertion, so the failure names the file that
    drifted.
  - `test_the_hex_guard_detects_a_hex` — the guard's own detector applied to a
    synthetic source string containing `background_color="#FF00AA"`, asserting it
    is flagged. AC 5 is a claim about what *fails*, and the only way to check a
    guard bites without editing a shipped component is to run its detector over a
    sample. Factor the detector into a module-level
    `_literal_hexes(source: str) -> list[str]` so both tests call the same code
    and the self-test cannot drift from the guard.
  - Confirm `ADMIN_MODULE_PATTERNS`' `components/admin_*.py` entry actually
    covers `admin_shell.py` before relying on it — the whole guard rests on that
    glob, and `test_admin_modules_are_discoverable` only proves the glob matches
    *something*. If any admin module is unmatched, add its pattern.
  - Update the module docstring: the "One deliberate exception, recorded for
    STORY-018" paragraph should now say where STORY-018 asserted it
    (`tests/test_render_invariants.py`), so the note stops being a forward
    reference.

- **Mirror**: `tests/test_admin_palette.py:56-62` (`_admin_modules`),
  `tests/test_register.py:456-464` (`test_no_literal_hex_colour`).
- **Validate**: `python -m pytest tests/test_admin_palette.py -q`

### Task 3: the console's contrast matrix in `tests/test_contrast.py` (AC 6)

- **File**: `tests/test_contrast.py`
- **Action**: UPDATE
- **Implement**:

  The file already covers the inks on `PAPER`, on their tints, on `HOVER`, and
  the neutral pairs including the gate's inverted button on `MUTE`. What it does
  not do is state the console's pairings *as a set*, which is what AC 6 asks
  for — every pairing the console introduced, not a list someone remembered to
  extend.

  Add one block below the existing ones:

  - `_CONSOLE_INKS` — the six colours the console draws text in, by name:
    `INK`, `MUTE`, `INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FAULT`.
  - `_CONSOLE_GROUNDS` — the three grounds it draws them on, by name: `PAPER`
    (the page and the fault panel), `CARD` (the gate panel and the masthead) and
    `HOVER` (a hovered register row).
  - `test_every_console_pairing_is_readable`, parametrized over the full
    18-entry cross product, asserting `contrast(ink, ground) >= AA_NORMAL`.

  A cross product over-asserts — the register never paints `INK_HELD` on the
  gate's card — and that is deliberate: it is a superset of what ships, it needs
  no maintenance when a component moves an ink onto a ground it did not use
  before, and all eighteen clear the floor today (verified: the tightest is
  `MUTE` on `PAPER` at 4.63:1, the same pairing the existing neutral block
  already flags as the tightest in the file). Say so in the docstring, including
  that value, so a future token change that drops one below 4.5 reads as the real
  regression it is rather than as the matrix being too strict.

  The two inverted-button pairs (`PAPER` on `INK`, `PAPER` on `MUTE`) stay where
  they are in `test_neutral_pairs_are_readable`: they are specific pairings, not
  a matrix, and moving them would churn a passing test for nothing.

- **Mirror**: `tests/test_contrast.py:71-84` (the `_INK_ON_HOVER` block — same
  shape, same parametrize idiom, same `contrast()` helper).
- **Validate**: `python -m pytest tests/test_contrast.py -q`

### Task 4: the full suite, and nothing else changed

- **File**: — (verification only)
- **Action**: none
- **Implement**: Run the whole suite and confirm the three files above are the
  only ones changed. PRD Section 11's quality bar requires
  `tests/test_audit_router.py`, `tests/test_stats_router.py`,
  `tests/test_admin_auth.py`, `tests/test_db.py`,
  `tests/test_route_reservations.py` and `tests/test_chat_state.py` to pass
  **unmodified**; this story must not have needed to touch any of them.
- **Validate**:
  ```bash
  python -m pytest -q
  git status --porcelain          # only the three test files
  git diff main --stat -- app/    # empty
  ```

---

## End-to-End Tests

Executed by `/implement` after the tasks:

- [ ] `python -m pytest tests/test_render_invariants.py -q` — green, and the
      probe fixture did not `pytest.fail` (a crashed subprocess is reported as a
      failure, never as a skip).
- [ ] The non-vacuity test is genuinely load-bearing: temporarily point the
      probe's seeding at zero rows and confirm the preview assertions still pass
      while the positive-control test **fails**. Revert. This is the one check
      that proves the file is not a tautology; run it once by hand and record the
      outcome in the story report.
- [ ] The palette guard bites: temporarily add `background_color="#FF00AA"` to
      `chat_ui/chat_ui/components/summary.py` and confirm both
      `tests/test_admin_palette.py` (AC 5) and `tests/test_render_invariants.py`'s
      AC 4 subset assertion fail. Revert and re-run to confirm green. AC 5 is
      stated as a failure, so it is verified by producing one.
- [ ] `python -m pytest -q` — the full suite green, with the PRD-001/003/004 test
      files untouched.
- [ ] `git diff main --stat -- app/` prints nothing.

---

## Validation

```bash
python -m pytest tests/test_render_invariants.py tests/test_admin_palette.py tests/test_contrast.py -q
python -m pytest -q
git diff main --stat -- app/
git status --porcelain
```

---

## Acceptance Criteria

(Copied from story `STORY-018`)

- [ ] Given a seeded database whose rows carry distinctive `prompt_preview` and `response_preview` strings, when the register is rendered, then neither string appears anywhere in the rendered output.
- [ ] Given `AuditRow`, when its attributes are enumerated, then it has no preview field — the boundary assertion complementing the render assertion (Risk 2).
- [ ] Given the register and the summary, when their rendered output is inspected, then no `TINT_*` value from `chat_ui/chat_ui/theme.py` appears (Risk 6).
- [ ] Given the console's rendered output, when its colour values are collected, then every one resolves to a token in `theme.py` and falls within the allowed set: the four verdict inks plus the ground tokens — no `INK_UPSTREAM`, no `INK_SELF`, no colour outside `theme.py`.
- [ ] Given a new hard-coded hex added to any admin component, when the suite runs, then the palette test fails.
- [ ] Given `tests/test_contrast.py`, when the suite runs, then every pairing the console introduced clears `AA_NORMAL`.
- [ ] All tasks completed
- [ ] Full suite green, PRD-001/003/004 test files unmodified
- [ ] No file under `app/` or `chat_ui/` changed
- [ ] Follows existing patterns

---

## Risks + Mitigations

**1. A string search over a compiled template proves nothing on its own.**
Reflex compiles a page to a template that references state vars; seeded values
live in the payload, not the template. A test that seeds a database and then
greps `str(register())` for the sentinel passes whether or not the boundary
holds — and would keep passing if `AuditRow` grew a preview field tomorrow.
*Mitigation*: assert over the payload (`state.dict()`) **and** the template, and
make the positive control — four rows loaded, four verdicts derived, `a.torres`
present in the payload — a first-class test whose failure is the signal that the
file has gone vacuous. Prototyped: with one seeded row the payload is ~2.9KB,
contains `a.torres` and `visible_rows`, and contains neither sentinel.

**2. `INK_UPSTREAM` is in every admin page's output, legitimately.**
`theme.GLOBAL_CSS` sets `:focus-visible { outline: 2px solid #34567F }` and
`admin_page()` owns the stylesheet, so a naive hex sweep of a page finds the
chat-only blue and AC 4 fails on a shared accessibility affordance.
*Mitigation*: strip `str(rx.el.style(theme.GLOBAL_CSS))` from the page before
collecting hexes, assert the strip actually shortened the string, and pin the
exception with its own test asserting the blue *is* in the stylesheet.
Prototyped: after stripping, the register page's hexes are exactly the four inks
plus `INK`, `MUTE`, `RULE`, `RULE_SOFT`, `PAPER`, `CARD`, `HOVER`, and the
summary page's are a subset of the same. Stripping `theme.GLOBAL_CSS` itself
does **not** work — Reflex escapes the string on the way into the style element —
which is why the probe emits the rendered stylesheet rather than the raw
constant. `tests/test_admin_palette.py`'s docstring predicted this failure for
this story; the plan meets it as a decision.

**3. `INK_SELF` cannot be excluded by value.**
`INK_SELF == INK == "#14181C"`. Any hex-based "no `INK_SELF`" assertion either
fails on every page (because `INK` is everywhere) or is written to pass and means
nothing.
*Mitigation*: the claim stays where it can be true — `tests/test_admin_palette.py`'s
by-name source grep — and the new file records why with a one-line test on the
token identity. Written down so the impossible check is not attempted later.

**4. The probe imports the app config, which requires environment.**
`admin_state` imports `app.config.settings`, where `ADMIN_TOKEN` and
`OPENROUTER_API_KEY` are required fields; a bare subprocess raises at import.
*Mitigation*: the same env defaults `tests/test_register.py` and
`tests/test_admin_shell.py` already pass (`test-token`, `test-key`), and the gate
is driven with `settings.ADMIN_TOKEN` rather than a retyped literal.

**5. The probe writes a database.**
`init_db()` against the default `sqlite:///harness_ai.db` would seed sentinel
previews into the developer's real audit log.
*Mitigation*: `settings.DATABASE_URL` is set to a `tempfile.mkdtemp()` path as
the **first** statement after the config import and before any database call, and
the process is a throwaway. This is the reason the seeding happens inside the
subprocess rather than in a pytest fixture: nothing in the parent process ever
touches a database.

**6. Cross-product contrast assertions could over-constrain a future palette.**
Eighteen pairings, some of which no component draws, would block a token change
that is fine on the pairings that ship.
*Mitigation*: all eighteen clear AA today with margin (tightest 4.63:1), the
docstring records that number, and the set is small enough to narrow
deliberately if a real design change ever collides with it. The alternative — a
hand-maintained list of the pairings that ship — rots the first time a component
moves an ink, which is exactly the drift Risk 6 is about.
