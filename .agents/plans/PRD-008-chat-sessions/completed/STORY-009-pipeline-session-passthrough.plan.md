---
story: STORY-009
prd: PRD-008
slug: pipeline-session-passthrough
title: "run_query threads session_id to all seven log_query call sites, blocked and failed included"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-04
---

# Plan: run_query threads session_id to all seven log_query call sites, blocked and failed included

## Summary

STORY-008 gave `log_query` a `session_id: Optional[str] = None` and wired it through `AuditLog`, `insert_audit_log` and `_row_to_audit_log`; every one of the seven callers in `app/services/query_pipeline.py` still writes `NULL` because none of them passes it. This story is that passthrough and nothing else: `run_query` gains `session_id: Optional[str] = None` appended **after** `call_openrouter` (so the router's keyword call and every positional call in the suites are untouched), and each of its six inline `log_query(...)` calls gains `session_id=session_id`. The seventh caller lives in `_deny`, which serves all three authorization arms, and it takes `session_id` as a **required** parameter rather than a defaulted one — the story's last AC is explicit that a closed-over or defaulted value is exactly how one of three arms silently stops passing it, whereas a required parameter turns a forgotten arm into a `TypeError` the suite raises immediately rather than a `NULL` nobody notices for a release. No behaviour changes when `session_id` is omitted: the same seven rows are written with the same fields, `session_id` `NULL`. `call_openrouter` is not touched, no validation is added (the UUID check and the 403 are STORY-010, at the router boundary), and the tests are written **per arm** — seven arms, seven assertions, plus a source-level census so an eighth arm added later cannot ship without one.

## User Story

As a compliance admin
I want the conversation named on every audit row a send can produce
So that the rows missing from a session's history are not exactly the interesting ones — the blocked, the denied and the failed.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-009-pipeline-session-passthrough.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Pipeline & API), Section 6 (send path), Section 11, Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `app/services/query_pipeline.py` (one file), `tests/` (one new suite) |
| Story | STORY-009 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

**Dependencies verified**: STORY-008 is `status: done` (commit `ea5aa9a`) — confirmed by reading `app/services/audit_logger.py:28`, where `session_id: Optional[str] = None` is the last parameter and reaches `AuditLog(..., session_id=session_id)` at line 49. Nothing blocks this story. It blocks STORY-010 (`QueryRequest.session_id` plus the 403) and STORY-013 (`ChatState` passing `session_id` into `run_query`); neither is touched here.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed fresh for this plan and holds exactly one entry, `frontend-design`. Its `SKILL.md` `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one", and its body is entirely palette, typography, layout and copy direction. This story edits `app/services/query_pipeline.py` and one test file, renders nothing, and adds no string a user reads. | None |

The story's frontmatter carries `skills: []` and its Technical Notes reach the same conclusion; the scan was re-run rather than inherited. `chat_ui/AGENTS.md`'s **reflex-docs** and **reflex-process-management** rules are likewise not engaged — no file under `chat_ui/` is opened by any task below.

---

## Patterns to Follow

### Naming — the optional passthrough parameter, keyword-defaulted, appended last

```python
# SOURCE: app/services/audit_logger.py:12-29
def log_query(
    user_id: str,
    prompt: str,
    device: Optional[str] = None,
    ...
    role: Optional[str] = None,
    denied_permission: Optional[str] = None,
    session_id: Optional[str] = None,
) -> int:
```

STORY-008 established the shape one layer down and PRD-005's `role` / `denied_permission` established it before that: `Optional[str] = None`, appended after everything already there, no existing call site edited. `run_query` follows the same rule — which in its case means appending after `call_openrouter`, not before it, so a caller that ever passes the injected client positionally keeps working.

### The existing call shape at the only production caller — keyword, so an appended parameter is invisible to it

```python
# SOURCE: app/routers/query.py:27-33
        return run_query(
            identity=identity,
            prompt=request.prompt,
            device=request.device,
            model=request.model,
            openrouter_api_key=request.openrouter_api_key,
            call_openrouter=call_openrouter,
        )
```

Untouched by this story. STORY-010 adds `session_id=request.session_id` here.

### Error/denial handling — the shared helper that serves three arms

```python
# SOURCE: app/services/query_pipeline.py:31-42
def _deny(
    identity: Identity, prompt: str, device: Optional[str], exc: PermissionDenied, reason: str
) -> QueryBlockedForbiddenResponse:
    log_query(
        user_id=identity.user_id,
        prompt=prompt,
        device=device,
        success=True,
        role=identity.role,
        denied_permission=exc.permission,
    )
    return QueryBlockedForbiddenResponse(reason=reason, required_permission=exc.permission)
```

Note `success=True` on a denial: a refusal is a successful *harness* outcome, and `tests/test_query_pipeline_authorization.py:93` pins it. That is not changed here.

### Tests — the arm-by-arm pipeline suite, with its fresh-row helpers

```python
# SOURCE: tests/test_query_pipeline_authorization.py:23-34
def _last_audit_id() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        return row["id"]


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)
```

### Tests — forcing the output-side redactor arm without touching the input side

```python
# SOURCE: tests/test_query_router.py:451-461
def _boom_on_second_call():
    real_redact = query_pipeline.redact
    calls = []

    def _redact(text):
        calls.append(text)
        if len(calls) == 1:
            return real_redact(text)
        raise PiiRedactorError("PII analysis failed: analyzer exploded on output")

    return _redact
```

`redact` is called twice in `run_query` — once on the prompt (line 99), once on the response (line 126). Raising on the first call reaches the input arm, on the second the output arm. This is the existing idiom; it is reused rather than reinvented.

### Tests — the census idiom, for "every arm, not just the ones I remembered"

```python
# SOURCE: tests/test_untouched_app.py:135-151
    gone = set(_TEST_DEF.findall(base_source)) - set(_TEST_DEF.findall(current_source))
    assert sorted(gone) == [], f"{path} lost test functions present at {_BASE}: {sorted(gone)}"
```

STORY-023 replaced byte-pinning with counting-what-matters. The same instrument answers this story's AC 2 — *seven* `log_query(` call sites, every one passing `session_id` — as a test rather than as a grep somebody runs once.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | `session_id` on `run_query` and on `_deny`; `session_id=session_id` on all seven `log_query(...)` calls |
| `tests/test_query_pipeline_session_passthrough.py` | CREATE | One assertion per arm (7), the omitted-value NULL cases, and the source census |

**Not changed, deliberately:**

| File | Why not |
|------|---------|
| `app/services/openrouter_client.py` | Story Technical Notes: `call_openrouter` is not touched and its `prompt: str` signature is not touched. PRD Section 4 lists multi-turn as out of scope. |
| `app/routers/query.py` | `QueryRequest.session_id`, the UUID validation and the 403 are STORY-010. `run_query`'s new parameter is defaulted, so the router keeps compiling and behaving identically. |
| `app/models/schemas.py` | Same — STORY-010 and STORY-011. |
| `chat_ui/chat_ui/state.py` | Passing `session_id` from `ChatState` is STORY-013. |
| `tests/test_query_pipeline_authorization.py`, `tests/test_integration.py`, `tests/test_query_router.py`, `tests/test_route_reservations.py` | Story AC 7 and PRD Section 11 require these to pass **unmodified**. They are run, not edited. |
| `tests/test_untouched_app.py` | Its two censuses assert that baseline test functions were not *removed*; adding a new suite is invisible to both, and `test_query_pipeline_authorization.py` appears in neither list. No update needed. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `_deny` takes `session_id` explicitly, as a required parameter

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE (lines 31-42)
- **Implement**:
  - Change the signature to `def _deny(identity: Identity, prompt: str, device: Optional[str], session_id: Optional[str], exc: PermissionDenied, reason: str) -> QueryBlockedForbiddenResponse:` — `session_id` sits with the other row fields it travels with, and carries **no default**.
  - Add `session_id=session_id,` to the `log_query(...)` call, last, after `denied_permission=`.
  - Add a short comment on the parameter recording *why* it is required and not closed over: the helper serves three arms, and a defaulted or captured value is how one arm silently stops passing it. This is the story's final AC stated in the code, where the next editor will read it.
- **Mirror**: `app/services/audit_logger.py:28,49` for the argument name and its last position in the `log_query` call; `app/services/query_pipeline.py:34-41` for the call's existing shape.
- **Note**: no default means the three call sites in Task 2 *must* be updated in the same edit — arity changes from 5 to 6, so a missed arm is a `TypeError` the suite raises immediately, not a `NULL` discovered in production. That is the intended failure mode.
- **Validate**: `python -c "import inspect, app.services.query_pipeline as q; p=inspect.signature(q._deny).parameters; print(list(p)); print(p['session_id'].default is inspect.Parameter.empty)"` → prints the six names and `True`.

### Task 2: `run_query` accepts `session_id` and hands it to the three denial arms

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE (lines 45-67)
- **Implement**:
  - Append `session_id: Optional[str] = None,` to `run_query`'s signature, **after** `call_openrouter`. Appending last preserves every positional call; `Optional[str] = None` matches `log_query`'s precedent and satisfies AC 1 and AC 7.
  - Update the three `_deny(...)` calls to pass it explicitly by keyword, so the argument's identity survives any future reordering:
    - line ~56 (missing `query:submit`) → `_deny(identity, prompt, device, session_id=session_id, exc=exc, reason="Missing required permission")`
    - line ~61 (model not permitted) → same shape, `reason="Model not permitted for this role"`
    - line ~67 (BYOK without `query:byok`) → same shape, `reason="Missing required permission"`
  - Do not add validation, a UUID check, an ownership check or a truthiness branch. `run_query` takes what it is given; the 403 is STORY-010 at the router boundary, and keeping validation out here is what keeps the in-process `ChatState` caller and the HTTP caller on one code path (PRD-002's arrangement, restated in the story's Technical Notes).
- **Mirror**: `app/routers/query.py:27-33` for the all-keyword call style; `app/services/audit_logger.py:12-29` for the appended-last defaulted parameter.
- **Validate**: `python -c "import inspect; from app.services.query_pipeline import run_query; p=inspect.signature(run_query).parameters; print(list(p)[-1], p['session_id'].default)"` → `session_id None`.

### Task 3: the three non-authorization blocking and failure arms pass `session_id`

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: add `session_id=session_id,` as the last keyword to each of these `log_query(...)` calls, leaving every other argument exactly as it is:
  - duplicate-blocked, line ~72 (after `success=True`)
  - pattern-blocked, line ~86 (after `success=True`)
  - input-side `PiiRedactorError`, line ~101 (after `error_message=str(exc)`)
- **Mirror**: `app/services/audit_logger.py:49` — `session_id` is last in the `AuditLog` construction, and last is where it goes at every call site too, so the seven calls stay visually identical to each other.
- **Note**: the `raise` after the input-redactor `log_query` stays. The row is written *before* the exception leaves the pipeline, which is why this arm produces an audit row at all — that ordering is what AC 5 depends on.
- **Validate**: `grep -c "session_id=session_id" app/services/query_pipeline.py` → `4` at this point (one from Task 1, three from here).

### Task 4: the remaining three arms — upstream error, output redactor, success

- **File**: `app/services/query_pipeline.py`
- **Action**: UPDATE
- **Implement**: add `session_id=session_id,` last to each:
  - `OpenRouterError`, line ~115 (after `error_message=str(exc)`)
  - output-side `PiiRedactorError`, line ~128 (after `pii_entities=input_entities`)
  - success, line ~144 (after `pii_entities=masked_entities`) — the call whose return value is `audit_id`, so the row the UI footer already names now also carries the session (AC 6)
- **Mirror**: same as Task 3.
- **Validate**: `grep -c "log_query(" app/services/query_pipeline.py` → `8` (one import line plus seven calls); `grep -c "session_id=session_id" app/services/query_pipeline.py` → `7`. AC 2 satisfied.

### Task 5: the per-arm test suite — seven arms, seven assertions

- **File**: `tests/test_query_pipeline_session_passthrough.py`
- **Action**: CREATE
- **Implement**: a module docstring naming PRD-008 STORY-009 and stating the rule the story insists on — *the test is written per arm, not per function, because one forgotten `session_id=` is invisible in the success path and the success path is the one everybody tests first*. Then the prologue and helpers copied from the sibling suite (the `os.environ.setdefault` pair, `_last_audit_id`, `_fail_if_called`, `_fake_call_openrouter`), a module-level `_SESSION_ID = "0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"` (the same UUID4 `tests/test_audit_logger.py:242` already uses, so the two suites read as one story), and one test per arm, each taking `temp_db` and each asserting `get_audit_log(...).session_id == _SESSION_ID`:

  1. `test_permission_denied_arm_carries_the_session_id` — `Identity(user_id="reviewer", role="auditor")`, `call_openrouter=_fail_if_called`. Also assert `isinstance(result, QueryBlockedForbiddenResponse)` so a test that stops reaching the arm fails loudly instead of asserting about the wrong row.
  2. `test_model_not_permitted_arm_carries_the_session_id` — `Identity("ana", "user")`, `model="not-a-real-model"`, `_fail_if_called`.
  3. `test_byok_denied_arm_carries_the_session_id` — `Identity("ana", "user")`, `openrouter_api_key="sk-caller-supplied"`, `_fail_if_called`.
  4. `test_duplicate_blocked_arm_carries_the_session_id` — the case the story calls the one that matters most. Send once with `_fake_call_openrouter` to seed the prompt hash into `audit_logs`, then send the identical prompt again with `session_id=_SESSION_ID`; assert `isinstance(result, QueryBlockedDuplicateResponse)` and that the newest row carries the id. Seed the first send with **no** `session_id`, so the assertion cannot pass by accidentally reading the seeding row.
  5. `test_pattern_blocked_arm_carries_the_session_id` — a prompt containing `"ignore previous instructions"` (`app/services/pattern_detector.py:5`), `_fail_if_called`; assert `QueryBlockedSuspiciousResponse`.
  6. `test_input_redactor_failure_arm_carries_the_session_id` — `monkeypatch.setattr(query_pipeline, "redact", _boom)` where `_boom(text)` raises `PiiRedactorError`; wrap the call in `pytest.raises(PiiRedactorError)`, then read the row that was written before the raise.
  7. `test_openrouter_failure_arm_carries_the_session_id` — a `call_openrouter` stub raising `OpenRouterError("upstream exploded")`; `pytest.raises(OpenRouterError)`, then read the row. Assert `entry.model_used == "gpt-4"` too, which is what distinguishes this arm's row from the input-redactor arm's.
  8. `test_output_redactor_failure_arm_carries_the_session_id` — `_boom_on_second_call()` per the mirror above; `pytest.raises(PiiRedactorError)`, then read the row. Assert `entry.success is False` alongside, to prove this is the output arm and not the input one.
  9. `test_success_arm_carries_the_session_id_on_the_row_the_footer_names` — `_fake_call_openrouter`, assert `QuerySuccessResponse` and read the row by `result.audit_id` rather than by `_last_audit_id()`, which is what ties AC 6 to the id the UI actually shows.
- **Mirror**: `tests/test_query_pipeline_authorization.py:1-34` (prologue plus helpers), `tests/test_query_router.py:294-295` (`_boom`), `tests/test_query_router.py:451-461` (`_boom_on_second_call`), `tests/test_audit_logger.py:237-248` (the round-trip assertion shape).
- **Validate**: `pytest tests/test_query_pipeline_session_passthrough.py -q` — nine tests, all green.

### Task 6: the omitted-value case — `NULL`, and nothing else moved

- **File**: `tests/test_query_pipeline_session_passthrough.py`
- **Action**: UPDATE
- **Implement**: two more tests covering AC 7.
  - `test_session_id_omitted_writes_null_on_every_arm` — parametrized over a small table of `(kwargs, expected_response_type)` covering the denial, duplicate, pattern and success arms with **no** `session_id` argument at all; assert `session_id is None` on each resulting row. This is the regression that protects every caller predating STORY-010 and STORY-013, and every API client that omits the field.
  - `test_omitting_session_id_leaves_the_rest_of_the_success_row_identical` — run the success arm twice on distinct prompts, once without `session_id` and once with it, and assert the two rows agree on `user_id`, `device`, `model_used`, `tokens_used`, `success`, `role`, `denied_permission`, `pii_detected_input`, `pii_detected_output` and `pii_entities` — differing only in `session_id`, `id`, `prompt_hash`, `prompt_preview` and `timestamp`. AC 7's "every other field is identical to the current release", asserted rather than assumed.
- **Mirror**: `tests/test_audit_logger.py:251-262` (`test_session_id_defaults_to_none_when_omitted`, including its docstring's framing).
- **Validate**: `pytest tests/test_query_pipeline_session_passthrough.py -q`.

### Task 7: the census guard — an eighth arm cannot ship without a `session_id`

- **File**: `tests/test_query_pipeline_session_passthrough.py`
- **Action**: UPDATE
- **Implement**: `test_every_log_query_call_site_in_the_pipeline_passes_session_id`. Read the module source with `inspect.getsource(query_pipeline)`, and:
  - assert there are exactly **seven** `log_query(` call sites — count occurrences of `log_query(` excluding the `from app.services.audit_logger import log_query` import line — matching AC 2's grep exactly;
  - assert every one of those seven passes the argument: `source.count("session_id=session_id") == 7`;
  - docstring: this is the guard for the defect the story says is most likely to ship. A later arm added without the argument moves one of the two counts and fails here, in a test named after the problem, rather than surfacing as a `NULL` in a compliance report months later.
- **Mirror**: `tests/test_untouched_app.py:135-151` — the census idiom STORY-023 established; and `tests/test_session_ownership.py` for the precedent of asserting a rule against source and signatures rather than against memory.
- **Validate**: `pytest tests/test_query_pipeline_session_passthrough.py -q` → eleven tests green; then temporarily delete one `session_id=session_id` from the pipeline, re-run, confirm this test **fails**, and restore it. A guard that has never been seen to fail is decoration.

### Task 8: prove the untouched suites are untouched

- **File**: — (verification only)
- **Action**: VERIFY
- **Implement**: run the four suites the story and PRD Section 11 pin, then the whole suite, then confirm the diff touches exactly two files.
- **Validate**:
  - `pytest tests/test_query_pipeline_authorization.py tests/test_integration.py tests/test_query_router.py tests/test_route_reservations.py -q` — green, with **no edit** to any of them
  - `pytest -q` — full suite green
  - `git status --porcelain` — exactly `app/services/query_pipeline.py` modified and `tests/test_query_pipeline_session_passthrough.py` added
- **Note**: a burst of fixture errors across many suites at once is the libSQL dev container degrading under repeated runs, not this change — restart `harness-libsql-dev` and re-run before investigating the diff.

---

## End-to-End Tests

- [ ] `grep -n "log_query(" app/services/query_pipeline.py` reports **seven** call sites (plus the import), and each one passes `session_id` — AC 2
- [ ] `run_query(..., session_id="<uuid4>")` on a **duplicate** prompt → the blocked row carries the `session_id` — AC 3, the case a user is most likely to ask about
- [ ] `run_query(..., session_id="<uuid4>")` with a pattern-matching prompt, a role lacking `query:submit`, a model outside the allowlist, and a BYOK key without `query:byok` → all four rows carry the `session_id` — AC 4
- [ ] A raising `redact` on the input side, a raising `call_openrouter`, and a raising `redact` on the output side → all three failure rows carry the `session_id`, and the exception still propagates — AC 5
- [ ] A successful send → `get_audit_log(result.audit_id).session_id` is the value passed, on the same row whose `audit_id` the chat footer already shows — AC 6
- [ ] `run_query(...)` with no `session_id` → `session_id` is `NULL` and every other audit field matches a pre-change run on the same fixture — AC 7
- [ ] `inspect.signature(_deny)` shows `session_id` with no default, and all three arms pass it by keyword — AC 8
- [ ] `tests/test_query_pipeline_authorization.py` and `tests/test_integration.py` pass **unmodified**; `git diff --stat` shows neither file
- [ ] `POST /query` through `tests/test_query_router.py` is unchanged end to end — the router does not yet send a `session_id` and must not have to

---

## Validation

```bash
pytest tests/test_query_pipeline_session_passthrough.py -q
pytest tests/test_query_pipeline_authorization.py tests/test_integration.py -q
pytest tests/test_query_router.py tests/test_route_reservations.py tests/test_audit_logger.py -q
pytest -q
grep -n "log_query(" app/services/query_pipeline.py
grep -c "session_id=session_id" app/services/query_pipeline.py   # expect 7
python -c "import inspect; from app.services.query_pipeline import run_query; p=inspect.signature(run_query).parameters; print(list(p)[-1], p['session_id'].default)"
python -c "import inspect, app.services.query_pipeline as q; p=inspect.signature(q._deny).parameters; print(list(p), p['session_id'].default is inspect.Parameter.empty)"
git status --porcelain
git diff --stat
```

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given `app/services/query_pipeline.py`, when `run_query` is read, then it accepts `session_id: Optional[str] = None`.
- [ ] Given the module, when `grep -n "log_query(" app/services/query_pipeline.py` is run, then it reports **seven** call sites and every one of them passes `session_id`. Six are in `run_query`; the seventh is in `_deny`, which serves the three authorization arms.
- [ ] Given a duplicate-blocked send, when the audit row is read, then it carries the `session_id`.
- [ ] Given a pattern-blocked send, a permission-denied send, a model-not-permitted send and a BYOK-denied send, when each audit row is read, then all four carry the `session_id`.
- [ ] Given a `PiiRedactorError` on the input side, a `PiiRedactorError` on the output side and an `OpenRouterError`, when each failure row is written, then all three carry the `session_id`.
- [ ] Given a successful send, when the row is read, then it carries the `session_id` alongside the `audit_id` the UI already shows in its footer.
- [ ] Given `run_query(...)` called without `session_id`, when the row is written, then it is `NULL` and every other field is identical to the current release — asserted against `tests/test_query_pipeline_authorization.py` and `tests/test_integration.py` passing unmodified.
- [ ] Given `_deny`, when its signature is read, then it takes `session_id` explicitly rather than closing over it.
- [ ] All tasks completed
- [ ] Full suite `pytest -q` green
- [ ] `call_openrouter` untouched; no validation added to the pipeline (STORY-010 owns the 403)
- [ ] Follows existing patterns (STORY-008's appended-last optional parameter; STORY-023's census guard)
