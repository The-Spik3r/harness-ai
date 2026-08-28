---
id: PRD-005
slug: rbac
title: Role-Based Access Control (RBAC)
status: draft
base_branch: main
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
updated: 2026-08-28
---

## 1. Executive Summary

Harness IA intercepts every prompt/response pair and logs it, but it has no notion of *who* is making the request. `QueryRequest.user_id` is a plain string in the request body, self-declared by the caller and never verified; in the chat UI, `ChatState.submit_user_id()` accepts any non-empty text. The only secret in the system, `ADMIN_TOKEN`, is a shared bearer token that identifies a *role* rather than a *person* — it is not attributable, not revocable per user, and gates only `/audit` and `/stats`.

This PRD closes the "Role-based access control (RBAC)" item on the project roadmap. It does so in the only order that makes it meaningful: **authentication first, authorization second**. Roles layered on top of a self-declared `user_id` would be decorative — the caller would simply pick their own role. So the MVP introduces a local identity store (a `users` table with per-user bearer tokens), resolves every request to a verified `Identity`, and evaluates a **deny-by-default** permission check as step 0 of the shared query pipeline.

The critical architectural constraint is that this system has **two ingresses into the same pipeline**: `POST /query` (HTTP) and `ChatState.send()` in the Reflex UI, which calls `run_query(...)` in-process and never traverses FastAPI's dependency chain. An authorization check implemented as a `Depends(...)` on the router — the shape used today for `ADMIN_TOKEN` in `app/routers/admin.py` — would be bypassed entirely by the chat UI. The MVP therefore makes `Identity` a **required parameter of `run_query(...)`**, so that the enforcement point is structural: no caller can reach the pipeline without having first produced a verified identity. HTTP dependencies remain as an additional outer layer, not as the layer.

Scope is deliberately narrow, in keeping with PRD-001 and PRD-003: three fixed roles, a small permission set covering capabilities that already exist in the code, no external identity provider, no new runtime dependencies, and no change to duplicate detection, pattern detection, or PII redaction behavior.

## 2. Mission

Make "who is allowed to do what" a deployment decision enforced by the harness, rather than a claim the caller makes about itself.

Core principles:
- **Authentication before authorization**: a role attached to an unverified `user_id` is not a control. Identity is established from a credential the server can verify, or the request is rejected.
- **Deny by default**: an unmapped user, an unknown role, or an undeclared permission is a denial. Permissions are granted explicitly, never inferred.
- **One enforcement point, structurally enforced**: authorization lives in the shared pipeline, and the pipeline's signature makes it impossible to call without an identity. The HTTP layer adds defense in depth, it does not own the decision. This is the same lesson PRD-002 Risk 4 recorded when it extracted `run_query(...)` in the first place.
- **A denial is an audited event**: refusing a request is logged with the same rigor as serving one. The audit trail must show what was attempted, not only what succeeded — the principle already applied to duplicate and pattern blocks.
- **No new dependencies, no new services**: identity lives in the same SQLite file as the audit log, using only the standard library, consistent with PRD-001's portability principle.

## 3. Target Users

**Security/Compliance Admin** — Needs the audit trail to be attributable to real people rather than to self-reported strings, and needs to revoke one person's access without rotating a secret shared by everyone. Today `ADMIN_TOKEN` gives all-or-nothing access to `/audit` and `/stats`, which makes it impossible to grant read-only audit visibility to a compliance reviewer without also handing over every other privilege the token carries. Technical level: comfortable with REST APIs and env vars.

**End User (Employee)** — Interacts through the chat UI. Wants to log in once per session and use the harness; should not be able to grant themselves capabilities (an unlisted model, their own OpenRouter key) by editing a request. Technical level: non-technical to technical.

**Auditor / Compliance Reviewer** — Needs `/audit` and `/stats` but must not be able to submit queries or spend budget against the organization's OpenRouter key. This role does not exist today and cannot be expressed with a single shared token.

**Integrating Developer** — Wants a predictable authentication contract for `POST /query` (a standard bearer token), clear `401` vs `403` semantics, and no silent behavior changes to the checks the harness already performs.

## 4. MVP Scope

### In Scope
- [ ] `users` table in the existing SQLite database: `user_id`, `role`, `token_hash`, `active`, `created_at`
- [ ] Additive schema-migration mechanism for existing database files (does not exist on `main` today — `init_db()` is `CREATE TABLE IF NOT EXISTS` only)
- [ ] Per-user bearer tokens: generated with `secrets.token_urlsafe(32)`, stored only as a SHA-256 digest, never recoverable after issuance
- [ ] `Identity` value object (`user_id`, `role`) resolved from a verified credential — the single currency of authorization in the system
- [ ] `app/services/authz.py`: role→permission matrix, permission constants, `authorize(identity, permission)` raising `PermissionDenied`, deny-by-default
- [ ] Three fixed roles: `admin`, `auditor`, `user`
- [ ] `run_query(...)` gains a **required** `identity: Identity` parameter and performs the permission check as step 0, before the duplicate check
- [ ] `POST /query` authenticates via `Authorization: Bearer <user token>`; the body's `user_id` is no longer trusted as identity
- [ ] Chat UI: the free-text `user_id` prompt is replaced by a login form that verifies a credential; the role is re-resolved server-side on every `send()`, never read from a client-mutable state var
- [ ] Backend-side model allowlist per role — `QueryRequest.model` is validated server-side (today any string is accepted)
- [ ] `openrouter_api_key` in the request body becomes a privileged capability (`query:byok`), denied by default
- [ ] `/audit` scoping: `audit:read:all` returns every row; `audit:read:own` returns only the caller's rows
- [ ] `/stats` gated by `stats:read`
- [ ] `audit_logs` gains `role` and `denied_permission` columns; every denial writes a row
- [ ] New `QueryBlockedForbiddenResponse` member of the `QueryResponse` union, with an explicit branch in `ChatState.send()`
- [ ] `ADMIN_TOKEN` retained as a break-glass credential mapped to the `admin` role, so existing integrations and `tests/test_admin_auth.py` keep working
- [ ] Bootstrap CLI (`scripts/manage_users.py`) to create, list, deactivate users and issue tokens
- [ ] Role/permission matrix loadable from a versioned JSON file (`RBAC_ROLES_FILE`), with the built-in default matrix as the zero-config fallback

### Out of Scope
- [ ] External identity providers (OIDC/SAML/LDAP), SSO, refresh tokens, and token expiry — a local store only
- [ ] Human-chosen passwords (which would make a KDF such as argon2/bcrypt mandatory); MVP credentials are high-entropy random tokens only
- [ ] User-management HTTP endpoints (`POST /users`, etc.) — administration happens through the CLI in this MVP
- [ ] Multi-tenancy, groups, role hierarchies, per-user permission overrides, or custom roles beyond the three fixed ones
- [ ] Changing the scope of duplicate detection — `check_duplicate(prompt)` remains global across users (see Risk 3)
- [ ] Any change to pattern detection or PII redaction behavior
- [ ] Exposing raw `prompt_preview`/`response_preview` through `/audit` — those columns exist in the database but no endpoint returns them today, so there is nothing yet for a `pii:view_raw` permission to gate (see Section 13)
- [ ] Per-role rate limits, quotas, or budget caps
- [ ] Action-policy rules for tool calls (roadmap item; depends on this PRD, not delivered by it)

## 5. User Stories

1. **As a security admin**, I want every request to be attributable to a credential the server verified, so that the audit trail records who actually asked rather than what the caller typed into a `user_id` field.
   - Example: `POST /query` with `{"user_id": "ceo"}` and no `Authorization` header returns `401`, and no row is written attributing anything to `ceo`.

2. **As a security admin**, I want the same authorization decision applied whether a request arrives over HTTP or through the chat UI, so that the browser ingress is not a way around the control.
   - Example: a user whose role lacks `query:submit` gets the same denial from `POST /query` and from the chat input box, because both paths pass through the identical check inside `run_query(...)`.

3. **As a compliance reviewer**, I want read access to `/audit` and `/stats` without the ability to submit queries, so that reviewing traffic does not also grant the ability to generate it.
   - Example: the `auditor` role holds `audit:read:all` and `stats:read` but not `query:submit`; a query attempt returns `403`.

4. **As an end user**, I want to log in once per chat session with my own credential, so that my activity is attributed to me and can be revoked without disrupting anyone else.
   - Example: deactivating one user in the `users` table blocks that person's next request; every other user is unaffected — unlike rotating `ADMIN_TOKEN` today.

5. **As a security admin**, I want the model choice validated on the server against the caller's role, so that the allowlist is a real control rather than a frontend convenience.
   - Example: a `user`-role caller requesting an expensive model outside their role's allowlist is blocked before the OpenRouter call is made, and the attempt is logged.

6. **As a security admin**, I want a caller-supplied `openrouter_api_key` to be a privilege rather than a default, so that the harness cannot be used as a pass-through that bypasses the organization's own key and cost controls.
   - Example: a `user`-role request carrying `openrouter_api_key` is denied; the same request from an `admin` is allowed.

7. **As a compliance admin**, I want every denial recorded in the audit log with the role and the permission that was missing, so that "what was attempted and refused" is as visible as "what succeeded".
   - Example: a denied request writes a row with `role="user"`, `denied_permission="query:byok"`, and no call to OpenRouter.

8. **As an operator upgrading an existing deployment**, I want a clear, one-time bootstrap step rather than a silent behavior change, so that turning on RBAC never leaves the service either wide open or mysteriously broken.
   - Example: starting with `RBAC_ENABLED=true` and no users seeded fails fast at startup with an actionable message naming the bootstrap command.

## 6. Core Architecture & Patterns

```
  Chat UI (Reflex)                              POST /query
  ChatState.login()                             Authorization: Bearer <user token>
        │                                             │
        └───────────────┬─────────────────────────────┘
                        ▼
        ┌──────────────────────────────────┐
        │  identity.resolve(credential)    │  NEW
        │  token → SHA-256 → users lookup  │
        │  → Identity(user_id, role)       │  miss/inactive ⇒ 401
        └───────────────┬──────────────────┘
                        │ Identity  (required argument)
                        ▼
        ┌──────────────────────────────────┐
        │ 0. authorize(identity, perm)     │  NEW — deny by default
        │    · query:submit                │  ⇒ 403 / BLOCKED
        │    · model in role allowlist     │
        │    · query:byok if key supplied  │
        ├──────────────────────────────────┤
        │ 1. duplicate check (24h)         │  unchanged
        │ 2. pattern check (injection)     │  unchanged
        │ 3. PII redaction (prompt)        │  unchanged
        │ 4. OpenRouter call               │  unchanged
        │ 5. PII redaction (response)      │  unchanged
        │ 6. audit log write               │  + role, denied_permission
        └──────────────────────────────────┘
```

A denial short-circuits at step 0: OpenRouter is never called, and the denial is logged — the same shape the duplicate and pattern checks already use.

**New modules**
```
app/services/authz.py          # Identity, Role, PERMISSIONS, authorize(), PermissionDenied
                               # role→permission matrix loaded once at startup
app/services/identity.py       # credential → Identity resolution (token hash lookup, ADMIN_TOKEN break-glass)
scripts/manage_users.py        # bootstrap/admin CLI: create-user, issue-token, deactivate, list
```

**Changes to existing modules**
- `app/db/models.py` — `CREATE_USERS_TABLE`; `AUDIT_LOGS_ADDED_COLUMNS` mapping introduced for the additive migration; `AuditLog` gains `role` and `denied_permission`.
- `app/db/database.py` — `init_db()` applies missing columns via `ALTER TABLE ... ADD COLUMN` (every added column needs a non-NULL default, since SQLite rejects `ADD COLUMN NOT NULL` without one); user lookup/CRUD helpers; `list_audit_logs(limit, user_id=None)` gains scoping.
- `app/services/query_pipeline.py` — `run_query(...)` takes `identity: Identity` as a required parameter and performs step 0.
- `app/middleware/auth.py` — `require_identity` and `require_permission(p)` dependencies; `require_admin_token` reimplemented on top of them so the existing behavior and its tests are preserved.
- `app/routers/query.py` — resolves the identity from the header and passes it through; maps `PermissionDenied` to the response shape in Section 10.
- `app/routers/admin.py` — `/audit` and `/stats` move from `require_admin_token` to permission-based dependencies, with `/audit` scoped by `audit:read:all` vs `audit:read:own`.
- `app/models/schemas.py` — `QueryBlockedForbiddenResponse` joins the `QueryResponse` union; `QueryRequest.user_id` is deprecated as an identity input.
- `chat_ui/chat_ui/state.py` — `submit_user_id()` becomes `login()`; `send()` re-resolves the identity server-side and handles the new union member with an explicit branch.
- `chat_ui/chat_ui/components/chat.py` — the `user_id` prompt becomes a login form.

**Design patterns**
- **Enforcement by signature** — `Identity` is a required argument of `run_query(...)`, so the check cannot be skipped by adding a new caller. This is the answer to the two-ingress problem and the single most important structural decision in this PRD.
- **Value object** — `Identity` is an immutable dataclass produced only by `identity.resolve(...)`. Nothing else constructs one in production code.
- **Policy table over conditionals** — the role→permission matrix is data (a dict, overridable by JSON), not `if role == "admin"` branches scattered through the codebase. This is also the prerequisite shared with the roadmap's "configurable, per-deployment pattern lists".
- **Startup-loaded configuration** — the matrix is parsed once at startup, mirroring how PRD-003 loads the Presidio model.
- **Adapter/facade** — `authz.py` is the only module the pipeline imports for authorization decisions, keeping the storage details of identity out of the pipeline.

## 7. Tools/Features

| Feature | Detail |
|---|---|
| Verified identity | Bearer token → SHA-256 → `users` row. Inactive or unknown ⇒ `401`. `ADMIN_TOKEN` still resolves, to a synthetic `admin` identity. |
| Deny-by-default matrix | Unknown role, missing permission, or malformed matrix ⇒ denial. No implicit grants. |
| Pipeline step 0 | `authorize(...)` runs before the duplicate check, so a forbidden request never touches the dedup path or OpenRouter. |
| Server-side model allowlist | `QueryRequest.model` validated against the role's allowlist. `*` for `admin`. |
| BYOK as a privilege | A caller-supplied `openrouter_api_key` requires `query:byok`. |
| Scoped audit reads | `audit:read:all` ⇒ every row; `audit:read:own` ⇒ `WHERE user_id = ?`. |
| Denial auditing | `role` and `denied_permission` columns; one row per denial, `success=1` (the harness worked as designed), no OpenRouter call. |
| Break-glass | `ADMIN_TOKEN` preserved so existing deployments and `tests/test_admin_auth.py` are unaffected. |
| Bootstrap CLI | `python scripts/manage_users.py create-user --user-id x --role admin` prints the token once. |

**Default role→permission matrix**

| Permission | `admin` | `auditor` | `user` |
|---|:--:|:--:|:--:|
| `query:submit` | ✅ | ❌ | ✅ |
| `query:byok` | ✅ | ❌ | ❌ |
| `audit:read:all` | ✅ | ✅ | ❌ |
| `audit:read:own` | ✅ | ✅ | ✅ |
| `stats:read` | ✅ | ✅ | ❌ |
| Model allowlist | `*` | — | `MODEL_ALLOWLIST` |

## 8. Technology Stack

**Backend (no additions to PRD-001/PRD-003's stack)**
- `secrets` — token generation and `compare_digest` for constant-time comparison (already used in `app/middleware/auth.py`)
- `hashlib` — SHA-256 of the issued token
- `json` — role matrix file parsing
- `sqlite3` — the `users` table lives in the existing database file

**Why SHA-256 and not a KDF**: the credential is a 256-bit value generated by `secrets.token_urlsafe(32)`, not a human-chosen password, so it is not subject to dictionary or brute-force attack and a fast hash is appropriate. This holds **only** as long as tokens stay machine-generated. If human-chosen passwords are ever introduced (Section 13), argon2 or bcrypt becomes mandatory. `hash_prompt()` in `duplicate_checker.py` is not reused for credentials — the two concerns share an algorithm, not a purpose.

**Testing**
- `pytest` — role×permission matrix, deny-by-default, `401` vs `403` vs in-pipeline block, `/audit` scoping, migration against a pre-RBAC database file, and — critically — a test that exercises the **chat UI ingress**, not only the router.

**Deployment**
- No image or dependency changes. One new env-var group and a one-time bootstrap step.

## 9. Security & Configuration

**Authentication**
- `POST /query`, `/audit`, `/stats`: `Authorization: Bearer <token>`.
- Chat UI: the session credential is submitted through the login form, exchanged for a server-side identity, and **never stored in an `rx.var`** — Reflex state vars are serialized to the client, and events originating from the client can mutate them. `ChatState` holds the authenticated `user_id` only, and the role is re-resolved from the database inside `send()`. UI conditionals (`rx.cond`) that hide controls by role are cosmetic and are explicitly not treated as a control.

**HTTP semantics (explicit decision)**

The codebase currently mixes two conventions: `require_admin_token` raises `401`, while pipeline blocks return `200` with `status: "BLOCKED"`. This PRD fixes the split rather than letting it drift:

| Condition | Response |
|---|---|
| Missing/invalid/inactive credential | `401 Unauthorized` |
| Authenticated, but lacks the permission for the endpoint (`query:submit`, `audit:read:*`, `stats:read`) | `403 Forbidden` |
| Authenticated and allowed to call the endpoint, but the *content* of the request is refused by policy (model outside the role's allowlist, `openrouter_api_key` without `query:byok`) | `200` with `status: "BLOCKED"`, `reason`, `required_permission` |

The third row keeps the chat UI's rendering model intact: an in-thread bubble, exactly like a duplicate or an injection block. The first two rows are transport-level failures the UI surfaces as a session error, not as a chat message.

**Environment variables (additions)**
```bash
# RBAC
RBAC_ENABLED=true              # deny-by-default enforcement; see rollout note below
RBAC_DEFAULT_ROLE=user         # role assigned to users created without an explicit one
RBAC_ROLES_FILE=               # optional path to a JSON matrix; empty ⇒ built-in default
MODEL_ALLOWLIST=gpt-4,claude-3-sonnet,openai/gpt-4o,anthropic/claude-3.5-sonnet

# Retained from PRD-001 — now a break-glass credential mapped to the admin role
ADMIN_TOKEN=change-me
```

**Rollout / breaking change**: `RBAC_ENABLED` defaults to `true` (secure by default). If it is `true` and no active user exists, startup **fails fast** with a message naming the bootstrap command, rather than either denying every request opaquely or silently allowing them. `RBAC_ENABLED=false` is a documented escape hatch that preserves exact PRD-001 behavior for existing deployments during migration, and is the only supported way to run without identity.

**In scope for MVP security**: verified identity per request, deny-by-default authorization at a single structural choke point, per-user revocation, audited denials, server-side model and BYOK validation.

**Out of scope for MVP security**: token expiry/rotation policy, external IdPs, encryption at rest for the `users` table, rate limiting, and exposing raw audit previews (which remain unexposed by any endpoint).

## 10. API Specification

### `POST /query` — request
```http
POST /query
Authorization: Bearer <user token>
Content-Type: application/json

{"prompt": "...", "model": "gpt-4", "device": "laptop-01"}
```
`user_id` remains accepted for backward compatibility but is **ignored as an identity input**; the audited `user_id` always comes from the resolved credential. If present and different from the authenticated user, the request is refused with `403` rather than silently overridden.

### `POST /query` — 401 (no or invalid credential)
```json
{"detail": "Invalid or missing credential"}
```

### `POST /query` — 403 (authenticated, lacks `query:submit`)
```json
{"detail": "Permission denied: query:submit"}
```

### `POST /query` — 200, refused by policy
```json
{
  "status": "BLOCKED",
  "reason": "Model not permitted for this role",
  "required_permission": "query:model:anthropic/claude-3.5-sonnet"
}
```

### `GET /audit` — scoping
Requires `audit:read:all` or `audit:read:own`. With only `audit:read:own`, the response contains solely the caller's rows and `total` reflects that scoped count. Entries gain the acting role:
```json
{
  "audit_id": 42,
  "user_id": "ana",
  "role": "user",
  "denied_permission": "query:byok",
  "timestamp": "2026-08-28T12:00:00Z"
}
```

### `GET /stats`
Requires `stats:read`. No shape change beyond existing fields.

## 11. Success Criteria

**MVP definition of done**
- [ ] No request reaches OpenRouter without a server-verified identity when `RBAC_ENABLED=true`
- [ ] `run_query(...)` cannot be called without an `Identity` — enforced by its signature, verified by a test that both ingresses construct one
- [ ] The chat UI ingress is denied identically to the HTTP ingress for the same role, proven by a test exercising `ChatState.send()`
- [ ] Deny-by-default: an unknown role, an unmapped permission, or an inactive user is refused
- [ ] `QueryRequest.model` is validated server-side against the role's allowlist
- [ ] A caller-supplied `openrouter_api_key` without `query:byok` is refused before the OpenRouter call
- [ ] Every denial writes an audit row carrying `role` and `denied_permission`
- [ ] An existing pre-RBAC `harness_ai.db` migrates in place; historical rows keep their data and take column defaults
- [ ] `tests/test_admin_auth.py` passes unmodified — `ADMIN_TOKEN` still opens `/audit` and `/stats`
- [ ] Duplicate detection, pattern detection, and PII redaction behavior are unchanged, with their existing test suites passing unmodified

**Quality indicators**

| Metric | Target |
|---|---|
| Role×permission matrix coverage in tests | 100% of cells asserted, both grant and deny |
| Ingress parity | Every permission tested through both `POST /query` and `ChatState.send()` |
| Existing PRD-001/002/003 test suite | 100% pass, unmodified except where identity is now required |
| Added latency per request | One indexed SQLite lookup on `users`; matrix evaluation is in-memory |
| Credential exposure | Tokens unrecoverable after issuance; no token appears in logs, audit rows, or `rx.var`s |

## 12. Implementation Phases

**Phase 1 — Identity foundation** (~3 days)
- Goal: a verifiable identity exists and can be administered.
- Deliverables: additive-migration mechanism in `init_db()`; `users` table; `app/services/identity.py`; `scripts/manage_users.py`; `ADMIN_TOKEN` break-glass mapping.
- Validation: a seeded token resolves to an `Identity`; an unknown or deactivated token does not; a pre-RBAC database file migrates without data loss.

**Phase 2 — Authorization core** (~2 days)
- Goal: the decision exists, is data-driven, and defaults to deny.
- Deliverables: `app/services/authz.py` with permission constants, the default matrix, `RBAC_ROLES_FILE` loading at startup, and `authorize(...)`.
- Validation: full role×permission matrix under test; unknown role and unmapped permission both deny; a malformed matrix file fails fast at startup.

**Phase 3 — Pipeline and ingress wiring** (~3 days)
- Goal: both ingresses enforce the same decision, and denials are audited.
- Deliverables: `identity` as a required parameter of `run_query(...)` plus step 0; `QueryBlockedForbiddenResponse`; `role`/`denied_permission` audit columns; bearer auth on `POST /query`; chat UI login replacing the free-text prompt; explicit union branch in `ChatState.send()`.
- Validation: identical denial through both ingresses; a denial writes its row and never calls the mocked OpenRouter client.

**Phase 4 — Endpoint permissions, docs, rollout** (~2 days)
- Goal: admin endpoints move to permissions; the feature is documented and the roadmap checkbox flips.
- Deliverables: `/audit` scoping and `/stats` gating; README (Features, Environment Variables, API Reference, Roadmap, Troubleshooting) and `.env.example` updates; documented bootstrap and migration procedure.
- Validation: `auditor` reads `/audit` but cannot query; `user` sees only their own rows; README reflects actual behavior; startup with `RBAC_ENABLED=true` and no seeded users fails with the documented message.

## 13. Future Considerations

Explicitly deferred post-MVP:
- External identity providers (OIDC/SAML), SSO, token expiry and rotation policy
- Human-chosen passwords for the chat UI login — requires argon2/bcrypt, not the SHA-256 used for machine-generated tokens
- User-management HTTP endpoints and an admin UI, replacing the bootstrap CLI
- Custom roles, groups, role hierarchies, and per-user permission overrides
- A `pii:view_raw` permission, as a prerequisite for any endpoint that would expose the raw `prompt_preview`/`response_preview` columns — the data exists in the database today but no endpoint returns it, so the permission has nothing to gate yet
- Selectable duplicate-detection scope (`global` | `per-user` | `per-role`), which becomes necessary the moment multi-tenancy or team separation is introduced (see Risk 3)
- Per-role rate limits, token budgets, and cost caps — the natural next use of a verified identity
- Action-policy rules for MCP tool calls, where "the same `DELETE` is denied for one role and allowed for another" — this PRD is the prerequisite the roadmap already names
- Carrying identity through the planned OpenAI-compatible endpoint, where the credential is the `Authorization` header and `user_id` maps to the standard's optional `user` field

## 14. Risks & Mitigations

1. **Risk**: The chat UI bypasses the control. `ChatState.send()` calls `run_query(...)` in-process and never traverses FastAPI's dependency chain, so an authorization check written as a router `Depends(...)` — the pattern used today in `app/routers/admin.py` — would leave the browser ingress completely unguarded.
   **Mitigation**: `Identity` is a **required parameter** of `run_query(...)`, and the check is step 0 of the pipeline. A new caller that forgets authorization fails to construct a valid call rather than silently skipping the check. An ingress-parity test asserts both paths deny identically. HTTP dependencies remain as an outer layer only.

2. **Risk**: Enabling RBAC breaks every existing deployment, since no users exist and deny-by-default refuses everything.
   **Mitigation**: Fail fast at startup when `RBAC_ENABLED=true` and no active user is seeded, with a message naming the bootstrap command — an actionable failure instead of a service that returns `401` to everything. `ADMIN_TOKEN` continues to work as break-glass, and `RBAC_ENABLED=false` is a documented, explicitly supported migration escape hatch.

3. **Risk**: Duplicate detection stays global and becomes an authorization side channel. `check_duplicate(prompt)` hashes only the prompt and does not filter by user, so one user's prompt blocks another's and discloses `first_query_at` across role boundaries.
   **Mitigation**: Accepted, documented residual risk for this MVP — the behavior is unchanged from PRD-001, and changing it would alter a core guarantee (and its tests) that this PRD deliberately does not touch. Selectable dedup scope is tracked in Section 13 and becomes mandatory before any multi-tenant deployment.

4. **Risk**: Adding audit columns fails against existing database files. `main` has no migration mechanism: `init_db()` runs `CREATE TABLE IF NOT EXISTS`, which is a no-op on a table that already exists, so new columns would never appear and every insert would fail.
   **Mitigation**: Phase 1 builds the additive-migration mechanism before any column is added, applying `ALTER TABLE ... ADD COLUMN` for whichever columns are missing. Every added column declares a non-NULL default, because SQLite rejects `ADD COLUMN NOT NULL` without one. A test runs migration against a fixture database created from the pre-RBAC schema.

5. **Risk**: Reflex state is treated as trusted. State vars are serialized to the client and mutated by client-originated events, so a role cached in an `rx.var` is not a safe basis for a decision; separately, the final `else` in `ChatState.send()` is a catch-all over the `QueryResponse` union, so adding a fourth member silently routes forbidden results into the wrong bubble.
   **Mitigation**: `ChatState` stores no credential and no role — only the authenticated `user_id`, set exclusively by `login()` — and the role is re-resolved server-side on every `send()`. The union gains an explicit `isinstance` branch for `QueryBlockedForbiddenResponse`, with a test asserting each member of the union renders its own bubble.

## 15. Appendix

**Related docs**
- [README.md](../../../README.md) — Roadmap item "Role-based access control (RBAC)" this PRD implements
- [PRD-001 — Harness IA MVP](../PRD-001-harness-ia/PRD.md) — the pipeline, `ADMIN_TOKEN`, and audit schema this PRD extends
- [PRD-002 — Reflex Chat UI](../PRD-002-reflex-chat-ui/PRD.md) — Risk 4 and the shared-pipeline extraction that make the two-ingress problem explicit
- [PRD-003 — PII Redaction](../PRD-003-pii-redaction/PRD.md) — Section 9 and Risk 4 record the unresolved RBAC gap on `/audit` that this PRD closes

**Skills referenced**: None — `.agents/skills/` does not exist in this repository.

**Dependencies**
- No new runtime dependencies: `secrets`, `hashlib`, `json`, and `sqlite3` are all standard library
- **Branch coupling**: `epic/PRD-004-chat-ui-redesign` is unmerged and rewrites `chat_ui/chat_ui/state.py` (typed `ChatMessage`, `pending` flag, `formatting.py`, `copy.py`, and a frontend `MODEL_ALLOWLIST`). This PRD's chat-UI changes touch the same file. Merge PRD-004 into `main` before starting Phase 3, or expect a non-trivial conflict in `state.py`. The backend-side model allowlist specified here supersedes PRD-004's frontend-only list, which remains valid as a UI affordance but is not the control.
- **ID note**: `PRD-004` is already taken by `epic/PRD-004-chat-ui-redesign`, which is not yet merged into `main` and therefore does not appear in `.agents/PRDs/` on this branch. This PRD is numbered `005` to avoid the collision.
