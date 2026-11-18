---
id: STORY-003
prd: PRD-020
slug: registry-loader-and-validation
title: Provider registry loader, validation and the legacy implicit provider
type: feature
priority: high
complexity: large
phase: "1 - Registry and legacy equivalence"
status: in-progress
labels: [backend, config, security]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/STORY-003-registry-loader-and-validation.plan.md
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-004, STORY-005]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-003: Provider registry loader, validation and the legacy implicit provider

## Description

As a platform operator, I want `PROVIDERS_FILE` parsed and validated at startup into an immutable registry, with a startup error for every misconfiguration, so that a bad provider, key or URL fails the boot and never a request.

## Acceptance Criteria

- [ ] Given a registry YAML with every F1 field, when `provider_registry.load()` runs, then frozen dataclasses expose each provider and model with its documented default (`label`=name, `trust=external`, `pii=standard`, `byok=false`, `passthrough=false`, `usage_missing=estimate`, `estimate_chars_per_token=4`, `timeout_seconds`=`OPENROUTER_TIMEOUT_SECONDS`, model `upstream`=id, capabilities all false/unset), and the snapshot cannot be mutated.
- [ ] Given each F1 startup error (unknown key at any level; missing `name`/`type`/`base_url`/`models`; `version` != 1; duplicate provider name or model id; more than one `passthrough`; `default_model` neither catalogued nor passthrough-routable; `type` != `openai_compatible` naming PRD-022; bad `base_url`; unset/empty `key_env`; `pii: relaxed` without internal; internal on a public IP literal; `byok` unusable; `max_context_tokens` < 1; `estimate_chars_per_token` outside (0, 8]; `timeout_seconds` <= 0), when `load()` runs, then each raises a startup error that names the file, the provider or model and the rule, and a test per error asserts the message contains neither a key value nor a whole URL.
- [ ] Given `base_url` values, when validated, then `https://<any>` and loopback `http://` pass; `http://` on a private IP literal (10/8, 172.16/12, 192.168/16, fc00::/7) passes only with `insecure_http: true`; `http://` on a hostname or a public IP is refused even with it.
- [ ] Given the three F1 WARNING conditions (an `insecure_http` provider, `trust: internal` on a hostname, a `key_env` not matched by the action policy's `secrets.env` globs), when `load()` runs, then each logs one WARNING (caplog) naming scheme+host or the variable name, never the key, and does not fail startup.
- [ ] Given `PROVIDERS_FILE` empty, when the accessors are used, then the legacy implicit provider (section 6.2: `openrouter`, label `OpenRouter`, `passthrough: true`, `usage_missing: error`, `byok: true`, one model per `MODEL_ALLOWLIST` entry with `tools` from `V1_TOOL_MODELS`) is derived from the live settings (OD1), and `load()` is called after `action_config.load()` in both lifespans.
- [ ] Given the shared fixture `tests/_providers.py`, when a test writes a registry YAML to `tmp_path` through it, then the registry is loaded for the test and legacy mode is restored afterwards, including when the test fails.

## Technical Notes

- New module `app/services/provider_registry.py`, YAML through `app/services/strict_yaml.py:62` (`safe_load`, duplicate keys refused by `_StrictSafeLoader` at `:31-34`), the `PATTERNS_FILE` / `ACTION_POLICY_FILE` shape. Pure after `load()`: no I/O in `resolve`/accessors.
- Startup wiring: `app/main.py:17-24` lifespan (`action_config.load()` at `:23`; add `provider_registry.load()` after it and before `authz.check_bootstrap()`), and the Reflex process `chat_ui/chat_ui/chat_ui.py:267` (`app.register_lifespan_task(action_config.load)`; add the registry task after it, `:272` is `authz.check_bootstrap`). app.main's lifespan never fires under Reflex (`chat_ui.py:241-246` comment).
- D5 base-URL rule extends today's validator: loopback hosts `_LOOPBACK_HOSTS` at `app/config.py:97`, validator `:513-555` (messages quote scheme and host only, `:550-551`); reuse the host parsing, do not loosen the setting's own rule. Use `ipaddress` for literals; CGNAT `100.64.0.0/10` is not private for this purpose (O4).
- The `secrets.env` WARNING compares `key_env` with the built-in globs `_BUILT_IN_SECRET_ENV` at `app/services/action_config.py:327-335` (and the loaded policy's own list); this is why `load()` runs after `action_config.load()`.
- Orchestrator decision (stories): legacy mode reads settings LIVE. The suite monkeypatches `settings.MODEL_ALLOWLIST`, `V1_TOOL_MODELS` and `OPENROUTER_*` per test (~53 references). The immutable snapshot exists only in file mode; in legacy mode the accessors derive the implicit provider from the current settings on each call (memoizing on those settings values is allowed).
- Orchestrator decision (stories): "CI runs the suite once with a `PROVIDERS_FILE` fixture" means file-mode tests use the shared `tests/_providers.py` fixture inside the one existing CI job. There is no second full-suite CI job; the existing suite pins legacy behaviour through settings.
- Orchestrator decision (stories): `key_env` is resolved from `os.environ`, then from the dotenv file pydantic-settings reads (`app/config.py:176-177`, `env_file=".env"`), so a key in `.env` works as `OPENROUTER_API_KEY` does today. In legacy mode the key is `settings.OPENROUTER_API_KEY` read at call time (today's message for a missing key unchanged). Key values are never in a repr, log or error. The resolved key is held outside any dataclass `repr` (`field(repr=False)`) and outside the snapshot's `__eq__`.
- `tests/_providers.py` is the one file-mode entry point for stories 004-014 (a context manager/fixture such as `providers_file(tmp_path, yaml_text)`); it must reset the registry and any memoized legacy state in teardown. Starting the catalogue from the legacy builder is the only path that reads `settings.MODEL_ALLOWLIST`/`V1_TOOL_MODELS`/`OPENROUTER_*`.
- Open-decision note: O3 allows `trust: internal` on hostnames with a WARNING; O4 limits `insecure_http` ranges to RFC 1918 and ULA.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-004, STORY-005

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Registry), 6.2, 7 F1, F3, 9.2 T1, T2, T4, T11; decisions D1, D2, D5, D7
