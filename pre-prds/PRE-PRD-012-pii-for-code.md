---
target_prd: PRD-012
slug: pii-for-code
title: PII redaction for code and large contexts
status: draft
prd:
depends_on: [PRD-010]
blocks: [PRD-014]
estimated_stories: 12-14
created: 2026-09-16
---

# PII redaction for code and large contexts

## Problem

[pii_redactor.py](../app/services/pii_redactor.py) runs Presidio + spaCy (`en_core_web_lg`) over the full input and the full output, replacing entities with fixed placeholders.

- **It corrupts code.** Identifiers read as `PERSON`/`LOCATION`; example emails and IPs in configs, tests and fixtures are real matches. Redacting the **output** means a coding agent writes `<EMAIL_ADDRESS>` into the user's files.
- **It breaks structure.** Redacting inside a JSON tool-call argument can leave it invalid.
- **It is not reversible.** The model answers with `<PERSON>`, the agent sends that back next turn, and context degrades turn over turn.
- **Latency.** spaCy over 50–100k tokens, twice per request, CPU-bound under the GIL.
- **Shape.** `redact(text: str)`; OpenAI `content` may be a list of parts or `null` (normalized by PRD-010, but the policy per part is undefined).
- `PII_SCORE_THRESHOLD=0.35` is tuned for prose, not code.

## Goal

A PII policy that protects personal data in what humans write without corrupting code the agent reads or writes, with a latency budget that holds on large contexts.

## Proposed scope

**In**
- Benchmark first: latency and false positives on real code contexts at 10k/50k/100k tokens.
- Policy by direction (input/output) and by profile (`chat`/`code`, shared with PRD-011).
- Policy by role (redact `user`; decide for `tool`, `system`, `assistant`).
- Detect and skip fenced code blocks (configurable).
- Never redact inside tool-call arguments; guarantee valid JSON if any structured content is touched.
- Size limit with a defined behaviour when exceeded.
- Spike and decision: fixed vs. reversible (per-conversation mapping) placeholders.
- Audit telemetry keeps working (`pii_detected_input/output`, `pii_entities`).

**Out**
- Non-English models.
- Secret detection (API keys, tokens) — belongs with action policy / patterns.

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | Output redaction under `code` profile? | Off. Input-only. |
| D2 | Code blocks under `code` profile? | Skipped for input too; prose around them is redacted. |
| D3 | Which roles are redacted? | `user` and `tool`; `system` configurable; `assistant` history already redacted (PRD-010 D5). |
| D4 | Over the size limit? | Refuse with explicit reason (fail closed), configurable to skip-and-flag. |
| D5 | Reversible placeholders? | Not in this PRD unless the spike shows fixed placeholders make agents unusable; a stored mapping is itself PII at rest. |
| D6 | Separate threshold for `code`? | Yes, `PII_SCORE_THRESHOLD_CODE`, set from benchmark data. |

## Evidence

- `redact()` returns `(text, entities)`; pipeline calls it on the prompt and on `openrouter_result.response`.
- `PII_ENTITIES` default includes `PERSON` and `LOCATION`, the two most code-noisy types.

## Success criteria

- A source file with example emails and names round-trips through the `code` profile without syntax-breaking changes.
- `chat` profile behaviour identical to today.
- p95 redaction latency under a set budget at 50k tokens (budget fixed by the benchmark story).
- No tool-call argument is ever modified.

## Risks

| Risk | Mitigation |
|---|---|
| Skipping code blocks lets real PII through inside code | Documented trade-off; profile is per endpoint, not per caller. |
| Benchmark shows spaCy cannot meet any reasonable budget | Fallback: regex-only recognizers for `code` profile. |
| Reversible mapping creates a new sensitive store | Deferred by default (D5). |

## Tentative story breakdown

1. Benchmark harness and baseline numbers
2. Direction policy settings
3. Profile + role policy
4. Code-block detection and skipping
5. Structured-content guard (no redaction in tool args, JSON validity)
6. Size limit and over-limit behaviour
7. Code threshold setting
8. Placeholder spike + decision record
9. Pipeline integration over messages
10. Audit telemetry regression
11. Code round-trip corpus
12. `chat` profile regression
13. README and `.env` docs
