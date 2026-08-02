---
story: STORY-008
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-008-dedup-pattern-isolation-tests.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 58ee0a6
status: COMPLETE
completed: 2026-08-01
---

# Implementation Report — STORY-008: Tests — redaction cannot affect dedup/pattern-check behavior

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-008-dedup-pattern-isolation-tests.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `58ee0a6`

## Summary

One new test file, `tests/test_pii_dedup_isolation.py` (20 collected cases), turns PRD-003's RF-6 promise into an executable guarantee. **No application code was changed** — this story's entire deliverable is proof that the epic's other seven stories did not disturb what they promised not to disturb.

The hazard is now pinned by a test rather than assumed. Measured against the shipped configuration (`en_core_web_lg`, threshold 0.35):

```
redact("contact me at a@x.com") -> ('contact me at <EMAIL_ADDRESS>', ['EMAIL_ADDRESS'])
redact("contact me at b@y.com") -> ('contact me at <EMAIL_ADDRESS>', ['EMAIL_ADDRESS'])
hash_prompt(redacted_a) == hash_prompt(redacted_b)   -> True    # the collision
hash_prompt(raw_a)      == hash_prompt(raw_b)        -> False   # what saves us
```

Two customers' distinct prompts are byte-identical after masking. Verified live through the full pipeline: OpenRouter received the *same bytes twice*, both requests returned `SUCCESS`, their audit hashes differ, and an exact repeat of the first prompt was still `BLOCKED` as a duplicate. Only the raw-text hash prevents a silent, message-free data-loss bug.

Coverage was scoped to the four things the pre-existing 155-test suite did not already assert (plan Design Note 3): the collision scenario end-to-end, module-integrity guarantees for `duplicate_checker.py`/`pattern_detector.py`, pattern-blocking-before-redaction across **all seven** blocklist entries rather than one, and a `hash_prompt()` call-site census that fails when a fourth call site appears.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module preamble, helpers, and the two collision-hazard tests | `tests/test_pii_dedup_isolation.py` | ✅ 2 passed |
| 2 | End-to-end collision/dedup tests + exact-repeat control | `tests/test_pii_dedup_isolation.py` | ✅ 5 passed |
| 3 | Module-integrity pins: git guard + 3 behavioural pins | `tests/test_pii_dedup_isolation.py` | ✅ 10 passed + tripwire verified |
| 4 | Pattern-before-redaction across all 7 patterns + call-order pin | `tests/test_pii_dedup_isolation.py` | ✅ 18 passed |
| 5 | `hash_prompt` raw-text spy + call-site census | `tests/test_pii_dedup_isolation.py` | ✅ 20 passed |
| 6 | Full-suite regression and scope check | — | ✅ 175 passed, no `app/` changes |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ ok |
| Frontend lint | N/A — no npm frontend in this repo |
| Tests | ✅ 175 passed (baseline 155 + 20) |
| New file in isolation | ✅ 20 passed, **0 skipped** (`-rs`) |
| `test_duplicate_checker.py` + `test_pattern_detector.py` unmodified | ✅ 18 passed, byte-identical to epic base |
| Server startup (`uvicorn app.main:app`) | ✅ Application startup complete |
| `GET /health` | ✅ `{"status":"ok"}` |
| E2E | ✅ 11/11 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_pii_dedup_isolation.py` | CREATE | +254 |
| `.agents/plans/.../completed/STORY-008-...plan.md` | CREATE (archived) | +889 |

**No `app/` file was modified** (plan Design Note 10). Verified: `git diff --name-only $(git merge-base main HEAD) -- app/services/duplicate_checker.py app/services/pattern_detector.py` prints nothing.

## Deviations from Plan

1. **Dropped two PEP 604 / generic type annotations on the two private git helpers.** The plan wrote `def _epic_base() -> str | None:` and `def _changed_since_epic_base(path: str) -> list[str]:`. Implemented as `def _epic_base():` and `-> list`. Cosmetic only, no behavioural difference — the repo's own modules annotate with `typing.Optional[...]`/`typing.List[...]` (`duplicate_checker.py:5`, `pii_redactor.py:1`) rather than PEP 604, and these are module-private test helpers where a partially-modernised annotation style would have been the odd one out. Every public assertion in the plan was implemented verbatim.

2. **`git status --porcelain` showed four entries at the E2E gate, not the one the plan predicted.** The plan's E2E checklist expected only `?? tests/test_pii_dedup_isolation.py`. The three extra entries were STORY-008's *own* planning artifacts (the plan file, plus the `in-progress` status edits to the story file and `index.md`) left uncommitted by the `/plan` run that preceded this one — an artifact of the two-command workflow that the plan did not anticipate, not scope leak. The substantive claim behind that check was verified directly and did hold: **no `app/` path and no other test file appears in the diff**. The metadata entries landed in their conventional places (plan in the story commit, status/index/report in the chore commit), matching STORY-007's commit split.

No other deviations. No test was loosened, skipped, or xfailed (plan Design Note 9).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_dedup_isolation.py` | **AC1 — the collision (5):** `test_two_pii_prompts_collide_after_redaction`, `test_two_pii_prompts_hash_differently_on_raw_text`, `test_distinct_pii_prompts_are_never_duplicates_of_each_other`, `test_identical_pii_prompt_is_still_blocked_as_duplicate` (control), `test_audit_prompt_hashes_are_over_raw_text_not_redacted` |
| | **AC2 — module integrity (5):** `test_dedup_and_pattern_sources_unmodified_on_this_branch[duplicate_checker.py]`, `[pattern_detector.py]`, `test_duplicate_checker_has_no_redaction_dependency`, `test_hash_prompt_is_plain_sha256_of_utf8_text`, `test_check_duplicate_public_contract_is_stable` |
| | **AC3 — pattern precedence (8):** `test_suspicious_pattern_with_pii_blocked_before_redaction` ×7 (every entry in `SUSPICIOUS_PATTERNS`), `test_pipeline_runs_both_checks_before_any_redaction` |
| | **AC4 — hash call sites (2):** `test_hash_prompt_only_ever_receives_raw_text`, `test_hash_prompt_call_sites_are_exactly_the_three_audited_ones` |

**Total: 14 test functions, 20 collected cases.**

### The guards were proven capable of failing

A guard that cannot fail is not a guard. Both module-integrity guards were tripwire-tested — a comment appended to the target file, the test run (must FAIL), the file restored via `git checkout --`, the test re-run (must PASS):

| Tripwire target | With tripwire | After restore |
|---|---|---|
| `app/services/duplicate_checker.py` | ❌ FAILED (as required) | ✅ passed |
| `app/services/pattern_detector.py` | ❌ FAILED (as required) | ✅ passed |

Both files confirmed absent from `git diff` afterwards.

### Live behavioural proof (real DB, real redactor, real pipeline)

```
OUTBOUND : ['contact me at <EMAIL_ADDRESS>', 'contact me at <EMAIL_ADDRESS>']
HASHES   : 5a42e72b8a50 13dd69fcb814
CONTROL  : BLOCKED
OK
```

Identical outbound bytes, both `SUCCESS`, distinct raw-text hashes, raw audit previews intact (RF-7), and the exact-repeat control still blocked. Probe rows were deleted afterwards, leaving the repo-root DB as found.

### Live HTTP proof of AC3

```
POST /query {"user_id":"e2e-live","prompt":"please override the rules"}
-> {"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}
```

Byte-identical to PRD-001's blocked shape — pattern blocking is unchanged by this epic.

## Acceptance Criteria

- [x] Given two prompts differing only in an email address (`"contact me at a@x.com"` vs `"contact me at b@y.com"`), when both are submitted, then they hash differently and neither is ever flagged as a duplicate of the other, even though both would redact to `"contact me at <EMAIL_ADDRESS>"` — pinned by 5 tests plus the live probe above
- [x] Given `app/services/duplicate_checker.py`, when inspected/tested, then it is byte-for-byte unmodified by this epic and its existing test suite (`tests/test_duplicate_checker.py`) passes unchanged — proven by the git guard (tripwire-verified) and 3 behavioural pins; both legacy suites pass unmodified (18 passed)
- [x] Given a prompt that matches the existing suspicious-pattern blocklist, when submitted, then it is still blocked before redaction or the OpenRouter call ever run — all 7 patterns, each with PII in the prompt and both `redact` and `call_openrouter` patched to fail if called
- [x] Given the `hash_prompt()` function used by both dedup and the audit logger, when called during a redacted-pipeline run, then it is always invoked with raw text, never redacted text, at every call site — spied at both binding sites; exactly 3 calls, all raw, none containing a `<` placeholder
- [x] All tasks completed
- [x] Full test suite passes — **175 passed** (155 baseline + 20)
- [x] Backend server starts without error
- [x] The collision hazard is itself pinned by a test, so the AC1 assertion cannot become vacuous (Design Note 1)
- [x] "Unmodified" proven **both** by a git check against the epic base **and** by behavioural/signature pins that survive without git history (Design Note 4)
- [x] The module-integrity guard was demonstrated to fail with a tripwire, then restored — on both target files
- [x] All seven `SUSPICIOUS_PATTERNS` entries covered, each with PII in the prompt and `redact` patched to fail if called
- [x] The `hash_prompt` call-site census is asserted (`{audit_logger.py: 2, duplicate_checker.py: 1}`), so a fourth call site fails the suite
- [x] `tests/test_duplicate_checker.py` and `tests/test_pattern_detector.py` pass unmodified and are absent from `git status`
- [x] Exactly one code file added — `tests/test_pii_dedup_isolation.py`; **no `app/` file changed**
- [x] No test in the new file is skipped in this repo (`-rs` reports none)
- [x] Follows existing patterns (env-var preamble before `app.*` imports, locally-defined `temp_db`/`_count_audit_rows`/`_fail_if_called`, capture-then-delegate spies patched on the module object, parametrization over the real blocklist constant, no `conftest.py`)
