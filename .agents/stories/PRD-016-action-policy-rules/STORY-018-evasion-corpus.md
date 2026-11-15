---
id: STORY-018
prd: PRD-016
slug: evasion-corpus
title: Evasion corpus — obfuscated variants of denied calls, none may produce allow
type: technical
priority: high
complexity: medium
phase: "4 - Evidence"
status: todo
labels: [tests, security, corpus]
epic_branch: epic/PRD-016-action-policy-rules
plan: null
report: null
commit: null
depends_on: [STORY-017]
blocks: [STORY-020]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-018: Evasion corpus — obfuscated variants of denied calls, none may produce allow

## Description

As a security admin, I want obfuscated versions of every denied call checked in and asserted never to be allowed, so that the classifiers are proven against the tricks an attacker would use and any regression is a red build.

## Acceptance Criteria

- [ ] Given `tests/corpora/actions/evasion/`, when counted, then it holds at least 30 files, each naming the synthetic file it is a variant of (`of:`), covering every group listed in PRD Section 11 (Corpus criteria): quoting and escapes, flag permutations, wrappers, chaining, substitution, `eval`/`source`, base64-to-interpreter, nested `bash -c`, SQL comments, casing and stacked statements, path tricks, URL tricks.
- [ ] Given each evasion file, when evaluated for every role in the test matrix (including `dba`), then the decision is never `allow`; the assertion message names the file, the decision and the rule.
- [ ] Given an evasion file whose `of:` target does not exist or is not itself a `deny`, when the suite collects, then it fails collection.
- [ ] Given a variant that the classifiers allow while the story is being written, when it is found, then the classifier is fixed in the same commit and the fix is recorded in the story report as a finding; the corpus is never edited to pass.

## Technical Notes

- Orchestrator note (STORY-010): candidate evasion rows the shell head tables do not cover yet: `format`, `diskpart`, `Clear-Disk`, winget/choco/dnf/yum/`npm ci`, PowerShell `rm -r X` (no force), and code no parse reaches (`python -c "os.system(..)"`, `find -exec`, `git -c alias.x=!cmd`, awk `system()`). Record each as caught or as a stated limitation.
- File shape (PRD F12): `{tool_call, of: <synthetic file>, expect: not_allow, technique: "..."}`.
- Extend `tests/test_action_corpus.py` with the evasion parametrization; seed from the tokenizer cases in STORY-009 and the URL/path cases in STORY-011/011.
- Each `technique` value comes from a fixed list mirroring the PRD's groups, so the suite can assert every group is covered.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-017
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 7 (F12), 9.2 (T2), 11 (Corpus criteria), 14 (Risk 1), 15 (D5)
