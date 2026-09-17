---
id: PRD-009
slug: duplicate-rescoping
title: Duplicate Detection Rescoping — Per-Caller, Conversation-Shaped Keys
status: draft
base_branch: main
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-16
updated: 2026-09-16
---

## 1. Executive Summary

Duplicate detection is the product's central control, and it is scoped wrong for any caller that retries or converses. `find_duplicate_timestamp` ([app/db/database.py:758](../../../app/db/database.py)) runs `WHERE prompt_hash = ? AND timestamp >= ?` over every `audit_logs` row: no `user_id`, no `success`, no distinction between a row that reached the model and one that was itself blocked. Three consequences follow, and each is observable in `POST /query` today:

1. **A retry after a failure is held as a duplicate of the failure.** The pipeline logs both failure arms (`PiiRedactorError` on the prompt, `OpenRouterError` upstream) with the prompt and `success=False`, so the user's second attempt matches the attempt that never produced an answer. A human retries once and gives up; a coding agent retries automatically, and that turns it into a loop.
2. **The hash is global.** `check_duplicate(prompt)` ([app/services/duplicate_checker.py](../../../app/services/duplicate_checker.py)) takes a string and nothing else, so two users sending "summarise this ticket" block each other.
3. **Multi-turn has no definition.** The README's [Multi-turn context](../../../README.md#multi-turn-context) section names this as the reason multi-turn is deferred: "yes", "go on" and "thanks" would collide across every user. PRD-010 is blocked on a key that does not exist yet.

This PRD redefines a duplicate as **the same caller asking the same thing in the same context within the window**, and nothing else. It adds a `dedup_key` column to `audit_logs`, computed by a pure function over a *conversation* (a sequence of role/content turns), not a string. Single-turn `/query` is the case where the prefix is empty. The lookup is scoped by `user_id`, and only rows that got a real verdict count: they reached the model or were blocked by a content check. Failures, policy denials and duplicate-blocked rows are excluded. `prompt_hash` and everything `/audit`, `/stats` and the admin console read from it stay byte-for-byte unchanged.

**MVP goal:** a retry after an upstream failure goes through, the same prompt from two users goes through, and the same prompt from the same user within 24h of a success is still blocked. The six `/query` outcomes are pinned before the change and still hold after it.

## 2. Mission

Make "duplicate" mean what a user would call a duplicate, in a shape multi-turn can use as it is, without weakening the control in any case the threat reasoning has not named.

Core principles:
- **Pin before you change.** Characterization tests capture today's behaviour, including the parts this PRD deliberately changes, before any production line moves. Each behaviour change then appears as an explicit edit to a test that already existed, never as a test that silently started passing.
- **Only a real verdict counts.** A row counts as a prior query if the request reached the model or a content check blocked it. A failure, a policy denial or a duplicate block is not a prior query.
- **The key takes a conversation, not a string.** One function defines the key for every current and future ingress. `/query` calls it with one turn, PRD-010 with many, and nobody writes a second key.
- **Additive schema, untouched evidence.** A new nullable column plus a new index, converged by `init_db()` in the PRD-003/005/008 pattern. `prompt_hash` keeps its meaning, so every existing row, `/audit` response and admin figure is unchanged.
- **Every weakening is written down.** Per-user scoping lets N accounts send the same prompt N times. The PRD accepts that on purpose, names it in the threat reasoning, and assigns the mitigation to PRD-013. It does not happen as a side effect.

## 3. Target Users

**End User (Employee)** — the person whose second attempt is refused today after the first one failed with a 502. They also get blocked by a colleague's identical prompt they never saw. They need a duplicate block to mean *"you already asked this"*, which is the only reading the block message offers them. Technical level: unchanged. They type prompts in the chat UI and never see a key.

**Integrating Developer / Coding Agent operator** — runs clients that retry on 5xx and, once PRD-010 and PRD-014 land, resend whole conversations. They need retries to be safe and conversational turns ("continue", "yes") not to collide across the whole deployment. `POST /query`'s request and response shapes do not change for them.

**Security/Compliance Admin** — owns the control being rescoped. They need the change reasoned about rather than just implemented: what gets weaker (multi-account repetition), what gets stronger (a denial can no longer be used to poison another user's window), and where the remaining gap is covered (PRD-013). Their `/audit`, `/stats` and console figures (`blocked_duplicates` among them) must mean exactly what they meant before.

**PRD-010 implementer** — an internal persona, but a real one. They need a key function whose input already accepts a list of turns, so the multi-turn pipeline feeds it the real conversation without redefining it.

## 4. MVP Scope

### In Scope

**Threat reasoning & characterization**
- [ ] A written threat analysis of the rescoped control: what each change weakens, strengthens or leaves unchanged. It lives in Section 9 of this PRD and is condensed into the README
- [ ] Characterization tests pinning today's lookup: failed rows match, other users' rows match, denial rows match, duplicate-blocked rows extend the window (see D3 correction in Section 6.4)
- [ ] A six-outcome regression baseline for `POST /query` (Section 11), captured before any change

**Schema (`app/db/`)**
- [ ] `audit_logs.dedup_key TEXT`, nullable, declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`
- [ ] `CREATE INDEX IF NOT EXISTS idx_audit_logs_dedup ON audit_logs(user_id, dedup_key, timestamp)`, created in `init_db()` **after** `_add_missing_columns()`
- [ ] `AuditLog.dedup_key: Optional[str] = None`; `insert_audit_log` writes it

**Key function (`app/services/duplicate_checker.py`)**
- [ ] `dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str`, a pure function with no I/O
- [ ] Single-turn input yields an empty prefix hash, so `/query` is the special case and not a separate code path
- [ ] Refuses input it has no rule for (empty sequence, last turn not `user`, any `tool` turn) with `ValueError`, not a guess

**Lookup (`app/db/database.py`)**
- [ ] Excludes `success = 0` rows
- [ ] Excludes policy denials (`denied_permission IS NOT NULL`) (D1)
- [ ] Excludes duplicate-blocked rows (`was_duplicate_blocked = 1`) (D3)
- [ ] Scoped by `user_id`
- [ ] Matches on `dedup_key`; `ORDER BY timestamp ASC LIMIT 1` retained so `first_query_at` is the earliest qualifying row

**Pipeline & logging (`app/services/`)**
- [ ] `run_query` computes the key once, before authorization, from `identity.user_id` and the one-turn conversation `[user: prompt]`
- [ ] `check_duplicate(user_id, key)` replaces `check_duplicate(prompt)`
- [ ] `log_query(..., dedup_key=...)` on all seven pipeline call sites, so every row `run_query` writes carries the key
- [ ] The router's foreign-session refusal (`app/routers/query.py`) writes `dedup_key=None`, documented inline: that row is `success=False` and can never match

**Tests**
- [ ] Retry-after-failure: an `OpenRouterError` followed by the same prompt reaches the model. Same for an input `PiiRedactorError`
- [ ] Two users, same prompt, both reach the model
- [ ] Same user, same prompt, after a success, within 24h: blocked, with `first_query_at` = the success's timestamp
- [ ] Deliberate, commented updates to the three contract tests this PRD invalidates (Section 6.5)
- [ ] Six-outcome regression passes, with outcome assertions unmodified

**Documentation**
- [ ] README: the Multi-turn context section no longer names duplicate detection as its blocker. The Features table row and the OpenAI-compatible endpoint's "what gets hashed" open question are updated
- [ ] README: the sentence claiming a failed duplicate check "lets the query through" is corrected to the tested behaviour (500). See Appendix, *Observed discrepancy*
- [ ] `.env.example`: confirmed to need no change (no new setting, window unchanged), recorded in the story report

### Out of Scope

- [ ] Semantic / near-match duplicate detection (separate roadmap item)
- [ ] Accepting message arrays in `run_query`, `QueryRequest` or the chat UI (PRD-010)
- [ ] `tool`-role turns in the key (PRD-016; this PRD refuses them explicitly, D4)
- [ ] Changing the 24h window or making it configurable
- [ ] Recomputing, renaming or re-meaning `prompt_hash`, or exposing `dedup_key` on `GET /audit` (D5)
- [ ] Backfilling `dedup_key` on pre-existing rows (D6)
- [ ] Rate limits, multi-account abuse detection, counting failures toward usage (PRD-013)
- [ ] Changing the duplicate block response shape or the chat UI's duplicate bubble
- [ ] Changing the storage-failure behaviour of the duplicate check (still 500)

## 5. User Stories

1. **As an end user, I want a retry after an upstream error to go through, so that a provider hiccup does not lock me out of my own question for a day.**
   *Example:* Juan sends "draft the Q3 vendor summary". OpenRouter times out → 502, and a `success=0` row is logged. Juan sends it again ten seconds later. Today he gets `BLOCKED: Duplicate query within 24 hours`. After this PRD, the request reaches the model.

2. **As an end user, I want my prompt not to be blocked by someone else's identical prompt, so that a common question works for everyone who asks it.**
   *Example:* María sends "summarise this week's incidents" at 09:00. Juan sends the identical text at 09:05. Both get a model response, and each row carries a different `dedup_key`.

3. **As a security admin, I want a genuine repeat from the same user to still be blocked, so that the control keeps doing the job it was built for.**
   *Example:* Juan's 09:00 prompt succeeds. His identical 14:00 prompt returns `BLOCKED` with `first_query_at: "…T09:00:00Z"`, exactly as today.

4. **As a security admin, I want policy denials and duplicate blocks not to count as prior queries, so that the window measures real answers and a blocked row cannot extend it.**
   *Example:* Juan sends a prompt with a disallowed model and gets denied. He resends it with an allowed model, and it reaches the model. A row blocked at 23h no longer keeps a prompt blocked at 25h.

5. **As a PRD-010 implementer, I want a key function that already takes a list of turns, so that multi-turn feeds it the real conversation without a second definition of "duplicate".**
   *Example:* `dedup_key("juan", [user("hi"), assistant("hello"), user("yes")])` and `dedup_key("juan", [user("list files"), assistant("…"), user("yes")])` differ. `dedup_key("juan", [user("yes")])` equals the single-turn key `/query` computes for "yes".

6. **As an integrating developer, I want `POST /query` to return the same six outcomes for the same inputs, so that nothing I built against it changes.**
   *Example:* the success, three `BLOCKED` shapes, 502 and 500 responses in `tests/test_query_router.py` and `tests/test_integration.py` keep their status codes, bodies and audit-row counts.

7. **As a compliance admin, I want `/audit`, `/stats` and the console to report exactly what they reported before, so that historical figures stay comparable.**
   *Example:* `blocked_duplicates` still counts `was_duplicate_blocked = 1` rows, and `prompt_hash` on a new row still equals `sha256(prompt)`, so `tests/test_two_instance_smoke.py`'s `prompt_hash == hash_prompt(prompt_preview)` assertion holds.

8. **As a security admin, I want the weakened cases written down with their mitigations, so that the rescoping is a decision I can review and not a regression I discover.**
   *Example:* the README's duplicate-detection note states that per-user scope permits one repeat per account, and that PRD-013 limits cover it.

## 6. Core Architecture & Patterns

### 6.1 Request flow (unchanged order, changed inputs)

```
POST /query ─► identity ─► run_query
                             │
                             ├─ key = dedup_key(identity.user_id, [DedupTurn("user", prompt)])   ← new, pure
                             ├─ authorize / authorize_model / BYOK ──deny──► log_query(..., dedup_key=key)
                             ├─ check_duplicate(identity.user_id, key) ──dup──► log_query(..., was_duplicate_blocked, dedup_key=key)
                             ├─ detect_suspicious_pattern(prompt) ──hit──► log_query(..., dedup_key=key)
                             ├─ redact(prompt) ──PiiRedactorError──► log_query(success=False, dedup_key=key)
                             ├─ call_openrouter ──OpenRouterError──► log_query(success=False, dedup_key=key)
                             ├─ redact(response) ──PiiRedactorError──► log_query(success=False, dedup_key=key)
                             └─ log_query(success=True, dedup_key=key)
```

The check order does not change: authorization, then duplicate, then pattern, then redaction. `test_forbidden_identity_blocked_before_check_duplicate` and `test_pipeline_runs_both_checks_before_any_redaction` keep asserting it. The key is computed before authorization because it is pure, and because every row `run_query` writes carries it, denial rows included. Denial rows can never match, but a row with a missing key would stand out in a later investigation for no reason.

### 6.2 The key

```python
# app/services/duplicate_checker.py
class DedupTurn(Protocol):
    role: str
    content: str

DEDUP_KEY_VERSION = "v1"
_KEYED_ROLES = frozenset({"system", "user", "assistant"})

def dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str:
    if not turns:
        raise ValueError("dedup_key needs at least one turn")
    if any(t.role not in _KEYED_ROLES for t in turns):
        raise ValueError("dedup_key has no rule for this role (tool turns: PRD-016)")
    *prefix, last = turns
    if last.role != "user":
        raise ValueError("dedup_key keys on a final user turn")
    prefix_hash = "" if not prefix else _sha256_json([[t.role, t.content] for t in prefix])
    return _sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(last.content), prefix_hash])
```

Design decisions, each deliberate:
- **Structural `Protocol`, not a dataclass this PRD owns.** PRD-010's message model satisfies it without importing from here or converting. For `/query`, the pipeline passes a small private frozen dataclass.
- **Canonical JSON (`ensure_ascii=False`, `separators=(",", ":")`) as the framing.** Joining with a delimiter would let `("a|b", "c")` and `("a", "b|c")` collide. JSON arrays are unambiguous.
- **The last turn contributes `hash_prompt(content)`, the exact value stored in `prompt_hash`.** The key and the evidence column agree on what "the prompt" was, and the raw-text invariant `test_pii_dedup_isolation.py` protects carries over: the key is built from raw text, never redacted text.
- **`user_id` is inside the key *and* in the `WHERE` clause.** The column scopes the index range. The key's own uniqueness means a future lookup that forgets the column still cannot match across users. That is defence in depth, not redundancy.
- **Versioned.** PRD-016 changes the key's rules for `tool` turns. A version tag makes that a visible key change, not a silent collision between old and new formats inside one window.
- **Empty prefix is `""`, not `sha256("[]")`.** "No context" is a distinguished value, readable in a debugger.

### 6.3 The lookup

```python
def find_duplicate_timestamp(user_id: str, dedup_key: str, since: str) -> Optional[str]:
    # SELECT timestamp FROM audit_logs
    # WHERE user_id = ? AND dedup_key = ? AND timestamp >= ?
    #   AND success = 1
    #   AND was_duplicate_blocked = 0
    #   AND denied_permission IS NULL
    # ORDER BY timestamp ASC
    # LIMIT 1
```

`idx_audit_logs_dedup (user_id, dedup_key, timestamp)` serves the equality prefix and the range. The three flag predicates filter the handful of rows left inside one user's key range and do not need to be indexed.

What counts as a prior query after this PRD:

| Row written by | `success` | Other flags | Counts? | Change from today |
|---|---|---|---|---|
| Success | 1 | — | **Yes** | — |
| Suspicious-pattern block | 1 | `suspicious_pattern` set | **Yes** (D1: content check) | — |
| Duplicate block | 1 | `was_duplicate_blocked = 1` | No (D3) | **Changed** |
| Policy denial (`_deny`, 3 arms) | 1 | `denied_permission` set | No (D1) | **Changed** |
| Input `PiiRedactorError` | 0 | — | No | **Changed** |
| `OpenRouterError` | 0 | — | No | **Changed** |
| Output `PiiRedactorError` | 0 | — | No | **Changed** — see Risk 4 |
| Router foreign-session refusal | 0 | `dedup_key` NULL | No | **Changed** |
| Any row by another `user_id` | — | — | No | **Changed** |
| Pre-PRD row (`dedup_key` NULL) | — | — | No (D6) | **Changed** — see Risk 3 |

### 6.4 Decision D3: correcting the premise

The pre-PRD proposed "match the first non-blocked occurrence, *as today's `ORDER BY timestamp ASC` implies*". It does not. Today a duplicate-blocked row carries the same `prompt_hash` and falls inside the window, so once the original success ages past 24h, the blocked row becomes the earliest match. The window chains:

```
t=0h   success     (A)
t=23h  duplicate   (B, blocked — matched A)
t=25h  same prompt → A is outside the window, B is inside → BLOCKED, first_query_at = B   ← today
                   → no qualifying row                    → reaches model              ← after PRD-009
```

So D3 is a **behaviour change**, not a preservation. STORY-001 pins the chaining as today's behaviour, and the lookup story flips that test with a comment pointing here.

### 6.5 Contract tests this PRD deliberately invalidates

These tests exist to fail on exactly this kind of change. Each is updated in the story that breaks it, with a comment citing this section. None is deleted.

| Test | Pins | Update |
|---|---|---|
| `tests/test_pii_dedup_isolation.py::test_check_duplicate_public_contract_is_stable` | `check_duplicate(prompt: str)` | Pin `(user_id: str, key: str)`; the result dataclass fields are unchanged |
| `tests/test_pii_dedup_isolation.py::test_hash_prompt_call_sites_are_exactly_the_three_audited_ones` | `duplicate_checker.py: 1` | New count, with the raw-text justification for the `dedup_key` call site restated |
| `tests/test_pii_dedup_isolation.py::test_hash_prompt_only_ever_receives_raw_text` | Order of `hash_prompt` calls | Expected sequence updated. Every hashed text is still raw |
| Spies wrapping `check_duplicate(prompt)` in `test_pii_dedup_isolation.py`, `test_query_router.py:315`, `test_query_pipeline_authorization.py:47` | Spy signature | The wrapper signature changes. What each test asserts does not |
| `tests/test_duplicate_checker.py` (all) | Global `prompt_hash` lookup | Re-seeded with `user_id` + `dedup_key`. Window/boundary/earliest cases kept |
| `tests/test_audit_session_id.py:94` docstring | "global 24h exact-match" | Docstring corrected; test logic unchanged |

### 6.6 Directory structure (files touched)

```
app/
  db/
    models.py            # dedup_key column (CREATE + ADDED_COLUMNS), index DDL, AuditLog field
    database.py          # init_db() index, insert_audit_log, find_duplicate_timestamp
  services/
    duplicate_checker.py # DedupTurn, dedup_key, check_duplicate(user_id, key)
    audit_logger.py      # log_query(dedup_key=...)
    query_pipeline.py    # compute key once; pass to check + all seven log_query calls
  routers/
    query.py             # foreign-session refusal: dedup_key=None, commented
tests/
  test_duplicate_characterization.py   # new — STORY-001, today's behaviour pinned
  test_dedup_key.py                    # new — key function
  test_duplicate_scope.py              # new — retry-after-failure, two users, denial, chaining
  test_query_outcomes_regression.py    # new — the six outcomes, captured before any change
  test_duplicate_checker.py            # rewritten for the new lookup
  test_db.py                           # column + index convergence
README.md
```

### 6.7 Patterns followed

- **Additive column convergence**: `AUDIT_LOGS_ADDED_COLUMNS` plus the matching `CREATE` declaration, per the comment in `app/db/models.py` ("listing a column in only one of them means every new deployment ALTERs its own brand-new table on first boot").
- **Index in the single `init_db()` `_session()` block**: `CREATE INDEX IF NOT EXISTS`, following PRD-008 STORY-003's `idx_chat_sessions_user_updated`. It must follow `_add_missing_columns()`, because an index on a column that does not exist yet fails on a pre-existing database.
- **One log call site, every arm**: PRD-008 STORY-009 threaded `session_id` through all seven `log_query` calls and made `_deny`'s parameter required, so that a forgotten arm fails loudly. `dedup_key` follows the same rule: required on `_deny`, and asserted non-NULL on every row `run_query` writes.

## 7. Tools/Features

### F1 — Characterization baseline
A test module that runs against today's code and passes. It pins: a failed row blocks a retry, another user's row blocks, a denial row blocks, and a blocked row chains the window. It also pins the six-outcome regression (Section 11). Later stories flip the behavioural assertions with comments citing D1/D3. The six-outcome assertions are never flipped.

### F2 — `dedup_key` column and index
A nullable `TEXT` column and a composite index, converged on a fresh database, a pre-PRD database, and a database where a concurrent instance already added the column (the `_is_duplicate_column` path). A steady-state boot issues no `ALTER`, and `test_init_db_issues_no_alter_when_schema_is_current` keeps passing.

### F3 — Conversation-shaped key function
`dedup_key(user_id, turns)` as specified in 6.2. Properties under test:
- deterministic across processes (no `hash()`, no dict ordering)
- single-turn key ≠ multi-turn key with the same final turn
- different `user_id` → different key
- whitespace-sensitive, like today (`"hello world"` ≠ `"hello world "`)
- `ValueError` on empty, a final non-user turn, or any `tool` turn
- unaffected by PII redaction settings (raw text only)

### F4 — Lookup excludes non-verdict rows
`success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL`.

### F5 — Lookup scoped by user
`user_id = ?` plus the key match.

### F6 — Pipeline and audit integration
Compute once, check with it, log it on every arm. `check_duplicate` keeps raising `DuplicateCheckError` on `StorageError`, and the router keeps mapping that to 500.

### F7 — Documentation
README updates listed in Section 4, plus a short "Duplicate detection scope" note under Features/Security. It states what counts, what does not, and the per-account repetition trade-off.

## 8. Technology Stack

No new dependencies. Everything uses what `requirements.txt` already pins.

| Layer | Technology | Use in this PRD |
|---|---|---|
| Runtime | Python 3.11 (`Dockerfile`: `python:3.11`, `python:3.11-slim`) | `typing.Protocol`, `dataclasses` |
| API | FastAPI (existing) | No route or schema change |
| Storage | Turso / libSQL, `libsql==0.1.11` (PRD-007) | New column + composite index; lookup query |
| Hashing | stdlib `hashlib` (SHA-256), `json` | Key derivation, same primitive as `hash_prompt` |
| Chat UI | Reflex `0.9.6.post1` | **Untouched**: `ChatState.send()` calls `run_query(prompt=...)` as before |
| Tests | pytest, `fastapi.testclient`, existing `temp_db` / `uninitialized_db` fixtures | All new tests use existing fixtures |

Skill constraints: `.agents/skills/` contains only `frontend-design`, which covers UI visual design. This PRD changes no UI surface, so no skill rule applies to Sections 6, 8, 9 or 11. See the Appendix.

## 9. Security & Configuration

### 9.1 Authentication & authorization
Unchanged. The key uses `identity.user_id` as resolved from the bearer token by `app/middleware/auth.py`. It never uses the request body's `user_id`, which the router already refuses to let differ. A caller therefore cannot choose whose window they are checked against.

### 9.2 Threat reasoning

| # | Change | Effect on the control | Assessment |
|---|---|---|---|
| T1 | Scope by `user_id` | **Weaker**: N accounts can each send the same prompt once per window. | Accepted. The control's stated purpose ("you already asked this") is per-caller, and a global scope already fails it by blocking legitimate users. Multi-account repetition is an abuse-rate problem, owned by PRD-013 (per-user rate limits and token budgets). Account creation is admin-only (`scripts/manage_users.py`), which bounds N. |
| T2 | Scope by `user_id` | **Stronger**: one user can no longer deny another user a prompt by sending it first (window poisoning). | Today any user who can guess a colleague's next prompt can block it for 24h. This closes that. |
| T3 | Exclude failures | **Weaker**: a caller who can force failures can resend a prompt repeatedly without being held. | Limited. Only an upstream failure or a redactor crash produces `success=0`, and a caller cannot reliably cause either. An upstream failure means no model output, so nothing was obtained twice. Every attempt is still audited. PRD-013 counts failures toward usage. |
| T4 | Exclude policy denials | **Stronger**: a denied request could previously poison the window for the allowed retry. | Denials already audit with `denied_permission`, and nothing is lost. |
| T5 | Exclude duplicate-blocked rows | **Weaker only against persistence**: a prompt resent continually no longer stays blocked forever. It is allowed once per 24h after its last *answered* occurrence. | This is what "24h window" means in the README and the block message. The chaining was accidental (Section 6.4). |
| T6 | Output `PiiRedactorError` excluded | **Weaker**: the model *was* called, but the answer was withheld, so a retry calls it again. | Accepted. The user never received a response. See Risk 4. |
| T7 | Key includes conversation prefix | **Neutral for `/query`** (prefix always empty). For PRD-010, the same last turn in a different context is not a duplicate. | Intended. It is the premise of multi-turn. PRD-010 owns the context-resend behaviour of agents (a resent full history is a *different* prefix only if the history changed). |
| T8 | Pre-PRD rows have NULL `dedup_key` | **Weaker, once, for ≤24h after deploy**: prompts answered in the 24h before deploy can be sent again once. | Accepted by default (D6). Bounded, one-off and documented in the release notes. The alternative is in Risk 3. |

Invariants that must still hold, each asserted by an existing or new test:
- Duplicate check runs **after** authorization and **before** pattern detection and redaction.
- The key is built from **raw** text, and redacted placeholders are never hashed (`test_hash_prompt_only_ever_receives_raw_text`).
- A storage failure during the duplicate lookup returns **500** and does not let the query through (`test_duplicate_check_storage_failure_returns_500`).
- Every attempt, including failures, denials and blocks, still writes exactly one audit row.

### 9.3 Configuration
**No new environment variables.** The 24h window stays a module constant, as today. `.env.example` needs no change, and STORY-009 confirms that explicitly rather than by omission.

### 9.4 Out of scope (security)
Rate limiting, usage budgets and multi-account correlation (PRD-013). Semantic near-duplicates. Changing fail-closed storage behaviour. Protecting `dedup_key` against an actor who already has database read access (it is a SHA-256 of data already sitting beside it in `prompt_hash` and `user_id`).

## 10. API Specification

**No request, response or status-code change.**

| Endpoint | Change |
|---|---|
| `POST /query` | None to the shape. Behaviour changes only as listed in Section 6.3: a retry after failure or denial, and a same-prompt send by a different user, now reach the model where they were blocked before. |
| `GET /audit` | None. `AuditQueryEntry` does not gain `dedup_key` (D5). |
| `GET /stats` | None. `blocked_duplicates` still counts `was_duplicate_blocked = 1`. |

The duplicate block body is unchanged:

```json
{
  "status": "BLOCKED",
  "reason": "Duplicate query within 24 hours",
  "first_query_at": "2026-09-16T09:00:00Z"
}
```

`first_query_at` is now the earliest *qualifying* row for this user and key (success or suspicious-pattern block), not the earliest row with this text.

Internal API (Python, not HTTP):

```python
dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str
check_duplicate(user_id: str, key: str) -> DuplicateCheckResult     # raises DuplicateCheckError
find_duplicate_timestamp(user_id: str, dedup_key: str, since: str) -> Optional[str]
log_query(..., dedup_key: Optional[str] = None) -> int
```

## 11. Success Criteria

### MVP definition
A `/query` retry after an upstream failure reaches the model. The same prompt from two users reaches the model twice. A same-user repeat after a success within 24h is blocked. The six outcomes below are unchanged.

### Functional requirements
- [ ] A retry after `OpenRouterError` (502) is not blocked
- [ ] A retry after an input `PiiRedactorError` (500) is not blocked
- [ ] A retry after a policy denial (model allowlist, BYOK, missing `query:submit`) is not blocked
- [ ] The same prompt from two users is not blocked for either
- [ ] The same prompt from the same user within 24h after a success is blocked, and `first_query_at` equals the success's timestamp
- [ ] The same prompt from the same user within 24h after a suspicious-pattern block is blocked (D1)
- [ ] A prompt whose only in-window matches are duplicate-blocked rows is not blocked (D3)
- [ ] Boundary behaviour at 24h ± 1 minute unchanged
- [ ] Whitespace sensitivity unchanged
- [ ] `dedup_key` is non-NULL on every row `run_query` writes, on all seven arms
- [ ] `prompt_hash` on every new row still equals `hash_prompt(prompt)`
- [ ] `init_db()` converges column and index on a fresh DB, a pre-PRD DB, and under a concurrent-add race, and issues no `ALTER` when current
- [ ] `dedup_key` raises `ValueError` for empty input, a final non-user turn, and any `tool` turn
- [ ] `dedup_key(u, [user(x)])` differs from `dedup_key(u, [user(y), assistant(z), user(x)])`

### The six `/query` outcomes (regression, captured in STORY-001, green at every story)

| # | Outcome | Status | Body `status` / detail | Audit rows |
|---|---|---|---|---|
| 1 | Success | 200 | `SUCCESS` | 1 |
| 2 | Duplicate block | 200 | `BLOCKED`, `reason: "Duplicate query within 24 hours"` | 1 |
| 3 | Suspicious-pattern block | 200 | `BLOCKED`, `reason: "Suspicious pattern detected"` | 1 |
| 4 | Policy refusal | 200 | `BLOCKED`, `required_permission` set | 1 |
| 5 | Upstream failure | 502 | `OpenRouterError` detail | 1 |
| 6 | Internal failure (redactor / duplicate storage) | 500 | error detail | 1 (redactor) / per current test (storage) |

Outcome 2's regression uses a *same-user, after-success* repeat, the case whose result is unchanged. Inputs whose outcome this PRD deliberately changes are covered by the functional requirements above, not by the regression.

### Quality indicators
- [ ] Full test suite green. Following the libSQL dev-server note, mass fixture errors mean restarting the container, not bisecting code
- [ ] No outcome assertion in `test_query_router.py` or `test_integration.py` modified. Only spy signatures adapt (Section 6.5)
- [ ] Every modified pre-existing test carries a comment citing PRD-009 and the decision (D1/D3/D5) that changed it
- [ ] `tests/test_two_instance_smoke.py` passes unmodified
- [ ] No added round trip on `/query`: the lookup stays one query, and the key is computed in-process

## 12. Implementation Phases

### Phase 1 — Pin and prepare (Stories 1–3)
**Goal:** today's behaviour is pinned, and the new column, index and key exist, with nothing reading them yet.
**Deliverables:** threat reasoning committed in this PRD; `test_duplicate_characterization.py` and `test_query_outcomes_regression.py` green on untouched production code; `dedup_key` column + `idx_audit_logs_dedup` converged by `init_db()`; `dedup_key()` with full property tests.
**Validation:** full suite green; `/query` behaviour byte-identical (no production caller changed).

### Phase 2 — Rescope the lookup (Stories 4–5)
**Goal:** the lookup excludes non-verdict rows and is scoped by user. At this point it still matches on `prompt_hash`, so each change ships and is reviewed alone.
**Deliverables:** `find_duplicate_timestamp` gains `success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL` (Story 4), then `user_id = ?` (Story 5). Characterization assertions for D1/D3/failures (Story 4) and cross-user (Story 5) flipped with citations.
**Validation:** six-outcome regression green after each story; retry-after-failure passes after Story 4; two-user passes after Story 5.

### Phase 3 — Switch to the key (Stories 6–7)
**Goal:** the pipeline computes, checks and logs `dedup_key`, and the lookup matches on it.
**Deliverables:** `check_duplicate(user_id, key)`; `log_query(dedup_key=...)` on all seven arms plus the router's documented `None`; lookup on `dedup_key`; contract tests in Section 6.5 updated; `test_duplicate_scope.py` covering every row of the Section 6.3 table end to end through `POST /query`.
**Validation:** non-NULL key on every pipeline-written row; all Section 11 functional requirements green.

### Phase 4 — Regress and document (Stories 8–9)
**Goal:** prove nothing else moved, and tell readers what changed.
**Deliverables:** final six-outcome regression run plus the `/audit`/`/stats`/console invariance check; README updates (Multi-turn blocker resolved, Features row, OpenAI-endpoint question answered, T1/T8 trade-offs, the line-329 correction); `.env.example` confirmed unchanged.
**Validation:** full suite green; README links resolve; `pre-prds/PRE-PRD-009` marked `promoted`.

## 13. Future Considerations

- **PRD-010 (multi-turn pipeline)**: feeds `dedup_key` the real conversation. D5 of PRE-PRD-010 (redacted history sent to the model) does not affect the key, which stays on raw text.
- **PRD-013 (audit & usage limits)**: the mitigation for T1 and T3. Per-user rate limits and budgets, with failures counted.
- **PRD-014 (OpenAI-compatible endpoint)**: maps a duplicate block to an error object. The key is already defined for `messages`.
- **PRD-016 (tool calling)**: lifts the `tool`-role refusal. Pre-PRD-016's proposed default excludes tool turns from the last-turn component and includes them in the prefix, which is a `DEDUP_KEY_VERSION` bump.
- **Legacy-row fallback removal**: nothing to remove under D6's default. If Risk 3's alternative is chosen instead, remove its `prompt_hash` branch in a follow-up after 24h in production.
- **Configurable window, semantic duplicates**: roadmap items, unaffected by this key shape.
- **Exposing `dedup_key` on `/audit`**: possible later for investigators ("which rows would have matched?"), deliberately not now (D5).

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Weakening the central control**: per-user scope lets N accounts repeat a prompt (T1); excluding failures lets a caller who can force errors resend (T3). | Medium / Medium | Stated in the threat reasoning (9.2) and the README, not left implicit. Accounts are admin-provisioned. PRD-013 adds per-user rate and budget limits that count failures. Every attempt stays audited. |
| 2 | **Libsql schema change on a live Turso DB**: the column add or index creation fails or races across instances at boot. | Low / High (container won't boot) | Additive and idempotent, same path as PRD-008 STORY-003: `AUDIT_LOGS_ADDED_COLUMNS` with the `_is_duplicate_column` race tolerance, and `CREATE INDEX IF NOT EXISTS` placed after the column add. Tests cover a fresh DB, a pre-PRD DB, a concurrent add, and a no-`ALTER` steady state. |
| 3 | **Transition gap (T8)**: pre-deploy rows have NULL `dedup_key`, so prompts answered in the last 24h can be resent once after deploy. | Certain / Low | Default (D6): accept and document it in the release notes, since it is bounded to one resend per prompt per user within 24h. *Alternative if unacceptable:* for single-turn input only, add `OR (dedup_key IS NULL AND prompt_hash = ?)` within the same `user_id` scope and flags. The legacy branch is covered by the existing `user_id`-leading index, and a follow-up removes it after 24h. |
| 4 | **An output-redaction failure excluded (T6) doubles model spend on retry**: the model was called, but the row is `success=0`. | Low / Low | Accepted. The user received nothing, and blocking their retry recreates defect #1. Spend is PRD-013's concern. The behaviour is noted in the threat reasoning so it is not "discovered" later. |
| 5 | **Contract-test churn hides a real regression**: updating six pinned tests (6.5) could mask an unintended change. | Medium / High | Characterization and six-outcome tests land first (STORY-001) on untouched code. Each pre-existing test update carries a comment naming its decision. Outcome assertions in `test_query_router.py`/`test_integration.py` are forbidden to change, and only spy wrappers adapt. |
| 6 | **A pipeline arm forgets `dedup_key`**: that row is written with NULL and can never serve as a prior query, silently disabling the control for that path. | Medium / High | `_deny` takes `dedup_key` as a required keyword (PRD-008 STORY-009's pattern). A test drives all seven arms and asserts a non-NULL key on each row. |

## 15. Appendix

### Source
- Pre-PRD brief: [pre-prds/PRE-PRD-009-duplicate-rescoping.md](../../../pre-prds/PRE-PRD-009-duplicate-rescoping.md)
- Track overview and dependency graph: [pre-prds/README.md](../../../pre-prds/README.md). This PRD blocks PRD-010.

### Decisions (resolved from the brief's open decisions)

| # | Question | Decision |
|---|---|---|
| D1 | Is a policy denial a prior query? | **No.** Only rows that reached the model or were blocked by a content check (suspicious pattern) count. |
| D2 | Scope: `user_id` or `user_id + session_id`? | **`user_id` + conversation prefix hash.** External clients have no session id. |
| D3 | Does a duplicate-blocked row extend the window? | **No.** *Correction to the brief:* today it **does** (Section 6.4), so this is a behaviour change, pinned first and then flipped. |
| D4 | Are `tool` turns part of the key? | **Not in this PRD.** `dedup_key` raises `ValueError` on them, so PRD-016 has to decide rather than inherit a default. |
| D5 | Recompute `prompt_hash` or add a column? | **New `dedup_key` column.** `prompt_hash`, `/audit` and `/stats` are untouched. |
| D6 | *(new)* Backfill or fallback for pre-deploy rows? | **Neither by default.** Accept a one-off gap of up to 24h (T8, Risk 3), with the fallback documented as the alternative. |

### Evidence (verified against `main` @ `57f2d67`)
- `app/db/database.py:758-769`: `find_duplicate_timestamp(prompt_hash, since)`, `WHERE prompt_hash = ? AND timestamp >= ?`, no `user_id`, no `success`, no flag predicates.
- `app/services/audit_logger.py:34`: `prompt_hash=hash_prompt(prompt)` on every call.
- `app/services/query_pipeline.py`: seven `log_query` call sites. `success=False` on input `PiiRedactorError`, `OpenRouterError` and output `PiiRedactorError`. `success=True` with `denied_permission` on three `_deny` arms.
- `app/routers/query.py`: foreign-session refusal logs `success=False`; `DuplicateCheckError` → 500.
- `tests/test_pii_dedup_isolation.py:223, 304, 343`: contract tests on `check_duplicate` signature and `hash_prompt` call sites.
- `README.md:641-643`: "Rescoping that hash … deserves its own threat reasoning and its own tests rather than arriving as a side effect".

### Observed discrepancy (fixed in documentation only)
`README.md:329` says a duplicate-check storage failure "lets the query through rather than rejecting it". The code (`app/routers/query.py`, `DuplicateCheckError` → `HTTPException(500)`) and `tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500` both say it returns 500. This PRD keeps the tested behaviour and corrects the sentence. Making the check fail open would be a separate security decision.

### Tentative story breakdown (for `/create-stories`)
1. Threat reasoning + characterization tests of current duplicate behaviour + six-outcome baseline
2. `dedup_key` column and `idx_audit_logs_dedup`, converged by `init_db()`
3. `dedup_key()` over a conversation (single-turn as the special case)
4. Lookup excludes failed, denied and duplicate-blocked rows
5. Lookup scoped by `user_id`
6. `check_duplicate` and pipeline use the key; `log_query` writes it on all seven arms; contract tests updated
7. Two-user, retry-after-failure and denial end-to-end tests through `POST /query`
8. Six-outcome regression and `/audit`/`/stats` invariance
9. README and `.env` documentation

### Related documents
- PRD-003 (PII redaction): raw-text hashing invariant
- PRD-005 (RBAC): `denied_permission`, `_deny`
- PRD-007 (Turso migration): libSQL client, `init_db()` reachability guard
- PRD-008 (chat sessions): `AUDIT_LOGS_ADDED_COLUMNS` convergence, index-in-`init_db()` pattern, seven-arm threading (STORY-003, STORY-009)

### Dependencies
- Depends on: none
- Blocks: PRD-010

**Skills referenced:** none applicable. `.agents/skills/` was scanned; its only skill, `frontend-design`, covers UI visual design, and this PRD changes no UI surface.
