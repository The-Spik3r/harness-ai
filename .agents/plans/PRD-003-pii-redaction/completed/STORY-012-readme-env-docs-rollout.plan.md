---
story: STORY-012
prd: PRD-003
slug: readme-env-docs-rollout
title: "README, .env.example, and roadmap updates for PII redaction"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-003-pii-redaction        # all stories commit here, no per-story branch
created: 2026-08-02
---

# Plan: README, `.env.example`, and roadmap updates for PII redaction

## Summary

PRD-003 shipped across STORY-001…STORY-011, but `README.md` and `.env.example` still describe the pre-PRD-003 system: the pipeline is documented as `duplicate check → pattern check → forward to OpenRouter → audit log` (README.md:53), the Features table has no redaction row, the Environment Variables table lists six vars and none of the four `PII_*` ones, the `POST /query`/`GET /audit`/`GET /stats` examples omit every field STORY-007 and STORY-009 added, and the roadmap still shows `- [ ] PII redaction on input/output`. This story closes that gap — **documentation only, zero source changes** — by editing exactly two files. Its distinguishing constraint is that every documented value must be copied from the *shipped* code, not from the PRD's pre-implementation draft: the PRD's `GET /audit` example (PRD.md:207-217) shows a `prompt_preview` field that `AuditQueryEntry` has never exposed, and PRD §10's `/stats` example omits fields the endpoint actually returns. Task 9 is a mechanical cross-check of every documented value against `app/config.py`, `app/models/schemas.py` and `app/routers/admin.py` for exactly this reason. The plan also carries the four follow-ups STORY-011's report explicitly handed to this story (image-size figures, `en_core_web_lg`-only baking, the changed missing-model failure mode, and the build-time network requirement).

## User Story

As an integrating developer or devops engineer evaluating this project
I want `README.md` and `.env.example` to accurately document PII redaction, its env vars, its response fields, and its deployment cost
So that the documented behavior matches what is actually shipped and the roadmap reflects a delivered feature

## Story Reference

- Story file: `.agents/stories/PRD-003-pii-redaction/STORY-012-readme-env-docs-rollout.md`
- PRD: `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — §12 (Phase 4 — Docs & Rollout), §9 (Environment variables), §10 (API Specification), Risk 5

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (documentation) |
| Complexity | LOW |
| Systems Affected | `README.md`, `.env.example` — no application code, no tests |
| Story | STORY-012 |
| PRD | PRD-003 |
| Epic Branch | `epic/PRD-003-pii-redaction` (commit directly on this branch) |

---

## Skills In Use

None — `.agents/skills/` does not exist in this repository (confirmed via `ls`: `NO .agents/skills`; story frontmatter `skills: []`). The same finding is recorded in the [[STORY-001]], [[STORY-002]] and [[STORY-011]] plans.

`chat_ui/AGENTS.md` mandates the Reflex skills (`reflex-docs`, `setup-python-env`, `reflex-process-management`) **before writing or editing any Reflex code**. This story edits no Reflex code — `chat_ui/` is not touched — so that gate does not apply. If a task is ever expanded to touch `chat_ui/`, load `reflex-docs` first.

---

## Dependency Check

| Dependency | Status | Evidence |
|---|---|---|
| STORY-010 (E2E integration tests) | ✅ done | commit `306b5cc`, report present |
| STORY-011 (Docker spaCy model) | ✅ done | commit `2457952`, report present |

Both satisfied — no blockers. This is the last story of PRD-003 (`blocks: []`); after it, all 12 stories are `done`.

---

## Patterns to Follow

### `.env.example` — one comment line above each var, no blank-line-free runs

```bash
# SOURCE: .env.example:1-17
# OpenRouter API key used to call the upstream LLM provider (required)
OPENROUTER_API_KEY=your-openrouter-key-here

# SQLite connection string for the audit_logs database
DATABASE_URL=sqlite:///harness_ai.db

# Log verbosity (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

Every var: a single `#` sentence-case comment line, then `VAR=value`, then one blank line. Required vars end their comment with `(required)`. Comment text is reused verbatim as the README table's Description column. The four new vars follow this exactly.

### README Environment Variables — 4-column table, backticked defaults, `—` for none

```markdown
// SOURCE: README.md:182-189
| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | API key used to call the upstream LLM provider via OpenRouter. |
| `LOG_LEVEL` | No | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
```

Descriptions are full sentences ending in a period; defaults are backticked; missing defaults are an em dash.

### README Features — capability in bold, one-sentence description

```markdown
// SOURCE: README.md:108-110
| **Duplicate blocking** | Exact-match (word-for-word) detection of repeated prompts within a rolling 24-hour window. |
| **Prompt-injection blocking** | Case-insensitive substring match against a maintained pattern list. |
| **Full audit logging** | Every request — success or blocked — writes one row to SQLite: ... IP addresses and geolocation are never captured. |
```

Note the house style for stating a deliberate limit inside the description (`IP addresses and geolocation are never captured.`) — the redaction row uses the same device for "masks, never blocks" and "English-only".

### README API Reference — `curl` block, then the JSON response it returns

```markdown
// SOURCE: README.md:197-213
### `POST /query` — success

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "juan@empresa.com", "prompt": "what is the weather today"}'
```

```json
{
  "status": "SUCCESS",
  "response": "La respuesta del modelo",
  "audit_id": 1,
  "model_used": "gpt-4",
  "tokens_used": 45
}
```
```

Bare ```` ```json ```` fences, two-space indent, no trailing commentary inside the block; prose clarifications go after the fence (see README.md:237, 283).

### README Troubleshooting — bold error string, then the one-line fix

```markdown
// SOURCE: README.md:305-315
**`ModuleNotFoundError: No module named 'fastapi'`**
Run `pip install -r requirements.txt`.

**`401 Unauthorized` on `/audit` or `/stats`**
Confirm the `Authorization: Bearer <token>` header matches `ADMIN_TOKEN` in `.env` exactly.
```

Error text bold on its own line, remedy on the next line, no bullet.

### Shipped values these docs must mirror (not the PRD draft)

```python
# SOURCE: app/config.py:15-18
PII_REDACTION_ENABLED: bool = True
PII_SCORE_THRESHOLD: float = 0.35
PII_ENTITIES: str = "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION"
PII_NLP_MODEL: str = "en_core_web_lg"
```

```python
# SOURCE: app/models/schemas.py:14-21, 41-52, 60-69
class QuerySuccessResponse(BaseModel):      # blocked responses gain NO pii fields
    ...
    pii_redacted: bool = False
    pii_entities_masked: List[str] = []

class AuditQueryEntry(BaseModel):           # note: no prompt_preview, by design
    ...
    pii_detected_input: bool = False
    pii_detected_output: bool = False
    pii_entities: List[str] = []

class StatsResponse(BaseModel):
    ...
    pii_detected_queries: int = 0
    top_pii_entities: List[str] = []
```

```python
# SOURCE: tests/test_pii_redaction_integration.py:28-38 — measured against the shipped model
_PII_PROMPT     = "my name is Maria Gomez, my email is juan@empresa.com and my phone is 555-123-4567"
_REDACTED_PROMPT= "my name is <PERSON>, my email is <EMAIL_ADDRESS> and my phone is <PHONE_NUMBER>"
_EXPECTED_ENTITIES = ["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"]
```

These strings were measured against `en_core_web_lg` at `PII_SCORE_THRESHOLD=0.35` by STORY-010 — reuse them in the README examples rather than inventing new ones, so the documented output is provably what the system produces.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | Features row, Requirements, both Quickstarts, Chat UI note, Environment Variables (4 rows), API Reference (3 examples), Running Tests note, Troubleshooting (2 entries), Roadmap checkbox |
| `.env.example` | UPDATE | Four `PII_*` vars in the existing comment style |
| `app/**`, `chat_ui/**`, `tests/**`, `Dockerfile`, `docker-compose.yml` | NO CHANGE | Story is explicitly doc-only ("no source code changes") |
| `.github/workflows/ci.yml` | NO CHANGE (finding recorded) | See Design Note 6 — a real gap, but out of scope for a doc-only story |

---

## Design Notes (decisions worth stating up front)

1. **Document the shipped shape, not PRD §10.** PRD.md:207-217 shows `GET /audit` returning `prompt_preview`. `AuditQueryEntry` (`app/models/schemas.py:41-52`) has never carried it, and `tests/test_audit_router.py::test_response_never_includes_ip_or_raw_text` actively asserts its absence — STORY-009's report records this as a deliberate scope decision. The README's `/audit` example therefore adds only the three telemetry fields to the *existing* documented entry shape. Same discipline for `/stats`: PRD §10 lists only the two new fields, while the endpoint returns all eight — the README keeps its full existing example and appends two rows. The story's own Technical Notes ("document the actual shipped shape of every field, not the PRD's pre-implementation draft") is the governing instruction whenever PRD and code disagree.

2. **`pii_redacted` / `pii_entities_masked` appear on the success response only.** `QueryBlockedDuplicateResponse` and `QueryBlockedSuspiciousResponse` (`app/models/schemas.py:24-33`) have no PII fields, and redaction runs *after* both block checks (`app/services/query_pipeline.py:27-57`) so a blocked prompt is never analyzed. The two blocked examples (README.md:215-235) stay byte-identical — Task 5 must not touch them — and one sentence of prose states why.

3. **The pipeline one-liner and the ASCII architecture diagram are in scope even though no AC names them.** README.md:53 and README.md:71-96 assert a four-step pipeline that is now six steps; leaving them is a documented falsehood in the two places a reader looks first, and the PRD's Phase 4 validation criterion is "README accurately reflects new env vars **and behavior**". The edit is additive and small (Task 3). If a reviewer objects to scope, drop Task 3 alone — every AC still passes without it.

4. **Image size is quoted from `docker image inspect`, with the measurement method named.** STORY-011's report measured 131 MB (pre-PRD-003) → 628 MB (post), and explicitly warns that this containerd-backed Docker Desktop's `docker images` SIZE column reports 484 MB / 1.78 GB for the same images. Quoting one method and naming it is the only honest option; quoting a bare number invites a "the README is wrong" bug report from anyone using the other command.

5. **The local Quickstart genuinely needs a new step, not just a note.** `requirements.txt` installs `spacy` but not `en_core_web_lg` (the model ships separately). The current Quickstart — `pip install -r requirements.txt` → `python app.py` — now fails at startup on a clean machine with `PiiRedactorError: Failed to load Presidio NLP model 'en_core_web_lg'` (`app/services/pii_redactor.py:26`), because `load()` runs in `lifespan` (`app/main.py:14`) and, under Reflex, as a registered lifespan task (`chat_ui/chat_ui/chat_ui.py:46`). So `python -m spacy download en_core_web_lg` is a required Quickstart line, not a footnote. Docker needs no such line — STORY-011 baked it into the image.

6. **CI gap found during exploration — recorded, not fixed here.** `.github/workflows/ci.yml:21-25` runs `pip install -r requirements.txt` then `pytest -q`, with no `spacy download` step. `tests/test_pii_redactor.py` and `tests/test_pii_redaction_integration.py` exercise the real analyzer with no skip guard (`grep` for `skip` in `test_pii_redactor.py` returns nothing), so CI on this epic branch would fail on a clean GitHub runner. That is a workflow fix, not a documentation fix, and this story is explicitly doc-only. The README's Running Tests section will state the model prerequisite (Task 8); the workflow fix is raised as a follow-up in the report and in the Risks table below. Do **not** silently edit `ci.yml` as part of this story.

7. **Nothing in the Chat UI section changes behaviorally, but its pipeline sentence is now incomplete.** README.md:166 enumerates the pipeline the chat shares with `POST /query`; redaction is part of that shared path, and PRD §13 lists "Chat UI surfacing of redaction" as explicitly deferred. One clause added to that sentence plus one bullet under "Known limitations (MVP)" keeps the section true without implying a UI feature exists.

8. **Table of Contents needs no change.** All edits land inside existing `##` sections; no section is added or renamed, so README.md:19-34 stays as-is. Task 9 verifies this rather than assuming it.

---

## Tasks

Execute in order. Each task is atomic + verifiable. Every task edits `README.md` unless stated otherwise; none touches application code.

### Task 1: Add the PII redaction row to the Features table

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Insert one row after the **Prompt-injection blocking** row (README.md:109), before **Full audit logging** — placing it in pipeline order. It must state all three facts AC1 requires (Presidio-backed, mask-not-block, English-only):
  ```markdown
  | **PII redaction** | [Microsoft Presidio](https://microsoft.github.io/presidio/) masks personal data (names, emails, phone numbers, cards, SSNs, IBANs, locations) in the outbound prompt before it reaches OpenRouter, and in the model's response before it reaches the caller. Masking never blocks a request, and the audit log keeps the raw text. English-only in this release. |
  ```
- **Mirror**: `README.md:108-110` — bold capability, single-sentence-style description, deliberate limits stated inline (as `IP addresses and geolocation are never captured.` does).
- **Validate**: `grep -n "PII redaction" README.md` shows the row inside the Features table (between lines ~109 and ~111); the table renders with 2 columns on every row.

### Task 2: Update the Solution intro line

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Replace the pipeline one-liner at README.md:52-54 so it shows the two new stages:
  ```
  duplicate check (24h)  →  prompt-injection check  →  PII redaction (prompt)  →  forward to OpenRouter  →  PII redaction (response)  →  audit log
  ```
  Leave the following sentence ("If either check fails…", README.md:56) intact but extend it with one clause making clear redaction is not a third block: `Redaction, by contrast, never rejects anything — it only masks.`
- **Mirror**: `README.md:52-56` — same fenced plain block, same arrow spacing.
- **Validate**: `sed -n '48,58p' README.md` reads correctly and no longer claims a two-check-only pipeline.

### Task 3: Update the ASCII architecture diagram

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: In the Harness IA box (README.md:71-80), add steps 5 and 6 after `4. Pattern check`:
  ```
  │  5. PII redaction     │
  │     (outbound prompt) │
  ```
  and add a redaction stage between the OpenRouter box and the audit-log box:
  ```
  ┌───────────────────────┐
  │  PII redaction        │
  │  (model response)     │
  └───────────┬───────────┘
  ```
  Keep the existing box-drawing characters and column width exactly (23 chars inside the borders). Then extend the sentence at README.md:98 with: `Redaction sits after both checks, so a blocked request is never analyzed for PII.`
- **Mirror**: `README.md:62-98` — identical glyphs (`┌ ─ ┐ │ └ ┘ ▼ ◄`) and alignment; and `PRD.md:89-107`, which is the authoritative 10-step pipeline this diagram is a simplification of.
- **Validate**: View the block in a fixed-width renderer (or `sed -n '60,100p' README.md`) — every border column aligns; no line exceeds the original block width.

### Task 4: Requirements + both Quickstarts — spaCy model step and image-size note

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Three edits (AC6):
  1. **Requirements** (README.md:117-121) — add two bullets:
     ```markdown
     - ~500 MB of disk for the English spaCy NLP model (`en_core_web_lg`) used by PII redaction
     - Network access at install/build time to download that model
     ```
  2. **Quickstart — Local** (README.md:127-132) — add the download line after `pip install`:
     ```bash
     pip install -r requirements.txt
     python -m spacy download en_core_web_lg   # English NLP model used by PII redaction (~425 MB)
     cp .env.example .env
     ```
     Follow the block with one sentence: `The model is a separate download — \`requirements.txt\` installs Presidio and spaCy but not the model itself. Skipping this step makes the service fail at startup with \`PiiRedactorError\`. To run without it, set \`PII_REDACTION_ENABLED=false\` in \`.env\`.`
  3. **Quickstart — Docker** (README.md:139-152) — add after the existing persistence sentence:
     `The image bakes \`en_core_web_lg\` in at build time, so no model download happens at container start. This makes the image substantially larger: measured with \`docker image inspect\`, the pre-PII image was 131 MB and the current one is 628 MB (of which ~446 MB is the model layer), and the first build spends ~40 s downloading it. Accepted tradeoff — see PRD-003 Risk 5. (\`docker images\` reports larger figures for the same images on containerd-backed installs; the numbers above use \`docker image inspect\`.)`
- **Mirror**: `README.md:117-152` — bullet style in Requirements, fenced `bash` blocks with a trailing prose sentence in the Quickstarts; figures taken verbatim from `.agents/reports/PRD-003-pii-redaction/STORY-011-docker-image-spacy-model.report.md:79-91`.
- **Validate**: On a machine without the model, following Quickstart — Local verbatim yields a service that starts (Task 10 E2E). `grep -n "en_core_web_lg" README.md` shows hits in Requirements, Quickstart — Local, Quickstart — Docker, Environment Variables, and Troubleshooting.

### Task 5: Chat UI section — redaction applies, no UI indicator

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: In README.md:166, extend the parenthesised pipeline to `(duplicate check → pattern check → PII redaction → OpenRouter call → audit log)`. Then add a bullet to **Known limitations (MVP)** (README.md:172-176):
  ```markdown
  - No visible indicator when PII is masked — redaction still applies to every chat message, but the UI does not yet surface *that* it happened (the REST API does, via `pii_redacted`).
  ```
- **Mirror**: `README.md:172-176` — existing limitation bullets, each one line, "No X — Y" shape.
- **Validate**: `sed -n '156,178p' README.md`; the claim is consistent with `chat_ui/chat_ui/state.py` (no PII field is read there) and with PRD §13's deferred "Chat UI surfacing of redaction".

### Task 6: Environment Variables — four `PII_*` rows

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Append four rows to the table (after `LOG_LEVEL`, README.md:189), values copied from `app/config.py:15-18` (AC2):
  ```markdown
  | `PII_REDACTION_ENABLED` | No | `true` | Master switch for PII redaction on prompts and responses. Set to `false` to skip all NLP work (and the model download requirement). |
  | `PII_SCORE_THRESHOLD` | No | `0.35` | Minimum Presidio confidence for an entity to be masked. Deliberately low — the project favors over-masking over missing real PII. |
  | `PII_ENTITIES` | No | `PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION` | Comma-separated list of Presidio entity types to detect and mask. |
  | `PII_NLP_MODEL` | No | `en_core_web_lg` | spaCy model backing Presidio's analyzer. Only this model is installed by the Dockerfile and the Quickstart — pointing at another one (e.g. `en_core_web_trf`) requires installing it yourself, or startup fails. |
  ```
  Then add one sentence below the table, before the `.env.example` link (README.md:191): `All four PII settings are read once at startup (\`app/config.py\`); changing them requires a restart.`
- **Mirror**: `README.md:182-189` — 4-column layout, backticked defaults, full-sentence descriptions.
- **Validate**: Every default in the table matches `app/config.py:15-18` character-for-character (Task 9 automates this).

### Task 7: API Reference — three response examples

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Three edits (AC3), using STORY-010's measured strings so the examples are provably real:
  1. **`POST /query` — success** (README.md:197-213): change the request `prompt` to a PII-bearing one and show the masked result:
     ```bash
     curl -X POST http://localhost:8000/query \
       -H "Content-Type: application/json" \
       -d '{"user_id": "analyst-7", "prompt": "my name is Maria Gomez, my email is juan@empresa.com"}'
     ```
     ```json
     {
       "status": "SUCCESS",
       "response": "Sure — I will reply to <EMAIL_ADDRESS> for <PERSON>.",
       "audit_id": 1,
       "model_used": "gpt-4",
       "tokens_used": 45,
       "pii_redacted": true,
       "pii_entities_masked": ["EMAIL_ADDRESS", "PERSON"]
     }
     ```
     Follow the fence with: `OpenRouter received \`my name is <PERSON>, my email is <EMAIL_ADDRESS>\` — never the raw text. \`pii_entities_masked\` is the sorted union of entity types masked in the prompt and in the response; when nothing is detected, \`pii_redacted\` is \`false\` and the list is empty. Both fields are additive — clients that ignore unknown fields are unaffected, and the two \`BLOCKED\` shapes below are unchanged (redaction runs only after both checks pass).`
  2. **`GET /audit`** (README.md:246-262): add three keys to the single example entry, after `"device"`:
     ```json
     "pii_detected_input": true,
     "pii_detected_output": false,
     "pii_entities": ["EMAIL_ADDRESS", "PERSON"]
     ```
     Follow with: `\`pii_entities\` is the union of types masked in either direction. The audit trail deliberately stores the **raw, unmasked** prompt and response previews in the database — an auditor investigating an incident needs the actual value, not \`<EMAIL_ADDRESS>\` — but this endpoint exposes neither the raw previews nor the masked text, only the flags above.`
  3. **`GET /stats`** (README.md:271-281): add two keys after `"top_users"`:
     ```json
     "pii_detected_queries": 34,
     "top_pii_entities": ["EMAIL_ADDRESS", "PERSON"]
     ```
     Follow with: `\`pii_detected_queries\` counts audit rows flagged on input **or** output; \`top_pii_entities\` ranks individual entity types by frequency across rows.`
  **Do not touch** the two `BLOCKED` examples (README.md:215-235) — Design Note 2.
- **Mirror**: `README.md:197-283` for structure; `app/models/schemas.py:14-21,41-52,60-69` for field names/types; `app/routers/admin.py:26-67` for what `/audit` and `/stats` actually emit; `tests/test_pii_redaction_integration.py:28-38` for the masked strings; STORY-009's report (§Summary) for `top_pii_entities` semantics.
- **Validate**: Every key in each JSON example exists in the corresponding Pydantic model, and no model field documented elsewhere is contradicted (Task 9).

### Task 8: Running Tests + Troubleshooting notes

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Two edits:
  1. **Running Tests** (README.md:287-299): add one sentence before the local `pytest` block — `The PII tests load the real \`en_core_web_lg\` model, so run the \`spacy download\` step from Quickstart — Local first; the in-container run needs nothing extra (the image already has it).`
  2. **Troubleshooting** (README.md:303-315): add two entries in the existing style, before the `401` entry:
     ```markdown
     **`PiiRedactorError: Failed to load Presidio NLP model 'en_core_web_lg'` at startup**
     Run `python -m spacy download en_core_web_lg`. Since the model is loaded at startup, a missing or misnamed model fails the boot rather than the first request. To run without redaction entirely, set `PII_REDACTION_ENABLED=false`.

     **Model responses contain `<PERSON>` or `<EMAIL_ADDRESS>` where you expected real text**
     That is PII redaction working as designed — the threshold (`PII_SCORE_THRESHOLD`, default `0.35`) deliberately favors over-masking. Raise it, or trim `PII_ENTITIES`, if a specific entity type is too aggressive for your use case.
     ```
- **Mirror**: `README.md:305-315` — bold error line, plain remedy line, blank line between entries. Content of the first entry comes from STORY-011's report §Follow-ups for STORY-012.
- **Validate**: `sed -n '287,325p' README.md`; the error string matches `app/services/pii_redactor.py:26`'s message format exactly.

### Task 9: Roadmap checkbox

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: At README.md:326, change `- [ ] PII redaction on input/output` to `- [x] PII redaction on input/output` (AC4). Leave its position in the list unchanged — the list is not sorted by status (README.md:321-328 already interleaves). Do not touch the other three unchecked items.
- **Mirror**: `README.md:321-324` — checked items use `- [x]` with no annotation.
- **Validate**: `grep -n "PII redaction on input/output" README.md` → exactly one hit, `- [x]`.

### Task 10: `.env.example` — four `PII_*` vars

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Append after `LOG_LEVEL` (`.env.example:17`), matching the file's comment style exactly — one comment line, the var, one blank line (AC5):
  ```bash
  # Master switch for PII redaction on prompts and responses (true/false)
  PII_REDACTION_ENABLED=true

  # Minimum Presidio confidence to mask an entity - low by design, favors over-masking
  PII_SCORE_THRESHOLD=0.35

  # Comma-separated Presidio entity types to detect and mask
  PII_ENTITIES=PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION

  # spaCy model backing Presidio's analyzer (install with: python -m spacy download en_core_web_lg)
  PII_NLP_MODEL=en_core_web_lg
  ```
  Values are the code defaults, so copying `.env.example` to `.env` changes nothing about behavior. Do not add quotes (no existing var is quoted) and do not use `-` bullets in comments.
- **Mirror**: `.env.example:1-17` — the comment/var/blank-line rhythm and sentence-case wording.
- **Validate**: `python -c "from app.config import Settings; s = Settings(_env_file='.env.example'); print(s.PII_REDACTION_ENABLED, s.PII_SCORE_THRESHOLD, s.PII_NLP_MODEL, s.pii_entities_list)"` parses without error and prints values identical to `app/config.py:15-18`'s defaults.

### Task 11: Cross-check every documented value against the code

- **File**: none — verification only
- **Action**: VERIFY
- **Implement**: Mechanical audit of what Tasks 1-10 wrote. For each item, the README statement must match the named source:
  | Documented item | Source of truth |
  |---|---|
  | 4 env var names + defaults | `app/config.py:15-18` |
  | `pii_redacted`, `pii_entities_masked` on success only | `app/models/schemas.py:14-33` |
  | `/audit` entry keys (and absence of `prompt_preview`) | `app/models/schemas.py:41-52`, `app/routers/admin.py:26-44` |
  | `/stats` keys | `app/models/schemas.py:60-69`, `app/routers/admin.py:52-67` |
  | Masked placeholder format `<ENTITY_TYPE>` | `tests/test_pii_redaction_integration.py:28-38` |
  | Redaction runs after both block checks | `app/services/query_pipeline.py:27-57` |
  | Model baked into image, model-only-`en_core_web_lg` caveat | `Dockerfile:44-51` |
  | Image-size figures + measurement method | STORY-011 report:79-91 |
  | Startup load (both entry points) | `app/main.py:11-15`, `chat_ui/chat_ui/chat_ui.py:41-46` |
  Also confirm: the Table of Contents (README.md:19-34) still matches every `##` heading (no section added/renamed — Design Note 8); no internal anchor link broke; and `git diff --stat` lists **exactly two files**, `README.md` and `.env.example`.
- **Mirror**: STORY-009's report §Scope Decision — the precedent for choosing shipped shape over PRD text and saying so out loud.
- **Validate**: `git diff --stat` → 2 files, 0 under `app/`, `tests/`, `chat_ui/`. `python -m pytest -q` → 202 passed, byte-identical to the pre-story baseline (a doc-only change cannot move it).

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `git diff --stat` → exactly `README.md` + `.env.example`; no application, test, Docker, or CI file modified (story is doc-only)
- [ ] `python -m pytest -q` → 202 passed, unchanged from the STORY-011 baseline
- [ ] `python -c "from app.config import Settings; s=Settings(_env_file='.env.example'); print(s.PII_REDACTION_ENABLED, s.PII_SCORE_THRESHOLD, s.PII_NLP_MODEL, s.pii_entities_list)"` → `True 0.35 en_core_web_lg ['PERSON', 'EMAIL_ADDRESS', 'PHONE_NUMBER', 'CREDIT_CARD', 'US_SSN', 'IBAN_CODE', 'LOCATION']`, i.e. identical to `app/config.py`'s defaults
- [ ] Follow **Quickstart — Local** verbatim in a scratch venv without the model → service starts and `curl http://localhost:8000/health` returns `{"status":"ok"}` (proves Task 4's added step is sufficient and correctly ordered)
- [ ] In that same venv, *skip* the `spacy download` line → startup fails with `PiiRedactorError: Failed to load Presidio NLP model 'en_core_web_lg'`, matching the new Troubleshooting entry verbatim
- [ ] Run the documented `POST /query` success example against a live server (`call_openrouter` stubbed, or a real key if available) → response JSON has the same key set as the README example, `pii_redacted: true`, and `pii_entities_masked` sorted
- [ ] `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/audit` → key set of each entry matches the README example exactly (including no `prompt_preview`)
- [ ] `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/stats` → key set matches the README example exactly
- [ ] `grep -c "PII" README.md` > 0 in each of: Features, Requirements, Quickstart — Local, Quickstart — Docker, Chat UI, Environment Variables, API Reference, Running Tests, Troubleshooting, Roadmap
- [ ] `grep -n "PII redaction on input/output" README.md` → `- [x]`, exactly one hit
- [ ] Render `README.md` (GitHub preview or any Markdown viewer) → all tables have consistent column counts, all fences close, the ASCII diagram aligns, and the Table of Contents links all resolve

---

## Validation

```bash
cd f:\AI\harness-ai

git diff --stat
python -m pytest -q

python -c "from app.config import Settings; s=Settings(_env_file='.env.example'); print(s.PII_REDACTION_ENABLED, s.PII_SCORE_THRESHOLD, s.PII_NLP_MODEL, s.pii_entities_list)"

grep -n "en_core_web_lg" README.md
grep -n "PII redaction on input/output" README.md
grep -n "pii_redacted\|pii_entities_masked\|pii_detected_input\|pii_detected_output\|pii_entities\|pii_detected_queries\|top_pii_entities" README.md

python app.py &
curl http://localhost:8000/health
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/audit
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/stats
```

---

## Risks

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Docs drift from code again — a documented default silently diverges from `app/config.py` | Task 11 is a line-by-line cross-check with named sources, and Task 10's validation *parses* `.env.example` through the real `Settings` class rather than eyeballing it |
| 2 | The README's `/audit` example is copied from PRD §10 and gains a `prompt_preview` field the endpoint does not return | Design Note 1 + Task 7's explicit "add three keys to the existing entry" instruction; Task 11 checks the key set against `AuditQueryEntry` |
| 3 | Scope creep — a "docs" story quietly edits code, or fixes the CI gap from Design Note 6 | Task 11's `git diff --stat` gate: exactly two files. The CI gap is written up as a follow-up story recommendation in the report, not fixed here |
| 4 | Image-size figures become stale, or a reader's `docker images` disagrees with the README | Quote one measurement method and name it (Design Note 4); the sentence attributes the numbers to a specific build rather than promising them |
| 5 | The ASCII diagram (Task 3) breaks alignment in fixed-width rendering | Preserve the existing 23-char interior width and glyph set exactly; the render check in E2E covers it. Task 3 is independently droppable if it proves fiddly (Design Note 3) |
| 6 | Documented example output (`<PERSON>`, `<EMAIL_ADDRESS>`) does not match what the model actually produces on a reader's machine | Examples reuse STORY-010's strings, which were measured against the shipped `en_core_web_lg` at threshold `0.35`; the surrounding prose frames redaction as probabilistic and recall-biased rather than promising exact output |
| 7 | This is PRD-003's last story — anything undocumented here has no later story to catch it | The four follow-ups STORY-011's report handed forward are each mapped to a task (image size → Task 4; `en_core_web_lg`-only → Task 6; changed failure mode → Task 8; build-time network → Task 4) |

---

## Acceptance Criteria

(Copied from story STORY-012)

- [ ] Given `README.md`'s Features table (around README.md:102), when read, then it lists PII redaction on input/output, mentioning it's English-only, mask-not-block, and Presidio-backed. — Task 1
- [ ] Given `README.md`'s Environment Variables section (around README.md:180), when read, then it documents `PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `PII_ENTITIES`, `PII_NLP_MODEL` with the same defaults as [[STORY-001]]'s implementation. — Task 6
- [ ] Given `README.md`'s API Reference section (around README.md:195), when read, then the `POST /query` response example includes `pii_redacted`/`pii_entities_masked`, and `GET /audit`/`GET /stats` examples include the new PII telemetry fields from [[STORY-009]]. — Task 7
- [ ] Given `README.md`'s Roadmap section (README.md:326), when read, then `- [ ] PII redaction on input/output` is changed to `- [x] PII redaction on input/output`. — Task 9
- [ ] Given `.env.example`, when read, then it includes the four new `PII_*` vars with a short comment each, matching the existing file's comment style. — Task 10
- [ ] Given `README.md`'s Requirements/Quickstart sections, when read, then they note the added spaCy model download step and the image-size/build-time impact from [[STORY-011]] (PRD Risk 5). — Task 4
- [ ] All tasks completed
- [ ] No source code changed — `git diff --stat` shows only `README.md` and `.env.example`
- [ ] Full test suite still passes unchanged (202 passed)
- [ ] Follows existing patterns (`.env.example` comment rhythm, README table/fence/troubleshooting styles)
