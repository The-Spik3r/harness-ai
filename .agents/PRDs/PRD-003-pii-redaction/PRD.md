---
id: PRD-003
slug: pii-redaction
title: PII Redaction (Presidio) — Input & Output Masking
status: draft
base_branch: main
epic_branch: epic/PRD-003-pii-redaction
created: 2026-07-23
updated: 2026-07-31
---

## 1. Executive Summary

Harness IA (PRD-001) already intercepts every prompt/response pair, but today it forwards raw prompt text to OpenRouter and returns the raw model response to the caller with no protection against personally identifiable information (PII) leaking to a third-party model provider. This PRD closes the "PII redaction on input/output" item already listed in the project roadmap.

The feature adds **Microsoft Presidio** (Analyzer + Anonymizer) as a new pipeline step. It runs on both directions of traffic — the outbound prompt before it reaches OpenRouter, and the inbound model response before it reaches the caller — and **masks** detected PII entities in place. It never blocks a request: masking-only was chosen deliberately so this feature cannot introduce a new denial-of-service failure mode alongside the existing duplicate/pattern blocks.

The MVP is intentionally narrow, mirroring the scoping discipline of PRD-001: **English-only** text coverage (Spanish/LATAM-specific identifiers like DNI or CUIT/CUIL are an explicit non-goal), no reversible de-anonymization, and no attempt to optimize the latency Presidio's NLP inference adds — that cost is accepted for the MVP and revisited later. The duplicate-detection hash and the audit log's raw-text preview are both explicitly **unchanged** by this feature — redaction only affects what leaves the system (to OpenRouter) and what the caller sees back; it does not affect what internal audit review can see.

## 2. Mission

Prevent personal data present in user prompts or model responses from reaching a third-party model provider, without ever denying a legitimate request.

Core principles:
- **Mask, never block**: redaction changes what text looks like, never whether a request completes. Consistent with the existing pipeline's philosophy that blocking is reserved for duplicate/pattern checks only.
- **Recall over precision**: when uncertain, redact. An over-masked response is an acceptable cost; an unmasked leak is not.
- **English-first, extensible later**: ship solid English coverage now rather than a shallow multi-language pass; Spanish/LATAM recognizers are a tracked follow-up, not a blocker for this MVP.
- **No interference with existing guarantees**: the duplicate-detection hash and the audit log's raw-text retention are untouched — this feature only changes what is sent externally and what is returned to the caller.
- **Portable by default**: same NLP dependency footprint and behavior in `python app.py` and Docker, consistent with PRD-001's portability principle.

## 3. Target Users

**Security/Compliance Admin** — Wants confidence that PII typed into a prompt, or produced by a model in its response, never reaches OpenRouter unmasked. Still needs the *raw* text available via `/audit` to investigate what was actually attempted — redaction protects the third party, not the internal audit trail. Technical level: same as PRD-001 (comfortable with REST APIs and env vars).

**End User (Employee)** — Sends prompts that may incidentally contain personal data (a name, an email, a phone number) without realizing it. Wants their data protected automatically, with no extra step, and no risk of their request being rejected because of it. Technical level: non-technical to technical, interacts only through the existing chat UI or `/query`.

**Integrating Developer** — Wants this feature to be invisible to the existing `POST /query` contract: no new required fields, no behavior change to duplicate/pattern blocking, so already-integrated tools keep working unmodified.

## 4. MVP Scope

### In Scope
- [ ] Presidio `AnalyzerEngine` + `AnonymizerEngine` integrated as a new pipeline step, running **after** the existing duplicate-check and pattern-check steps
- [ ] English-only NLP model (`en_core_web_lg`, or `en_core_web_trf` if recall requires it) loaded **once** at service startup (FastAPI `lifespan`), never per-request
- [ ] PII redaction applied to the **outbound prompt** before it is forwarded to OpenRouter
- [ ] PII redaction applied to the **model's response** before it is returned to the caller
- [ ] Default entity set: `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `IBAN_CODE`, `LOCATION` — configurable via env var
- [ ] Confidence threshold tunable via env var, defaulting to a **permissive/low** value that favors recall over precision (business preference: masking too much is safer than missing real PII)
- [ ] Duplicate-check hash continues to operate on the **raw** prompt, exactly as in PRD-001 — no change to `duplicate_checker.py`, no change to existing dedup tests
- [ ] Audit log continues to store the **raw, unredacted** `prompt_preview`/`response_preview` (unchanged from PRD-001) — auditors need to see exactly what was attempted, not the masked version
- [ ] New audit fields recording whether PII was detected on input/output and which entity types, so `/stats` can report redaction activity without exposing the masked values themselves
- [ ] API response includes a lightweight signal that redaction occurred (see Section 10), so callers/UI can surface it without seeing the underlying PII

### Out of Scope
- [ ] Spanish/LATAM-specific entity recognizers (DNI, CUIT/CUIL, Argentine phone formats, etc.) — English-only for this MVP
- [ ] Reversible de-anonymization / encrypted mapping storage to "unmask" for legitimate internal use
- [ ] Latency optimization for the NER inference step (async processing, model distillation, streaming) — cost accepted for MVP, tracked as future work
- [ ] Encryption at rest for the audit log's PII-bearing columns
- [ ] RBAC for `/audit` access (already tracked separately in the PRD-001 roadmap; this feature increases the value of that item but does not implement it)
- [ ] Any change to what the duplicate-check hashes, or to the pattern-injection blocklist
- [ ] Custom ML scoring beyond Presidio's built-in recognizer confidence scores

## 5. User Stories

1. **As an end user**, I want any PII I type into a prompt masked before it leaves the organization's infrastructure, so my personal data is never sent to the third-party model provider.
   - Example: prompt `"my email is juan@empresa.com, can you draft a reply?"` is forwarded to OpenRouter as `"my email is <EMAIL_ADDRESS>, can you draft a reply?"`.

2. **As an end user**, I want PII appearing in the model's response also masked before I see it, so a model that echoes back or infers personal data doesn't expose it to me either.
   - Example: a response containing a name the model inferred or repeated is masked to `<PERSON>` before being returned in the `POST /query` response.

3. **As a compliance admin**, I want the audit log to retain the raw, unmasked text, so I can investigate exactly what PII was attempted to be sent, not just that "something" was masked.
   - Example: `GET /audit` still returns the same raw `prompt_preview`/`response_preview` fields as today, unchanged by this feature.

4. **As a compliance admin**, I want the system to favor over-masking over under-masking, so missed PII is minimized even at the cost of occasional false positives on ordinary text.
   - Example: the confidence threshold is tuned low enough that borderline matches (e.g., a name-like word) are masked rather than passed through.

5. **As an integrating developer**, I want PII redaction added with zero changes to the existing `POST /query` request contract, so already-integrated tools keep working unmodified.
   - Example: the same request shape from PRD-001 Section 10 still works; only the outbound/returned text and one new optional response field change.

6. **As a security admin**, I want duplicate-detection behavior completely unaffected by redaction, so two legitimately distinct requests from different users are never conflated because their redacted text happens to look identical.
   - Example: two different customers' prompts, differing only in an email address, still hash differently and are never treated as duplicates of each other.

7. **As a devops engineer**, I want the Presidio NLP model loaded once at service startup, so redaction doesn't add cold-start latency to every individual request.
   - Example: the `en_core_web_lg` model loads during the FastAPI `lifespan` startup hook, not inside the `/query` request handler.

8. **As a product owner**, I want this MVP scoped to English-only text, so the core masking capability ships now, with Spanish/LATAM recognizer work explicitly deferred to a follow-up PRD rather than blocking this one.

## 6. Core Architecture & Patterns

```
POST /query
   │
   ▼
1. Verify user_id present                         (unchanged, PRD-001)
2. Hash raw prompt → duplicate check (24h)         (unchanged, PRD-001 — operates on RAW text)
3. Pattern check (injection) on raw prompt         (unchanged, PRD-001)
4. PII Analyze (Presidio) on raw prompt            (NEW)
5. PII Anonymize → redacted_prompt                 (NEW)
6. Forward redacted_prompt to OpenRouter           (CHANGED: was raw prompt)
7. Receive raw model response
8. PII Analyze + Anonymize on response             (NEW) → redacted_response
9. Audit log write:
     - prompt_hash / response_hash over RAW text   (unchanged)
     - prompt_preview / response_preview = RAW     (unchanged — auditor needs raw text)
     - pii_detected_input, pii_detected_output,
       pii_entities (types found)                  (NEW columns)
10. Return redacted_response to caller             (CHANGED: was raw response)
```

The raw prompt/response only ever exist in-memory during steps 2–8 of a single request — never persisted or transmitted in raw form beyond the audit log's existing raw-preview fields (which are a deliberate, pre-existing exception documented in Section 9).

New module:
```
app/services/pii_redactor.py     # Presidio AnalyzerEngine + AnonymizerEngine wrapper
                                  # exposes redact(text) -> (redacted_text, entities_found)
                                  # NLP engine loaded once as a module-level singleton
```

Changes to existing modules:
- `app/main.py` — `lifespan` loads the Presidio `AnalyzerEngine`/NLP model once at startup, alongside whatever else is already initialized there.
- `app/routers/query.py` — pipeline gains steps 4–5 (before the OpenRouter call) and step 8 (after receiving the response), inserted around the existing `openrouter_client` call.
- `app/services/audit_logger.py` — gains `pii_detected_input`/`pii_detected_output`/`pii_entities` fields on write; `prompt_preview`/`response_preview` logic is **not** modified.
- `app/db/models.py` — `audit_logs` table gains the three new columns above.

Design patterns:
- **Pipeline pattern**, extending the existing 8-step `query.py` flow from PRD-001 with two additional stages, keeping each stage independently testable — consistent with PRD-001 Section 6.
- **Singleton/startup-loaded resource**, mirroring how `OPENROUTER_API_KEY` and DB setup are already handled in `lifespan`, applied to the Presidio NLP engine to avoid per-request load cost.
- **Adapter pattern** in `pii_redactor.py` — isolates all Presidio-specific API surface behind a single `redact(text)` function, so the pipeline code has no direct Presidio import.

## 7. Tools/Features

| Feature | Maps to | Detail |
|---|---|---|
| Input redaction | RF-1, RF-2 | Prompt is analyzed and anonymized after duplicate/pattern checks, before the OpenRouter call. |
| Output redaction | RF-3 | Model response is analyzed and anonymized before being logged/returned. |
| Startup-loaded NLP engine | RF-4 | `en_core_web_lg` (or `_trf`) loaded once in `lifespan`, shared across requests. |
| Recall-biased threshold | RF-5 | Confidence threshold configurable, defaults low to favor masking borderline matches. |
| Dedup isolation | RF-6 | `duplicate_checker.py` untouched; hash always computed over raw text. |
| Raw audit retention | RF-7 | `prompt_preview`/`response_preview` remain raw text, unchanged from PRD-001. |
| Redaction telemetry | RF-8 | New audit columns (`pii_detected_input`, `pii_detected_output`, `pii_entities`) feed future `/stats` reporting without exposing masked values. |
| Response signal | RF-9 | `POST /query` response gains an optional field indicating redaction occurred (Section 10). |

## 8. Technology Stack

**Backend (additions to PRD-001's stack)**
- `presidio-analyzer` — PII detection (NER + built-in recognizers)
- `presidio-anonymizer` — applies masking operators to detected entities
- `spacy` + `en_core_web_lg` model (English NLP model backing Presidio's analyzer)

**Testing**
- `pytest` cases asserting: redacted text never reaches the OpenRouter client mock; duplicate-check hash is computed from raw text regardless of redaction; audit log preview fields remain raw and unchanged.

**Deployment**
- Same Docker/`docker-compose` parity goal as PRD-001. Note: the spaCy model adds meaningfully to image size/build time and container memory footprint — documented as an accepted tradeoff in Section 14, not a blocker.

**Dependencies (additions to `requirements.txt`)**
```
presidio-analyzer
presidio-anonymizer
spacy
en_core_web_lg  # installed via: python -m spacy download en_core_web_lg
```

## 9. Security & Configuration

**Redaction scope**
- Applies to the outbound prompt (→ OpenRouter) and the inbound model response (→ caller).
- Does **not** apply to: the text hashed for duplicate detection, or the raw preview text persisted to the audit log — both remain exactly as in PRD-001.

**Why the audit log stays raw (explicit decision)**
Compliance/security review needs to see exactly what PII was attempted, not a masked placeholder — an auditor investigating an incident needs the actual value, not `<EMAIL_ADDRESS>`. This is a deliberate continuation of PRD-001's existing behavior (the `response_preview` field was already raw text), not a new exception introduced by this feature.

**Residual risk this decision accepts**
The audit log is now a more clearly identified, concentrated store of PII than before this feature existed to name what's in it. Access to it is still gated only by a single shared `ADMIN_TOKEN` bearer secret — the RBAC item from the PRD-001 roadmap remains unimplemented. This is documented as an accepted residual risk (Section 14, Risk 4), not resolved by this PRD.

**Environment variables (additions)**
```bash
# PII Redaction
PII_REDACTION_ENABLED=true
PII_SCORE_THRESHOLD=0.35        # low/permissive by design — favors recall over precision
PII_ENTITIES=PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION
PII_NLP_MODEL=en_core_web_lg
```

**In scope for MVP security**: masking of outbound prompt and inbound response, recall-biased threshold, no change to existing dedup/pattern/audit security posture.

**Out of scope for MVP security**: encryption at rest for audit PII columns, RBAC on `/audit`, reversible unmasking, non-English recognizers.

## 10. API Specification

### `POST /query` — request
Unchanged from PRD-001 — no new required fields.

### `POST /query` — response (success, redaction occurred)
```json
{
  "status": "SUCCESS",
  "response": "Sure, I'll draft a reply to <EMAIL_ADDRESS>.",
  "audit_id": 1,
  "model_used": "gpt-4",
  "tokens_used": 45,
  "pii_redacted": true,
  "pii_entities_masked": ["EMAIL_ADDRESS"]
}
```
`pii_redacted` / `pii_entities_masked` are additive fields; existing integrations that ignore unknown fields are unaffected. When no PII is detected, `pii_redacted` is `false` and `pii_entities_masked` is an empty list.

### `GET /audit` (admin token required) — additions
```json
{
  "audit_id": 1,
  "user_id": "juan@empresa.com",
  "prompt_preview": "my email is juan@empresa.com, can you draft a reply?",
  "pii_detected_input": true,
  "pii_detected_output": true,
  "pii_entities": ["EMAIL_ADDRESS"]
}
```
`prompt_preview`/`response_preview` remain raw text, exactly as in PRD-001 — the new fields only add redaction telemetry.

### `GET /stats` (admin token required) — additions
```json
{
  "pii_detected_queries": 34,
  "top_pii_entities": ["EMAIL_ADDRESS", "PERSON"]
}
```

## 11. Success Criteria

**MVP definition of done**
- [ ] Prompts containing default-entity PII (English) are masked before reaching the OpenRouter client
- [ ] Model responses containing default-entity PII are masked before being returned to the caller
- [ ] `duplicate_checker.py` and its existing tests are unmodified and still pass — hash is computed over raw text
- [ ] `prompt_preview`/`response_preview` in the audit log remain raw and unchanged from PRD-001
- [ ] Presidio NLP model loads once at startup (`lifespan`), not per-request
- [ ] `/audit` and `/stats` expose new PII telemetry fields without exposing masked values as distinct new leak surface

**Quality indicators**

| Metric | Target |
|---|---|
| Default-entity PII masked (English text) | Best-effort, recall-biased — no hard SLA (probabilistic by nature, documented limitation) |
| Existing dedup/pattern test suite | 100% pass, unmodified |
| Latency added per request | Accepted for MVP — no ceiling target; optimization deferred |
| False positives on output masking | Accepted — mask-only means no functional break, per business preference for recall over precision |

## 12. Implementation Phases

**Phase 1 — Presidio Integration** (~2 days)
- Goal: `pii_redactor.py` wrapping Presidio Analyzer + Anonymizer, English model loaded once at startup.
- Deliverables: `app/services/pii_redactor.py`, `lifespan` change in `main.py`, `requirements.txt` additions.
- Validation: `redact("my email is a@b.com")` returns masked text with `EMAIL_ADDRESS` reported, model loads once and is reused across calls.

**Phase 2 — Pipeline Wiring** (~2 days)
- Goal: insert redaction into `query.py` at the two points specified in Section 6, without touching steps 1–3.
- Deliverables: updated `query.py`, `audit_logger.py` + `db/models.py` with new columns.
- Validation: outbound call to OpenRouter (mocked in tests) never receives raw PII; returned response to caller is the masked version; audit row still stores raw preview.

**Phase 3 — Isolation Testing** (~2 days)
- Goal: prove redaction cannot affect dedup/pattern-check behavior.
- Deliverables: tests asserting identical-except-for-PII prompts still produce different hashes and are never flagged as duplicates of each other; existing PRD-001 test suite passes unmodified.
- Validation: full existing test suite green + new redaction-specific tests green.

**Phase 4 — Docs & Rollout** (~1 day)
- Goal: document the feature and flip the roadmap checkbox.
- Deliverables: README updates (Features table, Environment Variables, Roadmap), `.env.example` additions.
- Validation: README accurately reflects new env vars and behavior; roadmap item "PII redaction on input/output" marked done.

## 13. Future Considerations

Explicitly deferred post-MVP:
- Spanish/LATAM-specific recognizers (DNI, CUIT/CUIL, AR phone formats) and the corresponding `es_core_news_lg` model
- Reversible de-anonymization with an encrypted mapping store, for legitimate internal "unmask" use cases
- Latency optimization for the NER inference path (async analysis, distilled/smaller model, batching)
- Encryption at rest for audit log PII-bearing columns
- RBAC-gated access to `/audit` (tracked in PRD-001's roadmap; this feature raises its priority but doesn't implement it)
- Chat UI surfacing of redaction (e.g., a visible "N fields masked" indicator, similar to the existing blocked-message bubble pattern)

## 14. Risks & Mitigations

1. **Risk**: Spanish/LATAM PII (DNI, CUIT/CUIL, local phone formats) goes undetected because the MVP is English-only.
   **Mitigation**: Explicit, documented non-goal for this PRD; tracked as a follow-up PRD rather than silently unaddressed.

2. **Risk**: Presidio's NER inference adds latency to every request, on top of the existing duplicate/pattern/OpenRouter pipeline.
   **Mitigation**: Load the NLP model once at startup (non-negotiable minimum). Per-request inference cost is accepted for the MVP; optimization (async, smaller model) is tracked as future work, not solved here.

3. **Risk**: Recall-biased thresholding produces false positives, over-masking legitimate text in the model's response.
   **Mitigation**: Accepted by design — since redaction never blocks, an over-masked response only degrades text quality, never denies service. Business preference is explicitly recall over precision.

4. **Risk**: The audit log becomes a more clearly identified, concentrated repository of raw PII, protected only by a single shared `ADMIN_TOKEN` with no RBAC.
   **Mitigation**: Documented as an accepted residual risk for this MVP. Encryption at rest and RBAC are tracked as future work (Section 13), not resolved by this PRD.

5. **Risk**: `presidio-analyzer`/`spacy`/`en_core_web_lg` meaningfully increase Docker image size and container memory footprint versus PRD-001's lightweight profile.
   **Mitigation**: Accepted as the known cost of the feature; documented in README requirements so deployers aren't surprised by image size/build time changes.

## 15. Appendix

**Related docs**
- [README.md](../../../README.md) — Roadmap item "PII redaction on input/output" this PRD implements
- [PRD-001 — Harness IA MVP](../PRD-001-harness-ia/PRD.md) — base pipeline this feature extends (duplicate check, pattern check, audit logging)

**Skills referenced**: None — `.agents/skills/` does not exist in this repository.

**Dependencies**
- `presidio-analyzer`, `presidio-anonymizer` (MIT-licensed, compatible with this project's MIT license)
- `spacy` + `en_core_web_lg` model download
- No new external service dependency — runs in-process, same as the rest of the pipeline
