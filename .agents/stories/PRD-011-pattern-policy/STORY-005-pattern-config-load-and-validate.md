---
id: STORY-005
prd: PRD-011
slug: pattern-config-load-and-validate
title: "pattern_config: built-in policy, YAML loading, startup validation"
type: feature
priority: high
complexity: large
phase: "2 - Configuration and profiles"
status: done
labels: [backend, config, security]
epic_branch: epic/PRD-011-pattern-policy
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-005-pattern-config-load-and-validate.plan.md
report: .agents/reports/PRD-011-pattern-policy/STORY-005-pattern-config-load-and-validate.report.md
commit: 534ca17
depends_on: [STORY-002, STORY-003, STORY-004]
blocks: [STORY-006, STORY-007]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-005: pattern_config: built-in policy, YAML loading, startup validation

## Description

As a platform operator, I want the pattern lists loaded from a file I control and validated at startup, so that I can change policy without a code change and a broken file stops the boot instead of silently disabling protection.

## Acceptance Criteria

- [ ] Given `PATTERNS_FILE=""`, when `pattern_config.load()` runs, then no file is read and `get_policy()` returns the built-in policy, whose lists together hold exactly today's seven patterns and whose verdicts match STORY-001's characterization for every case outside that story's declared flip set.
- [ ] Given a valid `PATTERNS_FILE`, when `load()` runs, then the built-in policy is replaced **wholesale** — a list present in the built-in policy and absent from the file is gone, asserted by a test — and every pattern is compiled once, at load, with `compile_pattern` from STORY-002.
- [ ] Given a malformed file, when `load()` runs, then it raises `PatternConfigError` whose message names the offending list or profile and the rule that failed, for each of: a missing path, unparseable YAML, an unknown key in a list or profile, an unknown `match`, an unknown `scope`, an empty `patterns:`, a missing `lists:` or `profiles:` section, an empty `profiles:`, and a profile naming a list that is not defined.
- [ ] Given `PATTERNS_ALLOW_REGEX=false` and a file containing a `match: regex` list, when `load()` runs, then it raises `PatternConfigError` naming the list and the setting to change. Given `PATTERNS_ALLOW_REGEX=true`, then an uncompilable pattern and a nested-quantifier pattern each raise `PatternConfigError` naming the list and the pattern.
- [ ] Given `load()` has never been called, when `get_policy()` is called, then the built-in policy is returned rather than raising — the pipeline (STORY-008) and every test that never boots an app depend on that, exactly as `ROLE_PERMISSIONS` stands on its own before `authz.load()` runs.

## Technical Notes

- New file `app/services/pattern_config.py`, modelled on [app/services/authz.py](../../../app/services/authz.py)'s `load()` / `AuthzConfigError`: return early on an empty setting, replace the module-level policy wholesale, never merge, never fall back silently (PRD Sections 6.3, 6.9).
- `yaml.safe_load` only. Wrap every `yaml.YAMLError` in `PatternConfigError` with the path (PRD Risk 7). Catch `PatternCompileError` from STORY-002 and re-raise with the list name attached — that is why there are two exception types.
- Frozen dataclasses `PatternList` and `PatternPolicy` exactly as in PRD Section 6.2, with `compiled` built at load. Not pydantic: loaded once at startup by our own validator (PRD Section 8).
- Declared order is load-bearing and must survive parsing: `inspect()` reports lists in declared order and patterns in declared order (PRD Section 6.2, F5). `yaml.safe_load` preserves mapping order on Python 3.7+, but store lists as a `tuple` so nothing downstream can reorder them.
- Unknown-key rejection is what makes acceptance criterion 2 of STORY-002's sibling user story work (`mach: word` → a named error). Validate keys against an explicit allowed set per node type; do not silently ignore extras.
- `PATTERN_PROFILE_DEFAULT` validation and the profile model land in STORY-006; this story stops at lists. Keep `load()`'s profile handling minimal but ordered so STORY-006 extends rather than rewrites it.
- Tests in `tests/test_pattern_config.py`, one case per malformed-file rule. Write the files under `tmp_path`, not in the repo.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-003, STORY-004
- **Blocks**: STORY-006, STORY-007

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 4 (Configuration), 6.2, 6.3, 6.9, 7 (F3), 8, 9.2 (T4, T5, T7), 11 (Functional requirements)
