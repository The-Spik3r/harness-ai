---
id: STORY-001
prd: PRD-012
slug: pii-corpora
title: "PII corpora: code, prose and JSON samples as checked-in files"
type: technical
priority: high
complexity: medium
phase: "1 - Measure and pin"
status: done
labels: [tests, pii, corpus]
epic_branch: epic/PRD-012-pii-for-code
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-001-pii-corpora.plan.md
report: .agents/reports/PRD-012-pii-for-code/STORY-001-pii-corpora.report.md
commit: beeb0b9
depends_on: []
blocks: [STORY-003, STORY-008, STORY-013]
skills: []
created: 2026-09-23
updated: 2026-09-23
---

# STORY-001: PII corpora: code, prose and JSON samples as checked-in files

## Description

As a security admin, I want the claims about false positives and masked PII to be tested against checked-in files, so that "it works on code" is evidence a reviewer can read rather than an assertion.

## Acceptance Criteria

- [ ] Given `tests/corpora/pii/code/`, when it is listed, then it holds at least one `.java`, `.ts`, `.py`, `.yaml` and `.json` file, each containing example emails, personal names and phone-shaped numbers, and at least one Markdown file mixing fenced (```` ``` ```` and `~~~`) and unfenced code with PII in the prose around the fences.
- [ ] Given the code corpus, when it is read, then it includes the named edge cases: a name with an apostrophe (`O'Brien`), a string literal whose PII sits right against its quotes, an escaped quote and a backslash path inside a string, and an unterminated fence.
- [ ] Given `tests/corpora/pii/prose/`, when each file is read, then it declares its expected entity types in a header (the PRD-011 `injections/` convention), covering at least `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `IBAN_CODE` and `PERSON`.
- [ ] Given `tests/corpora/pii/json/`, when each file is loaded with `json.loads`, then it parses; together they cover PII in string values, PII in keys, a phone and a card number as JSON **number** tokens, nesting, and `\\` / `\"` escapes inside strings.
- [ ] Given a small loader test (`tests/test_pii_corpus_files.py`), when it runs, then every JSON file parses, every `.py` file passes `ast.parse`, and every prose file has a readable expected-entities declaration. It asserts nothing about redaction yet.

## Technical Notes

- All data is synthetic: `example.com` / `example.org` domains, `555-01xx` phone numbers, test card numbers such as `4111 1111 1111 1111`, and IBAN test values. No real person's data goes into the repository. Record the provenance in `tests/corpora/pii/SOURCES.md`, the way `tests/corpora/agent_prompts/SOURCES.md` does.
- Mirror the PRD-011 layout (`tests/corpora/code/`, `agent_prompts/`, `injections/`). Keep this corpus under its own `pii/` directory; merging the two corpora is a Future Consideration (PRD Section 13).
- STORY-003 counts false positives over `code/` and times redaction over conversations built from it; STORY-008 and STORY-013 assert behaviour over all three directories. Make the files realistic in size, since a benchmark over 10-line toys measures nothing. Aim for a few hundred lines per source file.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-003, STORY-008, STORY-013

## PRD Reference

Source: [`PRD-012-pii-for-code/PRD.md`](../../PRDs/PRD-012-pii-for-code/PRD.md) — sections 4 (Corpora), 7 (F11), 11 (MVP definition)
