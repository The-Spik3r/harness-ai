---
story: STORY-018
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-018-docs-and-promotion.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: a990e96
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report — STORY-018: README, docs/features.md, docs/roadmap.md, .env.example; brief promotion verified

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-018-docs-and-promotion.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `a990e96`

## Summary

Tool calling on `/v1` is documented as shipped behind `V1_TOOLS_ENABLED` (default off), written from the code and the two E2E runs as built, including the run's amendments (shape rule 4, the mark-failed step of D8, the text-only response rule, `null` handling, the flag-on legacy-API message). `docs/features.md` has a new `### Tool calling` section with `#### Setting up OpenCode` and `#### Setting up Cline`; every "not yet called" statement in `features.md`, `README.md`, `docs/roadmap.md`, `docs/api.md`, `docs/configuration.md`, `docs/deployment.md` and `.env.example` was reworded; `.env.example` gained `V1_TOOLS_ENABLED` and `V1_TOOL_MODELS` with two presence tests; the stale "Nothing reads these yet" comment in `app/config.py` was reworded (comment only); Milestone 2 is marked reached. The brief's promotion was re-verified, no drift.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Link checker baseline (0 failures at HEAD) | scratchpad `linkcheck018.py` (not committed) | done |
| 2 | Two settings and action-policy header | `.env.example` | done |
| 3 | Two `.env.example` tests; section comment updated | `tests/test_config.py` | done |
| 4 | `### Tool calling`, OpenCode and Cline setup | `docs/features.md` | done |
| 5 | De-stale Action policy, pattern and PII sections | `docs/features.md` | done |
| 6 | Features rows, `## Tool calling` section, TOC, Architecture sentence, Action policy section, Roadmap | `README.md` | done |
| 7 | Shipped items, `Tool calling (PRD-017)` paragraph, MCP bullet, "Built ... called by `/v1`", "What PRD-017 added" | `docs/roadmap.md` | done |
| 8 | `ingress`, `has_tool_calls`; two settings rows; `action_decisions` paragraph | `docs/api.md`, `docs/configuration.md`, `docs/deployment.md` | done |
| 9 | Promotion verified; Milestone 2 and PRD-016 line | `pre-prds/README.md`, `pre-prds/PRE-PRD-016-tool-calling.md` (verified only) | done |
| 10 | Link and anchor check | scratchpad | done |
| 11 | Targeted validation | n/a | done |
| 12 | Stale comment (orchestrator addition) | `app/config.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| Tests | 230 passed (`tests/test_config.py`: 221, including the 2 new; `tests/test_untouched_app.py`: 9), 0 failed, 0 skipped |
| Link/anchor check over the 8 docs | baseline 0 failures at HEAD; working tree 0 failures; 0 NEW, 0 pre-existing, 0 fixed. Sanity-checked: a deliberately broken anchor appended to the README was reported as NEW, then reverted |
| Stale-text grep (`not yet called`, `until tool calling exists`, `reachable by tests only`, `stays unticked`, `once it exists`, `nothing writes it yet`, `PRD-014 will add`) over README, docs, `.env.example` | no hits |
| Full suite | deferred to orchestrator (user decision) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `docs/features.md` | UPDATE | +171/-9 |
| `README.md` | UPDATE | +39/-10 |
| `docs/roadmap.md` | UPDATE | +9/-8 |
| `docs/configuration.md` | UPDATE | +4/-2 |
| `docs/api.md` | UPDATE | +2/-2 |
| `docs/deployment.md` | UPDATE | +1/-1 |
| `.env.example` | UPDATE | +15/-1 |
| `pre-prds/README.md` | UPDATE | +2/-2 |
| `tests/test_config.py` | UPDATE | +27/-2 (two comment lines removed, no assertion) |
| `app/config.py` | UPDATE | +4/-2 (comment only) |

## Deviations from Plan

- **Orchestrator addition:** the "Nothing reads these yet" comment before the PRD-016 Action policy settings in `app/config.py` was reworded to say `action_config.load()` reads them at startup (PRD-016 STORY-006/007/008) and that `/v1` calls the engine under the flag (PRD-017 STORY-010). The plan had said to leave it. The sibling comment before the PRD-015 V1 settings (same words, "Nothing reads these yet") was left, as it was outside the requested scope; flagged for the orchestrator.
- Roadmap: the Action policy item was moved to Shipped as `[x]` (plan default Q2). `docs/configuration.md` still has no rows for `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, `OPENROUTER_BASE_URL` (pre-existing gap; only the two tool rows were added, Q1).
- The benchmark command in the docs is `pytest tests/test_tool_calling_criteria.py -m benchmark --run-benchmark` (the marker and flag were checked in `tests/conftest.py` and the test file).
- `pre-prds/PRE-PRD-016-tool-calling.md` is unchanged: `status: promoted`, `prd:` correct. Its body describes the state at the time of the brief (historical).
- Not changed: `chat_ui/`, `SECURITY.md`, `docs/testing.md`, `tests/e2e/scripts/README.md`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_env_example_documents_the_tool_vars_with_a_comment`, `test_env_example_tool_defaults_match_settings` (defaults and Settings order: after `V1_SSE_KEEPALIVE_SECONDS`, before `ACTION_POLICY_FILE`) |

## Acceptance Criteria

- [x] `docs/features.md` has a Tool calling section (flag, `V1_TOOL_MODELS`, order of steps, per-check tool-content table, denial note and `finish_reason` rule, `harness.actions`, buffered deltas, dedup rule, limits); the Action policy rules section no longer says nothing calls the engine
- [x] README and `docs/features.md` give per-client setup for OpenCode and Cline from the E2E runs (provider config, model name, workspace root, `shell.allow`, the Cline `tools:` mapping and `opaque_tools`)
- [x] `docs/roadmap.md`: the "Not yet" paragraph and "What PRD-017 adds" describe what shipped; Action policy is ticked (moved to Shipped)
- [x] `.env.example` has `V1_TOOLS_ENABLED` and `V1_TOOL_MODELS` with comments in the existing style (proved by the two new tests)
- [x] Brief is `status: promoted` with `prd:` pointing at PRD-017, the track table links PRD-017, Milestone 2 is marked reached; every relative link in the changed docs resolves (link check, 0 failures)
