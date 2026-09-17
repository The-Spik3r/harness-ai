# Pre-PRDs — OpenAI-compatible endpoint track

Working briefs that feed `/create-prd`. Each file captures the problem, the evidence in the current code, the decisions still open, and a proposed scope — enough context for the PRD to be generated without re-deriving the analysis.

A pre-PRD is **not** a PRD: it has no stories, no epic branch, and no status board. Once its PRD exists under `.agents/PRDs/`, mark the pre-PRD `promoted` and link the PRD.

## Why this track exists

The README roadmap lists an [OpenAI-compatible endpoint](../README.md#openai-compatible-endpoint) so coding agents (OpenCode, Cline, Continue, Aider, the OpenAI SDKs) can point at the harness by changing one base URL. The router itself is small. What is not small is that every existing protection — duplicate detection, pattern detection, PII redaction, audit — was designed for a single-turn, human-written chat prompt, and each one misbehaves on a coding agent's multi-turn, code-heavy, auto-retrying traffic. This track fixes those first, then ships the endpoint, then tools.

## The briefs

| Order | Brief | Target PRD | Est. stories | Depends on |
|---|---|---|---|---|
| 1 | [Duplicate detection rescoping](./PRE-PRD-009-duplicate-rescoping.md) | PRD-009 | 8–10 | — |
| 2 | [Multi-turn pipeline](./PRE-PRD-010-multi-turn-pipeline.md) | PRD-010 | 16–20 | 009 |
| 3 | [Pattern policy per role](./PRE-PRD-011-pattern-policy.md) | PRD-011 | 10–12 | 010 |
| 3 | [PII redaction for code](./PRE-PRD-012-pii-for-code.md) | PRD-012 | 12–14 | 010 |
| 3 | [Audit & usage limits](./PRE-PRD-013-audit-and-usage-limits.md) | PRD-013 | 16–18 | 010 |
| 4 | [OpenAI-compatible endpoint (text)](./PRE-PRD-014-openai-compatible-endpoint.md) | PRD-014 | 14–16 | 011, 012, 013 |
| 4 | [Action policy rules](./PRE-PRD-015-action-policy-rules.md) | PRD-015 | 12–15 | 011 |
| 5 | [Tool calling on the compatible endpoint](./PRE-PRD-016-tool-calling.md) | PRD-016 | 10–12 | 014, 015 |

Estimated total: ~98–117 stories.

```
009 Duplicates ──► 010 Multi-turn ──┬──► 011 Patterns ──┬───────────────► 015 Action policy ─┐
                                    ├──► 012 PII ───────┤                                     ▼
                                    └──► 013 Audit ─────┴──► 014 Endpoint ──────────────► 016 Tools
```

- **Serial:** 009 → 010. Everything else depends on the message model 010 defines.
- **Parallel:** 011, 012 and 013 once 010 is done. 015 can start as soon as 011 lands (configurable lists are its prerequisite, per the README).
- **Milestone 1** — PRD-014 done: usable from the OpenAI SDKs, Aider and Continue.
- **Milestone 2** — PRD-016 done: drop-in for OpenCode and Cline in agent mode.

**Shortcut (explicit debt):** 009 → 010 → 014 with conservative defaults (patterns on `user` turns only, PII on input only, audit unchanged). ~38–46 stories. Do not start 016 until 011–013 and 015 are closed.

## How to promote a brief

1. Confirm the brief's **Open decisions** are answered (or accept the proposed defaults).
2. Run `/create-prd <slug>` with the brief in context. PRD IDs are assigned as max+1, so promoting in the order above keeps the numbers aligned; if not, update the "Target PRD" field.
3. Set the brief's `status: promoted` and fill `prd:` with the path.

## Status legend

- `draft` — analysis written, decisions open
- `ready` — decisions answered, can be promoted
- `promoted` — PRD exists
- `dropped` — superseded or out of scope
