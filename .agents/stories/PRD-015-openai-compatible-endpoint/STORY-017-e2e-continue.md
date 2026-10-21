---
id: STORY-017
prd: PRD-015
slug: e2e-continue
title: "E2E: Continue chat through the harness"
type: technical
priority: medium
complexity: medium
phase: "4 - Real clients, deployment, documentation"
status: todo
labels: [tests, e2e, clients]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-013, STORY-014, STORY-015]
blocks: [STORY-019]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-017: E2E: Continue chat through the harness

## Description

As an integrating developer using Continue, I want its chat to answer through the harness with a model entry pointing at `/v1`, so that my editor's assistant is covered by the same controls.

## Acceptance Criteria

- [ ] Given Continue configured with the PRD Section 10 `config.yaml` model entry (provider `openai`, `apiBase` the harness `/v1`, `apiKey` a harness token), when a chat message is sent, then the stub's scripted answer is shown and the audit row has `ingress='v1'`, `profile='code'` and the request's `streamed` flag.
- [ ] Given a message the harness blocks, when sent, then Continue shows the error with the harness reason and does not resend it (one row).
- [ ] Given Continue's model discovery or startup calls, when they hit `/v1/models` or `/v1/models/{id}`, then they succeed; any other `/v1` path Continue calls is recorded in the report.
- [ ] Given the run, when the report is written, then it records the pinned Continue version, whether the run was the headless CLI or a recorded manual VS Code run (with screenshots in `docs/screenshots/`), and whether Continue sends `tools` in chat mode.

## Technical Notes

- Prefer Continue's CLI in headless mode if the pinned version has one; otherwise a manual run in VS Code, recorded in the report with screenshots. The PRD allows either (Section 8).
- Continue parses SSE itself rather than through the OpenAI SDK; this story is where keep-alive comment lines are checked against a non-SDK parser (PRD Risk 1). Use a stub delay of at least 15 s once.
- If chat mode sends `tools`, configure it out (`capabilities`, roles) and document the setting for STORY-019 (PRD Risk 2).
- The device header can be set with `requestOptions.headers` (`X-Harness-Device`); include it and assert `device` on the row.
- Skills: none applicable. (Continue's UI is the client's, not this project's; `frontend-design` does not apply.)

## Dependencies

- **Blocked by**: STORY-013, STORY-014, STORY-015
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 8, 10 (Continue config), 11, 14 (Risks 1, 2, 3)
