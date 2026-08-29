---
story: STORY-018
prd: PRD-005
slug: rbac-documentation
title: README, .env.example, and roadmap updates for RBAC
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-29
---

# Plan: README, `.env.example`, and roadmap updates for RBAC

## Summary

PRD-005 shipped across STORY-001…STORY-017 (all `done`, `depends_on` satisfied), but `README.md` still describes the pre-RBAC system: the Features table has no authentication row, the Environment Variables table lists none of `RBAC_ENABLED` / `RBAC_DEFAULT_ROLE` / `RBAC_ROLES_FILE` / `MODEL_ALLOWLIST`, the API Reference's `POST /query` example carries no `Authorization` header and neither the `401` nor the `403` case is documented, `GET /audit`'s example entry is missing the `role`/`denied_permission` fields STORY-015 added, the Chat UI section still describes a free-text `user_id` prompt when `chat_ui/chat_ui/state.py`'s `login()` now verifies a bearer token, the Roadmap still lists RBAC under Planned, and Troubleshooting has no entry for `RbacNotBootstrappedError` or for the new `401` vs `403` split. Separately, `RBAC_ENABLED` defaults to `true` (`app/config.py:17`) and STORY-016's fail-fast guard means the documented Quickstart — as currently written — boots straight into a startup crash, because no user is ever seeded before `python app.py` runs.

One correction to the story's own scope assumption: `.env.example` **already** carries all four RBAC vars (`RBAC_ENABLED`, `RBAC_DEFAULT_ROLE`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST` — commit `c2aca34`, STORY-005) and matches `Settings` field-for-field today. AC6 is satisfied by prior work; Task 3 below verifies this rather than editing a file that needs no change. This story is therefore effectively **`README.md`-only**, mirroring PRD-003's STORY-012 in shape (doc-only, zero source changes) but not in file count.

## User Story

As an operator
I want README and `.env.example` to document authentication, roles, and the bootstrap procedure
So that a deployment can be upgraded without reading the source

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-018-rbac-documentation.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md` — §9 (Security & Configuration), §12 (Phase 4), §13

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (documentation) |
| Complexity | LOW |
| Systems Affected | `README.md` — no application code, no tests, no `.env.example` change expected |
| Story | STORY-018 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains only `frontend-design` (unrelated — this is prose documentation, not UI work). `skills: []` in the story frontmatter confirms this.

`chat_ui/AGENTS.md` mandates the Reflex skills (`reflex-docs`, `setup-python-env`, `reflex-process-management`) before writing or editing any Reflex code. This story edits no Reflex code — it only edits prose in `README.md` that *describes* `chat_ui/chat_ui/state.py`'s already-shipped `login()`/`send()` behavior — so that gate does not apply, exactly as recorded for PRD-003's STORY-012 (`.agents/plans/PRD-003-pii-redaction/completed/STORY-012-readme-env-docs-rollout.plan.md:46`).

---

## Dependency Check

| Dependency | Status | Evidence |
|---|---|---|
| STORY-016 (fail-fast startup guard) | ✅ done | commit `0580a98`, report present, `check_bootstrap()` shipped in `app/services/authz.py` |
| STORY-017 (RBAC test suite) | ✅ done | commit `0056d30`, report present, 410 tests passing |

Both satisfied — no blockers. This is the last story of PRD-005 (`blocks: []`); after it, all 18 stories are `done`.

**Pre-existing uncommitted state**: `git status` shows `README.md` modified in the working tree (not yet committed). Reading the diff shows this is an in-progress restructuring of the Roadmap section into `### Shipped` / `### Planned` subsections plus three new "intended direction" sections (OpenAI-compatible endpoint, MCP servers and agent skills, Action policy rules) — content that already exists in the file as read by this plan. This plan's Roadmap edits (Task 7) build on top of that existing working-tree state; it is not reverted or discarded.

---

## Patterns to Follow

### README Features — capability in bold, one-sentence description, deliberate limits stated inline

```markdown
// SOURCE: README.md:117-119
| **PII redaction** | [Microsoft Presidio](https://microsoft.github.io/presidio/) masks personal data ... Masking never blocks a request, and the audit log keeps the raw text. English-only in this release. |
| **Full audit logging** | Every request — success or blocked — writes one row to SQLite: ... IP addresses and geolocation are never captured. |
```

### README Environment Variables — 4-column table, backticked defaults, full-sentence descriptions

```markdown
// SOURCE: README.md:198-209
| Variable | Required | Default | Description |
|---|---|---|---|
| `ADMIN_TOKEN` | Yes | — | Shared-secret bearer token required to call `/audit` and `/stats`. |
| `PII_REDACTION_ENABLED` | No | `true` | Master switch for PII redaction on prompts and responses. ... |
```

### `.env.example` values to mirror verbatim (already shipped — verification source only)

```bash
# SOURCE: .env.example:13-27 (committed c2aca34, STORY-005)
ADMIN_TOKEN=change-me
RBAC_ENABLED=true
RBAC_DEFAULT_ROLE=user
RBAC_ROLES_FILE=
MODEL_ALLOWLIST=gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet
```

```python
# SOURCE: app/config.py:17-20 — the Settings fields these vars must match field-for-field
RBAC_ENABLED: bool = True
RBAC_DEFAULT_ROLE: str = "user"
RBAC_ROLES_FILE: str = ""
MODEL_ALLOWLIST: str = "gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet"
```

### Shipped response/error shapes these docs must mirror (not the PRD's pre-implementation draft)

```python
# SOURCE: app/middleware/auth.py:14-31 — actual 401/403 text
raise HTTPException(status_code=401, detail="Invalid or missing credential")
raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
```

```python
# SOURCE: app/routers/query.py:20-24 — user_id/identity mismatch
raise HTTPException(status_code=403, detail="user_id does not match the authenticated identity")
```

```python
# SOURCE: app/services/query_pipeline.py:31-67 — in-pipeline BLOCKED shape (200, not 403)
QueryBlockedForbiddenResponse(reason="Missing required permission", required_permission=exc.permission)
QueryBlockedForbiddenResponse(reason="Model not permitted for this role", required_permission=f"query:model:{model}")
```

```python
# SOURCE: app/services/authz.py:119-123 — the exact fail-fast guard message
"RBAC_ENABLED=true but no active users exist. Bootstrap one with: "
"python scripts/manage_users.py create-user --user-id <id> --role <admin|auditor|user>"
```

```python
# SOURCE: app/models/schemas.py:54-67 — AuditQueryEntry now carries role/denied_permission
class AuditQueryEntry(BaseModel):
    ...
    role: Optional[str] = None
    denied_permission: Optional[str] = None
```

```
# SOURCE: tests/test_rbac.py:104-127, 176-241 — proven request/response pairs
POST /query, Authorization: Bearer <auditor-token>, no query:submit
  -> 403 {"detail": "Permission denied: query:submit"}
POST /query, Authorization: Bearer <user-token>, openrouter_api_key set, no query:byok
  -> 200 {"status": "BLOCKED", "reason": "Missing required permission", "required_permission": "query:byok"}
POST /query, Authorization: Bearer <user-token>, model outside MODEL_ALLOWLIST
  -> 200 {"status": "BLOCKED", "reason": "Model not permitted for this role", "required_permission": "query:model:<model>"}
```

These strings were measured against the real endpoints by STORY-017 — reuse them verbatim rather than inventing new ones.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | Features row, Requirements/Quickstarts (bootstrap step), Solution + Architecture (optional), Chat UI section, Environment Variables (4 rows + `ADMIN_TOKEN` description), API Reference (3 endpoints), Troubleshooting (401/403/bootstrap), Roadmap (RBAC → Shipped, Action-policy cross-reference) |
| `.env.example` | VERIFY ONLY, NO CHANGE | Already carries all four RBAC vars, committed by STORY-005, matches `Settings` field-for-field |
| `app/**`, `chat_ui/**`, `tests/**`, `Dockerfile`, `docker-compose.yml` | NO CHANGE | Story is explicitly doc-only ("no source changes") |

---

## Design Notes (decisions worth stating up front)

1. **`.env.example` needs no edit — Task 3 is a verification task, not an implementation task.** STORY-005 already committed all four RBAC vars in the correct comment style (`.env.example:13-27`). Re-editing a file that already satisfies its AC would be unnecessary churn; Task 3 instead runs the same `Settings(_env_file=...)` parse check PRD-003's STORY-012 used, so the "matches field for field" claim in AC6 is provably true rather than assumed.

2. **The Quickstart is currently broken by STORY-016's own fail-fast guard and must gain a bootstrap step, even though no AC names "Quickstart" directly.** `RBAC_ENABLED` defaults to `true` (`app/config.py:17`); `authz.check_bootstrap()` raises `RbacNotBootstrappedError` at startup when zero active users exist, and `ADMIN_TOKEN` alone does not satisfy it (`app/services/authz.py:108-123`, STORY-016 AC5). Following today's README Quickstart verbatim — `pip install` → `cp .env.example .env` → `python app.py` — now crashes on first boot. This is the same category of gap PRD-003's STORY-012 plan called out for the spaCy model download (Design Note 5 there): the story's Technical Notes explicitly ask for "the one-time bootstrap sequence," and a Quickstart that doesn't boot is a documentation defect a reader hits immediately. Task 10 adds the `manage_users.py create-user` step to both Quickstarts.

3. **Document the shipped shape, not the PRD's `GET /audit` draft.** PRD.md:268-278 shows an audit entry without `prompt_hash`, `was_duplicate_blocked`, `suspicious_pattern_detected`, or `device` — fields the real endpoint has carried since PRD-001/PRD-003. The README's existing example already has those; Task 5 only adds the two fields STORY-015 introduced (`role`, `denied_permission`), onto the existing example, not a PRD-shaped rewrite.

4. **`query:submit` is enforced twice, and the README should say so once, briefly.** `POST /query` denies missing `query:submit` at the router via `Depends(require_permission(...))` — a `403`, before `run_query()` is ever called (`app/routers/query.py:16-18`). The chat UI has no router layer, so its only enforcement of `query:submit` is `run_query()`'s own step-0 check, which returns a `200 BLOCKED` bubble instead (`app/services/query_pipeline.py:53-56`). This is a real, tested asymmetry (STORY-017's report, "documented audit asymmetry"), not a bug. The PRD's own Section 9 table already documents `query:submit` denial as `403` — that stays the primary documented behavior for `POST /query`; Task 4 adds one sentence noting the chat UI surfaces the identical *decision* as an in-thread bubble rather than a session-level error, which is the reader-facing consequence that actually matters.

5. **The Solution one-liner and Architecture diagram updates (Task 11) are additive and independently droppable**, exactly as PRD-003's STORY-012 Design Note 3 treated the same category of edit. No AC names them; they exist only so the diagram doesn't keep asserting a request pipeline with no authentication step in it. If alignment proves fiddly during implementation, this task alone can be skipped without failing any AC.

6. **The `login_gate()` component (`chat_ui/chat_ui/components/shell.py:193-198`) already uses a password-type token input, not a `user_id` text field** — the README's Chat UI section describing "a plain text field" for `user_id` is stale from PRD-002/PRD-003 and must be rewritten to match `state.py`'s `login()` (token → `resolve()` → `Identity`, `_token` held only in a backend-only Reflex var). Task 9 rewrites this section from the shipped code, not from memory of the old flow.

---

## Tasks

Execute in order. Each task is atomic + verifiable. Every task edits `README.md` unless stated otherwise; none touches application code.

### Task 1: Add an Authentication row to the Features table

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Insert one row after **Chat UI** (README.md:114) and before **Duplicate blocking** (README.md:115) — placing it first, matching the pipeline order (identity/authorization runs before the duplicate check):
  ```markdown
  | **Role-based access control** | Every request is resolved to a verified `Identity` from a per-user bearer token — no self-declared `user_id` is trusted. Three fixed roles (`admin`, `auditor`, `user`) each hold an explicit permission set; deny-by-default for any unmapped role or permission. `ADMIN_TOKEN` remains a break-glass admin credential, not the primary auth mechanism. |
  ```
- **Mirror**: README.md:117 (the PII redaction row) — bold capability, single-sentence-style description, deliberate scope note inline.
- **Validate**: `grep -n "Role-based access control" README.md` shows one hit inside the Features table.

### Task 2: Environment Variables — four RBAC rows + updated `ADMIN_TOKEN` description

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Two edits (AC2):
  1. Update the `ADMIN_TOKEN` row (README.md:201) description to reflect its new role:
     ```markdown
     | `ADMIN_TOKEN` | Yes | — | Break-glass bearer token that always resolves to the `admin` role, independent of the `users` table. Not the primary auth mechanism — issue individual tokens with `scripts/manage_users.py` instead. |
     ```
  2. Insert four rows after `LOG_LEVEL` (README.md:205) and before `PII_REDACTION_ENABLED` (README.md:206), values copied from `app/config.py:17-20`:
     ```markdown
     | `RBAC_ENABLED` | No | `true` | Deny-by-default authorization enforcement. `false` preserves exact pre-RBAC (PRD-001) behavior — a documented migration escape hatch, not a normal operating mode. |
     | `RBAC_DEFAULT_ROLE` | No | `user` | Role assigned by `scripts/manage_users.py create-user` when `--role` is omitted. |
     | `RBAC_ROLES_FILE` | No | — (empty) | Optional path to a JSON role→permission matrix overriding the built-in default. A malformed file or an unrecognized permission fails startup rather than silently falling back. |
     | `MODEL_ALLOWLIST` | No | `gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet` | Comma-separated models a `user`-role caller may request. Validated server-side; `admin` bypasses this list entirely. |
     ```
- **Mirror**: README.md:198-209 — 4-column layout, backticked defaults, full-sentence descriptions; `README.md:206-209`'s PII row group for how a feature's whole var group is appended together.
- **Validate**: Every default in the new rows matches `app/config.py:17-20` character-for-character (Task 12 automates this).

### Task 3: Verify `.env.example` matches `Settings` field-for-field (AC6)

- **File**: none — verification only
- **Action**: VERIFY
- **Implement**: Confirm `.env.example:13-27` (`ADMIN_TOKEN`, `RBAC_ENABLED`, `RBAC_DEFAULT_ROLE`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST`) already exists with the same comment-line-then-var rhythm as the rest of the file, and that every RBAC/PII/base var in `Settings` (`app/config.py:7-25`) has a corresponding line. Do not edit the file unless this check fails.
- **Mirror**: `.env.example:1-43` (full file, as read in this plan).
- **Validate**: `python -c "from app.config import Settings; s = Settings(_env_file='.env.example'); print(s.RBAC_ENABLED, s.RBAC_DEFAULT_ROLE, s.RBAC_ROLES_FILE, s.MODEL_ALLOWLIST, s.model_allowlist_list)"` parses without error and prints values identical to `app/config.py`'s defaults.

### Task 4: API Reference — `POST /query`: bearer auth, 401, 403, and policy-BLOCKED examples

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Four edits under the existing `POST /query` heading (README.md:219-263) (AC3):
  1. Add `-H "Authorization: Bearer $USER_TOKEN"` to the success `curl` example (README.md:221-225); follow the JSON fence with: `The token identifies the caller — the request body's user_id, if present, is accepted only for backward compatibility and must match the authenticated identity or the request is refused with 403 (\`user_id does not match the authenticated identity\`).`
  2. Add a new subsection `### POST /query — 401 (no or invalid credential)`:
     ```json
     {"detail": "Invalid or missing credential"}
     ```
     Follow with: `Missing header, unknown token, or a deactivated user all map to this same response — deliberately indistinguishable, so a caller cannot enumerate valid credentials.`
  3. Add a new subsection `### POST /query — 403 (authenticated, lacks query:submit)`:
     ```json
     {"detail": "Permission denied: query:submit"}
     ```
     Follow with: `The auditor role holds no query:submit permission by default, so it always gets this response from POST /query. In the chat UI, the identical decision renders as an in-thread bubble rather than a session error, because the browser ingress has no router layer to enforce it at.`
  4. Add a new subsection `### POST /query — 200, refused by policy` after the two existing BLOCKED examples (README.md:241-263):
     ```json
     {
       "status": "BLOCKED",
       "reason": "Model not permitted for this role",
       "required_permission": "query:model:claude-3-opus"
     }
     ```
     Follow with: `Model-allowlist and BYOK (openrouter_api_key) refusals return 200 with this shape, not 403 — the caller is authenticated and allowed to call the endpoint, but the content of the request is what's refused. This is the same rendering path as a duplicate or injection block.`
- **Mirror**: README.md:219-263 for structure; `app/middleware/auth.py:14-31`, `app/routers/query.py:20-24`, `app/services/query_pipeline.py:31-67` for exact text; `tests/test_rbac.py:104-127,176-241` for proven request/response pairs.
- **Validate**: Every JSON key/value in the new examples matches a real response captured by `tests/test_rbac.py` (Task 12).

### Task 5: API Reference — `GET /audit`: scoping, `role`/`denied_permission` fields

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Two edits to the existing `GET /audit` section (README.md:265-293) (AC3):
  1. Retitle the heading from `### GET /audit (admin token required)` to `### GET /audit (requires audit:read:all or audit:read:own)`.
  2. Add `"role": "user", "denied_permission": "query:byok"` to the example entry, after `"device"` (README.md:284).
  Follow the fence with: `audit:read:all returns every row; with only audit:read:own, the response contains solely the caller's rows and total reflects that scoped count. An identity holding neither permission gets 403 {"detail": "Permission denied: audit:read:own"} (the last permission attempted). role and denied_permission are populated on every row — null for rows written before this control existed or for a successful, non-denied query.`
- **Mirror**: `app/routers/admin.py:29-62` for the scoping decision order; `app/models/schemas.py:54-67` for the field names.
- **Validate**: Field set in the example matches `AuditQueryEntry` exactly (Task 12).

### Task 6: API Reference — `GET /stats`: permission requirement

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Retitle `### GET /stats (admin token required)` (README.md:295) to `### GET /stats (requires stats:read)`. Replace the trailing sentence at README.md:318 (`A request to /audit or /stats without a valid ADMIN_TOKEN bearer value returns 401 Unauthorized.`) with: `A missing or invalid credential on any endpoint returns 401. An authenticated identity that lacks the endpoint's required permission (e.g. a user role calling GET /stats) returns 403 with {"detail": "Permission denied: stats:read"}.` No change to the JSON example body — the shape is unchanged from today.
- **Mirror**: `app/routers/admin.py:65-69` (`require_permission(PERMISSION_STATS_READ)` dependency).
- **Validate**: `grep -n "stats:read" README.md` shows a hit in both the heading and the 403 sentence.

### Task 7: Roadmap — RBAC moves from Planned to Shipped; update Action-policy cross-reference

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Two edits (AC4), against the file's current (uncommitted, working-tree) Roadmap structure:
  1. Append `- [x] Role-based access control (RBAC)` to the end of the `### Shipped` list, after `- [x] PII redaction on input/output`. Remove `- [ ] Role-based access control (RBAC)` from the `### Planned` list entirely (not just unchecked — delete the line).
  2. In the **Action policy rules** section's closing paragraph (currently: `These rules are per-deployment configuration, which makes *Configurable, per-deployment pattern lists* a prerequisite for this work rather than an independent nice-to-have. RBAC is the natural pairing: the same DELETE may be denied for one role and allowed for another.`), rewrite the last sentence to reflect that RBAC is shipped, not planned: `RBAC, already shipped, is the natural pairing: the same DELETE can already be denied for one role and allowed for another via the role→permission matrix in app/services/authz.py — action policy rules would extend that same deny-by-default model from prompts to tool calls.`
- **Mirror**: README.md's existing `- [x]` items for style (no annotation, just the checked box).
- **Validate**: `grep -n "Role-based access control" README.md` → exactly one hit, under `### Shipped`, `- [x]`. `grep -n "Role-based access control" README.md` under `### Planned` → zero hits.

### Task 8: Troubleshooting — bootstrap failure, 401 vs 403

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Two edits (AC5):
  1. Replace the existing `**401 Unauthorized on /audit or /stats**` entry (README.md:360-361) — now stale, since 401 applies to `/query` too and is no longer ADMIN_TOKEN-specific — with two entries covering both status codes:
     ```markdown
     **`401 Unauthorized` on `/query`, `/audit`, or `/stats`**
     The `Authorization: Bearer <token>` header is missing, doesn't match any active user's token, or matches a deactivated user. Issue a token with `python scripts/manage_users.py create-user --user-id <id> --role <admin|auditor|user>`, or confirm `ADMIN_TOKEN` in `.env` matches exactly (it always works as break-glass).

     **`403 Forbidden` on `/query`, `/audit`, or `/stats`**
     The credential is valid, but the role lacks the permission that endpoint requires — for example, an `auditor` calling `/query`, or a `user` calling `/stats`. This is different from `401`: authentication succeeded, authorization did not. See the role→permission matrix in the Features table above, or `app/services/authz.py`.
     ```
  2. Add a new entry, placed before the two above (bootstrap failure happens first, at startup):
     ```markdown
     **`RbacNotBootstrappedError: RBAC_ENABLED=true but no active users exist` at startup**
     Bootstrap at least one user: `python scripts/manage_users.py create-user --user-id <id> --role admin`. This is required even when `ADMIN_TOKEN` is set — break-glass does not satisfy the bootstrap guard (`app/services/authz.py`'s `check_bootstrap()`). To migrate an existing deployment without bootstrapping immediately, set `RBAC_ENABLED=false`.
     ```
- **Mirror**: README.md:342-361 — bold error line, plain remedy line, blank line between entries.
- **Validate**: `sed -n '340,365p' README.md`; error text matches `app/services/authz.py:119-123` and `app/middleware/auth.py:19,28` exactly.

### Task 9: Chat UI section — replace the stale free-text `user_id` description with the real login flow

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Replace the **Session identity** paragraph (README.md:183) — which describes a plain-text `user_id` field, PRD-002/PRD-003-era behavior — with:
  ```markdown
  **Session identity** — on first load, the chat presents a login form asking for a bearer token (the same credential issued by `scripts/manage_users.py` or `ADMIN_TOKEN`), rendered as a password-style input. The token is held only in a backend-only Reflex var (`_token`, never serialized to the client) and is never cached as a role — every message re-resolves the identity, and therefore the role, from the database via the same `identity.resolve()` used by `POST /query`. An invalid or expired token shows an inline error on the login form and never reaches the chat.
  ```
  Also update the pipeline parenthetical at README.md:181 to prepend authorization: `(identity resolution → duplicate check → pattern check → PII redaction → OpenRouter call → audit log)`.
  In **Known limitations (MVP)** (README.md:187-192), remove the now-false bullet `- No login/auth beyond the user_id field — same trust model already used by POST /query.` and replace it with: `- A denied query (missing permission, disallowed model, or BYOK without query:byok) renders as an in-thread bubble, not a session error — the same rendering path as a duplicate or injection block.`
- **Mirror**: `chat_ui/chat_ui/state.py:24-43,71-97` (docstring + `login()`/`logout()`) and `chat_ui/chat_ui/components/shell.py:193-198` (`login_gate()`'s `type="password"` input) for what the shipped flow actually does.
- **Validate**: `sed -n '171,195p' README.md`; the claim is consistent with `state.py` (`_token` is a private, non-`rx.var` field; no role field exists anywhere on `ChatState`).

### Task 10: Requirements + both Quickstarts — bootstrap step

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Add the bootstrap step to both Quickstarts, since `RBAC_ENABLED` defaults to `true` and the app now fails to start without at least one active user (Design Note 2):
  1. **Quickstart — Local** (README.md:135-150) — insert after the `.env` edit line, before `python app.py`:
     ```bash
     python scripts/manage_users.py create-user --user-id admin --role admin
     # copy the printed token now -- it cannot be recovered later; this is
     # your bearer token for POST /query, /audit, and /stats
     python app.py
     ```
     Follow with one sentence: `Skipping this step makes the service fail at startup with RbacNotBootstrappedError (see Troubleshooting) — ADMIN_TOKEN alone is not sufficient, by design.`
  2. **Quickstart — Docker** (README.md:152-167) — insert the same `create-user` command after `docker-compose up -d --build`, run inside the container: `docker-compose run --rm harness-ai python scripts/manage_users.py create-user --user-id admin --role admin`, with the same one-line note about the guard.
- **Mirror**: README.md:135-150's fenced `bash` block + trailing prose sentence style (same pattern PRD-003's STORY-012 used for the `spacy download` step).
- **Validate**: On a machine with a fresh `harness_ai.db`, following Quickstart — Local verbatim yields a service that starts and `curl http://localhost:8000/health` returns `{"status":"ok"}` (Task 10 in End-to-End Tests below covers this; do not confuse with this table's Task 10).

### Task 11 (optional, independently droppable): Solution one-liner + Architecture diagram — add the identity/authorization step

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Two edits (no AC names this directly — see Design Note 5):
  1. Prepend to the pipeline one-liner (README.md:52-54): `identity resolution + authorization  →  duplicate check (24h)  →  ...` (keep the rest of the arrow chain unchanged). Extend the following sentence with one clause: `An unverified or unauthorized request never reaches the duplicate check at all.`
  2. In the Architecture box (README.md:62-105), add a step before `1. Validate request`:
     ```
     │  0. Resolve identity  │◄──── SQLite (users)
     │     + authorize       │
     ```
     Adjust the numbering of the existing steps 1-5 by one if renumbering is desired, or leave them as-is with the new step labeled `0.` — match whichever reads less disruptively once the box is edited. Preserve the existing box-drawing glyphs (`┌ ─ ┐ │ └ ┘ ▼ ◄`) and the 23-character interior column width exactly.
- **Mirror**: README.md:52-105; PRD.md:104-130's authoritative pipeline diagram (Section 6), which is the source this ASCII block simplifies.
- **Validate**: View the block in a fixed-width renderer — every border column aligns; no line exceeds the original block width. If alignment is fiddly, skip this task — no AC depends on it.

### Task 12: Cross-check every documented value against the code

- **File**: none — verification only
- **Action**: VERIFY
- **Implement**: Mechanical audit of what Tasks 1-11 wrote. For each item, the README statement must match the named source:
  | Documented item | Source of truth |
  |---|---|
  | 4 RBAC env var names + defaults | `app/config.py:17-20` |
  | `ADMIN_TOKEN` break-glass description | `app/services/identity.py:12-17,55-56` |
  | `401`/`403` text | `app/middleware/auth.py:19,28,36` |
  | `user_id` mismatch `403` text | `app/routers/query.py:20-24` |
  | `200 BLOCKED` policy shapes | `app/services/query_pipeline.py:31-67` |
  | `RbacNotBootstrappedError` message | `app/services/authz.py:100-123` |
  | `GET /audit` field set incl. `role`/`denied_permission` | `app/models/schemas.py:54-67`, `app/routers/admin.py:29-62` |
  | `GET /stats` permission gate | `app/routers/admin.py:65-69` |
  | Chat UI login flow | `chat_ui/chat_ui/state.py:24-97`, `chat_ui/chat_ui/components/shell.py:193-286` |
  | Three fixed roles + default matrix | `app/services/authz.py:10-45` |
  Also confirm: the Table of Contents (README.md:19-34) still matches every `##` heading (no section added or renamed); no internal anchor link broke; and `git diff --stat` lists **one file**, `README.md` (`.env.example` unchanged per Task 3's verification).
- **Mirror**: STORY-009's report §Scope Decision and PRD-003's STORY-012 Task 11 — the established precedent for a named-source cross-check before calling documentation done.
- **Validate**: `git diff --stat` → 1 file (`README.md`), 0 under `app/`, `tests/`, `chat_ui/`, `.env.example` unchanged. `python -m pytest -q` → 410 passed, byte-identical to the STORY-017 baseline (a doc-only change cannot move it).

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `git diff --stat` → `README.md` only; `.env.example` and every application/test file unmodified (story is doc-only)
- [ ] `python -m pytest -q` → 410 passed, unchanged from the STORY-017 baseline
- [ ] `python -c "from app.config import Settings; s=Settings(_env_file='.env.example'); print(s.RBAC_ENABLED, s.RBAC_DEFAULT_ROLE, s.RBAC_ROLES_FILE, s.MODEL_ALLOWLIST)"` → `True user  gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet`, identical to `app/config.py`'s defaults
- [ ] On a scratch copy with a fresh `harness_ai.db`: follow **Quickstart — Local** verbatim (including the new bootstrap step) → service starts, `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] In that same scratch setup, *skip* the `create-user` step → startup fails with `RbacNotBootstrappedError: RBAC_ENABLED=true but no active users exist. Bootstrap one with: python scripts/manage_users.py create-user ...`, matching the new Troubleshooting entry verbatim
- [ ] `curl -X POST http://localhost:8000/query -H "Authorization: Bearer <admin-token>" -H "Content-Type: application/json" -d '{"prompt": "hello"}'` → `200 SUCCESS`, matching the updated README example's shape
- [ ] `curl -X POST http://localhost:8000/query` with no `Authorization` header → `401 {"detail": "Invalid or missing credential"}`, matching the new README example verbatim
- [ ] `curl -X POST http://localhost:8000/query -H "Authorization: Bearer <auditor-token>"` → `403 {"detail": "Permission denied: query:submit"}`, matching the new README example verbatim
- [ ] `curl http://localhost:8000/audit -H "Authorization: Bearer <admin-token>"` → entries include `role` and `denied_permission` keys matching the updated README example
- [ ] `curl http://localhost:8000/stats -H "Authorization: Bearer <user-token>"` → `403 {"detail": "Permission denied: stats:read"}`, matching the updated README's 403 sentence
- [ ] `grep -n "Role-based access control" README.md` → one hit under `### Shipped` (`- [x]`), zero hits under `### Planned`
- [ ] Render `README.md` (GitHub preview or any Markdown viewer) → all tables have consistent column counts, all fences close, any edited ASCII diagram still aligns, and the Table of Contents links all resolve

---

## Validation

```bash
cd f:\AI\harness-ai

git diff --stat
python -m pytest -q

python -c "from app.config import Settings; s=Settings(_env_file='.env.example'); print(s.RBAC_ENABLED, s.RBAC_DEFAULT_ROLE, s.RBAC_ROLES_FILE, s.MODEL_ALLOWLIST)"

grep -n "Role-based access control" README.md
grep -n "RBAC_ENABLED\|RBAC_DEFAULT_ROLE\|RBAC_ROLES_FILE\|MODEL_ALLOWLIST" README.md
grep -n "RbacNotBootstrappedError\|Permission denied\|Invalid or missing credential" README.md

python scripts/manage_users.py create-user --user-id admin --role admin
python app.py &
curl http://localhost:8000/health
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"prompt": "hello"}'
```

---

## Acceptance Criteria

(Copied from story STORY-018)

- [ ] Given the README Features table, when read, then RBAC is listed alongside the existing capabilities — Task 1
- [ ] Given the Environment Variables section, when read, then every `RBAC_*` variable and `MODEL_ALLOWLIST` is documented with its default — Task 2
- [ ] Given the API Reference, when read, then the bearer-token requirement and the `401` / `403` / `200`-`BLOCKED` split are documented for `/query`, `/audit`, and `/stats` — Tasks 4, 5, 6
- [ ] Given the Roadmap, when read, then "Role-based access control (RBAC)" has moved from Planned to Shipped — Task 7
- [ ] Given Troubleshooting, when read, then it covers the unseeded-startup failure and the `401` vs `403` distinction — Task 8
- [ ] Given `.env.example`, when compared to `Settings`, then it matches field for field — Task 3 (already true; verified, not re-implemented)
- [ ] All tasks completed
- [ ] No source code changed — `git diff --stat` shows only `README.md`
- [ ] Full test suite still passes unchanged (410 passed)
- [ ] Follows existing patterns (README table/fence/troubleshooting styles, `.env.example` comment rhythm)
