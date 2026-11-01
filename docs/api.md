# API reference

Every request and response shape for `POST /query`, `GET /audit` and `GET /stats`.

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
  "model_used": "gpt-4",
  "tokens_used": 45,
  "pii_redacted": true,
  "pii_entities_masked": ["EMAIL_ADDRESS", "PERSON"]
}
```

OpenRouter received `my name is <PERSON>, my email is <EMAIL_ADDRESS>` — never the raw text. `pii_entities_masked` is the sorted union of entity types masked in the prompt and in the response; when nothing is detected, `pii_redacted` is `false` and the list is empty. Both fields are additive — clients that ignore unknown fields are unaffected, and the two `BLOCKED` shapes below are unchanged (redaction runs only after both checks pass).

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

`session_id` names the conversation a row belonged to, so three rows that were one conversation are visibly one conversation instead of a guess. It is `null` for two whole classes of row: everything written before this release, and every send that carried no session — `POST /query` without the field, which keeps working unchanged. **This is the only place a session reaches an admin.** No endpoint and no console surface exposes a transcript; the auditor learns that rows were related, not what was said in them beyond the previews this endpoint already withholds.

`pattern_role` and `pattern_action` say which message tripped a pattern and what was done about it: `pattern_role` is the role of the message the match was found in (`user`, `tool`, …), and `pattern_action` is `block` or `flag`. Both are `null` on rows with no pattern hit and on every row written before this release. `suspicious_pattern_detected` keeps its meaning — *a pattern matched* — so it is `true` for a flag as well as a block; `pattern_action` is what tells them apart. See [Pattern policy](features.md#pattern-policy).

`profile` names the policy that ran — `chat` for every row `POST /query` and the chat UI write — and the admin console's Register page shows it too. It is `null` on rows written before this release and on `POST /query`'s refusal of a foreign `session_id`. It matters for reading the PII flags: under the `code` profile the response is not analyzed, so `pii_detected_output: false` there means *not looked at*, not *clean*. See [PII redaction](features.md#pii-redaction).

Eight fields describe the request itself (PRD-013):

| Field | Meaning |
|---|---|
| `ingress` | The door the request came through: `query` (`POST /query`), `chat` (the chat UI) or `v1` (the OpenAI-compatible endpoint, once it exists). `null` on a direct call that named none |
| `message_count` | Messages in the conversation as received, before redaction: `1` on `POST /query`, the whole history plus the new turn in the chat |
| `input_tokens` | Prompt tokens the provider reported (`usage.prompt_tokens`). `null` when no upstream call was made or the provider reported no split |
| `output_tokens` | Completion tokens the provider reported (`usage.completion_tokens`), under the same rule. `tokens_used` is unchanged: still the provider's total |
| `streamed` | The response was delivered as a stream. Always `false` until the OpenAI-compatible endpoint exists |
| `has_tool_calls` | The request or response carried tool calls. Always `false` until tool calling exists |
| `conversation_key` | A grouping key for the conversation the row belongs to; see below |
| `limit_exceeded` | `requests` or `tokens` on a [usage-limit refusal](#post-query--blocked-usage-limit); `null` on every other row |

Rows written before PRD-013 return `null` for the six nullable fields and `false` for `streamed` and `has_tool_calls`, which were impossible then. No row is backfilled.

`conversation_key` is a versioned hash of the user, the first `system` message and the first `user` message, over the raw text. An agent resends its whole history on every request, so every turn of one agent conversation carries the same key. It is a grouping aid, not an identity, with three limits:

- **Different conversations can share a key.** Two conversations by one user that open with the same system prompt and the same first instruction share it, and so does every identical `POST /query` prompt by one user.
- **One conversation can change key.** A client that compacts its context and rewrites its first user message starts a new key.
- **In the chat, the key can change mid-session.** Once a long chat drops its oldest exchange to fit the context limits, the first user message sent is a different one. For chat rows, `session_id` is the authoritative grouping.

It is a hash of text this endpoint's reader can already identify through `user_id` and the previews, and it is not reversible. `GET /audit` does not filter on it; the admin console's Register search does.

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
  "blocked_usage_limits": 4
}
```

`input_tokens` and `output_tokens` are sums over every audit row, with a row that recorded no split counted as `0`, so on a deployment upgraded from before PRD-013 they cover only the rows written since. `blocked_usage_limits` counts usage-limit refusals. Those rows are `success=true`, so they count in `success_rate` the way duplicate blocks do. The admin console's Summary shows the same three figures.

`pii_detected_queries` counts audit rows flagged on input **or** output; `top_pii_entities` ranks individual entity types by frequency across rows. Both count what was analyzed: a `code` row's response was not, so it can only be flagged on input. No ingress runs `code` today, so the figures are what they were.

**`blocked_suspicious` counts blocks only.** It used to count every row with a matched pattern, which was the same thing while every hit blocked. A `flag` row matches a pattern without blocking, so counting it would inflate the security figure an admin watches; flags are excluded here and in the admin console's summary. Rows written before this release carry no `pattern_action` and still count — every one of them was a block — so no historical figure moves, and a deployment with no `tool` traffic sees no change at all.

A missing or invalid credential on any endpoint returns `401`. An authenticated identity that lacks the endpoint's required permission (e.g. a `user` role calling `GET /stats`) returns `403` with `{"detail": "Permission denied: stats:read"}`.

---
