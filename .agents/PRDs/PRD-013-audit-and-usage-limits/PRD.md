---
id: PRD-013
slug: audit-and-usage-limits
title: Audit for Conversations and Usage Limits — What Was Attempted, Through Which Door, at What Cost, Within a Bound
status: draft
base_branch: main
epic_branch: epic/PRD-013-audit-and-usage-limits
created: 2026-10-04
updated: 2026-10-20
---

## 1. Executive Summary

The audit row was shaped for one prompt and one response, and the harness has no limit on what a valid token can spend. Both stop being acceptable the moment a coding agent is pointed at it.

**The audit row cannot describe multi-turn traffic.** [app/services/audit_logger.py](../../../app/services/audit_logger.py) writes a `prompt_hash`, two 500-character previews and one `tokens_used` total. PRD-010 already made `prompt` the last user turn, so the preview is no longer the system prompt, but the row still does not say which ingress the request came through, how many messages it carried, how the tokens split between input and output, or whether it was streamed or carried tool calls. `session_id` is a harness-minted UUID4 (PRD-008) that only the chat UI has; a `/v1` client (PRD-014) has no session, so nothing groups an agent's fifty turns into one conversation.

**There are no usage limits.** No rate limit and no token budget exists per user or per role. The harness holds the only OpenRouter key, so any valid user token can spend it without bound, and an agent in a retry loop will. PRD-009 accepted two weakenings on the promise that this PRD would cover them: N accounts repeating a prompt (T1) and a caller resending after forced failures (T3).

**The break-glass token is a sharp edge.** `resolve()` ([app/services/identity.py](../../../app/services/identity.py)) maps `ADMIN_TOKEN` to a synthetic admin that bypasses the model allowlist (`MODEL_ALLOWLIST_WILDCARD_ROLES` in [app/services/authz.py](../../../app/services/authz.py)). It is the one credential every operator has to hand, so it is the one that will be pasted into an agent's config.

This PRD adds eight additive audit columns and writes them on every arm of `run_conversation`. It adds a derived `conversation_key` so an external client's turns group without a session. It adds a per-user daily token budget and a per-user request rate limit, both with role defaults and per-user overrides, held in one Turso counter table so they hold across instances. A refusal is a new audited `BLOCKED` outcome, never a `429`. `ADMIN_TOKEN` is refused on any ingress outside an allowed set that can never include `/v1`. `/audit`, `/stats` and the admin console show the new fields, and the console gains one usage table. As with PRD-011 and PRD-012, `/v1` does not exist yet: `ingress="v1"` is reachable through `run_conversation(ingress="v1")` and tested there.

**MVP goal:** a 50-turn conversation produces 50 rows sharing one `conversation_key`, each previewing its own user turn. A user over budget is refused with an audited row while another user is unaffected, and the same holds when the two requests land on two instances. `ADMIN_TOKEN` is refused under `ingress="v1"`. The admin console shows usage per user, and the existing `/query`, chat and console regression suites pass with no assertion changed.

## 2. Mission

Make every row answer "what was attempted, by whom, through which door, at what cost" for multi-turn traffic, give every user a bounded spend, and keep the break-glass credential break-glass.

Core principles:

- **Additive only.** Every new column is nullable or defaulted, converged by `init_db()`, and never backfilled. Every existing field of `/audit` and `/stats` keeps its meaning.
- **A limit is a verdict, and it is audited.** A budget or rate refusal writes one row that names the limit, like every other block (PRD-001's founding property). It is never a silent drop and never a `429`.
- **Count attempts, charge spend.** The rate limit counts every authorized attempt, including the ones later blocked or failed. The budget charges tokens the provider actually reported, including the ones whose response was then lost to an output-redaction failure.
- **One clock, one counter.** Windows are computed by the database, not by the instance, and each check is one atomic statement. Two instances cannot disagree about the minute or double-admit a request.
- **Fail closed on the gate, never on the receipt.** If the counter cannot be read, the request does not reach the model. If the charge cannot be written after the model answered, the user still gets the answer, and the audit row is the record to reconcile from.
- **The server names the ingress.** `ingress` is a call-site argument, like `profile` (PRD-011 Section 6.6). No request field can set it.
- **Break-glass tightens, never loosens.** The setting that governs `ADMIN_TOKEN` can remove ingresses from the allowed set. It cannot add `/v1`.

## 3. Target Users

**Security/Compliance Admin.** Reads the audit to reconstruct what happened. They need a row that says which door a request came through, how big the conversation was and what it cost, and they need an agent's turns to be visibly one conversation. They also need a refusal for spend to be evidence, not an absence.

**Platform Operator.** Owns `.env` and the OpenRouter bill. They need a default bound on every user from the first boot, a way to raise it for one user without a deploy, and a mis-set value to stop the boot with a message naming it. They need the limit to hold when a second instance is added (PRD-007).

**Integrating Developer (coding agent).** Will point an agent at `/v1` once PRD-014 lands. When their agent loops, they need a refusal that says which limit was hit, what the maximum is and when it resets, in a shape their client shows them instead of retrying.

**End User (Employee).** Chats in the Reflex UI. They should never notice the rate limit in ordinary use. If they reach the budget, they need to be told what happened and when they can continue.

**Admin holding the break-glass token.** Uses `ADMIN_TOKEN` to sign in to the console and recover a deployment. They need that to keep working, and they need the harness to refuse the token in the one place it would be left lying around.

**PRD-014 / PRD-016 implementers** (internal). PRD-014 passes `ingress="v1"` and `streamed=True` and maps the usage-limit result to an OpenAI error object. PRD-016 sets `has_tool_calls`. Both need the columns to exist and the pipeline arguments to be in place.

## 4. MVP Scope

### In Scope

**Baseline**
- [ ] Characterization tests of today's audit row on every arm of `run_conversation`, and of how `call_openrouter` reads `usage`, green on untouched code

**Audit columns (`app/db/models.py`, `app/db/database.py`)**
- [ ] `audit_logs`: `ingress TEXT`, `message_count INTEGER`, `input_tokens INTEGER`, `output_tokens INTEGER`, `streamed INTEGER NOT NULL DEFAULT 0`, `has_tool_calls INTEGER NOT NULL DEFAULT 0`, `conversation_key TEXT`, `limit_exceeded TEXT`
- [ ] Each declared in `CREATE_AUDIT_LOGS_TABLE` and in `AUDIT_LOGS_ADDED_COLUMNS`; written by `insert_audit_log`; mapped by `_row_to_audit_log` on both read shapes, including the `json_object(...)` in `_SUMMARY_SQL`
- [ ] No backfill

**OpenRouter client (`app/services/openrouter_client.py`)**
- [ ] `OpenRouterResult` gains `input_tokens: Optional[int]` and `output_tokens: Optional[int]`, read from `usage.prompt_tokens` and `usage.completion_tokens`
- [ ] `tokens_used` (from `usage.total_tokens`) unchanged and still required; a response without the split leaves both new fields `None`

**Conversation key (`app/services/conversation_key.py`, new)**
- [ ] `conversation_key(user_id, messages) -> str`: a versioned hash of the user id, the first `system` message and the first `user` message, over raw text
- [ ] Computed once in `run_conversation`, beside `dedup_key`, and written on every row

**Pipeline (`app/services/query_pipeline.py`)**
- [ ] `run_conversation(..., *, profile=None, ingress=None, streamed=False)`; `run_query(..., ingress="query")`
- [ ] Every `log_query` call passes `ingress`, `message_count`, `conversation_key` and `streamed` explicitly; the upstream arms also pass `input_tokens` and `output_tokens`
- [ ] Break-glass ingress refusal, as a fourth authorization arm
- [ ] Usage gate after authorization: rate, then budget, as a new audited `BLOCKED` outcome
- [ ] Charge after the upstream call returns, before output redaction

**Usage limits (`app/services/usage_limits.py`, new)**
- [ ] `usage_daily` table: one row per user per UTC day, holding the day's request and token counts and the current one-minute window
- [ ] `admit(identity) -> Admission`: one atomic statement that counts the attempt and returns the window count and the day's tokens
- [ ] `charge(user_id, day, input_tokens, output_tokens)`: one statement
- [ ] Limit resolution: per-user override, else the role's entry, else `*`
- [ ] `UsageLimitError` on a storage failure in `admit`, mapped to `500` like `DuplicateCheckError`

**Settings (`app/config.py`)**
- [ ] `USAGE_LIMITS_ENABLED`, `USAGE_DAILY_TOKEN_BUDGET`, `USAGE_REQUESTS_PER_MINUTE`, `BREAK_GLASS_INGRESSES`, with startup validators

**Identity and users**
- [ ] `users.token_budget_daily INTEGER` and `users.requests_per_minute INTEGER`, nullable, through a new `USERS_ADDED_COLUMNS` convergence
- [ ] `Identity` gains `break_glass: bool = False`, `token_budget_daily: Optional[int] = None`, `requests_per_minute: Optional[int] = None`, set only by `resolve()`
- [ ] `scripts/manage_users.py set-limits --user-id … [--token-budget N|default] [--requests-per-minute N|default]`; `list-users` shows both

**API (`app/models/schemas.py`, `app/routers/`)**
- [ ] `QueryBlockedUsageLimitResponse` in the `QueryResponse` union; `/query` returns it as `200`
- [ ] `AuditQueryEntry` gains the eight fields
- [ ] `StatsResponse` gains `input_tokens`, `output_tokens`, `blocked_usage_limits`

**Chat UI and admin console (`chat_ui/`)**
- [ ] A `usage_limit` bubble, persisted and restored like the other refusal bubbles
- [ ] Register: tokens shown as input / output; ingress, message count, conversation key, streamed, tool calls and limit on disclosure; search matches `conversation_key` and `ingress`; a usage-limit row reads **denied**
- [ ] Summary: token totals and the usage-limit count
- [ ] Usage: one table, one row per user active today

**Proof and docs**
- [ ] Two-instance test: a budget and a rate limit both hold when requests alternate between two processes
- [ ] Latency of the gate and the charge measured and recorded
- [ ] Eight-outcome `/query` regression (seven existing rows unchanged, plus usage limit); chat and console regression
- [ ] README and `.env.example`

### Out of Scope

- [ ] Billing, invoices, cost in currency. Tokens only
- [ ] Distributed rate limiting beyond what Turso provides (no Redis, no in-memory token bucket)
- [ ] An HTTP ingress that passes `ingress="v1"` or `streamed=True` (PRD-014), and anything that sets `has_tool_calls` (PRD-016). The columns and arguments ship here; their producers do not
- [ ] Mapping the usage-limit result to an OpenAI error object and status code (PRD-014 D2)
- [ ] A `GET /usage` endpoint and the RBAC permissions it would need. The refusal body carries the maximum, the usage and the reset time
- [ ] Charts, trends or history in the usage view. One table, today only
- [ ] Per-user concurrency caps on the pipeline executor (PRD-010 T6) and budgeting `max_tokens` before the call (PRD-010 T5)
- [ ] Per-role PII telemetry, the skip-and-flag record (PRD-012 Section 13), per-pattern metrics and a table for more than one flag per request (PRD-011 Section 13). Earlier PRDs pointed these here. The brief did not carry them, and they are deferred again in Section 13
- [ ] A `conversation_key` filter on `GET /audit`, and an index for it
- [ ] Retention or expiry of `usage_daily` rows
- [ ] Changing `dedup_key`, `prompt_hash`, the previews, or `tokens_used`
- [ ] Changing how the admin console itself authenticates. It keeps comparing against `ADMIN_TOKEN`

## 5. User Stories

1. **As a compliance admin, I want an agent's turns grouped into one conversation, so that I read fifty rows as one piece of work.**
   *Example:* an agent sends 50 requests that all start with the same system prompt and the same first instruction. All 50 rows carry the same `conversation_key`. Pasting that key into the Register's search shows those rows, each with its own user turn's hash.

2. **As a compliance admin, I want each row to say which door the request came through and what it cost, so that I can tell a chat message from an agent step.**
   *Example:* a row reads `ingress = chat`, `message_count = 7`, `input_tokens = 2,140`, `output_tokens = 312`. A `/query` row reads `ingress = query`, `message_count = 1`.

3. **As a platform operator, I want every user bounded by default, so that one looping agent cannot spend the whole key.**
   *Example:* with `USAGE_DAILY_TOKEN_BUDGET=*=1000000`, a user who has used 1,000,000 tokens today is refused until 00:00 UTC. The row carries `limit_exceeded = tokens`.

4. **As a platform operator, I want to raise one user's limit without a deploy, so that a heavy user is not a config change for everyone.**
   *Example:* `python scripts/manage_users.py set-limits --user-id dana --token-budget 5000000` takes effect on Dana's next request.

5. **As an integrating developer, I want a refusal that names the limit and the reset time, so that I know whether to wait a minute or until tomorrow.**
   *Example:* `{"status": "BLOCKED", "reason": "Usage limit reached", "limit": "requests", "maximum": 60, "actual": 61, "resets_at": "2026-10-04T14:23:00Z"}`.

6. **As a compliance admin, I want limits to hold across instances, so that adding a container is not a way to double a budget.**
   *Example:* two processes share one database. A user with a limit of 5 requests a minute sends 10, alternating between them. Exactly 5 are admitted.

7. **As a security admin, I want the break-glass token refused where agents connect, so that pasting it into an agent's config does not work.**
   *Example:* `run_conversation(identity_from_ADMIN_TOKEN, …, ingress="v1")` returns a policy refusal with `required_permission = "ingress:break_glass"` and writes one row.

8. **As an end user, I want to be told plainly when I have reached today's limit, so that I do not keep retrying.**
   *Example:* the chat shows "You've reached today's usage limit. You can send again after 00:00 UTC." The bubble is still there after a reload.

## 6. Core Architecture & Patterns

### 6.1 Where the new steps sit

The check order from PRD-010 Section 6.1, PRD-011 Section 6.1 and PRD-012 Section 6.1 is unchanged. Existing step numbers are kept, because three PRDs and the code comments cite them. The new steps take letters:

```
0.  structural validation (no audit row)
1.  dedup_key over the raw conversation
1b. conversation_key over the raw conversation            <-- new, pure
2.  authorize / model / BYOK                              → forbidden (row)
2b. break-glass ingress policy                            → forbidden (row)      <-- new
2c. USAGE GATE: admit(identity)                           → usage_limit (row)    <-- new
      rate first, then budget; one statement, one round trip
3.  context limits
4.  duplicate
5.  patterns
6.  redact input
7.  upstream
7b. CHARGE: charge(user_id, day, input, output)                                  <-- new
8.  redact output; audit; return
```

**Why the gate is at 2c.** It sits after every authorization arm, so a caller without `query:submit` learns nothing about limits and does not consume anyone's window. It sits before context limits, the duplicate check and patterns, so that every authorized attempt counts toward the rate, including the ones those steps then refuse. That is what bounds a looping agent, whose retries are mostly duplicates, and it is what closes PRD-009 T1 and T3: a repeat from a second account and a resend after a forced failure are both attempts.

**Why the charge is at 7b.** It runs as soon as the provider has reported usage, before step 8's output redaction. So the output-redaction error arm cannot forget it, and tokens spent on a response the user never received are still charged (PRD-009 Risk 4: "Spend is PRD-013's concern").

**One limit is reported.** The rate is checked first and the budget only if the rate passed, the same rule as `_context_limit_exceeded`.

### 6.2 New audit columns

| Column | Type | Written | Meaning |
|---|---|---|---|
| `ingress` | `TEXT` | Every row | `query`, `chat` or `v1`. `NULL` on rows before this PRD and on a direct call that passed none |
| `message_count` | `INTEGER` | Every row | `len(messages)` as received, before redaction. `NULL` before this PRD |
| `input_tokens` | `INTEGER` | Upstream arms | `usage.prompt_tokens`. `NULL` when no upstream call was made or the provider omitted the split |
| `output_tokens` | `INTEGER` | Upstream arms | `usage.completion_tokens`. Same rule |
| `streamed` | `INTEGER NOT NULL DEFAULT 0` | Every row | The response was delivered as SSE. Always `0` until PRD-014 |
| `has_tool_calls` | `INTEGER NOT NULL DEFAULT 0` | Every row | The request or response carried tool calls. Always `0` until PRD-016 |
| `conversation_key` | `TEXT` | Every row | Section 6.3. `NULL` before this PRD |
| `limit_exceeded` | `TEXT` | Usage-limit arm | `requests` or `tokens`. `NULL` on every other row |

`streamed` and `has_tool_calls` are `NOT NULL DEFAULT 0` because `0` is true of every row written before them: neither was possible. The other six are nullable with no default and no backfill, the PRD-009 choice for `dedup_key`.

`limit_exceeded` is not in the brief's list. It is added because the brief requires refusals to be "audited like any block", and the pipeline's own rule (the comment at step 3 of `run_conversation`) is that a verdict row is `success=True` only when the row names the verdict in a dedicated column. Without one, a refusal would be a `success=False` row with a string in `error_message`, which the console would file as a **fault**.

**`tokens_used` is unchanged.** It stays `usage.total_tokens`, which the success response, the chat footer and the Register already read.

### 6.3 Conversation key (Decision D2)

```python
# app/services/conversation_key.py
CONVERSATION_KEY_VERSION = "c1"

def conversation_key(user_id: str, messages: Sequence[Message]) -> str:
    first_system = next((m.content for m in messages if m.role == "system"), "")
    first_user = next(m.content for m in messages if m.role == "user")
    return _sha256_json([CONVERSATION_KEY_VERSION, user_id, first_system, first_user])
```

- **Over raw text.** No redacted string is ever hashed (the PRD-003 invariant, extended in PRD-010 Section 9.2).
- **Stable across an agent's turns.** A `/v1` client resends its history on every request, so the first `system` and first `user` message are the same on turn 1 and turn 50.
- **A grouping aid, not an identity.** Two conversations by the same user that begin with the same system prompt and the same first instruction share a key. Every identical `/query` prompt by one user shares a key. A client that compacts its context and rewrites its first user message starts a new key. All three are documented.
- **The chat UI's key can change mid-session.** `chat_history.fit` drops the oldest whole exchanges, and once the first exchange is dropped the first user message is a different one. For chat rows `session_id` is the authoritative grouping, and the README says so.
- **Unlike `dedup_key`, it is exposed** on `/audit` and in the console. It is a hash of data the same reader can already see as `user_id` and the previews.

### 6.4 What "the prompt" means on a multi-turn row (correction to the brief)

The brief says the first 500 characters of a conversation are usually the system prompt. That was true before PRD-010 and is not true on `main`: `run_conversation` sets `prompt = messages[-1].content`, so `prompt_hash` and `prompt_preview` already describe the last user turn. The brief's second half, "hash of the full conversation", is also already on the row: `dedup_key` is a hash over the user id and every message of the raw conversation.

So this PRD adds no preview code and no new hash column. It pins both facts with tests so they cannot regress: on a 50-turn conversation, each row's `prompt_hash` is the hash of that row's own last user turn, and each row's `dedup_key` differs.

### 6.5 Usage counters (Decisions D1, D3)

One table, one row per user per UTC day:

```sql
CREATE TABLE IF NOT EXISTS usage_daily (
    user_id TEXT NOT NULL,
    day TEXT NOT NULL,                       -- 'YYYY-MM-DD', UTC, from the database clock
    requests INTEGER NOT NULL DEFAULT 0,     -- authorized attempts today
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    unsplit_tokens INTEGER NOT NULL DEFAULT 0,   -- total_tokens of calls with no split reported
    window_start INTEGER NOT NULL,           -- unix minute of the current rate window
    window_requests INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
)
```

**The gate is one statement.** `admit()` counts the attempt and reads back everything both checks need:

```sql
INSERT INTO usage_daily (user_id, day, requests, window_start, window_requests)
VALUES (?, date('now'), 1, strftime('%s','now') / 60, 1)
ON CONFLICT(user_id, day) DO UPDATE SET
    requests = requests + 1,
    window_requests = CASE WHEN window_start = excluded.window_start
                           THEN window_requests + 1 ELSE 1 END,
    window_start = excluded.window_start
RETURNING day, window_start, window_requests,
          input_tokens + output_tokens + unsplit_tokens AS tokens_today
```

- **Atomic.** The increment and the read are one statement on the server. Two instances that admit the same user at the same moment get two different `window_requests` values, so exactly one of them can be the one over the limit.
- **One clock.** `date('now')` and `strftime('%s','now')` are the database's. Instance clock skew cannot split a window.
- **One round trip.** The driver has no client batch (PRD-007 STORY-001 §2.6, quoted above `_SUMMARY_SQL`), so a single statement is the only way to keep the gate to one. Putting the rate window on the day's row is what makes that possible.
- **No cleanup.** The rate window is overwritten in place. Day rows accumulate at one per active user per day, and they are what the usage view reads.

Then, in Python:

```python
if admission.window_requests > limits.requests_per_minute:        → limit "requests"
elif charges_budget and admission.tokens_today >= limits.token_budget_daily:  → limit "tokens"
```

**To verify in the storage story, not assumed:** that `libsql==0.1.11` returns rows from `INSERT … ON CONFLICT … DO UPDATE … RETURNING`. `RETURNING` was not among the six driver behaviours PRD-007 STORY-001 verified. If it does not, the fallback is the same upsert followed by a `SELECT` inside one `_session()` transaction: two round trips, still atomic, and the latency story measures that instead.

**The charge is one statement:**

```sql
UPDATE usage_daily
   SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?,
       unsplit_tokens = unsplit_tokens + ?
 WHERE user_id = ? AND day = ?
```

`day` is the one `admit()` returned, so a request that straddles midnight is charged to the day it was admitted.

**Known properties, stated rather than discovered later:**

- **The budget can be overshot.** It is check-then-charge. A request admitted at 999,999 of 1,000,000 tokens runs, and so does every request already in flight. The overshoot is bounded by the user's rate limit times one response. Reserving `max_tokens` before the call would close it and is a Future Consideration.
- **The rate window is fixed, not sliding.** A user can send the limit at the end of one minute and again at the start of the next. The row also resets at 00:00 UTC, so one extra window opens once a day. Both are at most 2× for one minute.
- **A refused attempt still counts.** The increment and the check are one statement. Because the window is fixed, this does not extend a lockout: the count resets when the minute does.
- **BYOK is rate-limited but not budget-charged (Decision D8).** When `openrouter_api_key` is supplied, the spend is the caller's own key, not the harness's. The attempt counts toward the rate, the budget check is skipped, and no tokens are charged. The audit row records the tokens either way.

### 6.6 Limit resolution (Decision D1)

```python
@dataclass(frozen=True)
class UsageLimits:
    token_budget_daily: Optional[int]     # None = unlimited
    requests_per_minute: Optional[int]    # None = unlimited

def limits_for(identity: Identity) -> UsageLimits: ...
```

Order, for each of the two limits independently: the identity's per-user override if set, else the role's entry in the setting, else the `*` entry.

- **Role defaults are settings**, in a `role=value` map with a required `*` entry: `USAGE_DAILY_TOKEN_BUDGET="*=1000000"`, `USAGE_REQUESTS_PER_MINUTE="*=60,admin=120"`. A value is an integer `≥ 1` or the word `unlimited`. Role names are not validated against the RBAC matrix, because `RBAC_ROLES_FILE` can define any role name and is loaded later. An unknown role simply gets `*`.
- **Per-user overrides are two nullable columns on `users`.** `NULL` means "use the role's". `resolve()` already reads the user's row on every request, so carrying the two values on `Identity` costs no extra round trip. The chat UI re-resolves the identity on every send (PRD-005 Risk 5), so a change made with `set-limits` applies to the next send.
- **The break-glass identity has no `users` row**, so it gets the `admin` role's limits. It is not exempt.
- **`RBAC_ENABLED=false` does not turn limits off.** They have their own switch, `USAGE_LIMITS_ENABLED`. With it `false`, `admit()` and `charge()` are not called, no counter row is written, and the pipeline makes exactly the round trips it makes today.

### 6.7 The refusal

```python
class QueryBlockedUsageLimitResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str                              # "Usage limit reached"
    limit: Literal["requests", "tokens"]
    maximum: int
    actual: int                              # window count, or tokens used today
    resets_at: str                           # UTC, the audit timestamp format
```

- **Audited** with `success=True`, `limit_exceeded` set, `role`, the non-NULL `dedup_key`, and `error_message=None`. No `prompt` is withheld: the row has the same hash and preview as any other.
- **Never a prior query.** `find_duplicate_timestamp` gains one predicate, `AND limit_exceeded IS NULL`, beside the three it already has. Without it, a prompt refused for budget today would be held as a duplicate when the user sends it again tomorrow. `NULL` passes, so every row written before this PRD behaves as before.
- **Never `429` (Decision D5).** On `/query` it is `200` with the `BLOCKED` body, like the other four blocks. The brief's "403" is the `/v1` mapping, and PRD-014 D2 owns it. The result distinguishes `requests` from `tokens` and carries `resets_at`, so PRD-014 can choose per limit.
- **`resets_at`** is the end of the current minute for `requests` and the next 00:00 UTC for `tokens`, both derived from the `window_start` and `day` the gate returned.

### 6.8 Break-glass ingress policy (Decision D4)

```python
Ingress = Literal["query", "chat", "v1"]
```

`resolve()` sets `Identity.break_glass = True` only on the `ADMIN_TOKEN` path. At step 2b:

```python
if identity.break_glass and ingress not in settings.break_glass_ingresses:
    → _deny(..., exc=PermissionDenied("ingress:break_glass"),
            reason="Break-glass credential not permitted on this ingress")
```

- **Default `BREAK_GLASS_INGRESSES="query,chat"`**, which is today's behaviour on both existing ingresses. The validator accepts any subset of `query` and `chat`, including empty, and **rejects `v1`** with a message saying the token is never accepted there. The setting can tighten and cannot loosen.
- **Fails closed.** `ingress=None` (a direct call that named no ingress) is not in any allowed set, so a break-glass identity is refused. Tests that build `Identity("admin", "admin")` directly have `break_glass=False` and are unaffected.
- **It reuses the forbidden arm.** One row, `success=True`, `denied_permission="ingress:break_glass"`, and the existing `QueryBlockedForbiddenResponse`. No new response class, and the chat UI's forbidden bubble already renders it.
- **The admin console is not an ingress.** `AdminState.authenticate` compares against `ADMIN_TOKEN` directly and never reaches the pipeline. It is unchanged.
- **Not changed here:** an admin *user* token still bypasses the model allowlist. That is PRD-005's design and D4's stated alternative ("admins use a normal user token with the `admin` role"). It is now bounded by that user's budget.

### 6.9 `ingress` on every row

`run_conversation` takes `ingress` and `streamed` as keyword-only arguments and passes them to every `log_query` call. `_deny` takes `ingress`, `message_count` and `conversation_key` as required parameters, for the reason it already requires `session_id`, `dedup_key` and `profile`: a forgotten arm must be a `TypeError`, not a `NULL`.

| Call site | Passes |
|---|---|
| `POST /query` → `run_query` | `ingress="query"` (the adapter's default) |
| `/query`'s foreign-session refusal (writes before `run_query`) | `ingress="query"`, `message_count=1`. It knows both. `conversation_key` stays `NULL`, like `dedup_key` and `profile` there |
| `ChatState._do_send` → `run_conversation` | `ingress="chat"` |
| `ChatState._do_send` → `run_query` (history off, first send) | `ingress="chat"` |
| PRD-014 | `ingress="v1"`, `streamed=<request's stream flag>` |

A test scans the production call sites of `run_conversation` and `run_query` and fails if one passes no `ingress` (the PRD-012 STORY-011 scanning pattern). The argument defaults to `None` rather than being required because several hundred test call sites call the pipeline directly, and `NULL` is the honest record for them.

### 6.10 Surfaces

**`GET /audit`.** `AuditQueryEntry` gains `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key`, `limit_exceeded`, all optional or defaulted and unvalidated (the `session_id` reasoning).

**`GET /stats`.** `StatsResponse` gains `input_tokens: int = 0`, `output_tokens: int = 0` (sums over all rows, `NULL` as 0) and `blocked_usage_limits: int = 0`. `_SUMMARY_SQL` grows from ten named columns to thirteen, and `SUMMARY_FIGURES`, `_SUMMARY_DECODERS`, `_summary_figure_by_figure` and the console's `_READS` grow with it, one label per figure (PRD-007 Risk 6).

**Admin console · Register.** The tokens cell reads `2,140 / 312` when the split exists and the total otherwise. The disclosure gains ingress, messages, conversation key, streamed, tool calls and limit. The search needle matches `conversation_key` and `ingress`, so pasting a key shows a conversation. `derive_verdict` gains one line: `limit_exceeded` → **denied**, placed after `was_duplicate_blocked` and before the `success` check. `AuditRow` stays a projection with no preview field.

**Admin console · Usage.** One table, read by one statement over `usage_daily` for the database's current UTC day, joined to `users` for the role and overrides and to a count of today's `limit_exceeded` rows:

| User | Role | Requests | Input | Output | Budget | Used | Refused |
|---|---|---|---|---|---|---|---|

Every figure is scoped in the table's caption ("Today, UTC"), the PRD-006 Risk 4 rule that a figure states its window. No chart, no history, no controls beyond the console's existing refresh.

**Chat UI.** A `usage_limit` bubble kind, added to `ChatMessage`, `_append_and_persist`, the `rx.match` in `components/bubbles.py`, and the stored-message mappers. `chat_history.assemble` reads only `assistant` rows, so the bubble never enters history (PRD-010 D4).

**Skill constraints (`frontend-design`).** The bubble and the usage table follow the existing bubble system and console register (`chat_ui/chat_ui/theme.py`, `components/register.py`), not a new visual direction. The skill's rule *"Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it."* is why the usage view is a plain table with a stated window and no meters or accent colours. Its writing rules apply to the copy verbatim: *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."* and *"Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it … Errors don't apologize, and they are never vague about what happened."* So the bubble says "You've reached today's usage limit. You can send again after 00:00 UTC." and "You're sending too fast. Wait a minute, then send again." It does not say "rate limit exceeded", and it does not apologize. An empty usage table says "No one has sent anything today."

### 6.11 Directory structure (files touched)

```
app/
├── config.py                         # + 4 settings, validators, parsed-map properties
├── models/schemas.py                 # QueryBlockedUsageLimitResponse; AuditQueryEntry + 8; StatsResponse + 3
├── routers/
│   ├── query.py                      # UsageLimitError → 500; foreign-session row gets ingress, message_count
│   └── admin.py                      # /audit projects new fields; /stats reports new figures
├── db/
│   ├── models.py                     # + 8 audit columns; usage_daily; USERS_ADDED_COLUMNS; User + 2
│   └── database.py                   # writer, mapper, _SUMMARY_SQL; admit/charge/usage_snapshot;
│                                     #   set_user_limits; duplicate lookup predicate
└── services/
    ├── conversation_key.py           # NEW
    ├── usage_limits.py               # NEW: UsageLimits, limits_for, admit, charge, UsageLimitError
    ├── identity.py                   # Identity + break_glass, + 2 overrides
    ├── openrouter_client.py          # OpenRouterResult + input_tokens, output_tokens
    ├── audit_logger.py               # log_query + 8 fields
    └── query_pipeline.py             # steps 1b, 2b, 2c, 7b; ingress/streamed arguments; every arm
chat_ui/chat_ui/
├── state.py                          # ingress="chat"; usage_limit branch; UsageLimitError branch
├── models.py / copy.py               # usage_limit kind and copy
├── components/bubbles.py             # usage_limit bubble
├── admin_models.py / admin_formatting.py / admin_copy.py   # AuditRow + fields; verdict line; UsageRow
├── admin_state.py                    # _READS + 3; usage rows; search needle
└── components/register.py, summary.py, usage.py (NEW), admin_shell.py
scripts/
├── manage_users.py                   # + set-limits; list-users shows limits
└── measure_usage_latency.py          # NEW, beside measure_history_latency.py
tests/
├── test_audit_characterization.py    # NEW: today's row per arm, before anything moves
├── test_conversation_key.py          # NEW
├── test_usage_limits.py              # NEW
├── test_query_pipeline_audit_fields.py     # NEW: 8 fields on every arm; call-site scan
├── test_query_pipeline_usage_limits.py     # NEW: gate, charge, BYOK, order, dedup exclusion
├── test_query_pipeline_break_glass.py      # NEW
├── test_usage_bubble.py / test_usage_view.py   # NEW
├── test_two_instance_smoke.py        # + limits across two processes
└── test_query_outcomes_regression.py # + row 8
```

### 6.12 Patterns followed

- **Characterization first** (PRD-009 STORY-001, PRD-011 STORY-001, PRD-012 STORY-002).
- **Additive column convergence**: one entry in the `CREATE` and one in the added-columns mapping, per the comment in [app/db/models.py](../../../app/db/models.py). `USERS_ADDED_COLUMNS` is the third mapping, run through the same `_add_missing_columns`.
- **Required keyword on every audit arm** (PRD-008 STORY-009, PRD-009 Risk 6).
- **Server-selected call-site argument, no request field** (PRD-011 Section 6.6).
- **One statement per read** where the driver has no batch (PRD-007 Section 6 Pattern 3).
- **Settings validated at startup with instructive errors**, in the `CHAT_SESSION_LIMIT` style in [app/config.py](../../../app/config.py).
- **Settings read per call in the pipeline**, so `monkeypatch.setattr(settings, …)` works (the `_context_limit_exceeded` note).
- **Fail-closed storage errors mapped to `500`** by a named exception (`DuplicateCheckError`).
- **Two-instance proof in `tests/test_two_instance_smoke.py`**; measurement by a script in `scripts/` with its numbers in the README.

## 7. Tools/Features

### F1 — Characterization
Pins the full audit row written by each arm of `run_conversation` (three forbidden arms, context limit, duplicate, pattern block, pattern flag, redaction limit, both redaction errors, upstream error, success) and what `call_openrouter` returns for a `usage` object with and without the split. Green on untouched code. The row assertions gain fields later and lose none.

### F2 — Audit columns
The eight columns of Section 6.2 through `CREATE_AUDIT_LOGS_TABLE`, `AUDIT_LOGS_ADDED_COLUMNS`, `AuditLog`, `insert_audit_log`, `_row_to_audit_log` and the `json_object` in `_SUMMARY_SQL`. `init_db()` needs no new code for them.

### F3 — Split token counts
`OpenRouterResult(response, model_used, tokens_used, input_tokens=None, output_tokens=None)`. `prompt_tokens` and `completion_tokens` are read with `.get`, accepted only when they are non-negative integers, and never make the call fail. `total_tokens` keeps today's strictness. The injected stubs across the suite construct `OpenRouterResult` with three positional fields and keep working.

### F4 — Conversation key
Section 6.3. Pure, no I/O, no settings. Tests: stable across 50 growing turns; differs by user; differs by first user message; a conversation with no `system` turn; the same key for `[user]` and `[user, assistant, user]` with the same first turn.

### F5 — Audit fields on every arm
`log_query` gains the eight parameters. `run_conversation` computes `message_count` and `conversation_key` once, beside the key, and passes them with `ingress` and `streamed` on every call. `has_tool_calls` is passed as `False` at one place with a comment naming PRD-016. `_deny` requires the new values.

### F6 — Settings
Section 9.3. The two limit maps are parsed once into `dict[str, Optional[int]]` properties. Each validator's message names the setting, quotes the offending entry, and shows a valid example.

### F7 — Per-user overrides
`users.token_budget_daily`, `users.requests_per_minute`; `User` and `_row_to_user` carry them; `set_user_limits(user_id, …)`; `manage_users.py set-limits`, where `default` clears an override to `NULL` and a number below 1 is refused; `list-users` prints both columns, with `default` for `NULL`.

### F8 — Counter storage
`usage_daily` created in `init_db()`'s one `_session()` block. `admit_usage(user_id) -> UsageAdmission(day, window_start, window_requests, tokens_today)` and `charge_usage(user_id, day, input, output, unsplit)` in `database.py`, each one statement. The story verifies `RETURNING` on the pinned driver first and records the result.

### F9 — `usage_limits`
`limits_for(identity)`, `admit(identity, charges_budget) -> Admission`, where `Admission` is either admitted (carrying `day`) or refused (carrying `limit`, `maximum`, `actual`, `resets_at`), and `charge(...)`. `admit` wraps `StorageError` in `UsageLimitError`. `charge` catches `StorageError`, logs at `ERROR` with the user id, the day and both counts, and returns.

### F10 — Gate in the pipeline
Step 2c. Skipped entirely when `USAGE_LIMITS_ENABLED` is false. On refusal: the audited arm of Section 6.7 and `QueryBlockedUsageLimitResponse`. `/query` maps `UsageLimitError` to `500`; `ChatState` renders it through the existing internal-error bubble.

### F11 — Charge in the pipeline
Step 7b, immediately after `call_openrouter` returns. When the split is present, `input_tokens` and `output_tokens` are charged. When it is absent, `tokens_used` is charged to `unsplit_tokens`, so the day's total is still right. Not called for BYOK, or when limits are off.

### F12 — Break-glass policy
Section 6.8: `Identity.break_glass`, the setting, the step 2b arm.

### F13 — `/audit` and `/stats`
Section 6.10. `/stats` keeps `row_limit=0`.

### F14 — Chat bubble
Section 6.10. Two copy strings, one per limit, with `resets_at` formatted in UTC by the existing formatting helpers.

### F15 — Register and summary
Section 6.10. The column set of the Register row does not grow; the tokens cell changes format and the rest is disclosure.

### F16 — Usage view
`usage_snapshot() -> list[UsageRow]` in one statement; a `UsageRow` projection in `admin_models.py`; `components/usage.py`; loaded by `AdminState.load` with its own `READ_LABEL`, so a failed usage read names itself and does not blank the summary. `sign_out()` clears it.

### F17 — Two-instance test and latency
`test_two_instance_smoke.py` gains: a rate limit of 5 with 10 requests alternated across two processes admits exactly 5; a budget exhausted through one process refuses on the other; a second user is admitted throughout. `scripts/measure_usage_latency.py` reports p50/p95 of `admit` and `charge` against the local libSQL server and against a remote endpoint.

### F18 — Documentation
README: a *Usage limits* section under Features; the audit field table; the eighth `/query` outcome; the *Duplicate detection scope* note changed from "planned as PRD-013" to shipped; *The database is a hard dependency* updated with the new round trips; the `ADMIN_TOKEN` row and the four new settings in the environment table; the roadmap entry. `.env.example`: four settings.

## 8. Technology Stack

No new dependencies.

| Layer | Technology (installed) | Use in this PRD |
|---|---|---|
| Storage | Turso / libSQL, `libsql==0.1.11` (PRD-007) | Eight nullable or defaulted audit columns; two `users` columns; one new table; `INSERT … ON CONFLICT … RETURNING` for the gate |
| API | FastAPI, pydantic v2 | One response model; additive fields on two read models |
| HTTP client | httpx (sync) | Unchanged; two more fields read from `usage` |
| Settings | `pydantic-settings` | Four settings, existing `Settings` class and validator style |
| Chat UI / console | `reflex==0.9.6.post1` | One bubble kind; one table component; `pydantic.BaseModel` row models (`rx.Base` does not exist in this version, per `admin_models.py`) |
| Tests | pytest, pytest-asyncio, existing `temp_db` fixtures | Two-instance smoke extended |

**Skill constraints (`frontend-design`):** the two UI surfaces this PRD adds follow the existing register and bubble system. The rules quoted in Section 6.10 govern their structure and copy.

## 9. Security & Configuration

### 9.1 Authentication & authorization

Identity still comes from the bearer token, and the three existing authorization arms run first and unchanged. Two things are added after them. The break-glass arm (2b) refuses one credential on ingresses outside the allowed set. The usage gate (2c) refuses an authorized identity that is over a limit. Neither can admit a request that authorization refused. The limits an identity carries are set only by `resolve()` from the `users` row; `Identity` is frozen, and no request field reaches them.

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **Unbounded spend of the harness key** by one valid token | Daily token budget per user, on by default. Closes PRD-009 T1 and PRD-010 T5/T6 as far as spend goes |
| T2 | **A looping agent** resends the same request | Rate limit counts every authorized attempt at 2c, before the duplicate check, so duplicate-blocked retries still consume the window |
| T3 | **Forced failures used to resend** (PRD-009 T3) | Failed attempts are counted by the rate limit. Tokens are charged whenever the provider reported them, even if the response was then lost |
| T4 | **Prefix variation to defeat the duplicate key** (PRD-010 T4) | Not prevented; bounded. Every variation is an attempt and a charge |
| T5 | **A second instance doubles the limit** | One counter row in the shared database, one atomic statement, the database's clock. Proven by the two-instance test |
| T6 | **Budget overshoot by concurrency** | Accepted and bounded by the rate limit times one response (Section 6.5). Stated in the README |
| T7 | **Counter outage as a bypass** | `admit` fails closed: `UsageLimitError`, `500`, nothing sent upstream. The same choice the duplicate check makes |
| T8 | **Charge write fails after the model answered** | Fails open on purpose: the user gets the answer they paid for, the failure is logged at `ERROR`, and the audit row's `input_tokens`/`output_tokens` are the record. Under-counting for the length of an outage is accepted; reconciliation is a Future Consideration |
| T9 | **Break-glass token pasted into an agent** | Refused on `v1`, audited. The setting cannot add `v1`. A direct call with no ingress is refused too |
| T10 | **Audit flooding**: a client hammering a rate limit writes one row per refusal | Accepted for now, because every attempt audited is the founding property. Rows are small, the Register filters by verdict, and the usage view shows the refusal count. Coalescing is a Future Consideration (Risk 3) |
| T11 | **Usage limit as an oracle** for an unauthorized caller | The gate runs after all authorization arms, so a caller without `query:submit` sees only the permission refusal |
| T12 | **A user locks out another user** | Counters are keyed by the credential-resolved `user_id`, never by a request field (the PRD-009 F5 rule) |
| T13 | **`conversation_key` leaks content** | It is a SHA-256 over text whose previews the same reader already sees. It is not reversible and adds no new disclosure |
| T14 | **BYOK as a way around the budget** | By design: BYOK spends the caller's key. It requires `query:byok`, which only `admin` has by default, and it is still rate-limited and fully audited |

Invariants that must hold, each asserted by a test:

- Authorization → break-glass → usage gate → context limit → duplicate → patterns → redaction → upstream → charge. Order asserted with spies.
- Every outcome still writes exactly one audit row (the PRD-011 flag arm's second row aside), and every row carries `ingress`, `message_count` and `conversation_key`.
- `conversation_key`, `dedup_key` and `prompt_hash` are computed from raw text only.
- A usage-limit row is never a prior query.
- With `USAGE_LIMITS_ENABLED=false`, no statement touches `usage_daily`.
- No schema accepts `ingress`, `streamed` or a limit as a request field.

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `USAGE_LIMITS_ENABLED` | `true` | — | Master switch for the gate and the charge. `false` writes and reads no counter |
| `USAGE_DAILY_TOKEN_BUDGET` | `*=1000000` | `role=value` pairs; a `*` entry is required; each value an integer `≥ 1` or `unlimited`; no role twice | Tokens per user per UTC day, by role |
| `USAGE_REQUESTS_PER_MINUTE` | `*=60` | Same | Authorized attempts per user per minute, by role |
| `BREAK_GLASS_INGRESSES` | `query,chat` | Any subset of `query`, `chat`, possibly empty; `v1` is rejected | Ingresses on which the `ADMIN_TOKEN` identity may submit to the pipeline |

The defaults are provisional. They are chosen so that no ordinary chat or script use reaches them, and so that a deployment is bounded from its first boot. The latency story records what a looping agent reaches at these values, and the README states them as starting points.

`ADMIN_TOKEN` keeps its meaning. Its README row gains one sentence: it is refused on `/v1`, and `BREAK_GLASS_INGRESSES` can refuse it on `/query` and the chat UI as well.

### 9.4 Out of scope (security)

Per-user concurrency caps. Multi-account correlation (the same person holding several accounts). Reserving `max_tokens` against the budget. Retention of `usage_daily` and of `audit_logs`. Removing the admin role's model-allowlist bypass. Alerting when a user approaches a limit.

## 10. API Specification

**`POST /query`: no request change.** The response union gains one member, returned as `200`:

```json
{
  "status": "BLOCKED",
  "reason": "Usage limit reached",
  "limit": "tokens",
  "maximum": 1000000,
  "actual": 1003412,
  "resets_at": "2026-10-05T00:00:00Z"
}
```

| Endpoint | Change |
|---|---|
| `POST /query` | New `200` `BLOCKED` usage-limit body. `500` when the usage counter cannot be read. A request authenticated with `ADMIN_TOKEN` behaves as today under the default `BREAK_GLASS_INGRESSES` |
| `GET /audit` | `AuditQueryEntry` gains `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key`, `limit_exceeded`. Additive |
| `GET /stats` | `StatsResponse` gains `input_tokens`, `output_tokens`, `blocked_usage_limits`. Additive. Usage-limit rows are `success=true`, so they count in `success_rate` the way duplicate blocks do |
| `GET /health` | None |
| Chat UI | New `usage_limit` bubble |
| Admin console | Register fields, three summary figures, Usage table |

Internal API (Python):

```python
conversation_key(user_id: str, messages: Sequence[Message]) -> str
usage_limits.limits_for(identity: Identity) -> UsageLimits
usage_limits.admit(identity: Identity, *, charges_budget: bool) -> Admission   # raises UsageLimitError
usage_limits.charge(user_id: str, day: str, input_tokens: Optional[int],
                    output_tokens: Optional[int], total_tokens: int) -> None   # never raises
run_conversation(identity, messages, device, model, openrouter_api_key,
                 params=None, call_openrouter=call_openrouter, session_id=None,
                 *, profile=None, ingress=None, streamed=False) -> QueryPipelineResult
run_query(identity, prompt, device, model, openrouter_api_key,
          call_openrouter=call_openrouter, session_id=None,
          *, ingress="query") -> QueryPipelineResult
```

CLI:

```bash
python scripts/manage_users.py set-limits --user-id dana --token-budget 5000000
python scripts/manage_users.py set-limits --user-id dana --requests-per-minute default
```

## 11. Success Criteria

### MVP definition

A 50-turn conversation run through `run_conversation(ingress="v1")` writes 50 rows with one `conversation_key`, 50 distinct `dedup_key` values, and a `prompt_hash` on each that is the hash of that row's own last user turn. A user over budget gets the usage-limit body and one row with `limit_exceeded='tokens'`, while a second user's request in the same test succeeds. Both hold with the requests split across two processes on one database. `run_conversation` with the `ADMIN_TOKEN` identity and `ingress="v1"` is refused. The admin console renders a Usage table, and `test_query_outcomes_regression.py` rows 1–7, `test_chat_outcomes_regression.py` and the console tests pass with no assertion changed.

### Functional requirements

**Audit**
- [ ] `init_db()` converges all eight columns on a pre-existing database, backfills nothing, and issues no `ALTER` when the schema is current
- [ ] Every arm of `run_conversation` writes `ingress`, `message_count`, `conversation_key` and `streamed`; `/query` rows carry `ingress='query'`, chat rows `ingress='chat'`
- [ ] `message_count` is the count as received: 1 on `/query`, `2N-1` on the Nth chat send of a session with nothing trimmed (N-1 prior exchanges plus the new turn)
- [ ] The success row and the output-redaction-error row carry `input_tokens` and `output_tokens`; the upstream-error row carries neither
- [ ] A provider response without the split still succeeds, with both fields `NULL` and `tokens_used` set
- [ ] `conversation_key` is identical across turns of one growing conversation and differs across users
- [ ] No production call site of `run_conversation` or `run_query` omits `ingress` (scan test)
- [ ] `/audit` returns the eight fields; rows written before this PRD return `null` for the six nullable ones and `false` for the two flags
- [ ] `/stats` returns the three figures and they equal direct sums over `audit_logs`; the batched read and the figure-by-figure fallback agree

**Limits**
- [ ] With a rate limit of N, attempt N+1 inside one minute is refused with `limit="requests"` and attempt 1 of the next minute is admitted
- [ ] A duplicate-blocked attempt and a context-limit refusal each consume one unit of the rate window
- [ ] A caller without `query:submit` consumes none, and `usage_daily` has no row for them
- [ ] A user at or over the token budget is refused with `limit="tokens"`; `resets_at` is the next 00:00 UTC
- [ ] When both limits are broken, `requests` is the one reported
- [ ] Tokens are charged on success and on the output-redaction-error arm, and not on the upstream-error arm
- [ ] A BYOK request is counted by the rate limit, is not refused for budget, and charges nothing
- [ ] A per-user override wins over the role entry; `default` restores the role entry; a role with no entry gets `*`; `unlimited` is never refused
- [ ] A usage-limit row has `success=1`, `limit_exceeded` set and a non-NULL `dedup_key`, and the same prompt sent after the window resets is **not** held as a duplicate
- [ ] A storage failure in `admit` returns `500` on `/query` and makes no upstream call; a storage failure in `charge` returns the response and logs an error
- [ ] With `USAGE_LIMITS_ENABLED=false`, no statement touches `usage_daily` and the pipeline's round-trip count equals today's
- [ ] Each of the four settings rejects an invalid value at startup with a message naming it; `BREAK_GLASS_INGRESSES=v1` is rejected

**Break-glass**
- [ ] `resolve(ADMIN_TOKEN).break_glass` is `True`; a user with the `admin` role resolves with `False`
- [ ] The break-glass identity is refused under `ingress="v1"` and `ingress=None`, with one row carrying `denied_permission="ingress:break_glass"`
- [ ] Under the default setting it is admitted on `query` and `chat`, exactly as today
- [ ] The admin console still signs in with `ADMIN_TOKEN`

**Surfaces**
- [ ] The chat shows the usage-limit bubble for each limit, and a reload restores it
- [ ] The Register shows a usage-limit row as **denied** and finds a conversation by its key
- [ ] The Usage table shows one row per user active today with requests, input, output, budget, share used and refusals; an empty day shows its empty-state line
- [ ] A failed usage read names itself and leaves the summary and Register rendered
- [ ] `sign_out()` clears the usage rows

### Eight `/query` outcomes (seven unchanged, plus one)

| # | Outcome | Status | Body `status` / detail | Audit rows |
|---|---|---|---|---|
| 1–7 | As PRD-010 Section 11 | unchanged | unchanged | unchanged |
| **8** | **Usage limit** | **200** | **`BLOCKED`, `"Usage limit reached"`** | **1** |

### Cross-instance and latency

- [ ] Two processes, one database: a rate limit of 5 admits exactly 5 of 10 alternating requests
- [ ] A budget exhausted through instance A refuses on instance B
- [ ] p50/p95 of `admit` and `charge` are recorded for the local dev server and a remote endpoint, and the README states the added round trips per request

### Refinement of the brief's criteria

- "A 50-turn conversation produces 50 rows … each previewing its own user turn" already holds for the preview on `main` (Section 6.4). It is pinned here, not built.
- "`ADMIN_TOKEN` is refused on the non-UI ingress" is tested as `ingress="v1"` by direct call, because `/v1` does not exist until PRD-014. `/query` is also a non-UI ingress; it keeps accepting the token by default so that no existing script breaks, and an operator can refuse it there with `BREAK_GLASS_INGRESSES=chat`.

### Quality indicators

- [ ] Full suite green. Mass fixture errors mean restart the libSQL dev container, not bisect code
- [ ] No assertion changed in `test_query_outcomes_regression.py` rows 1–7, `test_chat_outcomes_regression.py`, `test_duplicate_scope.py`, `test_pii_characterization.py`
- [ ] Every modified pre-existing test carries a comment citing PRD-013 and its decision
- [ ] `tests/test_admin_models.py` still fails if a preview field is added to `AuditRow`

## 12. Implementation Phases

### Phase 1 — The row (Stories 1–6)
**Goal:** every row describes a multi-turn request, and nothing about limits exists yet.
**Deliverables:** characterization; the eight columns; split token counts; `conversation_key`; `ingress`, `message_count`, `conversation_key`, `streamed` and the token split on every arm, with call sites passing `ingress`; `/audit` and `/stats` fields.
**Validation:** characterization green before and after; the 50-turn criterion passes; seven-outcome and chat regression unchanged.

### Phase 2 — Limit primitives (Stories 7–10)
**Goal:** limits can be configured, stored and evaluated in isolation.
**Deliverables:** four settings with validators; `users` override columns, `Identity` fields and `set-limits`; `usage_daily` with `admit` and `charge` (and the `RETURNING` finding); `usage_limits` with resolution and the two checks.
**Validation:** unit tests green; no pipeline behaviour changed; `USAGE_LIMITS_ENABLED` not yet read by the pipeline.

### Phase 3 — Enforcement (Stories 11–14)
**Goal:** the pipeline refuses, charges and audits.
**Deliverables:** the gate, the response model, the audited arm and the duplicate-lookup predicate; the charge with the BYOK rule; the break-glass arm; the chat bubble.
**Validation:** order asserted with spies; eighth regression row green; the existing seven unchanged.

### Phase 4 — See it and prove it (Stories 15–18)
**Goal:** an admin can see usage, and the limits are shown to hold where it matters.
**Deliverables:** Register and summary changes; the Usage table; the two-instance test and the latency measurement; regression sweep, README and `.env.example`.
**Validation:** full suite green; README figures match the measurement report.

## 13. Future Considerations

- **`GET /usage`** for a caller's own remaining budget, with `usage:read:own` / `usage:read:all`. Deferred because a new permission is denied by default for every deployment with a custom `RBAC_ROLES_FILE`.
- **Reserving `max_tokens`** against the budget before the call, which closes the overshoot in Section 6.5.
- **Per-user concurrency caps** on the pipeline executor (PRD-010 T6).
- **Coalescing rate-limit refusals**: one audited row per window with a count, if flooding (T10) is seen in practice.
- **Reconciliation** of `usage_daily` from `audit_logs` after a charge outage (T8).
- **Budget periods other than daily**, and budgets per model or in currency.
- **`conversation_key` as a `/audit` filter**, with an index on `(user_id, conversation_key)`.
- **Per-role PII telemetry and the skip-and-flag record** (PRD-012 Section 13), **per-pattern metrics** and **more than one flag per request** (PRD-011 Section 13). These need a per-request detail table, which is its own design.
- **A sliding rate window**, if the fixed window's 2× edge matters.
- **Retention** for `usage_daily`, with the audit retention the README already lists as missing.
- **PRD-014** passes `ingress="v1"` and `streamed`, and maps the usage-limit result to an OpenAI error. **PRD-016** sets `has_tool_calls`.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Counter round trips add latency to every request**: one for the gate, one for the charge, on a path that already makes two | High / Medium | Each is a single statement on a primary key. Measured against local and remote endpoints, with the numbers in the README. `USAGE_LIMITS_ENABLED=false` restores today's count exactly |
| 2 | **`RETURNING` does not work on the pinned driver** | Medium / Medium | Verified first, in the storage story, before the gate depends on it. The fallback is upsert plus select in one transaction, and the measurement covers whichever ships |
| 3 | **A hammering client floods `audit_logs`** with refusal rows | Medium / Medium | Accepted with T10's reasoning. The Register filters by verdict and the Usage table shows the count. Coalescing is specified as the follow-up |
| 4 | **Default limits refuse a legitimate user** on upgrade | Low / High | Defaults set well above chat use; the refusal names the limit and the reset; one CLI command raises one user; one setting raises a role; the master switch turns both off |
| 5 | **Touching the duplicate lookup** breaks PRD-009's control | Low / High | One added predicate that `NULL` passes. `test_duplicate_scope.py` and the characterization suite may not change an assertion, and a new test covers the refused-then-resent case |
| 6 | **Admin console scope creep** (PRD-006 was 20 stories) | Medium / Medium | The usage view is one table with no chart, no history and no controls. The Register gains no column. Anything else is Section 13 |
| 7 | **`conversation_key` groups unrelated conversations** or splits one | Medium / Low | It includes the user id, is documented as a grouping aid, and `session_id` remains authoritative for chat rows |
| 8 | **`_SUMMARY_SQL` grows from ten figures to thirteen** and a positional parameter shifts | Low / Medium | The three new figures take no parameter and are appended after the existing ten. The existing batched-versus-standalone agreement test is extended to all thirteen |

## 15. Appendix

### Source
- Pre-PRD brief: [pre-prds/PRE-PRD-013-audit-and-usage-limits.md](../../../pre-prds/PRE-PRD-013-audit-and-usage-limits.md)
- Track overview: [pre-prds/README.md](../../../pre-prds/README.md). Depends on PRD-010; blocks PRD-014.

### Decisions (resolved from the brief's open decisions)

| # | Question | Decision |
|---|---|---|
| D1 | Budget period | **Daily, UTC, per user**, with role defaults in settings and a per-user override on `users`. As proposed. The day is the database's, not the instance's (Section 6.5) |
| D2 | Conversation key for external clients | **Hash of user id + first `system` + first `user` message**, versioned, over raw text, written on every row and exposed. As proposed (Section 6.3) |
| D3 | Rate limit storage | **Turso counter rows**. As proposed, narrowed to one row per user per day that also holds the rate window, so the gate is one statement (Section 6.5) |
| D4 | Admin token on `/v1` | **Refused**, and the setting cannot allow it. *Extension:* `/query` and the chat UI keep accepting it by default and can be tightened with `BREAK_GLASS_INGRESSES` (Section 6.8) |
| D5 | Budget exhausted response | **Never `429`.** *Refinement:* on `/query` it is `200` `BLOCKED`, like every other block there. The `403` is the `/v1` mapping and belongs to PRD-014 D2 (Section 6.7) |
| D6 | *(new)* How is a refusal recorded? | **`audit_logs.limit_exceeded`**, with `success=1`, excluded from the duplicate lookup (Sections 6.2, 6.7) |
| D7 | *(new)* Where does the gate sit, and what does it count? | **After authorization, before every content check.** The rate counts every authorized attempt; the budget charges reported tokens (Section 6.1) |
| D8 | *(new)* BYOK | **Rate-limited, not budget-charged** (Section 6.5) |
| D9 | *(new)* What if the counter is unavailable? | **Gate fails closed, charge fails open** (T7, T8) |
| D10 | *(new)* How is `ingress` set? | **By the call site**, keyword-only, with a scan test over production call sites (Section 6.9) |

### Assumptions
- The default limits (`1,000,000` tokens a day, `60` requests a minute) are placeholders to be confirmed by the operator. Nothing in the repository states an intended spend.
- Limits are on by default. A deployment that upgrades gets them without opting in.
- The brief's "non-UI ingress" is read as `/v1`. `/query` is left accepting `ADMIN_TOKEN` by default to avoid breaking existing scripts.

### Evidence (verified against `main` @ `b184614`, the PRD-012 merge)
- `app/services/audit_logger.py`: `_PREVIEW_LENGTH = 500`; `prompt_preview = prompt[:500]`; `response_hash` and `response_preview` computed the same way; no ingress, count, split or conversation field.
- `app/services/query_pipeline.py`: `prompt = messages[-1].content`; `dedup_key(identity.user_id, messages)` at step 1; ten `log_query` call sites, `_deny` (which serves the three authorization arms) among them; `run_conversation(..., *, profile=None)`.
- `app/services/openrouter_client.py`: `tokens_used = data["usage"]["total_tokens"]`; `OpenRouterResult(response, model_used, tokens_used)`.
- `app/services/identity.py`: `resolve()` returns `Identity("admin", "admin")` for `ADMIN_TOKEN` without reading `users`; `Identity` has `user_id` and `role` only.
- `app/services/authz.py`: `MODEL_ALLOWLIST_WILDCARD_ROLES = {"admin"}`; `query:byok` granted to `admin` only in the built-in matrix.
- `app/db/database.py`: `find_duplicate_timestamp` filters on `success = 1`, `was_duplicate_blocked = 0`, `denied_permission IS NULL` and the flag exclusion; `_add_missing_columns(conn, table, columns)` is table-generic; the driver has no batch, and `_SUMMARY_SQL` is one statement of ten named columns.
- `app/db/models.py`: `users` has five columns and no added-columns mapping.
- `app/routers/query.py`: the foreign-session refusal writes its own row before `run_query`.
- `chat_ui/chat_ui/admin_state.py`: `authenticate` compares the submitted token to `settings.ADMIN_TOKEN` directly.
- `chat_ui/chat_ui/admin_formatting.py`: `derive_verdict` is duplicate → held, pattern block → denied, `not success` → fault, otherwise cleared. A permission refusal (`denied_permission` set, `success=1`) therefore reads **cleared** today. Noted, not changed by this PRD.
- `scripts/manage_users.py`: `create-user`, `list-users`, `deactivate-user`, `issue-token`.
- `requirements.txt`: `libsql==0.1.11`, `reflex==0.9.6.post1`.

### Tentative story breakdown (to be generated by `/create-stories`)
Reordered from the brief: characterization first; the columns before anything writes them; settings and storage before enforcement; the chat bubble added, because `ChatState` must handle every result type.

1. Characterize today's audit row per arm and the client's `usage` parsing
2. Eight additive audit columns: convergence, `AuditLog`, writer, both read shapes (brief 1)
3. Split token counts from OpenRouter (brief 3)
4. `conversation_key` derivation (brief 4)
5. `log_query` and every pipeline arm write the new fields; `ingress` at every call site (brief 2, 5)
6. `/audit` entry fields and `/stats` aggregates (brief 6, 7)
7. Limit and break-glass settings with startup validators (brief 8)
8. Per-user overrides: `users` columns, `Identity`, `manage_users.py set-limits` (brief 8)
9. `usage_daily`, `admit` and `charge`; `RETURNING` verified (brief 9)
10. `usage_limits`: resolution and the two checks (brief 9)
11. Usage gate in the pipeline: response, audited arm, duplicate-lookup exclusion (brief 10, 11, 12)
12. Charge after upstream; BYOK rule; counter-failure behaviour (brief 10)
13. Break-glass ingress policy (brief 13)
14. Chat UI usage-limit bubble
15. Admin console: Register fields, verdict, search, summary figures (brief 14)
16. Admin console: Usage table (brief 15)
17. Two-instance limit test and latency measurement (brief 16)
18. Eight-outcome, chat and console regression; README and `.env` docs (brief 17, 18)

### Related documents
- PRD-005 (RBAC): `Identity`, `resolve()`, the role matrix, the admin model bypass
- PRD-006 (admin console): `AuditRow` as a projection, the verdict precedence, figures state their window
- PRD-007 (Turso migration): no client batch, one statement per read, `init_db()` convergence, the two-instance requirement
- PRD-008 (chat sessions): `session_id`, the foreign-session refusal, bubble persistence
- PRD-009 (duplicate rescoping): the lookup's exclusions, T1 and T3 assigned here, Risk 4
- PRD-010 (multi-turn pipeline): `Message`, `run_conversation`, the audit `prompt` as the last user turn, T4–T6
- PRD-011 (pattern policy): the server-selected call-site argument; the flag arm's second row
- PRD-012 (PII for code): `audit_logs.profile` on every arm; the call-site scanning test

### Dependencies
- Depends on: PRD-010 (done, merged). PRD-011 and PRD-012 are also merged to `main`, and this PRD builds on their `profile` plumbing.
- Blocks: PRD-014.

**Skills referenced:** frontend-design
