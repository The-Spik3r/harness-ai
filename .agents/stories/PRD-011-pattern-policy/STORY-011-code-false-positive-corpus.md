---
id: STORY-011
prd: PRD-011
slug: code-false-positive-corpus
title: "Code and agent-prompt corpus: the false-positive claim as evidence"
type: technical
priority: high
complexity: medium
phase: "4 - Prove and document"
status: todo
labels: [backend, tests, security]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: [STORY-008]
blocks: [STORY-012, STORY-013]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-011: Code and agent-prompt corpus: the false-positive claim as evidence

## Description

As an integrating developer, I want the harness's "safe for code" claim backed by real source files and real agent system prompts in the test suite, so that a future change that reintroduces false positives fails CI instead of my requests.

## Acceptance Criteria

- [ ] Given `tests/corpora/code/`, when the suite runs, then it holds at least a Java file with `@Override`, a TypeScript file with an `override` member, a C# file with `public override`, a Kotlin file with `override fun`, and a CSS file with `!important` override comments — each a plausible file, not a one-line stub — and every one of them passes clean under the `code` profile as a `user` turn.
- [ ] Given `tests/corpora/agent_prompts/`, when the suite runs, then it holds three real coding-agent system prompts with provenance recorded in `SOURCES.md` (agent, version or date, where it came from), and each passes clean under the `code` profile in a `system` turn **and** in a `user` turn.
- [ ] Given at least one agent prompt, when it is run through the **built-in `chat`** profile as a `user` turn, then it is blocked — asserted, with a comment explaining that this is the proof the corpus is not vacuous (PRD Risk 5). The test names the pattern that catches it.
- [ ] Given every corpus file, when the test parametrizes over the directory, then files are discovered from disk rather than listed in the test body, so adding a sample needs no test edit, and an empty corpus directory fails rather than passing vacuously.
- [ ] Given the `CONTEXT_MAX_MESSAGES` ceiling, when a conversation of that many corpus messages is inspected, then the elapsed time is measured and recorded in this story's report (PRD Section 11, Quality indicators) — a number in the report, not an assertion with a threshold in CI.

## Technical Notes

- Files on disk, not inline strings (PRD Section 7 F8): a reviewer must be able to read them as code, and an operator adding a sample should not have to edit a test.
- The three agent prompts are the load-bearing part. They are what demonstrate the claim in PRD Section 1 — that today's detector would block close to every coding-agent request — and what justify `system` not being inspected under `code` (PRD Section 6.4). Record provenance honestly in `SOURCES.md`; if a prompt is reconstructed or abridged rather than verbatim, say so in that file.
- "Passes clean" means `inspect()` returns no block **and** no flag. Assert both, not just the absence of a block.
- Keep this corpus separate from STORY-001's characterization cases: that one describes the old detector, this one describes the new policy.
- New file `tests/test_pattern_corpus.py`, shared with STORY-012, which adds the injection half.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: STORY-012, STORY-013

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 1, 4 (Corpora), 6.4, 7 (F8), 11 (Corpus criteria), 14 (Risk 5)
