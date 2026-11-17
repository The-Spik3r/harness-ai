# API reference

Every request and response shape for `POST /query`, `GET /audit`, `GET /audit/actions`, `GET /stats`, `GET /storage/status`, and the OpenAI-compatible `POST /v1/chat/completions` and `GET /v1/models`.

← Back to the [README](../README.md).

---

## API Reference

### `POST /query` — success

```bash
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "my name is Maria Gomez, my email is juan@empresa.com"}'
```

```json
{
  "status": "SUCCESS",
  "response": "Sure — I will reply to <EMAIL_ADDRESS> for <PERSON>.",
  "audit_id": 1,
  "audit_ref": "3f2a9c1e8b7d4a6f9e0c5d2b1a8f7e63",
  "model_used": "gpt-4",
  "tokens_used": 45,
  "pii_redacted": true,
  "pii_entities_masked": ["EMAIL_ADDRESS", "PERSON"]
}
```

OpenRouter received `my name is <PERSON>, my email is <EMAIL_ADDRESS>` — never the raw text. `pii_entities_masked` is the sorted union of entity types masked in the prompt and in the response; when nothing is detected, `pii_redacted` is `false` and the list is empty. Both fields are additive — clients that ignore unknown fields are unaffected, and the two `BLOCKED` shapes below are unchanged (redaction runs only after both checks pass).

`audit_ref` is on every success and equals the audit row's `write_id`, a client-minted id that lets a replayed write be recognised. `audit_id` is the row's number, and is `null` only when the row was written to the [audit journal](deployment.md#what-a-database-outage-does) because the database could not take it; the answer is still released, and `audit_ref` is how the row is found once it has drained.

The token identifies the caller — the request body's `user_id`, if present, is accepted only for backward compatibility and must match the authenticated identity or the request is refused with `403` (`user_id does not match the authenticated identity`).

`session_id` is optional and names the conversation a send belongs to. **Omit it and the request behaves exactly as it did in the previous release**, writing `NULL` to the audit row — clients written against the earlier API need no change. Supplied, it must be a **canonical lowercase UUID4** string: the harness mints session ids and echoes them back unchanged, so `{braces}`, a `urn:uuid:` prefix, uppercase hex and non-v4 ids are each a `422`. The value is recorded exactly as sent rather than normalized, which is why a second spelling of the same id is refused instead of quietly accepted. `POST /query` stores no transcript — the field only labels the audit row with the conversation it belonged to.

### `POST /query` — 401 (no or invalid credential)

```json
{"detail": "Invalid or missing credential"}
```

Missing header, unknown token, or a deactivated user all map to this same response — deliberately indistinguishable, so a caller cannot enumerate valid credentials.

### `POST /query` — 403 (authenticated, lacks `query:submit`)

```json
{"detail": "Permission denied: query:submit"}
```

The `auditor` role holds no `query:submit` permission by default, so it always gets this response from `POST /query`. In the chat UI, the identical decision renders as an in-thread bubble rather than a session error, because the browser ingress has no router layer to enforce it at.

### `POST /query` — 403 (session belongs to another identity)

```json
{"detail": "session_id does not belong to the authenticated identity"}
```

A `session_id` the caller does not own is refused at the boundary, beside the `user_id` check above. Unlike that one, **this refusal is written to the audit log** — with the attempted `session_id` on the row — because a rejected send is recorded with the same rigor as an accepted one. An unknown session and another user's session produce the identical response, so the id space cannot be probed for which conversations exist.

### `POST /query` — blocked (duplicate)

Send the exact same prompt again from the same account, within 24 hours of it being answered:

```json
{
  "status": "BLOCKED",
  "reason": "Duplicate query within 24 hours",
  "first_query_at": "2026-07-04T10:30:00Z"
}
```

`first_query_at` is the earliest qualifying occurrence in the window — an answered or pattern-blocked send, never a failure or an earlier held repeat. See [Duplicate detection scope](features.md#duplicate-detection-scope).

### `POST /query` — blocked (suspicious pattern)

```json
{
  "status": "BLOCKED",
  "reason": "Suspicious pattern detected",
  "pattern": "override"
}
```

The default policy's patterns, matched as whole words and phrases, case-insensitively: the `injection` list — `ignore previous instructions`, `forget everything`, `show system prompt`, `reveal password` — and the `keywords` list — `execute code`, `admin mode`, `override` — which ignores hits inside code blocks. A deployment replaces both with its own file via `PATTERNS_FILE`; see [Pattern policy](features.md#pattern-policy).

The body names the matched pattern and never the role of the message it was found in — that goes to the audit (`pattern_role`), where an admin reads it. The body is byte-identical to the previous release's.

### `POST /query` — 200, refused by policy

```json
{
  "status": "BLOCKED",
  "reason": "Model not permitted for this role",
  "required_permission": "query:model:claude-3-opus"
}
```

Model-allowlist and BYOK (`openrouter_api_key`) refusals return `200` with this shape, not `403` — the caller is authenticated and allowed to call the endpoint, but the content of the request is what's refused. This is the same rendering path as a duplicate or injection block.

### `POST /query` — blocked (context limit)

```json
{
  "status": "BLOCKED",
  "reason": "Conversation exceeds context limit",
  "limit": "characters",
  "maximum": 200000,
  "actual": 250113
}
```

**This is the only outcome the multi-turn release (PRD-010) added** — the six before it are unchanged, request and response alike. `limit` is `messages`, `characters` or `redaction_characters` (below). For the first two, **only one is ever reported**: the message count is checked first and returns immediately, so a conversation over both is reported as `messages`. A caller that shortens to fit the count is told about the character count on the next attempt; naming both would imply the two were measured independently when the second was never reached. `maximum` is the limit as configured for that call, echoed back so a client can see the bound it broke without reading the server's configuration.

The check sits after authorization and before the duplicate check. After, so a caller without `query:submit` learns nothing about how the deployment is configured; before, so an over-limit conversation neither consults the 24-hour window nor lands in it — it never got a verdict, so it is not a query anyone asked twice. The attempt is still audited, as `success=false` with `error_message` naming the limit — the same shape an upstream failure writes, and no new `audit_logs` column. `GET /audit` and `GET /stats` are unchanged; these rows count against `success_rate`, which is accepted.

`redaction_characters` is the `code` profile's PII limit, with `"reason": "Conversation exceeds redaction limit"` and `maximum` set to `PII_MAX_CHARACTERS_CODE`. It is checked at redaction — after the duplicate and pattern checks, not beside the other two — because what it measures depends on the PII policy: only the roles `code` redacts count, and fenced content does not. It is audited the same way, `success=false` with `error_message` reading `redaction limit: characters <actual> > <maximum>`. **It is unreachable from `POST /query`**, which runs `chat`, a policy with no PII-specific limit. See [PII redaction](features.md#pii-redaction).

For `POST /query` the reachable case is a single prompt over `CONTEXT_MAX_CHARACTERS` (200,000 by default, ≈50k tokens of English), which previously went upstream. See [Multi-turn context](features.md#multi-turn-context).

### `POST /query` — blocked (usage limit)

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

The eighth `POST /query` outcome, added by PRD-013; the seven before it are unchanged. `limit` is `requests` (the per-minute rate) or `tokens` (the daily budget), and when both are broken, `requests` is the one reported. `maximum` is the limit that applied to this user — their own override, their role's entry, or `*`. `actual` is this minute's attempt count, this one included, for `requests`, and the tokens already charged today for `tokens`, which can be above `maximum` (see [Usage limits](features.md#usage-limits) on overshoot). `resets_at` is UTC in the audit timestamp format: the start of the next minute for `requests`, the next 00:00 UTC for `tokens`. It is a `200`, like every other block on this endpoint, never a `429`.

The check sits after authorization and the break-glass check, and before the context limit and every content check. After, so a caller without `query:submit` learns nothing about the deployment's limits and spends nothing; before, so a refused request is never analyzed. The attempt is audited as one row with `success=true` and `limit_exceeded` set to the limit, the way a duplicate block is recorded, and it is never treated as a prior query by the duplicate check. If the usage counter cannot be read, the response is a `500` and nothing is sent upstream.

### `POST /query` — 503 (storage unavailable)

```json
{"detail": "Storage unavailable"}
```

```json
{"detail": "Storage unavailable: the request was not sent to the model."}
```

Both come with a `Retry-After` header in whole seconds (at least 1). The first answers when the identity read fails; the second when the session-ownership check, the usage gate or the duplicate check fails because the database is unreachable, and it is the harness saying nothing was sent upstream and nothing was spent. `Retry-After` is the time to the storage circuit breaker's next probe, or `1` when the breaker is closed and only the retry budget ran out.

Two more cases answer `503`: the answer was produced but its audit row could be neither written nor journaled (nothing is released), and the audit journal has no headroom for a request (`Retry-After: 1`, checked before the model is called). A failure that is not an outage, such as a statement the database refused, keeps its `500` and its detail. The driver's own text never appears in a response: bodies carry this fixed copy, and the driver text is logged redacted. See [What a database outage does](deployment.md#what-a-database-outage-does).

### `GET /audit` (requires `audit:read:all` or `audit:read:own`)

```bash
curl http://localhost:8000/audit \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "total": 250,
  "queries": [
    {
      "audit_id": 1,
      "user_id": "juan@empresa.com",
      "timestamp": "2026-07-04T10:30:00Z",
      "model": "gpt-4",
      "prompt_hash": "abc123def456",
      "was_duplicate_blocked": false,
      "suspicious_pattern_detected": false,
      "device": "Chrome/Windows",
      "pii_detected_input": true,
      "pii_detected_output": false,
      "pii_entities": ["EMAIL_ADDRESS", "PERSON"],
      "role": "user",
      "denied_permission": "query:byok",
      "session_id": "0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34",
      "pattern_role": null,
      "pattern_action": null,
      "profile": "chat",
      "ingress": "query",
      "message_count": 1,
      "input_tokens": 38,
      "output_tokens": 7,
      "streamed": false,
      "has_tool_calls": false,
      "conversation_key": "5c1f0e9d2b7a4c3e8f6d1a0b9c8e7f6a5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a",
      "limit_exceeded": null
    }
  ]
}
```

`pii_entities` is the union of types masked in either direction. The audit trail deliberately stores the **raw, unmasked** prompt and response previews in the database — an auditor investigating an incident needs the actual value, not `<EMAIL_ADDRESS>` — but this endpoint exposes neither the raw previews nor the masked text, only the flags above.

`audit:read:all` returns every row; with only `audit:read:own`, the response contains solely the caller's rows and `total` reflects that scoped count. An identity holding neither permission gets `403` `{"detail": "Permission denied: audit:read:own"}` (the last permission attempted). `role` and `denied_permission` are populated on every row — `null` for rows written before this control existed or for a successful, non-denied query.

**`audit_id` is not time order after an outage.** A row that was written to the [audit journal](deployment.md#what-a-database-outage-does) and drained later gets its `audit_id` when it is drained, so it can be higher than rows written after it. The list is ordered by `timestamp`, which the drain preserves; do not sort by `audit_id` to recover time order.

`session_id` names the conversation a row belonged to, so three rows that were one conversation are visibly one conversation instead of a guess. It is `null` for two whole classes of row: everything written before this release, and every send that carried no session — `POST /query` without the field, which keeps working unchanged. **This is the only place a session reaches an admin.** No endpoint and no console surface exposes a transcript; the auditor learns that rows were related, not what was said in them beyond the previews this endpoint already withholds.

`pattern_role` and `pattern_action` say which message tripped a pattern and what was done about it: `pattern_role` is the role of the message the match was found in (`user`, `tool`, …), and `pattern_action` is `block` or `flag`. Both are `null` on rows with no pattern hit and on every row written before this release. `suspicious_pattern_detected` keeps its meaning — *a pattern matched* — so it is `true` for a flag as well as a block; `pattern_action` is what tells them apart. See [Pattern policy](features.md#pattern-policy).

`profile` names the policy that ran — `chat` for every row `POST /query` and the chat UI write — and the admin console's Register page shows it too. It is `null` on rows written before this release and on `POST /query`'s refusal of a foreign `session_id`. It matters for reading the PII flags: under the `code` profile the response is not analyzed, so `pii_detected_output: false` there means *not looked at*, not *clean*. See [PII redaction](features.md#pii-redaction).

Eight fields describe the request itself (PRD-013):

| Field | Meaning |
|---|---|
| `ingress` | The door the request came through: `query` (`POST /query`), `chat` (the chat UI) or `v1` (the OpenAI-compatible endpoint). `null` on a direct call that named none |
| `message_count` | Messages in the conversation as received, before redaction: `1` on `POST /query`, the whole history plus the new turn in the chat |
| `input_tokens` | Prompt tokens the provider reported (`usage.prompt_tokens`). `null` when no upstream call was made or the provider reported no split |
| `output_tokens` | Completion tokens the provider reported (`usage.completion_tokens`), under the same rule. `tokens_used` is unchanged: still the provider's total |
| `streamed` | The response was delivered as a stream. Always `false` until the OpenAI-compatible endpoint exists |
| `has_tool_calls` | The request carried an assistant `tool_calls` or a `tool` turn, or the upstream response carried tool calls (counted before the action policy decides them). `false` on every row while `V1_TOOLS_ENABLED=false` |
| `conversation_key` | A grouping key for the conversation the row belongs to; see below |
| `limit_exceeded` | `requests` or `tokens` on a [usage-limit refusal](#post-query--blocked-usage-limit); `null` on every other row |

Rows written before PRD-013 return `null` for the six nullable fields and `false` for `streamed` and `has_tool_calls`, which were impossible then. No row is backfilled.

`conversation_key` is a versioned hash of the user, the first `system` message and the first `user` message, over the raw text. An agent resends its whole history on every request, so every turn of one agent conversation carries the same key. It is a grouping aid, not an identity, with three limits:

- **Different conversations can share a key.** Two conversations by one user that open with the same system prompt and the same first instruction share it, and so does every identical `POST /query` prompt by one user.
- **One conversation can change key.** A client that compacts its context and rewrites its first user message starts a new key.
- **In the chat, the key can change mid-session.** Once a long chat drops its oldest exchange to fit the context limits, the first user message sent is a different one. For chat rows, `session_id` is the authoritative grouping.

It is a hash of text this endpoint's reader can already identify through `user_id` and the previews, and it is not reversible. `GET /audit` does not filter on it; the admin console's Register search does.

### `GET /audit/actions` (requires `audit:read:all` or `audit:read:own`)

The action policy's decisions, newest first, one entry per tool call, allowed ones included. Rows are written when `V1_TOOLS_ENABLED=true` and a `/v1` response carries tool calls (see [Action policy rules](features.md#action-policy-rules)); with the flag off the list stays empty. Scoped exactly like `GET /audit`: `audit:read:all` reads every user's rows, `audit:read:own` only the caller's, and neither is a `403` naming `audit:read:own`.

```bash
curl "http://localhost:8000/audit/actions?decision=deny&limit=1"   -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "entries": [
    {
      "id": 41,
      "timestamp": "2026-11-20T14:02:11Z",
      "audit_id": null,
      "user_id": "dev-1",
      "role": "user",
      "tool_call_id": "call_9",
      "tool_name": "query",
      "operation_kind": "sql",
      "target_preview": "DROP TABLE users",
      "decision": "deny",
      "rule": "sql.ddl",
      "reason": "destructive SQL is not permitted: DROP",
      "granted_by": null,
      "classifications": [{"rule": "sql.ddl", "kind": "sql", "detail": "DROP"}],
      "policy_digest": "sha256:3f1c…"
    }
  ]
}
```

- `?limit=` is `1` to `500` (default `100`); `?decision=` is `allow`, `flag` or `deny`, and any other value is a `422`. `?audit_id=` (a positive integer, the request's `audit_logs.id`) lists one request's decisions; it combines with `?decision=` and with the scoping, so under `audit:read:own` another user's request is `[]`, and a non-integer, zero or negative value is a `422`.
- `classifications` lists everything the classifiers saw, not only the rule that decided; `kind` is `null` for `tool.unknown` and `tool.malformed`. `audit_id` is the request's `audit_logs` row; `null` only for a decision recorded outside a request.
- `arguments_preview`, `arguments_hash` and `session_id` are on the stored row but deliberately **not** on this entry: the target is what the rule judged. There is no `total`.
- The Docker Caddyfile routes `/audit/actions` to the API (`tests/test_caddyfile_routes.py`).

### `GET /stats` (requires `stats:read`)

```bash
curl http://localhost:8000/stats \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "total_queries": 250,
  "blocked_duplicates": 12,
  "blocked_suspicious": 3,
  "unique_users": 8,
  "success_rate": "98.4%",
  "top_models": ["gpt-4", "claude-3-sonnet"],
  "top_users": ["juan@empresa.com", "maria@empresa.com"],
  "pii_detected_queries": 34,
  "top_pii_entities": ["EMAIL_ADDRESS", "PERSON"],
  "input_tokens": 412880,
  "output_tokens": 96410,
  "blocked_usage_limits": 4,
  "actions_denied": 0,
  "actions_flagged": 0,
  "actions_allowed": 0
}
```

`input_tokens` and `output_tokens` are sums over every audit row, with a row that recorded no split counted as `0`, so on a deployment upgraded from before PRD-013 they cover only the rows written since. `blocked_usage_limits` counts usage-limit refusals. Those rows are `success=true`, so they count in `success_rate` the way duplicate blocks do. The admin console's Summary shows the same three figures.

`actions_denied`, `actions_flagged` and `actions_allowed` count `action_decisions` rows by decision. They are additive, and `0` until a `/v1` tool call is decided (`V1_TOOLS_ENABLED=true`).

`pii_detected_queries` counts audit rows flagged on input **or** output; `top_pii_entities` ranks individual entity types by frequency across rows. Both count what was analyzed: a `code` row's response was not, so it can only be flagged on input. `/v1` is the one ingress that runs `code`, so its rows can only be flagged on input.

**`blocked_suspicious` counts blocks only.** It used to count every row with a matched pattern, which was the same thing while every hit blocked. A `flag` row matches a pattern without blocking, so counting it would inflate the security figure an admin watches; flags are excluded here and in the admin console's summary. Rows written before this release carry no `pattern_action` and still count — every one of them was a block — so no historical figure moves, and a deployment with no `tool` traffic sees no change at all.

A missing or invalid credential on any endpoint returns `401`. An authenticated identity that lacks the endpoint's required permission (e.g. a `user` role calling `GET /stats`) returns `403` with `{"detail": "Permission denied: stats:read"}`.

### `GET /storage/status` (requires `stats:read`)

```bash
curl http://localhost:8000/storage/status   -H "Authorization: Bearer $ADMIN_TOKEN"
```

```json
{
  "instance": "harness-7c9d:1",
  "breaker": {
    "state": "closed",
    "since": "2026-11-17T09:12:40Z",
    "consecutive_failures": 0,
    "last_failure_class": null,
    "retry_after_seconds": null
  },
  "journal": {
    "open": true,
    "entries": 0,
    "bytes": 0,
    "max_bytes": 67108864,
    "headroom_bytes": 2097152,
    "oldest_timestamp": null,
    "draining": false,
    "adopted_files": 0,
    "held_back_entries": 0,
    "held_back_files": 0
  },
  "counters": {
    "retries": {"admit_usage:not_sent": 2},
    "exhausted": {},
    "breaker_opens": 0,
    "journal_appended": 0,
    "journal_drained": 0,
    "torn_tail_discarded": 0
  }
}
```

What this process's storage layer is doing, answered from memory with **no database call**, so it responds while the breaker is open. `/health` is unchanged. The break-glass `ADMIN_TOKEN` can read it. The admin console shows the same at `/admin/storage`.

- `instance` is `<hostname>:<pid>`. `breaker.state` is `closed`, `open` or `half_open`; `since` is the last transition (UTC); `retry_after_seconds` is set while it is open.
- `journal.open` is `false` when this process opened no journal. `entries` and `bytes` are what is waiting to drain; both are `0` in steady state. `headroom_bytes` is the admission reserve (pipeline workers × 64 KiB), **not** free bytes. `held_back_files` and `held_back_entries` are what stays on disk and is never retried by this process: see [What a database outage does](deployment.md#what-a-database-outage-does).
- `counters` are per process and reset on restart. `retries` and `exhausted` are keyed `"<operation>:<failure class>"`.

### `POST /v1/chat/completions` — success

Requires a bearer token with `query:submit`. Headers: `Authorization: Bearer <harness token>`, `Content-Type: application/json`, and optionally `X-Harness-Device`. See [OpenAI-compatible endpoint](features.md#openai-compatible-endpoint) for what it accepts and what it does not.

```json
{
  "model": "openai/gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a careful code reviewer."},
    {"role": "user", "content": "Review this diff"}
  ],
  "temperature": 0.2
}
```

```json
{
  "id": "chatcmpl-harness-1842",
  "object": "chat.completion",
  "created": 1792569600,
  "model": "openai/gpt-4o",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "..."},
    "logprobs": null,
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908},
  "harness": {"audit_id": 1842, "audit_ref": "3f2a9c1e8b7d4a6f9e0c5d2b1a8f7e63", "pii_redacted": false, "pii_entities_masked": []}
}
```

`200`, with an `X-Harness-Audit-Id: 1842` header. When the audit row was journaled because the database could not take it, `harness.audit_id` is `null`, the header is `X-Harness-Audit-Ref: <write_id>` instead, and `id` is `chatcmpl-harness-ref-<write_id>`; `harness.audit_ref` is present either way. `id` is derived from the audit row's id. `model` is the requested name. `finish_reason` is the upstream's (`stop`, `length`, `content_filter`), or `stop` when it sent none. When the provider reported no prompt/completion split, both are `0` and `total_tokens` is still the reported total; the audit row keeps `null` for the split. `harness` is an extension object that clients which do not know it ignore. `content` is the response as the `code` profile leaves it: not masked, unless `PII_CODE_REDACT_OUTPUT=true`. A flagged request (an injection phrase in an `assistant` or `tool` turn) is answered like this and writes its flag on the row.

**With `V1_TOOLS_ENABLED=true`** the request may also carry `tools`, `tool_choice`, `parallel_tool_calls`, assistant `tool_calls` and `tool` turns. A response whose model proposed tool calls carries the released calls in `message.tool_calls`, `finish_reason: "tool_calls"` when at least one was released, a note in `content` for each denied call, and `harness.actions` with one decision per evaluated call. A text-only response is the body above, byte for byte. The full shape, with a denied `DROP TABLE` as the example, is in [Tool calling](features.md#tool-calling).

### `POST /v1/chat/completions` — streamed

The same request with `"stream": true` (and optionally `"stream_options": {"include_usage": true}`) answers `200` with `Content-Type: text/event-stream`, `Cache-Control: no-cache` and `X-Accel-Buffering: no`, once the upstream call has started:

```
: keep-alive

data: {"id":"chatcmpl-harness-1842","object":"chat.completion.chunk","created":1792569600,"model":"openai/gpt-4o","choices":[{"index":0,"delta":{"role":"assistant","content":"<the whole response>"},"finish_reason":null}]}

data: {"id":"chatcmpl-harness-1842","object":"chat.completion.chunk","created":1792569600,"model":"openai/gpt-4o","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: {"id":"chatcmpl-harness-1842","object":"chat.completion.chunk","created":1792569600,"model":"openai/gpt-4o","choices":[],"usage":{"prompt_tokens":812,"completion_tokens":96,"total_tokens":908}}

data: [DONE]
```

- `: keep-alive` repeats every `V1_SSE_KEEPALIVE_SECONDS` until the pipeline finishes. Clients ignore comment lines.
- The whole response is **one** content chunk, sent only after every check has passed.
- With tool calls released, the content chunk is followed by **one chunk per released call carrying its whole `arguments`**. No chunk carries the `harness` object.
- The usage chunk (empty `choices`) is sent only with `include_usage`.
- There is no `X-Harness-Audit-Id` header: the row does not exist when the headers go out. Every chunk's `id` carries it (the `chatcmpl-harness-ref-<write_id>` form when the row was journaled).
- A block decided before the upstream call (every verdict in the table below) is answered as JSON with its own status, exactly as unstreamed. A failure after the stream started is one `data: {"error": {...}}` event, the same object as below, and the stream ends without `[DONE]`.

### `POST /v1/chat/completions` — errors

Every error has the OpenAI shape plus a `harness` object holding the pipeline response's own fields, where there is one:

```json
{
  "error": {
    "message": "Usage limit reached: tokens 1000412 of 1000000; resets at 2026-10-22T00:00:00Z",
    "type": "permission_error",
    "param": null,
    "code": "usage_limit_exceeded",
    "harness": {"reason": "Usage limit reached", "limit": "tokens", "maximum": 1000000,
                "actual": 1000412, "resets_at": "2026-10-22T00:00:00Z"}
  }
}
```

| Cause | Status | `type` | `code` | Retried by the OpenAI SDK |
|---|---|---|---|---|
| Duplicate within 24 h | `400` | `invalid_request_error` | `duplicate_request` | no |
| Suspicious pattern in a blocking role | `400` | `invalid_request_error` | `suspicious_pattern` | no |
| Conversation over `CONTEXT_MAX_MESSAGES` or `CONTEXT_MAX_CHARACTERS` | `400` | `invalid_request_error` | `context_length_exceeded` | no |
| Over `PII_MAX_CHARACTERS_CODE` | `400` | `invalid_request_error` | `redaction_limit_exceeded` | no |
| Model not permitted for the caller's role | `403` | `permission_error` | `model_not_permitted` | no |
| `ADMIN_TOKEN` used | `403` | `permission_error` | `break_glass_not_permitted` | no |
| Any other missing permission | `403` | `permission_error` | `permission_denied` | no |
| Usage limit (`requests` or `tokens`) | `403` | `permission_error` | `usage_limit_exceeded` | no |
| Bad `messages`: empty, last turn not `user` (or `tool`, with tools on), an image part, a `tool` turn that answers no preceding call, no `user` turn at all, … | `400` | `invalid_request_error` | `invalid_messages` | no |
| A forwarded parameter out of range, `max_tokens` and `max_completion_tokens` disagreeing, or (with tools on) a malformed `tools` item, `tool_choice` or `parallel_tool_calls` | `400` | `invalid_request_error` | `invalid_parameter` | no |
| A parameter not at its only supported value (`n`, `logprobs`, `top_logprobs`, `response_format`, `modalities`, `audio`) | `400` | `invalid_request_error` | `unsupported_parameter` | no |
| Tools, tool turns or assistant `tool_calls` with `V1_TOOLS_ENABLED=false`; `functions` or `function_call` always; with tools on, a model not in `V1_TOOL_MODELS` | `400` | `invalid_request_error` | `tools_not_supported` | no |
| `X-Harness-Device` over 128 characters or not printable | `400` | `invalid_request_error` | `invalid_header` | no |
| Body not JSON, or not the request schema | `400` | `invalid_request_error` | `invalid_request` | no |
| Missing or invalid bearer token | `401` | `authentication_error` | `invalid_api_key` | no |
| Token lacks `query:submit` | `403` | `permission_error` | `permission_denied` | no |
| Upstream timeout, connection error, `5xx` or `429` | `502` | `api_error` | `upstream_unavailable` | **yes** |
| Upstream `4xx`, malformed response, no content, or no OpenRouter key | `502` | `api_error` | `upstream_error` | no |
| The database is unavailable: the identity read, the duplicate check or the usage gate failed, the audit journal is full or has no headroom, or the audit row was neither written nor journaled | `503` | `api_error` | `storage_unavailable` | **yes**, with `Retry-After` |
| A storage failure that is not an outage (a refused statement) in the duplicate check or usage gate, or the action decisions could not be recorded | `500` | `api_error` | `internal_error` | **yes** |
| PII redaction failed | `500` | `api_error` | `redaction_failed` | no |

- **Not retried** means a status the OpenAI SDKs never retry (`400`, `401`, `403`) or, for a `5xx`, the `x-should-retry: false` header, which they read before their status rule. Every non-retryable error carries the header, so the rule is one rule. There is never a `429`.
- `message` is the reason plus its details (`: <pattern>`, `first seen <timestamp>`, `messages 140 > 100`). For an upstream fault it is the harness's own description of the HTTP failure, never the provider's response body.
- A `storage_unavailable` `503` carries `Retry-After` in whole seconds (at least 1) and no `x-should-retry` header, so the SDKs retry it. Like every `/v1` error it has `"harness": null`; the driver's text is never in `message`. A failure after a stream has started is one SSE `error` event, with no `Retry-After` because the headers are already sent. See [What a database outage does](deployment.md#what-a-database-outage-does).
- `param` names the offending field on a `400` from the request's shape, for example `"messages[2].role"`, `"temperature"` or `"tools[2].function.name"`.
- Each pipeline verdict writes the same audit row it writes on `POST /query`, with `ingress='v1'`. A shape refusal (`invalid_*`, `unsupported_parameter`, `tools_not_supported`) runs no pipeline step and writes no row. A retried upstream fault writes one `success=false` row per attempt; such rows are never a prior query for the duplicate check, so the retry is not held as a duplicate.
- A denied tool call is **not** an error: the response is a `200` with the call dropped and a note in `content` (see [Tool calling](features.md#tool-calling)).
- An unknown path under `/v1/` is `404` with `"code": "not_found"`, and a wrong method `405` with `"code": "method_not_allowed"`. Outside `/v1/`, every error keeps its existing FastAPI shape.

### `GET /v1/models` and `GET /v1/models/{id}`

Require a bearer token with `query:submit`. They run no pipeline and write no audit row.

```json
{"object": "list", "data": [
  {"id": "gpt-4", "object": "model", "created": 0, "owned_by": "harness"},
  {"id": "openai/gpt-4o", "object": "model", "created": 0, "owned_by": "openai"}
]}
```

The entries are `MODEL_ALLOWLIST`, in its order. `owned_by` is the part before the first `/`, or `harness`. `created` is `0`, because the harness does not know it. An `admin` may request models outside the list but sees the same list. There is no capability field: `V1_TOOL_MODELS` is how a deployment says which models may use tools. `GET /v1/models/{id}` returns one entry (ids with `/` work as written, e.g. `/v1/models/openai/gpt-4o`), or `404` with `"code": "model_not_found"` for a name not in the list. `ADMIN_TOKEN` is `403 break_glass_not_permitted` on both.

---
