---
story: STORY-022
prd: PRD-008
slug: readme-and-env-docs
title: "README and .env: document the persistence model the code actually has, including what is now at rest"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-07
---

# Plan: README and .env — document the persistence model the code actually has

## Summary

PRD-008 changed the product's data-at-rest posture and the README still describes the release before
it. Exploration of the merged code found the damage is wider than the two ACs about the environment
table: the Chat UI section states **"No persisted chat history"** as a limitation (`README.md:218`),
the persistence section says **"Both tables the harness owns — `audit_logs` and `users`"** (`:228`)
when `init_db()` now creates four, the architecture diagram names only `audit_logs` and `users` as
stores (`:79`, `:100`), and the Roadmap's Shipped list stops at RBAC (`:525`). This plan edits
`README.md` in place — no new top-level section, so the Table of Contents is untouched — and
verifies `.env.example` rather than changing it, because it already matches `app/config.py` exactly.

Three things this plan does that the ACs do not literally ask for, each because the story's governing
rule is **"describe the code that exists, not the PRD's intentions"**:

1. **`README.md:240` is now false.** It says two-instance operation has no end-to-end proof and is
   "still outstanding work, not a completed test." STORY-021 — a dependency of this story — shipped
   `tests/test_two_instance_smoke.py`, which runs two processes against one database and asserts they
   serve the same session. Leaving that sentence in place would be the same defect this story exists
   to correct, one section higher.
2. **`README.md:220` is stale from a different epic.** It says there is "no visible indicator when
   PII is masked"; PRD-004 STORY-009 shipped the badge (`chat_ui/chat_ui/copy.py`'s
   `PII_BADGE_TEMPLATE`, `tests/test_pii_badge.py`). It sits inside the Known-limitations list this
   story rewrites, so it is corrected in the same pass and recorded as a divergence in the report.
3. **`tests/test_two_instance_smoke.py:462` cites `README.md:456` by line number.** Every edit below
   is above that line, so the citation goes stale on commit. Task 9 reconciles it. This is the only
   file outside `README.md` this plan touches, and it changes a comment, not an assertion.

The plan also records one behaviour the PRD does **not** describe and the code does, which AC 7
("the session rail as it actually behaves") makes load-bearing: **the first user bubble of a brand-new
chat is never persisted.** `ChatState._do_send` appends and persists the user bubble *before* it
lazily creates the session (`chat_ui/chat_ui/state.py:979-1006`), so at that moment `session_id` is
`""` and `_append_and_persist`'s guard skips the write. The code names the consequence itself: "a
restored first turn starts at the assistant bubble." A README that promised a faithful transcript
would be wrong on the first turn of every conversation.

## User Story

As an integrating developer and as a security admin
I want the README to describe what this release stores and what the switch does
So that the largest change in the product's data posture is discoverable without reading a PRD

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-022-readme-and-env-docs.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 9 (security & configuration, the at-rest
  widening), Section 10 (API specification), Section 11 (success criteria), Section 12 Phase 4,
  Section 13 (multi-turn, and why it is deferred)
- Precedent this plan follows:
  `.agents/plans/PRD-007-turso-migration/completed/STORY-015-readme-and-deployment-docs.plan.md` —
  the same "read the merged implementation, document that, put divergences in the report" bar

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (documentation correctness) |
| Complexity | MEDIUM (the story says small; ten ACs, nine distinct README edits, one stale cross-file line citation) |
| Systems Affected | `README.md`. Verification only on `.env.example`. One comment in `tests/test_two_instance_smoke.py`. **No change to `app/`, `chat_ui/`, `scripts/`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`.** |
| Story | STORY-022 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed and read in full: it holds exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" — aesthetic direction, typography, layout. This story edits Markdown and renders no UI. The story frontmatter carries `skills: []` and its Technical Notes reach the same conclusion explicitly. | none |

No skill's `allowed-tools` or workflow constraint gates any task below.

---

## Patterns to Follow

### The environment table is a real four-column table — extend it in `Settings` field order

```markdown
// SOURCE: README.md:270-287
| Variable | Required | Default | Description |
|---|---|---|---|
| `PII_REDACTION_ENABLED` | No | `true` | Master switch for PII redaction on prompts and responses. Set to `false` to skip all NLP work (and the model download requirement). |
```

The table's row order mirrors `app/config.py`'s field declaration order, and
`tests/test_config.py::test_env_example_chat_vars_appear_in_settings_field_order` pins the same
ordering rule for `.env.example`. `CHAT_HISTORY_ENABLED` and `CHAT_SESSION_LIMIT` are declared last in
`Settings`, so they go last in the table — after `PII_NLP_MODEL`.

### A README claim about behaviour names the file that produces it

```markdown
// SOURCE: README.md:289
All four PII settings are read once at startup (`app/config.py`); changing them requires a restart.
```

```markdown
// SOURCE: README.md:397
`pii_entities` is the union of types masked in either direction. The audit trail deliberately stores
the **raw, unmasked** prompt and response previews in the database ...
```

The existing prose states the at-rest fact plainly and says why. The new persistence paragraphs match
that register: what is stored, who can read it, and the reason — not the schema.

### Roadmap: the bullet is a link, the substance lives below the line

```markdown
// SOURCE: README.md:530-535
- [ ] [OpenAI-compatible endpoint](#openai-compatible-endpoint) — drop-in use from OpenCode and other coding agents
...
Everything below this line is **intended direction, not current behavior**. The only ingress that exists today is `POST /query`.
```

This is how the story's constraint ("multi-turn must land **below** it") and AC 8 ("multi-turn context
appears in the Planned list") are both satisfied without contradiction: a one-line Planned bullet that
links down, and the explanation in a new `###` subsection **after** line 535. Subsections under
Roadmap are not in the Table of Contents (`#openai-compatible-endpoint` is not), so the ToC is
unchanged.

### The refusal shapes are documented as `### POST /query — <case>` blocks

```markdown
// SOURCE: README.md:330-336
### `POST /query` — 403 (authenticated, lacks `query:submit`)

{"detail": "Permission denied: query:submit"}
```

The foreign-session 403 gets the same shape, with the detail string copied verbatim from
`app/routers/query.py:15`.

---

## Ground Truth Established by Exploration

Every claim the README will make, with the file that proves it. `/implement` must not restate the PRD
where this table and the code disagree.

| Claim to document | Source of truth |
|---|---|
| `CHAT_HISTORY_ENABLED` default `true`; `CHAT_SESSION_LIMIT` default `50` | `app/config.py:82-83` |
| `CHAT_SESSION_LIMIT` below 1 is a **startup error**, not a clamp; the message points at `CHAT_HISTORY_ENABLED` instead | `app/config.py:_validate_chat_session_limit` |
| `session_id` optional on `QueryRequest`; omitting it is byte-identical to the previous release and writes `NULL` | `app/models/schemas.py:17-25` |
| Malformed `session_id` → `422`. "Malformed" means **not a canonical lowercase UUID4**: `{braces}`, `urn:uuid:`, uppercase hex and v1 ids are all refused, and the value is never normalized | `app/models/schemas.py:27-72` |
| Foreign `session_id` → `403`, detail `"session_id does not belong to the authenticated identity"` | `app/routers/query.py:15,68-81` |
| That 403 **is audited** (`success=False`, reason in `error_message`, the attempted `session_id` on the row); the older `user_id`-mismatch 403 is **not** | `app/routers/query.py:35-81` |
| `AuditQueryEntry.session_id: Optional[str]`; `null` for pre-PRD rows and for sessionless sends; no validator on the read side | `app/models/schemas.py:125-139` |
| Four tables now: `audit_logs`, `users`, `chat_sessions`, `chat_messages` | `app/db/database.py` (`init_db`), `app/db/models.py:196-228` |
| `chat_messages` stores the **prompt as typed** (`content=text, prompt=text` on the user bubble) and the **released, redacted** response (`content=result.response`) — the raw upstream text is never written | `chat_ui/chat_ui/state.py:1076-1087`, PRD Section 9 |
| Only the owner reads it: every store function takes an undefaulted `user_id`; `chat_messages` has no `user_id` column, so reads and deletes scope through an `EXISTS`/subselect on `chat_sessions` | `app/db/database.py:1542-1574,1722-1750`, `tests/test_session_ownership.py` |
| `audit_logs` is **unchanged**: still `prompt_hash` plus 500-character raw previews. The one addition is the `session_id` column | PRD Section 9, `README.md:397` (existing, still true) |
| `CHAT_HISTORY_ENABLED=false`: no write, no read, and the rail renders **absent** (`rx.fragment()`), not empty | `app/services/chat_sessions.py` (nine short-circuits), `chat_ui/chat_ui/components/session_rail.py:569-576` |
| Deleting a chat removes `chat_sessions` + `chat_messages` in one transaction and touches no `audit_logs` row; the orphaned `session_id` there is expected and is what preserves the evidence | `app/services/chat_sessions.py::delete`, `app/db/database.py:1542-1576`, `copy.py::SESSION_DELETE_CONFIRM_TEMPLATE` |
| A session row is written **on the first send, never on page load** | `chat_ui/chat_ui/state.py:995-1006` |
| **The first user bubble of a new chat is not persisted** — the create runs after it is appended, so a restored first turn starts at the assistant bubble | `chat_ui/chat_ui/state.py:972-1006`, `_append_and_persist` guard at `:879-885` |
| Auto-title derived once from the first prompt, inside `create`; **rename does not reorder the rail** | `app/services/chat_sessions.py::create,rename`, `app/db/database.py:1516` |
| Sending moves the session to the top; a failed reorder is cosmetic and reports separately from a failed save | `chat_ui/chat_ui/state.py:900-915`, `copy.py::SESSION_ORDER_STALE_NOTICE` |
| The rail lists at most `CHAT_SESSION_LIMIT`, and states its window against the **true account total**, not the list length | `app/services/chat_sessions.py::list_for,count`, `copy.py::SESSION_RAIL_SCOPE_TEMPLATE` |
| Three rail states — listed, "Start your first chat.", and a fault state that says nothing on screen changed | `chat_ui/chat_ui/components/session_rail.py::_body` |
| The rail collapses below `60rem` behind a control labelled **"Chats"** | `chat_ui/chat_ui/theme.py:115`, `chat_ui/chat_ui/components/shell.py:119-177` |
| Two tabs on one session do not see each other's writes | PRD Section 13; no polling or version column exists in `chat_sessions` |
| Multi-turn does **not** work — every send is one user turn, alone; nothing reads the transcript back into the prompt | `chat_ui/chat_ui/state.py::_do_send` passes only `prompt=text` to `run_query` |
| Two instances against one database is **proven**, not assumed | `tests/test_two_instance_smoke.py` (STORY-021, commit `9e0dafc`) |
| `.env.example` already matches `app/config.py` exactly — all 18 settings present, none extra | Both files read in full; `tests/test_config.py:334-360` |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | All ten ACs, plus the two stale claims at `:220` and `:240` |
| `.env.example` | VERIFY (no edit expected) | AC 10 — confirm the exact match with `app/config.py` |
| `tests/test_two_instance_smoke.py` | UPDATE (one comment) | The `README.md:456` line citation at `:462` shifts |

---

## Tasks

Execute in order. Tasks 1–8 are top-down through `README.md` so line numbers shift once, at the end.

### Task 1: Architecture diagram and Features — name the two new tables

- **File**: `README.md`
- **Action**: UPDATE (`:61-110`, `:112-127`)
- **Implement**: In the ASCII diagram, add the transcript store beside the existing Turso annotations
  so all four tables are visible — e.g. a `◄──── Turso (chat_sessions, chat_messages)` annotation on
  the response path where the UI persists the turn. **The pipeline line itself does not change**
  (AC 9): the eight steps, their order, and the `identity → duplicate → pattern → PII → OpenRouter →
  PII → audit` summary at `:56` are all untouched, because the pipeline is untouched. Add one row to
  the Features table: persisted per-conversation transcripts, owner-scoped, with the switch named.
- **Mirror**: the existing `◄──── Turso (audit_logs)` annotation at `README.md:79` and the
  `**PII redaction**` Features row at `:120`
- **Validate**: `grep -n "chat_sessions" README.md` returns the diagram line; the paragraph at `:110`
  about short-circuiting at step 0, 3 or 4 is unchanged

### Task 2: Chat UI — describe the rail as it behaves, and delete the false limitation

- **File**: `README.md`
- **Action**: UPDATE (`:199-222`)
- **Implement**: After the **Message rendering** paragraph, add a **Session rail** paragraph covering,
  in this order: a chat is created **on the first send, never on page load** — opening the app and
  sending nothing leaves nothing behind; it is auto-titled from that first prompt; the rail lists the
  signed-in user's chats newest-activity-first with the active one marked; sending moves a chat to the
  top and **renaming does not** (deliberately — it would move the row the user is looking at while
  they look at it); the rail lists at most `CHAT_SESSION_LIMIT` and states its window against the
  account's true total; it has three states (listed, "Start your first chat.", and a read-failure
  state that says nothing on screen has changed); it collapses below a narrow viewport behind a
  **Chats** control; and deleting asks for confirmation.

  Then rewrite **Known limitations (MVP)**:
  - **Delete** `:218` ("No persisted chat history") outright — it is now false.
  - **Delete** `:220` (no PII indicator) — stale since PRD-004 STORY-009 shipped the badge. Record in
    the report.
  - **Add**: no multi-turn context — every send is one user turn, alone; the model is never given the
    conversation (link to the new Roadmap subsection from Task 8).
  - **Add**: the first turn of a brand-new chat is not saved — the session is created after that
    prompt is on screen, so a reloaded first conversation begins at the assistant's reply.
  - **Add**: two tabs open on one chat do not see each other's writes.
  - **Keep** the streaming and denied-query bullets unchanged.
- **Mirror**: the existing `**Session identity**` paragraph at `README.md:207` — bolded lead-in, one
  paragraph, mechanism named
- **Validate**: `grep -n "No persisted chat history\|No visible indicator when PII" README.md` returns
  nothing

### Task 3: Persistence — what is now at rest, and what the switch does

- **File**: `README.md`
- **Action**: UPDATE (`:226-242`)
- **Implement**: Rewrite the first sentence of **Where state lives** (`:228`) from "Both tables" to
  the four the harness owns. Then add a new `### What is stored, and who can read it` subsection
  immediately after it, stating plainly:
  - `chat_messages` holds **the prompt as the user typed it** and **the response as redaction released
    it** — the raw upstream text is never written. This is a real widening over the previous release's
    hash-and-preview, and it is named as such.
  - Each row is readable **only by the account that wrote it**. Ownership is a parameter on every
    store function, re-checked on every read; a `session_id` belonging to someone else is refused at
    `POST /query` and returns an empty transcript everywhere else. There is no admin path to a
    transcript — `GET /audit` gains `session_id` and nothing more.
  - **`audit_logs` is unchanged.** It still stores the prompt hash and 500-character raw previews, and
    it gained one column, `session_id`. Nothing about the audit trail's contents moved.
  - **`CHAT_HISTORY_ENABLED=false` is a supported configuration, not a degraded mode.** Nothing is
    written, nothing is read, the rail is absent rather than empty, and the chat behaves exactly as it
    did before this release — from the same image, with no code fork. It is the configuration for a
    deployment that must not hold prompt text at rest.
  - **Deleting a chat removes the transcript and leaves the audit record intact.** The session and its
    messages go in one transaction; `audit_logs` is append-only and untouched, so the `session_id` on
    those rows is left orphaned on purpose — that is what preserves the evidence when a user tidies
    their list.
  - **No retention or expiry exists.** Transcripts persist until deleted (PRD Section 13).

  Finally, correct `:240`: two-instance operation now has its end-to-end proof
  (`tests/test_two_instance_smoke.py`). Keep the other two "not included" bullets — no load balancer
  configuration and no Reflex websocket session affinity are both still true — and keep the closing
  "unblocked, not delivered" framing, since the topology work genuinely is not done.
- **Mirror**: `README.md:397`'s existing raw-previews sentence — the register to match
- **Validate**: `grep -n "Both tables the harness owns" README.md` returns nothing

### Task 4: Environment table — the two new variables (AC 1)

- **File**: `README.md`
- **Action**: UPDATE (`:270-289`)
- **Implement**: Two rows appended after `PII_NLP_MODEL`, in `Settings` field order:
  - `CHAT_HISTORY_ENABLED` | No | `true` | Master switch for transcript persistence. `false` writes no
    transcript, reads none, and renders no session rail — the chat behaves exactly as it did before
    this release. A supported configuration for a deployment that must not hold prompt text at rest,
    not a degraded mode.
  - `CHAT_SESSION_LIMIT` | No | `50` | How many chats the rail lists per user. A value below `1` is a
    **startup error**, not a clamp: an empty rail on an account that has chats is a silent lie. To
    turn persistence off, use `CHAT_HISTORY_ENABLED=false`.

  Then correct `:289` — "All four PII settings are read once at startup" — so it covers the chat
  settings too, or generalize it to every setting in the table (all of `Settings` is read at import).
- **Mirror**: the `PII_REDACTION_ENABLED` and `RBAC_ENABLED` rows, which the AC names as the pattern
- **Validate**: `grep -c "CHAT_HISTORY_ENABLED\|CHAT_SESSION_LIMIT" README.md` ≥ 2; the two rows sit
  after `PII_NLP_MODEL` and before the closing prose

### Task 5: `POST /query` — `session_id`, the 422 and the 403 (AC 2)

- **File**: `README.md`
- **Action**: UPDATE (`:297-336`)
- **Implement**: In the success section, after the existing `user_id` backward-compatibility paragraph
  at `:320`, add one paragraph: `session_id` is optional; omitting it behaves exactly as the previous
  release and writes `NULL` to the audit row. Present, it must be a **canonical lowercase UUID4**
  string — the harness mints session ids and echoes them back unchanged, so `{braces}`, `urn:uuid:`,
  uppercase hex and non-v4 ids are each a `422`, and the value is written as supplied rather than
  normalized. Then add a new block after the existing `query:submit` 403 (`:336`), titled
  `### POST /query — 403 (session belongs to another identity)`, carrying the JSON
  `{"detail": "session_id does not belong to the authenticated identity"}` and one sentence noting
  that, unlike the `user_id` mismatch above, **this refusal is written to the audit log** — with the
  attempted `session_id` on the row — because a rejected send is logged with the same rigor as an
  accepted one.
- **Mirror**: `README.md:330-336`, the `query:submit` 403 block
- **Validate**: `grep -n "does not belong to the authenticated identity" README.md app/routers/query.py`
  — the strings match verbatim

### Task 6: `GET /audit` — `session_id` in the response shape (AC 3)

- **File**: `README.md`
- **Action**: UPDATE (`:374-406`)
- **Implement**: Add `"session_id": "0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"` to the example row's JSON,
  beside `role` and `denied_permission`. Extend the closing paragraph at `:406` (which already
  explains `null` for `role`/`denied_permission` on older rows) to cover `session_id`: `null` both for
  rows written before this release and for any send that carried no session, so three rows that were
  one conversation are visibly one conversation instead of a guess. State that this is the **only**
  place `session_id` surfaces to an admin — no endpoint and no console surface exposes a transcript.
- **Mirror**: the `role` / `denied_permission` treatment in the same block
- **Validate**: the JSON block still parses; `grep -c "session_id" README.md` increases

### Task 7: Roadmap — Shipped gains chat sessions (AC 8, first half)

- **File**: `README.md`
- **Action**: UPDATE (`:518-526`)
- **Implement**: Append `- [x] Chat sessions — persisted, per-conversation transcripts` after the RBAC
  entry.
- **Mirror**: the six existing `- [x]` entries
- **Validate**: `sed -n '516,530p' README.md`

### Task 8: Roadmap — multi-turn context, below the line (AC 8, second half)

- **File**: `README.md`
- **Action**: UPDATE (`:527-535` and after `:535`)
- **Implement**: Add one Planned bullet linking down —
  `- [ ] [Multi-turn context](#multi-turn-context) — sending a chat's history to the model` — and a
  new `### Multi-turn context` subsection **after** the "intended direction, not current behavior"
  line at `:535`. That subsection must:
  - Say outright that a session today is **not** a conversation the model remembers: every send is one
    user turn, alone.
  - State the duplicate-detection consequence as the reason it is deferred: `check_duplicate` hashes
    the whole prompt against a global 24-hour window with no user and no session scope, so in a real
    conversation *"yes"*, *"go on"* and *"thanks"* would collide constantly and be held. Rescoping
    that hash is a change to the product's central security control.
  - **Cross-reference, do not restate**, the [OpenAI-compatible endpoint](#openai-compatible-endpoint)
    section's existing open question about what to hash in a multi-turn conversation — the story is
    explicit that the question is already posed there and sessions make it unavoidable rather than
    optional.
  - Keep the line at `:535` verbatim. It stays true: this release adds no ingress.
- **Mirror**: the `### OpenAI-compatible endpoint` subsection's shape — bullet above, prose below
- **Validate**: `grep -n "Everything below this line" README.md` shows the line still precedes the new
  subsection; the anchor `#multi-turn-context` resolves to the new heading

### Task 9: Reconcile the cross-file line citation

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE (`:462`, a comment only)
- **Implement**: The comment cites `README.md:456` for the three-override in-container test command.
  Every edit above shifts that line. Re-locate the block
  (`grep -n "docker-compose run --rm" README.md`) and update the number — or, better, replace the
  number with the section name (`README.md`'s *Running Tests*), so the citation cannot go stale again.
- **Mirror**: n/a — this is a one-line comment fix
- **Validate**: `pytest tests/test_two_instance_smoke.py --collect-only -q` still collects; no
  assertion changed

### Task 10: Verify `.env.example` against `app/config.py` (AC 10)

- **File**: `.env.example`
- **Action**: VERIFY — **no edit is expected**
- **Implement**: Both files were read in full during exploration and already agree: all 18 `Settings`
  fields appear in `.env.example`, in declaration order, each with a comment, and nothing is
  documented that does not exist. `CHAT_HISTORY_ENABLED` and `CHAT_SESSION_LIMIT` landed there in
  STORY-001 with the off-state consequence spelled out. Confirm mechanically rather than by eye, and
  make **no change** if the check passes — an unnecessary edit to a file eight tests assert against is
  a risk with no upside. If the check finds a mismatch, fix `.env.example` and record it in the report
  as a divergence STORY-001 left behind.
- **Validate**: run `scripts`-free inline Python that reads both files, collects
  `re.findall(r"(?m)^    ([A-Z][A-Z0-9_]+):", config_text)` as the declared set and
  `re.findall(r"(?m)^#?\s?([A-Z][A-Z0-9_]+)=", env_text)` as the documented set, and asserts the
  symmetric difference is empty in both directions.

---

## End-to-End Tests

- [ ] `pytest tests/test_config.py -v` — the eight `.env.example` assertions pass unchanged
- [ ] `pytest tests/ -q` — full suite green; this story changes no application code, so any failure is
      a pre-existing one and belongs in the report, not in a fix here
- [ ] Every `README.md` anchor link resolves: `#multi-turn-context`, `#openai-compatible-endpoint`,
      `#persistence--deployment`, `#running-tests`, and the Table of Contents entries (unchanged)
- [ ] The detail string in the new 403 block is byte-identical to `_FOREIGN_SESSION_DETAIL` in
      `app/routers/query.py:15`
- [ ] Read the finished Chat UI and Persistence sections against the **Ground Truth** table above,
      line by line. Any sentence not traceable to a row there is either cut or given a source.
- [ ] Confirm the README nowhere claims the model sees prior turns, and nowhere implies the admin
      console shows sessions

## Validation

```bash
# The claims that must be gone
grep -q "No persisted chat history" README.md && echo FAIL || echo ok
grep -q "Both tables the harness owns" README.md && echo FAIL || echo ok

# The claims that must be present
grep -q "CHAT_HISTORY_ENABLED" README.md && echo ok
grep -q "CHAT_SESSION_LIMIT" README.md && echo ok
grep -q "session_id does not belong to the authenticated identity" README.md && echo ok

pytest tests/test_config.py -q
pytest tests/ -q
```

## Acceptance Criteria

(Copied from story `STORY-022`)

- [ ] Given `README.md`, when the environment table is read, then `CHAT_HISTORY_ENABLED` and
      `CHAT_SESSION_LIMIT` appear with their defaults and their effect, alongside
      `PII_REDACTION_ENABLED` and `RBAC_ENABLED`.
- [ ] Given the API reference section, when `POST /query` is read, then `session_id` is documented as
      optional, with the `422` on a malformed value and the `403` on a foreign one both stated.
- [ ] Given the API reference, when `GET /audit` is read, then `session_id` appears in the response
      shape.
- [ ] Given the persistence section, when it is read, then it states plainly what is now stored: the
      prompt as typed and the redacted response, per session, readable only by the owner — and that
      `audit_logs` still stores hashes and truncated previews and is unchanged.
- [ ] Given the same section, when it is read, then it states what `CHAT_HISTORY_ENABLED=false` does
      and that it is a supported configuration, not a degraded mode.
- [ ] Given the deletion behaviour, when it is documented, then it says that deleting a chat removes
      the transcript and leaves the audit record intact.
- [ ] Given the Chat UI section, when it is read, then the session rail is described as it actually
      behaves — including that a chat is created on the first send, not on page load.
- [ ] Given the Roadmap's **Shipped** list, when it is read, then chat sessions appear; and given the
      **Planned** list, then multi-turn context appears with the duplicate-detection consequence
      stated.
- [ ] Given the architecture diagram, when it is read, then the two new tables appear alongside
      `audit_logs` and `users`, and the pipeline line is unchanged — because the pipeline is unchanged.
- [ ] Given `.env.example`, when it is read, then it matches `app/config.py` exactly — every setting
      present, no setting documented that does not exist.
- [ ] All tasks completed
- [ ] Full test suite passes
- [ ] No application code changed
- [ ] Follows existing patterns

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| **The most likely defect in this release is a README that describes a session as a conversation the model remembers.** It is not. | Task 2 and Task 8 both say so explicitly, in the user-facing sections a reader actually reaches. The E2E checklist has a dedicated line for it. |
| Documenting the PRD rather than the code — particularly the first-turn persistence gap, which the PRD does not mention. | The **Ground Truth** table cites a file for every claim; anything not in it is cut or sourced. The gap is called out by name in the Summary and in Task 2. |
| Overstating the admin surface: `session_id` reaches `GET /audit` and stops. | Task 6 states the boundary in the same paragraph, and Task 3 repeats it from the security side. PRD Section 4 puts console grouping out of scope. |
| Editing `.env.example` unnecessarily and reddening `tests/test_config.py`. | Task 10 is a verification with a mechanical check and an explicit "make no change if it passes". |
| Line-number drift breaking the `README.md:456` citation in `tests/test_two_instance_smoke.py`. | Task 9, run last, after every README edit has landed — and it replaces the number with a section name so the problem does not recur. |
| Putting multi-turn **above** the "intended direction, not current behavior" line, contradicting it. | Task 8 splits the bullet from the substance, following the `#openai-compatible-endpoint` precedent already in the file, and keeps line 535 verbatim. |
| Silently "fixing" the audited/non-audited 403 asymmetry into a single sentence that flattens it. | `app/routers/query.py`'s own comment says an existing test pins the older arm to write no row. Task 5 documents the asymmetry as real behaviour rather than smoothing it. |
