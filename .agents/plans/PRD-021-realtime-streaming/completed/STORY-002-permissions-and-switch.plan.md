---
story: STORY-002
prd: PRD-021
slug: permissions-and-switch
title: Stream permissions and the STREAMING_ENABLED switch
type: NEW_CAPABILITY
complexity: small
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: Stream permissions and the STREAMING_ENABLED switch

## Summary

Declare two permissions in `authz.py` (`stream:realtime`, `reasoning:view`), union them into `_KNOWN_PERMISSIONS` the way `ACTION_PERMISSIONS` is, leave the built-in matrix untouched with a comment saying why, and declare three settings in `config.py` (`STREAMING_ENABLED=False`, `STREAM_HOLDBACK_MAX_CHARACTERS=400` in 100..4000, `STREAM_COALESCE_MS=50` in 0..500) with startup validators. Nothing reads the settings yet. Tests extend `tests/test_authz.py` and `tests/test_config.py`; one existing authz test must change (see Guard scan).

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-002-permissions-and-switch.md`
- PRD sections used: F1 (7), 9.1, 9.3, D1, D2
- Systems affected: `app/services/authz.py`, `app/config.py`, two test files

## Design Decisions

none beyond the tasks (not a critical story; no design points). Binding rules from the brief: grants are read with `holds()`, never `authorize()` (T8); no built-in role holds either permission, `admin` included; settings are declared only (D2: off means today).

## Guard scan (orchestrator's request)

Grepped `tests/` for `_KNOWN_PERMISSIONS`, `ACTION_PERMISSIONS`, `ROLE_PERMISSIONS`, `.env.example`, `model_fields`:

| Guard | Verdict |
|---|---|
| `tests/test_authz.py:285-289` `test_known_permissions_are_the_original_five_plus_the_six`: asserts `_KNOWN_PERMISSIONS == set(ALL_PERMISSIONS) | ACTION_PERMISSIONS` and `len(...) == 11` | **BREAKS** (13 after this story). Must be updated; the story AC "pass unchanged" cannot hold for this one test (report as a deviation) |
| `tests/test_authz.py:67-83` matrix tests (admin == `set(ALL_PERMISSIONS)`, auditor, user exact sets) and `:298-300` built-in roles | Pass unchanged; they prove the matrix is untouched. `ALL_PERMISSIONS` (`:37`) stays the original five |
| `tests/test_authz.py:292-295` no built-in role holds an action permission | Pass unchanged; add a sibling for `STREAM_PERMISSIONS` |
| `tests/test_action_corpus.py:285,356-358`, `tests/test_action_config.py:190` use `ACTION_PERMISSIONS` only | Unaffected. Do NOT add the new names to `ACTION_PERMISSIONS`: `action_config.py:437` validates rule `grant`s against it |
| `test_audit_characterization.py:134`, `test_action_*` monkeypatch `ROLE_PERMISSIONS`; `provider_registry.py:286` reads role names | Unaffected |
| `.env.example` guards (`tests/test_config.py:64-1568`, `tests/test_providers_docs.py:59-80`) | Every guard is per-variable-set (`_V1_VARS`, `_ACTION_VARS`, ...) or checks that documented names exist in `Settings`. None requires every `Settings` field to appear in `.env.example`. **No `.env.example` change here**; STORY-016 adds it (PRD-015 precedent: `tests/test_config.py:1235-1239`) |

## Skills In Use

`.agents/skills/` holds only `frontend-design` (not applicable); the story's `skills:` is empty. None.

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Constants + frozenset | `authz.py:20-42` | PRD-cited comment, `PERMISSION_*` names, closed `frozenset` |
| Known set union | `authz.py:44-53` | add `*STREAM_PERMISSIONS,` with a "Known, so RBAC_ROLES_FILE can grant them (PRD-021 D1)" comment |
| Matrix comment | `authz.py:55-60` | extend with the PRD-021 D1 rationale; add nothing to any role set |
| Declared-only setting | `config.py:378-388` | "Nothing reads these yet -- each names its consumer story" comment block |
| Range validator | `config.py:493-509` (int), `:736-752` (message shape) | `@field_validator`, `ValueError` naming the variable, got value, range, Example |
| Config tests | `tests/test_config.py:1241-1292`, helper `_settings` (`:95-97`) | `monkeypatch.delenv`, parametrized out-of-range, `pytest.raises(ValidationError)` |
| Authz tests | `tests/test_authz.py:274-345`, fixture `_reset_role_permissions` (`:131`) | literal-value constants test, `load()` of a tmp roles file, `holds` with RBAC on/off |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/authz.py` | UPDATE | constants, `STREAM_PERMISSIONS`, `_KNOWN_PERMISSIONS` union, matrix comment |
| `app/config.py` | UPDATE | three fields + two validators |
| `tests/test_authz.py` | UPDATE | new PRD-021 block; fix the `len == 11` guard |
| `tests/test_config.py` | UPDATE | new PRD-021 STORY-002 block |

## Tasks

### Task 1: Permissions in authz.py
- **File**: `app/services/authz.py`
- **Implement**: after `ACTION_PERMISSIONS` (`:42`) add `PERMISSION_STREAM_REALTIME = "stream:realtime"`, `PERMISSION_REASONING_VIEW = "reasoning:view"` and `STREAM_PERMISSIONS = frozenset({...})`, with short comments (PRD-021 F1, D1; read with `holds()`, T8). Add `*STREAM_PERMISSIONS,` inside `_KNOWN_PERMISSIONS` (`:44-53`). Extend the comment above `ROLE_PERMISSIONS` (`:55-60`): no built-in role holds either, `admin` included; who may read unfinished model output is a deployment decision, granted only through `RBAC_ROLES_FILE` (PRD-021 D1). Leave the matrix dict, `load()` (its check at `:123-128` already accepts known names) and `holds()` alone.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_authz.py`

### Task 2: Settings in config.py
- **File**: `app/config.py`
- **Implement**: after the V1 fields (`:388`) add a comment block "Real-time streaming (PRD-021 Section 9.3, D2). Nothing reads these yet: STORY-005 reads STREAMING_ENABLED, STORY-008 the hold-back bound, STORY-010 the coalesce interval." Fields: `STREAMING_ENABLED: bool = False`, `STREAM_HOLDBACK_MAX_CHARACTERS: int = 400`, `STREAM_COALESCE_MS: int = 50`. Add `_validate_stream_holdback_max_characters` (`100 <= v <= 4000`) and `_validate_stream_coalesce_ms` (`0 <= v <= 500`) beside `_validate_v1_sse_keepalive_seconds` (`:736`), messages in its shape, e.g. `"STREAM_COALESCE_MS must be between 0 and 500, got {value}. ... Example: STREAM_COALESCE_MS=50."`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_config.py`

### Task 3: authz tests
- **File**: `tests/test_authz.py`
- **Implement**: new block `# --- PRD-021 STORY-002 ...` after the PRD-016 block (extend imports):
  - literal values of both constants; `STREAM_PERMISSIONS` is a frozenset of exactly both; both in `_KNOWN_PERMISSIONS`; disjoint from `ACTION_PERMISSIONS`;
  - parametrized over admin/auditor/user: `ROLE_PERMISSIONS[role].isdisjoint(STREAM_PERMISSIONS)`;
  - `load()` with a tmp roles file granting `stream:realtime` (and separately `reasoning:view`) to `dba` is accepted (`_reset_role_permissions`); `holds` true for `dba`, false for `user`/`admin`; a misspelling (`stream:realtim`) is refused naming it;
  - `holds()` false for every built-in role and both permissions with `RBAC_ENABLED` False and True (T8); plus a contrast: `authorize()` with RBAC off returns None for the same pair, documenting why `holds()` is mandatory.
  - **Update** `test_known_permissions_are_the_original_five_plus_the_six` (`:285-289`): expected `set(ALL_PERMISSIONS) | ACTION_PERMISSIONS | STREAM_PERMISSIONS`, `len == 13`, with a comment citing PRD-021 D1. Keep the function name (no rename, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry).
- **Validate**: as Task 1.

### Task 4: config tests
- **File**: `tests/test_config.py`
- **Implement**: new block after the PRD-015 STORY-003 one (header: nothing reads these; `.env.example` is STORY-016's): defaults with the env vars deleted (`STREAMING_ENABLED is False`, 400, 50); `STREAMING_ENABLED="true"` parses to `True`; holdback out of range (99, 4001, 0, -1) and coalesce out of range (-1, 501) raise `ValidationError` whose message contains the variable name and `got <value>`; bounds accepted (100, 4000; 0, 500). Reuse `_settings(DATABASE_URL=_LOCAL_URL, ...)`.
- **Validate**: as Task 2.

## End-to-End Tests

- [ ] `from app.main import app` imports with the new settings (no consumer, so no route behaviour changes)
- [ ] The real `load()` of a tmp `RBAC_ROLES_FILE` granting `stream:realtime` (Task 3) is the E2E for the grant path; no `chat_ui` change

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_authz.py tests/test_config.py tests/test_providers_docs.py tests/test_untouched_app.py
```
`test_providers_docs.py` is included because it cross-checks documented names against `Settings`. No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed. Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 constants, frozenset, known set | 1, 3 | new stream-permission constants test; updated `test_known_permissions_are_the_original_five_plus_the_six` |
| AC2 no built-in role holds either; comment | 1, 3 | new parametrized no-built-in-role test; existing `test_built_in_roles_are_exactly_the_three_parametrized` |
| AC3 file grant accepted; `holds()` role-only; RBAC off false (T8) | 3 | new `load()` grant tests and `holds()` RBAC on/off tests |
| AC4 defaults, ranges, message names the variable | 2, 4 | new STORY-002 block in `tests/test_config.py` |
| AC5 existing tests pass | 3 | both files whole; one assertion pair (`test_authz.py:288-289`) updated by necessity (13 known permissions) |

## Risks

- AC5 "unchanged" conflicts with `tests/test_authz.py:288-289`; the change is minimal and cites PRD-021 D1. The orchestrator should accept it as a deviation.
- Do not append the new names to the test's `ALL_PERMISSIONS` (`:37`): the admin matrix test (`:68`) would then fail.
