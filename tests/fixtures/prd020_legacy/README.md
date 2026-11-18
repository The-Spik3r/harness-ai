# PRD-020 legacy byte-identical fixtures

Purpose: PRD-020 D1 ("no file, no change") and risk 1. Without `PROVIDERS_FILE`,
every byte the harness sends upstream and returns to clients is today's. These
files pin those bytes as recorded by PRD-020 STORY-001, against the unchanged
`app/`. They are replayed by `tests/test_prd020_legacy_fixtures.py`.

## Layout

- `upstream/<case>.request.json` and `<case>.meta.json`: the request
  `call_openrouter` sends (payload, `Authorization`, `Content-Type`, method,
  URL path), captured through `httpx.MockTransport`.
- `errors.json`: `OpenRouterError` message, `upstream_status` and `retryable`
  per failure case. `results.json`: the success `OpenRouterResult` fields.
- `v1/`: raw bodies of `GET /v1/models`, `/v1/models/openai/gpt-4o` and the
  missing-model 404, as an admin and as a user; `meta.json` holds statuses and
  `x-should-retry`.
- `query/`: raw `POST /query` bodies (success, default model, BYOK, blocked
  `query:model:<m>` and `query:byok`, admin off-list model), the upstream request
  of each case, and `meta.json`.

## Pinned inputs

`OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`, `OPENROUTER_API_KEY=test-key`,
`MODEL_ALLOWLIST` and `V1_TOOL_MODELS` at their defaults, `PII_REDACTION_ENABLED`
off (the prompts carry no PII). All by monkeypatch; nothing persists.

## How it compares

- Upstream request bodies: parsed with `json.loads(..., object_pairs_hook=list)`
  and compared as nested ordered pairs, so key order, values and types are
  pinned while httpx's whitespace and escaping (httpx is unpinned) are not.
  Headers: `Authorization`, `Content-Type`, method and URL path, exactly.
- `/v1/models*` and `/query` responses: raw `response.content` bytes.
- Error messages built from an httpx exception carry httpx's own wording, so for
  those cases only the harness prefix, status, `retryable` and the URL are pinned.

## Normalization

Only two values vary per run and are replaced before writing and comparing, in
`/query` success bodies: `audit_id` (an integer) becomes `<AUDIT_ID>` and
`audit_ref` (a UUID) becomes `<AUDIT_REF>`. Nothing else is normalized:
`/v1/models` `created` is the constant `0`, payloads carry no ids or timestamps,
and error strings are deterministic under the pinned base URL.

## Recording

`PRD020_RECORD_FIXTURES=1 pytest tests/test_prd020_legacy_fixtures.py` writes the
files. It was run once, for STORY-001, with `app/` unchanged (`git diff main -- app/`
was empty). A later story must never run it.

## The rule

Later stories (STORY-005 adapter, 007 routing, 011 `/v1/models`, 012 `/query`
default model) keep this suite green without editing a fixture. A failing
fixture is a legacy regression to report, never a stale file.
