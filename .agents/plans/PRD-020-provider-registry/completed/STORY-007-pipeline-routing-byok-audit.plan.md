---
story: STORY-007
prd: PRD-020
slug: pipeline-routing-byok-audit
title: Pipeline step 2 routing, BYOK per provider and per-row provider audit
type: ENHANCEMENT
complexity: large
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Pipeline step 2 routing, BYOK per provider and per-row provider audit

## Summary

`run_conversation` resolves the route once at step 2 (`authorize_route`, built in STORY-004), carries it in a local, adds a per-provider BYOK check, and stamps `provider` / `upstream_model` / `provider_trust` (from the Route) on every row written after step 2. The upstream seam is untouched: the original model id still goes through `call_openrouter(messages, model=, api_key=, **extra)`; `call_upstream` (`app/services/upstream/__init__.py:62`) already re-resolves and maps to `upstream`, so `_Upstream` in `app/routers/v1.py:140-171` needs no change.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-007-pipeline-routing-byok-audit.md`
- PRD sections: 6.1, F5, 9.1, 9.2 (T3, T6, T8), 10 (BYOK example); D3, D10, D12, D13
- Systems: `app/services/query_pipeline.py` only (app code); tests.

## Design Decisions

- Step 2 (`query_pipeline.py:404-413`): `route = authorize_route(identity, model)` in the same `try`, same `_deny` label (the PermissionDenied text) and reason `"Model not permitted for this role"`. Replace the `authorize_model` import (`:29`) with `authorize_route`; import `Route` (`from app.services.provider_registry import Route`; no cycle, it imports authz not the pipeline).
- BYOK (`:415-423`, D10): inside `if openrouter_api_key is not None:` keep the `authorize(identity, PERMISSION_QUERY_BYOK)` try block first, unchanged; then `if not route.provider.byok: return _deny(..., exc=PermissionDenied(f"query:byok:{route.provider.name}"), reason="Missing required permission", route=None)`. It runs before 2b/2c, so nothing goes upstream and nothing is charged (`admit` never runs). No `_KNOWN_PERMISSIONS` entry. Response `required_permission` is `query:byok:<name>`. The legacy provider is `byok: true`, so legacy is unchanged.
- Audit helper beside `_deny`: `_route_fields(route: Optional[Route]) -> dict` returning `{"provider": route.provider.name, "upstream_model": route.upstream_model, "provider_trust": route.provider.trust}`, or three `None`s. Sites use `**_route_fields(route)`. Values come from the Route, never from the upstream result; `model_used` stays the requested id.
- `_deny` gains a required keyword `route: Optional[Route]` (house rule: a forgotten arm is a TypeError, comments at `:262-285`), forwarded as `**_route_fields(route)` into its `log_query` (`:300`). The submit, model and both BYOK arms pass `route=None`; the break-glass arm passes `route=route`.
- `route` is assigned at step 2 and every later site is after the early `return`s, so it is always bound there.
- Untouched on purpose: `charges_budget=openrouter_api_key is None` (`:484`), BYOK charge skip (`:826`), `extra` (`:776-780`), the seam call (`:783-785`), `run_query` default callable (`:1025`), `pii_input_relaxed` / `usage_estimated` (default 0; 008/009 consume `route`), `relaxes_input()` and `max_context_tokens`.

### Every `log_query(` / `_deny` site (lines at `9ec66d5`)

| Site | Arm | provider fields |
|---|---|---|
| `_deny` `:300` | submit-permission denial `:392-401` | NULL (`route=None`) |
| `_deny` | model denial `:404-413` | NULL (no route exists) |
| `_deny` | BYOK permission denial `:416-423` | NULL |
| `_deny` | BYOK provider denial (new) | NULL |
| `_deny` | break-glass `:436-445` (2b) | route |
| `log_query` `:487` | usage limit refusal (2c) | route |
| `:533` | context limit (3) | route |
| `:565` | duplicate block (4) | route |
| `:620` | pattern block (5) | route |
| `:657` | pattern flag row (5, request continues) | route |
| `:699` | redaction size limit (6) | route |
| `:747` | input redaction error (6) | route |
| `:787` | upstream-error arm (7) | route |
| `:876` | output redaction error (8) | route |
| `:920` | success (8) | route |

`grep -c "log_query(" app/services/query_pipeline.py` must give 12 (11 above plus `_deny`'s), each with `**_route_fields(`; a test enforces it.

## Skills In Use

None apply (`skills: []`; `.agents/skills` holds only `frontend-design`).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Required-arg helper | `query_pipeline.py:257-318` | `_deny` comment style citing PRD ids; add `route` the same way |
| Route/authz | `app/services/authz.py:208-227` | `authorize_route` returns `Route`, raises `PermissionDenied("query:model:<m>")` |
| Seam | `app/services/upstream/__init__.py:62-81` | already resolves, D10 key choice, `model_used` = requested id |
| Two stubs | `tests/test_upstream_adapter.py:66-116,162-181` | `stubs` factory (log shows `auth=yes|no`), `_yaml(local_port, remote_port, byok=)`, `provider_file` from `tests/_providers.py` |
| Row assertions | `tests/test_query_pipeline_audit_fields.py:97-100,195` | `_fields(row)` via `getattr` on the read-back row; `temp_db` fixture |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/query_pipeline.py` | UPDATE | route at step 2, BYOK per provider, `_route_fields`, `_deny(route=)`, 11 log_query sites |
| `tests/test_query_pipeline_routing.py` | CREATE | two-stub routing, BYOK refusal, per-arm provider fields, injected stub |
| `tests/test_query_pipeline_break_glass.py` | UPDATE | spy helper `:326,338,363` (see Risks) |
| `tests/test_query_pipeline_multiturn.py` | UPDATE | spy helper `:142,154,177` |
| `tests/test_query_pipeline_usage_limits.py` | UPDATE | spy helper `:343,356,379` |

## Tasks

### Task 1: Route at step 2, BYOK, helper, `_deny`
- **File**: `app/services/query_pipeline.py`
- **Implement**: as in Design Decisions: imports `:25-30`; helper beside `_deny`; step 2 `:404-423`; new BYOK arm; `route=` on the four existing `_deny` calls (`:394, :407, :419, :438`).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Provider fields on the 11 direct `log_query` calls
- **File**: `app/services/query_pipeline.py`
- **Implement**: add `**_route_fields(route)` to each site in the table (`:487` through `:920`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_authorization.py tests/test_query_outcomes_regression.py`

### Task 3: Repoint the three step-order spies
- **Files**: the three tests above. Each does `monkeypatch.setattr(query_pipeline, "authorize_model", spy)` with trace label `"authorize"`; after Task 1 that name is gone from the module and `setattr` raises AttributeError. Spy `authorize_route` instead (same label, same args, return value passed through because the pipeline now uses it). Comment: `# PRD-020 D3, STORY-007: step 2 calls authorize_route`. The asserted order does not change.
- **Validate**: those three files.

### Task 4: New tests, `tests/test_query_pipeline_routing.py`
Fixtures: reuse the `stubs` factory and `_yaml` pattern of `tests/test_upstream_adapter.py:66-116` (copy; do not edit what STORY-005 pinned), `provider_file`, `temp_db`, identities as in `test_query_pipeline_audit_fields.py`.
- `/query` (TestClient) and `/v1/chat/completions` (client/auth setup from `tests/test_v1_query_isolation.py`): `remote/m` reaches only the remote stub (`auth=yes`, wire model `up-remote`), `local/m` only the local stub (`auth=no`, `up-local`); the other stub's log stays empty.
- BYOK: `byok=False` yaml, `openrouter_api_key` on `remote/m` -> forbidden body `required_permission == "query:byok:remote"`, reason `Missing required permission`, both stub logs empty, usage not charged (`USAGE_LIMITS_ENABLED` on, usage store unchanged), row `denied_permission` set and the three fields NULL. On a `byok: true` provider the caller's key reaches the stub. A caller without `query:byok` on a byok:true provider gets today's verdict with NULL fields.
- Per-row fields, parametrized over: break-glass, usage limit, context limit, duplicate, pattern block, redaction-size limit, input redaction error, upstream error (stub scripted 5xx; `model_used` is the requested id), output redaction error, success. Expect the route's `(provider, upstream, trust)`; submit, model and both BYOK denials NULL. Reuse the monkeypatch recipes of `test_query_pipeline_audit_fields.py` ARM_CASES for arms it already drives.
- Legacy: no file, model in `MODEL_ALLOWLIST` -> `("openrouter", <model>, "external")`, `model_used` unchanged.
- Injected `call_openrouter(messages, model, api_key, **kw)` stub: receives the original model id (not `upstream`), still works in file mode.
- Source guard: every `log_query(` call in `query_pipeline.py` contains `_route_fields(` (count 12), so a forgotten arm fails.

## End-to-End Tests

- [ ] `TestClient(app)` `POST /query` and `/v1/chat/completions` against two live stubs (Task 4).
- [ ] BYOK refusal over HTTP matches PRD section 10's body shape for `query:byok:<name>`.
- [ ] STORY-001 replay green and unedited: `tests/test_prd020_legacy_fixtures.py`. The fixtures hold HTTP bodies and upstream requests only (no audit-row columns), so none needs a change.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_routing.py tests/test_query_pipeline_authorization.py tests/test_query_pipeline_audit_fields.py tests/test_v1_query_isolation.py tests/test_query_outcomes_regression.py tests/test_prd020_legacy_fixtures.py tests/test_query_pipeline_break_glass.py tests/test_query_pipeline_multiturn.py tests/test_query_pipeline_usage_limits.py tests/test_provider_routing.py tests/test_upstream_adapter.py tests/test_untouched_app.py
```
Add `tests/test_query_pipeline.py` if it exists. No test is renamed or removed, so the PII guard is not needed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 authorize_route, same label/reason, order tests green | 1, 3 | `test_query_pipeline_authorization.py`; order tests in break_glass / multiturn / usage_limits |
| AC2 BYOK refusal per provider | 1, 4 | `test_query_pipeline_routing.py::test_byok_*`; legacy `byok_admin` replay |
| AC3 two stubs, own key, upstream name | 4 | `test_query_pipeline_routing.py::test_two_stubs_*` (query and v1) |
| AC4 per-row provider fields, NULL at/before step 2 | 1, 2, 4 | `test_query_pipeline_routing.py::test_row_provider_fields[arm]` + source guard |
| AC5 injected stub signature | 1, 4 | `test_query_pipeline_routing.py::test_injected_stub_*` |

## Risks / questions

- **Three existing step-order tests need a one-name repoint (Task 3).** `test_query_pipeline_break_glass.py:326-363`, `test_query_pipeline_multiturn.py:142-177`, `test_query_pipeline_usage_limits.py:343-379` patch `query_pipeline.authorize_model`; the binding design removes that call, so the spy follows it. Asserted order unchanged; they are neither STORY-001 fixtures nor the guards the story names. Rejected alternative: keep calling `authorize_model` as well (double resolution).
- `/v1` and the chat UI reach the pipeline through `run_conversation`: route fields flow with no router change.
- Legacy live settings (OD1): `call_upstream` re-resolves from live settings; a test changing `MODEL_ALLOWLIST` mid-request could see two routes. None does.
