---
story: STORY-015
prd: PRD-010
slug: history-latency-measurement
title: "Measure added per-send latency of history assembly and per-turn redaction at 20 exchanges"
type: SPIKE
complexity: LOW
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-19
---

# Plan: Measure added per-send latency of history assembly and per-turn redaction at 20 exchanges

## Summary

Add one non-collected measurement script, `scripts/measure_history_latency.py`, that seeds a session with 20 answered exchanges into the local libSQL dev server, then times 30 sends through the **real** `chat_history.assemble`, the **real** `pii_redactor.redact` and the **real** `run_conversation` with a stub upstream, reporting p50/p95 for each layer next to the same figures for a single-turn send. The deliverable is the numbers, recorded in `.agents/reports/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.report.md`, and a verdict on PRD Section 11's quality indicator ("added latency per chat send at most one `messages_for` read plus per-turn redaction"). No production file is modified; if the indicator misses, the gap and its numbers open the redaction-cache follow-up in PRD Section 13.

## User Story

As a platform operator
I want the cost of sending history measured on real Presidio and a real libSQL read
So that we know whether PRD Risk 3 needs its redaction-cache follow-up before users hit it.

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — Sections 11 (Quality indicators), 13 (Future Considerations), 14 (Risk 3)

## Metadata

| Field | Value |
|-------|-------|
| Type | SPIKE |
| Complexity | LOW |
| Systems Affected | `scripts/` (new), `.agents/reports/` (new), PRD Section 13 (conditional) |
| Story | STORY-015 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`, whose description covers visual design of new or reshaped UI. This story writes a backend measurement script and a report; no `SKILL.md` matches. Story frontmatter `skills: []` confirmed. | none |

---

## Patterns to Follow

### Naming — `scripts/` bootstrap and CLI shape

```python
# SOURCE: scripts/manage_users.py:1-28, 100-107
import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings
from app.db.database import init_db, insert_user
...

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/migrate_to_turso.py:1-33` adds the house module docstring: what the script is, the PRD/story that asked for it, then a literal `Usage:` block. Follow that.

### Timing — the existing measurement idiom

```python
# SOURCE: tests/test_two_instance_smoke.py:217-228
def measured(work):
    """Runs work(), returning (result, elapsed_ms, statements-issued)."""
    statements = []
    real = database.get_connection
    database.get_connection = lambda: Recording(real(), statements)
    started = time.perf_counter()
    try:
        result = work()
    finally:
        database.get_connection = real
    elapsed_ms = (time.perf_counter() - started) * 1000
    return result, elapsed_ms, statements
```

House conventions this carries, which the script keeps:
- `time.perf_counter()`, milliseconds, **never asserted** as a pass/fail bound (`tests/test_two_instance_smoke.py:1225-1246`: durations are recorded and printed; only statement *counts* are asserted).
- A warm-up call before the timed window, because the first `redact()` in a process pays the spaCy model load (`tests/test_two_instance_smoke.py:1169-1173`).
- The same-host caveat stated next to the figures (`.agents/reports/PRD-007-turso-migration/STORY-011-stats-endpoint-batched.report.md:46-57`).

**Deviation, stated up front:** the repo has no p50/p95 anywhere and never imports `statistics`. AC 1 requires percentiles, so `statistics` and a documented nearest-rank p95 are new ground here. Additive, and confined to `scripts/`.

### Warming Presidio

```python
# SOURCE: app/services/pii_redactor.py:43-46, used as an autouse fixture at
# tests/test_pipeline_concurrency.py:81-94
def load() -> None:
    if not settings.PII_REDACTION_ENABLED:
        return
    _get_analyzer()
```

STORY-014's report quantifies the cost of forgetting this: 67.73 s to 61.70 s once warmed.

### Seeding a session with answered exchanges

```python
# SOURCE: tests/test_chat_history.py:67-97
def _exchange(session_id: str, question: str, answer: str, *, owner: str = "ana") -> int:
    """One answered exchange: the `assistant` row that holds both halves."""
    return _row(
        session_id,
        "assistant",
        owner=owner,
        prompt=question,
        content=answer,
        created_at=ONE_INSTANT,
    )
```

`assemble` reads **only** `kind == "assistant"` rows with a non-empty `prompt` (`app/services/chat_history.py:109-117`), so one exchange is one row carrying both halves.

### The stub upstream signature

```python
# SOURCE: tests/test_pipeline_concurrency.py:179
def _fast_upstream(messages, model="gpt-4", api_key=None) -> OpenRouterResult:
    return OpenRouterResult(response="ok", model_used=model, tokens_used=1)
```

Three arguments only — `run_conversation` forwards `params=` only when it is set (`app/services/query_pipeline.py:286-298`), so a 3-arg stub is safe as long as the script passes no `params`. (`run_query` has no `params` argument at all: `query_pipeline.py:359-376`.)

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/measure_history_latency.py` | CREATE | The measurement harness: seed, warm, time four arms, print the table. Named so bare `pytest -q` never collects it. |
| `.agents/reports/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.report.md` | CREATE | The deliverable: the numbers, the verdict against PRD Section 11, the caveats. |
| `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` | UPDATE *(conditional)* | Only if the measurement misses the Section 11 indicator: add the redaction-cache follow-up to Section 13 with the data. Not a production file. |
| `.agents/stories/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.md` | UPDATE | Frontmatter `plan`, `status`, `updated` (done by `/plan` Phase 5). |
| `.agents/PRDs/PRD-010-multi-turn-pipeline/index.md` | UPDATE | Regenerate the STORY-015 row (done by `/plan` Phase 5). |

**No production file is modified.** `app/`, `chat_ui/` and `tests/` are untouched — AC 4.

---

## Design notes that shape the tasks

Four facts about the pipeline determine how this must be measured. Each is verified in the source, not assumed.

1. **The duplicate check runs at Step 4, before redaction at Step 6** (`app/services/query_pipeline.py:226-284`). Thirty sends of the same conversation would return `QueryBlockedDuplicateResponse` from iteration 2 onward, skipping redaction and upstream entirely and yielding meaningless timings. **Every iteration must carry a unique final user turn** so `dedup_key(user_id, messages)` differs. The script asserts `QuerySuccessResponse` on every iteration and aborts loudly otherwise — a silently-blocked arm is the likeliest way this spike produces a wrong number.

2. **`redact()` is called `len(messages) + 1` times per send** — once per message in the loop at `query_pipeline.py:265-284`, plus once on the response at `:314`. At 20 exchanges that is 40 history messages + 1 new turn + 1 response = 42 analyses, against 2 for a single-turn send. This quantity is what Risk 3 is about.

3. **`assemble` is exactly one DB read** (`chat_history.py:109-117` → `chat_sessions.messages_for:324-342` → `database.list_chat_messages`), and `fit` is pure, with no I/O and no settings reads (`chat_history.py:178-196`). So arm (a) can be timed standalone against the live dev server, and `fit` is cheap enough to fold into arm (a) rather than given its own row.

4. **Limits are not in play at this size.** 41 messages is under `CONTEXT_MAX_MESSAGES` (100) and roughly 33 k characters is under `CONTEXT_MAX_CHARACTERS` (200 000) at 800 chars/message, so no iteration takes the context-limit arm and `fit` drops nothing. The script prints both actuals so the report can state this rather than assume it.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the script skeleton — docstring, bootstrap, argparse

- **File**: `scripts/measure_history_latency.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring in the house style: what this measures, that it belongs to PRD-010 STORY-015 and serves PRD Section 11 / Risk 3, that it is a spike and asserts no latency bound, and a literal `Usage:` block:
    ```
    Usage:

        python scripts/measure_history_latency.py
        python scripts/measure_history_latency.py --exchanges 20 --sends 30 \
                                                  --database-url http://127.0.0.1:8080
    ```
  - `REPO_ROOT` + `sys.path.insert` bootstrap **before** any `app.` import.
  - Resolve the database URL and set `os.environ["DATABASE_URL"]` **before** `from app.config import settings`, because `Settings()` is built at import time and `DATABASE_URL` has no default — `tests/conftest.py:42-61` does exactly this with `setdefault`. Precedence: `--database-url`, then `HARNESS_TEST_LIBSQL_URL`, then `http://127.0.0.1:8080`. This forces a small `_database_url(argv)` helper that peeks at `sys.argv` ahead of full argparse; comment why, so a later reader does not "tidy" the imports back above it.
  - Flags: `--exchanges` (default 20), `--sends` (default 30), `--database-url`, `--keep` (skip cleanup), `--user-id` (default `story015-bench`).
  - `_build_parser()` / `main(argv=None) -> int` / `sys.exit(main())`.
- **Mirror**: `scripts/manage_users.py:1-28, 77-107`; docstring style from `scripts/migrate_to_turso.py:1-33`.
- **Validate**: `python scripts/measure_history_latency.py --help` prints the usage and exits 0.

### Task 2: Corpus — realistic prompts, 300–800 characters, some with PII

- **File**: `scripts/measure_history_latency.py`
- **Action**: UPDATE
- **Implement**: a `_corpus()` helper returning deterministic question/answer text in the 300–800 character band (AC 1). Roughly one question in three carries PII that Presidio's configured entity list actually detects — `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `LOCATION` (`settings.PII_ENTITIES`, `app/config.py:82`) — so the redaction timing exercises the anonymizer path rather than only the early `(text, [])` return at `pii_redactor.py:64-65`. Assistant answers are ordinary prose: PRD Risk 3 claims assistant turns are "already placeholder text and cheap to analyse", and the report should be able to confirm or correct that claim with arm (b).
- **Mirror**: entity names from `app/config.py:82`; redaction behaviour at `app/services/pii_redactor.py:49-73`.
- **Validate**: a `--show-corpus` debug flag prints each string's length; every one falls in 300–800.

### Task 3: Seed — user, session, 20 answered exchanges

- **File**: `scripts/measure_history_latency.py`
- **Action**: UPDATE
- **Implement**: `_seed(user_id, exchanges) -> str` returning the `session_id`. Call `init_db()`, then `insert_user(User(user_id=..., role="user", token_hash=...))` tolerating an existing row (`IntegrityError` is already imported this way in `scripts/manage_users.py`), then `create_chat_session(user_id, "STORY-015 latency bench")`, then `exchanges` calls to `append_chat_message(StoredMessage(session_id=..., kind="assistant", prompt=<question>, content=<answer>), session_id, user_id)`. Guard: refuse to run unless the resolved `DATABASE_URL` points at a local host, unless an explicit opt-out flag is passed — this script writes rows, and a mis-set `.env` must not seed a real deployment.
- **Mirror**: `tests/test_chat_history.py:67-97`; `StoredMessage` fields at `app/db/models.py:261-295`.
- **Validate**: run with `--exchanges 2 --sends 1`; `assemble` returns 4 messages.

### Task 4: The timing harness — warm-up, arms, percentiles

- **File**: `scripts/measure_history_latency.py`
- **Action**: UPDATE
- **Implement**:
  - `pii_redactor.load()` once before any timing window (story Technical Notes), then **one discarded warm iteration of every arm** — the first libSQL round trip and the first anonymizer call are both outliers.
  - `_percentiles(samples)`: `statistics.median` for p50; nearest-rank for p95, `sorted(samples)[math.ceil(0.95 * n) - 1]`, with a comment naming the method so the report's numbers are reproducible. Carry `n` and `min` as well.
  - Four arms, `--sends` iterations each, each iteration timed with `time.perf_counter()` in milliseconds:
    - **(a) `assemble`** — `chat_history.assemble(identity, session_id)`, one live `messages_for` read. Time `fit(history, new_turn, settings.CONTEXT_MAX_MESSAGES, settings.CONTEXT_MAX_CHARACTERS)` inside the same window and say in the output that it is included.
    - **(b) redaction of all messages** — the loop from `query_pipeline.py:265-284` reproduced over the assembled 41 messages: `for m in messages: redact(m.content)`. Reproduced rather than imported, because Step 6 is not separately callable; the script must carry a comment citing `query_pipeline.py:265-284` so the two cannot drift silently.
    - **(c) whole `run_conversation` excluding upstream** — `run_conversation(identity, messages, device=None, model=<allowlisted>, openrouter_api_key=None, call_openrouter=_stub, session_id=session_id)`. The stub records its own `perf_counter` span into a mutable cell; the arm's sample is `total - stub_span`, which is how "excluding upstream" is honoured rather than hand-waved. Assert `QuerySuccessResponse` every iteration (design note 1).
    - **(d) single-turn baseline** — the same measurements for `[Message("user", new_turn)]`: no `assemble` (report as n/a, and note that the flag-off path does not read), redaction of 1 message, and `run_conversation` excluding upstream.
  - **Unique final turn per iteration** — suffix the question with a run nonce and the iteration index so `dedup_key` differs (design note 1). Keep the suffix short so the 300–800 character band still holds.
  - Print a report-ready block: a fenced summary of run parameters (exchanges, sends, message count, total characters, `CONTEXT_MAX_*`, `PII_*` settings, host, Python version) followed by a markdown table of `arm | n | min | p50 | p95` for multi-turn and single-turn side by side, plus the derived `added latency = (c) multi-turn p50 minus (c) single-turn p50`.
- **Mirror**: `tests/test_two_instance_smoke.py:217-228` for the timing idiom; `tests/test_pipeline_concurrency.py:179` for the stub.
- **Validate**: `python scripts/measure_history_latency.py --exchanges 2 --sends 3` completes, prints the table, and every arm reports n=3 with no blocked iteration.

### Task 5: Corroborate the "one `messages_for` read" claim with a statement count

- **File**: `scripts/measure_history_latency.py`
- **Action**: UPDATE
- **Implement**: wrap one **untimed** send in the `Recording` connection proxy so the script also prints the SQL statements issued by a history send against a single-turn send. AC 2's indicator is phrased as "one `messages_for` read plus per-turn redaction"; a statement list is what actually proves the *read* half, and the house rule is that counts are the assertable number while latency is context (`tests/test_two_instance_smoke.py:1225-1246`). Expect single-turn `SELECT users` → `SELECT audit_logs` → `INSERT audit_logs` (pinned by name at `tests/test_two_instance_smoke.py:1194-1201`), with the history path adding one `SELECT` from `chat_messages` issued by `assemble` **before** the pipeline call, not inside it.
- **Mirror**: `tests/test_two_instance_smoke.py:190-228` (`Recording` + `measured`). Copy the proxy into the script rather than importing from `tests/` — `scripts/` must not depend on the test tree.
- **Validate**: the printed statement lists match the expectation above. If they do not, that divergence is itself a finding for the report, not a reason to adjust the script until it agrees.

### Task 6: Cleanup

- **File**: `scripts/measure_history_latency.py`
- **Action**: UPDATE
- **Implement**: in a `finally`, remove the seeded chat session, its messages and the bench user's `audit_logs` rows, unless `--keep`. Thirty sends per arm write 60+ audit rows; leaving them behind inflates the next run's duplicate-check read. Print what was removed. If `app/db/database.py` exposes no delete path for a chat session, **say so in the report and print a warning** rather than reaching past the service layer — `tests/test_chat_sessions.py` enforces that nothing outside `app/services/chat_sessions.py` calls the store's session functions, and this script should respect that boundary even though the AST test only scans `app/` and `chat_ui/`.
- **Mirror**: existing public helpers in `app/db/database.py`; boundary rule from `tests/test_chat_sessions.py::test_no_module_outside_the_service_calls_the_store_session_functions`.
- **Validate**: run twice back to back; the second run's arm (a) p50 is not materially worse than the first's.

### Task 7: Run the measurement and capture the output

- **File**: — (execution, no file)
- **Action**: RUN
- **Implement**: confirm the libSQL dev server is up (`docker start harness-libsql-dev`; first-time command in `tests/conftest.py:26-32`), then:
  ```
  python scripts/measure_history_latency.py --exchanges 20 --sends 30
  ```
  Run it **twice**, keep the second run's figures and note both. Per the story's Technical Notes and the standing dev-server note, if timings look pathological, **restart the container before drawing conclusions** — do not bisect the code.
- **Validate**: output contains four arms at n=30, no blocked iteration, no exception.

### Task 8: Write the report

- **File**: `.agents/reports/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.report.md`
- **Action**: CREATE
- **Implement**: follow the STORY-014 report structure — YAML front matter (`story`, `prd`, `plan`, `epic_branch`, `commit`, `status`, `completed`), `# Implementation Report — STORY-015: ...`, the `**Plan**` / `**Epic Branch**` / `**Commit**` lines, then `## Summary`, `## Tasks Completed`, `## Validation Results`, `## Files Changed`, `## Deviations from Plan`, `## Tests Written`, `## Acceptance Criteria`. Add a `## Measured latency` section carrying:
  - the raw printed block in a fenced code block (the STORY-014 AC 5 precedent, that report's L66-84);
  - the p50/p95 table for arms (a), (b) and (c), multi-turn against single-turn;
  - the **verdict sentence** AC 2 requires, with numbers: whether added per-send latency is at most one `messages_for` read plus per-turn redaction;
  - the same-host caveat — figures run against a local libSQL container, so the DB half understates a remote endpoint while the redaction half does not change;
  - the run parameters (exchanges, sends, character totals, effective settings, host/Python).
- **Mirror**: `.agents/reports/PRD-010-multi-turn-pipeline/STORY-014-pipeline-concurrency-tests.report.md` (structure); `.agents/reports/PRD-007-turso-migration/STORY-011-stats-endpoint-batched.report.md:46-57` (perf table + caveat wording).
- **Validate**: every AC in the story has a row in `## Acceptance Criteria` with its evidence.

### Task 9 *(conditional)*: Open the redaction-cache follow-up if the indicator misses

- **File**: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md`
- **Action**: UPDATE — **only if** the measurement shows added latency exceeding the Section 11 indicator
- **Implement**: add a bullet to **Section 13 Future Considerations** naming a per-content redaction cache, with the measured numbers inline. This is the mitigation Risk 3 pre-authorises: "a per-content redaction cache is a documented follow-up if the measurement is poor". State the gap in the report too. If the indicator holds, **make no PRD edit** and say so explicitly in the report.
- **Mirror**: the existing bullet style in Section 13 (`PRD.md:508-517`).
- **Validate**: `grep -n "redaction cache" .agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — present if and only if the report says the indicator missed.

### Task 10: Prove nothing else moved

- **File**: — (validation)
- **Action**: RUN
- **Implement**: `pytest -q tests/` for the full suite, then `git status --short` and `git diff --stat` to show no file under `app/`, `chat_ui/` or `tests/` changed.
- **Validate**: suite green (AC 4); diff confined to `scripts/` and `.agents/`.

---

## End-to-End Tests

- [ ] libSQL dev server reachable at `http://127.0.0.1:8080` (`libsql.connect(...).execute("SELECT 1")`, per `tests/conftest.py:132-152`)
- [ ] `python scripts/measure_history_latency.py --help` exits 0 and prints the `Usage:` block
- [ ] `python scripts/measure_history_latency.py --exchanges 2 --sends 3` gives four arms at n=3, every result a `QuerySuccessResponse`
- [ ] `python scripts/measure_history_latency.py --exchanges 20 --sends 30` gives the full figures; the assembled conversation is 41 messages and stays under both `CONTEXT_MAX_*` limits (printed, not asserted)
- [ ] No iteration returns `QueryBlockedDuplicateResponse` — the unique-final-turn guard holds
- [ ] The statement list for a history send shows exactly one extra `SELECT` against `chat_messages` versus a single-turn send
- [ ] `pytest -q tests/` collects **no** test from `scripts/` (the script is not named `test_*.py`) and the suite is green
- [ ] Script run twice back to back: arm (a) does not degrade, so cleanup works

---

## Validation

```bash
# dev server (first-time command in tests/conftest.py:26-32)
docker start harness-libsql-dev

python scripts/measure_history_latency.py --help
python scripts/measure_history_latency.py --exchanges 2 --sends 3
python scripts/measure_history_latency.py --exchanges 20 --sends 30

pytest -q tests/
git diff --stat   # nothing under app/, chat_ui/, tests/
```

There is no linter or formatter in this repo; "validate" is pytest against the local libSQL dev server.

---

## Acceptance Criteria

(Copied from story `STORY-015`)

- [ ] Given a session with 20 answered exchanges (realistic 300–800 character prompts, some with PII), when 30 sends are timed against the local libSQL dev server with real `redact()` and a stub upstream, then the report records p50/p95 for (a) `assemble`, (b) redaction of all messages, and (c) the whole `run_conversation` excluding upstream, next to the same figures for a single-turn send.
- [ ] Given the measurement, when the added latency is at most one `messages_for` read plus per-turn redaction (PRD Section 11 quality indicator), then the report says so with numbers. If not, it states the gap and opens the redaction-cache follow-up in PRD Section 13 with the data.
- [ ] Given the measurement script, when it is committed, then it lives under `scripts/` (`scripts/measure_history_latency.py`), is excluded from the default pytest run, and is runnable with one documented command.
- [ ] Given the full suite, when this story lands, then it is green and no production file is modified.
- [ ] All tasks completed
- [ ] Follows existing patterns (`scripts/` CLI shape, `perf_counter` timing idiom, warm-up before timing, same-host caveat beside the figures)

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | **The duplicate check short-circuits an arm.** Step 4 precedes redaction at Step 6, so identical repeated sends return `BLOCKED_DUPLICATE` and skip everything the spike measures. | Unique final user turn per iteration (run nonce + index); assert `QuerySuccessResponse` on every iteration and abort loudly otherwise. |
| 2 | **A cold spaCy load is counted as latency.** The first `redact()` pays for `en_core_web_lg`; STORY-014 measured 67.73 s to 61.70 s from this alone. | `pii_redactor.load()` before the timing window, plus one discarded warm iteration per arm. |
| 3 | **libSQL dev server degrades under repeated runs**, producing pathological arm (a) figures. | Per the story's Technical Notes and the standing dev-server note: restart `harness-libsql-dev` and re-measure before drawing any conclusion. Report the second of two consecutive runs. |
| 4 | **`PII_REDACTION_ENABLED=false` or a missing model** makes `redact()` a no-op returning `(text, [])`, and the numbers meaningless. | Print the effective `PII_*` settings in the output header; abort with a clear message if redaction is disabled. |
| 5 | **The script gets collected by CI.** Bare `pytest -q` runs from the repo root (`.github/workflows/ci.yml:62`) and there is no pytest config, so a `scripts/test_*.py` would be collected — and would run without `tests/conftest.py`'s DB bootstrap. | Name it `measure_history_latency.py`. Verified by Task 10's suite run. |
| 6 | **Seeding a real database.** The script writes users, sessions, messages and audit rows. | Local-URL guard with an explicit opt-out flag, plus cleanup in `finally`. |
| 7 | **Audit-table growth skews the duplicate-check read** across arms within a run. | Cleanup between runs; report arms (a) and (b) alongside (c), so a DB-side drift shows up rather than hiding inside the total. |
| 8 | **Percentiles are new to this repo** and could be computed inconsistently with the report's prose. | Nearest-rank p95 named in a code comment and restated in the report; `n`, `min`, p50 and p95 all printed. |

---

## Out of scope

- **Optimisation.** The story is explicit: the deliverable is the numbers plus the script; any redaction cache is a follow-up commit under PRD Section 13, not this one.
- **README documentation.** AC 3 asks only that the script be "runnable with one documented command", satisfied by the module docstring's `Usage:` block and the report. The README's multi-turn documentation pass is STORY-018's scope, and touching it here would collide with that story.
