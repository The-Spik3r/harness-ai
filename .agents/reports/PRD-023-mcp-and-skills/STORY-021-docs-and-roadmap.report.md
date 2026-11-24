---
story: STORY-021
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-021-docs-and-roadmap.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-24
---

# Implementation Report — STORY-021: Docs for the MCP gateway and skills

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-021-docs-and-roadmap.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `pending`

## Summary

Documentation written from the code's reality: a `### MCP gateway and skills` section in `docs/features.md` (topology, configuration with the nine settings and the code's defaults, skills, how a call is decided, correlation described as correlation not proof, per-client setup for OpenCode 2.3.2 and Cline 3.0.74, operating it, and a "what it does not cover" list re-checked against the code), README feature row, TOC and section, roadmap item ticked, `docs/configuration.md` rows, `docs/api.md` entries. Every "the harness never executes tools" sentence was reworded; rule counts fixed (26 rules, eleven non-grantable, `tool.not_in_skill` row added). A docs test pins settings, counts, the reworded sentence and every relative link and anchor. This is the last story: PRD status set to `done`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | MCP section, rule counts, reworded sentences | `docs/features.md` | done |
| 2 | Roadmap item shipped, open items listed | `docs/roadmap.md` | done |
| 3 | Feature row, TOC, section, roadmap wording | `README.md` | done |
| 4 | Nine setting rows; `POST /mcp`, `GET /skills`, audit filters | `docs/configuration.md`, `docs/api.md` | done |
| 5 | Docstring "ten" -> "eleven" (comment only) | `app/services/action_config.py` | done |
| 6 | Docs tests | `tests/test_mcp_docs.py` | done |
| 7 | PRD `status: done`, index regenerated | PRD.md, index.md | done (chore commit) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 273 passed (test_mcp_docs, test_providers_docs, test_action_config, test_caddyfile_routes, test_untouched_app) + 1 passed (test_mcp_config -k examples_load) |
| E2E | none driven (docs only); opt-in client E2E not rerun |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- More "never executes" sentences existed than the plan listed (features.md :777, README :160); all reworded, and the test matches `never executes (a|any)? tools?`.
- `requires` is a startup check (a role holding a skill must hold its `requires`), not a visibility filter: documented as the code does it.
- The OpenCode JSON follows `tests/e2e/_mcp.py` (`mcp.servers.harness`, `codemode` inside the entry), not the plan's sketch.
- The first run of the link test caught one broken link of my own (an anchor to a bold paragraph); fixed in the doc. No link that existed before this story was broken.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_mcp_docs.py` | settings documented (defaults equal the code's), rule counts (features, roadmap), never-executes reworded, relative links resolve (5 files), checker not vacuous, MCP section substance |

## Acceptance Criteria

- [x] AC1 features section: `test_features_mcp_section_substance`
- [x] AC2 roadmap ticked, sentence reworded: `test_never_executes_sentence_reworded`, `test_rule_counts_match_the_engine`
- [x] AC3 README + `.env.example` nine settings, `examples/mcp.yaml` loaded: `test_mcp_settings_documented`, `test_examples_load`
- [x] AC4 every docs link resolves: `test_relative_links_resolve`
