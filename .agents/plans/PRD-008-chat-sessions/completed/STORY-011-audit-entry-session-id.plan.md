---
story: STORY-011
prd: PRD-008
slug: audit-entry-session-id
title: "AuditQueryEntry.session_id so GET /audit reports the conversation"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-04
---

# Plan: AuditQueryEntry.session_id so GET /audit reports the conversation

## Summary

The column is already there and already populated. STORY-008 put `session_id` on `audit_logs`, on `AuditLog`, and on both read shapes in `_row_to_audit_log`; STORY-009 threaded it to all seven `log_query` call sites; STORY-010 opened the API end so a client can supply one. The value is written, stored and hydrated — and then dropped on the floor, because `AuditQueryEntry` projects fourteen of the audit row's nineteen fields and `session_id` is not one of them. This story adds the fifteenth: one field on the response model, one keyword in the `admin.py` projection. No query changes, no store function changes, no new endpoint. `list_audit_logs` already returns `AuditLog` objects whose `session_id` is populated, so the router has the value in hand at `admin.py:38` and simply does not pass it.

The whole of the risk in a one-field addition is who was pinning the old shape. Three assertions in the suite enumerate the `/audit` entry's keys exactly, and one of them lives in a suite this story's AC 5 calls "unmodified". That conflict is real, it is resolved below in **Deviation**, and it is the reason a LOW-complexity story gets a plan with a table in it.

## User Story

As a compliance admin
I want `GET /audit` to return the session an entry belongs to
So that three rows that were one conversation are visibly one conversation.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-011-audit-entry-session-id.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `app/models/schemas.py`, `app/routers/admin.py`, four test suites |
| Story | STORY-011 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |
| Depends on | STORY-008 (`status: done`) — verified before planning |
| Blocks | STORY-022 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | none | — |

`.agents/skills/` was listed and holds exactly one skill, `frontend-design`, read in full. Its description scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" — palette, typography, layout, copy, motion. This story changes a Pydantic response model and a dict projection in a FastAPI router; it renders nothing, adds no string to `copy.py` and touches no token in `theme.py`. No rule in that SKILL.md has a subject here. The story's own Technical Notes reached the same conclusion independently, and this plan confirms it rather than inheriting it.

---

## Patterns to Follow

### Naming — the optional, defaulted field appended last to a read model

`session_id` goes at the **end** of the field list, after `denied_permission`. That is where PRD-005 put `role` and `denied_permission` when it extended this same model, and where STORY-008 put `session_id` on `AuditLog` and STORY-010 put it on `QueryRequest`. Appending keeps the model's field order a history of what was added when, and keeps the diff one line.

```python
# SOURCE: app/models/schemas.py:110-124
class AuditQueryEntry(BaseModel):
    audit_id: int
    user_id: str
    timestamp: str
    model: Optional[str] = None
    prompt_hash: str
    was_duplicate_blocked: bool
    suspicious_pattern_detected: bool
    device: Optional[str] = None
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    pii_entities: List[str] = []
    role: Optional[str] = None
    denied_permission: Optional[str] = None
```

```python
# SOURCE: app/db/models.py:178-183 -- the same field, one layer down, added by STORY-008
    role: Optional[str] = None
    denied_permission: Optional[str] = None
    # PRD-008. Wired end to end as of STORY-008: insert_audit_log() writes it,
    # and _row_to_audit_log() maps it back on both read shapes -- the `SELECT *`
    # row and the json_object(...) the summary snapshot decodes.
    session_id: Optional[str] = None
    id: Optional[int] = None
```

### Projection — a straight passthrough, and the one field that is not

Every keyword in the comprehension is `log.<attr>` verbatim except `suspicious_pattern_detected` (a `is not None` test) and `pii_entities` (a split). `session_id` is a passthrough and is written as one; there is nothing to transform.

```python
# SOURCE: app/routers/admin.py:37-52
    queries = [
        AuditQueryEntry(
            audit_id=log.id,
            user_id=log.user_id,
            role=log.role,
            denied_permission=log.denied_permission,
            timestamp=log.timestamp,
            model=log.model_used,
            prompt_hash=log.prompt_hash,
            was_duplicate_blocked=log.was_duplicate_blocked,
            suspicious_pattern_detected=log.suspicious_pattern is not None,
            device=log.device,
            pii_detected_input=log.pii_detected_input,
            pii_detected_output=log.pii_detected_output,
            pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
        )
        for log in list_audit_logs(limit=100, user_id=scope_user_id)
    ]
```

### The value is already hydrated — nothing in `database.py` changes

```python
# SOURCE: app/db/database.py:632 (_row_to_audit_log)
        session_id=row["session_id"],
```

`list_audit_logs` builds its rows through `_row_to_audit_log`, so `log.session_id` is live at the projection today and reads `None` for every pre-PRD row — which is AC 3, satisfied by SQLite's nullable column rather than by any code this story writes.

### Tests — the present/absent pair, as the same suite already writes it

`test_audit_entry_carries_role_and_denied_permission` is the exact precedent for AC 4 and AC 3: two rows, one with the field and one without, keyed by `prompt_hash`, asserting the populated value and the `None`.

```python
# SOURCE: tests/test_audit_router.py:236-262
def test_audit_entry_carries_role_and_denied_permission(temp_db):
    insert_audit_log(
        AuditLog(
            timestamp="2026-07-01T10:00:00Z",
            user_id="ana",
            prompt_hash="h1",
            role="user",
            denied_permission="query:byok",
        )
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="ana", prompt_hash="h2")
    )

    response = client.get(
        "/audit", headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    )

    body = response.json()
    by_hash = {q["prompt_hash"]: q for q in body["queries"]}
    assert by_hash["h1"]["role"] == "user"
    assert by_hash["h1"]["denied_permission"] == "query:byok"
    assert by_hash["h2"]["role"] is None
    assert by_hash["h2"]["denied_permission"] is None
```

### Tests — the end-to-end suite this story's AC 4 belongs in

AC 4 ("three sends in one session") needs a real `POST /query` with a real token and a patched `call_openrouter`, none of which `test_audit_router.py` does — it drives `insert_audit_log` directly and has no user fixture beyond the two RBAC cases. STORY-010's suite is the shape to copy: its own `temp_db` override inserting genuine accounts, a module-level `TestClient` carrying the auth header, and `_session_owned_by` minting a session through the service.

```python
# SOURCE: tests/test_query_session_id.py:63-101
@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's two authenticated users."""
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    insert_user(User(user_id=_OTHER_USER_ID, role="user", token_hash=hash_token(_OTHER_TOKEN)))
    return temp_db


def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


def _session_owned_by(user_id: str) -> str:
    """One session belonging to `user_id`, created through the service."""
    identity = Identity(user_id=user_id, role="user")
    session_id = chat_sessions.create(identity, "the quarterly close", lambda text: text)
    assert session_id is not None
    return session_id
```

### Tests — the optional-with-`None`-default idiom AC 6 asks for

```python
# SOURCE: tests/test_schemas.py:196-197
    assert not QueryRequest.model_fields["session_id"].is_required()
    assert QueryRequest.model_fields["session_id"].default is None
```

### The guard that decides what "unmodified" is allowed to mean

```python
# SOURCE: tests/test_untouched_app.py:66-80
# PRD-006 Section 15, "Tests that must pass unmodified". These six were once
# pinned byte-for-byte; STORY-023 asserts them by census instead, for the reason
# the module docstring gives. Extending one of them passes, deleting a case from
# one fails.
_UNMODIFIED_SUITES = (
    "tests/test_admin_auth.py",
    "tests/test_audit_router.py",
    ...
)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | `AuditQueryEntry.session_id: Optional[str] = None`, appended last (AC 1, AC 6) |
| `app/routers/admin.py` | UPDATE | `session_id=log.session_id` in the `GET /audit` projection (AC 2) |
| `tests/test_audit_router.py` | UPDATE | `"session_id"` into the exact key-set assertion; a new present/absent test (AC 3, AC 5) |
| `tests/test_schemas.py` | UPDATE | `"session_id": None` into `test_audit_response_shape`'s expected dict; a new optional/default assertion (AC 6) |
| `tests/test_pii_redaction_integration.py` | UPDATE | `"session_id"` into `test_audit_endpoint_contract_has_no_preview_fields`' sorted key list |
| `tests/test_audit_session_id.py` | CREATE | AC 4 driven end to end: three `POST /query` sends on one session, read back through `GET /audit` |

**Not changed, deliberately:**

| File | Why not |
|------|---------|
| `app/db/database.py`, `app/db/models.py` | STORY-008 finished the store. `list_audit_logs` already hydrates `session_id`; there is no query, no column and no function to touch. |
| `app/routers/admin.py` — `get_stats` | PRD Section 4: "`GET /stats` is unchanged. `StatsResponse` gains no session dimension." `summary_snapshot(row_limit=0)` is not read for sessions and gains no figure. |
| `app/models/schemas.py` — `StatsResponse` | Same. |
| `AuditQueryEntry.success` / `.error_message` | The story's Technical Notes name this explicitly: a defect PRD-006 Section 1 documented and PRD-006 Section 13 parked. Adding it here would be a different PRD's work smuggled into this commit. The projection stays at fourteen fields plus the one this story owns. |
| `chat_ui/chat_ui/components/register.py`, `chat_ui/chat_ui/admin_state.py` | AC 7, and PRD Section 4's Out of Scope: "PRD-006's register and summary are untouched. The `session_id` column reaches `GET /audit` and stops there." Confirmed reachable-but-unused: `admin_state.py` imports counters from `app.db.database` directly and never calls `GET /audit`, so nothing there changes even incidentally. |
| `app/main.py`, `Caddyfile`, `tests/test_route_reservations.py` | No new route. PRD Section 10: "**No new endpoints.**" |
| `tests/test_integration.py` | Its `/audit` assertions read named keys (`was_duplicate_blocked`, `suspicious_pattern_detected`, `total`) and never enumerate the key set. Verified: an added field cannot fail it. Run, not edited. |
| `tests/test_untouched_app.py` | Its censuses assert only that baseline test functions were not *removed*. Every edit below is additive — one key added to a set literal, one test function added. No allowlist entry is needed and none is added. |
| `README.md`, `.env.example` | STORY-022 owns the documentation pass. |

### Deviation from the story's AC 5, stated plainly

**AC 5 says `tests/test_audit_router.py` "passes **unmodified**, and new assertions cover the present and absent cases". Those two clauses cannot both hold literally, and the plan takes the second.**

`test_valid_token_returns_expected_shape` pins the projection by exact key set:

```python
# SOURCE: tests/test_audit_router.py:75-89
        assert set(entry.keys()) == {
            "audit_id", "user_id", "timestamp", "model", "prompt_hash",
            "was_duplicate_blocked", "suspicious_pattern_detected", "device",
            "pii_detected_input", "pii_detected_output", "pii_entities",
            "role", "denied_permission",
        }
```

An additive field makes that set unequal. There is no implementation of AC 1 and AC 2 that leaves it passing, and the same is true of the two sibling assertions elsewhere:

| Assertion | Suite | Pinned by STORY-023? | Fate |
|---|---|---|---|
| `set(entry.keys()) == {...}` — `test_valid_token_returns_expected_shape` | `tests/test_audit_router.py:75` | yes, by **census** | `"session_id"` added to the set |
| `response.model_dump() == {...}` — `test_audit_response_shape` | `tests/test_schemas.py:99` | no | `"session_id": None` added to the dict |
| `sorted(entry) == [...]` — `test_audit_endpoint_contract_has_no_preview_fields` | `tests/test_pii_redaction_integration.py:190` | no | `"session_id"` added to the list |

Three points make this the right resolution rather than a shortcut:

1. **The census is the current instrument, and it permits exactly this.** STORY-023 retired byte-equality on these six suites eight commits ago, for this reason in its own words: *"Byte-equality was the wrong instrument … it fires on any edit, including the ones that add coverage. Extending a suite passes. Deleting a case fails."* No test function is removed, none is renamed, and no assertion is weakened — `set(...) == {...}` stays an exact-equality check over a set that is one member larger. `test_no_test_was_removed_from_the_six_pinned_suites[tests/test_audit_router.py]` passes.
2. **AC 5's second clause requires opening the file anyway.** "New assertions cover the present and absent cases" cannot be satisfied without editing `tests/test_audit_router.py`. The clause that survives is the one that asks for coverage; the clause that dies is the one that asked the file to stay closed while adding a test to it.
3. **The third assertion was designed to fire here.** `test_audit_endpoint_contract_has_no_preview_fields`' docstring: *"If a future story adds them, this test fails — forcing that to be a deliberate, reviewed decision rather than a drift."* This is that decision, made in the open. What that test actually guards — no `prompt_preview`, no `response_preview`, no `response_hash` on the admin payload — is untouched; `session_id` is an opaque UUID, not prompt text.

**What "unmodified" does still bind:** no existing test function in `tests/test_audit_router.py` is deleted, renamed, or has an assertion removed or loosened. The only edit inside an existing body is one string added to one set literal. Task 7 proves it by diff.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `AuditQueryEntry.session_id`

- **File**: `app/models/schemas.py`
- **Action**: UPDATE
- **Implement**: Append `session_id: Optional[str] = None` to `AuditQueryEntry`, after `denied_permission`. Carry a short comment in the register's own voice: the field is what makes three rows visibly one conversation (PRD Section 5 story 8); `None` for every row written before PRD-008 and for every send that carried no session, which is why it is optional and defaulted rather than required — a required field here would break every existing constructor, including `tests/test_schemas.py`'s own. Note that this is a **read** model and the value arrives already validated at the write end by `QueryRequest`'s UUID4 `field_validator` (STORY-010); revalidating on the way out would reject rows the database legitimately holds, so no validator is added here.
- **Mirror**: `app/models/schemas.py:110-124` (field order and the `Optional[str] = None` idiom); `app/db/models.py:178-183` (the same field, one layer down)
- **Do not**: add `success` or `error_message` — story Technical Notes; add a validator; reorder existing fields.
- **Validate**: `python -c "from app.models.schemas import AuditQueryEntry as A; f=A.model_fields['session_id']; print(list(A.model_fields), f.is_required(), f.default)"` → `session_id` last, `False`, `None`

### Task 2: the `GET /audit` projection

- **File**: `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**: Add `session_id=log.session_id,` to the `AuditQueryEntry(...)` construction inside the list comprehension, beside `denied_permission=log.denied_permission`. A verbatim passthrough — no transform, no default, no conditional. `list_audit_logs` already returns it (`_row_to_audit_log`, `database.py:632`), so this adds a keyword and nothing else. Leave `get_stats` and its `summary_snapshot(row_limit=0)` call untouched.
- **Mirror**: `app/routers/admin.py:37-52`
- **Validate**: `python -c "from app.main import app; print('ok')"` (imports clean), then Task 4's suite

### Task 3: `tests/test_schemas.py` learns about the new field

- **File**: `tests/test_schemas.py`
- **Action**: UPDATE
- **Implement**: Two edits.
  (a) In `test_audit_response_shape`, add `"session_id": None,` to the expected entry dict, after `"denied_permission": None`. The test constructs `AuditQueryEntry` without the field, so `None` is exactly what an omitted-and-defaulted field must serialize to — the assertion keeps proving the default rather than merely accommodating it.
  (b) Add `test_audit_query_entry_session_id_is_optional_with_a_none_default`, asserting `AuditQueryEntry.model_fields["session_id"].is_required() is False` and `.default is None`, with a docstring naming AC 6 and the reason: a required field here would break every existing constructor, in this file and in `app/routers/admin.py`.
- **Mirror**: `tests/test_schemas.py:196-197` for the field-introspection idiom; `tests/test_schemas.py:87-117` for the shape test
- **Validate**: `pytest tests/test_schemas.py -q`

### Task 4: `tests/test_audit_router.py` — the key set, and the present/absent pair

- **File**: `tests/test_audit_router.py`
- **Action**: UPDATE
- **Implement**: Two edits, and no others.
  (a) In `test_valid_token_returns_expected_shape`, add `"session_id",` to the `set(entry.keys()) == {...}` literal. One string; the assertion stays exact equality. (Deviation section above.)
  (b) Add `test_audit_entry_carries_session_id_when_present_and_null_when_absent`: `insert_audit_log` two rows, one with `session_id="0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"` and `prompt_hash="h-session"`, one omitting it entirely with `prompt_hash="h-no-session"`; `GET /audit` with the admin token; key by `prompt_hash`; assert the first entry's `session_id` equals the id and the second's `is None`. The second row is AC 3's pre-PRD row — a row constructed exactly as `AuditLog` was constructible before this PRD — so the same test proves both the absent case and backward compatibility.
- **Mirror**: `tests/test_audit_router.py:236-262` (`test_audit_entry_carries_role_and_denied_permission`), copied in structure
- **Do not**: delete or rename any test; touch any other assertion; add a fixture; import anything not already imported (`insert_audit_log`, `AuditLog`, `settings`, `client` are all in scope).
- **Validate**: `pytest tests/test_audit_router.py -q` and `git diff --stat tests/test_audit_router.py` (expect a small, additive diff)

### Task 5: `tests/test_pii_redaction_integration.py`'s contract list

- **File**: `tests/test_pii_redaction_integration.py`
- **Action**: UPDATE
- **Implement**: Add `"session_id",` to the `sorted(entry) == [...]` list in `test_audit_endpoint_contract_has_no_preview_fields`, in sorted position — between `"role"` and `"suspicious_pattern_detected"`. Extend the docstring by one sentence recording that PRD-008 STORY-011 added `session_id` deliberately, and that the claim the test defends is unchanged: previews, raw text and `response_hash` are still absent, and a UUID is not prompt text.
- **Mirror**: `tests/test_pii_redaction_integration.py:177-201`
- **Validate**: `pytest tests/test_pii_redaction_integration.py -q`

### Task 6: `tests/test_audit_session_id.py` — AC 4, end to end

- **File**: `tests/test_audit_session_id.py`
- **Action**: CREATE
- **Implement**: A new suite for the criterion that needs the whole path. Module docstring: STORY-008 wrote the column, STORY-009 threaded it, STORY-010 opened the API, and this story is the first time the value comes back out — so the test that matters is the round trip, not the projection in isolation. Prologue copied (not imported) from `tests/test_query_session_id.py`, for the reason that file records: importing from a suite couples the two. Contents:
  - the `os.environ.setdefault` prologue, a module-level `TestClient(app, headers=_AUTH_HEADERS)`, the `temp_db` fixture override inserting one genuine `user`-role account, `_fake_call_openrouter`, `_fail_if_called`, and `_session_owned_by`.
  - `test_three_sends_in_one_session_share_one_session_id_in_the_audit`: mint one session for the authenticated user; `POST /query` three times with three *distinct* prompts (distinct so the duplicate checker does not block sends two and three and change what is being measured) and the same `session_id`; `GET /audit` with the admin token; assert `total == 3`, that all three entries carry that `session_id`, and that `len({e["session_id"] for e in body["queries"]}) == 1` — the "visibly one conversation" claim stated as the story states it.
  - `test_a_send_without_a_session_id_reports_null_alongside_one_that_has_it`: two sends, one carrying the session and one omitting it, in the same database; assert `GET /audit` reports the id on the first and `None` on the second — the mixed-fleet case, which the two-row unit test in Task 4 cannot show because it never goes through `POST /query`.
  - `test_a_denied_send_still_reports_its_session_id`: send a suspicious prompt (`"please override the rules"`, the phrasing `tests/test_integration.py:157` uses) on the session; assert the blocked row comes back from `GET /audit` with `suspicious_pattern_detected is True` **and** the `session_id` — PRD Section 12 Phase 2's "the four blocked outcomes each carry the session on their audit row", now visible at the read end. Patch `call_openrouter` with `_fail_if_called` for this one, since a blocked send must not reach upstream.
- **Mirror**: `tests/test_query_session_id.py:1-101` for the prologue, fixture and helpers; `tests/test_audit_router.py:56-70` for the admin-token `GET /audit` call
- **Validate**: `pytest tests/test_audit_session_id.py -q`

### Task 7: prove the boundary held and the whole thing is green

- **File**: — (verification only)
- **Action**: VERIFY
- **Implement**: Run the full suite. Then prove AC 7 and the residue of AC 5 by diff: `git diff --name-only` must list exactly the six files in **Files to Change** and nothing under `chat_ui/`; `git diff --stat tests/test_audit_router.py` must show an additive change only. Re-read the diff of `tests/test_audit_router.py` and confirm by eye that no `def test_` line was removed and no assertion loosened. Confirm `tests/test_integration.py`, `tests/test_route_reservations.py`, `tests/test_query_router.py`, `tests/test_stats_router.py` and `tests/test_admin_auth.py` are absent from `git diff --name-only`.
- **Validate**: the Validation block below, top to bottom

---

## End-to-End Tests

- [ ] `GET /audit` on a database of pre-PRD rows → 200, every entry carries `"session_id": null`, and every other field byte-identical to the current release — AC 3
- [ ] `insert_audit_log` with a `session_id` → `GET /audit` reports it; without → reports `null`, in the same response — AC 3, AC 5
- [ ] Three `POST /query` sends with one `session_id` → `GET /audit` returns three entries sharing one id — AC 4
- [ ] A send carrying a session and a send omitting one, in one database → the ids reported are the id and `null` respectively — AC 3, AC 4
- [ ] A suspicious-pattern send on a session → the blocked row is returned with `suspicious_pattern_detected: true` and the `session_id` — PRD Section 12 Phase 2
- [ ] `AuditQueryEntry.model_fields["session_id"]` is not required and defaults to `None` — AC 6
- [ ] `GET /stats` response is unchanged: no session field, same nine figures — PRD Section 4
- [ ] `GET /audit` still carries no `prompt_preview`, `response_preview` or `response_hash` — `tests/test_pii_redaction_integration.py`
- [ ] `git diff` touches nothing under `chat_ui/` — AC 7
- [ ] No new route on `app.routes` — PRD Section 10
- [ ] `tests/test_untouched_app.py` green, including the census over `tests/test_audit_router.py`
- [ ] `pytest -q` green

---

## Validation

```bash
pytest tests/test_audit_session_id.py -q
pytest tests/test_audit_router.py tests/test_schemas.py -q
pytest tests/test_pii_redaction_integration.py tests/test_untouched_app.py -q
pytest tests/test_integration.py tests/test_route_reservations.py tests/test_stats_router.py tests/test_admin_auth.py -q
pytest -q
python -c "from app.models.schemas import AuditQueryEntry as A; f=A.model_fields['session_id']; print(list(A.model_fields)[-1], f.is_required(), f.default)"
python -c "from app.models.schemas import StatsResponse as S; print(sorted(S.model_fields))"
python -c "from app.main import app; print(sorted({r.path for r in app.routes}))"
git diff --name-only
git diff --stat tests/test_audit_router.py
git diff --name-only -- chat_ui/
git status --porcelain
```

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given `app/models/schemas.py`, when `AuditQueryEntry` is read, then it declares `session_id: Optional[str] = None`.
- [ ] Given `app/routers/admin.py`, when `GET /audit` projects a row, then `session_id` is included.
- [ ] Given a row written before this PRD, when it is returned, then `session_id` is `null` and every other field is unchanged — an additive field on a response model, invisible to a consumer that does not read it.
- [ ] Given three sends in one session, when `GET /audit` is called, then all three entries carry the same `session_id`.
- [ ] Given `tests/test_audit_router.py`, when the suite runs, then it passes **unmodified**, and new assertions cover the present and absent cases. *(Resolved per **Deviation**: no test removed, renamed, or loosened; one string added to one set literal so the additive field can be asserted at all.)*
- [ ] Given `tests/test_schemas.py`, when it runs, then the new field is asserted as optional with a `None` default — a required field here would break every existing constructor.
- [ ] Given PRD-006's admin console, when `git diff` is inspected, then nothing under `chat_ui/chat_ui/components/register.py` or `chat_ui/chat_ui/admin_state.py` changed.
- [ ] All tasks completed
- [ ] Full suite `pytest -q` green
- [ ] `GET /stats` and `StatsResponse` unchanged
- [ ] `AuditQueryEntry` gains exactly one field; `success` and `error_message` stay out
- [ ] Follows existing patterns
