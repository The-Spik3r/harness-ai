---
id: STORY-018
prd: PRD-022
slug: docs-examples-latency
title: Docs, example chains/providers files, latency check, PRD done
type: technical
priority: medium
complexity: small
phase: "4 - Observability, streaming, docs"
status: todo
labels: [docs]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-016, STORY-017]
blocks: []
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-018: Docs, examples, latency check

## Description

As an operator, I want the docs and example files to show how to declare an Anthropic provider and a fallback chain, what the new audit columns and endpoints mean, and what the failure semantics are, so that I can deploy this without reading the code.

## Acceptance Criteria

- [ ] Given `examples/`, when read, then a chains file (F3's example, valid against a matching providers example with an `anthropic-direct` provider) exists and a test loads both through the real loaders
- [ ] Given `docs/features.md`, `docs/api.md`, `docs/deployment.md`, when read, then they cover: `type: anthropic` and its fields/capabilities, the chain file and its rules (trust, capability, BYOK), fallback eligibility (6.2), the breaker (per process), `/providers/status`, the `/stats` figures, the new audit columns and `?request_id=`, `/v1`'s `X-Harness-Provider`/`harness.provider`/`attempts` and `retry-after` on exhaustion, the non-leading system-turn caveat, and the four settings; every example in them was run
- [ ] Given `scripts/measure_v1_latency.py`, when run with no chain file, then p95 overhead stays < 0.5 ms versus the PRD-021 baseline, and the numbers go in the report
- [ ] Given the last story, when committed, then the PRD frontmatter is `status: done`, every story is `done`, and `gen_index.py` prints `errors: none`

## Technical Notes

- Existing doc style: `docs/features.md` (PRD-020/021 sections), `docs/api.md`, `docs/deployment.md`; `docs/roadmap.md:32` names the single-upstream gap — update it.
- Record the "Not verified" items STORY-001 could not verify offline as documented limitations.

## Dependencies

- **Blocked by**: STORY-016, STORY-017
- **Blocks**: None

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.8 (docs), 11 (quality indicators), Phase 4
