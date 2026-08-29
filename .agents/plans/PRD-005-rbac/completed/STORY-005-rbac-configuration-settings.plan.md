---
story: STORY-005
prd: PRD-005
slug: rbac-configuration-settings
title: RBAC configuration settings and env vars
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-28
---

# Plan: RBAC configuration settings and env vars

## Summary

This story finishes the `RBAC_*` env-var group that STORY-004 started. `app/config.py` already has `RBAC_DEFAULT_ROLE: str = "user"` (added by STORY-004 because `create-user --role` omitted needed it early). This story adds the three remaining fields PRD Section 9 documents — `RBAC_ENABLED` (bool, default `true`), `RBAC_ROLES_FILE` (str, default empty), and `MODEL_ALLOWLIST` (CSV str) — plus a `model_allowlist_list` property that parses `MODEL_ALLOWLIST` exactly the way `pii_entities_list` already parses `PII_ENTITIES`. No new dependency: `pydantic-settings` already backs `Settings`. `.env.example` gets the same three variables with explanatory comments, kept in the same order as `Settings` so the two stay in lockstep. This is a pure configuration surface — nothing reads these fields yet (STORY-006 reads `RBAC_ENABLED`/`RBAC_DEFAULT_ROLE`, STORY-007 reads `RBAC_ROLES_FILE`, STORY-011 reads `model_allowlist_list`) — so the only behavior under test here is that the fields exist, default correctly, parse correctly, and are documented, not that anything downstream consumes them.

## User Story

As an operator
I want RBAC exposed as environment variables
So that enforcement, the default role, the matrix file, and the model allowlist are per-deployment decisions rather than code changes

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-005-rbac-configuration-settings.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md` — Section 9 (Environment variables), Section 7 (default role→permission matrix table, for `MODEL_ALLOWLIST`'s documented default values)
- Upstream plan: `.agents/plans/PRD-005-rbac/completed/STORY-004-manage-users-cli.plan.md` — Design Note 1: *"STORY-005 adds `RBAC_ENABLED`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST` on top of this field ... no rename, no merge conflict, no rework."* This plan is that promise being kept: `RBAC_DEFAULT_ROLE` is not touched, only added around.

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (extends an existing `Settings` class and an existing `.env.example`; no new module, no existing behavior modified) |
| Complexity | LOW |
| Systems Affected | `app/config.py` (additive), `.env.example` (additive), `tests/test_config.py` (new) |
| Story | STORY-005 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

**Dependency status**: `depends_on: []` — no blockers. STORY-005 is independently startable, confirmed by `.agents/PRDs/PRD-005-rbac/index.md`: *"STORY-005, STORY-008, and STORY-009 are unblocked and can start now."*

**Blocks**: STORY-006 (`authz.py` reads `RBAC_ENABLED` for its bypass branch and `RBAC_DEFAULT_ROLE` for matrix defaults), STORY-011 (server-side model allowlist reads `model_allowlist_list`), STORY-016 (fail-fast startup guard reads `RBAC_ENABLED`).

---

## Skills In Use

None. `.agents/skills/` contains exactly one skill, `frontend-design`, scoped to UI visual design. This story is a backend config change with no UI surface. The story's `skills:` frontmatter field is `[]`.

---

## Patterns to Follow

### CSV-string-plus-property list parsing (the pattern AC2 requires `model_allowlist_list` to match exactly)
```python
# SOURCE: app/config.py:22, 26-27
    PII_ENTITIES: str = "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION"

    @property
    def pii_entities_list(self) -> list[str]:
        return [item.strip() for item in self.PII_ENTITIES.split(",") if item.strip()]
```
`model_allowlist_list` is the same shape: split on `,`, strip whitespace, drop empty segments. `PII_ENTITIES` is consumed downstream as `entities=settings.pii_entities_list` (`app/services/pii_redactor.py:58`) — confirms the property, not the raw string, is what callers are meant to use.

### Existing `RBAC_DEFAULT_ROLE` field this story builds around, untouched
```python
# SOURCE: app/config.py:15-18
    # RBAC (PRD-005). RBAC_DEFAULT_ROLE is needed here for scripts/manage_users.py
    # (STORY-004); RBAC_ENABLED, RBAC_ROLES_FILE, and MODEL_ALLOWLIST are added by
    # STORY-005 on top of this field.
    RBAC_DEFAULT_ROLE: str = "user"
```

### Bool field with a default — same declaration shape pydantic-settings already uses elsewhere in this class
```python
# SOURCE: app/config.py:20
    PII_REDACTION_ENABLED: bool = True
```
`pydantic-settings` parses the string `"true"`/`"false"` (case-insensitive) from `.env` into a Python `bool` automatically — no custom validator needed, matching how `PII_REDACTION_ENABLED` already works.

### `.env.example` — one variable per block, a comment line then the `KEY=value` line
```
# SOURCE: .env.example:19-20
# Master switch for PII redaction on prompts and responses (true/false)
PII_REDACTION_ENABLED=true
```

### Test file bootstrap — mandatory env vars before any `app.*` import
```python
# SOURCE: tests/test_pii_redactor.py:1-9
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
```
Every test module in this repo that imports `app.config` sets these two required fields first, since `Settings()` is instantiated at import time (`app/config.py:30`) and `OPENROUTER_API_KEY`/`ADMIN_TOKEN` have no default.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Add `RBAC_ENABLED: bool = True`, `RBAC_ROLES_FILE: str = ""`, `MODEL_ALLOWLIST: str = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"`, and a `model_allowlist_list` property. |
| `.env.example` | UPDATE | Document the three new variables with explanatory comments, in `Settings` field order. |
| `tests/test_config.py` | CREATE | New test module — full AC coverage (defaults, CSV parsing parity, no-env-vars-set boot, `.env.example` documentation check). |

**Explicitly NOT touched**:
- `app/services/authz.py`, `app/services/query_pipeline.py`, `app/routers/*`, `chat_ui/*` — nothing downstream reads these fields yet (STORY-006/007/011/016's job). The story's Technical Notes say `app/config.py` only.
- `RBAC_DEFAULT_ROLE` — already correct (STORY-004), not renamed, not moved out of the `Settings` class.
- `requirements.txt` — no new dependency; `pydantic-settings` already parses bools and strings.

---

## Design Notes (decisions worth stating up front)

1. **Field order in both files follows PRD Section 9's env-var block, not alphabetical or arrival order**: `RBAC_ENABLED`, `RBAC_DEFAULT_ROLE`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST`. Since `RBAC_DEFAULT_ROLE` already exists mid-block, `RBAC_ENABLED` is inserted immediately above it and `RBAC_ROLES_FILE`/`MODEL_ALLOWLIST` immediately below it — no field is moved, only new ones are added around the existing one, exactly as STORY-004's Design Note 1 anticipated.

2. **`RBAC_ROLES_FILE` defaults to `""`, not `None`.** The story's AC1 types it as `str` with "default empty", and PRD Section 9's env block shows `RBAC_ROLES_FILE=` (present, empty) rather than the variable being absent. An empty string is also what `.env.example` naturally documents for "optional path, empty ⇒ built-in default" without needing `Optional[str]` machinery STORY-007 would then have to unwrap.

3. **`MODEL_ALLOWLIST`'s default value is the literal CSV string from PRD Section 9** (`gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet`) — the same four models `chat_ui/chat_ui/config.py`'s frontend-only `MODEL_ALLOWLIST` list already hardcodes. This is deliberate parity (PRD Appendix: *"backend-side model allowlist specified here supersedes PRD-004's frontend-only list"*), not a coincidence to reconcile later — STORY-011 is what actually wires the backend list in as the control.

4. **`model_allowlist_list` is a property, not a cached value**, matching `pii_entities_list` exactly (`app/config.py:26-27`) — re-splitting a short CSV string on every access is negligible cost and keeps the two properties structurally identical, which is what AC2 asks for ("parsed exactly the way `pii_entities_list` parses `PII_ENTITIES`").

5. **The `.env.example` AC ("matching `Settings` field for field") is verified by a real test, not eyeballed.** `tests/test_config.py` regex-scans `.env.example` for a comment line immediately followed by each new `KEY=` line, so a future edit to one file without the other fails CI rather than drifting silently — there is no existing test in this repo that already does this, so this story adds the first one.

6. **A `Settings(_env_file=None)` instance, not the module-level `settings` singleton, is used to test "no new env vars set" (AC3).** The repo's local `.env` (present, untracked) sets `OPENROUTER_API_KEY`/`ADMIN_TOKEN`/`DATABASE_URL`/`PORT`/`HOST`/`LOG_LEVEL` but none of the new `RBAC_*`/`MODEL_ALLOWLIST` vars — so the module-level `settings` object already exercises the "not set" path for these fields. But asserting that directly would make the test's correctness depend on what happens to be in a developer's local `.env` file. `pydantic-settings` 2.14.2 accepts `_env_file=None` as a per-instance override of `model_config`'s `env_file=".env"`, isolating the construction from both the local `.env` and any `RBAC_*` values a future developer might add to it, while still reading `OPENROUTER_API_KEY`/`ADMIN_TOKEN` from `os.environ` (set at module top per the standard bootstrap pattern) since those have no default and would otherwise raise.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Verify the baseline before writing anything

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `git branch --show-current` → `epic/PRD-005-rbac`.
  - `app/config.py` defines `RBAC_DEFAULT_ROLE: str = "user"` and nothing else `RBAC_*`; no `MODEL_ALLOWLIST` field.
  - `tests/test_config.py` does not exist yet.
  - Full suite is green at **306 passed** (per STORY-004's plan Task 9 handoff).
  - If any of the above differs, stop and re-plan.
- **Mirror**: STORY-004 plan Task 1 (same verification-gate shape)
- **Validate**:
  ```bash
  git branch --show-current
  .venv/Scripts/python.exe -m pytest -q   # 306 passed
  .venv/Scripts/python.exe -c "from app.config import settings; print(settings.RBAC_DEFAULT_ROLE); print(hasattr(settings, 'RBAC_ENABLED'))"
  ```
  expect `user` then `False`

### Task 2: Add `RBAC_ENABLED`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST` to `app/config.py`

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**: Replace the existing RBAC block (lines 15-18) with the full group, `RBAC_ENABLED` before `RBAC_DEFAULT_ROLE`, `RBAC_ROLES_FILE`/`MODEL_ALLOWLIST` after it — `RBAC_DEFAULT_ROLE`'s own line is untouched:
  ```python
      # RBAC (PRD-005). RBAC_DEFAULT_ROLE was added by STORY-004 for
      # scripts/manage_users.py; the rest of this group is added by STORY-005.
      RBAC_ENABLED: bool = True
      RBAC_DEFAULT_ROLE: str = "user"
      RBAC_ROLES_FILE: str = ""
      MODEL_ALLOWLIST: str = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"
  ```
  Then add the parsing property immediately after `pii_entities_list`, at the end of the class:
  ```python
      @property
      def model_allowlist_list(self) -> list[str]:
          return [item.strip() for item in self.MODEL_ALLOWLIST.split(",") if item.strip()]
  ```
- **Mirror**: `app/config.py:22, 26-27` (`PII_ENTITIES` / `pii_entities_list` — identical CSV-plus-property shape); `app/config.py:20` (`PII_REDACTION_ENABLED: bool = True` — identical bool-with-default shape)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -c "from app.config import settings; print(settings.RBAC_ENABLED, settings.RBAC_DEFAULT_ROLE, repr(settings.RBAC_ROLES_FILE), settings.MODEL_ALLOWLIST, settings.model_allowlist_list)"
  ```
  expect `True user '' gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet ['gpt-4', 'claude-3-sonnet', 'openai/gpt-4o', 'anthropic/claude-3.5-sonnet']`

### Task 3: Document the three new variables in `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Insert after the existing `ADMIN_TOKEN` block (line 14) and before `LOG_LEVEL` (line 16) — matching `Settings`' field order, `RBAC_DEFAULT_ROLE` is not yet present in `.env.example` today (STORY-004 added it to `Settings` but not to this file), so this task documents all four RBAC fields together, `RBAC_DEFAULT_ROLE` included:
  ```
  # Deny-by-default RBAC enforcement; false preserves pre-RBAC PRD-001 behavior
  # as a documented migration escape hatch (true/false)
  RBAC_ENABLED=true

  # Role assigned to a user created without an explicit --role
  RBAC_DEFAULT_ROLE=user

  # Optional path to a JSON role->permission matrix; empty uses the built-in default
  RBAC_ROLES_FILE=

  # Comma-separated models callers may request; enforced server-side per role
  MODEL_ALLOWLIST=gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet
  ```
- **Mirror**: `.env.example:19-26` (`PII_REDACTION_ENABLED` / `PII_ENTITIES` blocks — comment line, then `KEY=value`)
- **Validate**:
  ```bash
  grep -n "^RBAC_\|^MODEL_ALLOWLIST" .env.example
  ```
  expect all four keys present, each preceded by a `#` comment line

### Task 4: Tests — `tests/test_config.py` (AC1, AC2, AC3, AC4)

- **File**: `tests/test_config.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import os

  os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
  os.environ.setdefault("ADMIN_TOKEN", "test-token")

  import re
  from pathlib import Path

  from app.config import Settings, settings

  REPO_ROOT = Path(__file__).resolve().parents[1]


  # --- AC1: new fields are available with the documented defaults ---


  def test_rbac_settings_available_with_documented_defaults():
      assert settings.RBAC_ENABLED is True
      assert settings.RBAC_DEFAULT_ROLE == "user"
      assert settings.RBAC_ROLES_FILE == ""
      assert isinstance(settings.MODEL_ALLOWLIST, str)
      assert settings.MODEL_ALLOWLIST != ""


  # --- AC2: model_allowlist_list parses exactly like pii_entities_list ---


  def test_model_allowlist_list_parses_like_pii_entities_list(monkeypatch):
      monkeypatch.setattr(settings, "MODEL_ALLOWLIST", " gpt-4 , ,claude-3-sonnet ,")

      assert settings.model_allowlist_list == ["gpt-4", "claude-3-sonnet"]


  def test_model_allowlist_list_default_matches_prd_default_models():
      assert settings.model_allowlist_list == [
          "gpt-4",
          "claude-3-sonnet",
          "openai/gpt-4o",
          "anthropic/claude-3.5-sonnet",
      ]


  # --- AC3: none of the new vars set -- defaults apply, nothing raises ---


  def test_settings_construct_without_new_env_vars(monkeypatch):
      for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
          monkeypatch.delenv(var, raising=False)

      fresh = Settings(_env_file=None)

      assert fresh.RBAC_ENABLED is True
      assert fresh.RBAC_DEFAULT_ROLE == "user"
      assert fresh.RBAC_ROLES_FILE == ""
      assert fresh.model_allowlist_list  # non-empty


  # --- AC4: .env.example documents every new variable, Settings field for field ---


  def test_env_example_documents_every_new_rbac_var_with_a_comment():
      text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

      for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
          assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


  def test_env_example_rbac_vars_appear_in_settings_field_order():
      text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
      declared_order = ["RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"]

      positions = [text.index(f"{var}=") for var in declared_order]

      assert positions == sorted(positions)
  ```
- **Mirror**: `tests/test_pii_redactor.py:1-9` (env bootstrap before `app.config` import); `app/config.py:22, 26-27` (the parsing behavior under test)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`

### Task 5: Full-suite regression and diff gate

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `.venv/Scripts/python.exe -m pytest tests/test_config.py -v` — count the collected tests (expect **6**) and confirm all pass.
  - `.venv/Scripts/python.exe -m pytest -q` → **312 passed** (306 + 6). Any pre-existing test that now fails is a real regression — this story only adds fields, a property, doc comments, and a new test file.
  - `git status --short` shows exactly: `tests/test_config.py` (new/untracked) and `app/config.py`, `.env.example` (modified) — plus the pre-existing unstaged `README.md`, not this story's concern.
  - `grep -n "RBAC_ENABLED\|RBAC_ROLES_FILE\|MODEL_ALLOWLIST" app/config.py .env.example` — both files reference all three.
- **Mirror**: STORY-004 plan's final task (same regression + diff gate shape)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_config.py -v
  .venv/Scripts/python.exe -m pytest -q
  git status --short
  git diff --name-only
  grep -n "RBAC_ENABLED\|RBAC_ROLES_FILE\|MODEL_ALLOWLIST" app/config.py .env.example
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_config.py -v` — 6 pass
- [ ] `.venv/Scripts/python.exe -m pytest -q` — 312 pass, zero pre-existing failures
- [ ] `git status --short` — only `app/config.py`, `.env.example` (modified) and `tests/test_config.py` (new), plus the pre-existing unstaged `README.md`
- [ ] **Real process boot with no `RBAC_*`/`MODEL_ALLOWLIST` vars set** — confirms AC3 outside pytest, against the actual `Settings()` singleton import path:
  ```bash
  cd /f/AI/harness-ai
  OPENROUTER_API_KEY=test-key ADMIN_TOKEN=test-token .venv/Scripts/python.exe -c "
  import os
  for v in ('RBAC_ENABLED','RBAC_DEFAULT_ROLE','RBAC_ROLES_FILE','MODEL_ALLOWLIST'):
      os.environ.pop(v, None)
  from app.config import settings
  assert settings.RBAC_ENABLED is True
  assert settings.RBAC_DEFAULT_ROLE == 'user'
  assert settings.RBAC_ROLES_FILE == ''
  assert settings.model_allowlist_list
  print('boots clean with defaults')
  "
  ```
  expect `boots clean with defaults`, no traceback
- [ ] `.venv/Scripts/python.exe -c "from app.main import app"` — imports clean, no circular-import issues introduced by the new `Settings` fields
- [ ] Existing behavior untouched: `.venv/Scripts/python.exe -m pytest tests/test_manage_users_cli.py tests/test_pii_redactor.py -q` — all green, unmodified (the two suites most likely to interact with `Settings`)

---

## Validation

```bash
cd /f/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_config.py -v
.venv/Scripts/python.exe -m pytest -q
git status --short
git diff --name-only
grep -n "RBAC_ENABLED\|RBAC_ROLES_FILE\|MODEL_ALLOWLIST" app/config.py .env.example
curl http://localhost:8000/health
```

Frontend lint: **N/A** — this repository has no npm frontend; the UI is Reflex (Python) and this story does not touch it.

---

## Handoff to downstream stories

- **STORY-006** (`authz.py`) reads `settings.RBAC_ENABLED` for its deny-by-default bypass branch and `settings.RBAC_DEFAULT_ROLE` for matrix-default reasoning. Both fields exist and default correctly after this story; STORY-006's `depends_on: [STORY-003, STORY-005]` is satisfied once this lands.
- **STORY-007** (roles-file override) reads `settings.RBAC_ROLES_FILE`; empty string is the documented "use the built-in default" sentinel this story establishes.
- **STORY-011** (server-side model allowlist / BYOK) reads `settings.model_allowlist_list`, already parsed and ready to intersect against a role's allowlist.
- **STORY-016** (fail-fast startup guard) reads `settings.RBAC_ENABLED` to decide whether the guard runs at all.
- **Not delivered, by design**: no code path reads any of these fields yet — that is each downstream story's own job, per the story's Technical Notes ("`app/config.py` only").

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `.env`, when `Settings` loads, then `RBAC_ENABLED` (bool, default `true`), `RBAC_DEFAULT_ROLE` (str, default `user`), `RBAC_ROLES_FILE` (str, default empty), and `MODEL_ALLOWLIST` (CSV str) are all available — *Task 2, 4*
- [ ] Given `MODEL_ALLOWLIST`, when read via a `model_allowlist_list` property, then it is parsed exactly the way `pii_entities_list` parses `PII_ENTITIES` — *Task 2, 4*
- [ ] Given none of the new variables are set, when the app starts, then the documented defaults apply and nothing raises — *Task 2, 4*
- [ ] Given `.env.example`, when read, then every new variable is present with an explanatory comment, matching `Settings` field for field — *Task 3, 4*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Full pytest suite green (6 in `tests/test_config.py`, 312 overall)
- [ ] No new dependency in `requirements.txt`
- [ ] Follows existing patterns
