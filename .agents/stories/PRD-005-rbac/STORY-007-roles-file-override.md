---
id: STORY-007
prd: PRD-005
slug: roles-file-override
title: Role matrix loaded from RBAC_ROLES_FILE at startup
type: feature
priority: medium
complexity: small
phase: "Phase 2 — Authorization core"
status: todo
labels: [backend, config, security]
epic_branch: epic/PRD-005-rbac
plan: null
report: null
commit: null
depends_on: [STORY-006]
blocks: []
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-007: Role matrix loaded from RBAC_ROLES_FILE at startup

## Description

As an operator, I want the role matrix overridable by a versioned JSON file, so that permissions are per-deployment configuration rather than a code change.

## Acceptance Criteria

- [ ] Given `RBAC_ROLES_FILE` is empty, when the app starts, then the built-in matrix is used and no file is read
- [ ] Given a valid JSON matrix, when the app starts, then it **fully replaces** the built-in matrix — no merge, so an omitted permission is a denial
- [ ] Given a malformed or unreadable file, when the app starts, then startup fails with a message naming the file and the parse error, rather than silently falling back to the default
- [ ] Given a file granting an unrecognized permission name, when it loads, then startup fails listing the unknown name
- [ ] Given the file loads, when it happens, then it happens once at startup, never per request

## Technical Notes

- stdlib `json`; no new dependency.
- `authz.load()` is called from `app/main.py`'s `lifespan`, next to `pii_redactor.load()` — **and** registered in `chat_ui/chat_ui/chat_ui.py` via `app.register_lifespan_task(...)`, because Reflex's `api_transformer` mounts the FastAPI app under an outer Starlette app whose own lifespan runs instead. PRD-002 and PRD-003 hit this exact trap with `init_db()` and `pii_redactor.load()`; skipping it here would leave the chat UI running a **different permission matrix** from the API.
- Full replacement rather than merge is deliberate: a partial override that silently inherits grants is how a permission gets granted by accident.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: None

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 6 and 9
