# PRD-016-action-policy-rules: Action Policy Rules — Every Tool Call Classified, Decided per Role and Audited Before It Leaves the Harness — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-016-action-policy-rules` (base: `main`)
**Status**: active

## Progress

18/20 stories done — 90%

## Stories

All stories commit on the epic branch `epic/PRD-016-action-policy-rules`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Action threat model and adapter survey (OpenCode, Cline, Aider) with SOURCES.md | spike | ✅ done | small | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-001-action-threat-model-and-adapter-survey.plan.md) | `322067d` |
| STORY-002 | Retarget the six "(PRD-016)" tool-calling runtime strings to "(PRD-017)" | technical | ✅ done | small | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-002-retarget-tool-calling-runtime-strings.plan.md) | `9f7b379` |
| STORY-003 | Rule ids, operation kinds, the six action permissions and authz.holds() | feature | ✅ done | small | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-003-rule-vocabulary-and-action-permissions.plan.md) | `598bb29` |
| STORY-004 | ToolCall, Operation, the tool mapping layer and built-in OpenCode/Cline/SQL mappings | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-004-tool-call-adapter-layer.plan.md) | `9e277d3` |
| STORY-005 | Three action settings; strict_yaml with duplicate-key rejection; pattern_config adopts it | technical | ✅ done | small | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-005-action-settings-and-strict-yaml.plan.md) | `f7824a1` |
| STORY-006 | action_config, part 1: ActionPolicy model, built-in policy, get_policy(), digest, both lifespans | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-006-action-config-loader.plan.md) | `8648e3a` |
| STORY-007 | action_config, part 2: ACTION_POLICY_FILE load, per-id rule merge, wholesale sections, validation, sample file | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-007-action-policy-file-load-and-validation.plan.md) | `7e765b7` |
| STORY-008 | SQL classifier with sqlglot — read, write, unscoped write, DDL, DCL, unparsed | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-008-sql-classifier.plan.md) | `a45ae85` |
| STORY-009 | Shell classifier, part 1: reject-scan, shlex tokenization, segments, wrappers and shell.unclassifiable | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-009-shell-tokenizer-and-unclassifiable.plan.md) | `4b220ce` |
| STORY-010 | Shell classifier, part 2: allowlist, destructive flags, pipe-to-interpreter, inline interpreters, installs, services | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-010-shell-command-rules.plan.md) | `48f74eb` |
| STORY-011 | Filesystem path rules — normalization, workspace containment, protected paths | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-011-filesystem-path-rules.plan.md) | `13a2de4` |
| STORY-012 | Network egress rules — URL parse, IDNA, allowlist, reserved addresses | feature | ✅ done | small | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-012-network-egress-rules.plan.md) | `33c5327` |
| STORY-013 | Secret access rules, and shell embedding of SQL, URLs and secret reads | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-013-secret-rules-and-shell-embedding.plan.md) | `cbcb58c` |
| STORY-014 | Decision engine: evaluate(), grants via holds(), most-severe-wins, safe reasons, fail closed | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-014-decision-engine.plan.md) | `dab8066` |
| STORY-015 | action_decisions table, indexes, record() and read functions | feature | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-015-action-decisions-table-and-record.plan.md) | `0ceb250` |
| STORY-016 | GET /audit/actions with audit scoping, and the three action counts on /stats | feature | ✅ done | small | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-016-audit-actions-endpoint-and-stats.plan.md) | `694a619` |
| STORY-017 | Synthetic tool-call corpus, its suite end to end through record(), and evaluate() latency | technical | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-017-synthetic-tool-call-corpus.plan.md) | `e67fd27` |
| STORY-018 | Evasion corpus — obfuscated variants of denied calls, none may produce allow | technical | ✅ done | medium | [plan](../../plans/PRD-016-action-policy-rules/completed/STORY-018-evasion-corpus.plan.md) | `pending` |
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
