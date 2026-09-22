---
story: STORY-005
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-005-pattern-config-load-and-validate.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: 534ca17
status: COMPLETE
completed: 2026-09-22
---

# Implementation Report — STORY-005: pattern_config: built-in policy, YAML loading, startup validation

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-005-pattern-config-load-and-validate.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `534ca17`

## Summary

`app/services/pattern_config.py` now holds the whole of PRD-011's configuration surface: the three frozen dataclasses of PRD Section 6.2, a built-in policy reproducing today's seven patterns as PRD Section 6.3's two lists, `load()` over `PATTERNS_FILE`, `get_policy()`, and `PatternConfigError`. 57 cases in `tests/test_pattern_config.py` cover it. **No production code calls any of it** — STORY-007 registers `load()` in both lifespans, STORY-008's `inspect()` is the first reader of a compiled pattern — which is the same revertible posture STORY-002 through STORY-004 each held.

`load()` is `authz.load()`'s shape line for line where it can be: an empty setting returns before any I/O, the policy is replaced wholesale and never merged, and `_policy` is assigned as the very last statement so a file failing the ninth rule leaves the previous policy intact rather than a half-built one.

Two things in the diff are worth reading. First, the built-in policy was held to STORY-001's characterization corpus **directly** rather than on trust: all 19 pinned rows are walked, the 15 outside `PRD_011_FLIP_CASES` reproduce today's verdict and all 4 inside it produce their declared "after" verdict. That includes the fenced `@Override` row, which STORY-001 explicitly recorded as a *prediction* conditional on this story giving `keywords` `scope: outside_code` — the debt is paid here rather than deferred to STORY-008. Second, the `roles:` map is stored and deliberately **not** validated, because role and action vocabulary, the empty-`roles:` rule, `PATTERN_PROFILE_DEFAULT`'s cross-check and `get_profile()` all belong to STORY-006 by its own acceptance criteria; a test pins that boundary from this side so the split is visible rather than assumed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module skeleton — docstring, imports, `PatternConfigError`, closed vocabularies | `app/services/pattern_config.py` | ✅ |
| 2 | The three frozen dataclasses of PRD Section 6.2 | `app/services/pattern_config.py` | ✅ |
| 3 | Built-in policy (two lists, two profiles) and `get_policy()` | `app/services/pattern_config.py` | ✅ |
| 4 | List parsing and validation, incl. the regex gate and ReDoS heuristic | `app/services/pattern_config.py` | ✅ |
| 5 | Profile parsing, minimal and ordered for STORY-006 | `app/services/pattern_config.py` | ✅ |
| 6 | `load()` | `app/services/pattern_config.py` | ✅ |
| 7 | Tests — built-in policy and characterization parity (AC 1, AC 5) | `tests/test_pattern_config.py` | ✅ |
| 8 | Tests — wholesale replacement and compile-once (AC 2) | `tests/test_pattern_config.py` | ✅ |
| 9 | Tests — one case per malformed-file rule (AC 3) | `tests/test_pattern_config.py` | ✅ |
| 10 | Tests — regex gate and ReDoS heuristic (AC 4) | `tests/test_pattern_config.py` | ✅ |
| 11 | Full suite, and the no-consumer check | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `tests/test_pattern_config.py` | ✅ 57 passed |
| Neighbouring suites (`test_config`, `test_pattern_characterization`, `test_pattern_matching`, `test_pii_dedup_isolation`) | ✅ 172 passed, no assertion edited |
| Full suite | ✅ 2411 passed, 26 skipped, 2 pre-existing warnings, 215s |
| E2E | ✅ 9/9 |
| Frontend lint | n/a — no frontend file touched (this repo's UI is Reflex; this story's scope is a config loader) |

Baseline arithmetic: STORY-004's report recorded 2354 passed. 2354 + 57 new = 2411, so every pre-existing test still runs and still passes.

The two warnings are the pre-existing `StarletteDeprecationWarning` and `anyio.abc.BlockingPortal` deprecations, unrelated to this change.

**One transient failure, diagnosed not fixed.** The first full-suite run reported `ERROR tests/test_audit_router.py::test_response_never_includes_ip_or_raw_text` — a fixture error in an unrelated audit-router test. An identical re-run with no code change was clean. This is the known libSQL dev-server degradation under repeated suite runs that PRD Section 11's quality indicators and `tests/conftest.py` both name: mass or spurious fixture errors mean the container, not the code. Nothing in this story touches the database.

### E2E checklist

| # | Check | Result |
|---|-------|--------|
| 1 | `get_policy()` → `['injection', 'keywords']` with no `load()` call and `PATTERNS_FILE` unset | ✅ returns `BUILT_IN_POLICY` identically |
| 2 | `PATTERNS_FILE=""` → `load()` returns and `Path.read_text` is never called | ✅ zero reads |
| 3 | PRD Section 6.3's file verbatim → policy equal to the built-in in list names, scopes, pattern tuples, profile resolution and role maps | ✅ equal on every axis |
| 4 | `mach: word` → `PatternConfigError` naming the list and the key | ✅ `list 'keywords': unknown key 'mach' (expected one of: match, patterns, scope)` |
| 5 | `match: regex` with `PATTERNS_ALLOW_REGEX` false → error naming list and setting | ✅ `list 'risky': match: regex requires PATTERNS_ALLOW_REGEX=true` |
| 6 | Same file with the setting true → loads; `(a+)+` → error naming list and pattern | ✅ both |
| 7 | After a failing `load()`, `get_policy()` still returns the built-in policy | ✅ no half-applied state |
| 8 | `from app.main import app` still imports cleanly | ✅ |
| 9 | No production file outside `app/services/pattern_config.py` touched by this story | ✅ working tree showed only the new file |

E2E 3 is the one worth noting: PRD Section 6.3's sample file, comments included, parses to a policy equal to the built-in one. That is STORY-007's `examples/patterns.yaml` acceptance criterion proved a story early, so the format this story validates is demonstrably the format the PRD publishes.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pattern_config.py` | CREATE | +493 |
| `tests/test_pattern_config.py` | CREATE | +682 |
| `.agents/plans/PRD-011-pattern-policy/completed/STORY-005-…plan.md` | CREATE (archived) | +455 |

No existing production file was modified. `requirements.txt` needed nothing — STORY-004 already declared `PyYAML` explicitly.

## Deviations from Plan

1. **E2E check 9 was restated.** The plan wrote it as `git diff --name-only main...HEAD -- app/` naming only `pattern_config.py`. That command reports the whole epic branch against `main`, so it correctly lists the 12 files STORY-001 through STORY-004 changed. The per-story check is the working tree before staging (`git status --short app/`), which showed exactly one entry: `?? app/services/pattern_config.py`. The claim the check exists to prove — this story touches no other production file — holds.
2. **Two validation rules were added beyond AC 3's list**, both in the same spirit and both tested: `patterns:` given as a bare string rather than a sequence (`patterns: override` reads as one string in YAML, and iterating it would silently configure eight single-character patterns), and a profile missing its `lists:` key. Neither is an AC; both are the same "a policy arrived at by accident" failure T5 describes.
3. **`_check_keys` reports the first offender, not all of them.** A file with three unknown keys names one, and the operator fixes them one boot at a time. Matched to `authz.py`'s style and to the acceptance criterion, which asks that the message name "the offending list or profile and the rule that failed" — singular.

No deviation changed an acceptance criterion or a plan task.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_config.py` | 57 cases. **AC 1:** `load()` is a no-op and reads no file when `PATTERNS_FILE` is empty; the built-in lists hold exactly today's seven patterns (asserted against `SUSPICIOUS_PATTERNS` while it exists); the two lists are PRD 6.3's with their scopes; `keywords` order pinned as a tuple; patterns are compiled tuples; **19 parametrized parity cases** against `tests/test_pattern_characterization.py`'s corpus and flip set. **AC 2:** wholesale replacement (`injection`/`keywords` gone); compile-once with a call-counting spy; declared order survives parsing; profile lists resolve to objects; roles stored unvalidated (the STORY-006 boundary marker); built-in profiles carry the Section 6.4 matrix. **AC 3:** 17 parametrized malformed-file rows; missing path; and a sweep asserting every malformed message names the file path. **AC 4:** regex refused while the setting is false naming the setting; `word` lists unaffected; regex loads when true; uncompilable regex raising with `__cause__` a `PatternCompileError`; nested-quantifier refusal. **Shape:** dataclasses are frozen; `get_policy()` never touches the disk. |

The AC 1 parity test imports `_CASES` and `PRD_011_FLIP_CASES` from the characterization module rather than copying them. The coupling is deliberate and commented: a hand-copied corpus is one that drifts from the pinned one, and AC 1 is a claim about *that* corpus.

## Acceptance Criteria

- [x] Given `PATTERNS_FILE=""`, when `pattern_config.load()` runs, then no file is read and `get_policy()` returns the built-in policy, whose lists together hold exactly today's seven patterns and whose verdicts match STORY-001's characterization for every case outside that story's declared flip set.
- [x] Given a valid `PATTERNS_FILE`, when `load()` runs, then the built-in policy is replaced **wholesale** — a list present in the built-in policy and absent from the file is gone, asserted by a test — and every pattern is compiled once, at load, with `compile_pattern` from STORY-002.
- [x] Given a malformed file, when `load()` runs, then it raises `PatternConfigError` whose message names the offending list or profile and the rule that failed, for each of: a missing path, unparseable YAML, an unknown key in a list or profile, an unknown `match`, an unknown `scope`, an empty `patterns:`, a missing `lists:` or `profiles:` section, an empty `profiles:`, and a profile naming a list that is not defined.
- [x] Given `PATTERNS_ALLOW_REGEX=false` and a file containing a `match: regex` list, when `load()` runs, then it raises `PatternConfigError` naming the list and the setting to change. Given `PATTERNS_ALLOW_REGEX=true`, then an uncompilable pattern and a nested-quantifier pattern each raise `PatternConfigError` naming the list and the pattern.
- [x] Given `load()` has never been called, when `get_policy()` is called, then the built-in policy is returned rather than raising.
- [x] All tasks completed
- [x] Full suite green
- [x] Backend imports without error
- [x] No production file outside `app/services/pattern_config.py` is modified
- [x] Follows existing patterns (`authz.load()`, `app/models/messages.py` dataclasses, `tests/test_authz.py` fixtures)

## Notes for STORY-006 and STORY-007

- `_parse_profiles` is where STORY-006 extends: the `roles` line is a one-line `dict(...)` with a comment naming STORY-006's AC 2. Role and action validation, the empty-map rule and `PATTERN_PROFILE_DEFAULT`'s cross-check slot in beside it; `get_profile()` is a new public function next to `get_policy()`.
- `tests/test_pattern_config.py::test_roles_are_stored_but_not_validated_here` is the boundary marker and is written to be rewritten in place, with a comment citing PRD-011, when STORY-006 lands. It is not a claim that `martian: incinerate` is acceptable.
- STORY-007 can assert `examples/patterns.yaml` equals `BUILT_IN_POLICY`: the public name exists and is never rebound, and E2E check 3 already ran that comparison against PRD Section 6.3's text.
- STORY-008 replaces `tests/test_pattern_config.py`'s local `_verdict` walker with the real `inspect()`; the parity cases should move to that story's walk rather than being duplicated.
