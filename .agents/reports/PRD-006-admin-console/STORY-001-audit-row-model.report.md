---
story: STORY-001
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-001-audit-row-model.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 577a285
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-001: AuditRow and SummaryFigure models — a projection with no preview fields

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-001-audit-row-model.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `577a285`

## Summary

Created `chat_ui/chat_ui/admin_models.py` with the admin console's two typed models: `AuditRow`, a 16-field projection of `AuditLog` that has **no** `prompt_preview` and **no** `response_preview` field, and `SummaryFigure`, the tally sheet's figure. Both subclass `pydantic.BaseModel` following `models.py:ChatMessage`, and every field is defaulted. `tests/test_admin_models.py` pins the Risk 2 absence on two introspection surfaces and pins the field set as an exact equality. Nothing under `app/` was touched; the models are populated later by STORY-002 / STORY-004.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Create the epic branch from the PRD-004 epic | — (git) | ✅ |
| 1 | `AuditRow` + `SummaryFigure` | `chat_ui/chat_ui/admin_models.py` | ✅ |
| 2 | Absence + defaults + type tests | `tests/test_admin_models.py` | ✅ |
| 3 | Prove nothing else moved | — (verification) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Module import (`import chat_ui.chat_ui.admin_models`) | ✅ clean — pulls in neither `reflex` nor `app` |
| Both models construct with no arguments | ✅ 16 and 5 fields respectively |
| New tests | ✅ 7 passed |
| Full suite (`python -m pytest tests/ -q`) | ✅ 270 passed |
| Eight PRD Section 15 test files unmodified | ✅ `git diff epic/PRD-004-chat-ui-redesign -- tests/` empty |
| `git diff epic/PRD-004-chat-ui-redesign --stat -- app/` | ✅ empty |
| Mutation check on the Risk 2 guard | ✅ re-adding `prompt_preview` fails 3 tests; reverted |

No frontend lint step and no backend-import step apply: `chat_ui` is Reflex/Python with no JS package, and this story adds no route, component or FastAPI wiring. No Reflex compile/run cycle was needed, so `reflex-process-management` did not apply.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_models.py` | CREATE | +71 |
| `tests/test_admin_models.py` | CREATE | +160 |

## Deviations from Plan

1. **`pydantic.BaseModel` instead of `rx.Base`** — planned deviation from the story's AC wording, not from the plan. `rx.Base` does not exist in the pinned `reflex==0.9.6.post1` (`AttributeError: No reflex attribute Base`); Reflex 0.9.x is pydantic-v2 based and the shim is gone. `models.py:ChatMessage` already uses `pydantic.BaseModel` and renders under `rx.foreach`, so the AC's intent is met and only its literal class name was stale.
2. **Epic branch cut from `epic/PRD-004-chat-ui-redesign`, not `main`** — deviation from `implement.md` Phase 2.2, which says to branch from `base_branch`. Verified reason: `main` has no `chat_ui/chat_ui/theme.py`, `models.py` or `formatting.py` — PRD-004 is unmerged, so a branch off `main` would have no `ChatMessage` to mirror and no theme tokens for Phase 2.
3. **AC 5's diff base** — `git diff main --stat -- app/` reports `app/db/database.py` and `app/db/models.py` as changed, but those are PRD-004's committed changes, not PRD-006's. The equivalent check was run against the actual branch point (`git diff epic/PRD-004-chat-ui-redesign --stat -- app/` → empty). Once PRD-004 merges to `main`, the literal form becomes valid again; STORY-020 should use it then.
4. **One extra test** beyond the plan's six — `test_audit_row_verdict_defaults_to_empty_not_cleared`, pinning plan decision 4 (an unpopulated row must not claim it passed).
5. **`chat_ui/reflex.lock/` restored, not committed** — importing the `chat_ui` package caused Reflex to rewrite `bun.lock` and `package.json` (reformatting plus a `lucide-react` version bump). That is a side effect of running the interpreter, not of this story, so it was reverted with `git checkout --` and kept out of the commit.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_models.py` | `test_audit_row_has_no_preview_fields` (Risk 2, both introspection surfaces + no `"preview"` substring), `test_audit_row_carries_every_rendered_field` (exact set equality), `test_audit_row_constructs_with_no_arguments` (defaults + per-instance list), `test_audit_row_types` (`audit_id` int, `tokens_used` str), `test_audit_row_verdict_defaults_to_empty_not_cleared`, `test_summary_figure_fields_and_defaults`, `test_audit_row_populated_from_audit_log_drops_previews` (boundary in miniature) |

## Acceptance Criteria

- [x] `admin_models.py` defines `AuditRow` with all 16 register-rendered fields *(base class `pydantic.BaseModel` — see Deviation 1)*
- [x] `AuditRow` has no `prompt_preview` and no `response_preview`, asserted by test (Risk 2)
- [x] `SummaryFigure` defined with `label`, `value`, `scope`, optional `share` (plus `items` for the three ranked figures)
- [x] Every field on both models has a default; both construct with no arguments
- [x] No file under `app/` modified *(checked against the real branch point — see Deviation 3)*
- [x] All tasks completed
- [x] Full suite passes (270); the eight pinned test files unmodified
- [x] Follows existing patterns (`chat_ui/chat_ui/models.py`, `tests/test_contrast.py`)

## Notes Forward

- **STORY-002** owns `to_audit_row(log, now)` and the placeholder text for the empty `str` fields. `app/routers/admin.py:40` already parses `pii_entities` as `log.pii_entities.split(",") if log.pii_entities else []` — match it rather than inventing a second format.
- **STORY-011**'s `rx.match` over `verdict` needs a default arm, since `verdict` defaults to `""`.
- **STORY-015** renders `SummaryFigure.items` for `top_models` / `top_users` / `top_pii_entities`; the blocked-count indentation is layout, not a model field.
- Any command that imports the `chat_ui` package rewrites `chat_ui/reflex.lock/`. Keep it out of story commits unless a dependency actually changed.
