# PRD-011-pattern-policy: Pattern Policy per Role — Configurable Lists, Word Matching, Inspected Conversations — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-011-pattern-policy` (base: `main`)
**Status**: draft

## Progress

2/13 stories done — 15%

## Stories

All stories commit on the epic branch `epic/PRD-011-pattern-policy`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Characterize today's substring detector before anything moves | technical | ✅ done | small | [plan](../../plans/PRD-011-pattern-policy/completed/STORY-001-pattern-detector-characterization.plan.md) | `29743aa` |
| STORY-002 | Word-boundary and regex pattern compilation | feature | ✅ done | medium | [plan](../../plans/PRD-011-pattern-policy/completed/STORY-002-word-and-regex-compilation.plan.md) | `116e0aa` |
| STORY-003 | Code-span stripping and the outside_code scope | feature | ⬜ todo | medium | — | — |
| STORY-004 | Four pattern-policy settings with startup validators | technical | ⬜ todo | small | — | — |
| STORY-005 | pattern_config: built-in policy, YAML loading, startup validation | feature | ⬜ todo | large | — | — |
| STORY-006 | Profiles and the role inspection matrix | feature | ⬜ todo | medium | — | — |
| STORY-007 | pattern_config.load() in both lifespans, and a working sample file | technical | ⬜ todo | small | — | — |
| STORY-008 | inspect() over the conversation; _inspection_target deleted; block arm | feature | ⬜ todo | large | — | — |
| STORY-009 | Flag arm, and pattern_role / pattern_action audit columns | feature | ⬜ todo | medium | — | — |
| STORY-010 | blocked_suspicious counts blocks only; role and action surfaced in /audit and the console | enhancement | ⬜ todo | medium | — | — |
| STORY-011 | Code and agent-prompt corpus: the false-positive claim as evidence | technical | ⬜ todo | medium | — | — |
| STORY-012 | Direct and indirect injection corpus | technical | ⬜ todo | medium | — | — |
| STORY-013 | Default-config /query regression, README, .env and the promoted pre-PRD | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-002
- STORY-005 blocked by STORY-002, STORY-003, STORY-004
- STORY-006 blocked by STORY-005
- STORY-007 blocked by STORY-005, STORY-006
- STORY-008 blocked by STORY-001, STORY-006
- STORY-009 blocked by STORY-008
- STORY-010 blocked by STORY-009
- STORY-011 blocked by STORY-008
- STORY-012 blocked by STORY-009, STORY-011
- STORY-013 blocked by STORY-007, STORY-010, STORY-011, STORY-012
