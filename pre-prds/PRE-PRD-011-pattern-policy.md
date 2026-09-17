---
target_prd: PRD-011
slug: pattern-policy
title: Pattern policy per role
status: draft
prd:
depends_on: [PRD-010]
blocks: [PRD-014, PRD-015]
estimated_stories: 10-12
created: 2026-09-16
---

# Pattern policy per role

## Problem

[pattern_detector.py](../app/services/pattern_detector.py) is a hardcoded list of lowercase substrings matched anywhere in the prompt.

- **False positives on code.** `"override"` matches `@Override` (Java), `override` (TypeScript, C#, Kotlin), `!important` override comments, CSS. `"execute code"` and `"admin mode"` appear in coding agents' own system prompts. Applied to a full agent context, nearly every request would be blocked.
- **Substring, not word.** `"override"` also matches `overrides`, `overridden`.
- **Not configurable.** Same list for every deployment and every kind of traffic — the roadmap item *Configurable, per-deployment pattern lists* is still open.
- **Scope dilemma.** Inspecting only the human's turn misses **indirect injection** — instructions planted in a file, web page or tool result the agent read. Inspecting everything blocks legitimate code.

The README makes configurable lists a prerequisite of *Action policy rules* (PRD-015).

## Goal

Pattern detection that is configurable per deployment, matches words not substrings, and applies a documented policy per message role — measured against a real code corpus, not assumed.

## Proposed scope

**In**
- Word-boundary / regex-capable matching.
- Pattern lists loaded from a file (`PATTERNS_FILE`), validated at startup, defaulting to today's list.
- Profiles (e.g. `chat`, `code`) selecting which lists apply.
- A role inspection matrix: which roles each profile checks (`user`, `system`, `assistant`, `tool`).
- Audit records *which role* triggered the block.
- Two corpora in tests: code that must pass; direct and indirect injections that must block.

**Out**
- ML/semantic injection classifiers.
- Output (response) inspection — belongs with action policy in PRD-015.

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | Which roles does the `code` profile inspect? | `user` and `tool`; not `system` (client-authored) or `assistant` (model-authored, already passed). |
| D2 | How is the profile chosen? | Per endpoint (`/query` → `chat`, `/v1` → `code`), overridable per role in RBAC. |
| D3 | Does a hit inside a fenced code block count? | Configurable per list; default: injection phrases count everywhere, keyword lists skip code blocks. |
| D4 | Block or flag? | Block for `user`; flag-and-audit for `tool` in the first release, promote to block once corpus data exists. |
| D5 | File format | YAML, one list per name, with `match: word|regex`. |

## Evidence

- `SUSPICIOUS_PATTERNS` is a module constant; `detect_suspicious_pattern` does `pattern in prompt.lower()`.
- README *Action policy rules*: "These rules are per-deployment configuration, which makes *Configurable, per-deployment pattern lists* a prerequisite."

## Success criteria

- Code corpus (Java/TS/C# with `override`, three real coding-agent system prompts) passes under `code`.
- Injection corpus blocks, including at least one indirect injection in a `tool` turn.
- Default configuration reproduces today's `/query` behaviour.
- An invalid patterns file stops startup with a clear error.

## Risks

| Risk | Mitigation |
|---|---|
| A permissive `code` profile becomes a bypass for chat users | Profile selected by endpoint, not by the caller. |
| Flag-only on `tool` lets indirect injection through | Explicit in threat model; PRD-015 is the enforcement point for actions. |
| Regex patterns enable ReDoS | Timeout / linear-time engine, or restrict to word matching. |

## Tentative story breakdown

1. Characterization tests of current detector
2. Word-boundary matching
3. Patterns file format, loading and startup validation
4. Profiles
5. Role inspection matrix
6. Pipeline applies the matrix over messages
7. Audit column for triggering role
8. Code false-positive corpus
9. Direct and indirect injection corpus
10. `/query` regression under default config
11. README and `.env` docs
