---
story: STORY-015
prd: PRD-020
slug: providers-docs
title: Providers documentation, example registry, .env.example and README
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Providers documentation, example registry, .env.example and README

## Summary

Docs and one test only; no `app/` change. Add `examples/providers.yaml` (PRD F1 verbatim), a "Providers" section in `docs/features.md` whose recipes are complete, loadable registry YAML blocks, edit the `docs/configuration.md` rows, `.env.example`, README and `docs/testing.md`, and add `tests/test_providers_docs.py`, which parses the docs mechanically (no hand-copied lists): setting names against `Settings`, every fenced `yaml` block under the Providers heading through the registry loader via `tests/_providers.py`.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-015-providers-docs.md` (ACs live there)
- PRD sections used: Section 4 (Documentation, Out of Scope), 7 F1, 9.3, 13, 15 (D5, D7, D8, D10, O5, "Not verified")
- Systems affected: docs, `examples/`, `.env.example`, one new test. No app code.

## Design Decisions

- **Recipes are complete registries, not fragments.** Each recipe's fenced `yaml` block carries `version: 1`, `default_model` and one provider, so the loader (the only validator) checks every field and the test needs no merge logic. Only blocks fenced exactly as `yaml` under the `### Providers` heading (until the next `### ` heading) are collected; shell and env snippets there use `bash`.
- **Placeholders, no invented vendor facts.** The hosted cloud recipe uses a placeholder host (`https://llm.example.com/v1`) and `key_env: CLOUD_LLM_API_KEY`. Only LM Studio gets verified quirks (from the STORY-014 report). Ollama, vLLM, llama.cpp server and LocalAI each say "not verified by this repo's E2E (PRD Section 15): check the `usage` and `tool_calls` shapes before relying on them"; the four local recipes default to `usage_missing: estimate`.
- **UI wording.** Any UI-facing string stays inside the copy vocabulary (no "token"; the limit is "estimated length", `chat_ui/chat_ui/copy.py:173`). Docs prose may say token. This story adds no UI string; `tests/test_copy.py` is only read, never edited.
- **No streaming claim.** Say `stream()` / `collect()` exist for PRD-021, nothing streams upstream today, and harness output stays buffered (link `features.md` "No real token streaming").
- **Out of scope, stated in the docs:** Azure OpenAI URL scheme and extra headers (O5), hot reload, health probes, native adapters and fallback (PRD-022; a `type` other than `openai_compatible` is a startup error).

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | `.agents/skills/` holds only `frontend-design`, irrelevant to docs | n/a |

---

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Config row + key warning | `docs/configuration.md:57` | "Whoever controls this host receives `OPENROUTER_API_KEY`" sentence |
| Required column | `docs/configuration.md:13` | Row to change to "Yes, unless `PROVIDERS_FILE` is set and no provider uses it" |
| Legacy-only rows | `docs/configuration.md:24`, `:31`, `:57`, `:61` | Append "Ignored in file mode"; `:61` also "non-empty with `PROVIDERS_FILE` is a startup error"; `:31` "in file mode only the default `timeout_seconds`" |
| .env comment style | `.env.example:80-83` | Comment block above a key, with a warning sentence |
| Feature section style | `docs/features.md:238-262` | Level-3 heading, bold lead-ins, a "does not do" bullet list. Insert `### Providers` before `### Action policy rules` (`:344`) |
| README tables | `README.md:152-160` (Features), `:351-364` (Documentation) | One row each; quickstart `.env` lines at `:239`, `:262` |
| Docs-as-test | `tests/test_admin_copy.py:1-12` | Module docstring stating why the file exists; never touch `tests/test_copy.py` |
| File-mode loading | `tests/_providers.py:35-49` | `providers_file(tmp_path, yaml, monkeypatch=, env=)`; `env` must define every `key_env` |
| Warning assertions | `tests/test_provider_registry.py:312-323` | `caplog.set_level(logging.WARNING, logger=provider_registry.logger.name)` |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `examples/providers.yaml` | CREATE | PRD Section 7 F1 block, verbatim, including its first comment line |
| `docs/features.md` | UPDATE | New `### Providers` section |
| `docs/configuration.md` | UPDATE | `PROVIDERS_FILE` row, `:13`, legacy rows |
| `.env.example` | UPDATE | `PROVIDERS_FILE=` with three-line comment and key warning |
| `README.md` | UPDATE | Providers link and row |
| `docs/testing.md` | UPDATE | `HARNESS_E2E_LOCAL_BASE_URL` / `HARNESS_E2E_LOCAL_MODEL` beside `:34-36`; the `OPENROUTER_API_KEY not found` entry (`:122`) |
| `tests/test_providers_docs.py` | CREATE | Docs check (AC3, AC5) plus content assertions (AC1, AC2, AC4) |

If `docs/api.md` still calls `/query` `model` required, grep `model` there and fix it.

---

## Tasks

Execute in order.

### Task 1: examples/providers.yaml

- **File**: `examples/providers.yaml` (CREATE)
- **Implement**: copy the PRD F1 fenced block (`.agents/PRDs/PRD-020-provider-registry/PRD.md` lines ~279-335) byte for byte.
- **Mirror**: `examples/action_policy.yaml` (location only)
- **Validate**: Task 6.

### Task 2: docs/configuration.md

- **Implement**: add a `PROVIDERS_FILE` row (No, empty; path to the registry YAML, `examples/providers.yaml` is a sample; empty = implicit OpenRouter provider, today's behaviour byte for byte; an invalid file is a startup error in the API and the chat UI; no hot reload; link `features.md#providers`; whoever controls a provider's host receives its key and every prompt). Row `:13` Required becomes `Yes, unless PROVIDERS_FILE is set and no provider uses it`. Append "Ignored in file mode" to `OPENROUTER_BASE_URL`, `MODEL_ALLOWLIST`, `V1_TOOL_MODELS`, and the timeout note on `OPENROUTER_TIMEOUT_SECONDS`. Keep column order.
- **Mirror**: `docs/configuration.md:57`

### Task 3: docs/features.md `### Providers`

Sentence case, no emojis. In this order:
1. **What it is.** No file = one implicit OpenRouter provider, nothing changes (D1). One in-house `openai_compatible` adapter; exact model-id lookup, then at most one `passthrough` provider (D3), never prefix parsing.
2. **The registry file.** Link `examples/providers.yaml`; provider and model fields (PRD Section 4); roles precedence `model.roles` > `provider.roles` > every role (D4); a `roles` typo or `[]` is a startup error.
3. **Bold warning near the top:** whoever controls a provider's host receives its key and every prompt; `base_url` is operator-only. Plaintext rules (D5): `https` always, loopback `http` always, private IP literal `http` only with `insecure_http: true` (RFC 1918 and ULA; `100.64.0.0/10` not included), hostnames over `http` never, redirects not followed, keyless providers send no `Authorization`. **Plaintext LAN warning:** `insecure_http` sends prompts, answers and any key unencrypted, readable by anyone on that network.
4. **What `trust: internal` and `pii: relaxed` claim** (D7): the operator asserts the host is theirs and keeps nothing; the harness cannot verify it. `relaxed` needs `internal`; it skips input redaction and the code size limit only; output redaction is unchanged; each row records it. A public IP literal is refused; an internal hostname warns.
5. **Capabilities and usage.** `tools`, `streaming`, `reasoning`, `max_context_tokens` default off (O6); `reasoning` is informational. A conversation over `max_context_tokens` is refused as a context limit, which the chat UI words "estimated length". `usage_missing: estimate` charges characters / `estimate_chars_per_token` (default 4) as unsplit tokens and sets `usage_estimated` on the row (D8); `error` is the legacy default.
6. **Using it.** `/query` `model` is optional: omitted means `default_model` in file mode and `gpt-4` in legacy mode (D15; code at `app/routers/query.py:31`, `:189`). `openrouter_api_key` keeps its name and means the caller's key for the resolved provider, allowed only where `byok: true`, else a `query:byok:{provider}` forbidden verdict (D10, O8). An unknown or unpermitted model is the same `model not found` 404 on `/v1/models/{id}` (`app/routers/v1.py:525`) and the same denial on `/query` (T3). `GET /v1/models` is filtered per role with a `harness` extension in file mode. The admin Register has a provider column and `GET /audit` returns `provider`.
7. **Recipes**, one sub-heading each, each with a loadable `yaml` block and, if useful, a `bash` line to start the server: Ollama (loopback `:11434`, `usage_missing: estimate`, long `timeout_seconds`, its default context window may truncate silently), vLLM (LAN example with `insecure_http` and `key_env`), LM Studio, llama.cpp server, LocalAI, hosted OpenAI-compatible cloud (`https`, `key_env`, optional `byok`). Verified facts only for LM Studio, copied from `.agents/reports/PRD-020-provider-registry/STORY-014-local-model-e2e.report.md`: tested at `http://localhost:1235/v1` with `google/gemma-4-e4b` (do not claim LM Studio's own default port), keyless, reports real `usage`, `/api/version` not exposed, `/api/v0/models` exposes arch, quantization and state, **rejects the object form of `tool_choice` with HTTP 400 and accepts `"none"`, `"auto"`, `"required"`; the harness answers 502 and does not relay the upstream reason**. Every other server: not verified by this repo (PRD Section 15).
8. **Opt-in E2E** pointer to `testing.md`.
9. **What it does not do** (bullets): native Anthropic, Gemini, Bedrock and fallback (PRD-022); Azure OpenAI URL scheme and extra headers; hot reload (restart to change); health probes; per-provider cost or budgets; BYOK on `/v1` or in the chat UI. One sentence: `stream()`/`collect()` exist for PRD-021, nothing streams upstream today.
- **Mirror**: `docs/features.md:238-262`

### Task 4: .env.example and README

- **Implement**: `.env.example`, after the `OPENROUTER_BASE_URL` block (`:83`): `PROVIDERS_FILE=` directly under a three-line comment (what it is; empty keeps OpenRouter only, as before; file mode ignores `OPENROUTER_BASE_URL`, `MODEL_ALLOWLIST`, `V1_TOOL_MODELS`) and a key-warning line. If the comment at `:1-2` says the key is always required, qualify it. README: a "Providers" row in the Features table, a link `docs/features.md#providers` (also in the Documentation table, `:355`), and one sentence near the quickstart `.env` edit lines (`:239`, `:262`).
- **Mirror**: `.env.example:80-83`, `README.md:158`

### Task 5: docs/testing.md

- **Implement**: after `:36` add the opt-in command (`pytest tests/e2e/test_local_model.py -m e2e --run-e2e -v`) and a paragraph naming `HARNESS_E2E_LOCAL_BASE_URL` and `HARNESS_E2E_LOCAL_MODEL` with their real defaults. Read the defaults, the libSQL variable and the skip reasons from `tests/e2e/_local_model.py`, do not recall them. Skipped, never failed, when no server answers. Add "unless `PROVIDERS_FILE` is set and no provider's `key_env` names it" at `:122`.
- **Mirror**: `docs/testing.md:30-40`

### Task 6: tests/test_providers_docs.py

- **Implement** (docstring: the docs are checked by parsing them, so a renamed setting or a stale recipe fails the suite):
  - helpers: `_section(path, heading)` (from `### Providers` to the next `### `; assert the heading exists, message naming it), `_yaml_blocks(text)` (regex over `yaml` fences), `_key_envs(block)` (load with `yaml.safe_load`, collect every `key_env`), `_documented_settings()` = first-column backticked ALL_CAPS names of `docs/configuration.md` table rows plus `^[A-Z_]+=` keys in `.env.example`.
  - AC5: every documented name is in `Settings.model_fields` (non-empty set, contains `PROVIDERS_FILE`); at least six yaml blocks under Providers; each loads via `providers_file(tmp_path, block, monkeypatch=monkeypatch, env={name: "dummy-not-a-key" ...})`.
  - AC3: `examples/providers.yaml` loads with env for `OPENROUTER_API_KEY` and `VLLM_API_KEY`; with `caplog`, exactly one WARNING record, naming `gpu-box` and plaintext, none for `openrouter` or `ollama` (built-in secret globs cover both key names: `app/services/action_config.py:327-335`). Also assert the three provider names, `default_model`, and that `lan/llama-3.1-70b` is admin-only.
  - AC1: `PROVIDERS_FILE` row exists; the `OPENROUTER_API_KEY` row contains "unless `PROVIDERS_FILE` is set"; the three legacy rows contain "file mode".
  - AC2: the Providers section names the six recipes and contains the host-controls-key warning, "plaintext", `trust: internal`, `pii: relaxed`.
  - AC4: `.env.example` has `PROVIDERS_FILE=` with at least three comment lines above it; README links `docs/features.md#providers`.
- **Mirror**: `tests/test_admin_copy.py:1-12`, `tests/test_provider_registry.py:312-323`, `tests/_providers.py:35-49`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_providers_docs.py`

---

## End-to-End Tests

- [ ] The F1 example loads into a file-mode registry through `providers_file` (no HTTP needed; Task 6).
- [ ] No `chat_ui/` change, so no UI pass. Reread the prose once for "token" in any sentence that quotes UI copy.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_providers_docs.py tests/test_provider_registry.py tests/test_config.py tests/test_copy.py tests/test_admin_copy.py tests/test_untouched_app.py
```

`test_untouched_app.py` is a guard only; no `app/` file changes. Full suite: GitHub CI on push.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 configuration.md rows | 2 | `tests/test_providers_docs.py::test_configuration_rows_state_file_mode` |
| AC2 Providers section | 3 | `::test_providers_section_has_recipes_and_warnings` |
| AC3 example validates, one WARNING | 1 | `::test_example_registry_loads_with_only_the_insecure_http_warning` |
| AC4 .env.example and README | 4 | `::test_env_example_and_readme_point_at_providers` |
| AC5 parsed checks | 2, 3, 6 | `::test_documented_settings_exist_in_config`, `::test_every_recipe_block_loads_through_the_registry` |

Plus: all tasks done, validation passes, LM Studio quirks copied from the STORY-014 report and no other server's behaviour asserted.

## Risks

- A recipe fails a loader rule (for example an unset `key_env`): the test supplies dummy env values; fix the recipe, never the loader.
- Heading-based parsing breaks on a rename: the test asserts the heading first.
- The `/query` default drifts: docs use D15 wording, code cited above.
