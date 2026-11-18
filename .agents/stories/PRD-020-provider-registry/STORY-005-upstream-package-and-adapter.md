---
id: STORY-005
prd: PRD-020
slug: upstream-package-and-adapter
title: Upstream package, OpenAI-compatible adapter and call_upstream
type: technical
priority: high
complexity: large
phase: "2 - Adapter and routing"
status: done
labels: [backend, refactor]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-005-upstream-package-and-adapter.plan.md
report: .agents/reports/PRD-020-provider-registry/STORY-005-upstream-package-and-adapter.report.md
commit: null
depends_on: [STORY-001, STORY-003]
blocks: [STORY-007, STORY-009, STORY-013]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-005: Upstream package, OpenAI-compatible adapter and call_upstream

## Description

As a platform operator, I want the upstream call parameterized by provider (base URL, key, label, timeout), so that each request goes to its model's provider with that provider's key and nothing else.

## Acceptance Criteria

- [ ] Given the STORY-001 fixtures, when `call_upstream` replaces `call_openrouter` as the pipeline's default and `openrouter_client.py` becomes an alias-only shim, then every fixture passes unedited and every existing import (`call_openrouter`, `OpenRouterError`, `OpenRouterResult`, `GenerationParams`, `ToolParams`, `UnsupportedParameterError`) and injected stub keeps working.
- [ ] Given two stubs in one process (a keyed `openrouter`, a keyless `local`) and two keys in the environment, when `call_upstream` is called for a model of each, then each stub logs the expected `auth=yes|no`, each stub receives only its own key (cross-checked), the `local` request has no `Authorization` header, and a test proves no header value is ever written to the stub log.
- [ ] Given a provider `base_url` and `timeout_seconds`, when the adapter builds its client, then it is `httpx.Client(timeout=provider.timeout_seconds, follow_redirects=False)`, and a stub reply of `302` becomes a non-retryable `UpstreamError` that is not followed.
- [ ] Given the file-mode provider label `Local`, when the upstream fails, returns a malformed body or no text, then each error string is prefixed `Local ...`; the implicit legacy provider keeps `OpenRouter ...` byte for byte.
- [ ] Given a BYOK key, when `call_upstream` chooses the key (D10), then the caller's key is used only for a provider with `byok: true` and otherwise the provider's own key, and a missing key on a keyed provider raises today's message in legacy mode.

## Technical Notes

- Package layout (section 6.5): `app/services/upstream/__init__.py` (`call_upstream`, `UpstreamError`, `UpstreamResult`), `upstream/params.py` (`GenerationParams`, `ToolParams`, `UnsupportedParameterError` moved unchanged from `openrouter_client.py:11-117`), `upstream/openai_compatible.py` (`OpenAICompatibleAdapter.complete` = the body of `call_openrouter`, `openrouter_client.py:219-345`, parameterized by provider). `call_openrouter = call_upstream` and `OpenRouterError = UpstreamError` aliases in the shim.
- Signature stays `call_openrouter`'s: `(messages, model=..., api_key=None, params=None, client=None, *, tools=None)` (`openrouter_client.py:219-227`). Key resolution today: `api_key or settings.OPENROUTER_API_KEY` at `:235`, Bearer header `:241-244`, client `:265` (no `follow_redirects` argument today), URL per call `:268`, error classification `_classify_http_error` `:188-199`.
- No D8 estimate here (STORY-009: `usage_missing` handling keeps today's error at `:311-316`) and no `stream()` (STORY-013).
- Stub: `scripts/stub_openrouter.py` takes `"usage": null` in a reply (omit the key; `_parse_usage` `:246-261` and `_parse_reply` `:316-326` today reject non-objects), its log line (`:465-469`) gains `auth=yes|no` (presence only; `Authorization` is never logged, see the header note `:69-70`), and a redirect reply (e.g. `fail_status: 302` with a `Location`) if the existing `fail_status` cannot express it (`_send_error_body` `:429`). `make_server` binds the script per server (`:511-530`), so two stubs stay apart.
- Orchestrator decision (stories): legacy mode reads settings LIVE. The suite monkeypatches `settings.MODEL_ALLOWLIST`, `V1_TOOL_MODELS` and `OPENROUTER_*` per test (~53 references). The immutable snapshot exists only in file mode; in legacy mode the accessors derive the implicit provider from the current settings on each call (memoizing on those settings values is allowed).
- Orchestrator decision (stories): `key_env` is resolved from `os.environ`, then from the dotenv file pydantic-settings reads (`app/config.py:176-177`, `env_file=".env"`), so a key in `.env` works as `OPENROUTER_API_KEY` does today. In legacy mode the key is `settings.OPENROUTER_API_KEY` read at call time (today's message for a missing key unchanged). Key values are never in a repr, log or error.
- `/v1` wraps the call in `_Upstream` (`app/routers/v1.py:140-171`, looked up at call time as `call_openrouter`); keep that module-level name resolving so `monkeypatch.setattr("app.routers.v1.call_openrouter", ...)` still works.
- Provider-specific HTTP failure text follows `OpenRouter request failed: {exc}` (`:274-275`) with the label substituted; do not include the URL in new messages beyond what `httpx` already puts in `{exc}` for the legacy label.

## Dependencies

- **Blocked by**: STORY-001, STORY-003
- **Blocks**: STORY-007, STORY-009, STORY-013

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Adapter), 6.4, 6.5, 7 F3, F6, 9.2 T1, T6, T7; decisions D2, D5, D10, D12
