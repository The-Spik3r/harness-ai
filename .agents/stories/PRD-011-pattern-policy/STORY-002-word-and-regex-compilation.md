---
id: STORY-002
prd: PRD-011
slug: word-and-regex-compilation
title: "Word-boundary and regex pattern compilation"
type: feature
priority: high
complexity: medium
phase: "1 - Pin and match"
status: todo
labels: [backend, security]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-003, STORY-005]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-002: Word-boundary and regex pattern compilation

## Description

As a platform operator, I want patterns matched as words rather than substrings, so that ordinary vocabulary in a prompt is not reported as an injection attempt.

## Acceptance Criteria

- [ ] Given `compile_pattern(pattern, match="word")` in [app/services/pattern_detector.py](../../../app/services/pattern_detector.py), when it compiles `override`, then the result matches `override` and `Override`, and does **not** match `overrides`, `overridden` or `overriding`. It **does** match `@Override`, and a test asserts that explicitly with a comment citing PRD Section 6.2 — word boundaries do not fix that case, and a later story must not be written as though they did.
- [ ] Given `compile_pattern("ignore previous instructions", match="word")`, when the subject is `ignore\nprevious  instructions` or `Ignore Previous Instructions`, then it matches; when the subject is `ignoreprevious instructions`, it does not.
- [ ] Given a pattern containing regex metacharacters (`a.b`, `c+d`), when compiled with `match="word"`, then the metacharacters are matched literally — the tokens are `re.escape`d before being joined with `\s+`.
- [ ] Given `compile_pattern(pattern, match="regex")`, when the pattern is valid, then it is returned compiled with `re.IGNORECASE`; when it does not compile, then `PatternCompileError` is raised naming the pattern and the underlying `re.error` text.
- [ ] Given `has_nested_quantifier(pattern)`, when the pattern is `(a+)+`, `(\w*)*` or `(x+)*y`, then it returns `True`; when it is `overrid\w*` or `ignore\s+previous`, then it returns `False`. The docstring states it is a heuristic for the common catastrophic shape, not a proof of linear-time matching (PRD 9.2 T4).

## Technical Notes

- `app/services/pattern_detector.py` stays a **pure module**: no `settings` import, no file I/O, nothing read at import. It is the `app/models/messages.py` shape (PRD Section 6.9). Everything that reads configuration lives in `pattern_config.py` (STORY-005), including the `PATTERNS_ALLOW_REGEX` gate — this story only provides the primitives and the heuristic that the gate calls.
- Word compilation: `r"\b" + r"\s+".join(re.escape(tok) for tok in pattern.split()) + r"\b"`, `re.IGNORECASE`. Reject an empty or whitespace-only pattern with `PatternCompileError`.
- `PatternCompileError` is raised by the primitives; `pattern_config` catches it and re-raises as `PatternConfigError` with the list name attached (STORY-005). Two exception types on purpose: the pure module cannot know which list a pattern came from.
- Do not touch `detect_suspicious_pattern` or `SUSPICIOUS_PATTERNS` in this commit — the pipeline still calls them, and STORY-001's characterization must stay green. They are removed in STORY-008.
- New tests in `tests/test_pattern_matching.py`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-003, STORY-005

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 4 (Matching), 6.2, 7 (F1), 9.2 (T3, T4), 11 (Functional requirements)
