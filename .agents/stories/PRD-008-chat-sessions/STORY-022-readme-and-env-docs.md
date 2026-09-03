---
id: STORY-022
prd: PRD-008
slug: readme-and-env-docs
title: "README and .env: document the persistence model the code actually has, including what is now at rest"
type: technical
priority: medium
complexity: small
phase: "4 - Surface and hardening"
status: todo
labels: [docs, readme, security]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-010, STORY-011, STORY-019, STORY-021]
blocks: []
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-022: README and .env: document the persistence model the code actually has, including what is now at rest

## Description

As an integrating developer and as a security admin, I want the README to describe what this release stores and what the switch does, so that the largest change in the product's data posture is discoverable without reading a PRD.

## Acceptance Criteria

- [ ] Given [README.md](../../../README.md), when the environment table is read, then `CHAT_HISTORY_ENABLED` and `CHAT_SESSION_LIMIT` appear with their defaults and their effect, alongside `PII_REDACTION_ENABLED` and `RBAC_ENABLED`.
- [ ] Given the API reference section, when `POST /query` is read, then `session_id` is documented as optional, with the `422` on a malformed value and the `403` on a foreign one both stated.
- [ ] Given the API reference, when `GET /audit` is read, then `session_id` appears in the response shape.
- [ ] Given the persistence section, when it is read, then it states plainly what is now stored: the prompt as typed and the redacted response, per session, readable only by the owner — and that `audit_logs` still stores hashes and truncated previews and is unchanged.
- [ ] Given the same section, when it is read, then it states what `CHAT_HISTORY_ENABLED=false` does and that it is a supported configuration, not a degraded mode.
- [ ] Given the deletion behaviour, when it is documented, then it says that deleting a chat removes the transcript and leaves the audit record intact.
- [ ] Given the Chat UI section, when it is read, then the session rail is described as it actually behaves — including that a chat is created on the first send, not on page load.
- [ ] Given the Roadmap's **Shipped** list, when it is read, then chat sessions appear; and given the **Planned** list, then multi-turn context appears with the duplicate-detection consequence stated.
- [ ] Given the architecture diagram, when it is read, then the two new tables appear alongside `audit_logs` and `users`, and the pipeline line is unchanged — because the pipeline is unchanged.
- [ ] Given [.env.example](../../../.env.example), when it is read, then it matches [app/config.py](../../../app/config.py) exactly — every setting present, no setting documented that does not exist.

## Technical Notes

- Files: [README.md](../../../README.md), [.env.example](../../../.env.example) (reconciliation pass; the variables themselves landed in [[STORY-001]]).
- **Describe the code that exists, not the PRD's intentions.** PRD-007 STORY-015 set this bar for the Turso write-up and it applies here: read the merged implementation and document that. Where they disagree, the code wins and the divergence goes in the report.
- The README already draws a hard line at the Roadmap, verbatim: "Everything below this line is **intended direction, not current behavior**. The only ingress that exists today is `POST /query`." That line stays true — this PRD adds no ingress — and multi-turn must land **below** it.
- The Roadmap's OpenAI-compatible endpoint section already poses the duplicate-detection question this PRD deferred: "What gets hashed for duplicate detection in a multi-turn conversation — the last user turn only, or the full `messages` array." Cross-reference it rather than restating it; PRD Section 13 explains why sessions make that question unavoidable rather than optional.
- Do not claim multi-turn works. The most likely documentation defect in this release is a README that describes a session as a conversation the model remembers. It is not: every send is still one user turn, alone. Say so.
- Do not describe the admin console as showing sessions. It does not — PRD Section 4 puts that out of scope and [[STORY-011]] stops at `GET /audit`.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story writes documentation. No skill applies.

## Dependencies

- **Blocked by**: STORY-010, STORY-011, STORY-019, STORY-021
- **Blocks**: None

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 9, Section 10, Section 11, Section 12 Phase 4, Section 13
