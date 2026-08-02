---
story: STORY-008
prd: PRD-003
slug: dedup-pattern-isolation-tests
title: "Tests: redaction cannot affect dedup/pattern-check behavior"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-08-01
---

# Plan: Tests — redaction cannot affect dedup/pattern-check behavior

## Summary

This story writes **no application code**. It is the epic's proof obligation: PRD RF-6 promises that `duplicate_checker.py` is untouched and that the dedup hash is always computed over raw text, and right now that promise rests on the *absence* of a change rather than on anything that fails when the change appears. One test file — `tests/test_pii_dedup_isolation.py` — turns it into an executable guarantee.

The hazard is real and measured, not hypothetical. Probing this branch's actual redactor:

```
redact("contact me at a@x.com") -> ('contact me at <EMAIL_ADDRESS>', ['EMAIL_ADDRESS'])
redact("contact me at b@y.com") -> ('contact me at <EMAIL_ADDRESS>', ['EMAIL_ADDRESS'])
hash_prompt(redacted_a) == hash_prompt(redacted_b)   -> True    # the collision
hash_prompt(raw_a)      == hash_prompt(raw_b)        -> False   # what saves us
```

Two customers' distinct prompts are byte-identical after masking. If any future change ever routes redacted text into `check_duplicate()` or `log_query(prompt=...)`, the second customer's legitimate request is silently blocked as a "duplicate" of the first — a data-loss bug with no error message, no log line, and no way for the user to tell what happened. The first two tests in this file pin *both halves* of that measurement, so the suite says out loud why the rest of the file exists.

Coverage is deliberately scoped to what the existing 155-test suite does **not** already assert. [[STORY-005]] and [[STORY-006]] already left four relevant tests in `tests/test_query_router.py` (raw text reaches both checks; `redact` is not invoked on either blocked path; the audit row keeps the raw prompt). This story does not restate them (Design Note 3). It adds the four things nothing currently covers: the **collision scenario end-to-end**, a **module-integrity guarantee** for `duplicate_checker.py` / `pattern_detector.py`, pattern-blocking-before-redaction across **all seven** blocklist entries rather than one, and a **call-site census** for `hash_prompt()` that fails when a fourth call site appears.

The story's Technical Notes float two ways to prove "byte-for-byte unmodified" — a literal `git diff`, or a behavioural/signature pin. Design Note 4 takes **both**, because each covers the other's blind spot: the git check catches a reformat or a comment that a behavioural pin would sleep through, and the behavioural pin survives the epic being squash-merged, exported to a tarball, or run where `git` is absent. Neither alone is the guarantee RF-6 describes.

## User Story

As a security admin
I want duplicate-detection behavior completely unaffected by redaction
So that two legitimately distinct requests from different users are never conflated because their redacted text happens to look identical (PRD User Story 6, RF-6)

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-008-dedup-pattern-isolation-tests.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — User Story 6, Section 9 (RF-6 / RF-7), Section 12 Phase 3, Section 8 (Testing), Section 11 ("Existing dedup/pattern test suite — 100% pass, unmodified")

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (test-only; no application code changes) |
| Complexity | MEDIUM |
| Systems Affected | `tests/test_pii_dedup_isolation.py` (new). **No `app/` file is modified by this story.** |
| Story | STORY-008 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repository (verified — the directory is absent), the story's `skills:` frontmatter field is `[]`, and PRD Section 15 states it explicitly ("Skills referenced: None"). Same finding as the [[STORY-001]] through [[STORY-007]] plans.

---

## Dependency Check

| Dependency | Status | Verified |
|---|---|---|
| [[STORY-006]] — Redact model response before returning to caller | ✅ done (`87c7ea8`) | `redacted_response, output_entities = redact(openrouter_result.response)` at `app/services/query_pipeline.py:84` — the output half of the pipeline this story tests around |

The single `depends_on` entry is `done` — no blocker, no user confirmation needed. Transitively: [[STORY-005]] (`c69a656`) inserted input redaction at `:57`; [[STORY-007]] (`61e402c`) added the response signal, bringing the suite to its current **155 passed** baseline.

This story `blocks: [STORY-010]` (end-to-end PII integration suite). The division of labour: STORY-008 proves what redaction must **not** touch; [[STORY-010]] proves what it **does**. Keep the collision/isolation assertions here so [[STORY-010]] can assume them rather than re-derive them.

---

## Patterns to Follow

### The pipeline under test — order is the whole guarantee

```python
# SOURCE: app/services/query_pipeline.py:27-57
    duplicate_result = check_duplicate(prompt)          # RAW  (step 2)
    ...
    pattern_result = detect_suspicious_pattern(prompt)  # RAW  (step 3)
    ...
    try:
        redacted_prompt, input_entities = redact(prompt)   # first masking (step 4-5)
```

Both blocked branches `return` at `:37` and `:51` — **before** line 57. That ordering is what makes "blocked before redaction ever runs" true today; Task 4 pins it so a reordering fails loudly instead of silently changing what gets hashed.

### `hash_prompt` — the function both subsystems share

```python
# SOURCE: app/services/duplicate_checker.py:22-27
def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def check_duplicate(prompt: str) -> DuplicateCheckResult:
    prompt_hash = hash_prompt(prompt)
```

```python
# SOURCE: app/services/audit_logger.py:31-34
        prompt_hash=hash_prompt(prompt),
        prompt_preview=prompt[:_PREVIEW_LENGTH],
        response_hash=hash_prompt(response) if response is not None else None,
        response_preview=response[:_PREVIEW_LENGTH] if response is not None else None,
```

Census of every `hash_prompt(` call in `app/`, measured on this branch:

| File | Call sites |
|---|---|
| `app/services/duplicate_checker.py` | 1 (line 27, inside `check_duplicate`) |
| `app/services/audit_logger.py` | 2 (lines 31, 33) |

**Three, and only three.** That census is itself an assertion in Task 5 — AC4 says "at every call site", which is only checkable if the set of call sites is known and pinned.

Note the two import styles, because they determine how the spies must be installed:
`audit_logger.py:6` does `from app.services.duplicate_checker import hash_prompt`, binding a *copy* into its own namespace — patch `audit_logger.hash_prompt`. `check_duplicate` resolves the module global — patch `duplicate_checker.hash_prompt`. Patching only one leaves the other silent.

### HTTP-level pipeline tests with a monkeypatched OpenRouter

```python
# SOURCE: tests/test_query_router.py:26-56
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")
```

This repo has **no `tests/conftest.py`** — every test module is standalone and redefines its fixtures and helpers locally. Follow that; do not introduce a conftest for this story (Design Note 8).

### Spying on a pipeline collaborator while keeping real behaviour

```python
# SOURCE: tests/test_query_router.py:211-226
def test_duplicate_and_pattern_checks_still_receive_the_raw_prompt(temp_db, monkeypatch):
    seen_duplicate = []
    real_check_duplicate = query_pipeline.check_duplicate

    def _spy_duplicate(prompt):
        seen_duplicate.append(prompt)
        return real_check_duplicate(prompt)

    monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_duplicate)
```

Capture-then-delegate, patched on the *module object* (`query_pipeline`) rather than a string target, because `query_pipeline.py:9-12` imports these names directly. Every spy in this story uses this exact shape.

### Env-var preamble every test module opens with

```python
# SOURCE: tests/test_duplicate_checker.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

`app.config.Settings` requires both, so this must precede any `app.*` import — non-negotiable, and the reason imports in these files are not top-sorted.

### Parametrizing over the real blocklist

```python
# SOURCE: tests/test_integration.py:83-100
@pytest.mark.parametrize("pattern", SUSPICIOUS_PATTERNS)
def test_each_suspicious_pattern_blocked_and_openrouter_never_called(
    temp_db, monkeypatch, pattern
):
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
    ...
    assert body["pattern"] == pattern
```

Import `SUSPICIOUS_PATTERNS` and parametrize over it rather than hard-coding seven strings — a future eighth pattern is then covered automatically.

### Entity constants proven against the real redactor

```python
# SOURCE: tests/test_query_router.py:182-183, 337-338
_PII_PROMPT = "my email is juan@empresa.com, can you draft a reply?"
_REDACTED_PROMPT = "my email is <EMAIL_ADDRESS>, can you draft a reply?"
_PII_RESPONSE = "Sure, I will draft a reply to juan@empresa.com for Maria Gomez."
_REDACTED_RESPONSE = "Sure, I will draft a reply to <EMAIL_ADDRESS> for <PERSON>."
```

Reuse this convention. This story's own pair (`_PROMPT_A` / `_PROMPT_B` and their shared redaction) was measured against the real redactor before planning — see the Summary — so no unproven PII strings are introduced.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_pii_dedup_isolation.py` | CREATE | The entire story: 14 test functions (20 collected, one is parametrized ×7) proving RF-6 across four themes |

**Explicitly NOT touched:**

- `app/services/duplicate_checker.py` — **this is the thing being guaranteed** (AC2, RF-6). Must remain absent from `git diff` against the epic base
- `app/services/pattern_detector.py` — same guarantee (AC3, story Technical Note 3)
- `tests/test_duplicate_checker.py` (8 tests) and `tests/test_pattern_detector.py` (10 collected) — AC2 requires they pass **unmodified**. Modifying them to accommodate this story would destroy the very claim being made
- `app/services/query_pipeline.py`, `app/services/audit_logger.py`, `app/services/pii_redactor.py`, `app/routers/query.py`, `app/models/schemas.py`, `app/db/models.py` — no application behaviour changes in this story. If a test here fails, the correct response is to **report a real RF-6 violation**, not to soften the test (Design Note 9)
- `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_audit_logger.py`, `tests/test_pii_redactor.py`, `tests/test_schemas.py`, `tests/test_chat_state.py` — all pass unmodified
- `tests/conftest.py` — deliberately not created (Design Note 8)
- `/audit` + `/stats` PII telemetry — [[STORY-009]]. End-to-end redaction assertions — [[STORY-010]]

---

## Design Notes (decisions worth stating up front)

1. **Test the hazard before testing the defence.** `test_two_pii_prompts_collide_after_redaction` asserts that `redact(A)[0] == redact(B)[0]` and that those redactions hash *identically*. It looks like it asserts a bug, and that is the point: without it, `test_distinct_pii_prompts_are_never_duplicates` could pass for years because the two prompts differ in some way unrelated to redaction, and no one would notice the guarantee had stopped being tested. Pinning the collision makes the following assertion load-bearing — and if a future Presidio upgrade ever masks the two emails *differently* (say, preserving the domain), this test fails first and tells the maintainer that the scenario needs a new prompt pair, rather than leaving a quietly hollow suite.

2. **A new file, not an extension of `tests/test_duplicate_checker.py`.** The story offers either. A new `tests/test_pii_dedup_isolation.py` wins for a reason specific to AC2: that file must pass **unmodified** to satisfy its own acceptance criterion. Adding PRD-003 tests to it would put the epic's fingerprints on the very file the epic promises not to disturb, and would force it to import `app.main`/Presidio — turning a fast, pure-unit module into one that loads a spaCy model. `tests/test_pattern_detector.py` has the same property. Keep both pristine; put the new work beside them.

3. **Do not restate coverage that already exists.** Every existing PRD-003 test was reviewed against this story's ACs before writing a single new one:

   | Already covered | Where | This story adds |
   |---|---|---|
   | Both checks receive the raw prompt | `test_query_router.py:211-235` | — (referenced, not duplicated) |
   | `redact` not invoked when duplicate-blocked | `test_query_router.py:253-263` | — |
   | `redact` not invoked when pattern-blocked (1 pattern) | `test_query_router.py:266-276` | **all 7 patterns**, with PII in the prompt |
   | Audit row keeps raw prompt + raw hash | `test_query_router.py:238-250` | the two-distinct-users variant |
   | All 7 patterns blocked before OpenRouter | `test_integration.py:83-101` | the same, but asserting **redaction** never ran |
   | Two distinct-but-collide prompts are not duplicates | **nowhere** | AC1 — the core of the story |
   | `duplicate_checker.py` / `pattern_detector.py` unmodified | **nowhere** | AC2 |
   | `hash_prompt` call-site census | **nowhere** | AC4 |

   The four "nowhere" rows are the story. Duplicating the others would inflate the count while proving nothing new.

4. **Prove "unmodified" two ways, because each covers the other's blind spot.** The story's Technical Note offers a `git diff` check *or* a behavioural/signature pin, and suggests preferring the latter. Take both:

   - **Git check** (`test_*_source_unmodified_on_this_branch`): `git diff --name-only $(git merge-base main HEAD) -- <path>` must be empty. Verified working on this repo (merge-base `ca56187`, empty output for both files, and the diff covers *uncommitted* working-tree changes too, so it catches a change before it is even committed). It self-scopes over time: once the epic merges, the merge-base advances and the test becomes "this branch didn't touch it" — still true, still meaningful, never a false alarm from history. **Skipped, not failed,** when `git` is unavailable or the merge-base cannot be resolved (tarball export, shallow clone, no `main` ref) — a missing tool is not evidence of a violation.
   - **Behavioural pin** (`test_hash_prompt_is_plain_sha256_of_utf8_text`, `test_check_duplicate_public_contract_is_stable`, `test_duplicate_checker_has_no_redaction_dependency`): survives squash-merge, rebase, vendoring, and CI without git history. It cannot see a reformat; the git check can. It can see a *semantic* change that preserved the file's name in a diff-free way (e.g. someone monkeypatching at import time); the git check cannot.

   Neither alone is the RF-6 guarantee. A file-content SHA-256 was considered and rejected: it fails on every whitespace or comment edit with an error message that tells the reader nothing about which promise broke.

5. **Assert the hash is over raw text at the *value* level, not just by inspection.** `test_hash_prompt_only_ever_receives_raw_text` installs capture-then-delegate spies on **both** binding sites (Patterns → `hash_prompt`) and runs one `run_query()` with PII in the prompt *and* the response. Expected recording, in order:

   ```
   [("duplicate_checker", RAW_PROMPT), ("audit_logger", RAW_PROMPT), ("audit_logger", RAW_RESPONSE)]
   ```

   Three calls, three raw strings, and separately: no captured argument contains `"<"` (no `<EMAIL_ADDRESS>`, no `<PERSON>`). The substring check is what actually encodes AC4 — the ordered-equality check is what catches a *fourth*, unexpected call appearing.

6. **The call-site census is counted per file, not per line.** `{"app/services/duplicate_checker.py": 1, "app/services/audit_logger.py": 2}` — line numbers drift on any unrelated edit and would make this a maintenance tax rather than a guard. The regex must exclude the definition itself (`def hash_prompt(`), which is why it is written with a negative lookbehind. When a future story legitimately adds a call site, this test fails with a message naming the new file — the correct outcome, since a new `hash_prompt` call is exactly the moment someone must re-check whether it is being handed raw text.

7. **Use `en_core_web_lg`, the configured default — do not swap in `en_core_web_sm`.** `tests/test_pii_redactor.py:13-18` has an autouse fixture pinning the small model for speed; that is right for unit-testing the redactor, and wrong here. This story asserts that the *shipped configuration* collides on redaction and survives it anyway. A different model could mask differently and make the test prove something about a config nobody runs. Cost measured: the full suite runs in ~28s today with the large model already loaded once per session; these tests add a handful of `redact()` calls to an already-warm singleton.

8. **No `tests/conftest.py`.** Six existing test modules each redefine `temp_db`, `_count_audit_rows`, and `_fail_if_called` locally. Introducing a shared conftest as a side effect of a test-only story would touch the collection behaviour of every module in the suite — including `test_duplicate_checker.py` and `test_pattern_detector.py`, which AC2 requires to be untouched. Duplicate the ~15 lines; it is the cheaper of the two costs.

9. **If a test in this file fails, that is a finding, not a flaky test to loosen.** These assertions have no tolerance by design: they are the mechanism by which RF-6 stops being a comment in a PRD. A failure means either (a) an epic change reached a file it promised not to touch, or (b) redacted text reached a hashing/dedup path. Both are ship-blocking for PRD-003 and must be reported in the story report, not accommodated.

10. **This story adds no application code and must not.** `git diff --name-only` at the end must list exactly one file: `tests/test_pii_dedup_isolation.py`. Any `app/` entry means the story went out of scope — most likely by "fixing" something a test surfaced, which per Design Note 9 belongs in its own story with its own report.

11. **Use `.venv/Scripts/python.exe` for every command.** [[STORY-003]]'s report (Deviation 1) recorded that bare `python` on this machine resolves to a global Python 3.13 without `presidio-analyzer`, producing collection errors in every module that transitively imports `app.main` → `app.services.pii_redactor`. Environment mismatch, not a code defect.

12. **Baseline to preserve: 155 passed** (`.venv/Scripts/python.exe -m pytest`, measured on this branch immediately before planning — matches [[STORY-007]]'s report). Target after this story: **175 passed** (155 + 20 collected: 13 plain tests + 7 parametrized cases). Zero existing tests modified.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the module preamble and pin the collision hazard

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: CREATE
- **Implement**: Module header, shared helpers, constants, and the two hazard tests (AC1, first half).

  ```python
  import os

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  import hashlib
  import inspect
  import pathlib
  import re
  import subprocess

  import pytest
  from fastapi.testclient import TestClient

  from app.config import settings
  from app.db.database import get_audit_log, get_connection, init_db
  from app.main import app
  import app.services.audit_logger as audit_logger
  import app.services.duplicate_checker as duplicate_checker
  import app.services.query_pipeline as query_pipeline
  from app.services.duplicate_checker import (
      DuplicateCheckResult,
      check_duplicate,
      hash_prompt,
  )
  from app.services.openrouter_client import OpenRouterResult
  from app.services.pattern_detector import SUSPICIOUS_PATTERNS
  from app.services.pii_redactor import redact
  from app.services.query_pipeline import run_query

  client = TestClient(app)

  # Two prompts from two different users, differing ONLY in the email address.
  # Both mask to the same text -- PRD User Story 6 / RF-6 is the promise that this
  # collision can never reach the dedup hash.
  _PROMPT_A = "contact me at a@x.com"
  _PROMPT_B = "contact me at b@y.com"
  _REDACTED_BOTH = "contact me at <EMAIL_ADDRESS>"

  _REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


  @pytest.fixture
  def temp_db(tmp_path, monkeypatch):
      db_path = tmp_path / "test.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
      init_db()
      return db_path


  def _count_audit_rows() -> int:
      with get_connection() as conn:
          row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
          return row["n"]


  def _fail_if_called(*args, **kwargs):
      raise AssertionError("this collaborator should not have been called")


  def _capturing_openrouter(seen: list, response: str = "ok"):
      def _call(prompt, model="gpt-4", api_key=None):
          seen.append(prompt)
          return OpenRouterResult(response=response, model_used=model, tokens_used=5)

      return _call


  def test_two_pii_prompts_collide_after_redaction():
      """The hazard RF-6 exists to prevent: distinct prompts, identical once masked."""
      redacted_a, entities_a = redact(_PROMPT_A)
      redacted_b, entities_b = redact(_PROMPT_B)

      assert redacted_a == _REDACTED_BOTH
      assert redacted_b == _REDACTED_BOTH
      assert entities_a == entities_b == ["EMAIL_ADDRESS"]
      # Hashing the REDACTED text would conflate two different customers.
      assert hash_prompt(redacted_a) == hash_prompt(redacted_b)


  def test_two_pii_prompts_hash_differently_on_raw_text():
      """The defence: the hash is taken over raw text, so the collision never lands."""
      assert _PROMPT_A != _PROMPT_B
      assert hash_prompt(_PROMPT_A) != hash_prompt(_PROMPT_B)
      assert hash_prompt(_PROMPT_A) != hash_prompt(_REDACTED_BOTH)
      assert hash_prompt(_PROMPT_B) != hash_prompt(_REDACTED_BOTH)
  ```

  Notes for the implementer:
  - The env-var preamble **must** precede every `app.*` import (Patterns → env-var preamble). Do not let an import-sorter hoist them.
  - `_REDACTED_BOTH` is a measured value, not a guess — confirmed against this branch's redactor with the configured `en_core_web_lg` (Design Note 7). Do not add the `en_core_web_sm` autouse fixture from `tests/test_pii_redactor.py`.
  - Some imports (`inspect`, `re`, `subprocess`, `pathlib`, `hashlib`, `DuplicateCheckResult`, `audit_logger`, `duplicate_checker`, `run_query`, `get_audit_log`, `SUSPICIOUS_PATTERNS`) are used by Tasks 2-5; declare them now so the file's header is written once.
- **Mirror**: `tests/test_query_router.py:1-56` (preamble, `temp_db`, `_count_audit_rows`, `_fail_if_called`), `:186-191` (`_capturing_openrouter`).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v
  ```
  → 2 passed. If `test_two_pii_prompts_collide_after_redaction` fails, the redactor's behaviour changed — stop and re-measure the prompt pair before continuing (Design Note 1).

### Task 2: Prove the collision never becomes a duplicate, end to end

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement**: Append the three pipeline-level AC1 tests.

  ```python
  def test_distinct_pii_prompts_are_never_duplicates_of_each_other(temp_db, monkeypatch):
      seen = []
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter(seen))

      first = client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A})
      second = client.post("/query", json={"user_id": "maria@empresa.com", "prompt": _PROMPT_B})

      assert first.json()["status"] == "SUCCESS"
      assert second.json()["status"] == "SUCCESS"
      # OpenRouter literally received the same bytes twice -- and dedup still let both through.
      assert seen == [_REDACTED_BOTH, _REDACTED_BOTH]
      assert _count_audit_rows() == 2


  def test_identical_pii_prompt_is_still_blocked_as_duplicate(temp_db, monkeypatch):
      """Control for the test above: dedup is not simply broken in the presence of PII."""
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))
      first = client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A})
      assert first.json()["status"] == "SUCCESS"

      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)
      second = client.post("/query", json={"user_id": "maria@empresa.com", "prompt": _PROMPT_A})

      body = second.json()
      assert body["status"] == "BLOCKED"
      assert body["reason"] == "Duplicate query within 24 hours"


  def test_audit_prompt_hashes_are_over_raw_text_not_redacted(temp_db, monkeypatch):
      monkeypatch.setattr("app.routers.query.call_openrouter", _capturing_openrouter([]))

      first = client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A})
      second = client.post("/query", json={"user_id": "maria@empresa.com", "prompt": _PROMPT_B})

      entry_a = get_audit_log(first.json()["audit_id"])
      entry_b = get_audit_log(second.json()["audit_id"])

      assert entry_a.prompt_hash == hash_prompt(_PROMPT_A)
      assert entry_b.prompt_hash == hash_prompt(_PROMPT_B)
      assert entry_a.prompt_hash != entry_b.prompt_hash
      assert entry_a.prompt_hash != hash_prompt(_REDACTED_BOTH)
      assert entry_a.prompt_preview == _PROMPT_A
      assert entry_b.prompt_preview == _PROMPT_B
  ```

  Notes for the implementer:
  - `assert seen == [_REDACTED_BOTH, _REDACTED_BOTH]` is the single most valuable line in the story: it shows the outbound text *was* identical, which is precisely why the raw-text hash is the only thing preventing a false duplicate.
  - The two requests use **different `user_id`s** to match PRD User Story 6's "two different customers". Dedup keys on prompt hash only, so this is narrative rather than functional — keep it anyway; it is what the PRD promises.
  - `test_identical_pii_prompt_is_still_blocked_as_duplicate` is a control, not filler. Without it, `test_distinct_pii_prompts_are_never_duplicates_of_each_other` would pass just as happily if dedup were disabled outright.
  - `temp_db` gives each test a fresh SQLite file, so the 24-hour window never leaks between tests.
- **Mirror**: `tests/test_integration.py:60-80` (first-then-second post with the mock swapped mid-test), `tests/test_query_router.py:238-250` (raw-preview/raw-hash audit assertions).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v
  ```
  → 5 passed.

### Task 3: Pin the dedup and pattern modules as unmodified

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement**: Append the AC2 module-integrity block — a git guard plus three behavioural pins (Design Note 4).

  ```python
  def _epic_base() -> str | None:
      """Merge-base with `main`, or None when git/history is unavailable."""
      try:
          result = subprocess.run(
              ["git", "merge-base", "main", "HEAD"],
              cwd=_REPO_ROOT,
              capture_output=True,
              text=True,
              timeout=30,
          )
      except (OSError, subprocess.SubprocessError):
          return None
      if result.returncode != 0:
          return None
      return result.stdout.strip() or None


  def _changed_since_epic_base(path: str) -> list[str]:
      base = _epic_base()
      if base is None:
          pytest.skip("git history unavailable; behavioural pins below still apply")
      result = subprocess.run(
          ["git", "diff", "--name-only", base, "--", path],
          cwd=_REPO_ROOT,
          capture_output=True,
          text=True,
          timeout=30,
      )
      assert result.returncode == 0, result.stderr
      return [line for line in result.stdout.splitlines() if line.strip()]


  @pytest.mark.parametrize(
      "path",
      ["app/services/duplicate_checker.py", "app/services/pattern_detector.py"],
  )
  def test_dedup_and_pattern_sources_unmodified_on_this_branch(path):
      """RF-6: this epic must not touch either module -- working tree included."""
      assert _changed_since_epic_base(path) == []


  def test_duplicate_checker_has_no_redaction_dependency():
      source = inspect.getsource(duplicate_checker).lower()

      assert "pii" not in source
      assert "redact" not in source
      assert "presidio" not in source
      assert set(vars(duplicate_checker)) & {"redact", "pii_redactor", "PiiRedactorError"} == set()


  def test_hash_prompt_is_plain_sha256_of_utf8_text():
      for text in (_PROMPT_A, _PROMPT_B, _REDACTED_BOTH, "", "acentuación y emoji 🙂"):
          assert hash_prompt(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


  def test_check_duplicate_public_contract_is_stable():
      signature = inspect.signature(check_duplicate)

      assert list(signature.parameters) == ["prompt"]
      assert signature.parameters["prompt"].annotation is str
      assert signature.parameters["prompt"].default is inspect.Parameter.empty
      assert signature.return_annotation is DuplicateCheckResult
      assert [field.name for field in DuplicateCheckResult.__dataclass_fields__.values()] == [
          "is_duplicate",
          "first_query_at",
      ]
  ```

  Notes for the implementer:
  - `_changed_since_epic_base` **skips** rather than fails when git is unavailable (Design Note 4) — a missing tool is not evidence of a violation, and the three behavioural pins below it still run.
  - `git diff --name-only <base> -- <path>` compares base against the **working tree**, so an uncommitted edit is caught too. Verified on this repo: base `ca561879`, empty output for both files.
  - `test_duplicate_checker_has_no_redaction_dependency` is not decorative: it is what catches someone importing `redact` into `duplicate_checker.py` in a future story. Verified today — the module's source contains none of the three substrings, and its namespace has no overlap with the redactor's exports.
  - `check_duplicate`'s full signature string is `(prompt: str) -> app.services.duplicate_checker.DuplicateCheckResult`. Assert the **parts** rather than that string; the fully-qualified rendering is a Python-version detail, the parameter and return types are the contract.
  - `hash_prompt("")` is included deliberately: it pins that empty text is hashed rather than special-cased, which matters because `redact()` short-circuits on empty input (`pii_redactor.py:50`) while hashing does not.
- **Mirror**: `tests/test_integration.py:83-86` (parametrize over a module-level constant); `tests/test_pattern_detector.py:14-19` (deriving test cases from the source of truth rather than restating them).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v
  ```
  → 10 passed (5 + 2 parametrized git cases + 3 pins), no skips in this repo. Then confirm the guard is real rather than vacuous:
  ```bash
  cd f:/AI/harness-ai
  printf '\n# tripwire\n' >> app/services/duplicate_checker.py
  .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -k unmodified -q
  git checkout -- app/services/duplicate_checker.py
  git diff --name-only
  ```
  → the `-k unmodified` run must **FAIL** on the `duplicate_checker.py` case while the tripwire is present, then `git checkout --` restores the file and `git diff --name-only` prints nothing. A guard that cannot fail is not a guard.

### Task 4: Pin pattern blocking ahead of redaction, for every pattern

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement**: Append the AC3 tests.

  ```python
  @pytest.mark.parametrize("pattern", SUSPICIOUS_PATTERNS)
  def test_suspicious_pattern_with_pii_blocked_before_redaction(temp_db, monkeypatch, pattern):
      """Pattern blocking is unchanged from PRD-001: it wins, and nothing is analyzed."""
      monkeypatch.setattr(query_pipeline, "redact", _fail_if_called)
      monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

      response = client.post(
          "/query",
          json={
              "user_id": "juan@empresa.com",
              "prompt": f"please {pattern} and contact me at a@x.com",
          },
      )

      body = response.json()
      assert response.status_code == 200
      assert body["status"] == "BLOCKED"
      assert body["reason"] == "Suspicious pattern detected"
      assert body["pattern"] == pattern
      assert _count_audit_rows() == 1


  def test_pipeline_runs_both_checks_before_any_redaction(temp_db, monkeypatch):
      calls = []
      real_duplicate = query_pipeline.check_duplicate
      real_pattern = query_pipeline.detect_suspicious_pattern
      real_redact = query_pipeline.redact

      def _spy_duplicate(prompt):
          calls.append(("check_duplicate", prompt))
          return real_duplicate(prompt)

      def _spy_pattern(prompt):
          calls.append(("detect_suspicious_pattern", prompt))
          return real_pattern(prompt)

      def _spy_redact(text):
          calls.append(("redact", text))
          return real_redact(text)

      monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_duplicate)
      monkeypatch.setattr(query_pipeline, "detect_suspicious_pattern", _spy_pattern)
      monkeypatch.setattr(query_pipeline, "redact", _spy_redact)
      monkeypatch.setattr(
          "app.routers.query.call_openrouter", _capturing_openrouter([], response=_PROMPT_B)
      )

      response = client.post("/query", json={"user_id": "juan@empresa.com", "prompt": _PROMPT_A})

      assert response.status_code == 200
      assert [name for name, _ in calls] == [
          "check_duplicate",
          "detect_suspicious_pattern",
          "redact",
          "redact",
      ]
      # Both checks saw raw text; redaction only ever ran afterwards.
      assert calls[0][1] == _PROMPT_A
      assert calls[1][1] == _PROMPT_A
      assert calls[2][1] == _PROMPT_A
      assert calls[3][1] == _PROMPT_B
  ```

  Notes for the implementer:
  - The parametrized test differs from the existing `test_integration.py:83-101` in one decisive way: it patches `query_pipeline.redact` to `_fail_if_called`, so it fails if a future refactor moves redaction *ahead* of the pattern check. The existing test only guards the OpenRouter call.
  - Each prompt embeds real PII (`a@x.com`) alongside the blocklist phrase, so "blocked before redaction" is tested on text that genuinely would have been redacted.
  - No blocklist phrase is a substring of another (checked against all seven), so `body["pattern"] == pattern` is exact — see `tests/test_pattern_detector.py:36-42` for why list order otherwise matters.
  - `test_pipeline_runs_both_checks_before_any_redaction` is the ordering guarantee behind AC3 **and** AC4: it pins that exactly two `redact` calls happen, both after both checks, on prompt then response. The mock returns `_PROMPT_B` as the model response so the second `redact` argument is distinguishable from the first.
  - Patch on the **module object** `query_pipeline`, not the string path — `query_pipeline.py:9-12` binds these names directly.
- **Mirror**: `tests/test_query_router.py:211-235` (capture-then-delegate spies), `tests/test_integration.py:83-101` (parametrize over `SUSPICIOUS_PATTERNS`), `tests/test_query_router.py:266-276` (`redact` patched to fail on a blocked path).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v
  ```
  → 18 passed (10 + 7 parametrized + 1).

### Task 5: Audit every `hash_prompt` call site

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE
- **Implement**: Append the AC4 tests.

  ```python
  def test_hash_prompt_only_ever_receives_raw_text(temp_db, monkeypatch):
      seen = []
      real_hash = hash_prompt

      def _spy(label):
          def _hash(text):
              seen.append((label, text))
              return real_hash(text)

          return _hash

      # Two binding sites: audit_logger imported the name; check_duplicate uses the global.
      monkeypatch.setattr(duplicate_checker, "hash_prompt", _spy("duplicate_checker"))
      monkeypatch.setattr(audit_logger, "hash_prompt", _spy("audit_logger"))

      raw_response = "Sure, I will draft a reply to juan@empresa.com for Maria Gomez."

      def _fake_call(prompt, model="gpt-4", api_key=None):
          return OpenRouterResult(response=raw_response, model_used=model, tokens_used=9)

      result = run_query(
          user_id="juan@empresa.com",
          prompt=_PROMPT_A,
          device=None,
          model="gpt-4",
          openrouter_api_key=None,
          call_openrouter=_fake_call,
      )

      assert result.pii_redacted is True
      assert seen == [
          ("duplicate_checker", _PROMPT_A),
          ("audit_logger", _PROMPT_A),
          ("audit_logger", raw_response),
      ]
      # No masking placeholder was ever hashed, in either direction.
      assert all("<" not in text for _, text in seen)


  def test_hash_prompt_call_sites_are_exactly_the_three_audited_ones():
      """A new call site must fail here so it gets re-checked for raw-text input."""
      pattern = re.compile(r"(?<!def )hash_prompt\(")
      census = {}
      for path in sorted((_REPO_ROOT / "app").rglob("*.py")):
          count = len(pattern.findall(path.read_text(encoding="utf-8")))
          if count:
              census[path.relative_to(_REPO_ROOT).as_posix()] = count

      assert census == {
          "app/services/audit_logger.py": 2,
          "app/services/duplicate_checker.py": 1,
      }
  ```

  Notes for the implementer:
  - Both spies must be installed. Patching only `duplicate_checker.hash_prompt` misses the audit logger's two calls entirely, because `audit_logger.py:6` bound its own reference at import time (Patterns → `hash_prompt`).
  - This test drives `run_query()` directly rather than through `TestClient`, because it needs the returned model object (`result.pii_redacted`) to confirm redaction genuinely ran during the same request whose hashes it is auditing. Otherwise the assertion could pass trivially on a request where nothing was masked.
  - `assert all("<" not in text ...)` is the AC4 assertion proper; the ordered equality above it is what detects an unexpected fourth call.
  - The census excludes `def hash_prompt(` via negative lookbehind — without it, `duplicate_checker.py` counts 2 and the numbers stop meaning "call sites". Counts are per file, never per line (Design Note 6).
  - `.rglob("*.py")` will also walk `app/**/__pycache__/`, which contains no `.py` files — no filtering needed. Verified: the census on this branch is exactly the two entries asserted.
- **Mirror**: `tests/test_query_router.py:211-226` (capture-then-delegate), `.agents/plans/.../STORY-006` Task 5 (proving a change is invisible to what it must not touch).
- **Validate**:
  ```bash
  cd f:/AI/harness-ai && .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v
  ```
  → 20 passed. The file is complete: 14 test functions, 20 collected cases.

### Task 6: Full-suite regression and scope check

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Full suite green at **175 passed** (155 baseline + 20). A different number means either a test was accidentally modified or a new case was added beyond the plan.
  - `git diff --name-only` (plus untracked) lists **exactly one** file: `tests/test_pii_dedup_isolation.py`. No `app/` entry (Design Note 10), no `tests/conftest.py` (Design Note 8).
  - `tests/test_duplicate_checker.py` and `tests/test_pattern_detector.py` are byte-identical to the epic base and pass unmodified — AC2's literal wording.
  - `app/services/duplicate_checker.py` and `app/services/pattern_detector.py` absent from the diff against `git merge-base main HEAD` — the same check the suite now performs, run once by hand as a cross-check on the test itself.
  - No test in the new file is `xfail`, `skip`, or commented out (the two git tests must *run*, not skip, in this repo).
- **Mirror**: [[STORY-007]] plan Task 7 — same scope gate, adjusted file list.
- **Validate**:
  ```bash
  cd f:/AI/harness-ai
  .venv/Scripts/python.exe -m pytest
  .venv/Scripts/python.exe -m pytest tests/test_duplicate_checker.py tests/test_pattern_detector.py -v
  git status --porcelain
  git diff --name-only $(git merge-base main HEAD) -- app/services/duplicate_checker.py app/services/pattern_detector.py
  .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v -rs
  ```
  → 175 passed; the two legacy suites green and unmodified; `git status --porcelain` shows only `?? tests/test_pii_dedup_isolation.py`; the `git diff` prints nothing; `-rs` reports **no skipped tests**.

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v` → 20 passed, 0 skipped
- [ ] `.venv/Scripts/python.exe -m pytest` → full suite green, **175 passed** (baseline 155 + 20)
- [ ] `.venv/Scripts/python.exe -m pytest tests/test_duplicate_checker.py tests/test_pattern_detector.py -q` → green, and both files unmodified (AC2)
- [ ] `git status --porcelain` → only `?? tests/test_pii_dedup_isolation.py`
- [ ] Tripwire check — prove the module-integrity guard actually fails when violated, then restore:
  ```bash
  cd f:/AI/harness-ai
  printf '\n# tripwire\n' >> app/services/pattern_detector.py
  .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -k unmodified -q   # MUST FAIL
  git checkout -- app/services/pattern_detector.py
  .venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -k unmodified -q   # MUST PASS
  git status --porcelain
  ```
  → fails while the tripwire is present, passes after restore, working tree clean apart from the new test file
- [ ] Behavioural proof of AC1 against the real DB and the real redactor — two distinct users, colliding redactions, neither blocked:
  ```bash
  .venv/Scripts/python.exe -c "
  import os
  os.environ.setdefault('OPENROUTER_API_KEY','k'); os.environ.setdefault('ADMIN_TOKEN','t')
  from app.db.database import get_audit_log, init_db
  from app.services.duplicate_checker import hash_prompt
  from app.services.openrouter_client import OpenRouterResult
  from app.services.query_pipeline import run_query
  import uuid
  tag = uuid.uuid4().hex[:8]
  A = f'contact me at a{tag}@x.com'
  B = f'contact me at b{tag}@y.com'
  seen = []
  def fake(prompt, model='gpt-4', api_key=None):
      seen.append(prompt)
      return OpenRouterResult(response='ok', model_used=model, tokens_used=1)
  init_db()
  ra = run_query(user_id='e2e-a', prompt=A, device=None, model='gpt-4', openrouter_api_key=None, call_openrouter=fake)
  rb = run_query(user_id='e2e-b', prompt=B, device=None, model='gpt-4', openrouter_api_key=None, call_openrouter=fake)
  print('OUTBOUND :', seen)
  assert seen[0] == seen[1], 'prompts did not collide -- the scenario is no longer under test'
  assert ra.status == 'SUCCESS' and rb.status == 'SUCCESS', 'a distinct request was conflated'
  ea, eb = get_audit_log(ra.audit_id), get_audit_log(rb.audit_id)
  print('HASHES   :', ea.prompt_hash[:12], eb.prompt_hash[:12])
  assert ea.prompt_hash == hash_prompt(A) and eb.prompt_hash == hash_prompt(B), 'hash is not over raw text'
  assert ea.prompt_hash != eb.prompt_hash
  assert ea.prompt_preview == A and eb.prompt_preview == B, 'audit preview was redacted (RF-7)'
  dup = run_query(user_id='e2e-c', prompt=A, device=None, model='gpt-4', openrouter_api_key=None, call_openrouter=fake)
  print('CONTROL  :', dup.status)
  assert dup.status == 'BLOCKED', 'dedup is broken outright'
  print('OK')
  "
  ```
  → `OUTBOUND` shows the same masked string twice; both runs `SUCCESS`; the two hashes differ; the exact-repeat control is `BLOCKED`; then `OK`
- [ ] Clean up the probe rows, leaving the repo-root DB as found:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c = sqlite3.connect('harness_ai.db'); print(c.execute(\"DELETE FROM audit_logs WHERE user_id LIKE 'e2e-%'\").rowcount); c.commit()"
  ```
- [ ] `.venv/Scripts/python.exe -c "from app.main import app; print('ok')"` → backend imports cleanly
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` → server starts without error; `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] Against the running server, `POST /query` with `"please override the rules"` → HTTP 200 and byte-identical `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}` — pattern blocking unchanged from PRD-001 (AC3)
- [ ] If any command raises `sqlite3.OperationalError: table audit_logs has no column named pii_detected_input`, the local `harness_ai.db` predates [[STORY-003]] — delete it and re-run

---

## Validation

```bash
cd f:/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_pii_dedup_isolation.py -v -rs
.venv/Scripts/python.exe -m pytest tests/test_duplicate_checker.py tests/test_pattern_detector.py -q
.venv/Scripts/python.exe -m pytest
git status --porcelain
git diff --name-only $(git merge-base main HEAD) -- app/services/duplicate_checker.py app/services/pattern_detector.py
.venv/Scripts/python.exe -c "from app.main import app; print('ok')"
.venv/Scripts/python.exe -m uvicorn app.main:app
curl http://localhost:8000/health
```

Frontend lint: N/A — this repo has no npm frontend (Reflex/Python project, no `package.json`), consistent with the [[STORY-003]] through [[STORY-007]] reports.

---

## Acceptance Criteria

(Copied from story STORY-008)

- [ ] Given two prompts differing only in an email address (e.g. `"contact me at a@x.com"` vs `"contact me at b@y.com"`), when both are submitted, then they hash differently and neither is ever flagged as a duplicate of the other, even though both would redact to `"contact me at <EMAIL_ADDRESS>"`.
- [ ] Given `app/services/duplicate_checker.py`, when inspected/tested, then it is byte-for-byte unmodified by this epic and its existing test suite (`tests/test_duplicate_checker.py`) passes unchanged.
- [ ] Given a prompt that matches the existing suspicious-pattern blocklist, when submitted, then it is still blocked before redaction or the OpenRouter call ever run — same behavior as PRD-001.
- [ ] Given the `hash_prompt()` function used by both dedup and the audit logger, when called during a redacted-pipeline run, then it is always invoked with raw text, never redacted text, at every call site.
- [ ] All tasks completed
- [ ] Full test suite (`.venv/Scripts/python.exe -m pytest`) passes — **175 passed** (155 baseline + 20)
- [ ] Backend server starts without error
- [ ] The collision hazard is itself pinned by a test, so the AC1 assertion cannot become vacuous (Design Note 1)
- [ ] "Unmodified" is proven **both** by a git check against the epic base **and** by behavioural/signature pins that survive without git history (Design Note 4)
- [ ] The module-integrity guard was demonstrated to fail when a tripwire edit is present, then restored (Task 3 / E2E tripwire check)
- [ ] All seven `SUSPICIOUS_PATTERNS` entries are covered, each with PII in the prompt and `redact` patched to fail if called (AC3)
- [ ] The `hash_prompt` call-site census is asserted, so a fourth call site fails the suite and forces a re-audit (Design Note 6)
- [ ] `tests/test_duplicate_checker.py` and `tests/test_pattern_detector.py` pass **unmodified** and are absent from `git status`
- [ ] Exactly one file added — `tests/test_pii_dedup_isolation.py`; **no `app/` file changed** by this story (Design Note 10)
- [ ] No test in the new file is skipped in this repo (`-rs` reports none)
- [ ] Follows existing patterns (env-var preamble before `app.*` imports, locally-defined `temp_db`/`_count_audit_rows`/`_fail_if_called`, capture-then-delegate spies patched on the module object, parametrization over the real blocklist constant, no `conftest.py`)
