---
story: STORY-015
prd: PRD-016
slug: action-decisions-table-and-record
title: "action_decisions table, indexes, record() and read functions"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: action_decisions table, indexes, record() and read functions

## Summary

This story adds the decision audit (PRD-016 Sections 4 *Audit*, 6.10, F10, D8). It has four parts.

1. **Schema** in `app/db/models.py`: `CREATE_ACTION_DECISIONS_TABLE` (Section 6.10, plus a `reason` column by orchestrator decision), the two Section 6.10 indexes, a frozen `ActionDecisionRow` dataclass, and a closed `ACTION_DECISION_VALUES = ("allow", "flag", "deny")`. A comment block in the `usage_daily` style explains why there is no foreign key and no added-columns mapping.
2. **Storage** in `app/db/database.py`:
   - `init_db()` creates the table and both indexes inside its one `_session()` block.
   - `insert_action_decisions(rows) -> list[int]` writes the whole batch in one `_session()` block, so it is one transaction: all rows land or none do.
   - `list_action_decisions(limit=100, user_id=None, decision=None)` returns rows newest first, ordered by `id DESC` and never by the TEXT timestamp.
   - `count_action_decisions() -> dict[str, int]` returns `{allow, flag, deny}`, with 0 for any decision that has no rows.
3. **Service**: a new `app/services/action_audit.py` with `record(decisions, identity, audit_id=None, session_id=None) -> list[int]`, the Section 10 signature. It turns STORY-014's frozen `ActionDecision`s into rows:
   - `arguments_hash` is `hash_prompt()` of the full raw arguments string.
   - `arguments_preview` is the first 500 characters of that string.
   - `target_preview` is the reported operation's target, cut to 500 characters. For an `http` target, the query and fragment values are redacted first, keeping the keys (orchestrator decision, STORY-012 plan).
   - `classifications` is a JSON array of `{rule, kind, detail}`.
   - All rows in one call share one UTC timestamp.
4. **Tests**: a new `tests/test_action_audit.py` (with the `db` marker, through `temp_db`/`uninitialized_db`), plus one changed assertion in `tests/test_two_instance_smoke.py`. That test pins the exact sorted table list, which gains `action_decisions`.

No route, no `/stats`, no UI: those are STORY-016 and STORY-019.

## User Story

As an auditor
I want every action decision, allowed ones included, stored as one row per tool call with the policy digest that made it
So that the audit shows what was attempted and can be read correctly after the policy changes

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-015-action-decisions-table-and-record.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` (Sections 4, 6.10, 6.12, 7 F10, 9.2 T10, 10, 11, 15 D8)
- Input type: `app/services/action_policy.py:76-110` (`ActionDecision`, STORY-014 `dab8066`)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, new `app/services/action_audit.py`, tests |
| Story | STORY-015 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` ("visual design when building new UI"). This story has no UI. The story frontmatter has `skills: []`. | — |

---

## Binding inputs (orchestrator decisions, applied verbatim)

1. **STORY-014 plan: store `reason`.** The table gets `reason TEXT NOT NULL`, placed after `rule`, which is where the Section 10 API example puts it. This adds one column to the Section 6.10 DDL. `ActionDecisionRow` carries it too.
2. **STORY-014 plan: the input is the frozen `ActionDecision`.** That is the Section 6.2 fields plus `operations`, `operation` and `arguments` (`repr=False`). `record(decisions, identity, audit_id=None, session_id=None)` keeps its Section 10 signature. Nothing in `action_policy.py` changes.
3. **STORY-012 plan: redact the stored `http` target.** `Operation.target` for `http` is the whole URL, query string included. `target_preview` stores it with **query and fragment values** redacted and the keys kept. The AC tests say so explicitly (Task 5, group G3).

## Design decisions (for the implementer and the orchestrator)

### P-1. Where the 500 and the timestamp format come from

`record()` imports `_PREVIEW_LENGTH` and `_TIMESTAMP_FORMAT` from `app.services.audit_logger` (`audit_logger.py:8-9`), and `hash_prompt` from `app.services.duplicate_checker` (`duplicate_checker.py:23-24`), the same import `audit_logger.py:6` makes. Importing the constants keeps "the 500-character preview of `audit_logger`" (Section 6.12, story note) as one number rather than a copy. The underscore names are module-private by convention, so the import gets a comment citing Section 6.12. The repo does copy `_TIMESTAMP_FORMAT` in three places (`database.py:43`, `duplicate_checker.py:10`, `audit_logger.py:8`). The preview length exists only in `audit_logger`, and the PRD says to reuse it.

### P-2. What each column holds (from `ActionDecision` d and `Identity` i)

| Column | Value |
|---|---|
| `timestamp` | one `datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)` per `record()` call |
| `audit_id`, `session_id` | the arguments as given (`None` gives NULL) |
| `user_id`, `role` | `i.user_id`, `i.role` |
| `tool_call_id`, `tool_name` | `d.tool_call_id`, `d.tool_name` (already `""` when not a string) |
| `operation_kind` | `d.operation.kind` if `d.operation` else NULL. This is NULL for `tool.unknown`, `tool.malformed` and `tool.opaque`, and for the fail-closed path |
| `target_preview` | `d.operation.target` → `_redact_url()` when `kind == "http"` → `[:500]`; NULL when `d.operation is None`. The target is "what the rule judged" (Section 6.10): the *reported* operation, not `operations[0]` |
| `arguments_hash` | `hash_prompt(d.arguments)` over the full string, so `""` gives the hash of `""` |
| `arguments_preview` | `d.arguments[:500]`, unredacted, per T10 (see Q1) |
| `decision`, `rule`, `reason`, `granted_by`, `policy_digest` | copied |
| `classifications` | `json.dumps([{"rule": c.rule, "kind": c.operation.kind if c.operation else None, "detail": c.detail} for c in d.classifications], ensure_ascii=False, separators=(",", ":"))`. The `json.dumps` style follows `duplicate_checker.py:52`. `kind` is the operation kind, as in the Section 10 example `{"rule": "sql.ddl", "kind": "sql", "detail": "DROP"}` |

Redaction runs **before** truncation, so a cut can never split a key from its `***`, and a long URL is redacted all the way through.

### P-3. `_redact_url(url) -> str`: a string split, not `urlsplit`

The function is pure, total and never raises. It works on the raw string so that a URL `urlsplit` rejects is still redacted. Some of those URLs reach the audit: `net.unparsed` keeps the URL as its target, for example a bad bracketed host (`network.py:227`).

- `head, hash_sep, fragment = url.partition("#")`, then `base, q_sep, query = head.partition("?")`. These are the same first-`#`, then-first-`?` boundaries `urlsplit` uses.
- The query and the fragment each go through `_redact_pairs(text)`: split on `&`; each item `k=v` becomes `k=***`, an item `k=` stays `k=`, and an item with no `=` becomes `***`. A bare item is the value (`?AKIA…` or `#token`), and redacting it fails safe. `***` is the repo's existing marker (`database.py:458` `_REDACTED = "***"`), defined locally in `action_audit`.
- The rebuilt string is `base + q_sep + _redact_pairs(query) + hash_sep + _redact_pairs(fragment)`. An empty query or fragment stays empty, so `https://x/a?` stays `https://x/a?`.
- **Userinfo (see Q2).** The binding decision names query and fragment only. Section 6.10 already admits a `user:token@host` URL (`https://allowed.com@evil.com` is `net.unparsed`, but its target is still the whole URL). So `_redact_url` also replaces any userinfo in the authority of `base` with `***`. The authority is the text after the first `//` and up to the next `/`. If it contains `@`, everything before its last `@` becomes `***`. This is one extra branch with its own test. If the orchestrator wants the narrow reading, delete the branch and the test.

The target of a `shell` operation is not URL-redacted, even when it contains `curl https://…?token=`, and neither is `arguments_preview`. See Q1.

### P-4. One transaction, ids in order

`insert_action_decisions(rows)` runs one `with _session() as conn:` block. Each row is one `conn.execute(INSERT …)`, and `cursor.lastrowid` is collected in order, the `insert_audit_log` idiom (`database.py:788-840`). `_Connection.__exit__` rolls back on any exception (`database.py:346-351`), so a failure on row *k* leaves no row of the batch. Two other options were rejected:

- `executemany`: it gives no per-row id.
- A multi-row `INSERT … RETURNING id`: RETURNING order is not guaranteed by SQLite.

An empty `rows` returns `[]` without opening a session. The same holds for `record([])`: an empty response writes nothing and costs no round trip.

### P-5. Reads

- `list_action_decisions(limit: int = 100, user_id: Optional[str] = None, decision: Optional[str] = None) -> list[ActionDecisionRow]` builds `WHERE` from whichever filters are given and orders by `ORDER BY id DESC LIMIT ?`. The docstring gives the reason: a TEXT timestamp ties within one second (PRD-006 Section 13, as `list_chat_messages` documents at `database.py:2151-2161`). `limit` defaults to 100, matching `list_audit_logs` and the Section 10 API default. The DB layer does not validate `decision` (STORY-016's router does, with 422). An unknown value simply matches no row.
- `count_action_decisions() -> dict[str, int]` runs `SELECT decision, COUNT(*) AS n FROM action_decisions GROUP BY decision`. It starts from `{d: 0 for d in ACTION_DECISION_VALUES}`, so an empty table gives all zeros, which STORY-016 needs. It takes no parameters, matching F10. `ACTION_DECISION_VALUES` is in `models.py` because `app/db` imports nothing from `app/services` (verified: `database.py:14-22`). A test pins it equal to `action_classifiers.DECISIONS`.
- `_row_to_action_decision_row(row)` maps a row by column name, the `_row_to_audit_log` style (`database.py:888-935`).

### P-6. Indexes

The indexes are exactly Section 6.10's: `idx_action_decisions_user_ts ON action_decisions(user_id, timestamp)` and `idx_action_decisions_audit ON action_decisions(audit_id)`.

- STORY-016's `GET /audit/actions` for `audit:read:own` filters on `user_id`, which `user_ts` serves. Its `ORDER BY id DESC` reads the rowid that SQLite appends to every secondary index.
- PRD-017's join from an audit row uses `audit_id`.
- The `decision` filter and the `GROUP BY` have no index, which is acceptable for an append-only audit read behind admin permissions. Adding one would go beyond Section 6.10.

In `init_db()` the CREATE and both indexes go **last** in the block, after `CREATE_USAGE_DAILY_TABLE`. The position is not load-bearing because no other statement reads this table. The new table needs no `_add_missing_columns` pass.

### P-7. Failure surface

`record()` does not catch. A storage failure surfaces as `app.db.errors.StorageError`/`IntegrityError` through `_session()`/`_translated()`. What the live path does on an audit failure is for PRD-017, its first caller. The module docstring says so.

---

## Patterns to Follow

### Naming / schema comment and CREATE

```python
# SOURCE: app/db/models.py:216-235
# No foreign key to users, for the reason the chat tables give below, and for
# one of its own: the break-glass `admin` identity has no users row and is
# still counted (PRD Section 6.6).
#
# A new table, so it arrives by CREATE alone and has no added-columns mapping.
...
CREATE_USAGE_DAILY_TABLE = """
CREATE TABLE IF NOT EXISTS usage_daily (
```

The no-FK reason to cite: `app/db/models.py:247-252` (chat_messages). Index constants: `app/db/models.py:266-269`, `339-342`. Row dataclass with `id` last: `app/db/models.py:475-508` (`StoredMessage`: "this dataclass mirrors the table"). Frozen dataclass: `app/db/models.py:440-463` (`UsageDay`).

### Transactions and writes

```python
# SOURCE: app/db/database.py:1985-2003 (delete_chat_session: two statements, one _session() block = one transaction)
    with _session() as conn:
        conn.execute(...)
        cursor = conn.execute(...)
        return cursor.rowcount == 1
```

`init_db()` single block: `app/db/database.py:715-729`. Per-row `lastrowid`: `app/db/database.py:788-840`. ORDER BY id: `app/db/database.py:2148-2192`.

### Error handling

```python
# SOURCE: app/db/database.py:588-623 (_translated): a NOT NULL / UNIQUE failure arrives as
# app.db.errors.IntegrityError(constraint, message); _Connection.__exit__ (database.py:345-351) rolls back.
```

### Previews and hashes

```python
# SOURCE: app/services/audit_logger.py:6-9, 78-81
from app.services.duplicate_checker import hash_prompt
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_PREVIEW_LENGTH = 500
...
        prompt_hash=hash_prompt(prompt),
        prompt_preview=prompt[:_PREVIEW_LENGTH],
```

### Tests

```python
# SOURCE: tests/test_usage_storage.py:74-150
def test_init_db_creates_usage_daily_with_its_columns(temp_db):
    with get_connection() as conn:
        info = list(conn.execute("PRAGMA table_info(usage_daily)"))
    assert [(r["name"], r["pk"], r["dflt_value"]) for r in info] == _COLUMNS
...
def test_init_db_adds_usage_daily_to_a_pre_usage_database(uninitialized_db, db_connect):
    legacy = db_connect(uninitialized_db)
    legacy.execute(CREATE_AUDIT_LOGS_TABLE)
    ...
def test_init_db_creates_usage_daily_inside_the_one_bootstrap_session(uninitialized_db, monkeypatch):
    # _Recording proxy over database.get_connection
```

The fixtures are `temp_db`, `uninitialized_db` and `db_connect` (`tests/conftest.py:740-760, 789`). Requesting any of them applies the `db` marker automatically (`tests/conftest.py:100-105, 192-195`). Building decisions: `tests/test_action_policy.py:45-64` (`Identity("u","user")`, `_call`, `_with_rules`, `_grant`). The module header env defaults follow `tests/test_usage_storage.py:7-10`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Comment block + `CREATE_ACTION_DECISIONS_TABLE` (6.10 + `reason`), `CREATE_ACTION_DECISIONS_USER_TS_INDEX`, `CREATE_ACTION_DECISIONS_AUDIT_INDEX`, `ACTION_DECISION_VALUES`, frozen `ActionDecisionRow` |
| `app/db/database.py` | UPDATE | Imports; `init_db()` creates table + 2 indexes (+ docstring paragraph); `insert_action_decisions`, `_row_to_action_decision_row`, `list_action_decisions`, `count_action_decisions` |
| `app/services/action_audit.py` | CREATE | `record()`, `_redact_url`, `_redact_pairs`, `_classifications_json`, `_row_of` |
| `tests/test_action_audit.py` | CREATE | AC 1–5 plus redaction and edge cases |
| `tests/test_two_instance_smoke.py` | UPDATE | `test_both_instances_boot_simultaneously_against_one_database` (`:859-865`): add `"action_decisions"` to the exact sorted table list, with a comment citing PRD-016 STORY-015 / D8 |

Not changed: `app/services/action_policy.py`, `app/services/audit_logger.py`, routers, schemas, chat_ui.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Schema in `app/db/models.py`

- **File**: `app/db/models.py`
- **Action**: UPDATE (append after `CREATE_CHAT_MESSAGES_SESSION_INDEX`, `:339-342`; the dataclass after `StoredMessage`)
- **Implement**:
  - Comment block in the `usage_daily` style. It covers:
    - the action decision audit (PRD-016 Section 6.10, D8): one row per tool call, allowed calls included, because `audit_logs` is one row per request;
    - `audit_id` is nullable and points at `audit_logs.id`. There is **no foreign key**, for the reason `chat_messages` gives (cite it), and a direct caller has no audit row;
    - a new table arrives by CREATE alone with no added-columns mapping;
    - `reason` is stored by orchestrator decision (STORY-014 plan), beyond Section 6.10's DDL;
    - rows are read `ORDER BY id`, never by the TEXT timestamp (PRD-006 Section 13);
    - `target_preview` redacts `http` query and fragment values; `arguments_preview` is the raw 500 characters (T10).
  - `CREATE_ACTION_DECISIONS_TABLE` is Section 6.10 verbatim, with its inline comments, plus `reason TEXT NOT NULL,` after `rule`.
  - `CREATE_ACTION_DECISIONS_USER_TS_INDEX = ("CREATE INDEX IF NOT EXISTS idx_action_decisions_user_ts " "ON action_decisions(user_id, timestamp)")` and `CREATE_ACTION_DECISIONS_AUDIT_INDEX` (`… idx_action_decisions_audit ON action_decisions(audit_id)`). Each gets a one-line comment naming its reader: STORY-016's per-user read, and PRD-017's join.
  - `ACTION_DECISION_VALUES: tuple[str, ...] = ("allow", "flag", "deny")`, with a comment that it mirrors `action_classifiers.DECISIONS`, that `app/db` imports nothing from `app/services`, and that a test pins the two equal.
  - `@dataclass(frozen=True) class ActionDecisionRow`. Its fields are in table column order, `id: Optional[int] = None` comes last (`StoredMessage` precedent), and `classifications: str` holds the JSON text the column holds. The docstring follows `StoredMessage`'s "mirrors the table, decoding belongs to the reader".
- **Mirror**: `app/db/models.py:205-235`, `247-252`, `475-508`, `440-463`
- **Validate**: `.venv/Scripts/python -c "from app.db.models import CREATE_ACTION_DECISIONS_TABLE, ActionDecisionRow; print('OK')"`

### Task 2: Storage functions in `app/db/database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - Import the three statements, `ACTION_DECISION_VALUES` and `ActionDecisionRow` (alphabetical, in the `:22-40` block).
  - `init_db()`: after `conn.execute(CREATE_USAGE_DAILY_TABLE)` (`:729`), execute the table and then both indexes. Add a docstring paragraph in the existing per-PRD voice: "PRD-016 STORY-015 adds `action_decisions` and its two indexes, a new table, so CREATE alone … no other statement reads it, so position is not load-bearing; the indexes follow their table".
  - `insert_action_decisions(rows: Sequence[ActionDecisionRow]) -> list[int]` (P-4). The docstring covers one block, one transaction, rollback on any failure, ids in input order, and that `[]` opens no session. Place it after the chat functions at the end of the file, under a `# --- Action decisions (PRD-016 STORY-015) ---` header.
  - `_row_to_action_decision_row`, `list_action_decisions` and `count_action_decisions` (P-5). The `list_action_decisions` docstring carries the ORDER BY id reason. Build the `WHERE` from a list of fixed clause strings plus a parameter list; no user text ever reaches the SQL.
- **Mirror**: `app/db/database.py:788-840`, `960-976` (but `id DESC`), `1985-2003`, `2148-2192`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: `app/services/action_audit.py`

- **File**: `app/services/action_audit.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring, citing PRD-016 Sections 4, 6.10, 6.12, F10, T10 and D8:
    - the I/O edge (Section 6.12): this module holds all of the action audit's database I/O, and the engine stays pure;
    - the column mapping (P-2);
    - the redaction decision and its limits: URL values in `shell` targets and in `arguments_preview` are not redacted (T10);
    - no catch (P-7);
    - one timestamp per call.
  - Imports: `json`, `datetime`/`timezone`, `typing`, `from app.db.database import insert_action_decisions`, `from app.db.models import ActionDecisionRow`, `from app.services.audit_logger import _PREVIEW_LENGTH, _TIMESTAMP_FORMAT` (with a Section 6.12 comment), `from app.services.duplicate_checker import hash_prompt`. Use `TYPE_CHECKING` imports for `ActionDecision` and `Identity`, the `action_policy.py:71-72` idiom, so importing the audit module does not import the engine.
  - `_REDACTED = "***"`.
  - `_redact_pairs(text: str) -> str` and `_redact_url(url: str) -> str` (P-3), with short docstrings and the userinfo branch.
  - `_classifications_json(d) -> str` (P-2).
  - `_target_preview(d) -> Optional[str]`.
  - `record(decisions, identity, audit_id=None, session_id=None) -> list[int]`. It builds one `ActionDecisionRow` per decision, in order, with one timestamp, and returns `insert_action_decisions(rows)`. The docstring states the Section 10 signature, one transaction, ids in order, and `[]` → `[]`.
- **Mirror**: `app/services/audit_logger.py:12-107`; docstring voice of `app/services/action_policy.py:1-58`
- **Validate**: `.venv/Scripts/python -c "import app.services.action_audit; print('OK')"`, then the backend import check

### Task 4: Exact table list in the two-instance smoke test

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: At `:855-865`, insert `"action_decisions",` as the first element, since the list is `sorted()` (`:237-251`). Extend the existing comment: "Six since PRD-016 STORY-015 added the action decision audit (D8)." Change nothing else.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest "tests/test_two_instance_smoke.py::test_both_instances_boot_simultaneously_against_one_database" -q -p no:cacheprovider`

### Task 5: `tests/test_action_audit.py`

- **File**: `tests/test_action_audit.py`
- **Action**: CREATE
- **Implement**: The module docstring cites PRD-016 STORY-015, the AC numbers, the `db` marker, and the container-restart note. The env defaults header copies `tests/test_usage_storage.py:7-10`. Decisions are built with the real engine: `evaluate(_call(...), USER, policy)` with `_with_rules`, so every input is a genuine STORY-014 `ActionDecision`. The fixed inputs are:
  - allow: `query {"sql": "SELECT 1"}`;
  - flag: `bash {"command": "make release"}` under `shell.unlisted: Rule("flag", "action:shell:exec")`;
  - deny: `query {"sql": "DROP TABLE users"}`.

  Groups:
  - **G1 (AC 1), schema**:
    - `PRAGMA table_info(action_decisions)` gives the names in order (Section 6.10 + `reason` after `rule`) and the `notnull` flags. Compare against a `_COLUMNS` list whose comment cites 6.10 and the `reason` decision.
    - Both indexes exist, with their columns in order (`PRAGMA index_info`).
    - A second `init_db()` keeps a recorded row and raises nothing.
    - On a pre-PRD database (`uninitialized_db` + `db_connect` with the five legacy CREATEs and a seeded `audit_logs`/`users` row), `init_db()` creates the table and both indexes. The `sqlite_master.sql` of every pre-existing table and index is byte-identical before and after, and the seeded rows survive.
    - The CREATE rides the one bootstrap session (the `_Recording` proxy from `test_usage_storage.py:116-150`).
    - `ACTION_DECISION_VALUES == action_classifiers.DECISIONS`.
  - **G2 (AC 2), record a batch**:
    - Three decisions, `record(ds, Identity("u", "user"), audit_id=7, session_id="s1")`, return three ids, strictly increasing and in input order.
    - Reading back by id: `audit_id == 7`, `session_id == "s1"`, `user_id`/`role` from the identity, and `decision`/`rule`/`reason`/`granted_by`/`policy_digest`/`tool_call_id`/`tool_name`/`operation_kind` equal to each decision's.
    - The `_Recording` proxy shows exactly one session holding three `INSERT INTO action_decisions`.
    - All three rows share one timestamp.
    - A granted decision (dba holding `action:sql:write`, `DELETE FROM t WHERE id = 3`) stores `granted_by == "action:sql:write"`.
  - **G3 (AC 3), hash, previews, classifications, redaction**:
    - A `bash` call whose arguments exceed 500 characters (`{"command": "echo " + "a"*600}`): `arguments_hash == hash_prompt(full)`, `arguments_preview == full[:500]`, `target_preview == target[:500]`, `len == 500`.
    - `classifications` parses as a JSON list of `{rule, kind, detail}`, equal to the decision's classifications in order. Use a multi-classification call, `npm test && rm -rf build`, which gives two entries.
    - A `tool.unknown` decision stores `operation_kind` and `target_preview` NULL and `kind: null` in its classification.
    - **http redaction, stated in the test names**: `webfetch {"url": "https://api.example.com/v1?token=abc&q=1#access_token=zzz"}` stores `target_preview == "https://api.example.com/v1?token=***&q=***#access_token=***"`, while `arguments_preview` still holds the raw JSON (T10, asserted so the boundary is explicit).
    - Pure `_redact_url` table tests: no query (unchanged); `?a` → `?***`; `?a=` kept; `?a=1&&b=2`; fragment-only; `?` and `#` empty; a non-parseable URL (`http://[bad/x?k=v`) still redacted; userinfo `https://user:tok@evil.com/p` → `https://***@evil.com/p` (P-3, Q2); a redacted URL longer than 500 is truncated after redaction.
  - **G4 (AC 4), NULLs and atomicity**:
    - `record(ds, identity)` with `audit_id` and `session_id` omitted stores NULL in both.
    - `insert_action_decisions([good, bad, good])`, where `bad` has `decision=None`, raises `IntegrityError` and leaves `COUNT(*) == 0`.
    - A midway failure through `record()`: monkeypatch `database.get_connection` with a proxy that raises `StorageError` on the second `INSERT INTO action_decisions` leaves `COUNT(*) == 0`.
    - `record([], identity) == []` and opens no session (recording proxy, zero sessions).
  - **G5 (AC 5), reads**:
    - Rows are recorded for two users (`u` and `v`) with a known mix of decisions.
    - `list_action_decisions(100)` returns all rows ordered by `id` descending.
    - `user_id="u"` returns only u's rows; `decision="deny"` returns only denies; both filters combined return the intersection; `limit=1` returns the newest.
    - Rows recorded within the same second still come back by id. This holds by construction, since one batch has one timestamp; assert that the order equals the reverse insertion order.
    - `count_action_decisions()` equals the per-decision tally computed in Python. On an empty table it is `{"allow": 0, "flag": 0, "deny": 0}`.
    - The returned objects are `ActionDecisionRow` and are frozen (`dataclasses.FrozenInstanceError`).
- **Mirror**: `tests/test_usage_storage.py:1-150`; `tests/test_action_policy.py:30-80`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_audit.py -q -p no:cacheprovider`

### Task 6: Targeted regression run

- **Validate** (one invocation):
  `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_audit.py tests/test_usage_storage.py tests/test_conftest_fixtures.py tests/test_untouched_app.py "tests/test_two_instance_smoke.py::test_both_instances_boot_simultaneously_against_one_database" -q -p no:cacheprovider`
  followed by `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db.py -k "init_db" -q -p no:cacheprovider`. These cover the migration, idempotency, the single-session/no-ALTER claims and the pre-PRD paths. All of `test_db.py` is about 3,400 lines and stays with the orchestrator's full run. If many `db` tests error at fixture setup, run `docker restart harness-libsql-dev` and rerun.

---

## End-to-End Tests

- [ ] `record()` of three real `evaluate()` results against the libSQL dev server writes three rows that read back through `list_action_decisions` (Task 5 G2/G5; the DB round trip is the E2E for a story with no route)
- [ ] The backend imports: `.venv/Scripts/python -c "from app.main import app; print('OK')"`, so `init_db()` and the imports still load
- [ ] Two instances booting together converge on the new schema (Task 4)

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_action_audit.py tests/test_usage_storage.py tests/test_conftest_fixtures.py tests/test_untouched_app.py "tests/test_two_instance_smoke.py::test_both_instances_boot_simultaneously_against_one_database" -q -p no:cacheprovider
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db.py -k "init_db" -q -p no:cacheprovider
# Full suite: deferred to orchestrator (user decision)
```

---

## Acceptance Criteria

(Copied from story `STORY-015`)

- [ ] AC 1: Given a fresh database and one created before this PRD, when `init_db()` runs, then `action_decisions` exists with the columns of PRD Section 6.10 and both indexes; no existing table is altered; a second `init_db()` is a no-op. *Covered by: G1 (columns + `reason` per binding decision 1, both indexes, pre-PRD sqlite_master byte-identical, second call keeps rows, one bootstrap session). Note: on a fresh database, "a second `init_db()` is a no-op" is the existing `test_db.py::test_init_db_issues_no_alter_when_schema_is_current`, which is in the targeted run.*
- [ ] AC 2: Given three `ActionDecision`s (allow, flag, deny) and an identity, when `record(decisions, identity, audit_id=7, session_id="s1")` runs, then three rows are written in one transaction with `audit_id=7`, `session_id="s1"`, the identity's `user_id` and `role`, and three ids are returned in order. *Covered by: G2.*
- [ ] AC 3: Given a decision on arguments longer than 500 characters, when recorded, then `arguments_hash` is `hash_prompt()` of the full string, `arguments_preview` and `target_preview` are the first 500 characters, and `classifications` is a JSON array of `{rule, kind, detail}` for every classification. *Covered by: G3; plus `http` query/fragment values redacted in `target_preview` (binding decision 3).*
- [ ] AC 4: Given `record(...)` with `audit_id` omitted, when it runs, then the rows store `NULL`; given an insert failure midway, then no row of that batch is written. *Covered by: G4 (constraint failure at the DB layer and injected failure through `record()`).*
- [ ] AC 5: Given rows for two users, when `list_action_decisions(limit, user_id=None, decision=None)` and `count_action_decisions()` run, then they filter by user and decision, return newest first by `id`, and the counts match per decision. *Covered by: G5.*
- [ ] All tasks completed
- [ ] Backend import passes (no frontend lint in this repo)
- [ ] Follows existing patterns

---

## Risks

| Risk | Mitigation |
|---|---|
| `lastrowid` per statement inside one open Hrana transaction on the libSQL remote client | `append_chat_message` (`database.py:2045-2146`, `lastrowid` at `:2145` inside `_session()`) already reads `lastrowid` inside `_session()`. G2 asserts the ids against the rows read back, so a wrong id fails the test |
| The exact table list in `test_two_instance_smoke.py` breaks without Task 4 | Task 4 updates it, with a PRD-016 comment; it is the only exact-list assertion (`grep '"usage_daily",' tests/`) |
| Importing `audit_logger`'s underscore constants couples the modules | This is intentional (Section 6.12: one preview convention), and the import carries a comment saying so. The alternative is a copied `500` that can drift |
| Mass `db` fixture errors on this machine | `docker restart harness-libsql-dev`, then rerun (repo convention) |
| `PYTHONUTF8` missing makes `test_db_isolation_harness.py` and others fail | Every pytest command above is prefixed |

## Open questions for the orchestrator

- **Q1. Is `arguments_preview` raw (T10) while `target_preview` is redacted?** As planned, an `http` call's `arguments_preview` still carries `?token=…`, and so does a shell `curl` target. The binding decision names only the stored target, and T10 explicitly accepts the preview exposure. The tests assert this boundary so that it is visible. Redacting URLs inside arguments and shell text would need a URL scan of free text; that would be a new decision.
- **Q2. Should userinfo be redacted too?** P-3 also masks `user:pass@` in an `http` target. This goes beyond the binding decision's "query and fragment", but it is the same class of credential (T8/T11, `network.py` already refuses to put userinfo in `detail`). It is one branch and one test, easy to drop.
- **Q3. The STORY-016 note conflicts with binding decision 1.** The STORY-016 story's Technical Notes say "`reason` is not a column: rebuild it from `rule` …". That contradicts the STORY-014 decision this plan applies (`reason` is stored). STORY-016's note should be updated to read the column. This plan does not edit STORY-016.
- **Q4. `reason` is a deviation from the Section 6.10 DDL.** It is recorded here and in the models comment. The PRD text is unchanged; tell the planner if the PRD should be amended in STORY-020 (docs).
