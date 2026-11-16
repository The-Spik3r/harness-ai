---
story: STORY-020
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-020-docs-and-promotion.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: f4cf292
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-020: README, docs/features.md, docs/roadmap.md, .env.example; promotion

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-020-docs-and-promotion.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `f4cf292`

## Summary

Action policy rules documented as built and not yet called by `/v1` (PRD-017). Docs only, plus a small `.env.example` presence test. No file under `app/` or `chat_ui/` changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Promotion state verified (PRE-PRD-015 `promoted`, table row, PRD `draft`) | `pre-prds/` | done, no drift |
| 2 | Three settings with comments, Settings order | `.env.example` | done |
| 3 | PRD numbering and stale-ingress fixes | `docs/features.md` | done |
| 4 | New `### Action policy rules` section | `docs/features.md` | done |
| 5 | Features row, section, TOC, Documentation, Roadmap | `README.md` | done |
| 6 | Section rewritten, checkbox stays `[ ]` | `docs/roadmap.md` | done |
| 7 | Settings rows, `GET /audit/actions`, `/stats`, `action_decisions` | `docs/configuration.md`, `docs/api.md`, `docs/deployment.md` | done |
| 8 | PRD-017 hand-off, milestone line | `pre-prds/PRE-PRD-016-tool-calling.md`, `pre-prds/README.md` | done |
| 9 | `.env.example` presence tests (orchestrator Q4: yes) | `tests/test_config.py` | done |
| 10 | Link and anchor check against HEAD baseline | scratchpad script, not committed | 0 new failures |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| `tests/test_config.py` + `tests/test_action_corpus.py` | 774 passed, 1 skipped |
| Link/anchor checker (8 changed docs) | HEAD baseline 2 failures; now 0; 0 new |
| `grep "they are not built yet"` | no hits |
| Full suite | deferred to orchestrator (user decision) |

## Deviations from Plan (orchestrator answers applied)

1. README got its own `## Action policy rules` section (Q1).
2. The two fail-closed SQL gaps (`RELEASE SAVEPOINT`, generic `START TRANSACTION READ WRITE`) are documented as limitations; no code change (Q2).
3. Stale text fixed (Q3):
   - `docs/features.md` `:82`, `:153`, `:220`: PRD numbers corrected (action policy 016, endpoint 015); the claim that `code` has no HTTP ingress is false (`app/routers/v1.py` runs `profile="code"`) and now says `/v1` is its ingress. The flag is still "reachable by tests only" because `/v1` refuses `tool` turns (`app/services/v1_translate.py`).
   - `docs/api.md`: "No ingress runs `code` today" replaced with the `/v1` fact.
   - `docs/roadmap.md`: OpenAI-compatible endpoint moved to Shipped; its section rewritten as shipped (the old open design questions were removed); "The only ingress that exists today is `POST /query`" corrected.
   - `README.md`: Roadmap Shipped/Planned lines corrected; the dead `#openai-compatible-endpoint` anchor now points at `docs/roadmap.md#openai-compatible-endpoint`, the only place describing the endpoint after the README split. `pre-prds/README.md` had the same dead anchor (two links) and was fixed too. `pre-prds/PRE-PRD-014-openai-compatible-endpoint.md:17` has the same dead link; left alone (promoted brief, not in the changed set).
4. `.env.example` presence tests added at the spot the comment near `tests/test_config.py:1342` reserves (two tests, plus that comment's wording updated).
5. AC wording stale: "no pre-existing assertion changed except those STORY-002 and STORY-005 changed". STORY-016 and STORY-019 also changed pinned assertions, each with a PRD-016 comment. This story changed no assertion, only a comment line.
6. No `SECURITY.md` change (Q6).
7. Known gap, not fixed: `docs/configuration.md` has no rows for `V1_ENABLED`, `V1_SSE_KEEPALIVE_SECONDS`, `OPENROUTER_BASE_URL` (pre-existing from PRD-015); the roadmap points at `.env.example` for them.

## Files Changed

`.env.example`, `README.md`, `docs/{features,roadmap,configuration,api,deployment}.md`, `pre-prds/README.md`, `pre-prds/PRE-PRD-016-tool-calling.md`, `tests/test_config.py` (+2 tests, 1 comment), `.agents/` plan/story/index/report bookkeeping. PRD `status: draft` -> `done` lands in the chore commit.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_env_example_documents_the_action_policy_vars_with_a_comment`, `test_env_example_action_policy_defaults_match_settings` |

## Acceptance Criteria

- [x] features.md and README describe the rules as built, not yet called by `/v1`: table, file format, six permissions with a complete `RBAC_ROLES_FILE` example, path rule and OpenCode/Cline setup step, PowerShell and symlink limits, `PATTERNS_FILE` upgrade note
- [x] roadmap section says what is built and what PRD-017 adds; checkbox unticked
- [x] `.env.example` has the three variables with comments (proved by the two new tests)
- [~] Full suite deferred to the orchestrator; targeted tests green; links resolve (0 new failures); AC wording stale, see 5
- [x] PRE-PRD-015 `promoted`, `prd:` correct, table row present; no drift
- [x] Tasks complete; PRD `done` set in the chore commit
