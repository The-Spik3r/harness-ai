---
story: STORY-004
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-004-settings-and-rbac.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: d9beeb7
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-004: MCP settings and RBAC vocabulary

## Summary

Nine `MCP_*` settings with validators and a normalizing `mcp_allowed_origins` property in `app/config.py`; `mcp:connect` (held by built-in `admin` and `user`) and the dynamic `skill:<id>` family (accepted by `load()` through `re.fullmatch`) in `app/services/authz.py`; the nine settings documented in `.env.example`. Nothing reads the new settings yet.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `PERMISSION_MCP_CONNECT`, `MCP_PERMISSIONS`, `is_skill_permission`, `load()` skill check, built-in matrix | `app/services/authz.py` | done |
| 2 | Nine settings, six int validators, origin validator + normalizer + property | `app/config.py` | done |
| 3 | Nine documented vars | `.env.example` | done |
| 4 | Tests | `tests/test_authz.py`, `tests/test_config.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 1142 passed, 1 skipped (test_authz, test_config, test_rbac, test_action_corpus, test_query_pipeline_break_glass, test_untouched_app, test_audit_characterization, test_main) |
| E2E | 2/2 (app imports with `/mcp` absent; `load()` of a roles file granting `skill:open-pull-request` makes `holds()` True for that role, covered by `test_load_accepts_a_well_formed_skill_permission`) |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

None. Orchestrator decisions applied: default ports dropped in origin normalization (documented in the validator docstring and `.env.example`); `re.fullmatch`; existing test names kept. Also re-ran `test_audit_characterization.py` and `test_main.py` (frozen matrix copy and `/me` style checks): unchanged and passing. No other test asserts on the built-in matrix or `_KNOWN_PERMISSIONS`.

## Tests Written / Modified

- `tests/test_authz.py`: modified `test_admin_matrix_matches_prd_exactly`, `test_user_matrix_matches_prd_exactly`, `test_known_permissions_are_the_original_five_plus_the_six` (13 to 14), each with a PRD-023 O1 comment. New: mcp:connect membership, no built-in `skill:*`, no skill literal in the known set, load accepts/refuses skill ids (naming file, role, rule), old unknown message kept, `holds()` False for skills under RBAC on/off, `authorize()` bypass documented, non-string guard, source scan that no `authorize(` call names a skill.
- `tests/test_config.py`: defaults, `MCP_ENABLED` parse, out-of-range and bound cases per int setting, origin normalization and refusals, `.env.example` comment + order.

## Acceptance Criteria

- [x] AC1 nine settings, defaults, bounds (test_config MCP block)
- [x] AC2 `skill:` accepted / refused naming file, role, rule (test_authz)
- [x] AC3 built-in matrix and known set (updated matrix tests + new tests)
- [x] AC4 `.env.example` documents the nine (test_config)
