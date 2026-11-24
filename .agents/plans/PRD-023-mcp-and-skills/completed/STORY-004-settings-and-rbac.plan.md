---
story: STORY-004
prd: PRD-023
slug: settings-and-rbac
title: "MCP settings and RBAC vocabulary: `mcp:connect` and `skill:<id>`"
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: MCP settings and RBAC vocabulary

## Summary

Add the nine `MCP_*` settings to `app/config.py` (validators in the PRD-021 `STREAM_*` style, plus a normalizing parser for `MCP_ALLOWED_ORIGINS`), and teach `app/services/authz.py` the `mcp:connect` permission (a normal known permission held by built-in `admin` and `user`) and the dynamic `skill:<id>` family (accepted only by `load()`, by full-match of one pattern). Document the nine settings in `.env.example`. Nothing reads the new settings yet; no route, no `mcp_config`, no docs/ edits.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-004-settings-and-rbac.md`
- PRD sections used: §4 (RBAC, Settings), §9.1, §9.3 (settings table), D6, O1
- Systems affected: `app/config.py`, `app/services/authz.py`, `.env.example`, `tests/test_authz.py`, `tests/test_config.py`

## Design Decisions (binding, from the orchestrator)

- **`skill:<id>` is a dynamic family.** `authz.load()` accepts a permission only if `re.fullmatch(r"skill:[a-z0-9][a-z0-9-]{0,47}", p)`; any other string starting `skill:` is an `AuthzConfigError` naming the file, the role and the rule. Use `fullmatch`, not `^...$` (a `$` also matches before a trailing `\n`; add a `"skill:ok\n"` case). Never added to `_KNOWN_PERMISSIONS` as literals. Existence of the skill is STORY-007's.
- **`authorize()` is never called with `skill:*`**; visibility uses `holds()` (no `RBAC_ENABLED` bypass). `authorize()` and `holds()` bodies are unchanged. Tests prove `holds()` on `skill:x` is False with RBAC off and the built-in matrix.
- **`mcp:connect`** joins `_KNOWN_PERMISSIONS` through a new group; `admin` and `user` hold it (O1); `auditor` does not; no built-in role holds any `skill:*` (D6).
- **`MCP_ALLOWED_ORIGINS`** is stored as a `str` field (like `V1_TOOL_MODELS`) validated at construction; a property returns the normalized tuple. Normalized form `scheme://host[:port]`: lowercase, no trailing slash, no path. A path (anything beyond a lone `/`), wildcard (`*`), missing scheme, non-`http(s)` scheme, query, fragment or userinfo is a validation error naming the setting and the entry. `""` gives `()`. Duplicates dropped, order kept. Small judgement call, flag to orchestrator: a default port (`:80` on http, `:443` on https) is dropped, because browsers serialize `Origin` without it and an entry with it could never match.
- **Settings read per request by callers**, passed in. No new module reads `settings` at import; this story adds none.
- Bounds (§9.3): `MCP_CALL_TIMEOUT_SECONDS` 1-600 (int); `MCP_MAX_REQUEST_BYTES` >= 1024; `MCP_MAX_RESULT_BYTES` >= 1024; `MCP_TOOLS_CACHE_SECONDS` 0-86400; `MCP_UPSTREAM_SESSION_IDLE_SECONDS` >= 10; `MCP_LINK_WINDOW_SECONDS` 0-86400. All int. `MCP_ENABLED` bool False; `MCP_CONFIG_FILE` str "" (no cross-check here: `mcp_config.load()` owns "enabled needs a file", STORY-007).

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Permission group | `app/services/authz.py:20-57` | constant(s) + `frozenset` group + header comment citing PRD and "no built-in role holds"; `holds()` note at :44-48 |
| Known set | `app/services/authz.py:59-70` | `*GROUP` spread with a one-line comment |
| load() errors | `app/services/authz.py:142-147` | `AuthzConfigError(f"RBAC_ROLES_FILE '{path_str}' ...")`; matrix replaced only after every check, `ROLE_PERMISSIONS = matrix` last (:149) |
| Settings fields | `app/config.py:404-409` | comment block citing PRD section, then typed fields with defaults |
| Int range validator | `app/config.py:812-836` | `@field_validator` + `@classmethod`, message "NAME must be between a and b, got v. <what it is>. Example: NAME=v." |
| Comma-list setting | `app/config.py:115-117, 765-795, 965-967` | `_split_comma_list`, validator returning the raw string, `*_list` property |
| Settings tests | `tests/test_config.py:1710-1770` | `_settings(DATABASE_URL=_LOCAL_URL, ...)`, `monkeypatch.delenv` for defaults, parametrized out-of-range cases asserting the var name in the message |
| authz tests | `tests/test_authz.py:300-345, 380-420` | `_reset_role_permissions` fixture, roles file under `tmp_path`, `monkeypatch.setattr(settings, "RBAC_ROLES_FILE", ...)` |
| .env.example | `.env.example:219-232` | `# comment` line(s) directly above each `VAR=`; `tests/test_config.py:64-68` requires that shape for RBAC vars |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/authz.py` | UPDATE | `PERMISSION_MCP_CONNECT`, `MCP_PERMISSIONS`, skill pattern + `is_skill_permission()`, `load()` check, built-in matrix |
| `app/config.py` | UPDATE | nine settings, validators, `mcp_allowed_origins` property, origin normalizer |
| `.env.example` | UPDATE | document the nine settings |
| `tests/test_authz.py` | UPDATE | changed built-in assertions + new `skill:`/`mcp:connect`/`holds()` tests |
| `tests/test_config.py` | UPDATE | new MCP settings block |

## Tasks

### Task 1: authz vocabulary
- **File**: `app/services/authz.py`
- **Implement**:
  1. After `STREAM_PERMISSIONS` (:57): `PERMISSION_MCP_CONNECT = "mcp:connect"` and `MCP_PERMISSIONS = frozenset({PERMISSION_MCP_CONNECT})`, comment citing PRD-023 O1 (admin and user hold it, no role holds `skill:*`, D6) and that visibility reads `holds()`, never `authorize()`. Add `*MCP_PERMISSIONS` to `_KNOWN_PERMISSIONS` (:59-70).
  2. `import re`; `_SKILL_PERMISSION = re.compile(r"skill:[a-z0-9][a-z0-9-]{0,47}")` and `def is_skill_permission(p) -> bool` (`isinstance(p, str)` and `fullmatch`), docstring: dynamic family, not in `_KNOWN_PERMISSIONS`, existence checked by `mcp_config.load()` (STORY-007).
  3. Built-in matrix (:80-97): add `PERMISSION_MCP_CONNECT` to `admin` and `user`; extend the matrix comment (:72-79) with the O1/D6 sentence.
  4. `load()` (:136-149): after the parse, per role (iterate in sorted order for determinism), any str permission starting `skill:` that fails `is_skill_permission` raises `AuthzConfigError(f"RBAC_ROLES_FILE '{path_str}' role '{role}' grants invalid permission '{perm}': a skill permission must match skill:[a-z0-9][a-z0-9-]{{0,47}} (PRD-023 D6)")`. Then the existing unknown check runs on `granted` minus valid skill permissions. Update `load()` and `AuthzConfigError` docstrings. Do not touch `authorize()` or `holds()` code (add one docstring line to `holds()` naming `skill:<id>` as a reader).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_authz.py`

### Task 2: settings
- **File**: `app/config.py`
- **Implement**: after the `STREAM_*` fields (:409) add a block "MCP gateway (PRD-023 Section 9.3). Read per request by callers; settings never opens the file (mcp_config.load() does, STORY-007)" with the nine fields. One `@field_validator` per bounded int (message style :812-836, each naming what the value is and an example). `MCP_ALLOWED_ORIGINS`: module-level `_normalize_mcp_origin(entry) -> str` using `urlsplit` (scheme in `http|https`, hostname required, `.port` access inside try for a bad port, empty or `/` path only, no query/fragment/username/password, no `*`; lowercase; drop default port; keep IPv6 brackets); `@field_validator("MCP_ALLOWED_ORIGINS")` runs it over `_split_comma_list(value)` and returns the raw string; property `mcp_allowed_origins -> tuple[str, ...]` (next to `v1_tool_models_list`, :965) dedupes in order. Error names the setting, the entry and the rule, never anything else.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_config.py -k "mcp or stream or env_example"`

### Task 3: `.env.example`
- **File**: `.env.example`
- **Implement**: a PRD-023 block after the PRD-022/021 blocks (before the PRD-019 LB / Reflex tail), nine `# comment` + `VAR=default` pairs in the §9.3 order, comments state default, range and what happens out of range ("anything else fails startup"), as :219-232. `MCP_ENABLED=false`, `MCP_CONFIG_FILE=`, `MCP_ALLOWED_ORIGINS=` (comment: comma list of origins `scheme://host[:port]`, empty means any browser `Origin` is refused, CLI agents send none).

### Task 4: tests (see list below)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_authz.py tests/test_config.py -k "not turso"` (drop `-k` if test_config is fast enough)

## Existing tests that enumerate the matrix or `_KNOWN_PERMISSIONS` (grep'd `tests/`, excluding node_modules)

Changed assertions, each gets a `# PRD-023 O1/D6` comment:
- `tests/test_authz.py:71` `test_admin_matrix_matches_prd_exactly`: `set(ALL_PERMISSIONS)` becomes `set(ALL_PERMISSIONS) | {PERMISSION_MCP_CONNECT}` (leave `ALL_PERMISSIONS` :39-45 alone; the cells at :48-52 derive from the matrix and keep passing).
- `tests/test_authz.py:83` `test_user_matrix_matches_prd_exactly`: add `PERMISSION_MCP_CONNECT`.
- `tests/test_authz.py:287-293` `test_known_permissions_are_the_original_five_plus_the_six`: add `| MCP_PERMISSIONS`, `13` becomes `14`, extend the PRD-021 comment. (Keep the function name: renaming needs `_DELIBERATELY_SUPERSEDED_TESTS`.)
- `tests/test_authz.py:75` auditor stays unchanged (does not hold `mcp:connect`; add an explicit negative test).

Checked, unchanged (no assertion breaks): `tests/test_authz.py:296-299, 396-399` (disjoint from `ACTION_PERMISSIONS`/`STREAM_PERMISSIONS`), `:301-305` (three built-in roles), `tests/test_action_corpus.py:357-358` (disjoint from `ACTION_PERMISSIONS`), `tests/test_query_pipeline_break_glass.py:183` (label not known), `tests/test_rbac.py:102-334` (derive from `ROLE_PERMISSIONS`), `tests/test_main.py:196-204`. `tests/test_audit_characterization.py:140-144` holds a deliberate frozen literal copy of the built-in matrix with no `mcp:connect`; it is only used to refuse identities, so leave it unchanged and report it. Implementer re-greps `tests/ --include=*.py` for `_KNOWN_PERMISSIONS|ROLE_PERMISSIONS` before finishing.

New tests in `tests/test_authz.py`: `load()` accepts `skill:open-pull-request`, `skill:a`, a 48-char id, and `skill:0-x`; refuses `skill:Bad_Id`, a 49-char id, `skill:`, `skill:-x`, `skill:a b`, `"skill:ok\n"`, `skill:x:y`, asserting file path, role name and rule text in the message and matrix unchanged (as :318-329); a non-skill unknown still gets the old message; `mcp:connect` constant, in `_KNOWN_PERMISSIONS`, held by admin/user, not auditor; no built-in role holds any `skill:*` (`not any(is_skill_permission(p) for p in perms)` and no `startswith("skill:")`); `holds(Identity(role=r), "skill:x")` False for admin/auditor/user with `RBAC_ENABLED` in (False, True) while `authorize(..., "skill:x")` returns None with RBAC off (documents why `authorize` must not be used); `holds()` True after `load()` grants it; no `"skill:"` literal in `_KNOWN_PERMISSIONS`; a source scan of `app/**/*.py` asserting no `authorize(` call mentions `skill:`/`PERMISSION_SKILL`.
New tests in `tests/test_config.py` (new "PRD-023 STORY-004" block after :1770): defaults of all nine (delenv each); `MCP_ENABLED` parses `"true"`; one parametrized out-of-range test per bound (0 and 601 for timeout; 1023 for each byte cap; -1 and 86401 for cache and link window; 9 for idle) asserting the var name in the message; range bounds accepted (1, 600, 1024, 0, 86400, 10); origins: `""` gives `()`, normalization (`HTTPS://Example.COM/` gives `https://example.com`, `http://localhost:3000`, `https://a.com:443` gives `https://a.com`, duplicates collapse, whitespace around commas), refusals (`https://a.com/path`, `*`, `https://*.a.com`, `a.com`, `//a.com`, `ftp://a.com`, `https://a.com?x=1`, `https://u@a.com`, `https://a.com:notaport`), refusal names the setting and entry. `.env.example` test: each of the nine has a comment line directly above it (the `tests/test_config.py:64-68` regex) and they appear in §9.3 order.

## End-to-End Tests

- [ ] `from app.main import app` imports with default env (no route added; `/mcp` absent).
- [ ] `authz.load()` against a roles file granting `skill:open-pull-request` to a role sets the matrix and `holds()` is True for that role, False for `user`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_authz.py tests/test_config.py tests/test_rbac.py tests/test_action_corpus.py tests/test_query_pipeline_break_glass.py tests/test_untouched_app.py
```
Test renames: none planned (no `_DELIBERATELY_SUPERSEDED_TESTS` entry). Caddyfile and route census untouched. `docs/configuration.md` is not edited here (the PRD's docs deliverable is a later story).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 nine settings, defaults, bounds | 2, 4 | `tests/test_config.py` MCP defaults test + one parametrized out-of-range test per bound + origin tests |
| AC2 `skill:` accepted / refused naming file, role, rule | 1, 4 | `tests/test_authz.py` load-accepts / load-refuses skill tests |
| AC3 built-in matrix: admin+user hold `mcp:connect`, no `skill:*`, known set | 1, 4 | updated `test_admin_matrix...`, `test_user_matrix...`, `test_known_permissions...` + new no-skill and holds-with-RBAC-off tests |
| AC4 `.env.example` documents nine | 3, 4 | new `.env.example` test in `tests/test_config.py` |

## Risks

- `load()` order: skill check must precede the unknown check so `skill:Bad_Id` gets the role-naming message, not the generic one; add the ordering to a test.
- Non-string entries in a roles file already reach `sorted()` untyped (pre-existing); `is_skill_permission` guards `isinstance` so it adds no new crash. Left alone.
- Default-port dropping is a judgement call beyond the PRD text (see Design Decisions).
