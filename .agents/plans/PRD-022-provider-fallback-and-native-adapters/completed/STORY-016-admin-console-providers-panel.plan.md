---
story: STORY-016
prd: PRD-022
slug: admin-console-providers-panel
title: Admin console - Providers panel and attempt column on the Register
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Admin console Providers panel

## Summary

Add a sixth console view, Providers (`/admin/providers`), as a peer of Storage, built by mirroring Storage file for file: a `components/providers.py` view, a `providers_*` block in `AdminState`, `to_providers_view` + view models, copy in `admin_copy`. `AdminState.load()` fills it from `health.providers_status(names)` in process (names from `provider_registry.current().providers`, exactly as `GET /providers/status`, `app/routers/admin.py:247-248`). The Register gains an `attempt` column right after `provider`, a `request_id` disclosure line, and the free-text search matches `request_id` (client-side over the loaded window, the way `conversation_key` already works).

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-016-admin-console-providers-panel.md`
- PRD sections used: F8, F9 (Section 7), Section 8, Section 10 `/providers/status`
- Systems affected: `chat_ui/` only. No `app/` change, no new HTTP route (the console page is a Reflex page under `/admin/*`, already static in the `Caddyfile`; matcher untouched).

## Design Decisions

- **Gating (AC4).** The console has no per-permission switch: Storage sits behind the admin-token gate only (the token's role holds `stats:read`). Providers is gated identically: same `admin_page(...)` shell and the same `authenticated` early return in `load()` (`admin_state.py:1440`). Do not invent a role check; say so in the module docstring. Orchestrator: confirm this reading of "exactly as Storage is gated".
- **Do NOT add the three `/stats`-only figures** (`fallback_answers` SQL, `failed_attempts`, `answers_by_provider`) to `_READS` (`admin_state.py:382`). The in-memory `ProviderCounters.fallback_answers` IS shown, as a counter from `providers_status()`.
- **No new database read.** `request_id` filtering uses the already loaded window (`_READS[0]`, `admin_state.py:383`, `list_audit_logs` with `limit`). `list_audit_logs(request_id=)` exists (`app/db/database.py:1920-1926`) but is not used, so no census, `tests/test_db.py` snapshot or `_READS` change.
- **Own fault, strings and lists only**: `providers_error`, rendered by `fault_panel`; a failed read never touches `error` / `storage_error`.
- **No colour verdicts, meters or charts** (Storage's stated restraint, `components/storage.py:8-13`): state in words; only theme tokens `storage.py` already uses (palette guard).
- **Register track**: attempt gets its own twelfth track (see Task 5 and risks).

## Skills In Use

| Skill | Why it applies | Tasks |
|-------|---------------|-------|
| frontend-design | Distinctive, intentional, non-templated, yet the panel must follow `theme.py` and Storage's structure: the intent shows in information order (verdict naming unhealthy providers first, then one block per provider), not in new ink | 3, 4 |
| reflex-docs (`chat_ui/AGENTS.md`) | Check every Reflex API (`rx.foreach`, `rx.cond`, `custom_attrs`) against the installed package source, not memory | 3, 4 |

## Patterns to Follow

| Category | Source | Mirror |
|----------|--------|--------|
| View component | `chat_ui/chat_ui/components/storage.py:28-250` | helpers re-declared, not imported (:22-25); `_heading`, `_fact`, `_keyed_table`, `_caption`, `storage()` shell with `fault_panel` + `hx-scroll` body |
| State block | `admin_state.py:634-647` vars, `:1454` error reset, `:1463-1484` read + commit, `:1121-1129` state property, `:237-242` state consts | one try/except, `async with self` commit, `else` clears the error |
| Formatting | `admin_formatting.py:457-560` (`to_storage_view`, `_keyed_rows`) | strings only, `format_count`, `_text`; `"provider:kind"` keys split with `partition(":")` |
| Models | `admin_models.py:149-178` | `StorageFact` / `StorageCounterRow` / `StorageView` |
| Shell/routes | `admin_shell.py:70-83` constants, `:518-529` peer link; `chat_ui.py:123-125`, `:196-202` page + `add_page` | sixth peer, same separator box |
| Register column | `register.py:111-135` (`_GRID`, `_MIN_WIDTH`), `:579` (`_cell(row.provider)`), `:644` (head) | one track and head after provider |
| Search | `admin_state.py:491-527` (`_matches`) | add `row.request_id.casefold()` |
| Tests | `tests/test_storage_view.py:168-231` | console fixture, `_load`, AST import-purity test |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/providers.py` | CREATE | the Providers view |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `ProviderCard`, `ProviderFact`, `ProviderCounterRow`, `ProvidersView`; `AuditRow.attempt`, `.request_id` |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `to_providers_view`; `to_audit_row` sets `attempt`, `request_id` via `_text` (`:326`, `:345` area) |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | `VIEW_PROVIDERS_LABEL`, `READ_LABEL_PROVIDERS`, `PROVIDERS_*`, `COLUMN_ATTEMPT` (+ title), `DETAIL_REQUEST_LABEL` |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | imports (`health`, `provider_registry`, `to_providers_view`), `providers_*` vars, `providers_state`, read in `load()`, `_matches` |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | `ROUTE_PROVIDERS = "/admin/providers"`, `VIEW_PROVIDERS`, sixth peer |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `admin_providers_page`, `app.add_page` |
| `chat_ui/chat_ui/components/register.py` | UPDATE | twelfth track, attempt cell and head, request disclosure line, docstring counts |
| `tests/test_providers_view.py` | CREATE | view and state tests |
| `tests/test_register.py` | UPDATE | one assertion (track count) + new attempt / request_id tests |
| `tests/test_admin_shell.py`, `tests/test_copy.py`, `tests/test_caddyfile_routes.py` | UPDATE | pinned route/view/copy sets; `/admin/providers` in `STATIC_PATHS` |

## Tasks

### Task 1: Copy, models, formatting
- Files: `admin_copy.py`, `admin_models.py`, `admin_formatting.py`. English only.
- `ProviderCard`: `name`, `state`, `since`, `failures`, `last_failure`, `retry_after` (all str; null `last_failure` / `retry_after` -> the absent mark via `_text`; seconds as "{n} s"). `ProvidersView`: `verdict` in words ("All providers are closed." / "{n} provider(s) not closed: {names}."), `caption` (`This process: {instance}. Counters reset when it restarts.`), `cards`, `counters` (breaker opens, fallback answers), `failed` and `skipped` keyed rows (provider, class, count, from `attempts_failed` / `skipped`). Provider order = registry order, stable between refreshes. Own `ProviderFact`, so views stay independent.
- Only `kind` and reason strings, never message text (T10).
- Mirror: `admin_formatting.py:479-560`.

### Task 2: State
- `admin_state.py`: import `health` and `provider_registry` by name (see `chat_ui.py:22`); add `PROVIDERS_STATE_FAULT/READY`; vars after `:647`; clear `providers_error` beside `:1454`; read block right after the Storage block (`:1485`): `to_providers_view(health.providers_status([p.name for p in provider_registry.current().providers]))`, called directly (no thread; no DB, no network). Extend the docstring (`:24-26`). Extend `_matches` and its docstring with `request_id`.
- Do not touch `_READS` / `SUMMARY_FIGURES`. Check `reset()` on sign-out clears the new vars like the storage ones.

### Task 3: Providers component, shell, page
- `components/providers.py`: caption (instance + `refreshed_stamp()`), verdict, one block per provider via `rx.foreach` (heading = name, facts grid: state, since, consecutive failures, last failure, retry after, `_FACT_GRID` as in storage), counters, two keyed tables (failed attempts, skipped). Imports only `reflex`, `chat_ui`, `chat_ui.admin_state`, `chat_ui.components.admin_shell`.
- `admin_shell.py` constants + sixth peer box after `:529`; `chat_ui.py` page function + `add_page(..., context={"sitemap": None})`.
- Check the masthead still wraps at phone width (`hx-view-switch`, `admin_shell.py:530-534`).

### Task 4: Register attempt column and request_id
- `register.py`: add a `3.5rem` track after the provider track in `_GRID`; `_MIN_WIDTH` + 4.25rem (73.5 -> 77.75rem); `_cell(row.attempt, text_align="right"),` immediately after `_cell(row.provider),` (keeps the `tests/test_register.py:1464` adjacency pin); `_head_cell(admin_copy.COLUMN_ATTEMPT, align="right", title=...)` between the provider and tokens heads (keeps the `:1466-1468` order pin). Disclosure: `_detail_field(admin_copy.DETAIL_REQUEST_LABEL, row.request_id)` beside the conversation line (`register.py:509`), so the id can be pasted into the search. Update the "eleven" docstrings (`:111`, `:132`, `:560`) and any search placeholder copy listing fields (`:812-840`).
- NULL attempt (pre-step-7 and verdict rows) -> absent mark. Failed attempts are already their own audit rows (STORY-014): nothing to add.

### Task 5: Pinned-set updates
- `tests/test_register.py:790`: `== 11` -> `== 12` with a comment citing PRD-022 STORY-016 (same precedent as PRD-020's 10 -> 11 at :789). **This edits a PRD-020 test assertion**: orchestrator to approve. Any alternative (attempt inside the provider cell) breaks the `:1464` pin instead, so no cheaper option exists.
- `tests/test_admin_shell.py`: `EXPECTED_ROUTES` (:59-67), probe imports (:205-218), masthead lists (:256, :305-330, :345-349). `tests/test_copy.py:405-420`: census for the new constants. `tests/test_caddyfile_routes.py:66-68`: add `/admin/providers` to `STATIC_PATHS` (`EXPECTED_MATCHER` unchanged).

### Task 6: Tests
- `tests/test_providers_view.py`: closed / open / half_open verdict in words; card fields; null retry_after -> absent mark; counter rows split on `:`; order stable; `load()` fills the view from a stubbed `health.providers_status`; failing read sets only `providers_error`; a failed summary read still refreshes it; sign-out clears; unauthenticated `load()` leaves `providers_*` empty; `_READS` names none of the three `/stats` figures; AST import-purity test (no `app.routers`, no `httpx`).
- In `tests/test_register.py`: `to_audit_row` maps attempt / request_id (NULL -> absent); `filter_rows` by request_id returns exactly that request's rows; probe renders the attempt head and cell.

## End-to-End Tests

- [ ] `AdminState.load()` against the real `health` with two registry providers, one opened by repeated `health.record` failures: panel strings show `open` and a retry-after.
- [ ] `tests/test_chat_ui_startup_guard.py` compiles every page, including `/admin/providers`.
- [ ] Register: two rows sharing a `request_id` (attempt 1 fault, attempt 2 cleared) both render; searching the id shows both.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_providers_view.py tests/test_storage_view.py tests/test_register.py tests/test_admin_shell.py tests/test_copy.py tests/test_admin_palette.py tests/test_chat_ui_startup_guard.py tests/test_caddyfile_routes.py tests/test_providers_status.py tests/test_untouched_app.py
```
Also grep `tests/` for `AuditRow(`, `to_audit_row`, `admin_state` var-set snapshots (`test_usage_view.py`, `test_actions_view.py`, `test_chat_ui_storage_failures.py`) and run any hit. `test_schemas.py` / `test_reporting_invariance.py` only if `_READS` / `SUMMARY_FIGURES` were touched (they must not be). Run `test_chat_ui_startup_guard.py` with no other pytest running.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|----|---------|------|
| AC1 panel, in-process, beside Storage | 1,2,3 | `tests/test_providers_view.py`; `test_admin_shell.py` peer link |
| AC2 `attempt` column, `provider` kept, request_id filter | 4,5 | `tests/test_register.py` new tests + `:790` |
| AC3 theme + startup guard | 3 | `test_chat_ui_startup_guard.py`, `test_admin_palette.py`, `test_copy.py` |
| AC4 hidden without access | 2,3 | unauthenticated-load test in `test_providers_view.py` (same admin gate as Storage) |

## Risks / open questions

- The `test_register.py:790` edit of a PRD-020 assertion (needs orchestrator approval).
- AC4: the console has no per-permission gating; the admin-token gate is the rule.
- The `request_id` filter is client-side over the loaded window; a request older than the window is not found.
