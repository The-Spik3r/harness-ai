---
id: STORY-003
prd: PRD-011
slug: code-span-stripping-and-scope
title: "Code-span stripping and the outside_code scope"
type: feature
priority: high
complexity: medium
phase: "1 - Pin and match"
status: done
labels: [backend, security]
epic_branch: epic/PRD-011-pattern-policy
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-003-code-span-stripping-and-scope.plan.md
report: .agents/reports/PRD-011-pattern-policy/STORY-003-code-span-stripping-and-scope.report.md
commit: a7f75a2
depends_on: [STORY-002]
blocks: [STORY-005]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-003: Code-span stripping and the outside_code scope

## Description

As an integrating developer, I want keyword patterns not to fire on text inside code fences, so that pasting a diff into a prompt is not read as an attack.

## Acceptance Criteria

- [ ] Given `strip_code_spans(text)` in [app/services/pattern_detector.py](../../../app/services/pattern_detector.py), when the text contains a ```` ``` ````-fenced or `~~~`-fenced block opening at the start of a line, then that block's content is replaced and the surrounding text is returned unchanged.
- [ ] Given a stripped span, when the result is compared with the input, then `len(result) == len(text)` and every non-newline character of the span has become a newline — so a match offset in the stripped text still points at the same character in the original, and the lines either side of a stripped block cannot fuse into one phrase.
- [ ] Given inline spans, when the text contains `` `override` ``, ``` ``a `b` c`` ``` or a triple-backtick inline span, then their contents are stripped; given a lone unmatched backtick, then nothing is stripped and no exception is raised.
- [ ] Given an unterminated fence, when the text opens ```` ``` ```` and never closes it, then everything from the fence to the end of the text is stripped.
- [ ] Given `override` inside a fence and `override` outside it in the same text, when matched against a `scope: outside_code` list, then only the outside hit is reported; when matched against a `scope: everywhere` list, then the first hit in text order is reported, fence or not.

## Technical Notes

- Fence detection is line-based: an opening fence is three or more backticks or tildes at the start of a line (leading whitespace allowed, per CommonMark's three-space tolerance), and the closer is a run of the same character at least as long. An info string (` ```python `) is part of the opening line and is itself stripped.
- Inline spans are scanned after fences are removed, so a backtick inside a fenced block never opens an inline span.
- Do the stripping **once per message per scope requested**, not once per pattern (PRD Section 7 F2 and Risk 8). The natural shape is for `inspect()` (STORY-008) to compute at most two variants of a message's content — raw and stripped — and hand the right one to each list.
- This is a heuristic and the docstring must say so: unfenced source gets no protection from it, which is why the `code` profile's answer to `@Override` is not loading the keyword list at all (PRD Section 6.5). Do not oversell it in the docstring — a later reader deciding whether `tool` turns are safe will read exactly that sentence.
- The injection list is `scope: everywhere` precisely so that wrapping `ignore previous instructions` in a fence is not an evasion (PRD 9.2 T6). Add a test named for that threat.
- Tests extend `tests/test_pattern_matching.py`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 4 (Matching), 6.5 (D3), 7 (F2), 9.2 (T6), 11 (Functional requirements)
