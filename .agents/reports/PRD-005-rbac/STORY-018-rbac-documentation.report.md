---
story: STORY-018
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-018-rbac-documentation.plan.md
epic_branch: epic/PRD-005-rbac
commit: 540fced
status: COMPLETE
completed: 2026-08-29
---

# Implementation Report — STORY-018: README, .env.example, and roadmap updates for RBAC

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-018-rbac-documentation.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `540fced`

## Summary

`README.md` still described the pre-RBAC system shipped by STORY-001…STORY-017: no authentication row in the Features table, none of the four `RBAC_*`/`MODEL_ALLOWLIST` env vars documented, no bearer-token requirement or `401`/`403`/`200`-`BLOCKED` split in the API Reference, a stale free-text `user_id` description for the chat UI login (the shipped `login()` actually verifies a bearer token), RBAC still listed under Roadmap → Planned, and no Troubleshooting entry for the fail-fast bootstrap guard STORY-016 added. Investigation during planning found `.env.example` already carries all four RBAC vars (committed by STORY-005, commit `c2aca34`) and matches `Settings` field-for-field — so AC6 required verification, not an edit, making this effectively a `README.md`-only story.

All 12 plan tasks were completed, including the optional Task 11 (Solution one-liner + Architecture diagram identity/authorization step). Every documented value, error message, and JSON shape was cross-checked against the real source (`app/middleware/auth.py`, `app/services/authz.py`, `app/services/query_pipeline.py`, `app/models/schemas.py`) and then verified live: a scratch deployment was bootstrapped and exercised with real HTTP requests (`401`, `403` for `query:submit` and `stats:read`, `200 BLOCKED` for a disallowed model, and `GET /audit` carrying `role`/`denied_permission`), and the fail-fast startup guard was confirmed to fail with the exact documented message when no user is seeded.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Authentication row in Features table | `README.md` | ✅ |
| 2 | Four RBAC env var rows + updated `ADMIN_TOKEN` description | `README.md` | ✅ |
| 3 | Verify `.env.example` matches `Settings` field-for-field | — (verification) | ✅ |
| 4 | `POST /query` — bearer auth, 401, 403, 200-BLOCKED examples | `README.md` | ✅ |
| 5 | `GET /audit` — scoping note + `role`/`denied_permission` fields | `README.md` | ✅ |
| 6 | `GET /stats` — permission requirement | `README.md` | ✅ |
| 7 | Roadmap — RBAC moved to Shipped; Action-policy cross-reference updated | `README.md` | ✅ |
| 8 | Troubleshooting — bootstrap failure, 401 vs 403 | `README.md` | ✅ |
| 9 | Chat UI section — real login-flow description | `README.md` | ✅ |
| 10 | Both Quickstarts — bootstrap (`create-user`) step | `README.md` | ✅ |
| 11 | Solution one-liner + Architecture diagram — identity/authorization step (optional) | `README.md` | ✅ |
| 12 | Cross-check every documented value against the code | — (verification) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `git diff --stat` (app-code scope) | ✅ `README.md` only; 0 files under `app/`, `tests/`, `chat_ui/`, `.env.example` unchanged |
| `.venv/Scripts/python.exe -m pytest -q` | ✅ 410 passed, unchanged from STORY-017 baseline |
| `python -c "from app.main import app"` | ✅ |
| `.env.example` parses through `Settings` and matches `app/config.py` defaults | ✅ |
| Architecture diagram box alignment (33-char lines, matching existing rows) | ✅ |
| Table of Contents vs actual `##` headings | ✅ unchanged, no broken anchors |
| Markdown fence balance (`grep -c '```'`) | ✅ 42 (even) |
| E2E | ✅ 12/12 (see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +142/-16 (net across all 12 tasks) |
| `.env.example` | NO CHANGE | already correct (STORY-005) |

## Deviations from Plan

None. All 12 tasks, including the optional Task 11, were implemented exactly as scoped. The plan's own scope correction (`.env.example` needs no edit) was verified true, not re-litigated.

## Tests Written

None — documentation-only story, per its own Acceptance Criteria and the plan's explicit "no application code, no tests" scope. Verification was performed via the existing 410-test suite (unchanged) plus live E2E requests against a bootstrapped scratch deployment (see below).

## End-to-End Verification

Ran against a scratch SQLite database (`DATABASE_URL` pointed outside the repo, `PORT=8199`), never touching the real dev `.env`/`harness_ai.db`:

1. ✅ `python app.py` with `RBAC_ENABLED=true` and zero seeded users → exits with `RbacNotBootstrappedError: RBAC_ENABLED=true but no active users exist. Bootstrap one with: python scripts/manage_users.py create-user --user-id <id> --role <admin|auditor|user>` — matches the new Troubleshooting entry verbatim
2. ✅ `python scripts/manage_users.py create-user --user-id admin --role admin` (and for `auditor`/`user` roles) → prints the token exactly as the new Quickstart step describes
3. ✅ Same scratch DB, now bootstrapped → `python app.py` boots; `GET /health` → `200 {"status":"ok"}`
4. ✅ `POST /query` with no `Authorization` header → `401 {"detail":"Invalid or missing credential"}` — matches the new README example verbatim
5. ✅ `POST /query` with an `auditor` token → `403 {"detail":"Permission denied: query:submit"}` — matches the new README example verbatim
6. ✅ `POST /query` with a `user` token and a disallowed model → `200 {"status":"BLOCKED","reason":"Model not permitted for this role","required_permission":"query:model:claude-3-opus"}` — matches the new "200, refused by policy" example verbatim (same `reason`/shape, model name substituted)
7. ✅ `GET /audit` with the `admin` token, after the denial above → entry carries `"role": "user", "denied_permission": "query:model:claude-3-opus"` — confirms the new `role`/`denied_permission` fields render as documented
8. ✅ `GET /stats` with a `user` token → `403 {"detail":"Permission denied: stats:read"}` — matches the updated README sentence verbatim
9. ✅ `grep -n "Role-based access control" README.md` → one hit under `### Shipped` (`- [x]`), zero hits under `### Planned`
10. ✅ `git diff --stat` → `README.md` only in application scope
11. ✅ `pytest -q` → 410 passed, no regressions
12. ✅ Table of Contents, fence balance, and diagram alignment all verified structurally sound

## Acceptance Criteria

- [x] Given the README Features table, when read, then RBAC is listed alongside the existing capabilities
- [x] Given the Environment Variables section, when read, then every `RBAC_*` variable and `MODEL_ALLOWLIST` is documented with its default
- [x] Given the API Reference, when read, then the bearer-token requirement and the `401` / `403` / `200`-`BLOCKED` split are documented for `/query`, `/audit`, and `/stats`
- [x] Given the Roadmap, when read, then "Role-based access control (RBAC)" has moved from Planned to Shipped
- [x] Given Troubleshooting, when read, then it covers the unseeded-startup failure and the `401` vs `403` distinction
- [x] Given `.env.example`, when compared to `Settings`, then it matches field for field (already true; verified in Task 3)
