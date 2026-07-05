---
story: STORY-009
prd: PRD-002
slug: readme-chat-ui-docs
title: "README chat UI quickstart documentation"
type: technical
complexity: small
epic_branch: epic/PRD-002-reflex-chat-ui
created: 2026-07-05
---

# Plan: README chat UI quickstart documentation

## Summary

Add a "Chat UI" section to `README.md` that sits alongside the existing curl-based `/query` examples, documenting the browser chat introduced by this epic: one URL/one port shared with the REST API, the one-time `user_id` entry gate, and the distinct rendering for success vs. blocked (duplicate/suspicious) messages. Extend (don't rewrite) the existing "Features" bullet list and MVP-limitations framing, and verify the instructions against a real `docker-compose up -d --build` run — this is a docs-only story with one file changed, but its acceptance criteria require the steps to be actually exercised, not just written.

## User Story

As an end user or devops engineer reading the project README
I want a "chat UI" quickstart section alongside the existing curl examples
So that I know a browser-based chat is available and how to reach it, without reverse-engineering it from code

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-009-readme-chat-ui-docs.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | small |
| Systems Affected | Documentation only (`README.md`) |
| Story | STORY-009 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repo, and the story's `skills:` frontmatter field is empty — this is a plain Markdown edit, no Reflex/framework tooling involved in the change itself (only in verifying it via `docker-compose`).

---

## Patterns to Follow

### Existing README structure (extend, don't restructure)
```
// SOURCE: README.md:1-56
# Harness IA
...
## Features
- **`POST /query`** — ...
...
## Quickstart — Local
## Quickstart — Docker
## Environment Variables
```
New content is added as: one new "Chat UI" bullet in `## Features`, and a new `## Chat UI` section placed after `## Quickstart — Docker` and before `## Environment Variables` (i.e., right where a reader who just ran `docker-compose up` would look next, before diving into the curl-based `## API Reference`).

### Existing curl-example style to match tone/format
```
// SOURCE: README.md:57-111
### `POST /query` — success
​```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "juan@empresa.com", "prompt": "what is the weather today"}'
​```
```
The new Chat UI section should match this same terse, example-driven style: short prose + a fenced snippet, no marketing language.

### Actual chat UI behavior to describe accurately (verified from code, not guessed)
```
// SOURCE: chat_ui/chat_ui/chat_ui.py:24-35 — index() gates on ChatState.user_id != ""
// SOURCE: chat_ui/chat_ui/components/chat.py:68-88 — user_id_prompt(): plain text field + "Continue" button, placeholder "user_id"
// SOURCE: chat_ui/chat_ui/components/chat.py:6-51 — message_bubble(): user (right, blue), assistant (left, gray), system/blocked (centered, amber) — blocked bubbles use the exact `reason` string from run_query(), e.g. "Blocked — Duplicate query within 24 hours (first sent at ...)"
```

### MVP limitations to cross-reference (do not overstate capability)
```
// SOURCE: .agents/PRDs/PRD-002-reflex-chat-ui/PRD.md:50-57 (Section 4, Out of Scope)
- No token-by-token streaming
- No persisted chat history / multi-room chat
- No model picker
- No full auth/login (free-text user_id only)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | Add one "Chat UI" bullet to `## Features`; add a new `## Chat UI` section with quickstart steps, `user_id` gate explanation, blocked-bubble behavior, and known MVP limitations |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add a "Chat UI" bullet to the Features list

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Insert one new bullet into the existing `## Features` list (README.md:5-13), directly after the `**`POST /query`**` bullet, noting the browser chat shares the same port/pipeline. Do not reorder or reword existing bullets.
- **Mirror**: Existing bullet style, e.g. `- **`GET /audit`** and **`GET /stats`** — admin-only endpoints...` (README.md:11)
- **Validate**: Visual diff review — only one line added, nothing else in `## Features` touched.

### Task 2: Add the `## Chat UI` section

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**: Insert a new `## Chat UI` section after `## Quickstart — Docker` (ends README.md:42) and before `## Environment Variables` (README.md:44). Cover, in this order:
  1. How to open it: `http://localhost:8000/` after either `python app.py` or `docker-compose up -d --build` (same port as the API, no extra step).
  2. The one-time `user_id` entry gate: a plain text field ("Enter a user ID to start chatting"), no password/token/OAuth — entered once per browser session, matching the existing `user_id` presence check `/query` already requires.
  3. Message rendering: your own messages align right; model responses render as an assistant bubble on the left; blocked messages (duplicate within 24h, or a suspicious pattern match) render as a distinct centered/amber "system" bubble with the same `reason` text the REST API returns — never silently dropped.
  4. A short "Known limitations (MVP)" sub-list: no streaming (full response only, same as `/query` today), no persisted chat history across sessions/browsers, no login/auth beyond the `user_id` field.
- **Mirror**: `## Quickstart — Docker` (README.md:29-42) for section-heading style and terseness; `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md` Section 4 for the exact out-of-scope wording to reuse.
- **Validate**: Re-read the full updated `README.md` top-to-bottom — confirm `## API Reference`'s curl examples (README.md:57-157) are byte-for-byte unchanged, and the new section doesn't duplicate content already in `## Quickstart — Docker`.

### Task 3: Verify the documented steps against a real build

- **File**: N/A (verification only)
- **Action**: N/A
- **Implement**: From a clean-ish state, run `docker-compose up -d --build`, then confirm `curl http://localhost:8000/health` returns the healthy response and `http://localhost:8000/` serves the chat UI's initial HTML (containing the `user_id` entry prompt), exactly as STORY-008's report already validated. This story doesn't change any runtime code, so this is a confirmation that the just-written README steps match current, real behavior — not a new build validation.
- **Mirror**: Validation steps already executed and recorded in `.agents/reports/PRD-002-reflex-chat-ui/STORY-008-docker-single-port-packaging.report.md` (`curl http://localhost:8000/health` ✅, `GET http://localhost:8000/` ✅ 200).
- **Validate**: `curl http://localhost:8000/health` → `{"status":"ok"}`; `curl -s http://localhost:8000/ | grep -i "user id"` → non-empty (entry-gate HTML present).

---

## End-to-End Tests

- [ ] `docker-compose up -d --build` from the current branch state succeeds
- [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `curl http://localhost:8000/` → 200, HTML contains the `user_id` entry-gate prompt text
- [ ] Existing `## API Reference` curl examples in the README remain textually unchanged (diff review)

---

## Validation

```bash
docker-compose up -d --build
curl http://localhost:8000/health
curl -s http://localhost:8000/ | grep -i "user id"
docker-compose down
```

---

## Acceptance Criteria

(Copied from story STORY-009)

- [ ] `README.md` includes a "Chat UI" section describing how to open the chat (`http://localhost:8000/` after `docker-compose up`), placed alongside the existing curl-based `/query` examples.
- [ ] Existing curl examples for `/query`, `/audit`, `/stats` remain unchanged.
- [ ] A new reader understands: (a) chat UI and REST API share one port, (b) the chat UI requires entering a `user_id` once per session, (c) blocked messages render as distinct bubbles with an explanation.
- [ ] README notes known out-of-scope items: no streaming, no persisted chat history, no login/auth beyond `user_id`.
- [ ] `docker-compose up -d --build` from a clean checkout followed exactly per the README works — chat UI and `GET /health` both function.
- [ ] All tasks completed.
- [ ] Follows existing README patterns/style.
