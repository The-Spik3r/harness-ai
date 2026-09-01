---
id: STORY-005
prd: PRD-007
slug: turso-configuration
title: "Config: TURSO_AUTH_TOKEN, libSQL DATABASE_URL semantics, and no file fallback"
type: feature
priority: high
complexity: small
phase: "2 - Storage layer swap"
status: todo
labels: [backend, config, security, turso]
epic_branch: epic/PRD-007-turso-migration
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-006]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-005: Config: TURSO_AUTH_TOKEN, libSQL DATABASE_URL semantics, and no file fallback

## Description

As a platform engineer, I want `DATABASE_URL` to name a libSQL endpoint and a `sqlite:///` value to be a startup error, so that no deployment can silently create a local database file that nobody reads and nobody backs up.

`DATABASE_URL` currently defaults to `sqlite:///harness_ai.db` in [app/config.py](../../../app/config.py). That default is exactly the failure mode this PRD removes: a misconfigured container boots successfully, writes an audit trail to a file inside an ephemeral layer, and loses it on the next deploy. PRD Section 2: "A configuration that would have opened a file is a startup error, not a degraded mode."

## Acceptance Criteria

- [ ] Given [app/config.py](../../../app/config.py), when it is read, then `TURSO_AUTH_TOKEN` is declared alongside `OPENROUTER_API_KEY` and `ADMIN_TOKEN`, loaded through the same pydantic-settings `.env` mechanism.
- [ ] Given a remote endpoint (`libsql://` or `https://`), when `TURSO_AUTH_TOKEN` is empty, then configuration validation fails with a message naming the setting.
- [ ] Given a local dev-server endpoint (`http://`), when `TURSO_AUTH_TOKEN` is empty, then that is accepted — the local server takes no token. PRD Section 9: "a plaintext `http://` endpoint is permitted only for the local development server."
- [ ] Given `DATABASE_URL` set to any `sqlite:///` value, when configuration is validated, then it raises an error whose message names the correct replacement form. It must never fall back to opening a file, and never be silently ignored.
- [ ] Given `DATABASE_URL` unset, when configuration is validated, then it fails as a required setting. The `sqlite:///harness_ai.db` default is removed, not replaced with another default.
- [ ] Given a validation failure for either setting, when the message is inspected, then it does not contain the token value. PRD Section 9: the credential "is never logged, never echoed in error messages, and never committed."
- [ ] Given `tests/test_config.py`, when it runs, then it covers: remote URL without token (fail), local URL without token (pass), `sqlite:///` URL (fail, message names the replacement), unset URL (fail), and a valid remote pair (pass).

## Technical Notes

- Files: [app/config.py](../../../app/config.py), `tests/test_config.py`. `.env.example` if the repo carries one.
- This story adds configuration *validation only*. It does not construct a client and does not touch [app/db/database.py](../../../app/db/database.py) — that is [[STORY-006]]. Keeping them separate means a config mistake is diagnosable without a database in the loop.
- Accept the URL schemes named in PRD Section 4: `libsql://`, `https://`, and `http://` for the local dev server. The exact scheme the chosen client expects is an output of [[STORY-001]]'s decision record — read it before writing the validator rather than guessing.
- The existing `_SQLITE_PREFIX` constant and `_db_path()` in [app/db/database.py](../../../app/db/database.py) raise `ValueError(f"Unsupported DATABASE_URL scheme: {url}")` today. That rejection moves to config, where it fires at startup rather than on first query. Leave `_db_path()` alone in this story; [[STORY-006]] deletes it.
- Note the interaction with the Docker build. [Dockerfile](../../../Dockerfile) sets `DATABASE_URL=sqlite:///:memory:` as a build-time placeholder so `reflex export` can import `chat_ui.chat_ui` past Pydantic validation. **This story will break that build.** Either update the placeholder here or confirm [[STORY-014]] owns it — do not leave the build broken between commits without saying so in the report.
- Follow the existing style in `app/config.py`: settings grouped with a comment naming the PRD that introduced them, as the RBAC and PII groups already do.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 4 (in scope), Section 9 (Security & Configuration), Section 11 (functional requirements), Section 12 Phase 2
