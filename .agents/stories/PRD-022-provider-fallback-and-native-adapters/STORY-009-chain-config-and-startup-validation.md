---
id: STORY-009
prd: PRD-022
slug: chain-config-and-startup-validation
title: PROVIDER_CHAINS_FILE loader, settings, and startup validation (trust, capability, catalogue)
type: feature
priority: high
complexity: medium
phase: "3 - Chains and breaker"
status: in-progress
labels: [backend, config, security]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/STORY-009-chain-config-and-startup-validation.plan.md
report: null
commit: null
depends_on: [STORY-004]
blocks: [STORY-011]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-009: Chain configuration and startup validation

## Description

As an operator, I want to declare fallback chains in a strict YAML file and have startup refuse any chain that would leak `internal` traffic to an `external` provider or reach an id I never catalogued, so that a misconfiguration cannot become a data leak.

## Acceptance Criteria

- [ ] Given `PROVIDER_CHAINS_FILE` (default `""`), `PROVIDER_CHAIN_MAX_CANDIDATES` (default 3, 1–5), `PROVIDER_CHAIN_DEADLINE_SECONDS` (default unset → primary's `timeout_seconds`, > 0) and `PROVIDER_MIN_ATTEMPT_SECONDS` (default 5, > 0), when settings load, then they validate per PRD 9.3; a chains file without `PROVIDERS_FILE` is a startup error
- [ ] Given the F3 example, when loaded via `strict_yaml.safe_load`, then it yields an immutable snapshot keyed by `(model, ingress|None)` with ordered candidates carrying `allow_lower_trust` / `capability_scoped`; `chain_for(model, ingress)` returns the `(model, ingress)` match, else the `(model)` match, else `(model,)` alone
- [ ] Given each F3 rule, when violated, then startup fails with an error naming the file, the chain and the entry (format of PRD user story 2): `version` ≠ 1; unknown key; uncatalogued or passthrough-only id; first candidate ≠ `match.model`; repeated id; duplicate match; more than the max candidates; `internal → external` (compared with the **primary**, per entry) without `allow_lower_trust`; a candidate lacking a primary capability (`tools`, `streaming`, `reasoning`, `forced_tool_choice`) without `capability_scoped` — one parametrized test per rule, including T1's internal, internal, external, external chain where only the last opts in
- [ ] Given an entry with `allow_lower_trust: true` that actually crosses, when loaded, then one WARNING names the chain and entry; `allow_lower_trust` on a non-crossing entry is accepted silently
- [ ] Given no chains file, when the app runs, then no chain snapshot exists and `chain_for` returns the model alone (byte-identical to PRD-020)

## Technical Notes

- New `app/services/upstream/chain_config.py`; settings in `app/config.py`; load at startup wherever `provider_registry.load()` runs (after it, since validation resolves ids through the registry). Pattern: `provider_registry.py`'s `_fail`/`_check_keys` error style and `action_config.py`'s strict loader (PRD-016 D13).
- Pure validation over a registry snapshot; the loader is the only I/O. No settings read inside the validation functions (pass values in), so tests build snapshots directly.
- Registry reload: if the registry reloads, chain validation reruns against the new snapshot (follow how `provider_registry.load()`/`reset()` are used; do not invent a reload mechanism).

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-011

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.3, F3, 9.3, D5, D6, T1, User story 2
