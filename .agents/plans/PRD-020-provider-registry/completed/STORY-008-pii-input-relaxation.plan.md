---
story: STORY-008
prd: PRD-020
slug: pii-input-relaxation
title: PII input relaxation for an internal, relaxed provider
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: PII input relaxation for an internal, relaxed provider

## Summary

Step 6 of `run_conversation` evaluates `relaxed = route.relaxes_input()` once. When true it skips the code size limit and the per-message input redaction loop; the original `messages` go to the seam unchanged and `input_entities` stays empty. Every `log_query` written after that decision passes `pii_input_relaxed=relaxed`. Output redaction (step 8) and `_redact` are untouched. `relaxes_input()` (`provider_registry.py:150-156`), the `pii` key (validated at `:362-364`) and `log_query(pii_input_relaxed=)` (`audit_logger.py:112`) already exist (STORY-004/006); this story is pipeline wiring plus tests.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-008-pii-input-relaxation.md` (AC text lives there)
- PRD sections used: 6.6, 9.2 T4, D7, O2 (adopted: output redaction stays on under `chat`)
- Systems affected: `app/services/query_pipeline.py` only, plus tests

## Design Decisions (binding, from the orchestrator)

- `relaxed = route.relaxes_input()` evaluated ONCE at the start of step 6, after patterns (step 5, flag row `:693-713`), next to `policy = get_pii_policy(profile_name)` (`:719`). `route` is the local from `:426` (non-None past step 2). Never from a request field, role, profile or host.
- Relaxed: skip `_redaction_limit_exceeded` (`:735`) and the input loop (`:773-811`). `redacted_messages` is the original `messages` (same `Message` objects the seam at `:824` receives today). `input_entities = []`, so `pii_detected_input=0` (not analyzed).
- Not relaxed: today's path, textually unchanged. Legacy mode, `pii: standard`/absent and `PII_REDACTION_ENABLED=false` all give `relaxed == False`.
- Audit: `pii_input_relaxed=relaxed` on the five `log_query` calls after the decision: redaction-limit row (`:738`, unreachable when relaxed, passed for consistency), input-redaction-error (`:787`, same), upstream-error (`:828`), output-redaction-error (`:918`), success (`:963`). Rows before step 6 (denials, duplicate, break-glass, usage limit, step-5 flag row `:695`) keep the default 0. Not folded into `_route_fields` (`:253`), which serves pre-step-6 rows.
- `_redact` (`:233`) and the step-8 arm (`:914-947`) unchanged. No new `log_query` site: STORY-007's guard (`tests/test_query_pipeline_routing.py:403-409`, 11 sites, `_route_fields(route)` within 120 chars) stays valid; do not weaken it.
- Shape: `over = None if relaxed else _redaction_limit_exceeded(messages, policy)` and `if relaxed: redacted_messages = messages; input_entities = []` / `else:` the existing loop, so the standard path stays untouched. (Implementer's call between wrapping the loop in `if not relaxed:` and extracting it; keep the diff small.)

## Skills In Use

None (`skills: []`; nothing in `.agents/skills` matches this domain).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Comments | `query_pipeline.py:715-734` | step comments cite PRD sections/decisions ("PRD-020 D7, 6.6") and say why |
| Audit kwargs | `query_pipeline.py:963-990` | keyword args after `**_route_fields(route)`; flag beside `pii_detected_input` |
| Two-stub tests | `tests/test_query_pipeline_routing.py:75-130, 322-327` | `stubs` factory, `_yaml`, `provider_file`, `_run`, `_last_row`, `_audit_rows_since` |
| Redact stubs | `tests/test_audit_characterization.py:153-170, 276-285` | autouse `_shipped_settings` replaces `query_pipeline.redact` with a no-op; `pii_policy.load()` after `PII_*` changes |
| Source guard | `tests/test_query_pipeline_routing.py:403-409` | regex over `log_query(` sites |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | step 6 relaxation + flag on post-step-6 rows |
| `tests/test_query_pipeline_pii_relaxation.py` | CREATE | AC1-AC5, the four table columns |

`tests/test_query_pipeline_pii_profiles.py` and `tests/test_query_pipeline_routing.py` stay unedited.

## Tasks

### Task 1: Step 6 gate
- **File**: `app/services/query_pipeline.py` (`:715-811`)
- **Implement**: after `policy = get_pii_policy(...)` add `relaxed = route.relaxes_input()` with a comment (PRD-020 D7, 6.6: decided by the Route alone; skips only input redaction and the code size limit; patterns above and output below unchanged; `pii_detected_input=0` then means not analyzed). Gate the limit and the loop as in Design Decisions. Adjust the comment at `:762` only to say relaxation bypasses the loop.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Flag on every post-step-6 row
- **Implement**: add `pii_input_relaxed=relaxed,` to the `log_query` calls at `:738`, `:787`, `:828`, `:918`, `:963` (not `:695` or earlier).
- **Validate**: `grep -c "pii_input_relaxed=relaxed" app/services/query_pipeline.py` prints 5.

### Task 3: Tests, `tests/test_query_pipeline_pii_relaxation.py`
Reuse the routing module's imports and fixtures. Helpers: a YAML with `local` (`trust: internal`, `pii` parametrised `relaxed` / `standard` / absent; `pii: relaxed` on `external` is a load error) and `remote`; a regex email masker replacing `query_pipeline.redact` and `redact_for_policy` (no spaCy; applied inside the test after the autouse no-op stub); `pii_policy.load()` after any `PII_*` change. The stub does not echo, so script the local stub to reply with fixed text containing an email. Read what the stub received from its log, and the row from `_last_row()`.
- 2x2 matrix, parametrised: `chat` (`profile="chat"`) and `code` (`profile="code"`, `ingress="v1"`) by relaxed vs `standard`: the stub log holds the raw email only when relaxed, a mask token otherwise; flag 1/0; `pii_detected_input` 0 when relaxed.
- Chat relaxed: the returned response is masked, flag 1 (O2).
- Code relaxed with `PII_MAX_CHARACTERS_CODE` tiny: not refused, reaches the stub. Code standard, same limit: `QueryBlockedContextLimitResponse`, "redaction limit" row, flag 0, stub log empty.
- `pii` absent behaves as `standard`.
- `PII_REDACTION_ENABLED=false` with a relaxed provider: `authorize_route(...).relaxes_input()` is False, run succeeds, row flag 0.
- Pattern block with a relaxed provider (profile/patterns as in `tests/test_query_pipeline_patterns.py`, `_use_profile`): blocked before step 6, stub log empty, flag 0, provider fields set.
- Output-redaction error arm under relaxation (masker raises on the stub's reply): `PiiRedactorError` propagates, row `success=False`, flag 1, `pii_detected_input=0`.
- Injected `call_openrouter` capture receives the original `Message` objects (`is`) under relaxation, an assistant `tool_calls` turn intact.
- Source guard: exactly five `pii_input_relaxed=relaxed` in `query_pipeline.py`, each after the single `relaxed = route.relaxes_input()` (offset compare).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_pii_relaxation.py`

## End-to-End Tests

- [ ] `TestClient(app)` `POST /query` against a relaxed local model with two stubs: local stub log has the raw email, the response body is masked, `_last_row()` flag 1.
- [ ] `/v1` chat-completions on the same registry (code profile): email unmasked, flag 1 (AC1).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_pii_relaxation.py tests/test_query_pipeline_pii_profiles.py tests/test_query_pipeline_routing.py tests/test_query_pipeline_patterns.py tests/test_audit_characterization.py tests/test_prd020_legacy_fixtures.py tests/test_untouched_app.py
```
No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed. Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 code relaxed: unmasked, no limit, flag 1, detected 0 | 1, 2 | `test_query_pipeline_pii_relaxation.py` code-relaxed + tiny-limit cases |
| AC2 chat relaxed: input unmasked, output masked | 1, 2 | chat-relaxed case |
| AC3 standard/absent: masked, limit enforced, flag 0 | 1 | standard/absent cases |
| AC4 switch off -> false, flag 0; four columns | 1, 2 | switch-off case + 2x2 matrix |
| AC5 patterns unchanged, before step 6 | 1 | pattern-block case |

Plus: output-redaction error row carries flag 1; pre-step-6 rows flag 0; profiles, routing and legacy-fixture tests unedited and green.

## Risks

- The story's Technical Notes line numbers are stale; current ones are cited above.
- The routing module's autouse `_shipped_settings` stubs `redact` with a no-op; the new tests must install their masker after it.
- `relaxes_input()` reads the live setting at call time: set `PII_REDACTION_ENABLED` before the run.
