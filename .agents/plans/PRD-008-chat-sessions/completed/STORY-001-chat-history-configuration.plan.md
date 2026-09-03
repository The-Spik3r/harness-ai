---
story: STORY-001
prd: PRD-008
slug: chat-history-configuration
title: "CHAT_HISTORY_ENABLED and CHAT_SESSION_LIMIT settings, with the off state documented as supported"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-03
---

# Plan: CHAT_HISTORY_ENABLED and CHAT_SESSION_LIMIT settings, with the off state documented as supported

## Summary

Declare two settings in `app/config.py` — `CHAT_HISTORY_ENABLED: bool = True` and `CHAT_SESSION_LIMIT: int = 50` — as a commented group naming PRD-008, in the shape the `RBAC_*` and `PII_*` blocks already use, and guard the limit with a `field_validator` that refuses anything below 1 with a message naming the setting. Document both in `.env.example`, with the off state spelled out in the comment: no transcript written, none read, chat behaves as it did before this PRD. Extend `tests/test_config.py` with cases for the default, the string `"false"`, the rejected limit, and the `.env.example` documentation — reusing the `_settings()` helper at `tests/test_config.py:95-97` and leaving every existing assertion untouched.

Nothing reads these settings. That is the story's sharpest constraint and it is deliberate: `app/services/chat_sessions.py` in STORY-006 is the only consumer, and wiring a reader here would move the flag's observable behaviour into a story whose diff cannot demonstrate it. The value delivered here is that the mitigation for the PRD's largest risk (Risk 1, Section 9) exists in the tree before any of the twenty-one stories that widen the disclosure surface — a mitigation added last is a mitigation someone argues out of scope.

The diff is small; the exploration confirmed why each piece has to be shaped exactly this way. There is no `Field(ge=...)` anywhere in the repo, so a validator is the house idiom rather than a preference. There is no linter and no formatter — CI runs `pip install -r requirements.txt` then `pytest -q` and nothing else (`.github/workflows/ci.yml:59,62`) — so "validate" here means the suite, and the suite needs the local libSQL dev server that `tests/conftest.py:26-31` documents.

## User Story

As a **security admin**
I want transcript persistence to be a setting I control
So that a deployment that must not hold prompt text can run this build with the feature off, from the same image, rather than maintaining a fork.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-001-chat-history-configuration.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Configuration), Section 5 (story 7), Section 9 (Security & Configuration, incl. the new-variables table), Section 12 Phase 1, Section 14 Risk 1
- Acceptance bar, verbatim from Section 9: "`CHAT_HISTORY_ENABLED=false` turns the feature off entirely — no write, no read, no rail — and the deployment gets today's ephemeral behaviour from the same image. A deployment that cannot hold prompt text has a supported configuration rather than a fork."

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (configuration surface only) |
| Complexity | LOW — three files, no consumer, no runtime behaviour change |
| Systems Affected | `app/config.py`, `.env.example`, `tests/test_config.py` |
| Story | STORY-001 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It contains exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story touches `app/config.py`, `.env.example` and `tests/`. It renders nothing. |

The story's `skills:` frontmatter is `[]` and its Technical Notes reach the same conclusion independently. **No skill constrains any task below**, and no task names one.

---

## Patterns to Follow

### Naming — a settings group is introduced by a comment naming the PRD that added it

```python
# SOURCE: app/config.py:64-74
    # RBAC (PRD-005). RBAC_DEFAULT_ROLE was added by STORY-004 for
    # scripts/manage_users.py; the rest of this group is added by STORY-005.
    RBAC_ENABLED: bool = True
    RBAC_DEFAULT_ROLE: str = "user"
    RBAC_ROLES_FILE: str = ""
    MODEL_ALLOWLIST: str = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"

    PII_REDACTION_ENABLED: bool = True
    PII_SCORE_THRESHOLD: float = 0.35
    PII_ENTITIES: str = "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION"
    PII_NLP_MODEL: str = "en_core_web_lg"
```

Both existing feature flags are `bool = True` — the guard is on unless something deliberately turns it off. `CHAT_HISTORY_ENABLED` follows that, and for the same stated reason `DB_BOOTSTRAP_ENABLED` gives at `app/config.py:45-58`: a default of `False` would make the escape hatch the norm.

### Error handling — a validator that names the setting and offers the remedy

```python
# SOURCE: app/config.py:76-98
    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        """A libSQL endpoint, or a startup error -- never a file (PRD-007)."""
        url = value.strip()
        scheme = _scheme_of(url).lower()

        if scheme.startswith(_SQLITE_SCHEME):
            raise ValueError(
                "DATABASE_URL must name a libSQL endpoint, not a file. Replace the "
                ...
            )
```

Three properties to copy: a leading underscore on the method name, a one-line docstring stating the rule and citing the PRD, and a message that opens with the setting's own name. Wording for the bound itself comes from the only other "at least 1" message in the repo:

```python
# SOURCE: scripts/migrate_to_turso.py:780-784
    if args.batch_size < 1:
        print("Error: --batch-size must be at least 1.", file=sys.stderr)
```

**Why a validator and not `Field(ge=1)`**: the repo contains no `Field(...)` constraint anywhere — zero uses of `ge=`/`gt=`/`le=`. The two validators in `app/config.py` are the entire precedent, and the story's Technical Notes name `_validate_database_url` explicitly as the model to follow.

### Tests — construct `Settings` explicitly, never read the process environment

```python
# SOURCE: tests/test_config.py:95-97
def _settings(**overrides) -> Settings:
    base = {"OPENROUTER_API_KEY": "test-key", "ADMIN_TOKEN": "test-token"}
    return Settings(_env_file=None, **{**base, **overrides})
```

```python
# SOURCE: tests/test_config.py:267-273
def test_db_bootstrap_enabled_can_be_turned_off_for_the_build():
    result = _settings(DATABASE_URL=_LOCAL_URL, DB_BOOTSTRAP_ENABLED="false")

    assert result.DB_BOOTSTRAP_ENABLED is False
```

`_settings()` supplies no `DATABASE_URL`, so every call passes `_LOCAL_URL` (`tests/test_config.py:92`) — exactly as the `DB_BOOTSTRAP_ENABLED` pair at `:257-273` does. `_env_file=None` keeps a developer's real `.env` from deciding whether a test passes (rationale at `tests/test_config.py:80-86`).

```python
# SOURCE: tests/test_config.py:64-68
def test_env_example_documents_every_new_rbac_var_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in ("RBAC_ENABLED", ...):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"
```

Note the regex shape: the comment line must sit **immediately** above the assignment, with no blank line between. The `.env.example` block in Task 2 is written to satisfy it.

```python
# SOURCE: tests/test_config.py:103-106
    with pytest.raises(ValidationError) as exc_info:
        _settings(DATABASE_URL=url, TURSO_AUTH_TOKEN="")

    assert "TURSO_AUTH_TOKEN" in str(exc_info.value)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | Declare the two fields as a PRD-008 group after the `PII_*` block; add `_validate_chat_session_limit`. |
| `.env.example` | UPDATE | Document both variables with defaults and what the off state does, appended after `PII_NLP_MODEL` to keep file order matching field order. |
| `tests/test_config.py` | UPDATE | Append a PRD-008 section: default, explicit `"false"`, rejected limit, accepted boundary, `.env.example` documentation. |

Nothing else. Explicitly **not** touched, and each for a stated reason:

- `README.md:268-291` (the environment table) — STORY-022 owns it; one docs commit at the end, when the behaviour is real.
- `docker-compose.yml`, `Dockerfile` — both settings default on and need no deployment change; the builder stage's only flag is `DB_BOOTSTRAP_ENABLED=false`.
- Any consumer (`app/services/`, `chat_ui/`, `app/db/database.py`) — STORY-006 is the sole reader. Confirmed by search: `CHAT_HISTORY_ENABLED` and `CHAT_SESSION_LIMIT` appear nowhere in `app/`, `chat_ui/`, `scripts/`, `tests/`, `.env.example`, `README.md`, `Dockerfile` or `docker-compose.yml` today.

---

## Dependency Order

Task 1 (fields + validator) → Task 2 (`.env.example`) → Task 3 (tests) → Task 4 (full suite). Tasks 1 and 2 are independent of each other in principle; keeping the order above means the field-order convention in Task 2 is written against a file that already declares the fields.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Declare the two settings and the limit validator

- **File**: `app/config.py`
- **Action**: UPDATE
- **Implement**:
  1. After `PII_NLP_MODEL` (`app/config.py:74`), leave one blank line and add the group:

     ```python
     # Chat sessions (PRD-008). CHAT_HISTORY_ENABLED is the master switch for
     # transcript persistence: false means no chat_sessions or chat_messages row
     # is written, none is read, and the chat behaves as it did before this PRD
     # (PRD-008 Section 9, Risk 1). CHAT_SESSION_LIMIT caps how many sessions the
     # rail lists per user. Nothing reads either setting yet -- STORY-006's
     # app/services/chat_sessions.py is the only consumer.
     CHAT_HISTORY_ENABLED: bool = True
     CHAT_SESSION_LIMIT: int = 50
     ```

     Indented one level, inside `class Settings`. Field order matters: these go **after** the PII block so `.env.example` can append its block at the end and still mirror declaration order.
  2. After `_require_token_for_remote_endpoint` (ends `app/config.py:113`) and before the `@property` block at `:115`, add:

     ```python
     @field_validator("CHAT_SESSION_LIMIT")
     @classmethod
     def _validate_chat_session_limit(cls, value: int) -> int:
         """At least one session, or a startup error (PRD-008).

         A limit of 0 renders an empty rail on a user who has sessions, which is
         a silent lie rather than a small list -- so it fails at startup the way
         a bad DATABASE_URL does, rather than being defaulted away.
         """
         if value < 1:
             raise ValueError(
                 f"CHAT_SESSION_LIMIT must be at least 1, got {value}. It is the "
                 "number of sessions the rail lists per user; 0 would render an "
                 "empty rail for a user who has sessions. To turn transcript "
                 "persistence off, set CHAT_HISTORY_ENABLED=false instead."
             )
         return value
     ```
- **Mirror**: `app/config.py:64-74` for the group's comment-and-fields shape; `app/config.py:76-98` for the validator's name, docstring and message shape; `scripts/migrate_to_turso.py:780-784` for the "must be at least 1" wording.
- **Do not**: add a `field_validator` for `CHAT_HISTORY_ENABLED` (pydantic already parses `"false"`), add `Field(ge=1)` (no precedent in the repo), or read either setting anywhere.
- **Validate**: `python -c "from app.config import Settings; s = Settings(_env_file=None, OPENROUTER_API_KEY='k', ADMIN_TOKEN='t', DATABASE_URL='http://127.0.0.1:8080'); print(s.CHAT_HISTORY_ENABLED, s.CHAT_SESSION_LIMIT)"` → prints `True 50`.

### Task 2: Document both variables in `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: append after `PII_NLP_MODEL=en_core_web_lg` (`.env.example:55`), separated by one blank line:

  ```
  # Master switch for chat transcript persistence (true/false). false writes no
  # transcript, reads none, shows no session rail, and the chat behaves exactly
  # as it did before PRD-008 - the supported configuration for a deployment that
  # must not hold prompt text at rest
  CHAT_HISTORY_ENABLED=true

  # Maximum sessions listed per user in the rail; must be at least 1
  CHAT_SESSION_LIMIT=50
  ```

  Two constraints the file's own tests impose, both easy to violate: the comment block must end on the line **immediately** above the `VAR=` line with no blank between (regex at `tests/test_config.py:64-68`), and the two entries must appear in declaration order (`CHAT_HISTORY_ENABLED` before `CHAT_SESSION_LIMIT`, both after the PII block), matching the ordering convention asserted at `tests/test_config.py:71-77` and `:238-244`.
- **Mirror**: the `PII_REDACTION_ENABLED` entry at `.env.example:45-47` (a flag whose comment states what the off state does) and the `DB_BOOTSTRAP_ENABLED` entry at `.env.example:15-21` (a multi-line comment spelling out consequences).
- **Validate**: `grep -n -A1 "^# Master switch for chat" .env.example` shows the comment line immediately followed by `CHAT_HISTORY_ENABLED=true`.

### Task 3: Extend `tests/test_config.py`

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append only — every existing assertion stays byte-for-byte)
- **Implement**: append a new section after line 273, headed `# --- PRD-008 STORY-001: chat transcript persistence settings ---`, with:
  1. `test_chat_history_settings_available_with_documented_defaults` — `_settings(DATABASE_URL=_LOCAL_URL)`; assert `.CHAT_HISTORY_ENABLED is True` (identity, not truthiness — mirrors `:265`) and `.CHAT_SESSION_LIMIT == 50`. Covers AC 1.
  2. `test_chat_history_can_be_turned_off_with_the_string_false` — `_settings(DATABASE_URL=_LOCAL_URL, CHAT_HISTORY_ENABLED="false")`; assert `is False`. The string, not the bool, because that is what an `.env` file and a Docker `environment:` block actually supply. Covers AC 3. Mirror `tests/test_config.py:267-273`.
  3. `test_a_chat_session_limit_below_one_is_a_startup_error` — `@pytest.mark.parametrize("limit", [0, -1, "0"])`, each in `pytest.raises(ValidationError)`, asserting `"CHAT_SESSION_LIMIT" in str(exc_info.value)`. `"0"` is included because the environment supplies strings and the coercion happens before the validator. Covers AC 2.
  4. `test_a_chat_session_limit_of_one_is_accepted` — the boundary on the accepted side, so a validator written as `<= 1` fails here rather than in STORY-006.
  5. `test_settings_construct_without_the_chat_vars` — `monkeypatch.delenv` both names, then `_settings(DATABASE_URL=_LOCAL_URL)`; assert the defaults. Guards against a developer's exported `CHAT_SESSION_LIMIT` making test 1 pass or fail for the wrong reason. Mirror `tests/test_config.py:48-58`.
  6. `test_env_example_documents_both_chat_vars_with_a_comment` — the `rf"(?m)^#.+\n{var}="` loop over both names. Covers AC 4's presence half. Mirror `:224-228`.
  7. `test_env_example_chat_vars_appear_in_settings_field_order` — mirror `:238-244`.
  8. `test_env_example_says_what_the_off_state_does` — read `.env.example`, assert the comment block above `CHAT_HISTORY_ENABLED=` is non-trivial about the off state: it names `false` and states that nothing is written and nothing is read. Keep the assertion on the substance the AC names ("no transcript is written, none is read, and the chat behaves as it did before this PRD") rather than on an exact sentence, so a later wording fix does not turn into a red test. Covers AC 4's content half.
- **Do not**: modify or reorder any existing test, and do not add a consumer-level test (no service reads the flag yet — STORY-006 and STORY-021 own that proof).
- **Mirror**: `tests/test_config.py:255-273` (the `DB_BOOTSTRAP_ENABLED` pair) for the whole section's shape; `:95-97` for construction; `:103-106` for the `ValidationError` assertion.
- **Validate**: `pytest -q tests/test_config.py` — all pass, and `git diff --stat tests/test_config.py` shows insertions only (`0 deletions`), which is AC 5's "existing assertions pass unmodified" made mechanical.

### Task 4: Full suite, unmodified

- **File**: none
- **Action**: VERIFY
- **Implement**: run the whole suite the way CI does. It needs the local libSQL dev server; `tests/conftest.py:104-121` exits with the exact `docker run` line if it is unreachable:

  ```
  docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
    ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
  ```
- **Validate**: `pytest -q` → green, with no test outside `tests/test_config.py` touched. There is no lint or format step in this repo (no `pyproject.toml`, no ruff/black config; `.github/workflows/ci.yml:59,62` runs `pip install` then `pytest -q` and nothing else), so the suite **is** the gate.

---

## End-to-End Tests

- [ ] `python -c "from app.config import settings; print(settings.CHAT_HISTORY_ENABLED, settings.CHAT_SESSION_LIMIT)"` with the repo `.env` in place → `True 50`; the module still imports, which is the real risk of touching a file that constructs `Settings()` at import (`app/config.py:124`).
- [ ] `CHAT_HISTORY_ENABLED=false python -c "from app.config import settings; assert settings.CHAT_HISTORY_ENABLED is False"` → exits 0. The environment path, not just the constructor path.
- [ ] `CHAT_SESSION_LIMIT=0 python -c "import app.config"` → non-zero exit, and stderr names `CHAT_SESSION_LIMIT`. Startup fails, as AC 2 requires, rather than defaulting away.
- [ ] `CHAT_SESSION_LIMIT=1 python -c "import app.config"` → exits 0 (the accepted boundary).
- [ ] `pytest -q` → full suite green against the libSQL dev server.
- [ ] `git diff --stat` shows exactly three files changed and no deletions in `tests/test_config.py`.

---

## Validation

```bash
# The suite is the gate -- this repo has no linter and no formatter.
pytest -q tests/test_config.py
pytest -q

# Insertions only in the test file (AC 5).
git diff --stat tests/test_config.py

# The two startup paths the story is actually about.
CHAT_HISTORY_ENABLED=false python -c "from app.config import settings; assert settings.CHAT_HISTORY_ENABLED is False; print('off state ok')"
CHAT_SESSION_LIMIT=0 python -c "import app.config" ; echo "expected non-zero: $?"
```

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| **Scope creep into a consumer.** The natural instinct on adding a flag is to make something read it; doing so here would put the flag's behaviour in a diff that cannot show it working, and would collide with STORY-006. | Task 1 states "do not read either setting anywhere"; the Files to Change table lists three files and names the owner of every file deliberately left alone. |
| **A `.env.example` edit that silently breaks an existing test.** The documentation tests match a comment line *immediately* above the assignment and assert file order mirrors field order; a stray blank line or an entry placed above the PII block turns AC 5 red. | Task 2 pins both constraints with the asserting line numbers, and Task 3 adds the order test for the new pair so the convention is enforced rather than remembered. |
| **The validator accepts a string `"0"`.** Pydantic coerces before validating, so `CHAT_SESSION_LIMIT=0` from an `.env` arrives as `int` — but a reader may assume the validator sees the raw string and write `if not value` or a string comparison. | Task 3 parametrizes the rejection test over `0`, `-1` and `"0"`, so a validator that only handles one of them fails. |
| **`app/config.py` constructs `Settings()` at import (`:124`).** A malformed default or a validator that raises on the default value breaks collection for the entire suite, not just `test_config.py`. | Task 1's inline validation command runs before any test; Task 4 runs the full suite, where a broken import is unmissable. |
| **The suite needs a running libSQL server**, so "tests fail" can mean "no database" rather than "bad code". | Task 4 quotes the `docker run` line from `tests/conftest.py`, which `pytest.exit` also prints on an unreachable endpoint. |

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given `app/config.py`, when `Settings` is read, then `CHAT_HISTORY_ENABLED: bool = True` and `CHAT_SESSION_LIMIT: int = 50` are declared, grouped and commented in the style of the `RBAC_*` and `PII_*` blocks already there.
- [ ] Given `CHAT_SESSION_LIMIT`, when a value below 1 is supplied, then startup fails with a message naming the setting — a limit of 0 renders an empty rail on a user who has sessions, which is a silent lie rather than a small list.
- [ ] Given `CHAT_HISTORY_ENABLED=false` in the environment, when settings load, then `settings.CHAT_HISTORY_ENABLED is False` — asserted with the string `"false"`, since that is what an `.env` file and a Docker `environment:` block actually supply.
- [ ] Given `.env.example`, when it is read, then both variables appear with their defaults and a comment stating what the off state does: no transcript is written, none is read, and the chat behaves as it did before this PRD.
- [ ] Given `tests/test_config.py`, when the suite runs, then the existing assertions pass unmodified and new ones cover the default, the explicit `false`, and the rejected limit.
- [ ] All tasks completed
- [ ] Full `pytest -q` suite green (this repo has no lint step)
- [ ] `app.config` still imports — `Settings()` is constructed at import time
- [ ] Follows existing patterns (`app/config.py:64-98`, `tests/test_config.py:95-97,255-273`)
- [ ] No file outside the three listed is touched; `README.md` is left to STORY-022
