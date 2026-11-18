---
id: STORY-015
prd: PRD-020
slug: providers-docs
title: Providers documentation, example registry, .env.example and README
type: technical
priority: medium
complexity: medium
phase: "4 - Streaming interface, E2E, docs"
status: done
labels: [docs, config]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-015-providers-docs.plan.md
report: .agents/reports/PRD-020-provider-registry/STORY-015-providers-docs.report.md
commit: d35cbc6
depends_on: [STORY-010, STORY-012, STORY-014]
blocks: []
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-015: Providers documentation, example registry, .env.example and README

## Description

As a platform operator, I want the registry documented with copy-paste recipes and a tested example file, so that I can add a local or hosted provider without reading the code and without a misconfiguration leaking a key.

## Acceptance Criteria

- [ ] Given `docs/configuration.md`, when read, then it has a `PROVIDERS_FILE` row and `OPENROUTER_API_KEY` reads "Yes, unless `PROVIDERS_FILE` is set and no provider uses it", and the legacy-only settings (`OPENROUTER_BASE_URL`, `MODEL_ALLOWLIST`, `V1_TOOL_MODELS`) say they are ignored in file mode.
- [ ] Given `docs/features.md`, when read, then a "Providers" section has recipes for Ollama, vLLM, LM Studio, the llama.cpp server, LocalAI and a hosted OpenAI-compatible cloud, with the warning that whoever controls a provider's host receives its key and every prompt, the plaintext-LAN warning, and a statement of what `trust: internal` / `pii: relaxed` claim.
- [ ] Given `examples/providers.yaml` (the F1 example), when a test loads it with the registry through `tests/_providers.py`, then it validates with the expected WARNINGs for the `insecure_http` provider only.
- [ ] Given `.env.example` and the README, when read, then `PROVIDERS_FILE=` appears with a three-line comment and the key warning, and the README links the Providers section.
- [ ] Given the docs, when checked by a test, then every documented setting name exists in `app/config.py` and every provider field in a recipe is accepted by the loader.

## Technical Notes

- `docs/configuration.md:13` is the `OPENROUTER_API_KEY` row ("Yes"), `:57` the `OPENROUTER_BASE_URL` row with the whoever-controls-this-host warning to mirror. `.env.example:2` and the key comment near `:82`. README setup lines `README.md:239`, `:262`.
- `docs/features.md` has no Providers section yet: add one, with the recipes' known per-server quirks recorded from the STORY-014 E2E report, not from memory (section 15: usage and `tool_calls` shapes are unverified per server).
- `examples/providers.yaml` is the section 7 F1 example verbatim; its test lives with the registry tests and runs in the default suite.
- Docs-as-test precedent: `tests/test_admin_copy.py`, `tests/test_copy.py` (existing doc/copy guards); keep prose in sentence case, no emojis.
- Out of scope per section 4: Azure OpenAI URL scheme and extra headers (O5), hot reload, health probes.

## Dependencies

- **Blocked by**: STORY-010, STORY-012, STORY-014
- **Blocks**: None

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Documentation), 9.3, 13
