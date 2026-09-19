---
story: STORY-018
prd: PRD-010
slug: readme-and-env-documentation
title: "README: multi-turn context shipped, limits and trade-offs; .env.example settings"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-19
---

# Plan: README: multi-turn context shipped, limits and trade-offs; .env.example settings

## Summary

The last story of PRD-010 is documentation-only. `README.md` still describes the pre-epic world: a chat session is "a saved transcript, not a conversation the model remembers", *Multi-turn context* sits below the roadmap's "intended direction, not current behavior" line, and the four settings the epic added (`OPENROUTER_TIMEOUT_SECONDS`, `CONTEXT_MAX_MESSAGES`, `CONTEXT_MAX_CHARACTERS`, `PIPELINE_MAX_WORKERS`) appear in neither the configuration table nor `.env.example` — STORY-002 deliberately deferred them here.

The fix is seven README edits plus one `.env.example` group:

1. Features table — a **Multi-turn context** row.
2. `### Multi-turn context` **moves** from the Roadmap (below the "intended direction" line) to a shipped-behaviour section under Features, keeping the `#multi-turn-context` anchor so all four existing links stay live. It carries the five facts AC 1 names, the STORY-015 latency numbers (cost) and the STORY-014 result (executor).
3. Roadmap — the unchecked item moves from *Planned* to *Shipped*.
4. Chat UI *Known limitations* — "No multi-turn context" out; five new limitation facts in.
5. API Reference — a new `POST /query` — blocked (context limit) block, noted as the epic's only new outcome.
6. Environment Variables table — four new rows.
7. *OpenAI-compatible endpoint* — the two sentences that now describe shipped internals, without implying PRD-014 shipped.

`.env.example` gains a `# Multi-turn pipeline (PRD-010)` group of four settings. Two mirror tests in `tests/test_config.py` come with it (Task 8) because every other settings group in that file has them and their absence is the gap STORY-002 left when it deferred this work; that is a supporting edit, recorded under *Deviations* in the report. `pre-prds/PRE-PRD-010-multi-turn-pipeline.md` is verified, not edited — it already reads `status: promoted` with its `prd:` path set. Links and anchors are checked with a throwaway script, and the full suite is run.

## User Story

As a reader of the README
I want to know that chats are now conversations, what the model sees, what it doesn't, and which settings control it
So that the documented behaviour matches the shipped one

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-018-readme-and-env-documentation.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md` — Sections 6.4 (history assembly, D3–D5), 6.5 (context limits, D2), 6.6 (D6), 6.7 (D7), 7 (F9), 9.3 (configuration), 10 (API), 15 (*Refinement of the brief's criterion*)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (docs only; story `type: technical`) |
| Complexity | LOW |
| Systems Affected | `README.md`, `.env.example`, `tests/test_config.py` (two added tests). Verified only: `pre-prds/PRE-PRD-010-multi-turn-pipeline.md`, `pre-prds/README.md`, `app/config.py` |
| Story | STORY-018 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |
| Dependencies | STORY-014 ✅ `0b0a077`, STORY-015 ✅ `0a95158`, STORY-016 ✅ `233b208`, STORY-017 ✅ `92b2d2a` — all `done` |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds exactly one skill, `frontend-design`, read in full. Its description covers "distinctive, intentional visual design when building new UI or reshaping an existing one" — visual identity, typography, layout. This story writes prose in `README.md` and comments in `.env.example`; no UI is built or reshaped. The story's `skills: []` and its Technical Note ("Skills: none applicable") agree. No rule applies. | — |

---

## Facts the design depends on (verified during planning)

| Fact | Evidence |
|---|---|
| **The four settings exist with PRD 9.3's defaults and `≥ 1` / `> 0` validators.** | `app/config.py:108` `OPENROUTER_TIMEOUT_SECONDS: float = 120.0`; `:112` `CONTEXT_MAX_MESSAGES: int = 100`; `:118` `CONTEXT_MAX_CHARACTERS: int = 200_000`; `:122` `PIPELINE_MAX_WORKERS: int = 32`; validators at `:181` and `:192`, the latter using `_PIPELINE_LIMIT_DESCRIPTIONS` (`:19-21`). |
| **`.env.example` documents none of them — deliberately deferred to this story.** | `grep` over `.env.example` → no hit for any of the four. `STORY-002-timeout-context-and-executor-settings.md:41`: "Leave `.env.example` alone. STORY-018 documents all four settings together with the README." |
| **Every other settings group in `tests/test_config.py` has a `…_documents_…_with_a_comment` + `…_appear_in_settings_field_order` pair; the PRD-010 group has neither.** | `tests/test_config.py:64,71` (RBAC), `:224,238` (Turso), `:334,341` (chat). The PRD-010 block (`:366-449`) asserts defaults, validators and env-independence only. |
| **Context-limit body and its wording.** | `app/services/query_pipeline.py:214` `reason="Conversation exceeds context limit"`; `app/models/schemas.py:102-122` `QueryBlockedContextLimitResponse(status, reason, limit: Literal["messages","characters"], maximum, actual)`; **only one limit is reported**, `messages` checked first (docstring `:105-111`). |
| **Position in the pipeline: after all three authorization arms, before the duplicate check.** | `app/services/query_pipeline.py:181-216` (Step 3), with the reasoning in the comment: an unauthorized caller "learns nothing about how this deployment is configured", and an over-limit conversation "neither consults the duplicate window nor lands in it". |
| **The context-limit row audits `success=False`, `error_message="context limit: …"`, non-NULL `dedup_key`, no new column.** | Same block, `:204-212`. PRD 6.5 confirms, and PRD 9.2 T7 accepts the `success_rate` cost. |
| **History is only answered exchanges, and it recovers the unsaved first user turn.** | PRD 6.4: `assemble` reads `kind == "assistant"` rows in `id` order, emitting `Message("user", row.prompt), Message("assistant", row.content)`. `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` and `context_limit` rows are never read. |
| **History is always redacted, at the pipeline, on every send.** | `app/services/query_pipeline.py:258-281` (Step 6) redacts **every** message; `<ENTITY_TYPE>` placeholders are not re-detected (PRD 6.4, D5). |
| **D7: PII audit fields describe the new turn plus the output only.** | Same block, `:265-281`: `input_entities` is assigned only at `index == last_index`. Rationale in PRD 6.7 — otherwise one email in turn 1 inflates `pii_detected_queries` in `/stats` for the rest of the session. |
| **D6: patterns inspect the last user turn only, provisionally.** | `app/services/query_pipeline.py:243` Step 5 calls `detect_suspicious_pattern(_inspection_target(messages))`; PRD 6.6 marks it `PROVISIONAL (PRD-010 D6): … PRD-011 replaces this`. |
| **The chat UI trims oldest whole exchanges and says so on the reply.** | `chat_ui/chat_ui/copy.py:87-88` `FOOTER_TRIMMED_TEMPLATE = "{count} earlier exchanges were not sent to the model"` / `FOOTER_TRIMMED_SINGLE_TEMPLATE`; rendered in the assistant footer at `chat_ui/chat_ui/components/bubbles.py:203-230`, last item, and absent entirely at `history_trimmed == 0`. |
| **The context-limit bubble exists in the chat, held not rejected.** | `chat_ui/chat_ui/components/bubbles.py:353` `render_context_limit`; `chat_ui/chat_ui/copy.py:63` `TAG_CONTEXT_LIMIT = "TOO LONG"`, `:120-126` headline "This chat is too long to send.", "Start a new chat to continue.", detail `"{unit} {actual} of {maximum}"`. Routed at `chat_ui/chat_ui/components/chat.py:38`. |
| **`CHAT_HISTORY_ENABLED=false` keeps single-turn, selecting pipeline input rather than only persistence.** | PRD 7 F8: the explicit branch sends `run_query(prompt=text)` on the off path. `chat_ui/chat_ui/state.py:1103-1123`. |
| **Characters, not tokens, is a documented proxy.** | `app/config.py:114-117` comment; PRD Section 4 *Out of Scope*. |
| **The duplicate criterion refinement.** | PRD Section 15 *Refinement of the brief's criterion*: the first send of two new sessions within 24 h is `[user("yes")]` in both cases — identical to two `/query` calls — and PRD-009 blocks that on purpose. The key is unchanged by this epic; adding `session_id` would be a `DEDUP_KEY_VERSION` change owned by a follow-up. |
| **STORY-015 latency, as measured.** | `.agents/reports/…/STORY-015-history-latency-measurement.report.md`: at 20 exchanges (41 messages, 19,193 characters), **added per send p50 926.05 ms**, p95 961.22 ms; `assemble`+`fit` 5.17 ms p50, the extra per-turn redaction 927.22 ms — **redaction is ~97%** of the added cost, growing ~23 ms per message. Local libSQL, `en_core_web_lg`. |
| **STORY-014 concurrency, as proven.** | `.agents/reports/…/STORY-014-pipeline-concurrency-tests.report.md`: `tests/test_pipeline_concurrency.py`, five tests. With ten `/query` calls parked inside the upstream, `/health` answers in < 1 s and an eleventh `/query` returns `SUCCESS` in < 1 s writing exactly eleven audit rows; the same holds for ten sends through `ChatState._do_send` on its history path; with `PIPELINE_MAX_WORKERS=10` the eleventh queues while `/health` still answers. **No production file changed.** |
| **Pre-PRD already correct and tracked.** | `pre-prds/PRE-PRD-010-multi-turn-pipeline.md` frontmatter: `status: promoted`, `prd: .agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md`. `git ls-files pre-prds` lists all nine files — unlike PRD-009's STORY-010, no staging gate is needed. |
| **`pre-prds/README.md` needs no status edit.** | Its table (`:16`) carries Order / Brief / Target PRD / Est. stories / Depends on — there is no status column to mark. The "mark the pre-PRD `promoted`" instruction at `:5` refers to the brief's own frontmatter, which is already set. F9's sentence is satisfied by the brief, not the index. |
| **No test reads `README.md`.** | `grep -rn "README" tests/` → docstrings and comments only. `tests/test_config.py` reads `.env.example`, which is why Task 8 exists. |
| **No link or anchor checker exists** in `tests/`, `scripts/` or CI. | `scripts/` holds `manage_users.py`, `migrate_to_turso.py`, `measure_history_latency.py`. |
| **README line map (current, pre-edit).** | Features table row for chat sessions `:157`, table ends `:160`; `### Duplicate detection scope` `:162`, section ends before `---` `:188`; Chat UI limitations `:282`, "No multi-turn context" `:285`; env table last rows `:396-398`, closing sentence `:400`; API `### POST /query — 200, refused by policy` `:485`, `### GET /audit` `:497`; Roadmap *Shipped* ends `:652`, *Planned* multi-turn `:657`, "intended direction" line `:663`, `### Multi-turn context` `:665-671`, `### OpenAI-compatible endpoint` `:673`, answered dedup bullet `:687`. |
| **Four live links point at `#multi-turn-context`.** | `README.md:285` (Chat UI limitation), `:657` (roadmap item), `:687` (OpenAI bullet), plus `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md` → `../../../README.md#multi-turn-context`. Moving the section while keeping the heading text keeps every one of them resolving. |

---

## Patterns to Follow

### README voice: bold lead-in that states the claim, then the reason
```
// SOURCE: README.md:332
**`CHAT_HISTORY_ENABLED=false` is a supported configuration, not a degraded mode.** With it off, no transcript row is written and none is read, the session rail is *absent* rather than empty, and the chat behaves exactly as it did before this release — same image, same code path, no fork to maintain.
```

### Naming what is *not* included, in the same breath as what is
```
// SOURCE: README.md:184-186
Two weaknesses are accepted on purpose:

- **One repeat per account.** Because the scope is per user, N accounts can each send the same prompt once per window. … per-user rate limits and token budgets that close the gap are planned as PRD-013 and are not built yet.
```

### Citing a test as the proof of a claim
```
// SOURCE: README.md:181
Every case above has an end-to-end test in `tests/test_duplicate_scope.py`. The full threat reasoning … is in [PRD-009, Section 9.2](.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md#92-threat-reasoning).
```

### An API Reference outcome block: heading, JSON, then one paragraph of meaning
```
// SOURCE: README.md:485-495
### `POST /query` — 200, refused by policy

```json
{ "status": "BLOCKED", "reason": "Model not permitted for this role", "required_permission": "query:model:claude-3-opus" }
```

Model-allowlist and BYOK … refusals return `200` with this shape, not `403` — the caller is authenticated and allowed to call the endpoint, but the content of the request is what's refused.
```

### Environment-variable row: default, then the consequence of changing it
```
// SOURCE: README.md:396
| `CHAT_SESSION_LIMIT` | No | `50` | How many chats the session rail lists per user. … A value below `1` is a **startup error**, not a clamp — an empty rail on an account that has chats is a silent lie. |
```

### `.env.example` group: a comment block that states the consequence, then `VAR=default`
```
// SOURCE: .env.example:56-62
# Master switch for chat transcript persistence (true/false). false writes no
# transcript, reads none, shows no session rail, and the chat behaves exactly
# as it did before PRD-008 - the supported configuration for a deployment that
# must not hold prompt text at rest
CHAT_HISTORY_ENABLED=true
```
ASCII only in this file (`-` not `—`), and the comment sits on the line directly above the assignment — `tests/test_config.py:68` matches `(?m)^#.+\n{var}=`.

### Tests that guard `.env.example`
```
// SOURCE: tests/test_config.py:334-347
def test_env_example_documents_both_chat_vars_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for var in ("CHAT_HISTORY_ENABLED", "CHAT_SESSION_LIMIT"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_chat_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = ["CHAT_HISTORY_ENABLED", "CHAT_SESSION_LIMIT"]
    positions = [text.index(f"{var}=") for var in declared_order]
    assert positions == sorted(positions)
```

### In-page anchors (GitHub slug: lowercase, punctuation dropped, spaces → hyphens)
```
// SOURCE: README.md:31, 285, 657
- [Quickstart — Local](#quickstart--local)
See [Multi-turn context](#multi-turn-context) for why, and what it would cost to change.
```

### Commit messages on this epic
```
// SOURCE: git log (233b208, 92b2d2a, b910f8e)
test(pipeline): STORY-016 seven-outcome and chat UI regression on the finished epic
test(smoke): STORY-017 a multi-turn chat continued across two instances
chore(PRD-010): update STORY-017 status + index; record commit SHA
```

### Error handling
Not applicable — no runtime code changes. The "error" this story fixes is a README that documents pre-epic behaviour; it is fixed by stating the shipped behaviour and naming the test or code that proves it.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | Features row; `### Multi-turn context` moved to shipped behaviour; roadmap item moved to *Shipped*; Chat UI limitations rewritten; context-limit API block; four configuration rows; two *OpenAI-compatible endpoint* sentences |
| `.env.example` | UPDATE | `# Multi-turn pipeline (PRD-010)` group with the four settings, defaults and one-line comments |
| `tests/test_config.py` | UPDATE | Two mirror tests guarding the new `.env.example` group (supporting edit, see Task 8) |
| `pre-prds/PRE-PRD-010-multi-turn-pipeline.md` | **NONE** (verify only) | AC 5 — already `status: promoted` with `prd:` set |
| `pre-prds/README.md` | **NONE** (verify only) | F9's "track overview" sentence; no status column exists |
| `app/config.py` | **NONE** (verify only) | Confirm the documented defaults match the code, field for field |
| `<scratchpad>/check_readme_links.py` | CREATE (scratchpad, **not committed**) | AC 5 link/anchor verification |

---

## Tasks

Execute in order. Each task is atomic and verifiable. The copy below is the intended text — `/implement` may tighten wording but must keep every fact, link and number.

### Task 1: AC 1 — Features table gains a *Multi-turn context* row

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: insert after the *Persisted chat sessions* row (`:157`), before *Admin endpoints*:
  ```
  | **Multi-turn context** | The chat sends the conversation, not just the latest message: every answered exchange in the session that fits the configured limits goes upstream, redacted, on every send. The pipeline takes a list of messages; `POST /query` is the one-message case and is unchanged. See [Multi-turn context](#multi-turn-context). |
  ```
- **Mirror**: `README.md:157` (row voice: what it does, then the boundary of what it does)
- **Validate**: `grep -n "| \*\*Multi-turn context\*\* |" README.md` → one hit

### Task 2: AC 1 — move `### Multi-turn context` out of the roadmap and rewrite it as shipped

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: two moves in one edit.

  **(a) Delete** the section currently at `:665-671` (the `### Multi-turn context` heading and its three paragraphs), which sits *below* the "Everything below this line is **intended direction, not current behavior**" line at `:663`. Leave that line and `### OpenAI-compatible endpoint` in place.

  **(b) Insert** the section below at the end of the Features block — after the *Duplicate detection scope* section's last paragraph (`:187`), before the `---` at `:188`. Keep the heading text **exactly** `### Multi-turn context` so `#multi-turn-context` still resolves from `:285`, `:657`, `:687` and from PRD-009's PRD.

  ```markdown
  ### Multi-turn context

  **A chat session is now a conversation the model remembers.** Each send carries the session's earlier exchanges to the model, not just the latest message. The pipeline itself takes a list of messages rather than a string; `POST /query` sends a one-message list and behaves exactly as it did before this release.

  **History is built from answered exchanges only.** Each stored assistant reply carries the prompt that produced it, and those pairs — oldest first — are the history. A send that was held as a duplicate, blocked on a pattern, denied by policy, refused for length, or that failed upstream contributes nothing, and neither does the message that caused it. A side effect worth knowing: because the pair is recovered from the reply, the first question of a new chat reaches the model as history even though it is not itself stored (see *[Known limitations](#chat-ui)* under Chat UI).

  **History is always redacted.** Every message on every send goes through PII redaction before it leaves the process — history included, whatever wrote it. Stored prompts are raw, so this is enforced at the pipeline rather than trusted from the store. Presidio's `<ENTITY_TYPE>` placeholders are not re-detected, so an already-masked reply passes through unchanged.

  **Oldest exchanges are dropped when a chat outgrows the limits, and the answer says so.** `CONTEXT_MAX_MESSAGES` (default `100`) and `CONTEXT_MAX_CHARACTERS` (default `200000`) bound what a conversation may carry. The chat UI drops whole exchanges from the oldest end — never half of one — until both hold, and the reply's footer reads `3 earlier exchanges were not sent to the model`. Nothing is deleted: the transcript on your screen is complete, and only what went upstream was trimmed.

  **The pipeline refuses a conversation that is still over the limit.** Refuse, not silently truncate: a client that trims knows what it dropped, and a server that trims does not. The refusal is a `200` with `"status": "BLOCKED"`, naming the limit, the maximum and the actual — see [`POST /query` — blocked (context limit)](#post-query--blocked-context-limit). In the chat this renders as a held bubble reading *This chat is too long to send.* with *Start a new chat to continue.* One case reaches it from a single message: a prompt over `CONTEXT_MAX_CHARACTERS` is now refused where it previously went upstream. That is the one behaviour change on `POST /query` in this release.

  **`CHAT_HISTORY_ENABLED=false` keeps the chat single-turn.** The flag already governed whether transcripts are stored; it now also selects what the chat sends. With it off, each send carries one user turn, exactly as before — same image, same code path.

  **What it costs.** Measured on a session of 20 exchanges (41 messages, ~19k characters) against a local database: **about 0.93 s added per send** (p50 926 ms, p95 961 ms), growing roughly 23 ms per message. Reading the history is not the cost — that is 5 ms; **re-redacting every turn is ~97% of it**. A deployment that finds this too slow has two levers today, `CONTEXT_MAX_MESSAGES` and `PII_REDACTION_ENABLED`, and the second one turns off a security control. The measurement script is `scripts/measure_history_latency.py`.

  **Slow conversations no longer stall the process.** Long contexts mean long upstream calls, so the whole pipeline runs on its own bounded thread pool (`PIPELINE_MAX_WORKERS`, default `32`) rather than the shared server pool. `tests/test_pipeline_concurrency.py` proves it: with ten sends parked inside the upstream, `/health` answers in under a second and an eleventh query is answered in under a second, from both `POST /query` and the chat's history path. With the pool set to 10, the eleventh send queues — and `/health` still answers.
  ```
- **Note on the "not sufficient for external callers" gap**: it belongs to the *Known limitations* bullet in Task 4 (pattern inspection), not here, so this section reads as shipped behaviour and the caveats sit together in one place.
- **Mirror**: `README.md:162-187` (*Duplicate detection scope*: a shipped-behaviour subsection under Features, bold lead-ins, named trade-offs), `README.md:332` (voice)
- **Validate**:
  - `grep -n "^### Multi-turn context" README.md` → exactly one hit, and its line number is **below** `### Duplicate detection scope` and **above** the `## Requirements` heading.
  - `awk '/^Everything below this line/,0' README.md | grep -c "^### Multi-turn context"` → `0`
  - `grep -n "926\|0.93 s\|PIPELINE_MAX_WORKERS\|test_pipeline_concurrency" README.md` → all present

### Task 3: AC 1 — the roadmap item moves from *Planned* to *Shipped*

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**:
  - Delete the *Planned* item at `:657` (`- [ ] [Multi-turn context](#multi-turn-context) — …`).
  - Add to *Shipped*, after `- [x] Chat sessions — persisted, per-conversation transcripts` (`:652`):
    ```
    - [x] [Multi-turn context](#multi-turn-context) — the chat sends its history, so a session is a conversation
    ```
- **Why both halves matter**: AC 1 names "the unchecked item **and** the 'intended direction' section". Task 2(a) handled the section; this handles the checkbox. Leaving either behind would have the roadmap contradict the Features section one screen up.
- **Mirror**: `README.md:646-652` (*Shipped* list style)
- **Validate**: `grep -n "^- \[ \] \[Multi-turn" README.md` → no hits; `grep -n "^- \[x\] \[Multi-turn" README.md` → one hit

### Task 4: AC 2 — Chat UI *Known limitations* rewritten

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: replace the bullet at `:285` (`- **No multi-turn context.** …`) with the five bullets below. Keep the other four bullets (`:284`, `:286-288`) untouched; `- **The first turn of a brand-new chat is not saved.**` stays, because it is still true of the *transcript*, and Task 2 already explains why history is unaffected.
  ```markdown
  - **The context limits are characters, not tokens.** `CONTEXT_MAX_CHARACTERS` counts characters across message contents — a deliberate proxy, because counting tokens means a per-model tokenizer the harness does not carry. Budget conservatively: for English prose, ~200,000 characters is roughly 50,000 tokens, and code runs denser.
  - **Prompt-injection patterns are checked on the newest user turn only.** History is redacted but not re-inspected. For the chat that is sufficient — every earlier user turn was itself the newest turn of a send that passed. It is *not* sufficient for history a caller supplies, which is why no such ingress exists yet; per-role inspection of whole conversations is PRD-011, and this behaviour is provisional until it lands.
  - **The PII audit fields describe the new turn and the output, not the history.** `pii_detected_input` and `pii_entities` on an audit row cover the message you just sent plus the model's reply. Entities found while re-masking history are masked but not recorded again — otherwise one email in the first turn would mark every later send of that session as a PII event and inflate the figures in `/stats` and the admin console.
  - **The first send of two new chats with the same text is still a duplicate.** Two brand-new chats both start as a single turn, so within 24 hours the second is indistinguishable from repeating a `POST /query` call — and that is held, by design. Once a chat has one exchange behind it, its history is part of the key, so *"yes"* after two different conversations is two different queries. See [Duplicate detection scope](#duplicate-detection-scope).
  - **Redacted history can make answers less precise.** The model sees `<PERSON>` where you wrote a name, in every earlier turn as well as the current one, so a conversation that turns on the specifics of masked data will read as vaguer than the transcript on your screen. The trade is deliberate: unmasked text never leaves the process.
  ```
- **Mirror**: `README.md:284-288` (bullet voice: the limitation in bold, then why it is the way it is)
- **Validate**: `grep -n "No multi-turn context" README.md` → no hits; `sed -n '/^\*\*Known limitations (MVP)\*\*/,/^---/p' README.md | grep -c '^- '` → `8`

### Task 5: AC 3 — the context-limit `BLOCKED` body in the API Reference

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: insert a new block after `### POST /query — 200, refused by policy` (`:485-495`) and before `### GET /audit` (`:497`):
  ````markdown
  ### `POST /query` — blocked (context limit)

  ```json
  {
    "status": "BLOCKED",
    "reason": "Conversation exceeds context limit",
    "limit": "characters",
    "maximum": 200000,
    "actual": 250113
  }
  ```

  **This is the only outcome this release adds** — the six before it are unchanged, request and response alike. `limit` is `messages` or `characters`, and **only one is ever reported**: the message count is checked first and returns immediately, so a conversation over both is reported as `messages`. A caller that shortens to fit the count is told about the character count on the next attempt; naming both would imply the two were measured independently when the second was never reached. `maximum` is the limit as configured for that call, echoed back so a client can see the bound it broke without reading the server's configuration.

  The check sits after authorization and before the duplicate check. After, so a caller without `query:submit` learns nothing about how the deployment is configured; before, so an over-limit conversation neither consults the 24-hour window nor lands in it — it never got a verdict, so it is not a query anyone asked twice. The attempt is still audited, as `success=false` with `error_message` naming the limit — the same shape an upstream failure writes, and no new `audit_logs` column. `GET /audit` and `GET /stats` are unchanged; these rows count against `success_rate`, which is accepted.

  For `POST /query` the reachable case is a single prompt over `CONTEXT_MAX_CHARACTERS` (200,000 by default, ≈50k tokens of English), which previously went upstream. See [Multi-turn context](#multi-turn-context).
  ````
- **Mirror**: `README.md:485-495` (heading → JSON → meaning), `README.md:459-470` (a block that also explains *where* the check sits and what is audited)
- **Validate**: `grep -n "Conversation exceeds context limit" README.md` → one hit; `python -c "import app.models.schemas as s; print(s.QueryBlockedContextLimitResponse.model_fields.keys())"` → the four documented fields plus `status`

### Task 6: AC 3 — four rows in the Environment Variables table

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: insert after the `CHAT_SESSION_LIMIT` row (`:396`), before `REPORTS_AGENTS_DIR` (`:397`), keeping the table's declaration order:
  ```
  | `OPENROUTER_TIMEOUT_SECONDS` | No | `120.0` | How long to wait for the upstream model provider, in seconds. Was a hard-coded 30 s, which is too short for a long conversation. Must be greater than `0` — a non-positive value would either hang forever or fail every call instantly, so it is a **startup error**. |
  | `CONTEXT_MAX_MESSAGES` | No | `100` | Most messages a conversation may carry into the pipeline, counting every user and assistant turn plus the new one. Checked before `CONTEXT_MAX_CHARACTERS`, and the only limit reported when both are broken. The chat UI trims to fit before sending; a conversation still over it is refused. Must be at least `1`. |
  | `CONTEXT_MAX_CHARACTERS` | No | `200000` | Most characters a conversation may carry, summed over message contents. **Characters, not tokens** — a deliberate proxy, since counting tokens means a per-model tokenizer the harness does not carry. Roughly 50k tokens of English; code runs denser. Must be at least `1`. |
  | `PIPELINE_MAX_WORKERS` | No | `32` | Threads in the dedicated pipeline executor. The whole pipeline runs here rather than on the server's shared pool, which is what keeps `/health` and other queries answering while long upstream calls are in flight. Sizing it below the number of concurrent sends queues them; it does not drop them. Must be at least `1`. |
  ```
- **Mirror**: `README.md:396` (default, then the consequence, then what an invalid value does)
- **Validate**: `grep -n "OPENROUTER_TIMEOUT_SECONDS\|CONTEXT_MAX_MESSAGES\|CONTEXT_MAX_CHARACTERS\|PIPELINE_MAX_WORKERS" README.md` → 4 table rows (plus the prose mentions from Tasks 2 and 4); the sentence at `:400` ("read once at startup … requires a restart") still follows the table and needs no change.

### Task 7: AC 4 — `.env.example` gains the PRD-010 group

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: insert after `CHAT_SESSION_LIMIT=50` (`:64`), before the Reports block. ASCII only, comment directly above each assignment (`tests/test_config.py:68`'s pattern), and in `Settings` declaration order:
  ```
  # Multi-turn pipeline (PRD-010)

  # Seconds to wait for the upstream provider before giving up; must be > 0.
  # Replaces the old hard-coded 30s, too short for a long conversation
  OPENROUTER_TIMEOUT_SECONDS=120.0

  # Most messages one conversation may send to the pipeline, new turn included;
  # checked first, and the only limit named when both are exceeded (min 1)
  CONTEXT_MAX_MESSAGES=100

  # Most characters across message contents in one conversation - characters,
  # not tokens, which is a deliberate proxy for ~50k tokens of English (min 1)
  CONTEXT_MAX_CHARACTERS=200000

  # Threads in the dedicated pipeline executor; keeps /health and other queries
  # answering while long upstream calls are in flight (min 1)
  PIPELINE_MAX_WORKERS=32
  ```
- **Mirror**: `.env.example:56-64` (the chat group: consequence-stating comment block, then `VAR=default`)
- **Validate**:
  ```bash
  python - <<'PY'
  import re, pathlib
  t = pathlib.Path(".env.example").read_text(encoding="utf-8")
  for v in ("OPENROUTER_TIMEOUT_SECONDS","CONTEXT_MAX_MESSAGES","CONTEXT_MAX_CHARACTERS","PIPELINE_MAX_WORKERS"):
      assert re.search(rf"(?m)^#.+\n{v}=", t), v
  assert t.isascii()
  print("ok")
  PY
  ```
  and confirm each documented default equals the `app/config.py` field (`120.0`, `100`, `200000`, `32`).

### Task 8: `.env.example` guard tests (supporting edit)

- **File**: `tests/test_config.py`
- **Action**: UPDATE
- **Implement**: append to the PRD-010 block (after `test_settings_construct_without_the_multiturn_pipeline_vars`, `:433-449`), mirroring the chat pair exactly:
  ```python
  def test_env_example_documents_every_multiturn_pipeline_var_with_a_comment():
      text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

      for var in (
          "OPENROUTER_TIMEOUT_SECONDS",
          "CONTEXT_MAX_MESSAGES",
          "CONTEXT_MAX_CHARACTERS",
          "PIPELINE_MAX_WORKERS",
      ):
          assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


  def test_env_example_multiturn_pipeline_vars_appear_in_settings_field_order():
      text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
      declared_order = [
          "OPENROUTER_TIMEOUT_SECONDS",
          "CONTEXT_MAX_MESSAGES",
          "CONTEXT_MAX_CHARACTERS",
          "PIPELINE_MAX_WORKERS",
      ]

      positions = [text.index(f"{var}=") for var in declared_order]

      assert positions == sorted(positions)
  ```
- **Why this is in scope despite the story listing no test work**: every other settings group in `tests/test_config.py` carries this pair (RBAC `:64,71`; Turso `:224,238`; chat `:334,341`). The PRD-010 group lacks it only because STORY-002 deferred `.env.example` to this story. Adding the group without its guard leaves the epic's four settings as the only ones a future edit can silently drop. **Record it under *Deviations* in the report** as a supporting edit beyond the listed ACs.
- **Mirror**: `tests/test_config.py:334-347`
- **Validate**: `pytest tests/test_config.py -q` → green, including the two new tests. Then temporarily delete one comment line in `.env.example` and confirm the first test fails (proving it bites), and restore it.

### Task 9: AC 5 — verify the pre-PRD, the track overview and `app/config.py`

- **Files**: `pre-prds/PRE-PRD-010-multi-turn-pipeline.md`, `pre-prds/README.md`, `app/config.py`
- **Action**: VERIFY (no edits)
- **Implement**: run and capture verbatim for the report:
  ```bash
  sed -n '1,12p' pre-prds/PRE-PRD-010-multi-turn-pipeline.md      # status: promoted, prd: .agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md
  test -f .agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md && echo "prd path resolves"
  git ls-files pre-prds                                            # all nine files tracked -- no staging gate
  git diff --stat main -- app/config.py                            # the four settings landed in STORY-002; no change here
  ```
  In the report state explicitly: the brief was already `promoted` with its `prd:` set at PRD creation, this story changed neither; `pre-prds/README.md`'s table has **no status column** (Order / Brief / Target PRD / Est. stories / Depends on), so F9's "track overview marks PRE-PRD-010 promoted" is satisfied by the brief's own frontmatter, per the instruction at `pre-prds/README.md:5`; and `app/config.py` is unchanged by this story, with its four defaults matching the README table row for row.
- **Validate**: the frontmatter shows `status: promoted` and the `prd:` path; `git diff --stat main -- app/config.py` prints nothing

### Task 10: AC 5 — every anchor and relative link resolves

- **File**: `<scratchpad>/check_readme_links.py`
- **Action**: CREATE (scratchpad only; never committed)
- **Implement**: a script that
  1. parses `README.md` headings outside fenced code blocks and builds GitHub slugs (lowercase → drop every character not in `[a-z0-9 _-]` → spaces to `-`, de-duplicating with `-1`, `-2` suffixes);
  2. checks every `](#anchor)` in `README.md` against those slugs;
  3. for every non-`http(s)` `](path#anchor)` link, checks the file exists from the repo root and, where an anchor is present, that the target file has a heading with that slug;
  4. prints each failure and exits non-zero if any fail.

  **Self-check first**: run it against `git show HEAD:README.md`. Every existing link must pass, `#quickstart--local` and `#persistence--deployment` included — that proves the slug function before it is trusted on the new anchors.
- **Must cover**: `#multi-turn-context` (×4 in-repo: README `:285`, the roadmap item, the OpenAI bullet, plus the new Features row — and note `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md` links it from outside), `#post-query--blocked-context-limit` (new, from Task 2 — confirm the slug the script derives from `### \`POST /query\` — blocked (context limit)` matches the link exactly; the em dash drops and the backticks drop, giving `post-query--blocked-context-limit`), `#duplicate-detection-scope`, `#chat-ui`.
- **If the derived slug differs from the link written in Task 2**, fix the *link* to match the script's slug — never rename the heading, since Task 2's heading style has to match the five API headings around it.
- **Validate**: `python <scratchpad>/check_readme_links.py` → 0 failures, on both `HEAD:README.md` and the working copy

### Task 11: Full suite, change audit, commit

- **Action**: VERIFY + COMMIT
- **Implement**:
  1. Confirm the libSQL dev server is up (`docker ps --filter name=harness-libsql-dev`). On mass fixture errors, restart the container and re-run — do not bisect; the dev server degrades under repeated suites.
  2. `pytest tests/ -q` → green. `tests/test_config.py` must pass with the two new tests, and nothing else should move.
  3. `git diff --stat` → exactly `README.md`, `.env.example`, `tests/test_config.py`.
  4. `git diff README.md | grep -c "^[-+]"` and read the diff once end to end: no roadmap item left unchecked, no second `### Multi-turn context`, no stray `No multi-turn context`.
  5. Commit on `epic/PRD-010-multi-turn-pipeline`:
     ```
     docs(readme): STORY-018 multi-turn context shipped, its limits, and the four pipeline settings
     ```
     with the session's attribution trailer.
- **Validate**: suite green; the diff is the three files above and nothing else

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Moving the `### Multi-turn context` heading breaks four inbound links** (three in README, one in PRD-009's PRD). | The heading text is kept byte-identical, so the anchor is unchanged. Task 10's script checks all of them, and the PRD-009 link is checked from the other side (`../../../README.md#multi-turn-context`). |
| 2 | **The new API heading's slug is guessed wrong** — backticks, an em dash and parentheses in one heading. | Task 10 derives the slug mechanically and Task 2's link is corrected to match, never the reverse. The slug function is self-checked against the pre-edit README first. |
| 3 | **A latency number is misquoted.** 926 ms is added p50; 978 ms is the multi-turn arm; 952 ms is redaction alone. | Task 2's copy states "added per send" explicitly with both percentiles and names the script. The figures come from STORY-015 report Run 2 verbatim, and the report is the citation of record. |
| 4 | **The README overstates concurrency.** STORY-014 proved responsiveness under a blocked upstream, not throughput or per-user fairness. | Task 2's wording is scoped to what the tests assert, including the queueing case at `PIPELINE_MAX_WORKERS=10`, and names the test file so a reader can check. |
| 5 | **PRD-014 reads as shipped.** The *OpenAI-compatible endpoint* section is one screen from the new shipped content. | Task 12 (below) touches only the two sentences that describe internals, keeps "Everything below this line is intended direction", and adds no new claim about the endpoint. |
| 6 | **`.env.example` breaks `tests/test_config.py`** via a non-ASCII character or a blank line between comment and assignment. | Task 7's validator asserts both the `^#.+\n{var}=` pattern and `str.isascii()`; Task 8 makes the guard permanent. |
| 7 | **The duplicate refinement is stated as a bug.** "Two new chats with the same first message are a duplicate" reads as a defect unless framed. | Task 4's bullet states it as designed behaviour with the reason (both conversations are one turn), and contrasts it with the case that does work. |
| 8 | **Suite flakes from the libSQL dev server.** | Task 11 step 1: restart the container on mass fixture errors rather than bisecting. |

---

### Task 12: Technical Note — the *OpenAI-compatible endpoint* section

- **File**: `README.md`
- **Action**: UPDATE (two sentences only)
- **Implement**:
  - In the intro paragraph (`:675`), after "so tools that already speak it … can be pointed at the harness by changing one base URL", the translation-layer paragraph (`:681`) says it "maps the `messages` array onto the existing … flow". Add one sentence at the end of that paragraph:
    ```
    Half of that is now built: the pipeline already takes a `messages` list, redacts every turn and keys the duplicate check over the conversation — see [Multi-turn context](#multi-turn-context). What does not exist is the HTTP ingress and the trust model for `system` and `assistant` turns a caller supplies, which is what this section is still about.
    ```
  - In the answered dedup bullet (`:687`), the trailing "See [Multi-turn context](#multi-turn-context)" still resolves after the move; leave the bullet otherwise unchanged.
  - **Do not** change the "Everything below this line is **intended direction, not current behavior**" line (`:663`), the section heading, or the two open design questions.
- **Mirror**: `README.md:687` (the `**Answered:**` pattern — state what is settled, keep what is open visibly open)
- **Validate**: `sed -n '/^### OpenAI-compatible endpoint/,/^### MCP servers/p' README.md | grep -n "Half of that is now built"` → one hit; `git diff README.md | grep "^[-+].*intended direction"` → prints nothing

*(Task 12 runs with Tasks 1–6; it is listed last because it is the only edit driven by a Technical Note rather than an AC.)*

---

## End-to-End Tests

- [ ] Render `README.md` (VS Code Markdown preview, or the branch view on GitHub). The new Features row, the moved *Multi-turn context* section, the new API block and the four table rows all display correctly; both tables keep their column alignment.
- [ ] In the rendered preview, click every new or changed link: *Multi-turn context* from the Features row, from the Chat UI limitation, from the roadmap *Shipped* item, from the OpenAI paragraph and from the API block; *Duplicate detection scope* from the new limitation bullet; the context-limit API link from the *Multi-turn context* section. Each lands on the right heading.
- [ ] `python <scratchpad>/check_readme_links.py` → 0 failures (and passes on `HEAD:README.md` as the self-check)
- [ ] `grep -n "No multi-turn context" README.md` → no hits
- [ ] `grep -c "^### Multi-turn context" README.md` → `1`, above `## Requirements`
- [ ] `grep -n "^- \[ \] \[Multi-turn" README.md` → no hits
- [ ] `pytest tests/test_config.py -q` → green, with the two new tests collected
- [ ] `pytest tests/ -q` → green
- [ ] `git diff --stat` → `README.md`, `.env.example`, `tests/test_config.py` only

---

## Validation

```bash
python "<scratchpad>/check_readme_links.py"
grep -c "^### Multi-turn context" README.md                     # 1
grep -n "No multi-turn context\|^- \[ \] \[Multi-turn" README.md # nothing
grep -n "Conversation exceeds context limit" README.md          # 1
grep -n "OPENROUTER_TIMEOUT_SECONDS\|CONTEXT_MAX_MESSAGES\|CONTEXT_MAX_CHARACTERS\|PIPELINE_MAX_WORKERS" README.md .env.example
sed -n '1,12p' pre-prds/PRE-PRD-010-multi-turn-pipeline.md      # status: promoted
git diff --stat main -- app/config.py                            # nothing
pytest tests/test_config.py -q
pytest tests/ -q
git diff --stat                                                  # three files
```

---

## Acceptance Criteria

(Copied from story `STORY-018`)

- [ ] Given [README.md](../../../README.md), when read, then *Multi-turn context* moves from the roadmap (the unchecked item and the "intended direction" section) to shipped behaviour describing: history comes only from answered exchanges; history is always redacted; the oldest exchanges are dropped when a chat exceeds the limits, with a note on the reply; the pipeline refuses oversized conversations; `CHAT_HISTORY_ENABLED=false` keeps single-turn.
- [ ] Given the *Limitations* section, when read, then "No multi-turn context" is removed, and it states: limits are characters, not tokens; patterns inspect only the newest user turn (provisional until PRD-011); PII audit fields describe the new turn and output only (D7); the first send of two new chats with the same text within 24 h is still a duplicate; redacted history can make answers less precise.
- [ ] Given `POST /query` documentation, when read, then the context-limit `BLOCKED` body is shown, with the note that it is the only new outcome, and the configuration table lists `OPENROUTER_TIMEOUT_SECONDS`, `CONTEXT_MAX_MESSAGES`, `CONTEXT_MAX_CHARACTERS` and `PIPELINE_MAX_WORKERS` with defaults and purpose.
- [ ] Given [.env.example](../../../.env.example), when read, then the four settings appear with their defaults and one-line comments, in a `# Multi-turn pipeline (PRD-010)` group.
- [ ] Given [pre-prds/PRE-PRD-010-multi-turn-pipeline.md](../../../pre-prds/PRE-PRD-010-multi-turn-pipeline.md), when read, then `status: promoted` and `prd:` point at this PRD (already set at PRD creation; verify). Every new or changed README anchor link resolves.
- [ ] All tasks completed
- [ ] STORY-015 latency numbers recorded where the README discusses cost; STORY-014's result where it discusses the executor
- [ ] PRD-014 is not described as shipped
- [ ] No production code changed (`app/`, `chat_ui/` untouched)
- [ ] Full suite green
- [ ] Follows existing README patterns (voice, anchors, cited tests)
