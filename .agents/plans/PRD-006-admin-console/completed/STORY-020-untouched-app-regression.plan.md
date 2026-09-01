---
story: STORY-020
prd: PRD-006
slug: untouched-app-regression
title: "Full-suite regression and the proof that nothing under app/ changed"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Full-suite regression and the proof that nothing under app/ changed

## Summary

The last story of PRD-006 writes no feature. It produces **evidence**: that the
console PRD-006 built lives entirely inside `chat_ui/`, that the REST contract
and the audit schema are exactly what PRD-001 and PRD-003 shipped, that the
eight suites Section 15 names still pass, and that an admin can actually answer
the question Section 11 sets — *what was blocked, what failed, and how much of it
touched PII* — without a terminal. The method is the story's own Technical Note:
*"the claim is only as good as the evidence"*, so every check runs and its
literal output is pasted into the report rather than summarised into a tick.

Planning already ran the two diffs this story turns on, and they produce a result
the plan must be honest about up front. **PRD-006 changed nothing under `app/`** —
`git diff d3e6279 -- app/`, against the commit STORY-001 branched from, is
empty. But **`git diff main --stat` is not empty under `app/`**: `app/db/database.py`
and `app/db/models.py` differ from `main` because of commit `3f553f2`
("feat(chat-ui): implement PII column migration…", Nahuel Escalante,
2026-08-28) — a PRD-004-era commit by another author, landed *after* PRD-004's own
STORY-019 regression pass certified `app/` clean, and three commits before
PRD-006's first line was written. `main` is still at the PRD-003 merge
(`56a3781`), so it is not the branch point of this PRD's work; it is the branch
point of the *previous* one. Every prior story in this epic (STORY-015, -017,
-019) recorded the discrepancy and deferred it here with the words *"STORY-020
owns that reconciliation."*

So this story runs **both** baselines, states which claim each one settles, and
does not touch `app/` to make the literal wording of AC 2 come true — PRD Section 4
puts every change under `app/` out of scope and the story's own Technical Note
forbids fixing a defect found here. The reconciliation is recorded as a finding
with attribution, and the residual as a follow-up. It closes with one new guard
file so the property is re-checked on every future run rather than believed on
the strength of one afternoon.

## User Story

As an integrating developer
I want the console confined to `chat_ui/` with no new route on the FastAPI app
So that the REST contract, the audit schema and PRD-001/003's test suites are
provably unchanged.

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-020-untouched-app-regression.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 4 (out of scope), Section 5 (story 9), Section 10, Section 11, Section 12 Phase 4, Section 13, Section 15

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (verification pass; no application code written) |
| Complexity | LOW |
| Systems Affected | `tests/` (one new guard file), `.agents/` (report, story, index). **No source file under `app/` or `chat_ui/` is expected to change.** |
| Story | STORY-020 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

### The two baselines, named once so every task can refer to them

| Name | SHA | What it is | What a diff against it proves |
|---|---|---|---|
| `MAIN` | `56a3781` (`main`) | The PRD-003 merge. The branch point of **PRD-004**, not of this PRD. | What the *whole epic branch* changed — PRD-004 and PRD-006 together. This is what AC 2 names literally. |
| `BASE006` | `d3e6279` | Parent of `577a285` (STORY-001, PRD-006's first commit). | What **PRD-006 alone** changed. This is what AC 2 *means*, and the only baseline that can carry the claim. |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| **reflex-process-management** (plugin skill) | `chat_ui/AGENTS.md`, verbatim and quoted in the story's Technical Notes: *"When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."* AC 5 and AC 6 both require a running server. | Tasks 5, 6, 7, 8, 12 |
| **reflex-process-management** — compile first | *"`reflex compile --dry` … checks for syntax errors, import issues, and component problems without starting the server. Use this as a quick validation step."* Cheaper than a failed boot. | Task 5 |
| **reflex-process-management** — run in prod | *"always use production mode and redirect output to a log file: `reflex run --env prod --single-port 2>&1 \| tee reflex.log`"*, and *"**Do not assume the port is 8000**"* — read `App running at: http://0.0.0.0:<port>` out of `reflex.log`. | Tasks 5, 6, 7, 8 |
| **reflex-process-management** — Windows adaptation | The skill's `lsof -i :<port> -sTCP:LISTEN -t` does not exist on this host. The equivalent preserving the skill's critical property — match the **listening** socket, never a browser connection — is `netstat -ano \| findstr LISTENING \| findstr ":<port>"` → `taskkill /PID <pid>` (`/F` only if it does not exit). **Never kill by image name**; the skill's warning about killing the user's browser applies with more force when the matching is coarser. Carried forward from the STORY-019 plan, where it was established. | Tasks 5, 12 |
| **reflex-process-management** — investigating errors | *"When the user reports an error, read `reflex.log` to find and diagnose the issue."* Any boot or runtime failure during Tasks 6–8 is diagnosed from the log, not guessed at. | Tasks 5–8 |
| **frontend-design** (`.agents/skills/frontend-design/SKILL.md`, pinned in `skills-lock.json`) | Not a design story, but AC 5 walks Section 11's functional list, which includes the Section 6.1 claims. Verbatim: *"Critique your own work as you build, taking screenshots if your environment supports it."* Every AC-5 checkbox is recorded with a measured value or a screenshot, not a tick. | Tasks 7, 8 |

---

## Patterns to Follow

### The "unmodified test files" claim already has a machine-checkable form in this repo

```python
# SOURCE: tests/test_pii_redaction_integration.py:256-317
_PRE_EPIC_UNTOUCHED_TESTS = [
    "tests/test_admin_auth.py",
    "tests/test_duplicate_checker.py",
    "tests/test_integration.py",
    "tests/test_openrouter_client.py",
    "tests/test_pattern_detector.py",
    "tests/test_route_reservations.py",
]

def _epic_base():
    base = _git("merge-base", "main", "HEAD")
    return base.strip() if base and base.strip() else None

@pytest.mark.parametrize("path", _PRE_EPIC_UNTOUCHED_TESTS)
def test_pre_epic_test_files_are_unmodified_by_this_epic(path):
    """AC4, layer 1: the PRD-001 suites this epic never needed to open."""
    ...
    changed = _git("diff", "--name-only", base, "--", path)
    assert [line for line in changed.splitlines() if line.strip()] == []

def test_no_pre_epic_test_function_was_removed_or_renamed():
    """AC4, layer 2: catches a deletion inside a file the epic legitimately extended."""
```

PRD-003 wrote exactly this guard for exactly this acceptance criterion. Task 10
mirrors it for PRD-006 rather than inventing a new shape — including **layer 2**,
which is the half that matters: layer 1 cannot see an assertion deleted from a
file the epic was allowed to extend, and `test_copy.py` and `test_contrast.py`
are precisely such files.

Note the trap this file also documents by omission: its `_epic_base()` is
`merge-base main HEAD`, which on this branch still resolves to `56a3781` — that
is why `tests/test_chat_state.py` had to be **removed** from the list by PRD-004's
STORY-002 (`59899ca`). The new guard must therefore pin `BASE006` explicitly
rather than derive a base that would answer the wrong question.

### Seeding: `settings.DATABASE_URL` is redirected before any database call

```python
# SOURCE: tests/test_render_invariants.py:155-215 (_CHECK_SCRIPT)
    # First, and before any database call: init_db() against the default
    # sqlite:///harness_ai.db would write sentinel previews into the developer's
    # real audit log.
    settings.DATABASE_URL = "sqlite:///{}/console.db".format(
        tempfile.mkdtemp().replace("\\", "/")
    )
    ...
_ROWS = [
    dict(timestamp="2026-08-31T14:22:07", was_duplicate_blocked=False),
    dict(timestamp="2026-08-31T14:21:07", was_duplicate_blocked=True),
    dict(timestamp="2026-08-31T14:20:07", suspicious_pattern="ignore previous"),
    dict(timestamp="2026-08-31T14:19:07", success=False,
         error_message="OpenRouter request failed: timeout after 30s"),
]
```

One row per verdict, `insert_audit_log` rather than hand-written SQL, and the
logger's real timestamp format. This is the exact shape the story's Technical
Note asks for — *"a seeded database containing at least one row of each verdict,
at least one PII row and at least one row with an `error_message`"*. Task 4
reuses it, at a size that also exercises the register's cap line.

Timestamp format trap, recorded by STORY-011 and repeated by the STORY-019 plan:
the logger writes `%Y-%m-%dT%H:%M:%SZ` (`app/services/audit_logger.py:8`).
`datetime.isoformat()` writes microseconds, widens the column, and gives a false
layout signal.

### Forcing the fault path: an exclusive database lock, not a monkeypatch

```
# SOURCE: STORY-019 report, "End-to-End Verification"
The fault path was forced the way STORY-017 forced it — a `BEGIN EXCLUSIVE`
lock held on `harness_ai.db` from a second process, producing a real
`sqlite3.OperationalError` inside `asyncio.to_thread` and a multi-second
in-flight window to observe.
```

A live server cannot be monkeypatched from the test process. This is the
established way to make Section 11's *"a raised exception during a read renders
a fault panel with a retry"* checkbox observable.

### Reports paste the evidence, they do not summarise it

```markdown
# SOURCE: .agents/reports/PRD-006-admin-console/STORY-019-...report.md
| Check | Result |
|-------|--------|
| `reflex compile --dry` | ✅ clean |
| Tests | ✅ 848 passed |
| `git diff --stat -- app/` | ✅ empty |
```

The house style is a table of measured results plus a numbered E2E table. This
story's report adds one thing the others did not need: a **verbatim command-output
block** for each diff, because AC 2's Technical Note demands the raw output and
because the AC-2 finding below is only credible with the output attached.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_untouched_app.py` | CREATE | The permanent guard: `app/` unchanged since `BASE006`, and the eight Section 15 suites unmodified except the two this PRD was allowed to extend — with a function-census layer so an assertion cannot be deleted from those two |
| `.agents/reports/PRD-006-admin-console/STORY-020-untouched-app-regression.report.md` | CREATE | The evidence. AC 2's Technical Note makes the pasted diff output part of the deliverable, and AC 5 makes the Section 11 walkthrough a recorded artifact |
| `.agents/stories/PRD-006-admin-console/STORY-020-untouched-app-regression.md` | UPDATE | `plan`, `status`, `commit`, `updated` (Phase 5 now; commit SHA at implement time) |
| `.agents/PRDs/PRD-006-admin-console/index.md` | UPDATE | Status + plan link; 20/20 at completion |
| `.agents/PRDs/PRD-006-admin-console/PRD.md` | UPDATE (conditional) | **Only** if Task 3 or Tasks 6–8 surface a genuine `app/` defect — appended to Section 13 as a follow-up, never fixed. Per the story's Technical Note |

**Files that must NOT change** — this is the story's whole subject, and a change
to any of them is a failure of the story, not a step in it:

- anything under `app/`
- `requirements.txt`, `chat_ui/requirements.txt`
- `Caddyfile`, `chat_ui/rxconfig.py`
- `tests/test_admin_auth.py`, `test_audit_router.py`, `test_stats_router.py`,
  `test_db.py`, `test_route_reservations.py`, `test_chat_state.py`
- `tests/test_copy.py`, `tests/test_contrast.py` — extendable *by this PRD's
  earlier stories*, already extended, and **closed now**: STORY-020 adds nothing
  to them. STORY-019 established the precedent, declining to delete three
  now-unrendered constants precisely because it would have forced an edit to
  `test_copy.py`
- every chat module: `chat_ui/chat_ui/{state,copy,formatting,models}.py`,
  `components/{chat,bubbles,shell}.py`

**Files that will be dirtied by running the app and must be restored (Task 12)**:
`chat_ui/harness_ai.db` (gitignored but the user's real console database —
back it up), `chat_ui/reflex.lock/package.json` (tracked; modified by the
production build — STORY-017 Deviation 5), `chat_ui/reflex.log`.

---

## Tasks

Execute in order. Tasks 1–3 and 9 are evidence tasks: each names the exact
command, and the deliverable is its **literal stdout** in the report. A check
recorded as "verified" without its output does not satisfy this story.

### Task 1: The full suite, green, and its number recorded (AC 1)

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**:
  - From the repo root: `python -m pytest -q`. Record the pass count and the runtime.
  - The expected count is **848** at planning time (`python -m pytest --collect-only -q` → `848 tests collected`), plus whatever Task 10 adds. A number lower than 848 is a deleted test and a failure of this story, not a smaller suite.
  - Then run the eight Section 15 suites by name, separately, so the report can state each one's own result rather than one aggregate:
    `python -m pytest -q tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py tests/test_copy.py tests/test_contrast.py`
  - If anything fails, diagnose before proceeding — a red suite makes every later task unreadable. A failure inside `app/`'s own suites is a Task 3 finding (record, do not fix); a failure inside an admin suite is a defect this story must fix in `chat_ui/`.
- **Mirror**: STORY-019 report's Validation Results table (`Tests | ✅ 848 passed`).
- **Validate**: `python -m pytest -q` exits 0; per-file run exits 0; both outputs pasted.

### Task 2: `git diff main --stat`, run literally, pasted whole (AC 2, first half)

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**:
  - Run exactly what the AC names — `git diff main --stat` — and paste the **entire** output into the report. The story's Technical Note is explicit: *"Run the `git diff main --stat` check explicitly and paste its output into the story report; the claim is only as good as the evidence."* Not a filtered version, not a summary.
  - Then the scoped forms, each pasted:
    - `git diff main --stat -- app/` → expected **non-empty**: `app/db/database.py | 14 +++-` and `app/db/models.py | 11 +++`
    - `git diff main -- app/` → the full patch, so the reader can see what it actually is
    - `git diff main --stat -- requirements.txt chat_ui/requirements.txt` → expected **empty** (AC 3)
    - `git diff main --stat -- Caddyfile chat_ui/rxconfig.py` → expected **empty** (AC 4)
  - Record which parts of AC 2's sub-clauses hold against `MAIN` even so, because most of them do and the report should say which: `app/routers/`, `app/models/schemas.py`, `app/middleware/`, `app/services/` and `app/config.py` are **all** untouched vs `main`, so *"no change to `AuditQueryEntry` or `StatsResponse`"* and *"no query parameter"* hold literally against `main`. What does not hold against `main` is *"no new database function"* (`_add_missing_columns`) and *"no schema migration"* (`ALTER TABLE audit_logs ADD COLUMN`).
- **Validate**: four command outputs in the report, unedited.

### Task 3: Attribute every `app/` hunk, and state the claim the evidence actually supports (AC 2, second half)

- **File**: none (verification) — then `PRD.md` Section 13 only if a genuine defect surfaces
- **Action**: VERIFY
- **Implement**:
  - `git log --oneline main..HEAD -- app/` → expected to print exactly one line: `3f553f2 feat(chat-ui): implement PII column migration and enhance duplicate message formatting`.
  - `git log -1 --format='%H%n%an%n%ad%n%s' 3f553f2` → records the author (Nahuel Escalante) and the date (2026-08-28), establishing it as a PRD-004-era commit by a different author. Note the ordering that makes it unambiguous: PRD-004's STORY-019 regression pass (`c724de8`, completed 2026-08-25) certified `app/` clean and *predates* `3f553f2`; PRD-006's STORY-001 (`577a285`) *postdates* it. The drift entered between the two PRDs.
  - **The claim this story can and does make**: `git diff d3e6279 --stat -- app/` → **empty**. Paste it (an empty output is still evidence, and the report should say what command produced nothing). Add `git diff d3e6279 --name-only -- app/ | wc -l` → `0` so the emptiness is a printed number rather than an absence.
  - Restate AC 2 against `BASE006` clause by clause and confirm each: no new database function, no query parameter, no schema migration, no change to `AuditQueryEntry` or `StatsResponse` — all four hold, because nothing under `app/` changed at all.
  - Write the reconciliation into the report as a **Deviation**, in the house style, naming: the literal AC as written, the measured result, the attribution, the baseline that carries the claim, and the fact that the fix is out of scope. PRD Section 4 puts every change under `app/` out of scope; the story's Technical Note says *"If a genuine defect in `app/` surfaces during this pass, do **not** fix it here"*.
  - Decide and record the residual as a follow-up: whether `3f553f2` should be merged to `main` on its own or carried in the epic's merge is a branch-hygiene question for the epic's merge, not a code change for this story. Append it to PRD Section 13 only if the pass concludes it is a real outstanding item; do not append restatements of the three defects Section 13 already records (`error_kind`, projecting `success`/`error_message`, `count_answered_queries()`).
- **Validate**: the attribution log prints one commit; the `BASE006` diff prints nothing and `--name-only | wc -l` prints `0`; the deviation is written.

### Task 4: Seed the console database to the shape Section 11 requires

- **File**: `<scratchpad>/seed_story020.py` (throwaway; not committed)
- **Action**: CREATE
- **Implement**:
  - **Back up first**: `cp chat_ui/harness_ai.db chat_ui/harness_ai.db.story020.bak`. The server runs from `chat_ui/` and `chat_ui/.env` sets `DATABASE_URL=sqlite:///harness_ai.db`, which resolves against the process cwd — so that file, and not the repo-root one, is what the console reads. Restored in Task 12.
  - Write rows through `app.db.database.insert_audit_log` with `app.db.models.AuditLog`. No hand-written SQL — the point of this story is that the console reads what the application writes.
  - The distribution the story's Technical Note requires, plus what Section 11's checkboxes need to be observable:
    - at least one row of **each of the four verdicts** — cleared, held (`was_duplicate_blocked=True`), denied (`suspicious_pattern` set), fault (`success=False`)
    - at least one row with **PII** (`pii_detected_input`/`_output`, `pii_entities`)
    - at least one row with a non-null **`error_message`** — use a realistic one, `"OpenRouter request failed: timeout after 30s"`
    - **more than 100 rows total** (~120). This is not decoration: the register's cap line reads *"100 most recent of N"*, and with ≤100 rows the cap and the total are the same number and the checkbox *"states the cap against the true total"* cannot be distinguished from a coincidence.
    - a `user_id` that appears **exactly once** in the window, and one that dominates, so the free-text filter checkbox is checkable in both directions
    - varied `model_used` and `tokens_used` widths, and long real User-Agent strings
    - distinct **preview sentinels** on every row, so Section 11's last checkbox (*"`prompt_preview` and `response_preview` appear nowhere in the rendered output"*) is re-confirmed at scale for free
  - Timestamps in the logger's format, `%Y-%m-%dT%H:%M:%SZ`, spread over hours and descending.
  - Print a verdict tally and the total, and print the `audit_id` of the single-verdict rows — those ids are what Tasks 7's checkboxes filter on.
- **Mirror**: `tests/test_render_invariants.py:155-215` (`_CHECK_SCRIPT`'s seeding block) — same `settings.DATABASE_URL` discipline, same `init_db()`-first ordering; the STORY-019 plan's Task 1 for the distribution reasoning.
- **Validate**: the tally prints all four verdicts non-zero, ≥1 PII row, ≥1 row with `error_message`, and a total > 100; `count_audit_logs()` against the console's `DATABASE_URL` agrees.

### Task 5: Compile and run the production server, per the skill

- **File**: none (process)
- **Action**: RUN
- **Implement**:
  - `cd chat_ui && reflex compile --dry` — the skill's quick validation step, and cheaper than a failed boot. Any error here is read out of the output, not guessed at.
  - `reflex run --env prod --single-port 2>&1 | tee reflex.log`, backgrounded.
  - **Read the port from `reflex.log`'s `App running at: http://0.0.0.0:<port>` line.** The skill is explicit that 8000 must not be assumed, and a stale assumption is how the wrong process gets signalled in Task 12. STORY-017 and STORY-019 both landed on `:3000`; confirm, do not inherit.
  - Note in the report that `chat_ui/reflex.lock/package.json` will be modified by the production build — a side effect of running, recorded as such by STORY-017 Deviation 5 and reverted in Task 12.
- **Mirror**: STORY-019 plan Task 2; STORY-017 report's "End-to-End Verification (live, prod server on :3000)".
- **Validate**: `reflex compile --dry` clean; `reflex.log` carries the running line and no traceback; `GET /admin/audit` returns the gate.

### Task 6: The MVP walkthrough — Section 11's functional list, item by item (AC 5)

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: walk **all fourteen** of PRD Section 11's functional checkboxes against the seeded database and record a measured result for each — a value read out of the page, not a tick. In order:
  1. `/admin/audit` and `/admin/stats` render; `/admin` lands on the register — record the resolved URL/view for all three.
  2. An unauthenticated visit to either page shows the gate **and loads no data** — the second half is the one that matters and it is a state check, not a visual one: with no session, `AdminState.rows` must be empty. Read it from the serialized state, not inferred from a blank screen. This is PRD Risk 1's mitigation.
  3. A wrong token is refused with the same message as an empty one — submit both, record the two strings, assert they are identical (also a wrong-length and a whitespace token, since the AC's phrasing in Section 4 covers *"empty", "wrong length" and "wrong token"*).
  4. A correct token loads the register; **sign-out clears rows and figures from state** — again read from state after sign-out, not from the rendered gate.
  5. The register shows the 100 most recent rows and states the cap against the true total — with ~120 seeded, record both numbers and that they differ.
  6. Each of the four verdicts renders correctly against a row seeded to produce it — record the ink and the tag per verdict.
  7. A **fault** row discloses its `error_message` — open the disclosure, record the string.
  8. Filtering by verdict and by free text narrows the table **without a database read** — the negative half is the substance: watch the network/event traffic (or instrument the read) and confirm no read is issued per keystroke. PRD Risk 5.
  9. An `audit_id` from a chat success footer resolves to exactly one row — carried by Task 8, which produces a real footer id from a real chat send; record the id here and the row it resolves to.
  10. All nine `StatsResponse` figures render, each with its scope stated — enumerate all nine by name with the value and the scope text.
  11. The completion figure's label reflects that blocked rows count as successes — quote it verbatim (STORY-016 pins it; this re-reads it off the live screen).
  12. `pii_detected_queries` and `top_pii_entities` are visible on the summary — record both values.
  13. A raised exception during a read renders a fault panel with a retry, not an empty table — force it with a `BEGIN EXCLUSIVE` lock held on `chat_ui/harness_ai.db` from a second process, record the panel's text, release the lock, click retry, confirm recovery.
  14. `prompt_preview` and `response_preview` appear nowhere in the rendered output — search `document.documentElement.outerHTML` on both pages for every Task 4 sentinel; expect zero matches at ~120 rows.
  - Then the AC's own sentence, end to end and as one continuous action: open `/admin/audit`, enter the token, and answer *"what was blocked, what failed, and how much of it touched PII"* **with no terminal** — write the three answers into the report as the numbers a person would actually report, and name the on-screen element each came from.
- **Mirror**: STORY-019 report's numbered E2E table (check → measured result).
- **Validate**: fourteen recorded results plus the three answers; every one carrying a value or a quoted string.

### Task 7: The chat surface, through its six outcomes, exactly as PRD-004 shipped it (AC 6)

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**:
  - Six outcomes, one per `rx.match` arm in `chat_ui/chat_ui/components/chat.py:22-32` — `user`, `assistant`, `duplicate`, `injection`, `upstream_error`, `internal_error` — plus a note on the seventh, `render_fallback`, which is the default arm and is exercised by `tests/test_chat_components_import.py` rather than by a live send.
  - How to reach each on a live server, cheapest first:
    - **user** and **assistant** (cleared): one real send. `chat_ui/.env` carries a live `OPENROUTER_API_KEY`, so this costs exactly one upstream call — take one, not a series. Record the returned model, the token count and the `#audit_id` from the success footer; **that id is Task 6's checkbox 9**.
    - **duplicate** (held): re-send the same text within the 24h window. No upstream call — the duplicate check precedes the model.
    - **injection** (denied): send a known suspicious pattern. No upstream call — pattern detection precedes the model.
    - **upstream_error**: force an `OpenRouterError` without spending a call — point `OPENROUTER_API_KEY` at an invalid value (or the base URL at a closed port) in the server's environment and restart per the skill. Record which lever was used.
    - **internal_error**: `state.py:131` catches `DuplicateCheckError` and `PiiRedactorError`. The cheapest honest force is a database-side failure inside the duplicate check — the same `BEGIN EXCLUSIVE` lock Task 6 checkbox 13 uses.
  - For each: screenshot the bubble, record the tag (`YOU`/`CLEARED`/`HELD`/`DENIED`/`UPSTREAM`/`FAULT` — `chat_ui/chat_ui/copy.py:48-54`) and confirm no two share a treatment.
  - Then the AC's actual claim — *"exactly as PRD-004 shipped it"* — which is a **diff** claim, not only a visual one: `git diff d3e6279 --stat -- chat_ui/chat_ui/state.py chat_ui/chat_ui/copy.py chat_ui/chat_ui/formatting.py chat_ui/chat_ui/models.py chat_ui/chat_ui/components/chat.py chat_ui/chat_ui/components/bubbles.py chat_ui/chat_ui/components/shell.py` must be **empty**. Paste it. A screenshot proves the six render; the diff proves nothing was changed to make them.
  - `git diff d3e6279 -U0 -- chat_ui/chat_ui/theme.py | grep '^-[^-]'` must print nothing — PRD-006 was permitted to *add* tokens to the shared theme, never to retune one the chat already used.
- **Mirror**: `.agents/reports/PRD-004-chat-ui-redesign/STORY-019-six-outcome-regression-verification.report.md` — the walkthrough this one re-runs a PRD later.
- **Validate**: six outcomes rendered and screenshotted; the chat-module diff empty; the theme diff additions-only.

### Task 8: Restore the environment the chat checks perturbed, then re-confirm the console

- **File**: none (process)
- **Action**: VERIFY
- **Implement**:
  - Task 7 deliberately broke the upstream credential and locked the database. Undo both, restart the server per the skill, and re-confirm that a cleared send and the console's two pages still work — otherwise Task 12's "restored" claim rests on an unverified environment.
  - Re-read `chat_ui/.env` and confirm it is byte-identical to what Task 7 started with (it is gitignored, so git will not catch a drift here — diff it against a copy taken before Task 7).
- **Validate**: `.env` unchanged; a cleared send succeeds; both console pages render.

### Task 9: The negative-space check — nothing outside the intended surface moved (AC 2, 3, 4)

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**:
  - `git status --porcelain` — the working tree at this point should carry only Task 10's new test file and the `.agents/` writes. Anything else is Task 12's problem and must be resolved before the commit.
  - `git diff d3e6279 --name-only` piped through a filter for the forbidden paths (`^app/`, `requirements.txt`, `Caddyfile`, `rxconfig.py`, the six pinned test files, the seven chat modules) → must print nothing. Paste the command and its empty output.
  - `git diff d3e6279 --stat -- tests/` → expected: the admin test files this PRD created, plus `test_copy.py` and `test_contrast.py`, and **nothing else**. Confirm `test_db.py` and `test_chat_state.py` are absent from that list — which is the precise form in which AC 1's *"passing unmodified"* is true.
  - The one deletion in `test_contrast.py` (`git diff d3e6279 -- tests/test_contrast.py | grep '^-[^-]'` → one line, `-keeps every ink above the line as the palette evolves.`) is a **docstring rewording, not a removed assertion**. State it explicitly with the line quoted, and note that Task 10's function-census layer is what proves the general case rather than this one inspection.
- **Validate**: the forbidden-path filter prints nothing; the `tests/` diff contains only the expected files; the docstring deletion is explained.

### Task 10: Pin the claim so it is re-checked, not remembered

- **File**: `tests/test_untouched_app.py`
- **Action**: CREATE
- **Implement**: this story's entire output is otherwise a document, and a document does not fail when someone adds a database function next month. Mirror `tests/test_pii_redaction_integration.py:256-317` in shape, with the corrections this PRD's baseline requires:
  - A module docstring stating **why the baseline is a pinned SHA and not `merge-base main HEAD`**: the epic branch carries two PRDs' work, `main` is still at the PRD-003 merge, and `3f553f2` is PRD-004-era drift under `app/` that PRD-006 did not cause and is not permitted to fix. Name the commit and the story. This docstring is the durable home of the Task 3 reconciliation — a reader hitting a failure here needs it more than the report does.
  - `_BASE = "d3e6279"` as a named constant with the comment that it is the parent of `577a285`, PRD-006's first commit.
  - `test_no_file_under_app_changed_since_prd_006_began` — `git diff --name-only _BASE -- app/` is empty. This is AC 2 as a test.
  - `test_no_new_dependency_in_either_requirements_file` — both requirements files unchanged since `_BASE`. AC 3.
  - `test_the_caddyfile_and_rxconfig_are_unchanged` — AC 4.
  - `test_the_chat_modules_are_unchanged_since_prd_006_began` — the seven modules from Task 7. AC 6's diff half.
  - `@pytest.mark.parametrize` over the six Section 15 suites that must be **byte**-unmodified (`test_admin_auth`, `test_audit_router`, `test_stats_router`, `test_db`, `test_route_reservations`, `test_chat_state`) — AC 1's first half.
  - `test_no_assertion_was_removed_from_the_two_extendable_suites` — the census layer, over `test_copy.py` and `test_contrast.py` only: every `def test_*` present at `_BASE` is still present now. Byte-equality is the wrong assertion for these two (this PRD was allowed to extend them), and their absence from the parametrized list is exactly why the census is needed. Mirror `test_no_pre_epic_test_function_was_removed_or_renamed`'s `_TEST_DEF` regex and `git show {base}:{path}` mechanics.
  - `pytest.skip` when git or the history is unavailable, exactly as the source guard does — the tests must not fail in a shallow clone or an exported tree.
  - Every test's docstring names the AC it carries, in the house style.
- **Mirror**: `tests/test_pii_redaction_integration.py:256-317` throughout.
- **Validate**: `python -m pytest -q tests/test_untouched_app.py` green; **and each guard demonstrated to fail** — touch a file under `app/`, run, see red, revert. *"A guard nobody has watched fail is a guard nobody knows is armed"* (`tests/test_admin_palette.py`). Record the demonstration in the report.

### Task 11: Re-run the full suite with the guard in place

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: `python -m pytest -q` from the repo root. Expected: 848 + the number of tests Task 10 added, all passing. Re-run the eight-suite command from Task 1 as well, since Task 10's guard is now asserting things about those exact files and a contradiction between the two runs is a real finding.
- **Validate**: exit 0; the new total recorded and reconciled against 848 + N.

### Task 12: Stop the server and restore everything the pass borrowed

- **File**: `chat_ui/harness_ai.db`, `chat_ui/reflex.lock/`, `chat_ui/reflex.log`, `chat_ui/.env`
- **Action**: RESTORE
- **Implement**:
  - Stop the server by signalling the **listening** PID only, using the port read from `reflex.log` in Task 5: `netstat -ano | findstr LISTENING | findstr ":<port>"` → `taskkill /PID <pid>`. **Never by image name** — the skill's warning about not killing the user's browser applies with more force when the matching is coarser.
  - Restore `chat_ui/harness_ai.db` from the Task 4 backup, then delete the backup. Confirm the seeded rows are gone (`count_audit_logs()` back to its pre-seed value).
  - `git checkout -- chat_ui/reflex.lock` — modified by the production build, not by this story.
  - Remove `chat_ui/reflex.log`, or confirm it is ignored.
  - Confirm `chat_ui/.env` matches the Task 8 copy.
  - Final `git status --porcelain` must list only `tests/test_untouched_app.py` and the `.agents/` writes.
- **Validate**: `git status --porcelain` is exactly the expected set; the console database is at its pre-seed row count; no `reflex` process remains on the port.

### Task 13: Write the report

- **File**: `.agents/reports/PRD-006-admin-console/STORY-020-untouched-app-regression.report.md`
- **Action**: CREATE
- **Implement**: house style (see any STORY-0NN report), with the sections this story specifically owes:
  - **The diff evidence**, verbatim, in fenced blocks — every command from Tasks 2, 3, 7 and 9 with its literal output. This is AC 2's Technical Note discharged.
  - **The AC-2 reconciliation** as a Deviation: the literal AC, the measured result against `MAIN`, the attribution to `3f553f2`, the clean result against `BASE006`, and why nothing was fixed.
  - **The Section 11 walkthrough**, all fourteen checkboxes, each with a measured value (Task 6), plus the three-answer paragraph.
  - **The six chat outcomes** with their tags and screenshots (Task 7).
  - **The guard**, what it asserts, and the demonstration that each assertion fails when violated (Task 10).
  - **Follow-ups**: whatever Task 3 concluded about `3f553f2`, and any `app/` defect observed and deliberately not fixed. If none, say so — an empty follow-up list is a finding.
- **Validate**: every AC in the story maps to a named section of the report.

---

## End-to-End Tests

Run against the live production server with the ~120-row seeded database. Each
line records a measured value in the report, not a tick.

- [ ] `reflex compile --dry` clean; server up; port read from `reflex.log`'s `App running at:` line
- [ ] `/admin`, `/admin/audit`, `/admin/stats` all render; `/admin` lands on the register
- [ ] Unauthenticated on both pages: gate shown **and** `AdminState.rows` empty in the serialized state
- [ ] Empty, wrong, wrong-length and whitespace tokens all produce the identical refusal string
- [ ] Correct token loads the register; sign-out empties rows **and** figures from state
- [ ] Cap line states 100 against the true total, and the two numbers differ
- [ ] One row of each verdict renders its own ink and tag; no two share a treatment
- [ ] A fault row's disclosure shows its `error_message` verbatim
- [ ] Verdict filter and free-text filter both narrow the table, with **no** database read issued
- [ ] The `#audit_id` from Task 7's real chat success footer resolves to exactly one register row
- [ ] All nine `StatsResponse` figures present, each with its scope text quoted
- [ ] The completion label quoted off the live screen, blocked-inclusive wording intact
- [ ] `pii_detected_queries` and `top_pii_entities` both visible with values
- [ ] Database locked → fault panel with its named read and a retry; lock released → retry recovers
- [ ] No Task 4 preview sentinel in `outerHTML` on either page at ~120 rows
- [ ] The three answers — what was blocked, what failed, how much touched PII — written down, each sourced to an on-screen element, with no terminal used
- [ ] Chat: all six outcomes rendered and screenshotted, each with its distinct tag
- [ ] Chat: `git diff d3e6279 --stat` over the seven chat modules is empty
- [ ] `git diff d3e6279 -U0 -- theme.py | grep '^-[^-]'` prints nothing
- [ ] Environment restored (`.env`, database, `reflex.lock`, port free) and re-verified

## Validation

```bash
# the suite
python -m pytest -q
python -m pytest -q tests/test_admin_auth.py tests/test_audit_router.py \
  tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py \
  tests/test_chat_state.py tests/test_copy.py tests/test_contrast.py
python -m pytest -q tests/test_untouched_app.py

# AC 2 — literally as written, pasted whole into the report
git diff main --stat
git diff main --stat -- app/          # NON-EMPTY: 3f553f2, PRD-004-era, see Task 3
git diff main -- app/

# AC 2 — the claim this story makes, against PRD-006's own baseline
git diff d3e6279 --stat -- app/       # EMPTY
git diff d3e6279 --name-only -- app/ | wc -l    # 0
git log --oneline main..HEAD -- app/  # exactly one line: 3f553f2

# AC 3, AC 4
git diff main --stat -- requirements.txt chat_ui/requirements.txt   # EMPTY
git diff main --stat -- Caddyfile chat_ui/rxconfig.py               # EMPTY

# AC 6 — the chat, by diff as well as by eye
git diff d3e6279 --stat -- chat_ui/chat_ui/state.py chat_ui/chat_ui/copy.py \
  chat_ui/chat_ui/formatting.py chat_ui/chat_ui/models.py \
  chat_ui/chat_ui/components/chat.py chat_ui/chat_ui/components/bubbles.py \
  chat_ui/chat_ui/components/shell.py                               # EMPTY
git diff d3e6279 -U0 -- chat_ui/chat_ui/theme.py | grep '^-[^-]'    # prints nothing

# compile + run, per the reflex-process-management skill (from chat_ui/)
cd chat_ui && reflex compile --dry
cd chat_ui && reflex run --env prod --single-port 2>&1 | tee reflex.log
```

> **Known and reconciled, not a surprise to be rediscovered at implement time.**
> `git diff main --stat -- app/` is **not** empty on this branch. `app/db/database.py`
> and `app/db/models.py` differ from `main` because of `3f553f2`
> (Nahuel Escalante, 2026-08-28) — a PRD-004-era PII column migration that landed
> *after* PRD-004's own STORY-019 certified `app/` clean and *before* PRD-006's
> STORY-001. `main` is still at the PRD-003 merge (`56a3781`) and is therefore the
> branch point of PRD-004, not of this PRD. STORY-015, STORY-017 and STORY-019 each
> recorded this and deferred it here. **Do not fix it**: PRD Section 4 puts every
> change under `app/` out of scope and this story's Technical Note says so directly.
> Run both baselines, attribute the hunks, record the deviation.

---

## Risks + Mitigations

**1. The temptation to make AC 2 true by editing `app/`.**
The literal AC fails against `main`, and reverting two files would make it pass.
*Mitigation*: forbidden three times over — PRD Section 4, the story's Technical
Note, and this plan's "Files that must NOT change". Task 3 records the deviation
instead. A revert would also break `tests/test_db.py`, which this PRD promises not
to touch and which now covers the migration.

**2. The seeded database is the user's real console database.**
`chat_ui/.env` points `DATABASE_URL` at `chat_ui/harness_ai.db`, and Task 4 writes
~120 sentinel-bearing rows into whatever that resolves to.
*Mitigation*: back up before the first write (Task 4), restore and verify the row
count after (Task 12). The seed script prints its target path before writing.

**3. A live upstream call costs money and can fail for unrelated reasons.**
AC 6's *cleared* outcome needs a real model response.
*Mitigation*: exactly one real send (Task 7), and it does double duty — its
success-footer `#audit_id` is what Task 6's checkbox 9 resolves. The other five
outcomes need no upstream call at all: two are pre-model pipeline arms, two are
forced by breaking the credential or locking the database.

**4. Killing the wrong process on Windows.**
The skill's `lsof` idiom does not exist here, and the coarse alternatives match
too much.
*Mitigation*: the `netstat`/`taskkill` adaptation in Skills In Use, keyed to the
port read from `reflex.log` and filtered to `LISTENING`. Never by image name.

**5. A guard pinned to a hardcoded SHA rots or misleads.**
`_BASE = "d3e6279"` is opaque a year from now, and a rebase would orphan it.
*Mitigation*: the constant carries a comment naming it as `577a285`'s parent, the
module docstring explains why a derived base answers the wrong question, and the
guard skips rather than fails when the history is unavailable — the same
concession `tests/test_pii_redaction_integration.py` already makes.

**6. "Verified" without a number.**
The failure mode of every verification story: fourteen ticks that record only that
someone looked.
*Mitigation*: every E2E line above names the value to record, and Task 13 makes the
report's structure follow the ACs one to one.

**7. A genuine `app/` defect surfaces mid-pass.**
*Mitigation*: record as a follow-up in PRD Section 13, never fix. Section 13 already
carries the three known ones; do not restate them.

---

## Acceptance Criteria

(Copied from story `STORY-020`)

- [ ] Given the full test suite, when it runs, then it is green — including `tests/test_admin_auth.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_db.py`, `tests/test_route_reservations.py`, `tests/test_chat_state.py`, `tests/test_copy.py` and `tests/test_contrast.py`, each passing **unmodified** except where this PRD's own stories added assertions to `test_copy.py` and `test_contrast.py`.
- [ ] Given `git diff main --stat`, when it is run, then **no file under `app/` is changed** — no new database function, no query parameter, no schema migration, no change to `AuditQueryEntry` or `StatsResponse`. *(Carried against `BASE006`; the `MAIN` residual is attributed to `3f553f2` and recorded as a deviation — Task 3.)*
- [ ] Given both `requirements.txt` files, when they are diffed against `main`, then neither has a new dependency.
- [ ] Given the `Caddyfile` and `chat_ui/rxconfig.py`, when they are diffed, then neither is changed.
- [ ] Given the MVP walkthrough, when it is performed end to end, then an admin can open `/admin/audit`, enter the token, and answer "what was blocked, what failed, and how much of it touched PII" without a terminal — every Section 11 functional checkbox verified and recorded.
- [ ] Given the chat surface, when it is exercised through its six outcomes, then it behaves exactly as PRD-004 shipped it.
- [ ] All tasks completed
- [ ] `python -m pytest -q` passes
- [ ] `reflex compile --dry` clean and both console views render without error
- [ ] No file under `app/`, no requirements file, no `Caddyfile`, no `rxconfig.py` and no chat module changed by this story
- [ ] Follows existing patterns
