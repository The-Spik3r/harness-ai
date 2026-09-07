---
story: STORY-020
prd: PRD-008
slug: rail-design-guards
title: "Palette-drift and contrast assertions so the sidebar default fails a test, not a review"
type: TECHNICAL
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-07
---

# Plan: Palette-drift and contrast assertions so the sidebar default fails a test, not a review

## Summary

Close PRD-008 Risk 6 by turning Section 6.1's four refusals — no `TINT_*`, no verdict ink, no radius beyond `theme.RADIUS`, no colour outside the eight ground tokens — into parametrized assertions over the rail's *compiled* output, then prove the guard bites by adding a `TINT_HELD` fill to the active row, watching the suite go red, and removing it. No production code changes. `tests/test_session_rail.py` already carries the subprocess build probe and already collects `hexes` and `radii`; STORY-018 wrote its module docstring explicitly handing these guards to this story ("**The design guards are STORY-020's** ... That story extends this file rather than replacing it"), so the work is an extension of that file plus a rail pairing block in `tests/test_contrast.py` and one source-side test in `tests/test_copy.py`.

## User Story

As a maintainer
I want the rail's design refusals enforced by the suite
So that the drift toward a rounded, filled, accented sidebar is caught by CI rather than by whoever happens to review the pull request.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-020-rail-design-guards.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 6.1, Section 11 (Quality indicators), Section 12 Phase 4, Risk 6

## Metadata

| Field | Value |
|-------|-------|
| Type | TECHNICAL |
| Complexity | LOW |
| Systems Affected | Test suite only (`tests/`) — no application code |
| Story | STORY-020 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **frontend-design** (`.agents/skills/frontend-design/SKILL.md`) | Its calibration paragraph is what these assertions encode: the three AI-default looks "are legitimate for some briefs, but they are defaults rather than choices, and they appear regardless of subject." The rail's refusals (no fill, no pill, no accent) are the concrete form of that rule for this surface, and Section 6.1 pins them. The skill also supplies the *"where the brief pins down a visual direction, follow it exactly"* rule that makes these checkable rather than a matter of taste. | Tasks 1–6 (every guard's docstring cites the refusal it encodes), Task 7 |
| **frontend-design** — *"structural devices should encode something true about the content"* | The spine is the one place boldness is spent; the guards exist so nothing joins it. Quoted in the AC 3 radius guard's rationale. | Task 3 |

No other `SKILL.md` exists under `.agents/skills/` (the directory holds `frontend-design` only), and no skill restricts tooling for this story. `reflex-docs` is not listed on this story and is not needed: the render mechanism is already built and proven by STORY-018.

---

## Patterns to Follow

### The guard mechanism — a subprocess build probe, already in place

The story's technical note says to follow whatever `tests/test_admin_palette.py` uses "rather than inventing a second way to inspect rendered output." That file is a **source grep**; its rendered-output counterpart is `tests/test_render_invariants.py`, and the rail's own version of both already exists in `tests/test_session_rail.py`. Use it — do not add a third mechanism.

```python
# SOURCE: tests/test_session_rail.py:172-178 (inside _CHECK_SCRIPT, runs in the subprocess)
# Every colour the rail actually renders.
result["hexes"] = sorted(set(re.findall(r"#[0-9a-fA-F]{6}\b", rendered)))
result["radii"] = sorted(set(re.findall(r'\["borderRadius"\] : "([^"]+)"', rendered)))
```

```python
# SOURCE: tests/test_session_rail.py:180-192
@pytest.fixture(scope="module")
def probe() -> dict:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(_PYTHONPATH))
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"probe crashed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])
```

### Parametrized per-token guards, so a failure names the token

```python
# SOURCE: tests/test_render_invariants.py:388-401
@pytest.mark.parametrize("name", TINT_NAMES)
@pytest.mark.parametrize("page", PAGES)
def test_no_tint_reaches_either_page(probe, page, name):
    assert not probe["errors"], probe["errors"]
    value = getattr(theme, name).upper()
    assert value not in probe[page].upper(), name
```

### The allowed set read from `theme.py` by name, never copied as literals

```python
# SOURCE: tests/test_render_invariants.py:112-126
# Everything the console may paint: the four inks plus the ground tokens. Read
# from theme.py by name, never copied as literals — a token retuned in theme.py
# retunes this assertion in the same edit, which is the whole point of the
# single-file guarantee theme.py's docstring makes.
ALLOWED_COLOURS = {value.upper() for value in VERDICT_INKS.values()} | {
    theme.PAPER.upper(), theme.CARD.upper(), theme.INK.upper(), ...
}
```

### The detector self-test — how "watched failing" is kept true after the violation is removed

```python
# SOURCE: tests/test_admin_palette.py:148-158
def test_the_hex_guard_detects_a_hex():
    """The guard, watched failing. ... a guard is only worth what its detector
    catches. Running that detector over a sample is how the claim is checked
    without editing a shipped module."""
    sample = 'rx.box(background_color="#FF00AA", color=theme.INK)'
    assert _literal_hexes(sample) == ["#FF00AA"]
    assert _literal_hexes("rx.box(color=theme.INK)") == []
```

### A value-collision recorded as a test, not as a comment

```python
# SOURCE: tests/test_render_invariants.py:428-443
def test_ink_self_cannot_be_excluded_by_value():
    """Why AC 4's "no `INK_SELF`" is not asserted here as a hex. ...
    Recorded as a test rather than a comment so that a future attempt to add the
    value check finds the reason before writing it."""
    assert theme.INK_SELF == theme.INK
```

### Contrast pairings as a set, not a hand-maintained list

```python
# SOURCE: tests/test_contrast.py:114-155
_CONSOLE_INKS = (("INK", theme.INK), ("MUTE", theme.MUTE), ...)
_CONSOLE_GROUNDS = (("PAPER", theme.PAPER), ("CARD", theme.CARD), ("HOVER", theme.HOVER))

@pytest.mark.parametrize("ink_name,ink,ground_name,ground", [...cross product...])
def test_every_console_pairing_is_readable(ink_name, ink, ground_name, ground):
    """A cross product over-asserts ... and that is the point. It is a superset
    of what ships, so it needs no edit when a component moves an ink onto a
    ground it had not used before, which is exactly the drift a hand-maintained
    list misses."""
    assert contrast(ink, ground) >= AA_NORMAL, f"{ink_name} on {ground_name}"
```

### Docstring-excluded source string extraction (needed for AC 8 in `test_copy.py`)

```python
# SOURCE: tests/test_session_rail.py:81-115
def _docstring_nodes(tree: ast.AST) -> set:
    """Every `ast.Constant` that is a docstring, by identity.
    ... the assertions below are about *code*, and the prose has to be excluded
    rather than the prose rewritten to dodge a grep."""
```

---

## Exploration Findings

These four came out of reading the codebase and running the current suites, and each one changes what the implementation must do. They are the reason this plan is not "write eight asserts".

**1. `theme.INK_SELF == theme.INK == "#14181C"`, so AC 2 cannot be a value check for all seven inks.**
`chat_ui/chat_ui/theme.py:19` and `:43` are the same pigment. The rail paints every session title in `theme.INK` (`session_rail.py:152`, `:270`, `:394`, `:441`, `:487`), so `assert theme.INK_SELF not in rendered` fails on a correct rail — right about the bytes, wrong about the claim. STORY-018 predicted this and left it in its module docstring (`tests/test_session_rail.py:26-31`): *"compare against the six inks that are not `INK`, or compare by token name rather than by value."* `tests/test_render_invariants.py:428` records the identical exception for the console. **Resolution**: six inks by value against the rendered output, `INK_SELF` by token name against the source, plus a recording test asserting the collision so nobody re-adds the value check. Verified: `grep -n "INK_\|TINT_" chat_ui/chat_ui/components/session_rail.py` returns nothing — the source names no ink token at all, prose included, so the name-based half is clean today and starts green.

**2. The existing radius detector sees only one of the two spellings.**
`tests/test_session_rail.py:174` matches `["borderRadius"] : "..."` — Reflex's compiled inline-style form. A radius arriving as raw CSS (a `style=` string, a `_hover` CSS block, a `GLOBAL_CSS`-style rule) spells it `border-radius:` and would pass unseen. Confirmed against the live output: both current radii are `3px` and both are in the JS form, so widening the regex to cover `borderRadius` **and** `border-radius` is a no-op today and closes the gap for tomorrow. AC 3 names the pill as "the drift's most likely first step", which is exactly the edit that would introduce a raw-CSS override.

**3. AC 3 and AC 4 are already partly asserted — by one test that owns neither cleanly.**
`tests/test_session_rail.py:231-252`, `test_the_rail_renders_only_ground_tokens_and_one_radius`, makes both claims in one function and its own docstring calls itself "the floor" and says "STORY-020 owns the full guard". **Resolution**: split it, do not duplicate it. Its ground-token half becomes AC 4's test and its radius half becomes AC 3's, each parametrized and each citing its refusal. A second test asserting the same thing under a different name would make a failure print twice and teach nobody which claim broke.

**4. AC 6 needs no new pairing, and that is a finding worth writing down.**
The rail renders exactly two inks (`INK`, `MUTE`) on exactly two grounds (`PAPER` at `session_rail.py:590`, `HOVER` at `:177` and `:398`). All four pairings are already asserted in `tests/test_contrast.py:91-111`'s neutral block, including `("body ink on row hover", theme.INK, theme.HOVER)` — AC 6's specifically named case. `SPINE` and `RULE`/`RULE_SOFT` are hairlines and marks, not text, so they stay out on the same reasoning `test_contrast.py:107-109` already records for `RULE`. The story predicts this ("`tests/test_contrast.py` should need **no new pairing** if STORY-017 held the line on colours"), and STORY-017 held it. The work is therefore to state the rail's pairing set *as a set* so it survives a component moving an ink, not to add a missing assertion.

**Baseline, run before planning** (`.venv/Scripts/python.exe -m pytest`): `tests/test_session_rail.py tests/test_contrast.py tests/test_copy.py tests/test_admin_palette.py` → **111 passed**; `tests/test_render_invariants.py` → **57 passed**. AC 7 is green before this story starts. Live probe output confirms the rail renders seven hexes — `#14181C #626C77 #C3CBD3 #CBD2D9 #DDE2E7 #ECEFF1 #F1F3F5` — every one a ground token, and `theme.CARD` (`#FFFFFF`) simply unused, which AC 4's subset phrasing ("resolves to one of the ground tokens") already allows.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_session_rail.py` | UPDATE | AC 1–5. Widen the radius detector, add the tint/verdict-ink/radius/ground guards STORY-018 handed over, split the existing combined floor test, add the detector self-test and the `INK_SELF` recording test, update the module docstring to say the handover is complete. |
| `tests/test_contrast.py` | UPDATE | AC 6. A rail pairing block stating the two inks × two grounds as a set, mirroring the console block. |
| `tests/test_copy.py` | UPDATE | AC 8. Source-side assertion that no user-facing string is written as a literal in the rail component. |
| `tests/test_render_invariants.py` | VERIFY (no edit expected) | AC 7. Run green with the rail present; record in the report that the file is console-only and encodes no chat-surface invariant, so the rail's render invariants live in `test_session_rail.py` where Risk 6 asks for a *component* test. |
| `chat_ui/chat_ui/components/session_rail.py` | TEMPORARY EDIT, REVERTED | AC 5 only. The deliberate `TINT_HELD` violation, added, watched failing, removed. **Must not appear in any commit.** |

No production file is changed by this story. Per the story's technical note: "if a guard fails, the fix belongs in STORY-017, STORY-018 or STORY-019, with the reason recorded in this story's report."

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Widen the radius detector in the probe

- **File**: `tests/test_session_rail.py`
- **Action**: UPDATE — `_CHECK_SCRIPT`, the line at `:174`
- **Implement**: replace the `borderRadius`-only regex with one that collects both compiled spellings, so a raw-CSS radius cannot slip past the JS-style matcher:
  ```python
  result["radii"] = sorted(set(
      re.findall(r'\["borderRadius"\] : "([^"]+)"', rendered)
      + re.findall(r"border-radius\s*:\s*([^;\"'}]+)", rendered)
  ))
  ```
  Also emit `result["radius_probe_form"]` — the raw count of each form found — so a Reflex change to the compiled shape is visible rather than silent, in the spirit of `_page_without_the_stylesheet`'s length assertion.
- **Mirror**: `tests/test_render_invariants.py:277-284` — the strip-proved-non-empty idea: a detector that silently matches nothing is worse than no detector.
- **Why**: Exploration Finding 2. No-op against today's output; closes the drift route AC 3 names as most likely.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_session_rail.py -q` → still passes, `radii == ["3px"]`.

### Task 2: AC 1 — no `TINT_*` value reaches the rail

- **File**: `tests/test_session_rail.py`
- **Action**: UPDATE — new module constant + test, in a new `# --- The design guards (STORY-020) ---` section after the existing probe tests
- **Implement**: declare `TINT_NAMES` as the **six** tints in `theme.py` (`TINT_CLEAR`, `TINT_HELD`, `TINT_DENIED`, `TINT_FORBIDDEN`, `TINT_UPSTREAM`, `TINT_FAULT`) — note `test_render_invariants.py:98` lists only five, because PRD-006 predates `TINT_FORBIDDEN`; the rail must refuse all six. Parametrize one test per tint over the rendered output, comparing `.upper()` on both sides. Add the probe's `rendered` string to the probe result (`result["rendered"] = rendered`) if a full-string comparison is wanted, or assert against `probe["hexes"]` — prefer `hexes`, since the probe already extracts them and a tint is by definition a hex.
- **Mirror**: `tests/test_render_invariants.py:388-401` (`test_no_tint_reaches_either_page`) — same parametrized shape, same `getattr(theme, name)` by-name read.
- **Docstring must cite**: PRD-008 Risk 6 verbatim — "a card for a row, a rounded highlight for the active one, an accent for the button" — and Section 6.1's "The seven verdict inks stay in the transcript, where they mean something: a rail row is not a verdict and must not borrow one."
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_session_rail.py -q -k tint` → 6 passed.

### Task 3: AC 2 — none of the seven verdict inks appears in the rail

- **File**: `tests/test_session_rail.py`
- **Action**: UPDATE — two tests plus one recording test
- **Implement**: three parts, and the split is the point:
  1. `VERDICT_INKS_BY_VALUE` — the six inks that are **not** `theme.INK`: `INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FORBIDDEN`, `INK_UPSTREAM`, `INK_FAULT`. Parametrized, asserted absent from `probe["hexes"]`.
  2. `test_the_rail_names_no_verdict_ink` — a **source** grep over `RAIL_SOURCE_PATH` for all seven token names including `INK_SELF`, since `INK_SELF`'s value is indistinguishable from `INK`. This is the `tests/test_admin_palette.py:117-124` mechanism the story's technical note points at, applied to the one ink that needs it.
  3. `test_ink_self_cannot_be_excluded_by_rail_value` — asserts `theme.INK_SELF == theme.INK` and explains, in the docstring, why part 1 has six entries and not seven.
- **Mirror**: `tests/test_render_invariants.py:428-443` for the recording test; `tests/test_admin_palette.py:117-124` for the by-name source grep.
- **Guard against a trap**: the source grep runs over the whole file including docstrings. The rail names no ink token today (verified), but this test's own prose must not defeat a future one — keep the token names out of `session_rail.py`'s prose, and if a future rail docstring must *name* an ink in order to refuse it, switch this test to the `code_strings`/`_docstring_nodes` treatment already in this file at `:81-115` rather than weakening the grep.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_session_rail.py -q -k "ink"` → all pass.

### Task 4: AC 3 and AC 4 — one radius, ground tokens only

- **File**: `tests/test_session_rail.py`
- **Action**: UPDATE — split `test_the_rail_renders_only_ground_tokens_and_one_radius` (`:231-252`) into two
- **Implement**:
  - `test_the_only_radius_in_the_rail_is_the_theme_radius` — `assert probe["radii"] == [theme.RADIUS]`, with the docstring carrying AC 3's reasoning ("the pill row is the drift's most likely first step") and Section 6.1's refusal of "rounded pill rows". Compare against `theme.RADIUS` by name, never against `"3px"`.
  - `test_every_colour_in_the_rail_is_a_ground_token` — build `GROUND_TOKENS` as the eight names AC 4 lists (`PAPER`, `CARD`, `INK`, `MUTE`, `RULE`, `RULE_SOFT`, `HOVER`, `SPINE`) read from `theme` by name, and assert `set(probe["hexes"]) <= GROUND_TOKENS`. Keep the subset relation, not equality: `theme.CARD` is legitimately unrendered today (Finding 4) and demanding it would fail on a correct rail.
  - Delete the superseded combined test and note the supersession in its replacement's docstring, so a reader of the diff sees the claim moved rather than vanished.
- **Mirror**: `tests/test_render_invariants.py:404-419` (`test_no_colour_outside_the_allowed_set`) — the `found <= ALLOWED` shape and the `sorted(found - ALLOWED)` failure message, which names the offending colour instead of dumping the set.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_session_rail.py -q` → all pass, no test lost (count should rise, not fall, versus the Task 0 baseline).

### Task 5: AC 5 — add the violation, watch it fail, remove it

- **File**: `chat_ui/chat_ui/components/session_rail.py` (temporary), then reverted
- **Action**: TEMPORARY EDIT
- **Implement**: in `_row()` (`:344-368`) — which today has no active-conditional background at all, the spine being the whole of the active mark — add exactly the drift Risk 6 names:
  ```python
  # DELIBERATE VIOLATION — STORY-020 AC 5. Remove after watching the guard fail.
  background_color=rx.cond(_is_active(row), theme.TINT_HELD, "transparent"),
  ```
  `rx.cond` compiles both arms into the template, so `#FAF6EA` reaches `probe["hexes"]` and the guard sees it.
- **Watch fail**: run the suite and confirm **three** guards go red together — AC 1's `TINT_HELD` case, AC 4's ground-token subset, and (as a bonus signal) nothing else. Capture the exact failure output verbatim; it goes in the report. A run that fails only one of the two is a finding, not a pass.
- **Then**: `git checkout -- chat_ui/chat_ui/components/session_rail.py` and re-run to confirm green. **Verify with `git status` and `git diff` that the rail source is unmodified before any commit.**
- **Also add, permanently** — `test_the_tint_guard_detects_a_tint`, a detector self-test running the guard's own comparison over a synthetic `hexes` list containing `theme.TINT_HELD`, so the "watched failing" claim stays true after the violation is gone and does not decay into a line in a report nobody re-runs.
- **Mirror**: `tests/test_admin_palette.py:148-158` — the same argument, in that file's own words: "A guard nobody has watched fail is a guard nobody knows is armed."
- **Validate**: red run captured, then `.venv/Scripts/python.exe -m pytest tests/test_session_rail.py -q` → green, and `git diff --stat chat_ui/` → empty.

### Task 6: AC 6 — the rail's pairings, stated as a set

- **File**: `tests/test_contrast.py`
- **Action**: UPDATE — append a rail block after the console block (`:114-155`)
- **Implement**: `_RAIL_INKS = (("INK", theme.INK), ("MUTE", theme.MUTE))` and `_RAIL_GROUNDS = (("PAPER", theme.PAPER), ("HOVER", theme.HOVER))`, cross-producted into `test_every_rail_pairing_is_readable`, floor `AA_NORMAL`. The docstring records Finding 4 in full: that all four pairings were already covered by the neutral block — `INK`/`HOVER` being AC 6's named case, already at `:104` — that STORY-017 is the reason no new pairing was needed, and that `SPINE`, `RULE` and `RULE_SOFT` are excluded because AA is a text criterion and a hairline is not text (the reasoning `:107-109` already records for `RULE`).
- **Do not** delete the neutral-block entries this overlaps. They record *why each specific pairing exists*; the set records *what the surface is allowed to do*. `test_contrast.py`'s own module docstring makes exactly this distinction for the console block.
- **Mirror**: `tests/test_contrast.py:114-155`, verbatim in shape including the `ids=lambda` that keeps hex values out of test ids.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_contrast.py -q` → 4 new tests, all pass, no new pairing required.

### Task 7: AC 8 — no literal user-facing string in the rail component

- **File**: `tests/test_copy.py`
- **Action**: UPDATE — new source-side test at the end of the rail section (after `:784`)
- **Implement**: `test_no_rail_string_is_written_as_a_literal_in_the_component`. Parse `chat_ui/chat_ui/components/session_rail.py` with `ast`, exclude docstrings by identity, and assert that **every** non-private string constant in `copy.py` whose name starts with `SESSION_`/`TRANSCRIPT_`, plus `RETRY_LABEL`, appears in none of the rail's code strings. Drive it off `dir(copy)` rather than a hand-typed tuple.
- **Why this is not a duplicate of `tests/test_session_rail.py:258-273`**: that test walks a curated `COPY_NAMES` tuple — eleven names someone maintains. This one walks the whole `copy` vocabulary, so a constant added tomorrow and then pasted as a literal into the rail is caught without anyone editing a list. AC 8 asks for the assertion in `test_copy.py` specifically, and driving it from `copy.py`'s own contents is what earns it its place there rather than making it a second copy of an existing check. State that relationship in the docstring so a future reader does not "consolidate" the two.
- **Mirror**: `tests/test_session_rail.py:81-115` for `_docstring_nodes` / `code_strings` (copy the helpers or import them — prefer copying, since `test_copy.py` currently imports no test module and adding a cross-test import would make its collection order matter).
- **Watch it bite**: temporarily paste `"New chat"` as a literal into `_new_chat_control()`, confirm the test fails, revert. Same discipline as Task 5, and cheap.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_copy.py -q` → passes; the temporary literal makes it fail.

### Task 8: AC 7 — the render invariants still hold with the rail present

- **File**: `tests/test_render_invariants.py`
- **Action**: VERIFY — no edit expected
- **Implement**: run the suite. It is console-only: `PAGES = ("register_page", "summary_page")` (`:132`) and its probe renders `admin_page(register(), ...)` and `admin_page(summary(), ...)` only. It therefore encodes **no** invariant for the chat surface, and AC 7's second clause resolves to nothing to hold. Record that plainly in the report rather than inventing a chat page into this file: PRD-008 Risk 6 asks for "a **component** test", which is `tests/test_session_rail.py`, and duplicating the rail's guards onto a whole-chat-page probe would give two places to update and one of them would rot.
- **If it fails**: the fix belongs in STORY-017/018/019 per the story's technical note, not here — record the reason in this story's report.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_render_invariants.py -q` → 57 passed (the pre-story baseline; the number must not fall).

### Task 9: Update the STORY-018 handover note

- **File**: `tests/test_session_rail.py`
- **Action**: UPDATE — module docstring, `:20-31`
- **Implement**: the docstring currently says the design guards "are STORY-020's, not this file's" and leaves a note about `INK_SELF`. Rewrite those two paragraphs to say the handover is complete: which guards now live here, that the `INK_SELF` exception was resolved by splitting value-checks from name-checks, and where the deliberate violation is recorded (this story's report). A docstring that still promises future work after the work has landed is a small lie that costs the next reader a search.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_session_rail.py -q` → green.

---

## End-to-End Tests

- [ ] `tests/test_session_rail.py` passes with the rail unmodified, and its test count is strictly higher than the 111-test baseline for the four-file guard group.
- [ ] With the `TINT_HELD` violation applied to `_row()`, the AC 1 `TINT_HELD` case **and** the AC 4 ground-token case both fail; failure output captured verbatim for the report.
- [ ] With the violation reverted, `git diff chat_ui/` is empty and the suite is green.
- [ ] With `"New chat"` pasted as a literal into `_new_chat_control()`, `tests/test_copy.py`'s AC 8 test fails; reverted, it passes.
- [ ] A radius other than `theme.RADIUS` — e.g. `border_radius="9999px"` on the row open button — fails the AC 3 guard. (Optional third violation; cheap, and it is the drift AC 3 names.)
- [ ] `tests/test_render_invariants.py` → 57 passed, unchanged.
- [ ] Full suite green, with PRD-008 Section 11's pinned suites unmodified: `test_query_router.py`, `test_integration.py`, `test_route_reservations.py`, `test_admin_auth.py`, `test_audit_router.py`, `test_stats_router.py`, `test_rbac.py`, `test_summary.py`.

## Validation

```bash
# The guard group
.venv/Scripts/python.exe -m pytest tests/test_session_rail.py tests/test_contrast.py \
    tests/test_copy.py tests/test_admin_palette.py tests/test_render_invariants.py -q

# The rail source must be untouched by this story
git diff --stat chat_ui/

# Full suite
.venv/Scripts/python.exe -m pytest -q
```

**Environment note**: if the full suite reports mass fixture errors, the libSQL dev server has degraded under repeated runs — restart the container rather than bisecting these tests. The guard group above needs no database at all except `test_render_invariants.py`, which uses `database_url_factory`.

---

## Risks + Mitigations

| Risk | Mitigation |
|------|-----------|
| The `INK_SELF`/`INK` collision is "fixed" by someone adding the seventh ink to the value check, turning every rail row's title into a failure — or worse, by loosening the guard until it says nothing. | Task 3's recording test asserts the collision and explains it in its docstring, following `test_ink_self_cannot_be_excluded_by_value`'s precedent exactly: "so that a future attempt to add the value check finds the reason before writing it." |
| The deliberate violation is committed by accident, shipping a tinted active row. | Task 5 ends with `git checkout --` and both `git status` and `git diff --stat chat_ui/` as explicit gates; the End-to-End list repeats the check; the permanent detector self-test means the AC 5 claim does not depend on the violation ever existing again. |
| The guards duplicate `tests/test_session_rail.py`'s existing floor test, so a drift prints two failures and the reader cannot tell which claim is the real one. | Task 4 **splits** the existing test rather than adding beside it, and records the supersession in the replacement docstrings. |
| AC 8's test becomes a verbatim second copy of `test_every_user_facing_string_resolves_from_copy`, and someone later deletes one of them. | Task 7 drives off `dir(copy)` instead of a curated tuple, making it strictly stronger, and its docstring states the relationship between the two so a consolidation attempt meets the argument first. |
| The radius guard's regex silently matches nothing after a Reflex upgrade changes the compiled style form, leaving AC 3 green and unenforced. | Task 1 emits the per-form match counts alongside the values, so a form that stops matching is visible — the same defence `_page_without_the_stylesheet` uses for its strip. |
| `TINT_FORBIDDEN` is forgotten because the console's list at `test_render_invariants.py:98` has only five tints. | Task 2 states six explicitly and says why the console's list is shorter. |

---

## Acceptance Criteria

(Copied from story `STORY-020`)

- [ ] Given a test over `chat_ui/chat_ui/components/session_rail.py`'s rendered output, when it runs, then it asserts no `TINT_*` value appears.
- [ ] Given the same test, when it runs, then it asserts none of the seven verdict inks (`INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FORBIDDEN`, `INK_UPSTREAM`, `INK_FAULT`, `INK_SELF`) appears in the rail.
- [ ] Given the same test, when it runs, then it asserts no border radius other than `theme.RADIUS` appears — the pill row is the drift's most likely first step.
- [ ] Given the same test, when it runs, then it asserts every colour in the rail resolves to one of the ground tokens (`PAPER`, `CARD`, `INK`, `MUTE`, `RULE`, `RULE_SOFT`, `HOVER`, `SPINE`).
- [ ] Given a deliberate violation added during implementation — a `TINT_HELD` background on the active row — when the suite runs, then this test fails; the violation is then removed.
- [ ] Given `tests/test_contrast.py`, when it runs, then every ink/ground pairing the rail actually uses is covered and clears WCAG AA, including the active row's `INK` on `HOVER`.
- [ ] Given `tests/test_render_invariants.py`, when it runs, then it passes with the rail present, and any invariant it encodes for the chat surface still holds.
- [ ] Given `tests/test_copy.py`, when it runs, then it asserts no literal user-facing string appears in the rail component — every one resolves from `chat_ui/chat_ui/copy.py`.
- [ ] All tasks completed
- [ ] No production code changed — `git diff chat_ui/` empty
- [ ] Full suite passes; PRD-008 Section 11's pinned suites unmodified
- [ ] Follows existing patterns (`test_admin_palette.py`, `test_render_invariants.py`, `test_contrast.py`)
