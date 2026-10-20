---
story: STORY-018
prd: PRD-013
slug: regression-and-docs
title: "Regression sweep, README and .env docs"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits
created: 2026-10-20
---

# Plan: Regression sweep, README and .env docs

## Summary

This is the last story of PRD-013. It has the same shape as PRD-012 STORY-014 and PRD-011 STORY-013: one regression sweep and the documentation, in one commit. **No `app/`, `chat_ui/` or `scripts/` file changes.**

**Prove.** The suite was green at `5df7c69` (3,822 passed, 27 skipped, per the STORY-017 report). This story:
- re-runs the full suite;
- runs a git check of the four protected test files against the epic base `b184614`;
- audits every hunk in the 32 modified pre-existing test files for a PRD-013 citation. A hunk without one gets a comment, and never an assertion change.

**Document.**
- `README.md` gains a `### Usage limits` section under Features, after `### PII redaction`.
- It also gains a `### POST /query — blocked (usage limit)` API section, plus the eight `/audit` fields and three `/stats` fields.
- Four env rows are added and the `ADMIN_TOKEN` row is reworded.
- The *Duplicate detection scope*, *Where state lives*, *What is stored* and *The database is a hard dependency* sections are updated, and so are the Features table, Troubleshooting and the Roadmap.
- `.env.example` gains a `# Usage limits (PRD-013)` group with the four settings in field order. Its stale `ADMIN_TOKEN` comment is corrected.
- `tests/test_config.py` gains one `.env.example` guard group.

The pre-PRD is already `promoted` and linked (`pre-prds/README.md:19`, `PRE-PRD-013…md:5-6`), so it is not touched.

## User Story

As a platform operator
I want the documentation to state what is now limited, recorded and refused, and proof that nothing else moved
So that I can upgrade knowing what changes for my users

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-018-regression-and-docs.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md`, sections 6.2–6.10, 7 (F18), 9.2, 9.3, 10, 11 (*Quality indicators*), 12 (Phase 4), 15 (Decisions, Assumptions)
- Figures: `.agents/reports/PRD-013-audit-and-usage-limits/STORY-017-two-instance-limits-and-latency.report.md` (*Measured numbers*, *Notes for STORY-018*)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (tests + docs; story `type: technical`) |
| Complexity | MEDIUM |
| Systems Affected | `README.md`, `.env.example`, `tests/test_config.py` (one new guard group), and comment-only edits in pre-existing tests if Task 2 finds an uncited hunk. **No `app/`, `chat_ui/` or `scripts/` change.** |
| Story | STORY-018 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |
| Dependencies | STORY-013 ✅ `180ca6c`, STORY-014 ✅ `59e9fdc`, STORY-015 ✅ `b6085a4`, STORY-016 ✅ `6308359`, STORY-017 ✅ `5df7c69`. All `done` |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds one skill, `frontend-design`, which is scoped to building or reshaping UI. This story writes prose, config comments and one guard test, and it changes no UI. The story's `skills: []` and its note "Skills: none applicable. No UI surface changes" agree. The README quotes the bubble and console copy that STORY-014/016 wrote under that skill verbatim, and does not rewrite it. | — |

---

## Facts the design depends on (verified during planning)

| Fact | Evidence |
|---|---|
| **Epic base is `b184614`.** | `git merge-base HEAD main` = `b18461408c…`, the PRD-012 merge (PR #15). PRD Section 15 *Evidence* is also "verified against `main` @ `b184614`". |
| **Protected-file state since the base.** | `git log main..HEAD` touches two of the four:<ul><li>`tests/test_query_outcomes_regression.py` (+56/−0, commit `8dc6b4d`, STORY-011): two docstring lines, one `datetime` import, and `test_outcome_8_usage_limit` appended after outcome 7. No line removed, so rows 1–7 are byte-identical.</li><li>`tests/test_chat_outcomes_regression.py` (+2/−1, commit `1ab83f2`, STORY-005): the fake `_fake(...)` signature in `_capturing_run_conversation` gains `ingress=None`, with the comment `# \`ingress\` accepted since PRD-013 STORY-005; ChatState passes "chat".` This is a test double's parameter list, not an assertion.</li></ul>`test_duplicate_scope.py` and `test_pii_characterization.py` have no commits in the epic. See D1. |
| **Modified pre-existing tests.** | `git diff --name-only --diff-filter=M main HEAD -- tests/` lists 32 files. Every one contains at least one added line mentioning `PRD-013`, but that is per file, not per hunk. Files that changed existing lines (`−` > 0) include `test_admin_state.py` (−26), `test_summary.py` (−14), `test_db.py` (−9), `test_admin_shell.py` (−7), `test_two_instance_smoke.py` (−6), `test_identity.py` (−4) and the pipeline-fake files (−1/−2 each). Those are the hunks the AC's "every other modified pre-existing test carries a comment" applies to. See D2. |
| **Suite state.** | STORY-017 report: 3,822 passed, 27 skipped. One known `STREAM_EXPIRED` flake in `tests/test_query_pipeline_audit_fields.py` (PRE-PRD-017 shared-DB flake) passed on rerun. |
| **Shipped settings (not the PRD's examples).** | `app/config.py:322-338`:<ul><li>`USAGE_LIMITS_ENABLED: bool = True`</li><li>`USAGE_DAILY_TOKEN_BUDGET = "*=1000000"`</li><li>`USAGE_REQUESTS_PER_MINUTE = "*=60"`</li><li>`BREAK_GLASS_INGRESSES = "query,chat"`</li></ul>PRD 6.6's `"*=60,admin=120"` is the validator's **example** (`_LIMIT_MAP_EXAMPLES`, `:70-73`, alongside `"*=1000000,admin=unlimited"`), not the default. The README must not publish it as a default.<br>Validation (`:103-140`, `:498-536`): `role=value` pairs; `*` required; a value is digits ≥ 1 or `unlimited`; no repeated role. `0` is rejected with "0 does not turn the limit off; set USAGE_LIMITS_ENABLED=false for that". Role names are not checked against RBAC, and an unknown role gets `*`. `BREAK_GLASS_INGRESSES` accepts any subset of `query`/`chat` including empty, is case-sensitive, and rejects `v1` with its own message. |
| **CLI.** | `scripts/manage_users.py:94-115,158-180`: `set-limits --user-id ID [--token-budget N\|default] [--requests-per-minute N\|default]`. At least one flag is required. An omitted flag leaves its column alone, and `default` clears it to `NULL` (the role's value). N ≥ 1. **There is no `unlimited` per user**: the CLI accepts only N or `default`. `list-users` now prints two more tab-separated columns, budget and rate (`default` when `NULL`). Other commands: `create-user`, `deactivate-user`, `issue-token`. The README documents **no** command list today. `create-user` appears only in Quickstart (`:362`, `:386`) and Troubleshooting. See D5. |
| **The refusal.** | `QueryBlockedUsageLimitResponse` (`app/models/schemas.py:134-157`): `status: "BLOCKED"`, `reason: "Usage limit reached"`, `limit: "requests"\|"tokens"`, `maximum`, `actual`, `resets_at`. `resets_at` is the end of the current minute for `requests` and the next 00:00 UTC for `tokens` (`usage_limits.py:125-136`), in the audit timestamp format `%Y-%m-%dT%H:%M:%SZ`. On `/query` it is `200`, never `429`. `UsageLimitError` → `500` (`app/routers/query.py:36-37`). |
| **`/audit` and `/stats` fields.** | `AuditQueryEntry` (`schemas.py:230-240`): `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key`, `limit_exceeded`. Meanings are in PRD 6.2. `StatsResponse` (`:260-262`): `input_tokens: int = 0`, `output_tokens: int = 0`, `blocked_usage_limits: int = 0`. Usage-limit rows are `success=true`, so they count in `success_rate` as duplicate blocks do (PRD 10). |
| **The three limits of `conversation_key`** (AC 3). | PRD 6.3:<ol><li>Two conversations by one user that begin with the same system prompt and first instruction share a key, and so does every identical `/query` prompt by one user.</li><li>A client that compacts its context and rewrites its first user message starts a new key.</li><li>The chat UI's key can change mid-session once `chat_history.fit` drops the first exchange, so for chat rows `session_id` is authoritative.</li></ol> |
| **Measured round trips** (STORY-017). | Path A (one statement each). Local libSQL dev server, same host, 50 runs: `admit` p50 ≈ 8.5 ms / p95 ≈ 9.1–9.5 ms; `charge` p50 ≈ 7.5 ms / p95 ≈ 8.2–8.4 ms; **combined ≈ 16 ms p50 / ≈ 17.5 ms p95**. **Two added round trips per request, 3 → 5 statements**: identity read, usage gate, duplicate check, usage charge, audit write (`test_round_trip_cost_is_measured_and_reported`). A warm `POST /query` in-process is ~45 ms, printed and not asserted. **No remote figure exists.** STORY-017 had none available, and none is available here either (memory: no Turso endpoint). The reproduce command is in the report. `USAGE_LIMITS_ENABLED=false` restores 3 statements. |
| **Chat and console copy (verbatim).** | `chat_ui/chat_ui/copy.py:156,158`: "You've reached today's usage limit. You can send again after {reset} UTC." and "You're sending too fast. Wait a minute, then send again." `admin_copy.py:277`: "No one has sent anything today." `:394`: summary figure "Denied at a usage limit". |
| **README statements that become false or stale.** | <ul><li>`:184` "planned as PRD-013 and are not built yet".</li><li>`:476` "All four tables the harness owns" (`usage_daily` is a fifth).</li><li>`:486` "`audit_logs` is unchanged … gained exactly one column" (PRD-008's release voice; eight more columns now exist).</li><li>`:509` "one for the duplicate check, one for the audit write" (omits the identity read, and now the gate and the charge).</li><li>`:536` `ADMIN_TOKEN` row (no `/v1` or `BREAK_GLASS_INGRESSES`).</li><li>`.env.example:26` "Shared-secret bearer token required to call /audit and /stats", which has been stale since RBAC.</li></ul> |
| **README line map (pre-edit).** | <ul><li>Architecture prose `:140`.</li><li>Features table `:148-161`: *Full audit logging* `:156`, *Admin endpoints* `:159`.</li><li>*Duplicate detection scope* `:163-186`: "What does not" list `:172-178`, weakness `:184`.</li><li>*PII redaction* ends before `---` at ~`:341`.</li><li>*Where state lives* `:476`; *What is stored* `:486`; *The database is a hard dependency* `:507-511`.</li><li>Env table `:533-570`: `ADMIN_TOKEN` `:536`, last PII-code row `PII_CODE_SKIP_CODE_BLOCKS` before `REPORTS_*`.</li><li>API: context-limit `:669-687`, `GET /audit` `:689-731`, `GET /stats` `:733-760`.</li><li>Troubleshooting `:803-841`; Roadmap *Shipped* `:845-856`.</li></ul>The TOC lists top-level sections only, so it needs no entry. |
| **`.env.example` layout.** | The last group is `# PII for code (PRD-012)` (`:117-147`). The four usage fields are declared after `PII_CODE_SKIP_CODE_BLOCKS` in `app/config.py`, so field order puts the new group at the end of the file. Existing guard groups in `tests/test_config.py`: RBAC `:61-77`, Turso `:221-251`, chat `:334-363`, multi-turn `:452-476`, pattern `:597-650`, PII code `:869-938`. The PRD-013 STORY-007 group (`:941+`) tests the fields and has no `.env.example` guard. |
| **Index regeneration.** | `.agents/PRDs/PRD-013-audit-and-usage-limits/index.md:34` is the STORY-018 row, and `:9` reads "17/18 stories done". |

### Design decisions

- **D1: Prove the protected-file AC with git evidence, not a byte-identity claim.**
  - `test_query_outcomes_regression.py`: show that the diff has **no `−` line**. Rows 1–7 are then byte-identical and outcome 8 is appended. That satisfies "no changed assertion in rows 1-7" literally.
  - `test_chat_outcomes_regression.py`: quote the hunk. It is a test double's parameter list, not an assertion, and it already carries the PRD-013 comment.
  - `test_duplicate_scope.py` and `test_pii_characterization.py`: show an empty diff.
  - This follows PRD-012 STORY-014 D1: evidence, quoted in the report.
- **D2: Audit modified pre-existing tests per hunk, with a throwaway script, and fix only by comment.**
  - The script walks `git diff -U0 main HEAD` for the 32 `M` files. It reports every hunk with at least one `−` line (a changed line, not a pure addition) where neither the hunk nor the enclosing `def`/docstring mentions `PRD-013`.
  - Pure-addition hunks (new tests in an old file) are additive, and their own docstrings cite their story. The AC is about *modified* tests.
  - For each reported hunk, add one comment naming the PRD-013 story and decision (e.g. `# PRD-013 D10 (STORY-005): ingress is keyword-only on run_conversation.`). **Never change an assertion.**
  - If the script reports nothing, no test file outside `test_config.py` changes, and the report says so with the script's output.
- **D3: One new README section, `### Usage limits`, under Features, after `### PII redaction`.** Everything else points into it (`#usage-limits`), so the limits, the overshoot, BYOK and the failure rules have one source of truth, as *Pattern policy* and *PII redaction* do. No existing heading produces `#usage-limits`.
- **D4: State the shipped defaults as starting points.** The section says `*=1000000` tokens a day and `*=60` requests a minute. It says they are provisional, chosen so ordinary chat and script use never reaches them, and that **an upgraded deployment gets limits without opting in** (PRD 9.3, Assumptions). Role-map *examples* are labelled as examples (`admin=unlimited`, `admin=120`), never as defaults. Task 6's grep guards this.
- **D5: Document `manage_users.py` as a short command block inside *Usage limits*.** No user-management command list exists to sit beside, so the section shows the five commands (`create-user`, `list-users`, `set-limits`, `deactivate-user`, `issue-token`) with `set-limits` explained. The Quickstart `create-user` lines stay as they are. The block states that a per-user override is N or `default`. **`unlimited` exists only in the role map**, and the README must not imply otherwise.
- **D6: The latency figures are local-only, and the README says so.** It quotes STORY-017 figure for figure: 2 added round trips, `admit` ≈ 8.5 ms and `charge` ≈ 7.5 ms p50, ≈ 16 ms p50 / ≈ 17.5 ms p95 combined, same-host dev server, Path A, 50 runs. It says a remote endpoint adds its own network latency to each of the two, that none was measured, and names the reproduce command with `--allow-remote-database`. If a remote endpoint becomes available during implementation, run it, and the README and report quote that figure too. Otherwise no remote number is invented.
- **D7: One new API section; the context-limit section is untouched.** Add `### POST /query — blocked (usage limit)` after the context-limit section. The sentence "This is the only outcome the multi-turn release (PRD-010) added" is scoped to PRD-010, so it stays true and is not edited.
- **D8: Correct stale README statements in place, in the voice of the release that wrote them.**
  - `:476` becomes five tables.
  - `:486` gains one sentence: PRD-013 later added eight metadata columns and no content (pointer to `#get-audit-…`).
  - `:509` becomes the five statements.
  - Historical paragraphs are not rewritten beyond that.
- **D9: Do not touch `app/config.py`'s stale "no production code reads these yet / Consumed by STORY-0xx" comments.** No-app-change is the docs-story rule, and PRD-012 left its own "Consumed by STORY-007" comments in place. Record it in the report as a follow-up.
- **D10: The `.env.example` guard group mirrors PRD-012 STORY-014's group.** It checks that each var has a comment, field order is read from `Settings.model_fields`, the defaults match the fields, and substance checks pass: the `ADMIN_TOKEN` comment names `v1` and `BREAK_GLASS_INGRESSES`, and the `USAGE_LIMITS_ENABLED` comment says what `false` does. No test reads `README.md`, by precedent, so the README is checked with greps and a throwaway link checker.

---

## Patterns to Follow

### README feature section: bold lead-in claim, then the reason, then the test that proves it
```
// SOURCE: README.md:209-215, 283-285 (Pattern policy), 287-340 (PII redaction)
### Pattern policy

**What is matched, how, and against which messages is configuration, not code.** The patterns live in …

The full design, including the threat reasoning behind each cell of the table, is in [PRD-011](.agents/PRDs/PRD-011-pattern-policy/PRD.md).
```

### Measured figures: numbers, what dominates, the lever, the script
```
// SOURCE: README.md:205
**What it costs.** Measured on a session of 20 exchanges (41 messages, ~19k characters) against a local database: **about 0.93 s added per send** (p50 926 ms, p95 961 ms) … The measurement script is `scripts/measure_history_latency.py`.
```

### Blocked API section: JSON body, then the rules in bold-led paragraphs
```
// SOURCE: README.md:669-687
### `POST /query` — blocked (context limit)

```json
{ "status": "BLOCKED", "reason": "Conversation exceeds context limit", "limit": "characters", "maximum": 200000, "actual": 250113 }
```

**This is the only outcome the multi-turn release (PRD-010) added** — … `limit` is `messages`, `characters` or …
```

### Environment-variable row: default, validation as a startup error, the consequence
```
// SOURCE: README.md (PII_MAX_CHARACTERS_CODE row)
| `PII_MAX_CHARACTERS_CODE` | No | `200000` | Most characters `code` will analyze in one request, … Over it the request is **refused** with `limit: "redaction_characters"` and audited — never forwarded unmasked. Must be at least `1`. |
```

### `.env.example` group: section header, one comment block per variable, ASCII hyphens, lowercase bools
```
// SOURCE: .env.example:117-125
# PII for code (PRD-012)
# Used only where a call site runs the code profile; /query and the chat UI run
# chat, and no request can choose a profile (README, "PII redaction")

# Comma-separated Presidio entity types to detect and mask under code. With no
...
PII_ENTITIES_CODE=EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE
```

### `.env.example` guard tests
```
// SOURCE: tests/test_config.py:869-938
def test_env_example_pii_code_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = [name for name in Settings.model_fields if name in _PII_CODE_VARS]
    assert sorted(declared_order) == sorted(_PII_CODE_VARS)
    positions = [text.index(f"{var}=") for var in declared_order]
    assert positions == sorted(positions)

def test_env_example_existing_pii_comments_name_their_profile():
    comment = re.search(rf"(?m)((?:^#.*\n)+){var}=", text)
    block = comment.group(1).lower()
    assert "chat" in block, ...
```
Reuse `_env_example_value` (`:878-881`). Do not redefine it.

### Comment citing PRD-013 on a modified pre-existing test
```
// SOURCE: tests/test_chat_outcomes_regression.py:142
    # `ingress` accepted since PRD-013 STORY-005; ChatState passes "chat".
```

### Error handling
Not applicable. There are no production code changes and no new error path. The README describes existing arms: `UsageLimitError` → `500` (`app/routers/query.py:36-37`), and the charge failure logged at `ERROR` and returned (STORY-012).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_config.py` | UPDATE | New `.env.example` guard group for the four usage settings and the `ADMIN_TOKEN` comment (D10) |
| `.env.example` | UPDATE | `# Usage limits (PRD-013)` group at the end, in field order; `ADMIN_TOKEN` comment corrected |
| `README.md` | UPDATE | New `### Usage limits` section (D3–D6) and `### POST /query — blocked (usage limit)` (D7). Updates: Features table, architecture prose, *Duplicate detection scope*, *Where state lives*, *What is stored*, *The database is a hard dependency*, env table (`ADMIN_TOKEN` + 4 rows), `GET /audit` (8 fields), `GET /stats` (3 fields), Troubleshooting, Roadmap |
| `tests/*.py` (only those Task 2 reports) | UPDATE (comment only) | Add a PRD-013 citation to any uncited modified hunk (D2) |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Start the libSQL dev server before any pytest step: `docker start harness-libsql-dev`, or the `docker run` from README *Running Tests*. **A mass of fixture errors means the dev server has degraded. Restart the container; do not bisect code.**

### Task 1: Record the protected-file evidence before touching anything

- **File**: none (evidence for the report)
- **Action**: VERIFY
- **Validate**:
  ```bash
  git merge-base HEAD main                                    # expect b18461408c…
  git diff --stat b184614 HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_duplicate_scope.py tests/test_pii_characterization.py
  # expect: query_outcomes +56, chat_outcomes +2/-1, the other two absent
  git diff b184614 HEAD -- tests/test_query_outcomes_regression.py | grep -E '^-[^-]'   # expect: no output (rows 1-7 untouched)
  git diff b184614 HEAD -- tests/test_chat_outcomes_regression.py                        # expect: the single _fake signature hunk with its PRD-013 comment
  git log --oneline b184614..HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py   # expect 8dc6b4d, 1ab83f2
  ```
  Record all outputs in the report under D1.

### Task 2: Per-hunk PRD-013 citation audit of modified pre-existing tests

- **File**: scratchpad script (not committed); possibly comment-only edits in `tests/`
- **Action**: VERIFY, then UPDATE only if needed
- **Implement**:
  - Write a throwaway script. For each file in `git diff --name-only --diff-filter=M b184614 HEAD -- tests/`, parse `git diff -U0 b184614 HEAD -- <file>` into hunks.
  - For every hunk that **removes or replaces** a line (at least one `−` line), check for the string `PRD-013` in either place:
    - (a) the hunk's added lines;
    - (b) the enclosing function's lines in the HEAD file, found by walking up from the hunk's new-line number to the nearest `def `/`class ` and down to the next one. This covers a docstring or comment above.
  - Print `file:line` for every uncited hunk, with its removed and added lines.
  - For each one, add a single comment line directly above the changed line, naming the story and decision, e.g. `# PRD-013 D10 (STORY-005): run_conversation takes ingress keyword-only.` Use the `git log -L`/blame commit to name the right story. **Never alter an assertion, a value or a call.**
- **Mirror**: `tests/test_chat_outcomes_regression.py:142`.
- **Validate**: Re-run the script and expect zero uncited hunks. Then:
  ```bash
  git diff --stat -- tests/ ':!tests/test_config.py'    # only comment lines, if any
  git diff -- tests/ ':!tests/test_config.py' | grep -E '^[-+]' | grep -vE '^(\+\+\+|---|\+\s*#)'   # expect: no output (only added comment lines)
  ```
  Record the script output (before and after) in the report.

### Task 3: `.env.example`: the usage group and the `ADMIN_TOKEN` comment

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**:
  - Replace the `ADMIN_TOKEN` comment at `:26`. The value is unchanged. New text: "Break-glass bearer token: always resolves to the admin role, independent of the users table (required). Never accepted on /v1; BREAK_GLASS_INGRESSES can also refuse it on /query and the chat UI. The admin console signs in with it."
  - Append after `PII_CODE_SKIP_CODE_BLOCKS=true` (end of file, field order), with a blank line before:
    ```
    # Usage limits (PRD-013)
    # On by default: an upgraded deployment is limited from its first boot. The
    # defaults are starting points, chosen so ordinary chat and script use never
    # reaches them (README, "Usage limits")

    # Master switch for the usage gate and the token charge (true/false). false
    # writes and reads no counter, and each request makes the round trips it made
    # before PRD-013. RBAC_ENABLED=false does not turn limits off
    USAGE_LIMITS_ENABLED=true

    # Tokens per user per UTC day, by role: role=value pairs with a required *
    # entry; each value an integer >= 1 or unlimited (e.g. *=1000000,admin=unlimited).
    # Overridden per user with scripts/manage_users.py set-limits
    USAGE_DAILY_TOKEN_BUDGET=*=1000000

    # Authorized attempts per user per minute, by role, in the same shape
    # (e.g. *=60,admin=120). A fixed window on the database clock
    USAGE_REQUESTS_PER_MINUTE=*=60

    # Ingresses on which ADMIN_TOKEN may submit queries: any subset of query and
    # chat, possibly empty. v1 is rejected at startup - the token is never
    # accepted there, and this setting can only narrow where it is
    BREAK_GLASS_INGRESSES=query,chat
    ```
    Use ASCII hyphens only, matching the file.
- **Mirror**: `.env.example:117-147`.
- **Validate**:
  ```bash
  OPENROUTER_API_KEY=x ADMIN_TOKEN=x DATABASE_URL=http://127.0.0.1:8080 python -c "from app.config import Settings; s=Settings(_env_file='.env.example'); print(s.USAGE_LIMITS_ENABLED, s.usage_daily_token_budget_map, s.usage_requests_per_minute_map, sorted(s.break_glass_ingresses))"
  # expect: True {'*': 1000000} {'*': 60} ['chat', 'query']
  ```
  The `*=…` values contain `=`, so confirm that the `.env` parser reads the whole right-hand side. The print shows it.

### Task 4: `.env.example` guard group

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append at the end of the file; change no existing test)
- **Implement**: Add a header comment `# --- PRD-013 STORY-018: .env.example documents the usage-limit settings ---`. Then add:
  - `_USAGE_VARS = ("USAGE_LIMITS_ENABLED", "USAGE_DAILY_TOKEN_BUDGET", "USAGE_REQUESTS_PER_MINUTE", "BREAK_GLASS_INGRESSES")`
  - `test_env_example_documents_every_usage_var_with_a_comment`: uses `rf"(?m)^#.+\n{var}="`.
  - `test_env_example_usage_vars_appear_in_settings_field_order`: reads the order from `Settings.model_fields`.
  - `test_env_example_usage_defaults_match_settings`: uses `_env_example_value`. The bool is compared lowercase, and the three strings are compared exactly.
  - `test_env_example_admin_token_comment_names_v1_and_the_setting`: the comment block above `ADMIN_TOKEN=` contains `v1` and `BREAK_GLASS_INGRESSES`.
  - `test_env_example_says_what_disabling_usage_limits_does`: the block above `USAGE_LIMITS_ENABLED=` contains `false` and `counter`.

  Each docstring cites PRD-013 STORY-018 AC 4. Assert on substance, not exact sentences.
- **Mirror**: `tests/test_config.py:869-938`.
- **Validate**:
  ```bash
  pytest tests/test_config.py -q
  ```
  **Guard-bite (not committed)**: check that each assertion can fail, then revert both edits and record the result in the report.
  - Swap the two limit-map lines in `.env.example`; the order test should fail.
  - Delete `v1` from the `ADMIN_TOKEN` comment; the comment test should fail.

### Task 5: README, the `### Usage limits` section

- **File**: `README.md`
- **Action**: UPDATE. Insert after the last line of `### PII redaction` (its PRD-012 link line) and before the `---` that precedes `## Requirements`.
- **Implement**: `### Usage limits` (anchor `#usage-limits`), in the bold-lead-in voice, one claim per paragraph:
  1. **Two limits per user, on by default.**
     - A daily token budget (`USAGE_DAILY_TOKEN_BUDGET`, default `*=1000000`).
     - A request rate (`USAGE_REQUESTS_PER_MINUTE`, default `*=60`).
     - Both are keyed by the authenticated user, never a request field, and counted in one shared database row, so a second instance does not double them (`tests/test_two_instance_smoke.py`).
     - **An upgraded deployment gets them without opting in.** The defaults are starting points, chosen so ordinary chat and script use never reaches them. Confirm them for your traffic.
     - `USAGE_LIMITS_ENABLED=false` turns both off and writes no counter. `RBAC_ENABLED=false` does not.
  2. **Role maps.** `role=value` pairs with a required `*`; a value is an integer ≥ 1 or `unlimited`. Example, **labelled as an example**: `USAGE_DAILY_TOKEN_BUDGET=*=1000000,admin=unlimited`, `USAGE_REQUESTS_PER_MINUTE=*=60,admin=120`.
     - An unknown role gets `*`.
     - `0` is a startup error and is not "off".
     - The `ADMIN_TOKEN` identity gets the `admin` role's limits and is not exempt.
  3. **Per-user overrides.**
     - Resolution order, per limit: the user's override, else the role's entry, else `*`.
     - A command block with the five `manage_users.py` commands (D5). `set-limits` is shown with the PRD 10 examples (`--token-budget 5000000`, `--requests-per-minute default`).
     - `default` clears the override back to the role's value.
     - An override is a whole number ≥ 1. `unlimited` is a role-map value only.
     - `list-users` shows both columns.
     - A change applies to the user's next request: the identity is re-read on every request and every chat send.
  4. **What counts.**
     - The rate counts every **authorized** attempt, including ones then held as duplicates, refused for length, or failed upstream (T2, T3).
     - A caller refused authorization counts nothing.
     - The budget charges what the provider reported, input plus output: on success, and when the response then failed redaction; not when the upstream call failed.
  5. **The rate window is fixed, not sliding.**
     - It is a calendar minute on the database clock, so a user can send the limit at the end of one minute and again at the start of the next, at most 2× for one minute.
     - The day resets at 00:00 UTC.
     - A refused attempt counts toward the window it was refused in, but cannot extend a lockout.
  6. **The budget can be overshot.**
     - Check-then-charge: a request admitted just under budget runs, and so does every request already in flight.
     - The overshoot is bounded by the rate limit times one response.
     - Reserving `max_tokens` up front would close it, and is not built (T6).
  7. **BYOK.** A request with its own `openrouter_api_key`:
     - is rate-limited;
     - is never refused for budget and charges nothing, because it spends the caller's key;
     - still records its tokens in the audit;
     - requires `query:byok`, which only `admin` has by default (D8, T14).
  8. **The gate fails closed; the charge fails open.**
     - If the counter cannot be read, the request is a `500` and nothing goes upstream, as the duplicate check does (T7).
     - If the charge write fails after the model answered, the user still gets the answer, an `ERROR` is logged, and the audit row's `input_tokens`/`output_tokens` are the record. Usage is under-counted for the length of the outage (T8).
  9. **What the caller sees.**
     - `POST /query` returns `200` `BLOCKED` with `limit`, `maximum`, `actual` and `resets_at`, never `429` (link `#post-query--blocked-usage-limit`).
     - The chat shows the two bubbles verbatim (copy.py `:156`, `:158`). A reload restores them.
     - A refusal is audited `success=true` with `limit_exceeded` set, and is **never a prior query** for the duplicate check.
  10. **What the admin sees.**
      - Register: a usage-limit row reads **denied**; tokens read input / output; search matches `conversation_key` and `ingress`.
      - Summary: token totals and "Denied at a usage limit".
      - Usage page: one table, one row per user active today (UTC); requests, input, output, budget, share used, refusals. The empty state reads "No one has sent anything today."
      - `GET /stats` carries the same three figures.
  11. **`ADMIN_TOKEN` by ingress.** It is accepted on `/query` and the chat by default (`BREAK_GLASS_INGRESSES=query,chat`). It is never accepted on `/v1`, and the setting cannot add `v1`. A refusal is the existing `200` refused-by-policy body (`QueryBlockedForbiddenResponse`, `"reason": "Break-glass credential not permitted on this ingress"`; link `#post-query--200-refused-by-policy`), audited with `denied_permission: "ingress:break_glass"`. Verify the exact `required_permission` value against `tests/test_query_pipeline_break_glass.py` before writing it. The admin console is not an ingress and still signs in with it.
  12. **What it costs.** Quote STORY-017 figure for figure (D6):
      - **2 added database round trips per request** (5 statements: identity read, usage gate, duplicate check, usage charge, audit write; 3 with limits off);
      - `admit` ≈ 8.5 ms and `charge` ≈ 7.5 ms p50, **≈ 16 ms p50 / ≈ 17.5 ms p95 combined**;
      - local libSQL dev server on the same host, 50 runs, one statement per call;
      - a remote Turso endpoint adds its network latency to each, and none has been measured;
      - the script and command: `scripts/measure_usage_latency.py --runs 50`, plus the `--database-url … --allow-remote-database` form.

      Link `#the-database-is-a-hard-dependency-of-every-request`.
  13. Closing line: "The full design, including the threat reasoning, is in [PRD-013](.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md)."

  **Bold-claim check before writing.** Every behaviour claim maps to a PRD invariant that a test asserts (PRD 9.2 invariants, Section 11 functional requirements). For each paragraph, name in the report the test file that proves it (e.g. `tests/test_query_pipeline_usage_limits.py`, `tests/test_usage_limits.py`, `tests/test_query_pipeline_break_glass.py`). If a claim has no test, soften it or drop it.
- **Validate**:
  ```bash
  grep -n "^### Usage limits" README.md                       # exactly one
  grep -n -E "8\.5 ms|7\.5 ms|16 ms|17\.5 ms" README.md        # the STORY-017 figures
  grep -n "measure_usage_latency.py" README.md                 # ≥ 1
  grep -n "set-limits" README.md                               # ≥ 1
  grep -n -E "admin=120|admin=unlimited" README.md             # every hit labelled as an example (read each line)
  ```

### Task 6: README, the API reference

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**:
  - **New `### POST /query — blocked (usage limit)`** after the context-limit section (D7). Contents:
    - The PRD 10 JSON body (`"limit": "tokens"`, `"maximum": 1000000`, `"actual": 1003412`, `"resets_at": "2026-10-05T00:00:00Z"`).
    - `limit` is `requests` or `tokens`; when both are broken, `requests` is reported.
    - `actual` is the window count or tokens used today.
    - `resets_at` is UTC: the end of the minute, or the next 00:00 UTC.
    - `200`, never `429`.
    - The gate sits after authorization (and the break-glass check) and before the context limit, so a caller without `query:submit` learns nothing.
    - Audited `success=true`, `limit_exceeded` set, not a prior query.
    - A counter read failure is a `500`.
    - Link `#usage-limits`.
  - **`GET /audit`**:
    - Add the eight fields to the JSON example after `"profile"`, with realistic values: `"ingress": "query"`, `"message_count": 1`, `"input_tokens": 38`, `"output_tokens": 7`, `"streamed": false`, `"has_tool_calls": false`, `"conversation_key": "<64-hex>"`, `"limit_exceeded": null`.
    - Add a field table after the `profile` paragraph (PRD 6.2 meanings): `ingress` (`query`/`chat`/`v1`), `message_count` (as received, before redaction), `input_tokens`/`output_tokens` (`null` with no upstream call or no split reported; `tokens_used` unchanged), `streamed` and `has_tool_calls` (always `false` until the OpenAI endpoint and tool calls exist), `conversation_key`, `limit_exceeded` (`requests`/`tokens`, set only on a usage-limit refusal).
    - Rows written before PRD-013 return `null` for the six nullable fields and `false` for the two flags.
    - A `conversation_key` paragraph:
      - it is a versioned hash of the user, the first `system` and the first `user` message, over raw text;
      - it is a grouping aid, not an identity, with **its three limits** listed (facts table);
      - for chat rows `session_id` is authoritative;
      - `GET /audit` has no filter on it, but the console's Register search does.
  - **`GET /stats`**: add `"input_tokens"`, `"output_tokens"` and `"blocked_usage_limits"` to the example. Add one paragraph:
    - sums over all rows, `null` as 0;
    - usage-limit rows count in `success_rate` as duplicate blocks do;
    - the console summary shows the same figures.
- **Validate**:
  ```bash
  grep -n "^### \`POST /query\` — blocked (usage limit)" README.md
  for f in ingress message_count input_tokens output_tokens streamed has_tool_calls conversation_key limit_exceeded blocked_usage_limits; do printf "%s " $f; grep -c "\"$f\"\|\`$f\`" README.md; done   # each ≥ 1
  ```
  Cross-check every field name against `app/models/schemas.py:230-262`.

### Task 7: README, replacements elsewhere

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**:
  - **Features table**:
    - Add a row `| **Usage limits** | … |`: daily token budget and per-minute rate per user, by role with per-user overrides, on by default, shared across instances. See [Usage limits](#usage-limits).
    - *Full audit logging*: add "ingress, message count, input/output tokens and a conversation key".
    - *Admin endpoints*: add "and a Usage page in the admin console".
  - **Architecture prose `:140`**: one sentence. Between authorization and the duplicate check sits the usage gate (`usage_daily`), and after the upstream call the charge; see `#usage-limits`. The diagram is not redrawn, by PRD-012 precedent. Add "usage limit" to the list of blocks that short-circuit before the provider.
  - ***Duplicate detection scope***:
    - In "What does not" count, add a bullet: **Usage-limit refusals.** A prompt refused at a limit is not held as a duplicate when sent again after the reset.
    - `:184`: replace "planned as PRD-013 and are not built yet" with shipped wording. Per-user rate limits and token budgets now bound what N accounts can spend; see [Usage limits](#usage-limits).
  - ***Where state lives* `:476`**: "All five tables … and `usage_daily` (one counter row per user per UTC day)".
  - ***What is stored* `:486`**: append one sentence. PRD-013 later added eight metadata columns (ingress, counts, token split, conversation key, limit), with no content and no new preview. See `GET /audit`.
  - ***The database is a hard dependency* `:509`**:
    - Rewrite the round-trip clause: with usage limits on, every `POST /query` makes five statements (identity read, usage gate, duplicate check, usage charge, audit write), and three with `USAGE_LIMITS_ENABLED=false`.
    - Point to `#usage-limits` for the measured cost.
    - In `:511`, add one sentence: the usage gate fails closed the same way (`500`), and the charge fails open.
  - **Env table**:
    - `ADMIN_TOKEN` row: append "Never accepted on `/v1` (PRD-014's endpoint); `BREAK_GLASS_INGRESSES` can also refuse it on `POST /query` and the chat UI. The admin console signs in with it regardless."
    - Four new rows after `PII_CODE_SKIP_CODE_BLOCKS`, before `REPORTS_*`, in field order, each with the default, the validation as a **startup error**, and the consequence (PRD 9.3, shipped defaults):
      - `USAGE_LIMITS_ENABLED`, `true`;
      - `USAGE_DAILY_TOKEN_BUDGET`, `*=1000000`;
      - `USAGE_REQUESTS_PER_MINUTE`, `*=60`;
      - `BREAK_GLASS_INGRESSES`, `query,chat`, where `v1` is a startup error.
  - **Troubleshooting**: two entries.
    - **`"reason": "Usage limit reached"` on `POST /query`**: read `limit` and `resets_at`; raise one user with `set-limits`, or a role in the map.
    - **`500` naming the usage counter**: the database is unreachable and the gate fails closed by design; see *The database is a hard dependency*.
  - **Roadmap *Shipped***: add `- [x] [Audit fields and usage limits](#usage-limits) — per-user token budget and rate limit, shared across instances; ingress, token split and conversation key on every audit row; ADMIN_TOKEN scoped by ingress` after the PII-for-code line.
- **Validate**:
  ```bash
  grep -n "planned as PRD-013" README.md                  # no hits
  grep -n "All four tables" README.md                     # no hits
  grep -n -E "USAGE_LIMITS_ENABLED|USAGE_DAILY_TOKEN_BUDGET|USAGE_REQUESTS_PER_MINUTE|BREAK_GLASS_INGRESSES" README.md   # env rows + section
  grep -n "#usage-limits" README.md                       # several pointers
  ```
  Cross-check every documented default against `app/config.py:322-338`, row by row.

### Task 8: Link and anchor check (throwaway)

- **File**: scratchpad only (do not commit)
- **Action**: CREATE (throwaway)
- **Implement**: Reuse the PRD-012 STORY-014 approach. Parse every `](…)` link in `README.md`:
  - relative file links must exist;
  - `#anchor` links must match a GitHub slug of a heading.

  Self-check against `git show HEAD:README.md` first. It should report only the known pre-existing miss(es).
- **Validate**: No new failures. These must all resolve: `#usage-limits`, `#post-query--blocked-usage-limit`, `#the-database-is-a-hard-dependency-of-every-request`, the `GET /audit` anchor used, and `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md`.

### Task 9: Full sweep and scope checks

- **File**: none
- **Action**: VERIFY
- **Validate**:
  ```bash
  python -c "import app.main"
  pytest tests/ -q
  # expect: 3822 + Task 4's new tests passed, 27 skipped; record exact counts
  git diff --stat HEAD -- app/ chat_ui/ scripts/          # empty
  git diff --stat HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_duplicate_scope.py tests/test_pii_characterization.py   # empty (this story touches none)
  git diff --stat HEAD                                    # only the files in Files to Change
  ```
  If there is a mass of libSQL fixture errors, restart the dev container and re-run; do not bisect. A lone `STREAM_EXPIRED` in a file this story does not touch is the known shared-DB flake: rerun the file, and record it.
- **Optional, if a remote endpoint is available**: run the STORY-017 remote command and record it. Then add the remote figure to *Usage limits* §12. Otherwise leave the "none measured" sentence (D6).

---

## End-to-End Tests

- [ ] `pytest tests/ -q` is green; counts recorded.
- [ ] Task 1's git evidence is recorded: no `−` line in `test_query_outcomes_regression.py`, the one fake-signature hunk in `test_chat_outcomes_regression.py`, and empty diffs for the other two.
- [ ] Task 2's audit script reports zero uncited modified hunks (after any comment fixes), and the non-comment diff of `tests/` outside `test_config.py` is empty.
- [ ] Task 4's guard-bites fail as expected, then are reverted.
- [ ] `Settings(_env_file='.env.example')` parses the four values (Task 3).
- [ ] Read `### Usage limits` top to bottom against AC 2 and tick each item:
  - two limits;
  - defaults as starting points;
  - role maps;
  - per-user overrides with `set-limits`;
  - fixed window;
  - overshoot;
  - BYOK;
  - fail-closed gate and fail-open charge;
  - the measured round trips match STORY-017 figure for figure.
- [ ] Read the API reference against AC 3: the usage-limit body; eight `/audit` fields with meanings, including the three `conversation_key` limits; three `/stats` fields.
- [ ] Read the env table and `.env.example` against AC 4: four new rows each, and the `ADMIN_TOKEN` row and comment say "refused on `/v1`".
- [ ] Read *Duplicate detection scope*, *The database is a hard dependency* and Roadmap against AC 5.
- [ ] The link checker reports no new failures.

---

## Validation

```bash
python -c "import app.main"
pytest tests/ -q
pytest tests/test_config.py -q
git diff --stat b184614 HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_duplicate_scope.py tests/test_pii_characterization.py
```

Frontend lint: not applicable. There is no UI change, and no linter is configured (STORY-017 report).

---

## Risks

| Risk | Mitigation |
|---|---|
| The AC's "no changed assertion in `test_chat_outcomes_regression.py`" is read against the fake-signature hunk | D1: quote the hunk. It is a parameter on a test double and carries its PRD-013 comment; no assertion line changed |
| Per-file `PRD-013` mentions hide an uncited modified hunk | D2's per-hunk script, with comment-only fixes verified by the non-comment diff check |
| The README publishes the validator's examples (`admin=120`, `admin=unlimited`) as defaults | D4; Task 5's grep, reading every hit; defaults cross-checked against `app/config.py:322-338` |
| The README implies a per-user `unlimited` | D5: the CLI accepts N or `default` only, stated explicitly |
| Latency claims drift from STORY-017, or a remote figure is invented | D6: copy from the report's table; "none measured" unless Task 9's optional run happens |
| Over-claiming `/v1` exists | Every `/v1` mention says it is PRD-014's endpoint, under the "intended direction" convention |
| `*=…` values in `.env.example` misparse because of the `=` | Task 3's `Settings(_env_file=…)` check prints the parsed maps |
| Shared-DB flake mistaken for a regression | Restart the container on mass errors; rerun single-file `STREAM_EXPIRED` (STORY-017 precedent) |

---

## Acceptance Criteria

(Copied from story `STORY-018`)

- [ ] Given the full suite, when it runs, then it is green, and `git diff main` shows no changed assertion in `test_query_outcomes_regression.py` rows 1-7, `test_chat_outcomes_regression.py`, `test_duplicate_scope.py` or `test_pii_characterization.py`; every other modified pre-existing test carries a comment citing PRD-013 and the decision.
- [ ] Given the README, when it is read, then it has a *Usage limits* section covering the two limits, their defaults, role maps and per-user overrides, the fixed window, the possible budget overshoot, the BYOK rule, fail-closed gate and fail-open charge, and the measured round trips from STORY-017.
- [ ] Given the README's API reference, when it is read, then it documents the usage-limit `BLOCKED` body, the eight new `/audit` fields with their meanings (including the three limits of `conversation_key`) and the three new `/stats` fields.
- [ ] Given the README's environment table and `.env.example`, when they are read, then both list `USAGE_LIMITS_ENABLED`, `USAGE_DAILY_TOKEN_BUDGET`, `USAGE_REQUESTS_PER_MINUTE` and `BREAK_GLASS_INGRESSES`, and the `ADMIN_TOKEN` row says it is refused on `/v1`.
- [ ] Given the README's *Duplicate detection scope*, *The database is a hard dependency of every request* and roadmap sections, when they are read, then the PRD-013 note reads as shipped, the per-request round trips are updated, and the roadmap lists this PRD under shipped.
- [ ] All tasks completed
- [ ] Backend imports without error; no `app/`, `chat_ui/` or `scripts/` change
- [ ] Follows existing patterns (PRD-012 STORY-014 shape)
