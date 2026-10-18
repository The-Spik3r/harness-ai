---
story: STORY-007
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-007-usage-settings.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 2a26cfd
status: COMPLETE
completed: 2026-10-18
---

# Implementation Report — STORY-007: Limit and break-glass settings with startup validators

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-007-usage-settings.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `2a26cfd` (plan committed separately as `2702186`)

## Summary

`app/config.py` gains four settings in a PRD-013 group after the PRD-012 block:

| Setting | Default |
|---------|---------|
| `USAGE_LIMITS_ENABLED` | `True` |
| `USAGE_DAILY_TOKEN_BUDGET` | `"*=1000000"` |
| `USAGE_REQUESTS_PER_MINUTE` | `"*=60"` |
| `BREAK_GLASS_INGRESSES` | `"query,chat"` |

It also gains validators for them and three parsed properties:

- `usage_daily_token_budget_map: dict[str, Optional[int]]`
- `usage_requests_per_minute_map: dict[str, Optional[int]]`
- `break_glass_ingresses: frozenset[str]`

Both limit maps go through one module-level parser, `_parse_limit_map(setting, value)`. The field validator calls it so a bad value stops `Settings()`. Each property calls it again for the dict. Every error message names the setting, quotes the offending entry and shows that setting's own example from `_LIMIT_MAP_EXAMPLES`. `0` also names `USAGE_LIMITS_ENABLED=false` as the real way to turn limits off.

`BREAK_GLASS_INGRESSES` accepts any subset of `query`/`chat`, including empty. `v1` is checked before unknown names, so `query,v1` gets the "`ADMIN_TOKEN` is never accepted on `/v1`" message.

No production code reads any of the four. Each field's comment names its consumer: STORY-010 for the maps, STORY-011/012 for the switch, STORY-013 for the ingresses.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Baseline: `test_config.py` 121 passed; full suite 3483 passed, 27 skipped | — | ✅ |
| 2 | Constants (`_UNLIMITED`, `_LIMIT_MAP_EXAMPLES`, `_LIMIT_VALUE_RE`, `_BREAK_GLASS_ACCEPTED`) and `_parse_limit_map` | `app/config.py` | ✅ |
| 3 | Four fields, `_validate_usage_limit_map`, `_validate_break_glass_ingresses`, three properties | `app/config.py` | ✅ |
| 4 | New `PRD-013 STORY-007` test block (39 cases) | `tests/test_config.py` | ✅ |
| 5 | Full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A. No frontend in the change; the UI is Reflex (Python) and was not touched |
| `pytest tests/test_config.py` | ✅ 160 passed (121 + 39) |
| Full suite | ✅ 3522 passed, 27 skipped (3483 + 39) |
| Health check (`GET /health`) | ✅ `{"status":"ok"}`, see the deviations below |
| E2E | ✅ 4/4 |

E2E detail:

1. `pytest tests/test_config.py`: 160 passed.
2. Boot checks:
   - The real `.env` sets none of the four, and `import app.config` succeeds.
   - `USAGE_REQUESTS_PER_MINUTE=admin=10` fails with: "USAGE_REQUESTS_PER_MINUTE must include a '*' entry … got 'admin=10'. Example: USAGE_REQUESTS_PER_MINUTE=*=60,admin=120."
   - `BREAK_GLASS_INGRESSES=v1` fails with: "… ADMIN_TOKEN is never accepted on /v1 …"
3. AC 5 review: a `git grep` for the four names and three properties over `app chat_ui scripts app.py` matches only `app/config.py`.
4. Full suite green.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +151/-0 |
| `tests/test_config.py` | UPDATE | +148/-0 |

## Deviations from Plan

1. **Two extra test inputs.** `*=1_000` was added to the invalid-map cases, to pin the reason `_LIMIT_VALUE_RE` exists. The duplicate-ingress case became `" chat , chat "` so that it also covers whitespace.
2. **Duplicate and no-`=` cases quote the role, not the whole entry.** The duplicate message quotes the repeated role (`'admin'`) plus the whole value. The no-`=` case quotes the entry, which for `admin` is the role itself. The tests assert on `'admin'`, quotes included.
3. **The health check ran with `RBAC_ENABLED=false`, for that process only.** The first start failed with `RbacNotBootstrappedError`, because the local dev database has no active users. That is the existing PRD-005 bootstrap guard and has nothing to do with this story. No user was created in the developer's database.
4. **Unrelated working-tree changes were stashed.** `pre-prds/README.md` (modified) and `pre-prds/PRE-PRD-017-test-suite-db-isolation.md` (untracked) were stashed before the work, with the user's approval, to satisfy the clean-tree gate. They were restored afterwards.
5. **Three commits.** The plan was committed on its own (`2702186`) ahead of the story commit, and status/report in a follow-up chore commit. This follows the STORY-006 layout (`82a3923` → `eb77e8a` → `53f8ca1`).

## Findings for later stories

- **F-1 (plan Decision 1).** The `*_map` properties re-parse on every read instead of caching. That keeps `monkeypatch.setattr(settings, "USAGE_…", …)` working for STORY-010/011 tests. The cost is a few microseconds per read. PRD F6's "parsed once" is satisfied as one parser and one shape.
- **F-2.** `.env.example` does not document the four settings yet. STORY-018 owns that, and the existing `.env.example` order tests only cover their own variables.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_usage_settings_available_with_documented_defaults`, `test_usage_limits_enabled_parses_the_string_false`, `test_limit_map_parses_roles_and_unlimited` (×2 settings), `test_limit_map_strips_whitespace_and_accepts_an_unlimited_star`, `test_an_invalid_limit_map_is_a_startup_error` (11 inputs × 2 settings), `test_a_zero_limit_names_the_real_off_switch`, `test_limit_map_role_names_are_not_checked_against_rbac`, `test_break_glass_ingresses_accepts_any_subset_of_query_and_chat` (×5), `test_break_glass_ingresses_refuses_v1` (×2), `test_break_glass_ingresses_refuses_an_unknown_name` (×3) |

## Acceptance Criteria

- [x] Given no new variables set, when `Settings()` is built, then `USAGE_LIMITS_ENABLED` is `True`, `USAGE_DAILY_TOKEN_BUDGET` is `"*=1000000"`, `USAGE_REQUESTS_PER_MINUTE` is `"*=60"` and `BREAK_GLASS_INGRESSES` is `"query,chat"`.
- [x] Given `USAGE_REQUESTS_PER_MINUTE="*=60,admin=unlimited,auditor=10"`, when the parsed property is read, then it is `{"*": 60, "admin": None, "auditor": 10}`.
- [x] Given a limit map with no `*` entry, a value of `0`, a negative or non-numeric value, a role listed twice, or an entry with no `=`, when `Settings()` is built, then it raises with a message that names the setting, quotes the offending entry and shows a valid example.
- [x] Given `BREAK_GLASS_INGRESSES` set to `""`, `"chat"` or `"query"`, when `Settings()` is built, then it is accepted; given `"v1"` or `"query,v1"`, then it raises with a message saying `ADMIN_TOKEN` is never accepted on `/v1`; given an unknown name, then it raises naming the accepted values.
- [x] Given the story's diff, when it is reviewed, then no production code reads the four settings yet, and `tests/test_config.py` covers every case above.
