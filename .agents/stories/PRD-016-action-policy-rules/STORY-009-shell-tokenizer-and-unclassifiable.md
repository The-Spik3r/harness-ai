---
id: STORY-009
prd: PRD-016
slug: shell-tokenizer-and-unclassifiable
title: "Shell classifier, part 1: reject-scan, shlex tokenization, segments, wrappers and shell.unclassifiable"
type: feature
priority: high
complexity: medium
phase: "3 - Classifiers and the engine"
status: done
labels: [backend, security, classifier]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-009-shell-tokenizer-and-unclassifiable.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-009-shell-tokenizer-and-unclassifiable.report.md
commit: pending
depends_on: [STORY-006]
blocks: [STORY-010]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-009: Shell classifier, part 1: reject-scan, shlex tokenization, segments, wrappers and shell.unclassifiable

## Description

As a security admin, I want every shell command split into the commands it actually runs, with anything the tokenizer cannot fully read denied, so that quoting, chaining and substitution cannot hide what runs.

## Acceptance Criteria

- [x] Given `npm test && rm -rf build; ls | wc -l & echo x` (and the same with a newline), when segmented, then the segments are `npm test`, `rm -rf build`, `ls`, `wc -l`, `echo x`, each with the operator that joined it, in order.
- [x] Given `r''m -rf /`, `"rm" -rf /`, `\rm -rf /` and `/usr/bin/rm -rf /`, when tokenized and the head is extracted, then the head is `rm` in every case.
- [x] Given `sudo rm x`, `env FOO=1 rm x`, `FOO=1 rm x`, `nohup rm x`, `time rm x`, `xargs rm`, `doas rm x`, when the head is extracted, then the wrappers and assignments are stripped and the head is `rm`.
- [x] Given any of `ls $(cat x)`, a backtick substitution, `eval "$C"`, `source x.sh`, `. x.sh`, `diff <(a) <(b)`, `cat <<< x`, `$CMD arg`, an unbalanced quote, or nesting of `bash -c` deeper than three levels, when classified, then the result contains `shell.unclassifiable` and the function never raises.
- [x] Given the module, when imported, then it reads no settings and performs no I/O; `classify_shell` exposes the segment list for STORY-010 to apply head rules to.

## Technical Notes

- New `app/services/action_classifiers/shell.py`. The reject-scan runs on the raw string **before** `shlex`, because `shlex` removes the quotes that make `$(` visible (PRD Section 6.8, steps 1–4).
- `shlex.shlex(command, posix=True, punctuation_chars=";&|")` with `whitespace_split=True`; a `ValueError` (unbalanced quotes) → `shell.unclassifiable`.
- Newlines are segment separators; treat `\r\n` like `\n`.
- Head extraction: basename of argv[0] after stripping wrappers and leading `NAME=value` tokens. A head that starts with `$` is unclassifiable.
- Recursion depth for inline interpreters is tracked here (limit 3); STORY-010 decides what `-c` means.
- Tests: new `tests/test_action_shell.py` (tokenizer and segment cases); these cases are the seed of STORY-018's evasion corpus.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Classifiers: shell), 6.3 (`shell.unclassifiable`), 6.8, 9.2 (T2, T12), 15 (D3, D5)
