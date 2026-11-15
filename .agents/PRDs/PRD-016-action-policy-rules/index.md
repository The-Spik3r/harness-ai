# PRD-016-action-policy-rules: Action Policy Rules — Every Tool Call Classified, Decided per Role and Audited Before It Leaves the Harness — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-016-action-policy-rules` (base: `main`)
**Status**: active

## Progress

0/20 stories done — 0%

## Stories

All stories commit on the epic branch `epic/PRD-016-action-policy-rules`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Action threat model and adapter survey (OpenCode, Cline, Aider) with SOURCES.md | spike | ⬜ todo | small | — | — |
| STORY-002 | Retarget the six "(PRD-016)" tool-calling runtime strings to "(PRD-017)" | technical | ⬜ todo | small | — | — |
| STORY-003 | Rule ids, operation kinds, the six action permissions and authz.holds() | feature | ⬜ todo | small | — | — |
| STORY-004 | ToolCall, Operation, the tool mapping layer and built-in OpenCode/Cline/SQL mappings | feature | ⬜ todo | medium | — | — |
| STORY-005 | Three action settings; strict_yaml with duplicate-key rejection; pattern_config adopts it | technical | ⬜ todo | small | — | — |
| STORY-006 | action_config, part 1: ActionPolicy model, built-in policy, get_policy(), digest, both lifespans | feature | ⬜ todo | medium | — | — |
| STORY-007 | action_config, part 2: ACTION_POLICY_FILE load, per-id rule merge, wholesale sections, validation, sample file | feature | ⬜ todo | medium | — | — |
| STORY-008 | SQL classifier with sqlglot — read, write, unscoped write, DDL, DCL, unparsed | feature | ⬜ todo | medium | — | — |
| STORY-009 | Shell classifier, part 1: reject-scan, shlex tokenization, segments, wrappers and shell.unclassifiable | feature | ⬜ todo | medium | — | — |
| STORY-010 | Shell classifier, part 2: allowlist, destructive flags, pipe-to-interpreter, inline interpreters, installs, services | feature | ⬜ todo | medium | — | — |
| STORY-011 | Filesystem path rules — normalization, workspace containment, protected paths | feature | ⬜ todo | medium | — | — |
| STORY-012 | Network egress rules — URL parse, IDNA, allowlist, reserved addresses | feature | ⬜ todo | small | — | — |
| STORY-013 | Secret access rules, and shell embedding of SQL, URLs and secret reads | feature | ⬜ todo | medium | — | — |
| STORY-014 | Decision engine: evaluate(), grants via holds(), most-severe-wins, safe reasons, fail closed | feature | ⬜ todo | medium | — | — |
| STORY-015 | action_decisions table, indexes, record() and read functions | feature | ⬜ todo | medium | — | — |
| STORY-016 | GET /audit/actions with audit scoping, and the three action counts on /stats | feature | ⬜ todo | small | — | — |
| STORY-017 | Synthetic tool-call corpus, its suite end to end through record(), and evaluate() latency | technical | ⬜ todo | medium | — | — |
| STORY-018 | Evasion corpus — obfuscated variants of denied calls, none may produce allow | technical | ⬜ todo | medium | — | — |
| STORY-019 | Admin console: the Actions view — recent decisions, deny first, filterable | feature | ⬜ todo | medium | — | — |
| STORY-020 | README, docs/features.md, docs/roadmap.md, .env.example; full regression; brief promotion verified | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-004 blocked by STORY-001, STORY-003
- STORY-006 blocked by STORY-003, STORY-004
- STORY-007 blocked by STORY-005, STORY-006
- STORY-008 blocked by STORY-007
- STORY-009 blocked by STORY-006
- STORY-010 blocked by STORY-009
- STORY-011 blocked by STORY-006
- STORY-012 blocked by STORY-006
- STORY-013 blocked by STORY-008, STORY-010, STORY-011, STORY-012
- STORY-014 blocked by STORY-004, STORY-008, STORY-013
- STORY-015 blocked by STORY-014
- STORY-016 blocked by STORY-015
- STORY-017 blocked by STORY-014, STORY-015
- STORY-018 blocked by STORY-017
- STORY-019 blocked by STORY-016
- STORY-020 blocked by STORY-002, STORY-018, STORY-019
