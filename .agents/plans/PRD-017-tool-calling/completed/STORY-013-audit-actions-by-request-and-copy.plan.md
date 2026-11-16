---
story: STORY-013
prd: PRD-017
slug: audit-actions-by-request-and-copy
title: "GET /audit/actions?audit_id= and the Actions view's empty-state copy"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: GET /audit/actions?audit_id= and the Actions view's empty-state copy

## Summary

Two small, independent changes. (1) `GET /audit/actions` (`app/routers/admin.py:109-140`) gains
`?audit_id=<int>`, validated by a FastAPI `Query` constraint exactly as `limit` is
(`Query(..., ge=1, ...)`, `admin.py:112`), so a non-integer, zero or negative value is a 422 before
the handler runs. It is passed to `list_action_decisions` (`app/db/database.py:2329-2361`), which gains
an `audit_id=None` keyword and one more fixed `audit_id = ?` clause ANDed with the existing
`user_id` / `decision` clauses. Scoping is unchanged: the user filter is still computed first and
still always applied, so under `audit:read:own` another user's request reads as `[]`. Order stays
`ORDER BY id DESC`. The response shape is unchanged: `ActionsResponse` has no `total`
(`app/models/schemas.py:311-315`), and the console's "of N" figure comes from
`count_action_decisions()` read directly by `chat_ui/chat_ui/admin_state.py:281-283`, which never
filters by `audit_id`, so there is no total to keep consistent. (2) The Actions view's empty body
(`chat_ui/chat_ui/admin_copy.py:332-338`) stops saying nothing calls the engine and stops naming
PRD-017 as future work. It now says what the view holds (the action policy's decisions on `/v1`
tool calls, denied first) and how rows appear (tool calling is off unless `V1_TOOLS_ENABLED`). The
two `actions.py` docstrings that repeat the old reason (`components/actions.py:28-30, 243-245`) are
reworded to match. Copy only; no layout change.

## User Story

As an auditor
I want to list the decisions of one request and to see an Actions view that describes what it holds now that tool calls are live
So that "what was asked" and "what the model tried" read together.

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-013-audit-actions-by-request-and-copy.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Section 4 "Admin console and API" line 91, Section 5 story 7 example line 133, Section 10 line 421: "`GET /audit/actions` gains `?audit_id=<int>`, combined with `decision` and scoped exactly as today.")

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | admin API router, DB read helper, chat UI admin copy + docstrings, docs/api.md |
| Story | STORY-013 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

Dependency: STORY-010 is `status: done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`) | "Build with the brief's real content and subject matter throughout." "Write from the end user's side of the screen. Name things by what people control and recognize." "Treat failure and emptiness as moments for direction ... An empty screen is an invitation to act." Copy only: no token, layout, component or style change. | Task 4, Task 5 |

The new body therefore names what the view really holds (decisions on `/v1` tool calls, denied first),
the one thing the operator controls to get rows (`V1_TOOLS_ENABLED`), and keeps the established action
("Refresh to read again."). No PRD numbers, no "engine" internals.

---

## Patterns to Follow

### Query-parameter validation (the 422 the new parameter must match)
```python
# SOURCE: app/routers/admin.py:109-114
@router.get("/audit/actions", response_model=ActionsResponse)
def get_audit_actions(
    identity: Identity = Depends(require_identity),
    limit: int = Query(ACTIONS_LIMIT_DEFAULT, ge=1, le=ACTIONS_LIMIT_MAX),
    decision: Optional[ActionDecisionFilter] = Query(None),
) -> ActionsResponse:
```

### Scoping before the filter (unchanged; the new filter rides the same call)
```python
# SOURCE: app/routers/admin.py:122-139
    try:
        authorize(identity, PERMISSION_AUDIT_READ_ALL)
        scope_user_id = None
    except PermissionDenied:
        ...
        scope_user_id = identity.user_id

    entries = [
        _action_entry(row)
        for row in list_action_decisions(
            limit=limit, user_id=scope_user_id, decision=decision
        )
    ]
```

### Fixed-clause filters, values bound
```python
# SOURCE: app/db/database.py:2346-2361
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if decision is not None:
        clauses.append("decision = ?")
        params.append(decision)
    where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
```
The index `idx_action_decisions_audit` already exists (`app/db/models.py:400-403`, "PRD-017's join
from an audit_logs row to its decisions"); no schema change. `audit_id` has no foreign key
(`models.py:373`), so tests can insert rows with any `audit_id` without an `audit_logs` row.

### Copy constants and their comments
```python
# SOURCE: chat_ui/chat_ui/admin_copy.py:329-338
# The empty view says what it will contain, why it is empty, and the action.
EMPTY_ACTIONS_TITLE_TEMPLATE = "No {decision} actions recorded."
EMPTY_ACTIONS_ALL_TITLE = "No actions recorded."
# Time-bound by design: PRD-017 connects the engine and must reword this body.
EMPTY_ACTIONS_BODY = (
    "This view lists what agents tried to do and what the action policy "
    ...
)
```

### Tests (router)
```python
# SOURCE: tests/test_admin_actions.py:202-208  (422 before any DB read)
@pytest.mark.parametrize("limit", ["0", "501", "-1", "x"])
def test_limit_out_of_range_is_422(temp_db, monkeypatch, limit):
    monkeypatch.setattr("app.routers.admin.list_action_decisions", _fail_if_called)
    response = client.get(f"/audit/actions?limit={limit}", headers=_ADMIN_HEADERS)
    assert response.status_code == 422
```
```python
# SOURCE: tests/test_admin_actions.py:187-199  (filter combined with own scope)
def test_decision_filter_combines_with_own_scope(temp_db):
    insert_action_decisions([...])
    headers = _user("ana", "user")
    entries = _entries(client.get("/audit/actions?decision=flag", headers=headers))
```
Helpers to reuse: `_row(**overrides)` (`:72-96`, `audit_id=None` by default), `_user` (`:99-103`),
`_entries` (`:106-110`), `_fail_if_called` (`:68-69`), `_ADMIN_HEADERS` (`:46`).

### Tests (DB helper)
```python
# SOURCE: tests/test_action_audit.py:511-521
def test_list_filters_by_user_and_by_decision(temp_db):
    _seed_two_users()
    assert {r.user_id for r in list_action_decisions(100, user_id="u")} == {"u"}
    ...
```
`_seed_two_users()` (ends at `:498`) records three decisions for user `u` with `audit_id=1` and two
for `OTHER` (`v`) with `audit_id=2`, returning the ids in insert order.

### Tests (copy)
```python
# SOURCE: tests/test_actions_view.py:805-815
def test_the_empty_state_says_what_why_and_what_next(probe, actions_source):
    """AC 3: a sentence naming PRD-017 and Refresh, no grid."""
    ...
    assert "PRD-017" in body
    assert "nothing calls the policy engine yet" in body
    assert body.endswith(admin_copy.REFRESH_LABEL + " to read again.")
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `list_action_decisions(..., audit_id=None)`: one more fixed clause; docstring |
| `app/routers/admin.py` | UPDATE | `audit_id: Optional[int] = Query(None, ge=1)`; pass it through; docstring |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | Reword `EMPTY_ACTIONS_BODY` and its comment |
| `chat_ui/chat_ui/components/actions.py` | UPDATE | Reword the module docstring (`:28-30`) and `_empty_actions` docstring (`:243-245`) |
| `tests/test_admin_actions.py` | UPDATE | New `?audit_id=` tests; one modified assertion in `test_default_limit_is_100` |
| `tests/test_action_audit.py` | UPDATE | DB-level `audit_id` filter test |
| `tests/test_actions_view.py` | UPDATE | `test_the_empty_state_says_what_why_and_what_next` (`:805-815`) rewritten for the new body, PRD-017 comment |
| `docs/api.md` | UPDATE | Document `?audit_id=` (`:245`) and drop the two now-false "until PRD-017" phrases (`:216`, `:246`) — see Open question Q3 |

No file is created. `app/models/schemas.py` is not changed (no `total`, PRD-016 F10 / `schemas.py:311-315`).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `list_action_decisions` gains `audit_id`

- **File**: `app/db/database.py`
- **Action**: UPDATE (`:2329-2361`)
- **Implement**:
  - Signature: `limit: int = 100, user_id: Optional[str] = None, decision: Optional[str] = None, audit_id: Optional[int] = None` (new keyword last, so positional callers `list_action_decisions(100)` in `tests/test_action_audit.py` keep working).
  - After the `decision` clause: `if audit_id is not None: clauses.append("audit_id = ?"); params.append(audit_id)`.
  - Docstring: extend the "`user_id` and `decision` filter when given" paragraph to name `audit_id` ("PRD-017 Section 10: one request's decisions, by its `audit_logs.id`; `idx_action_decisions_audit` serves it"). Note that `audit_id` is not validated here either: the router rejects a bad value with 422 (as for `decision`).
  - Order stays `ORDER BY id DESC` (see Q1).
- **Mirror**: the `decision` clause at `database.py:2351-2353`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: `GET /audit/actions?audit_id=`

- **File**: `app/routers/admin.py`
- **Action**: UPDATE (`:109-140`)
- **Implement**:
  - Add a parameter after `decision`: `audit_id: Optional[int] = Query(None, ge=1),` with a short comment above the handler block, next to the existing `ACTIONS_LIMIT_*` / `ActionDecisionFilter` comments (`:97-106`): "PRD-017 Section 10: `?audit_id=` lists one request's decisions. `ge=1` as `limit`'s: an `audit_logs.id` is an AUTOINCREMENT id, so FastAPI rejects a non-integer, zero or negative value with 422 before the handler runs."
  - Pass it: `list_action_decisions(limit=limit, user_id=scope_user_id, decision=decision, audit_id=audit_id)`. Pass it always (it defaults to `None`, which is "no filter"), not only when set; the only kwargs-recording test is updated in Task 3.
  - Docstring: add one sentence: "`?audit_id=` and `?decision=` filter after the scoping and combine with it (AND), so under `audit:read:own` another user's request reads as empty, not as a 403 (PRD-017 Section 10)."
  - Do not touch `ActionsResponse` or `_action_entry`.
- **Mirror**: `limit`'s `Query(..., ge=1, ...)` at `admin.py:112`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: Router and DB tests

- **File**: `tests/test_admin_actions.py`
- **Action**: UPDATE
- **Implement**:
  - Module docstring: add one line "PRD-017 STORY-013 adds `?audit_id=` (Section 10)".
  - New section `# --- PRD-017 STORY-013: ?audit_id= (Section 10) ---`, placed after `test_decision_literal_mirrors_the_db_vocabulary` (`:248`):
    - `test_audit_id_returns_only_that_requests_decisions_newest_first`: insert `_row(audit_id=41)` x2, `_row(audit_id=42)`, `_row(audit_id=None)`, `_row(audit_id=41)` (interleaved). With `_ADMIN_HEADERS`, `?audit_id=41` returns exactly the three 41 ids, `== sorted(ids_41, reverse=True)`, and every `e["audit_id"] == 41`.
    - `test_audit_id_combines_with_decision`: rows 41/deny, 41/allow (rule `sql.read`), 42/deny; `?audit_id=41&decision=deny` returns only the 41 deny row.
    - `test_audit_id_of_another_users_request_is_empty_under_own_scope`: rows `user_id="other", audit_id=41` and `user_id="ana", audit_id=42`; with `_user("ana", "user")`, `?audit_id=41` → `200` and `[]`; `?audit_id=42` → ana's row only.
    - `test_audit_id_without_either_audit_permission_is_403`: `_user("outsider", "guest")`, `?audit_id=41` → 403 `{"detail": "Permission denied: audit:read:own"}` (same as the unfiltered call, `:141-152`).
    - `test_audit_id_invalid_is_422`, parametrized `["-1", "0", "x", "1.5"]`, with `list_action_decisions` monkeypatched to `_fail_if_called`, → 422. Also try `""`: FastAPI is expected to reject it as an int parse error (422). Verify at implement time; if FastAPI treats it as absent instead, drop `""` from the list and say so in the report.
    - `test_audit_id_is_passed_to_the_repository`: recorder (as `:235-245`) on `?audit_id=41` → `calls == [{"limit": 100, "user_id": None, "decision": None, "audit_id": 41}]`.
  - Modify `test_default_limit_is_100` (`:235-245`): the expected kwargs become `{"limit": 100, "user_id": None, "decision": None, "audit_id": None}`, with the comment `# PRD-017 STORY-013 (Section 10): the router now always passes audit_id; None is no filter.`
- **File**: `tests/test_action_audit.py`
- **Action**: UPDATE
- **Implement**: after `test_list_filters_by_user_and_by_decision` (`:511-521`), add `test_list_filters_by_audit_id` (PRD-017 STORY-013 docstring): `ids = _seed_two_users()`; `[r.id for r in list_action_decisions(100, audit_id=1)] == list(reversed(ids[:3]))`; `list_action_decisions(100, audit_id=2, decision="deny")` has only `c4`; `list_action_decisions(100, user_id="u", audit_id=2) == []` (filters AND); `list_action_decisions(100, audit_id=999) == []`.
- **Validate**: (run in Task 6's single pytest call)

### Task 4: Reword the empty body

- **File**: `chat_ui/chat_ui/admin_copy.py`
- **Action**: UPDATE (`:332-338`)
- **Skill**: frontend-design (real subject matter; name what the operator controls; empty = direction)
- **Implement**: replace the comment and body with:
  ```python
  # PRD-017 STORY-013: reworded now that `/v1` tool calls are decided live.
  # It names `V1_TOOLS_ENABLED`, so renaming that setting must reword it.
  EMPTY_ACTIONS_BODY = (
      "This view lists the decisions the action policy made on tool calls "
      "that models sent through /v1, denied first. Decisions are recorded "
      "only while tool calling is on (V1_TOOLS_ENABLED=true); each tool "
      "call a model makes then adds a row here. Refresh to read again."
  )
  ```
  The body is filter-neutral on purpose: it is shown under every filter's empty title ("No denied actions recorded."), so it must not claim the whole table is empty. It must still end with `REFRESH_LABEL + " to read again."` (`admin_copy.py:152`, `REFRESH_LABEL = "Refresh"`). The implementer may tune wording, but must keep: "/v1", "tool call", "denied first", "V1_TOOLS_ENABLED", the Refresh ending; and must not contain "PRD-017", "nothing calls" or "yet".
- **Mirror**: the sentence style of the existing body and `EMPTY_ACTIONS_*_TITLE` (`:330-331`).
- **Validate**: Task 6.

### Task 5: Reword the two docstrings

- **File**: `chat_ui/chat_ui/components/actions.py`
- **Action**: UPDATE (docstrings only, no code)
- **Implement**:
  - Module docstring `:28-30`: "It says what the view lists, why it is empty (nothing calls the policy engine until PRD-017) and the action," → "It says what the view lists (the policy's decisions on `/v1` tool calls), how rows appear (tool calling is off unless `V1_TOOLS_ENABLED`) and the action,".
  - `_empty_actions` docstring `:243-245`: "why it is empty (PRD-017)" → "how rows appear (`V1_TOOLS_ENABLED`)".
  - `test_actions_view.py` has a `_code_only(actions_source)` forbidden-word check (`:800-802`: `outline`, `tabindex`, `tab_index`, `box_shadow`); docstrings are stripped by `_code_only`, and the new text uses none of those words anyway.
- **Validate**: Task 6.

### Task 6: Copy test, docs, validation

- **File**: `tests/test_actions_view.py`
- **Action**: UPDATE `test_the_empty_state_says_what_why_and_what_next` (`:805-815`)
- **Implement**: docstring → `"""AC 3: what the view lists, how rows appear, and Refresh; no grid."""`. Replace the two lines at `:809-810` with (comment first):
  ```python
  # PRD-017 STORY-013 (Section 4, F10): tool calls are decided live, so the body
  # no longer names PRD-017 or says nothing calls the engine (was: "PRD-017" in
  # body, "nothing calls the policy engine yet" in body).
  assert "PRD-017" not in body
  assert "nothing calls" not in body
  assert "/v1" in body
  assert "denied first" in body
  assert "V1_TOOLS_ENABLED" in body
  ```
  Keep the Refresh-ending, `actions_empty_title`, `body in probe["empty"]`, no `columnheader` / `grid` assertions unchanged. The test name is unchanged, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry.
- **File**: `docs/api.md` (see Q3)
- **Implement**: `:216` drop "**Empty until PRD-017 calls the engine**: nothing in the request path writes a row yet (see ...)." and say instead that rows are written when `V1_TOOLS_ENABLED=true` and a `/v1` response carries tool calls. `:245` add "`?audit_id=` (a positive integer, the request's `audit_logs.id`) lists one request's decisions; it combines with `?decision=` and the scoping, so under `audit:read:own` another user's request is `[]`; a non-integer, zero or negative value is a `422`." `:246` drop "`audit_id` is `null` until PRD-017 links a decision to its `audit_logs` row." → "`audit_id` is the request's `audit_logs` row; `null` only for a decision recorded outside a request." Add a `curl ".../audit/actions?audit_id=412"` example only if it fits; not required.
- **Validate** (one pytest call, foreground, per the brief; no full suite):
  ```bash
  PYTHONUTF8=1 .venv/Scripts/python -m pytest \
    tests/test_admin_actions.py tests/test_action_audit.py \
    tests/test_actions_view.py tests/test_admin_copy.py tests/test_copy.py \
    tests/test_admin_state.py tests/test_chat_ui_startup_guard.py \
    tests/test_untouched_app.py -q
  .venv/Scripts/python -c "from app.main import app; print('OK')"
  ```
  `tests/test_chat_ui_startup_guard.py` covers the chat_ui import probe (brief). `tests/test_untouched_app.py` because app files change. `tests/test_admin_state.py` monkeypatches `list_action_decisions` with `lambda **_kwargs: []` (`:415`) and the console read `admin_state.py:281` does not pass `audit_id`, so it should be untouched; it is in the run as a check. No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed. If many `db` tests error at setup, `docker restart harness-libsql-dev` and rerun.

---

## End-to-End Tests

- [ ] TestClient (in the tests above): `GET /audit/actions?audit_id=41` with the admin token → 200, only 41's rows, newest first; `&decision=deny` narrows further.
- [ ] `?audit_id=-1`, `0`, `x`, `1.5` → 422 with no DB read; a guest → 403; `audit:read:own` + another user's request → `[]`.
- [ ] chat_ui import probe (`tests/test_chat_ui_startup_guard.py`) passes; the Actions view's empty panel shows the new body (asserted via `probe["empty"]` in `tests/test_actions_view.py`).

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_admin_actions.py tests/test_action_audit.py tests/test_actions_view.py tests/test_admin_copy.py tests/test_copy.py tests/test_admin_state.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py -q
```
Full suite: deferred to orchestrator (user decision).

---

## Risks and Open Questions

- **Q1 "in their stored order".** The endpoint orders `id DESC` (newest first, `database.py:2336-2339`), and `record()` inserts one request's calls in call order. This plan keeps `id DESC` for the filtered list too: one ordering rule for the endpoint, no branch on a filter, and the tests assert `sorted(ids, reverse=True)`. If the orchestrator reads "stored order" as ascending (call order) for `?audit_id=`, the change is a conditional `ORDER BY id ASC` when `audit_id` is set plus the test expectation; say so before implementing.
- **Q2 `ge=1` vs `ge=0`.** The AC names "non-integer or negative". `ge=1` also rejects `0`, which cannot be an `audit_logs.id` (AUTOINCREMENT starts at 1) and matches `limit`'s `ge=1`. If `0` must be accepted (returning `[]`), use `ge=0` and drop `"0"` from the 422 parametrization.
- **Q3 docs/api.md.** Not named by the story; STORY-018's scope is README, `docs/features.md`, `docs/roadmap.md`, `.env.example` (no `docs/api.md`). The API changes here and `docs/api.md:216,246` say "until PRD-017", which this PRD makes false, so the plan updates it in this story. If the orchestrator prefers to leave docs to STORY-018, skip that part of Task 6 and note it for STORY-018.
- **Risk: `""` for an `Optional[int]` query.** FastAPI behaviour for an empty value on a non-string query parameter should be a 422 parse error; verify, and drop the case if not (Task 3).
- **No total to keep consistent.** `ActionsResponse` has no `total` (`schemas.py:311-315`) and the console reads the DB directly (`admin_state.py:281-283`) without an `audit_id`, so the "of N" scope line (`admin_copy.py:326-327`) is unaffected. Nothing to change there.
- **Flag-off byte-identity (D10).** No `/v1` code is touched.

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given decisions recorded for audit rows 41 and 42, when `GET /audit/actions?audit_id=41` is called with `audit:read:all`, then only row 41's decisions are returned, in their stored order; combined with `?decision=deny` both filters apply. — Tasks 1-3: `test_audit_id_returns_only_that_requests_decisions_newest_first`, `test_audit_id_combines_with_decision`, `test_list_filters_by_audit_id`.
- [ ] Given `audit:read:own`, when `?audit_id=` names another user's request, then the response is empty (scoping applies before the filter, exactly as today); neither permission → 403; a non-integer or negative `audit_id` → 422/400 as the endpoint's other parameters fail. — Tasks 2-3: `test_audit_id_of_another_users_request_is_empty_under_own_scope`, `test_audit_id_without_either_audit_permission_is_403`, `test_audit_id_invalid_is_422`.
- [ ] Given the admin console's Actions view with zero rows, when rendered, then the body no longer says nothing calls the engine or names PRD-017 as future work; it says the view lists the decisions the action policy made on `/v1` tool calls, denied first, and how to get rows (tool calling is off unless `V1_TOOLS_ENABLED`), and `tests/test_actions_view.py:806-809` is updated with a PRD-017 comment. — Tasks 4-6: `test_the_empty_state_says_what_why_and_what_next`.
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] chat_ui startup guard passes
- [ ] Follows existing patterns
