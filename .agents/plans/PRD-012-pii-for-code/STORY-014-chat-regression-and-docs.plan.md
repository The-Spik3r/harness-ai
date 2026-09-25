---
story: STORY-014
prd: PRD-012
slug: chat-regression-and-docs
title: "chat regression sweep, README and .env docs, pre-PRD promoted"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code
created: 2026-09-25
---

# Plan: chat regression sweep, README and .env docs, pre-PRD promoted

## Summary

This is the last story of PRD-012. It follows the shape of PRD-011 STORY-013: one regression sweep plus the documentation, in one commit. **No `app/` or `chat_ui/` file changes.**

**Prove.** Most of the proof already exists and is green at `9a3f1a7`: 3,326 passed and 27 skipped, per the STORY-013 report. This story re-runs it and records it:
- the full suite;
- the `--run-benchmark` latency assertion, which the everyday suite skips;
- a git check of the five protected test files against the epic base `e10d191`.

One protected file has a known, sanctioned change. STORY-011 added `"profile"` to the expected key set in `tests/test_pii_redaction_integration.py:206-207`, with a PRD-012 D9 comment. The AC says "no changed assertion", so the report records this hunk as a deviation with its evidence. It must not claim byte-identity (see D1).

The only new test code is a `.env.example` guard group in `tests/test_config.py`. It is the per-group shape STORY-005's handoff asked for.

**Document.**
- `README.md` gains a `### PII redaction` section under Features, beside *Multi-turn context* and *Pattern policy*. It covers:
  - the `chat` and `code` profiles;
  - the Section 6.3 role table;
  - the plain trade-offs (fenced blocks unmasked, names and places not detected by default, output not masked, number tokens quoted in JSON, over-limit refused, `profile` in the audit);
  - the measured latency beside the ~0.93 s history figure, naming `scripts/measure_pii_latency.py`.
- Every other README change is a replacement or a pointer into that section:
  - the Features row;
  - the architecture note;
  - the *Multi-turn context* cost paragraph;
  - the four existing `PII_*` env rows plus six new ones;
  - the context-limit API section, which gains `redaction_characters`;
  - `profile` in `GET /audit` and a note in `GET /stats`;
  - Troubleshooting, Roadmap, and one sentence in *OpenAI-compatible endpoint*.
- `.env.example` gains the six settings in `app/config.py` field order, and its four existing `PII_*` comments say which profile they govern.
- `pre-prds/PRE-PRD-012-pii-for-code.md` is marked `promoted`, and its row in `pre-prds/README.md` links PRD-012.

## User Story

As a platform operator
I want the README to say exactly what the `code` profile masks and gives up, with measured figures
So that I can configure and defend the deployment without reading the code

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-014-chat-regression-and-docs.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`: sections 4 (*Documentation*), 6.2–6.8, 7 (F12), 9.2 (T1–T5), 9.3, 10, 11 (*Quality indicators*), 12 (Phase 4)
- Figures: `.agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md` and `.agents/reports/PRD-012-pii-for-code/STORY-013-code-round-trip-suite.report.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (tests + docs; story `type: technical`) |
| Complexity | MEDIUM |
| Systems Affected | `README.md`, `.env.example`, `tests/test_config.py` (one new guard group), `pre-prds/PRE-PRD-012-pii-for-code.md`, `pre-prds/README.md`. **No `app/`, `chat_ui/` or `scripts/` change.** |
| Story | STORY-014 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Dependencies | STORY-002 ✅ `5e93b18`, STORY-011 ✅ `faaa4be`, STORY-012 ✅ `970f16a`, STORY-013 ✅ `e828e2a`. All `done` |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds one skill, `frontend-design`, scoped to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story writes prose, config comments and one guard test, and builds no UI. The story's `skills: []`, its note "Skills: none applicable" and the PRD's skills line agree. | — |

---

## Facts the design depends on (verified during planning)

| Fact | Evidence |
|---|---|
| **Epic base is `e10d191`.** | The first PRD-012 commit, `c313842`, has parent `e10d191`, the PRD-011 merge into `main` (PR #14). Unlike PRD-011, `main` is the correct baseline here: `git merge-base HEAD main` = `e10d191`. |
| **Protected-file state since the base.** | `git diff --stat e10d191 HEAD` over the five files touches two of them:<ul><li>`tests/test_pii_characterization.py` (+369) was **created** in the epic (`5e93b18`, STORY-002). Its baseline is its own creation commit, and `git diff 5e93b18 HEAD` over it is empty.</li><li>`tests/test_pii_redaction_integration.py` (+2) is `faaa4be` (STORY-011). It inserts `# PRD-012 D9: additive, nullable (STORY-011).` and `"profile",` into the expected key set of `test_audit_endpoint_contract_has_no_preview_fields` (`:203-208`). That is a line inside an assertion, so D1 applies.</li></ul>`test_pii_redactor.py`, `test_query_outcomes_regression.py` and `test_chat_outcomes_regression.py` are byte-identical. |
| **Suite and benchmark state at `9a3f1a7`.** | STORY-013 report: full suite 3,326 passed and 27 skipped (25 `REPORTS_E2E_URL`, 1 `HARNESS_SLOW_SMOKE`, 1 benchmark). Benchmark: `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s` gives `code` p95 at 200k of 463.23 ms against the 1,500 ms budget. `--run-benchmark` is defined at `tests/conftest.py:69-90`. |
| **The figures the README quotes.** | **Agent-shaped conversation, 200,000 characters:**<ul><li>STORY-003 `chat` (today's `redact()` on every message): p50 10,228.84 ms, p95 10,749.60 ms.</li><li>STORY-013 `code` (the shipped policy): p50 449.13 ms, p95 465.44 ms. The test run reads 463.23 ms.</li><li>Budget: **1,500 ms**, STORY-003 rule R2. STORY-013 says to quote the fixed 1,500 ms and not the 1,250 ms a re-derivation prints today.</li></ul>**At 40k:** `chat` p95 1,841.87 ms, `code` p95 70.62 ms. **At 400k:** `chat` p95 22,481.89 ms, `code` p95 928.62 ms.<br>**Throughput at concurrency 4:** `chat` 0.70×, pattern path 1.00×. Threads do not help (T10).<br>**Host:** Python 3.11.9, 12 logical CPUs; presidio 2.2.364, spaCy 3.8.16, en_core_web_lg 3.8.0.<br>**Reproduce with:** `python scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs 20 --arms code,pattern-blank --concurrency 1` and the STORY-003 command. |
| **The existing ~0.93 s figure.** | `README.md:205`: 41 messages, ~19k characters, p50 926 / p95 961 ms, ~97% re-redaction, `scripts/measure_history_latency.py`. That is `chat` at ~19k. The new figures go **beside** it and do not replace it. |
| **Settings and defaults (final, not provisional).** | `app/config.py:216-240`: `PII_ENTITIES_CODE="EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE"`, `PII_SCORE_THRESHOLD_CODE=0.40` (R1, **not** the PRD's provisional 0.5), `PII_MAX_CHARACTERS_CODE=200_000` (R3), `PII_CODE_REDACT_OUTPUT=False`, `PII_CODE_REDACT_SYSTEM=False`, `PII_CODE_SKIP_CODE_BLOCKS=True`. Validators are at `:351-400`: entities non-empty and known, threshold in `[0, 1]`, max ≥ 1. |
| **What the four existing `PII_*` settings actually govern.** | These are not all "chat only":<ul><li>`PII_ENTITIES` and `PII_SCORE_THRESHOLD` feed `chat` only (`app/services/pii_policy.py:116-117`).</li><li>`PII_NLP_MODEL` backs the full analyzer (`pii_redactor.py:93`). That is `chat`'s, and `code`'s only if an NER type is added to `PII_ENTITIES_CODE` (`_NER_ENTITY_TYPES`, `:43`: PERSON, LOCATION, ORGANIZATION, NRP, DATE_TIME).</li><li>`PII_REDACTION_ENABLED` is the master switch for **every** policy (`pii_redactor.py:149,156,534`; `query_pipeline.py:133`, which also disarms the size arm).</li></ul>See D3. |
| **The size-limit arm.** | `query_pipeline.py:97-138`:<ul><li>It counts only roles the policy covers, measured on `strip_fenced_blocks(content)`.</li><li>Every `\n` is excluded, so fenced content counts zero.</li><li>The comparison is strict `>`.</li><li>It is off when `PII_REDACTION_ENABLED=false`.</li></ul>Refusal (`:425-432`): `reason="Conversation exceeds redaction limit"`, `limit="redaction_characters"`, audit `error_message="redaction limit: characters {actual} > {maximum}"`. `schemas.py:129` widens the literal. `chat.max_characters is None`, so the arm is unreachable from `/query` and the chat. |
| **The audit field.** | `AuditQueryEntry.profile: Optional[str] = None` (`app/models/schemas.py:185-190`), which is `NULL` on pre-PRD-012 rows and on `/query`'s foreign-session refusal. `/query` and the chat write `"chat"` (`tests/test_query_router.py:856`, `tests/test_chat_state.py:3309`). The README `GET /audit` example (`README.md:634-659`) does not show it yet. |
| **D5 does not change user-visible behaviour.** | `decisions/D5-placeholders.md:5`: "keep fixed `<TYPE>` placeholders (a) as the default … No production code changes". The story's note says to link D5 only if it changes user-visible behaviour, so the README **does not link it** (see D4). |
| **Logging caveat (STORY-007 finding).** | `LOG_LEVEL` is read by nothing, and no `logging.basicConfig` is called. So the "unknown profile falls back to `chat`" INFO line is emitted but not printed under the stock boot. The README must not claim that an operator will see it (STORY-007 handoff). |
| **Hand-offs addressed to this story.** | <ul><li>**STORY-002:** diff the characterization module against its commit.</li><li>**STORY-003:** `chat` ~10.2 s / 10.7 s at 200k, pattern path ~0.60 / 0.65 s, threads do not scale; quote beside ~0.93 s.</li><li>**STORY-005:** six settings in field order, each with a comment; `200000` without underscores; lowercase bools; guard tests per group.</li><li>**STORY-006:** "NER type" means the five in `_NER_ENTITY_TYPES`; adding one puts `code` on `en_core_web_lg` at lg's cost.</li><li>**STORY-013:** quote 463 ms against 1,500 ms; run the benchmark in the sweep; state names and places are not masked, fenced PII reaches the provider, a split span masks only its anchored part (F-1), JSON escapes are invisible to detection (F-4), and a letter escape before an IBAN or card in a source-code string can hide it (the open half).</li></ul> |
| **README line map (pre-edit).** | <ul><li>Features row `:155`.</li><li>Paragraph under the diagram `:140`.</li><li>*Multi-turn context*: "History is always redacted" `:195`, cost `:205`.</li><li>*Pattern policy* ends `:285` with its PRD-011 link, then `---`.</li><li>*Known limitations* PII bullets `:386`, `:388`.</li><li>Env table PII rows `:494-497`; last pattern row `PATTERN_MAX_SCAN_CHARACTERS` `:510`.</li><li>`### POST /query — blocked (context limit)` `:610-626`.</li><li>`GET /audit` JSON `:634-659`, paragraphs `:661-667`.</li><li>`GET /stats` line `:690`.</li><li>Troubleshooting PII entry `:765-766`.</li><li>Roadmap *Shipped* `:781-790`.</li><li>*OpenAI-compatible endpoint* paragraph `:811`.</li></ul>The TOC lists top-level sections only, so it needs no entry. |
| **Pre-PRD state.** | `pre-prds/PRE-PRD-012-pii-for-code.md` has `status: draft` and an empty `prd:`. The shape to match is `PRE-PRD-011`'s (`status: promoted`, `prd: .agents/PRDs/PRD-011-pattern-policy/PRD.md`). `pre-prds/README.md:18` reads `\| 3 \| [PII redaction for code](./PRE-PRD-012-pii-for-code.md) \| PRD-012 \| 12–14 \| 010 \| \`draft\` \|`. The Status column already exists (PRD-011 STORY-013 D1). |
| **`.env.example` has no PII guard tests yet.** | `tests/test_config.py` has guard groups for RBAC (`:64-77`), Turso (`:224-250`) and chat (`:334-360`), each with a comment check and a field-order check. None covers `PII_*`. |

### Design decisions

- **D1: Record the `test_pii_redaction_integration.py` hunk as a deviation; do not revert it.**
  - It adds one expected key to a contract assertion for an additive, nullable field. The assertion is stronger, not weaker, and it carries the PRD-012 D9 comment that PRD Section 11 *Quality indicators* requires of a modified pre-existing test.
  - Reverting it would make the test fail against the shipped `/audit` shape.
  - The report quotes the hunk and states: "no assertion removed or weakened; one expected key added (STORY-011, D9)". It does not claim "no changed assertion" literally. PRD-011 STORY-013 Task 1 set this precedent: evidence, not a byte-identity claim.
- **D2: One new README section, `### PII redaction`, under Features, after `### Pattern policy`.** This mirrors PRD-011 STORY-013 D4. Everything else points into it, so there is one source of truth for the role table and the trade-offs. The anchor is `#pii-redaction`. No existing heading collides with it: the Features table row is not a heading.
- **D3: Word the four existing rows accurately instead of stamping "chat only" on all of them.** AC 4 asks that they "say they apply to `chat`". Each row names `chat` explicitly, and each row says what it actually governs:
  - `PII_ENTITIES` and `PII_SCORE_THRESHOLD`: "`chat` profile only; `code` uses `*_CODE`".
  - `PII_NLP_MODEL`: "`chat`'s analyzer, and `code`'s only if `PII_ENTITIES_CODE` names an NER type".
  - `PII_REDACTION_ENABLED`: "master switch for every profile, `chat` and `code`".

  Writing "chat only" on the master switch would be false, and a reader would conclude that `code` cannot be turned off.
- **D4: Do not link D5 from the README.** The default placeholder is still fixed `<TYPE>`. The README states that plainly and adds one sentence of consequence for coding agents: an edit that quotes a masked value will not match the file on disk. It does not link the decision record. The PRD already links D5 (Section 15), and the README links the PRD.
- **D5: Leave the chat *Known limitations* bullets unchanged.** Under `chat`, the output is always analyzed, so `profile` changes nothing the bullets at `:386` and `:388` say (story note: "only where the `profile` field changes what they say"). The `code` semantics (`pii_detected_output = 0` means "not analyzed") go in the new section and in the `GET /audit` paragraph, where an auditor reads them.
- **D6: Add a `.env.example` guard group, and no README test.**
  - Guards: the six settings each have a comment line, and they appear in field order. This is STORY-005's handoff and the existing per-group pattern.
  - One substance check (the `test_env_example_says_what_the_off_state_does` shape): each of the four existing `PII_*` comment blocks mentions `chat`.
  - No test reads `README.md` today (PRD-010 STORY-018, PRD-011 STORY-013), so the README is checked with greps and a throwaway link checker.
- **D7: Document the size refusal inside the existing context-limit API section.** There is no new API section. It is the same response class with one more `limit` value (PRD Section 6.7), and it is unreachable from `POST /query`. The sentence "`limit` is `messages` or `characters`" becomes three values, with the third marked `code`-only and unreachable from `/query`.

---

## Patterns to Follow

### README feature section: bold lead-in claim, then the reason, then the test that proves it
```
// SOURCE: README.md:209-215, 237, 285
### Pattern policy

**What is matched, how, and against which messages is configuration, not code.** The patterns live in …

**An instruction planted in a tool result is recorded, and it still reaches the model.** State it plainly, because it is the one thing a reader could get wrong in the dangerous direction: …

The full design, including the threat reasoning behind each cell of the table, is in [PRD-011](.agents/PRDs/PRD-011-pattern-policy/PRD.md).
```

### Role table with one condensed reason line per cell
```
// SOURCE: README.md:223-231
| Profile | `system` | `user` | `assistant` | `tool` | Lists |
|---|---|---|---|---|---|
| `chat` | not inspected | **block** | not inspected | not inspected | `injection`, `keywords` |
| `code` | not inspected | **block** | not inspected | **flag** | `injection` |

- **`user` blocks in both.** The one cell that matches the previous release exactly.
```

### Measured figures: numbers, what dominates, the lever, the script
```
// SOURCE: README.md:205
**What it costs.** Measured on a session of 20 exchanges (41 messages, ~19k characters) against a local database: **about 0.93 s added per send** (p50 926 ms, p95 961 ms), growing roughly 23 ms per message. … The measurement script is `scripts/measure_history_latency.py`.
```

### Environment-variable row: default, validation as a startup error, the consequence
```
// SOURCE: README.md:510 (PATTERN_MAX_SCAN_CHARACTERS)
| `PATTERN_MAX_SCAN_CHARACTERS` | No | `1000000` | Most characters of any one message a pattern scan runs over. … A backstop far above anything `CONTEXT_MAX_CHARACTERS` admits by default. Must be at least `1`. |
```

### `.env.example` group: section header, one comment block per variable, no underscores in numbers
```
// SOURCE: .env.example:88-110
# Pattern policy (PRD-011)

# Optional path to a YAML file of pattern lists and profiles; empty uses the
# built-in policy and reads no file. …
PATTERNS_FILE=
```

### `.env.example` guard tests
```
// SOURCE: tests/test_config.py:334-360
def test_env_example_documents_both_chat_vars_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for var in ("CHAT_HISTORY_ENABLED", "CHAT_SESSION_LIMIT"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"

def test_env_example_chat_vars_appear_in_settings_field_order():
    ...
    positions = [text.index(f"{var}=") for var in declared_order]
    assert positions == sorted(positions)

def test_env_example_says_what_the_off_state_does():
    comment = re.search(r"(?m)((?:^#.*\n)+)CHAT_HISTORY_ENABLED=", text)
    block = comment.group(1).lower()
```

### Pre-PRD promotion frontmatter
```
// SOURCE: pre-prds/PRE-PRD-011-pattern-policy.md:1-11
status: promoted
prd: .agents/PRDs/PRD-011-pattern-policy/PRD.md
```

### Error handling
Not applicable: no production code changes, and no new error path is added. The refusal and error arms the README describes already exist (`query_pipeline.py:410-440`, and the redaction-error arm).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_config.py` | UPDATE | New `.env.example` guard group: six `*_CODE` settings commented and in field order; the four existing `PII_*` comment blocks name `chat` (D6) |
| `.env.example` | UPDATE | `# PII for code (PRD-012)` group with the six settings; the four `PII_*` comments say which profile they govern (D3) |
| `README.md` | UPDATE | New `### PII redaction` section (D2), plus replacements: Features row, architecture note, *Multi-turn context* cost pointer, env table (4 reworded, 6 new), context-limit API section (D7), `GET /audit` `profile`, `GET /stats` note, Troubleshooting, Roadmap, *OpenAI-compatible endpoint* sentence |
| `pre-prds/PRE-PRD-012-pii-for-code.md` | UPDATE | `status: promoted`, `prd: .agents/PRDs/PRD-012-pii-for-code/PRD.md` |
| `pre-prds/README.md` | UPDATE | Row 012: Target PRD linked, Status `promoted` |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Start the libSQL dev server before any pytest step: `docker start harness-libsql-dev`, or the `docker run` from README *Running Tests*. A mass of fixture errors means the dev server has degraded. Restart the container; do not bisect code.

### Task 1: Record the protected-file baseline before touching anything

- **File**: none (evidence for the report)
- **Action**: VERIFY
- **Implement**: Capture the state of the five protected files against the epic base.
- **Validate**:
  ```bash
  git diff --stat e10d191 HEAD -- tests/test_pii_redactor.py tests/test_pii_redaction_integration.py tests/test_pii_characterization.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py
  # expect: test_pii_characterization.py (created, +369) and test_pii_redaction_integration.py (+2) only
  git diff 5e93b18 HEAD -- tests/test_pii_characterization.py          # expect: empty (no change since creation)
  git diff e10d191 HEAD -- tests/test_pii_redaction_integration.py     # expect: exactly the D9 comment + "profile", hunk
  git diff e10d191 HEAD -- tests/test_pii_redaction_integration.py | grep -E '^-[^-]'   # expect: no output (nothing removed)
  git log --oneline e10d191..HEAD -- tests/test_pii_redaction_integration.py            # expect: faaa4be only
  ```
  Record all outputs in the report under D1.

### Task 2: `.env.example`: the six settings, and scope on the four existing ones

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**:
  - Reword the four existing comments at `:45-55`. The values do not change.
    - `PII_REDACTION_ENABLED`: "Master switch for PII redaction under every profile (chat and code): prompts, history, and responses where the profile redacts them (true/false)".
    - `PII_SCORE_THRESHOLD`: "… under the chat profile (code uses PII_SCORE_THRESHOLD_CODE)".
    - `PII_ENTITIES`: "… under the chat profile (code uses PII_ENTITIES_CODE)".
    - `PII_NLP_MODEL`: "… backs the chat profile's analyzer, and code's only if PII_ENTITIES_CODE names an NER type (PERSON, LOCATION, ORGANIZATION, NRP, DATE_TIME)". Keep the install hint.
  - Add a group **after `PATTERN_MAX_SCAN_CHARACTERS`**, the end of the file. That is `app/config.py` field order, since the six are declared after the pattern settings (`:216-240`). Head it `# PII for code (PRD-012)`, plus one line: "Used only where a call site runs the code profile; /query and the chat UI run chat, and no request can choose a profile". Then one comment block per variable, in field order:
    1. `PII_ENTITIES_CODE=EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE`: entity types under code. With no NER type in the list, a tokenizer-only analyzer runs and en_core_web_lg is never loaded for code. Adding PERSON or LOCATION masks names and places, at en_core_web_lg's cost.
    2. `PII_SCORE_THRESHOLD_CODE=0.40`: minimum confidence under code, 0 to 1. 0.40 is the highest value that still found every prose sample in the benchmark.
    3. `PII_MAX_CHARACTERS_CODE=200000`: most characters per request that code's redaction will analyze, fenced blocks and line breaks not counted. Over it, the request is refused (fail closed), never forwarded unmasked. Minimum 1.
    4. `PII_CODE_REDACT_OUTPUT=false`: redact the model's response under code. Off, because a coding agent writes its response into files, and a placeholder there corrupts them.
    5. `PII_CODE_REDACT_SYSTEM=false`: redact system turns under code. Off, because it is the client's own prompt and the largest fixed cost per request.
    6. `PII_CODE_SKIP_CODE_BLOCKS=true`: skip fenced code blocks under code. PII inside a fence reaches the provider unmasked. Prose around it, and inline backtick spans, are still masked.

    Keep ASCII hyphens, as the file does (`-`, not `—`). Numbers go without underscores and bools in lowercase (STORY-005 handoff).
- **Mirror**: `.env.example:88-110` (the PRD-011 group).
- **Validate**:
  ```bash
  python -c "from app.config import Settings; s=Settings(_env_file='.env.example'); print(s.PII_ENTITIES_CODE, s.PII_SCORE_THRESHOLD_CODE, s.PII_MAX_CHARACTERS_CODE, s.PII_CODE_REDACT_OUTPUT, s.PII_CODE_REDACT_SYSTEM, s.PII_CODE_SKIP_CODE_BLOCKS)"
  # expect: the six defaults, parsed with no validation error
  ```
  If `Settings(_env_file=...)` trips on the placeholder `DATABASE_URL`/`OPENROUTER_API_KEY`, set them in the environment for this one command. The point is that the six new lines parse.

### Task 3: `.env.example` guard group

- **File**: `tests/test_config.py`
- **Action**: UPDATE (append a group after the last `.env.example` group; change no existing test)
- **Implement**: A header comment `# --- PRD-012 STORY-014: .env.example documents the six PII code settings ---`, then:
  - `_PII_CODE_VARS` in `app/config.py` field order.
  - `test_env_example_documents_every_pii_code_var_with_a_comment`: the regex `rf"(?m)^#.+\n{var}="` for each.
  - `test_env_example_pii_code_vars_appear_in_settings_field_order`: derive the declared order from `Settings.model_fields` (keys filtered to the six) rather than a literal, so the test tracks `app/config.py`.
  - `test_env_example_pii_code_defaults_match_settings`: parse each `VAR=value` line and compare it with `Settings.model_fields[var].default`, normalising bools (`"false"` → `False`), the float and the int. A drift between the template and the code then fails.
  - `test_env_example_existing_pii_comments_name_their_profile`: for `PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `PII_ENTITIES` and `PII_NLP_MODEL`, the comment block above (`r"(?m)((?:^#.*\n)+){var}="`) contains `chat`. For `PII_REDACTION_ENABLED` it also contains `code`, since that switch governs both (D3). Assert on substance, not exact sentences, per the docstring of `test_env_example_says_what_the_off_state_does`.

  Each test docstring cites PRD-012 STORY-014 AC 4.
- **Mirror**: `tests/test_config.py:334-360`.
- **Validate**:
  ```bash
  pytest tests/test_config.py -q
  ```
  **Guard-bite, not committed**: swap two of the six lines in `.env.example` and check that the order test fails; delete `chat` from the `PII_ENTITIES` comment and check that the profile test fails. Revert both. Record in the report that each assertion can fail.

### Task 4: README, the `### PII redaction` section

- **File**: `README.md`
- **Action**: UPDATE (insert after `### Pattern policy`'s closing PRD-011 link line `:285`, before the `---`)
- **Implement**: `### PII redaction` (anchor `#pii-redaction`), in the bold-lead-in voice. One claim per paragraph:
  1. **Redaction is a policy per profile, chosen by the server.**
     - The same profile name as pattern policy selects it: `chat` for `POST /query` and the chat UI.
     - No request field chooses it (T1).
     - A profile name with no PII policy, such as a custom pattern profile, falls back to `chat`, the strictest.
     - Do **not** claim the fallback log line is visible. Say "logged once at startup at `INFO`" only if the report also notes it is not printed under the stock boot (STORY-007 finding). Otherwise omit the logging clause.
  2. **`chat` is exactly what it was.**
     - Every message on every send, history included, and the response.
     - `PII_ENTITIES` at `PII_SCORE_THRESHOLD`, with NER.
     - Pinned byte-for-byte by `tests/test_pii_characterization.py`, which no later change edited.
  3. **The role table** (PRD Section 6.3, reproduced exactly):

     | | `system` | `user` | `assistant` | `tool` | Output |
     |---|---|---|---|---|---|
     | `chat` | redact | redact | redact | redact (unreachable) | **redact** |
     | `code` | not redacted | redact prose | redact prose | redact prose | **not redacted** |

     Then one condensed reason line per `code` cell, from PRD 6.3:
     - output off (D1): the reader is the file system;
     - `system` off (D3): the client's own prompt, and the largest fixed cost;
     - `user` redacted, prose only;
     - `assistant` redacted, because a `/v1` client writes its own history (T7);
     - `tool` redacted, but no ingress sends one until PRD-016.

     Say "`code` has no HTTP ingress until the [OpenAI-compatible endpoint](#openai-compatible-endpoint) (PRD-014); in this release it is reached by direct call only". This mirrors *Pattern policy*'s sentence.
  4. **What `code` gives up, stated plainly.** A bullet list, one bullet per AC 2 item, each with its lever:
     - **Fenced blocks are not masked.** PII inside ```` ``` ```` or `~~~` reaches the provider. Prose around the fence is masked, and so are inline backtick spans. The parser is a heuristic, with PRD-011's limits: no indented blocks, and an unterminated fence runs to the end. Lever: `PII_CODE_SKIP_CODE_BLOCKS=false`. (T2)
     - **Names and places are not detected by default.** `Jane Doe` in prose goes out; `jane@corp.com` is masked. `code` runs pattern recognizers only: email, phone, card, SSN, IBAN. Lever: add `PERSON`/`LOCATION` to `PII_ENTITIES_CODE`. Any NER type (the five named) puts `code` on `en_core_web_lg` at `chat`'s cost, which the benchmark puts at 7× the budget. (T3, D7)
     - **The response is not masked.** The model has only what input redaction released, plus what it wrote itself. Lever: `PII_CODE_REDACT_OUTPUT=true`, at the cost of placeholders written into files. (T4)
     - **Placeholders are fixed `<TYPE>`.** An agent edit that quotes a masked value will not match the file on disk. This is the default and has no setting (D4 in this plan; do not link the decision record).
     - **Number tokens are quoted in JSON.** In a message whose content is a JSON document, a phone or card that is a JSON number becomes the string `"<PHONE_NUMBER>"`, so the document still parses. PII in a string value is replaced inside its quotes. If a redaction would still produce invalid JSON, the request fails closed with the redaction-error `500` and nothing goes upstream. (T6)
     - **Structure is never altered.** Quotes, backticks, backslashes and line breaks are never removed or added. A span that crosses one is split, and only the part holding the entity's anchor is replaced: `@` for an email, a digit for the rest (F-1). So `email='jane@example.com'` becomes `email='<EMAIL_ADDRESS>'`, not a syntax error.
     - **Escapes.** In JSON, escape sequences are invisible to detection, so `"\nGB82 …"` is still found (F-4). In a source-code string literal, a letter escape directly before an IBAN or card (`"card:\t4111 …"`) can hide it, under both profiles. This is recorded, not fixed (STORY-013 open half).
     - **Over the limit is refused, never skipped.** Over `PII_MAX_CHARACTERS_CODE` (200,000 analyzable characters: covered roles only, fenced content and line breaks not counted), the request is `BLOCKED` with `limit: "redaction_characters"` and audited `success=false`. It is never forwarded unmasked, and skip-and-flag is deliberately not shipped (T5, D4). Link `#post-query--blocked-context-limit`.
  5. **What the audit records.**
     - Every row `run_conversation` writes carries `profile`: `chat` from `/query` and the chat UI, `NULL` on rows from before this release.
     - `pii_detected_input` and `pii_entities` keep their meaning (the new turn plus the output).
     - Under `code`, `pii_detected_output` is `false` because the output was **not analyzed**, not because it was clean, and `profile` is what says so.
     - The audit still stores raw previews, as it always has (link `#get-audit-requires-auditreadall-or-auditreadown`, the anchor the existing heading produces; verify it in Task 9).
  6. **What it costs.** A small table: agent-shaped conversation, one system prompt, alternating turns, 13.7% fenced.

     | Characters | `chat` p95 | `code` p95 |
     |---|---|---|
     | 40,000 | 1,842 ms | 71 ms |
     | 200,000 | 10,750 ms | 465 ms |
     | 400,000 | 22,482 ms | 929 ms |

     Then the prose:
     - `code` at 200,000 is asserted under a **1,500 ms** budget by `tests/test_pii_code_corpus.py`, run with `--run-benchmark`. The last run was 463 ms.
     - NLP is 93% of `chat`'s cost, which is why `code` does not run it.
     - Threads do not help either profile: at concurrency 4, `chat`'s throughput is 0.70× and `code`'s 1.00×.
     - Put it beside the history figure explicitly: "The ~0.93 s per chat send in [Multi-turn context](#multi-turn-context) is this same `chat` cost at ~19k characters."
     - Name the host (Python 3.11.9, 12 logical CPUs; presidio 2.2.364, spaCy 3.8.16, now pinned in `requirements.txt`).
     - Name the script: `scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs 20`.
  7. Closing line: "The full design, including the threat reasoning behind each cell, is in [PRD-012](.agents/PRDs/PRD-012-pii-for-code/PRD.md)."

  Cross-check every number against the two reports. Round only as shown: ms to the integer, and the 463 ms figure as reported.
- **Validate**:
  ```bash
  grep -n "^### PII redaction" README.md                       # exactly one
  grep -n "redaction_characters" README.md                     # ≥ 2 (section + API)
  grep -n "measure_pii_latency.py" README.md                   # ≥ 1
  grep -n "0.93 s" README.md                                   # the original line still present
  grep -n -E "1,500 ms|463 ms" README.md                       # budget and measured figure
  grep -n "D5-placeholders" README.md                          # no hits (D4)
  ```

### Task 5: README, replacements and pointers

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**:
  - **Features row** `:155`:
    - Keep the first sentence's substance, but scope it: "Under the `chat` profile (`POST /query` and the chat UI), [Presidio] masks … in the prompt, the history, and the response."
    - Add: "A `code` profile for coding agents masks prose only, runs pattern recognizers only and leaves the response alone. See [PII redaction](#pii-redaction)."
    - Keep "Masking never blocks a request". Then qualify it: "under `chat`; under `code` a request too large to analyze is refused".
  - **Paragraph under the diagram** `:140`: add one sentence: the diagram is the `chat` profile; under `code`, the response box is skipped and `system` turns are not redacted (see `#pii-redaction`). The diagram itself is not edited.
  - ***Multi-turn context*, cost paragraph** `:205`: append one sentence pointing to `#pii-redaction` for the same cost at 40k–400k characters and the `code` profile's figures. Keep every existing number.
  - **Env table** `:494-497`, reworded per D3:
    - `PII_REDACTION_ENABLED`: "Master switch for PII redaction under **every** profile (`chat` and `code`) …". Keep the model-download clause.
    - `PII_SCORE_THRESHOLD`: prefix "Under the `chat` profile." and end "`code` uses `PII_SCORE_THRESHOLD_CODE`."
    - `PII_ENTITIES`: same shape, pointing at `PII_ENTITIES_CODE`.
    - `PII_NLP_MODEL`: "The `chat` profile's analyzer, and `code`'s only if `PII_ENTITIES_CODE` names an NER type." Keep the rest.
  - **Env table**: six new rows **after `PATTERN_MAX_SCAN_CHARACTERS`** (`:510`), in field order, before `REPORTS_*`. Each row gives the default, the validation as a **startup error**, and the consequence, per PRD 9.3 with the **final** defaults (`0.40`, `200000`, not the provisional ones):
    - `PII_ENTITIES_CODE`: non-empty, known names; no NER type means the tokenizer-only analyzer.
    - `PII_SCORE_THRESHOLD_CODE`: `0`–`1`; fixed from the benchmark.
    - `PII_MAX_CHARACTERS_CODE`: ≥ `1`; analyzable characters; over it is refused.
    - `PII_CODE_REDACT_OUTPUT`, `PII_CODE_REDACT_SYSTEM`, `PII_CODE_SKIP_CODE_BLOCKS`: what flipping each gives and what it costs.

    Each links `#pii-redaction` where useful.
  - **`### POST /query — blocked (context limit)`** (D7):
    - "`limit` is `messages` or `characters`" becomes "`limit` is `messages`, `characters` or `redaction_characters`".
    - Add one short paragraph after the check-order paragraph:
      - `redaction_characters` is the `code` profile's PII limit (`reason: "Conversation exceeds redaction limit"`);
      - it is checked at redaction, after the duplicate and pattern checks, because what it measures depends on the policy;
      - it is audited `success=false` with `error_message` naming it;
      - it is **unreachable from `POST /query`**, which runs `chat`.
    - The existing claim "**This is the only outcome this release adds**" describes the PRD-010 release. Leave it untouched unless it now reads as false about this release. If it does, change it to "the PRD-010 release added" wording, and note the change in the report.
  - **`GET /audit`**: add `"profile": "chat"` to the JSON example after `"pattern_action"`. Add one paragraph after the pattern paragraph (`:667`):
    - `profile` is the policy that ran;
    - it is `null` on rows before this release;
    - under `code`, `pii_detected_output: false` means "not analyzed";
    - link `#pii-redaction`.
  - **`GET /stats`** `:690`: append one sentence. `pii_detected_queries` counts what was analyzed, and a `code` row's output was not; no ingress runs `code` today, so the figures are unchanged.
  - **Troubleshooting** `:765-766`: append "Under the `code` profile the equivalents are `PII_SCORE_THRESHOLD_CODE` and `PII_ENTITIES_CODE`; the response itself is not masked there (see [PII redaction](#pii-redaction))."
  - **Roadmap *Shipped***: add `- [x] [PII redaction for code](#pii-redaction) — policy per profile, role and direction; fenced blocks skipped; within a measured latency budget` after the pattern-lists line. Leave `- [x] PII redaction on input/output` as it is: it is the `chat` behaviour and still true.
  - ***OpenAI-compatible endpoint*** `:811`: after "redacts every turn", add ", and the `code` PII policy that ingress will run, which leaves code blocks and the response unmasked, is built and measured (see [PII redaction](#pii-redaction))". The paragraph stays below the "intended direction" line, so the endpoint itself is still not claimed.
  - **Known limitations** `:386`, `:388`: **unchanged** (D5). Record the reason in the report.
- **Validate**:
  ```bash
  grep -n -E "PII_ENTITIES_CODE|PII_SCORE_THRESHOLD_CODE|PII_MAX_CHARACTERS_CODE|PII_CODE_REDACT_OUTPUT|PII_CODE_REDACT_SYSTEM|PII_CODE_SKIP_CODE_BLOCKS" README.md   # each ≥ 1, env rows present
  grep -n "0\.5\b" README.md | grep -i threshold       # no hit: the provisional 0.5 is not published
  grep -n '"profile"' README.md                        # the /audit example
  grep -n "#pii-redaction" README.md                   # several pointers
  ```
  Cross-check every documented default against `app/config.py:216-240`, row by row.

### Task 6: Promote the pre-PRD

- **Files**: `pre-prds/PRE-PRD-012-pii-for-code.md`, `pre-prds/README.md`
- **Action**: UPDATE
- **Implement**:
  - Brief frontmatter: `status: promoted` and `prd: .agents/PRDs/PRD-012-pii-for-code/PRD.md`, in the shape of `PRE-PRD-011`. The body is untouched.
  - `pre-prds/README.md:18`: `Target PRD` becomes `[PRD-012](../.agents/PRDs/PRD-012-pii-for-code/PRD.md)` and `Status` becomes `` `promoted` ``. No other row changes.
- **Validate**:
  ```bash
  grep -H -E "^(status|prd):" pre-prds/PRE-PRD-012-pii-for-code.md
  for f in pre-prds/PRE-PRD-0*.md; do echo "$f $(grep -m1 '^status:' $f)"; done   # every row's Status matches its brief
  grep -n "PRE-PRD-012" pre-prds/README.md
  ```

### Task 7: Link and anchor check (throwaway)

- **File**: scratchpad only (do not commit)
- **Action**: CREATE (throwaway)
- **Implement**: Reuse the PRD-010 STORY-018 / PRD-011 STORY-013 approach. Parse every `](…)` link in `README.md` and `pre-prds/README.md`:
  - relative file links must exist;
  - `#anchor` links must match a GitHub slug of a heading in the target file.

  Self-check the script against `git show HEAD:README.md` first. It should report only the pre-existing `SECURITY.md` miss.
- **Validate**: No new failures. In particular, `#pii-redaction`, `#post-query--blocked-context-limit`, the `GET /audit` anchor used in Task 4, `#openai-compatible-endpoint` and `.agents/PRDs/PRD-012-pii-for-code/PRD.md` all resolve.

### Task 8: Full sweep and scope checks

- **File**: none
- **Action**: VERIFY
- **Implement / Validate**:
  ```bash
  pytest tests/ -q
  # expect: 3326 + (Task 3's new tests) passed, 27 skipped; record exact counts
  pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s -q
  # expect: 1 passed; record the printed p95 (STORY-013: 463.23 ms). If it differs materially from 463 ms, the README quotes the report's figure and the report notes the rerun
  git diff --stat HEAD -- app/ chat_ui/ scripts/                        # empty
  git diff --stat HEAD -- tests/test_pii_redactor.py tests/test_pii_redaction_integration.py tests/test_pii_characterization.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py   # empty (this story touches none)
  git diff --stat HEAD                                                  # only the five files in Files to Change
  ```
  If there is a mass of libSQL fixture errors, restart the dev container and re-run; do not bisect.

---

## End-to-End Tests

- [ ] `pytest tests/ -q` is green; the counts are recorded.
- [ ] The `--run-benchmark` assertion passes, and the printed p95 at 200k is recorded against the 1,500 ms budget.
- [ ] Task 1's git evidence is recorded, and the D1 deviation is stated with the hunk quoted.
- [ ] The Task 3 guard-bites fail as expected, then are reverted.
- [ ] Read the README `### PII redaction` section top to bottom against AC 2 and tick each named item: `chat`/`code` described, the 6.3 table verbatim, fenced blocks unmasked, names and places not detected by default, output not masked, number tokens quoted in JSON, over-limit refused, `profile` in the audit.
- [ ] Read the env table against `app/config.py`: ten `PII_*` rows, four naming `chat` per D3, six new rows with final defaults.
- [ ] The link checker reports no new failures.

---

## Validation

```bash
python -c "import app.main"                      # backend imports (no app change, sanity only)
pytest tests/ -q
pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s -q
git diff --stat e10d191 HEAD -- tests/test_pii_redactor.py tests/test_pii_redaction_integration.py tests/test_pii_characterization.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py
```

Frontend lint: not applicable. There is no UI change and no linter is configured (STORY-013 report).

---

## Risks

| Risk | Mitigation |
|---|---|
| The AC's "no changed assertion" is read literally against the STORY-011 hunk | D1: the report quotes the hunk, shows nothing was removed, and cites the PRD's own rule for modified tests. If the reviewer wants it reverted, that is a STORY-011 regression to discuss, not something to do here |
| README figures drift from the reports | Every number in Task 4 is copied from a named report row; Task 8 reruns the benchmark and the report states both |
| Publishing the PRD's provisional values (`0.5` threshold) | Task 5's grep; defaults cross-checked against `app/config.py` |
| Over-claiming: fallback visible in logs, D5 as a behaviour change, `code` reachable over HTTP | STORY-007 finding, D4, and the explicit "direct call only / PRD-014" sentence |
| "Chat only" wording makes `PII_REDACTION_ENABLED` look unable to switch `code` off | D3 wording plus the Task 3 substance test |

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] Given the full suite, when it runs, then it is green, and `git diff` since the epic's base shows no changed assertion in `test_pii_redactor.py`, `test_pii_redaction_integration.py`, `test_pii_characterization.py`, `test_query_outcomes_regression.py` or `test_chat_outcomes_regression.py`. *(See D1: one additive expected key from STORY-011, reported as a deviation.)*
- [ ] Given the README PII section, when it is read, then it describes the `chat` and `code` profiles, reproduces the Section 6.3 role table, and states plainly: fenced blocks unmasked, names and places not detected by default, output not masked, number tokens quoted in JSON, over-limit refused, `profile` in the audit.
- [ ] Given the README, when it quotes latency, then it gives the STORY-003 / STORY-013 figures for both profiles beside the existing ~0.93 s history figure, and names `scripts/measure_pii_latency.py`.
- [ ] Given `.env.example` and the README configuration table, when they are read, then all six new settings appear with defaults and one-line purposes, and the four existing `PII_*` rows say they apply to `chat`.
- [ ] Given `pre-prds/PRE-PRD-012-pii-for-code.md` and `pre-prds/README.md`, when they are read, then the brief is `status: promoted` with `prd:` set, and its table row links PRD-012 with status `promoted`.
- [ ] All tasks completed
- [ ] Backend imports without error; no `app/`, `chat_ui/` or `scripts/` change
- [ ] Follows existing patterns (PRD-011 STORY-013 shape)
