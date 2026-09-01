---
id: PRD-006
slug: admin-console
title: Admin Console — Audit Register & Summary
status: draft
base_branch: main
epic_branch: epic/PRD-006-admin-console
created: 2026-08-28
updated: 2026-08-31
---

## 1. Executive Summary

The harness has recorded every prompt that passed through it since PRD-001, and PRD-003 added PII telemetry on top of that record. None of it has a screen. `GET /audit` and `GET /stats` are bearer-token JSON endpoints, so the only way a compliance admin can answer "did anything get blocked today?" is to hand-craft a `curl` with the admin token and read a 100-element JSON array. PRD-002 deferred an admin UI, and PRD-004 deferred it again — explicitly, in its Section 4 out-of-scope list and again in its Section 13 follow-ups.

The record is also being under-read by its own API. `AuditQueryEntry` projects nine fields out of the audit row and drops `success` and `error_message` entirely, so a query that failed on OpenRouter or in the PII redactor is indistinguishable over `/audit` from one that answered cleanly — even though `query_pipeline.py` writes both (`success=False`, `error_message=str(exc)`) at three separate points. And `StatsResponse.success_rate` is computed as `count_successful_queries() / count_audit_logs()`, where `count_successful_queries()` counts `success = 1` — which includes every duplicate-blocked and every injection-blocked row, because the pipeline logs both as `success=True`. The number reads as "how often users got an answer" and counts something else.

This PRD builds the **admin console** — and only the admin console. Two new Reflex pages under `/admin`, gated on `ADMIN_TOKEN`: a **register** listing the recorded traffic with the same outcome vocabulary the chat uses, and a **summary** rendering every `StatsResponse` field with its true scope stated. Nothing under `app/` changes: no new queries, no query parameters, no schema migration. The console reads the existing database functions in-process, exactly as PRD-004's `ChatState` calls `run_query(...)` in-process, and it renders no field the REST projection would not — minus the raw previews, which stay unrendered.

## 2. Mission

Give the record a reading surface, and let no number on it mean something other than what its label says.

Core principles:
- **The record is the subject**: the console is a register, not a dashboard. It presents what was written, in the order it was written, with the verdict attached.
- **Every number states its own scope**: an all-time count and a last-100 listing never share a frame without saying which is which. A label that would mislead gets rewritten, not decorated.
- **Same vocabulary as the chat**: an outcome an end user saw as *held* is *held* here too. PRD-004 established one ink per outcome; the console is the same legend applied to rows instead of bubbles.
- **Presentation only**: the console consumes what `app/db/database.py` already returns. If a cut of the data needs a new query, it is out of scope rather than a reason to change `app/`.
- **Read-only, and visibly so**: nothing on this surface mutates an audit row. The record is evidence; a console that could edit it would not be one.

## 3. Target Users

**Security/Compliance Admin** — the primary persona, and the first PRD where they get a screen. Today they hold `ADMIN_TOKEN` and read JSON. They need to answer three recurring questions without a terminal: what has been blocked recently and why, which users and models dominate the traffic, and how much of it is touching PII. Technical level: comfortable with a bearer token, not necessarily with `jq`.

**End User (Employee)** — unaffected. The chat surface is untouched by this PRD, they never see `/admin`, and the token gate is the only thing standing between the two. Their interest is indirect: the `audit_id` PRD-004 put in their success footer becomes a value an admin can actually look up.

**Integrating Developer** — cares that the console stays inside `chat_ui/` and adds no route, no query, and no schema change, so PRD-001's `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_admin_auth.py`, `tests/test_db.py` and `tests/test_route_reservations.py` all keep passing unmodified.

## 4. MVP Scope

### In Scope

**Console shell & access**
- [ ] New Reflex pages under `/admin`: `/admin/audit` (register) and `/admin/stats` (summary); `/admin` lands on the register
- [ ] `ADMIN_TOKEN` gate: token entry, compared with `secrets.compare_digest` against `settings.ADMIN_TOKEN` — the same comparison `require_admin_token` uses
- [ ] Failed entry returns one generic message; no distinction between "empty", "wrong length" and "wrong token"
- [ ] Authenticated state lives in the Reflex session state only; a sign-out action clears the token, the loaded rows and the stats
- [ ] Both pages gated independently — reaching `/admin/stats` directly with no session shows the gate, not the data
- [ ] Cross-surface separation: `ChatState` never reads admin state, and no admin page renders a chat component

**Register (`/admin/audit`)**
- [ ] Table of the 100 most recent audit rows, newest first, with the count and the cap stated on the surface
- [ ] Columns: timestamp (relative + absolute), `user_id`, verdict, `model_used`, `tokens_used`, PII indicator, `device`, `audit_id`
- [ ] Four verdicts derived from the row and rendered with PRD-004's existing inks: **cleared**, **held** (duplicate), **denied** (suspicious pattern), **fault** (`success = 0`)
- [ ] Row detail disclosure: `prompt_hash`, `error_message`, PII entity types, full User-Agent string, `suspicious_pattern`
- [ ] Client-side filter by verdict (multi-select) and free-text match over `user_id` / `model_used` / `audit_id`
- [ ] Sort by timestamp, user, or verdict
- [ ] Three distinct states: no rows recorded at all, rows recorded but none matching the filter, and rows shown

**Summary (`/admin/stats`)**
- [ ] Every `StatsResponse` field rendered — `total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, `success_rate`, `top_models`, `top_users`, `pii_detected_queries`, `top_pii_entities`
- [ ] `success_rate` labeled for what it counts — rows the pipeline completed without raising, blocked rows included — not as an answer rate
- [ ] Every figure carries its scope: all-time over the whole table, distinct from the register's last-100 window
- [ ] Blocked figures shown as counts *and* as a share of `total_queries`
- [ ] PRD-003's PII telemetry (`pii_detected_queries`, `top_pii_entities`) rendered for the first time in any UI
- [ ] `top_models` / `top_users` as ranked lists, with the "top 5" cut stated

**Data access & failure handling**
- [ ] `AdminState` reads through `app/db/database.py` in-process; the SQLite calls are offloaded with `asyncio.to_thread(...)`, per PRD-004's precedent
- [ ] Manual refresh action on both pages, with a last-refreshed timestamp
- [ ] Loading state while a read is in flight; the refresh control locks for its duration
- [ ] A failed read renders a fault panel naming what failed — never a silently empty table
- [ ] Catch-all `except Exception` on every read path, matching PRD-004's "no silent drops" invariant

**Design & copy** (direction specified in Section 6.1, per the **frontend-design** skill)
- [ ] Every colour, size and face comes from `chat_ui/theme.py`; any new token is added there, preserving the single-file guarantee
- [ ] The **stamp margin**: a fixed left column carrying the verdict ink as a solid mark, blank for cleared rows
- [ ] `FONT_DATA` as the register's dominant face, with numeric columns aligned down the full window
- [ ] The summary set as a ruled tally sheet — blocked figures indented beneath the total — with no cards, fills, or accent colour
- [ ] Every user-facing string lives in a copy module, per PRD-004 STORY-007
- [ ] Contrast parity: any new ink/ground pairing clears WCAG AA and is asserted in `tests/test_contrast.py`
- [ ] Quality floor: responsive down to a narrow viewport, visible keyboard focus, `prefers-reduced-motion` respected on the one moving element

### Out of Scope

- [ ] **Any change under `app/`** — no new database functions, no query parameters on `GET /audit`, no schema migration, no change to `AuditQueryEntry` or `StatsResponse`
- [ ] **Pagination past 100 rows** — `list_audit_logs(limit=100)` is the ceiling this PRD reads against; deeper history needs a new query
- [ ] **Server-side filtering, date ranges, or full-text search** — all filtering is client-side over the loaded window
- [ ] **Rendering `prompt_preview` / `response_preview`** — the raw prompt and response text stay unrendered, holding PRD-004 Section 9's guarantee that no new surface exposes them
- [ ] **Export** (CSV, JSON, download) — nothing leaves the screen
- [ ] **Charts and time series** — `StatsResponse` carries no time dimension, so any trend line would be invented
- [ ] **Multiple admin accounts, roles, or session expiry** — one shared `ADMIN_TOKEN`, unchanged from PRD-001
- [ ] **Auto-refresh, polling, or push updates** — refresh is a deliberate action
- [ ] **Mutating audit rows** — no edit, no delete, no annotate
- [ ] **Changes to the chat surface** — PRD-004 ships as-is
- [ ] **A full i18n framework** — copy centralization only, as in PRD-004

## 5. User Stories

1. **As a compliance admin**, I want to open a page and see the recent traffic, so that answering "what happened today" does not require a `curl` and a JSON reader.
   - Example: `/admin/audit` after entering the token shows 100 rows, newest first, with the newest at 2 minutes ago.

2. **As a compliance admin**, I want blocked traffic to stand out from cleared traffic at a glance, so that I can scan a hundred rows without reading a hundred rows.
   - Example: the three denied rows in the window are the only ones carrying the denied ink; finding them is a glance down the verdict column.

3. **As a compliance admin**, I want to see which queries failed and why, so that an outage or a broken redactor is visible in the record instead of hiding behind `/audit`'s projection.
   - Example: a row marked *fault* expands to `OpenRouter request failed: timeout after 30s` — a value `GET /audit` does not return at all.

4. **As a compliance admin**, I want to filter the register to one verdict or one user, so that investigating a specific report does not mean re-reading the whole window.
   - Example: filtering to *denied* plus `a.torres` narrows 100 rows to 2.

5. **As a compliance admin**, I want to look up the `audit_id` a user quoted from their chat footer, so that a support report resolves to a specific row instead of a paraphrase.
   - Example: a user reports a problem with `#127`; typing `127` into the register filter isolates that row and its verdict.

6. **As a compliance admin**, I want to see how much traffic touched PII and which entity types dominate, so that PRD-003's redaction has a reported effect rather than an invisible one.
   - Example: the summary reads `412 of 3,180 queries contained PII` with `EMAIL_ADDRESS, PERSON, PHONE_NUMBER` as the leading types.

7. **As a compliance admin**, I want each figure to say what it counts and over what window, so that I do not report a blocked-inclusive completion rate as a user success rate.
   - Example: the completion figure is labeled *completed without error (blocked queries included)*, and the register is labeled *100 most recent of 3,180*.

8. **As a security admin**, I want the console to require the admin token and to hold nothing after sign-out, so that an open browser on a shared machine is not a standing disclosure.
   - Example: signing out returns the gate, and the previously loaded rows are gone from state, not merely hidden.

9. **As an integrating developer**, I want the console confined to `chat_ui/` with no new route on the FastAPI app, so that the REST contract, the audit schema and PRD-001/003's test suites are provably unchanged.

## 6. Core Architecture & Patterns

The pipeline and the REST layer are unchanged. The console is a second consumer of the same in-process database module the API already reads:

```
                        app/db/database.py
                                │
        ┌───────────────────────┴───────────────────────┐
        │                                               │
  app/routers/admin.py                          chat_ui AdminState
  GET /audit  (Depends require_admin_token)     /admin/audit, /admin/stats
  GET /stats  (Depends require_admin_token)     token gate in state
        │                                               │
     JSON to curl                            rendered register + summary
```

Read path:

```
AdminState.authenticate(token)
   │  secrets.compare_digest(token, settings.ADMIN_TOKEN)
   ├── mismatch ──────────────────────────► generic gate error, no state change
   └── match ─────────────────────────────► authenticated = True, then load()

AdminState.load()   (Reflex background event)
   │  set loading = True
   ▼
await asyncio.to_thread(...)
   ├── list_audit_logs(limit=100) ────────► rows: list[AuditRow]
   ├── count_audit_logs() ────────────────► total (the register's denominator)
   ├── count_blocked_duplicates()          ┐
   ├── count_blocked_suspicious()          │
   ├── count_unique_users()                ├─► summary figures
   ├── count_successful_queries()          │
   ├── count_pii_detected_queries()        │
   ├── top_models() / top_users()          │
   └── top_pii_entities()                  ┘
   │
   ├── raises Exception ──────────────────► fault panel + retry, rows untouched
   ▼
set rows, set last_refreshed, loading = False
```

**Verdict derivation.** The register uses the chat's outcome vocabulary, computed once per row in Python when the row is built — never at render time, for the same reason PRD-004 put `format_duplicate_info` in `formatting.py`: component functions receive Reflex Vars, not values.

| Audit row condition | Verdict | Ink (existing `theme.py` token) |
|---|---|---|
| `was_duplicate_blocked = 1` | **held** | `INK_HELD` |
| `suspicious_pattern is not None` | **denied** | `INK_DENIED` |
| `success = 0` | **fault** | `INK_FAULT` |
| otherwise | **cleared** | `INK_CLEAR` |

Four verdicts, not PRD-004's six, and deliberately so. The chat can separate an upstream failure from an internal one because it catches the exception type; the audit row carries no such discriminator. `model_used` looks like one until you follow `query_pipeline.py`: the output-side `PiiRedactorError` arm logs `model_used=openrouter_result.model_used`, so an internal fault and an OpenRouter failure both land with a model recorded. Splitting *fault* on that field would encode the pipeline's statement order into the console and break the first time it is reordered. Instead, *fault* is one verdict and the row's `error_message` — surfaced on disclosure — carries the actual distinction. Section 13 records the schema change that would let the console split it honestly.

Files (all new, all inside `chat_ui/`):

```
chat_ui/
├── chat_ui/
│   ├── chat_ui.py                  # CHANGED: register the two admin pages
│   ├── admin_state.py              # NEW: AdminState — gate, reads, filters, sort
│   ├── admin_models.py             # NEW: AuditRow (rx.Base), SummaryFigure
│   ├── admin_copy.py               # NEW: every admin-facing string
│   ├── admin_formatting.py         # NEW: verdict derivation, relative time, shares
│   ├── theme.py                    # CHANGED: any new token, added here only
│   └── components/
│       ├── admin_shell.py          # NEW: token gate, console header, view switch
│       ├── register.py             # NEW: the audit table, filters, row detail
│       └── summary.py              # NEW: the stats sheet
└── tests/                          # CHANGED (repo root): admin state + gate tests
```

Design patterns:
- **Second in-process consumer**: `AdminState` imports `app/db/database.py` and never modifies it, the same boundary `ChatState` holds against `run_query(...)`. No HTTP call from the app to itself, and no admin token in the browser beyond the gate submission.
- **Gate as state, not as route**: the pages exist unconditionally; the token check decides what they render. Reflex has no server-side route guard here, so the guard is the render condition — and the data is not loaded until it passes.
- **Derived-once row model**: `AuditRow` carries the verdict, the relative time and the formatted device string as plain fields, computed in `admin_formatting.py`. Components read fields; they do not compute.
- **Filtering as a computed var**: the visible rows are an `rx.var` over the loaded rows plus the filter state, so filtering never re-reads the database.
- **Thread-offloaded blocking work**: SQLite reads go through `asyncio.to_thread(...)`; state mutation stays inside `async with self`, per Reflex's background-event contract.

**Routing constraint.** `/audit` and `/stats` are taken — by `app/routers/admin.py`, by `tests/test_route_reservations.py`, and by the `Caddyfile`'s `@backend_routes` matcher, which reverse-proxies `/query /audit /stats /health` to the backend. The console therefore lives at `/admin/audit` and `/admin/stats`, which fall through to Caddy's static `try_files` like every other Reflex page and need **no Caddyfile change**. Reflex's own reserved routes (`/ping`, `/_event`, `/_upload`) are untouched.

Per `chat_ui/AGENTS.md`, every Reflex API used here must be verified against the **reflex-docs** skill rather than recalled from memory, and any run/compile/restart cycle must follow the **reflex-process-management** skill.

### 6.1 Design direction

Written against the **frontend-design** skill (pinned in `skills-lock.json`). That skill's first rule is that *"where the brief pins down a visual direction, follow it exactly — the brief's own words always win"*. The direction is already pinned: `chat_ui/theme.py` declares the **inspection ledger** — *"the chat is not a messaging app, it is a running record of traffic that passed through a checkpoint"*. The console is the rest of that ledger, so the palette and the faces are inherited, not re-proposed. The freedom left is in **structure**, and that is where the design decisions below are spent.

**Subject, audience, job.** The subject is a bound inspection register. The audience is one compliance admin who already knows what the columns mean. The single job of `/admin/audit` is *find the exceptions in the last hundred entries*; the single job of `/admin/stats` is *state the totals without overstating them*.

**What this design is refusing.** The template answer for an admin screen is a row of four KPI cards with big numbers over a striped data table, a left sidebar, and an accent colour. The skill names that pattern directly — *"a big number with a small label, supporting stats, and a gradient accent is the template answer, only use if that's truly the best option."* It is not the best option here: the admin's question is never "what is the total", it is "which rows are not cleared", and a card row answers the wrong question loudly at the top of the page. The console has **no cards, no fills, and no accent colour of its own**.

**Color** — four of the six inks already in `theme.py`, one per verdict, and nothing else:

| Token | Verdict | Role |
|---|---|---|
| `INK_CLEAR` | cleared | the majority case, and therefore the quietest |
| `INK_HELD` | held | duplicate — held, not rejected |
| `INK_DENIED` | denied | the one the eye must find first |
| `INK_FAULT` | fault | the harness itself failed |

`INK_UPSTREAM` and `INK_SELF` stay chat-only: the register cannot honestly distinguish an upstream failure (Section 6), and there is no "your own words" on this surface. Ground, rules and mute text come from `PAPER` / `CARD` / `RULE` / `RULE_SOFT` / `MUTE` / `SPINE` unchanged. The `TINT_*` fills are **not** used on the register — a hundred tinted rows would be a heat map of noise, and the tint's job in the chat was to isolate one panel among prose.

**Type** — the same three faces, with their weights inverted from the chat. In the transcript, `FONT_BODY` (Source Serif 4) carried the prose and the data face was the footnote. A register has almost no prose: it is timestamps, ids, hashes, counts and user agents. So **`FONT_DATA` (JetBrains Mono) becomes the dominant face**, `FONT_DISPLAY` (Archivo) sets the verdict tags, column heads and figure labels, and `FONT_BODY` is reserved for the two or three explanatory lines that state a scope. Monospace is not a stylistic choice here — the columns are numeric and must align down a hundred rows for scanning to work at all.

**Layout** — one column, no sidebar. The two views are peers reached from a rule-separated switch in the header, because there are exactly two and a sidebar for two destinations is furniture.

```
┌──────────────────────────────────────────────────────────────┐
│ HARNESS · REGISTER          Register | Summary    Sign out    │  masthead, hairline under
├──────────────────────────────────────────────────────────────┤
│ 100 most recent of 3,180        [cleared|held|denied|fault]   │  scope line + verdict filter
│ Refreshed 14:22:07              [ filter user / model / id ]  │
├─┬────────────────────────────────────────────────────────────┤
│▉│ 2m ago   a.torres   DENIED   —        —     PII  #3180     │  ← stamp margin
│ │ 2m ago   m.silva    cleared  gpt-4    412        #3179     │
│▉│ 5m ago   a.torres   HELD     —        —         #3178     │
│▉│ 6m ago   j.rios     FAULT    gpt-4    —         #3177     │
│ │ 6m ago   m.silva    cleared  gpt-4    380   PII  #3176     │
└─┴────────────────────────────────────────────────────────────┘
```

**Signature — the stamp margin.** A narrow fixed column down the left edge of the register carrying nothing but the row's verdict as a solid mark in its ink. Cleared rows leave it blank. The result is that a hundred rows resolve into a vertical stripe of exceptions: finding the three denied entries is a glance at an edge, not a read of a table. This is the chat's rail (`RAIL_X`, `GLYPH`, `SPINE` — already in `theme.py`) continued rather than reinvented, and it encodes something true — the skill's *"structural devices should encode something true about the content, not decorate it."* It is also the one place boldness is spent; everything around it stays hairlines and alignment.

**On the row identifiers.** The skill warns that numbered markers are only appropriate *"if the content actually is a sequence."* Here it is: `#3180` is the row's real `audit_id`, monotonic, and the exact string a user quotes out of the chat's success footer (PRD-004 STORY-010). It is a key, not a decoration, and it is the register's join back to the chat.

**Summary as a tally sheet, not a dashboard.** The figures are set as a ruled list, not a grid of cards. `blocked_duplicates` and `blocked_suspicious` are **indented beneath** `total_queries`, because they are a subset of it and indentation is the honest structural statement of that relationship — a card grid asserts that all four numbers are peers, which is false. The who/what facts (`unique_users`, `top_models`, `top_users`) sit in a separate ruled block, because they answer a different kind of question than the counts do. PII telemetry closes the sheet.

**Copy.** Per the skill: *"errors don't apologize, and they are never vague about what happened"*, and *"an empty screen is an invitation to act."* The fault panel names the read that failed and offers the retry; the gate says access was refused without saying why; the no-matches state names the filter that produced it and offers to clear it. An action keeps its name across the flow — the control labeled **Refresh** produces the line **Refreshed 14:22:07**, and **Sign out** returns the gate, not a "session ended" notice.

**Motion.** Effectively none, and deliberately. The only state change worth marking is a read completing, which is already marked by the refreshed stamp. The skill's own caution applies — *"extra animation contributes to the feeling that the design is AI-generated"* — and a register that animates while an admin is scanning it for exceptions is working against its one job. `prefers-reduced-motion` is respected for the loading indicator, which is the sole moving element.

## 7. Tools/Features

| Feature | Maps to | Detail |
|---|---|---|
| Token gate | Mirrors `require_admin_token` | `secrets.compare_digest` against `settings.ADMIN_TOKEN`; one generic failure message. |
| Register table | Consumes `list_audit_logs(limit=100)` | The 100 most recent rows with the cap stated against `count_audit_logs()`. |
| Verdict column | Reuses PRD-004 inks | Four verdicts derived per row; no two share a treatment. |
| Fault visibility | Reads `success` / `error_message` | Fields `AuditQueryEntry` does not project — the console's clearest gain over `curl /audit`. |
| Row disclosure | Consumes remaining `AuditLog` fields | `prompt_hash`, `suspicious_pattern`, PII entity types, full User-Agent. Previews excluded by policy. |
| Client-side filter & sort | New | Verdict multi-select plus free text over user / model / `audit_id`; no database round trip. |
| `audit_id` lookup | Closes PRD-004's footer loop | The `#127` a user quotes from the chat resolves to a row. |
| Summary sheet | Consumes every `StatsResponse` field | Nine figures, each with its scope; blocked counts also as shares. |
| Honest completion label | Fixes a naming defect | `success_rate` counts blocked rows as successes; the label says so. |
| PII telemetry surface | Consumes PRD-003 counters | `pii_detected_queries` and `top_pii_entities` rendered for the first time. |
| Manual refresh | New | Explicit action, last-refreshed stamp, control locked while loading. |
| Fault panel | New | A failed read is rendered, never swallowed into an empty table. |

## 8. Technology Stack

**Frontend / Console (unchanged stack, new pages)**
- Reflex — version as pinned in `chat_ui/requirements.txt`; plugins already configured in `rxconfig.py`: `TailwindV4Plugin`, `RadixThemesPlugin`, `SitemapPlugin`
- `rx.Base` for `AuditRow`, `rx.var` for the filtered view, `rx.foreach` for the table body, `rx.match` for verdict dispatch, `app.add_page(..., route=...)` for the two routes — every API confirmed against the **reflex-docs** skill before implementation, per `chat_ui/AGENTS.md`
- `chat_ui/theme.py` — the existing token system, extended in place. Per the **frontend-design** skill, the visual direction is inherited rather than re-proposed: the skill's own rule is that a pinned direction wins, and `theme.py`'s "inspection ledger" is that pin. New tokens the register needs (row height, stamp-margin width, row hover ground, a micro type step) are added to `theme.py` and nowhere else.
- No CSS framework beyond the Tailwind plugin already configured; the console adds no icon set, no chart library and no font beyond the three faces `FONTS_HREF` already loads

**Backend (consumed, not modified)**
- `app/db/database.py` — all ten read functions, unchanged
- `app/db/models.py::AuditLog` — the row dataclass, unchanged
- `app/config.py::settings.ADMIN_TOKEN` — unchanged
- `app/models/schemas.py`, `app/routers/admin.py` — unchanged; the console does not call the routers

**Standard library**
- `secrets.compare_digest` for the token check
- `asyncio.to_thread` for the SQLite offload
- `datetime` for relative timestamps, as in `chat_ui/formatting.py`

**Testing**
- `pytest` + `pytest-asyncio`, already in use
- No new dependencies in either `requirements.txt`

## 9. Security & Configuration

**No new environment variables.** `ADMIN_TOKEN` is consumed unchanged from `app/config.py`; the console adds no setting of its own.

**Token handling** — the token is compared with `secrets.compare_digest`, the same constant-time comparison `app/middleware/auth.py` uses, and is not stored beyond the Reflex session state. It is never written to `localStorage`, never placed in a URL, and never sent as a header from the browser, because the console reads the database in-process rather than calling its own HTTP endpoints. Sign-out clears the token, the loaded rows and the summary figures from state.

**No token oracle** — an empty, malformed or wrong token produces the same message. The gate reports that access was refused, not why.

**Raw previews stay unrendered** — `prompt_preview` and `response_preview` are read into the process (they are columns on the row `list_audit_logs` returns) but are not bound to any component. This holds PRD-004 Section 9's guarantee verbatim: no new surface exposes the audit log's raw previews. What the console renders is the `AuditQueryEntry` projection plus `success`, `error_message` and `suspicious_pattern`.

**Error detail exposure** — `error_message` is shown to an authenticated admin only. These are the same exception strings PRD-004 already shows to end users in the chat's error bubbles, so surfacing them behind a token gate is a narrower disclosure than the one already shipped.

**Read-only by construction** — `AdminState` imports only the read functions from `app/db/database.py`. `insert_audit_log` is not imported, and there is no write path from any admin page.

**Surface separation** — the console adds no capability to the chat, and the chat holds no admin state. An end user with no token reaching `/admin/audit` sees the gate and no data, because the read does not run until the gate passes.

**Reflex reserved routes** — `/ping`, `/_event`, `/_upload` remain reserved (PRD-002 Section 9). `/admin/audit` and `/admin/stats` are frontend routes and collide with nothing, so `tests/test_route_reservations.py` continues to hold unmodified.

**Deployment** — the `Caddyfile`'s `@backend_routes` matcher lists `/query /audit /stats /health` explicitly; `/admin/*` is not in it and falls through to the static `file_server`, which is correct. No deployment change is required.

## 10. API Specification

**No new or modified endpoints.** `POST /query`, `GET /audit`, `GET /stats` and `GET /health` retain their exact contracts from PRD-001 and PRD-003, and `require_admin_token` is unchanged.

The console reads `app/db/database.py` in-process, as PRD-002 Section 10 established for the chat. What changes is that the recorded data acquires a second reader — one that sees slightly more of the row than the REST projection does:

| Audit row field | `GET /audit` (`AuditQueryEntry`) | Admin console |
|---|---|---|
| `id` | `audit_id` | shown, and filterable |
| `timestamp` | shown (raw) | relative + absolute |
| `user_id` | shown | shown, sortable, filterable |
| `model_used` | `model` | shown, filterable |
| `tokens_used` | **not projected** | shown |
| `prompt_hash` | shown | on row disclosure |
| `was_duplicate_blocked` | shown | drives the **held** verdict |
| `suspicious_pattern` | flattened to a boolean | verdict **denied**, pattern on disclosure |
| `success` | **not projected** | drives the **fault** verdict |
| `error_message` | **not projected** | on row disclosure |
| `device` | shown | truncated in-row, full on disclosure |
| `pii_detected_input` / `_output` | shown | combined PII indicator, split on disclosure |
| `pii_entities` | shown | entity types on disclosure |
| `prompt_preview` | not projected | **deliberately not rendered** |
| `response_preview` | not projected | **deliberately not rendered** |

## 11. Success Criteria

**MVP is done when** an admin can open `/admin/audit`, enter the token, and answer "what was blocked, what failed, and how much of it touched PII" without a terminal — with every figure on screen labeled for what it actually counts.

Functional requirements:
- [ ] `/admin/audit` and `/admin/stats` render; `/admin` lands on the register
- [ ] An unauthenticated visit to either page shows the gate and loads no data
- [ ] A wrong token is refused with the same message as an empty one
- [ ] A correct token loads the register; sign-out clears rows and figures from state
- [ ] The register shows the 100 most recent rows and states the cap against the true total
- [ ] A duplicate-blocked row renders **held**, a pattern-blocked row **denied**, a `success = 0` row **fault**, everything else **cleared**
- [ ] A **fault** row discloses its `error_message`
- [ ] Filtering by verdict and by free text narrows the table without a database read
- [ ] An `audit_id` from a chat success footer resolves to exactly one row
- [ ] All nine `StatsResponse` figures render, each with its scope stated
- [ ] The completion figure's label reflects that blocked rows count as successes
- [ ] `pii_detected_queries` and `top_pii_entities` are visible on the summary
- [ ] A raised exception during a read renders a fault panel with a retry, not an empty table
- [ ] `prompt_preview` and `response_preview` appear nowhere in the rendered output

Quality indicators:
- [ ] `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_admin_auth.py`, `tests/test_db.py`, `tests/test_route_reservations.py` and `tests/test_chat_state.py` pass **unmodified** — the proof that `app/` and the chat are untouched
- [ ] `git diff main --stat` shows no file under `app/` changed
- [ ] No new dependency in either `requirements.txt`
- [ ] Every admin string resolves from the copy module; no literal user-facing text in a component
- [ ] Every colour and size resolves from `theme.py`; `tests/test_contrast.py` covers any new pairing
- [ ] Section 6.1's direction is met on screen: the stamp margin reads as a scannable stripe, the summary carries no card or fill, and no accent colour outside the four verdict inks appears
- [ ] Keyboard-reachable gate and filters with visible focus; the table scrolls within its own container rather than the page
- [ ] Responsive down to a narrow viewport, and `prefers-reduced-motion` honoured by the loading indicator — the **frontend-design** skill's quality floor, met without announcing it

## 12. Implementation Phases

**Phase 1 — Access and data**
- Goal: an authenticated state that holds the record.
- Deliverables: `admin_state.py` with the `compare_digest` gate, sign-out, the `asyncio.to_thread` read of all ten database functions, the loading flag, the catch-all error arm; `admin_models.py`; `admin_formatting.py` with verdict derivation.
- Validation: unit tests drive the state directly — right token authenticates, wrong and empty tokens produce the same error, sign-out empties the row list, a patched database function raising produces an error string and leaves rows untouched, and each of the four verdicts is asserted against a constructed `AuditLog`.

**Phase 2 — The register**
- Goal: the rows on screen.
- Deliverables: the `theme.py` tokens Section 6.1 names (row height, stamp-margin width, hover ground, micro type step); `admin_shell.py` (gate, masthead, two-view switch); `register.py` (stamp margin, table, verdict column, row disclosure, filters, sort, three empty states); `admin_copy.py`; route registration in `chat_ui.py`.
- Validation: the page renders against a seeded database; a row of each verdict is visually distinct; the stamp margin resolves into a scannable stripe with a hundred rows loaded; filtering to a single verdict and to an `audit_id` both narrow correctly; the previews appear nowhere in the rendered HTML.

**Phase 3 — The summary**
- Goal: the figures on screen, honestly labeled.
- Deliverables: `summary.py` as the ruled tally sheet — all nine figures, blocked counts indented beneath the total, scope labels, blocked shares, the rewritten completion label, PII telemetry.
- Validation: every `StatsResponse` field is present on screen; the shares match the counts; the completion label is asserted in a copy test so the wording cannot regress to "success rate"; the sheet renders no card, fill or accent colour.

**Phase 4 — Hardening**
- Goal: the console holds under failure and inspection.
- Deliverables: fault panel with retry on both pages, refresh with last-refreshed stamp and locked control, contrast assertions for new pairings, the palette-drift test from Risk 6, keyboard/focus/reduced-motion/narrow-viewport pass.
- Validation: the full suite green with PRD-001/003/004 tests unmodified; `git diff main --stat` shows nothing under `app/`; a read forced to raise renders the fault panel and recovers on retry; a self-critique pass against Section 6.1 — per the **frontend-design** skill's "take one last look and remove one accessory" — with anything that does not serve the register's one job cut.

## 13. Future Considerations

- **An `error_kind` on the audit row** — the highest-value follow-up. One column (or one non-flattened field on `AuditQueryEntry`) would let the register split **fault** into *upstream* and *internal*, matching the chat's six-outcome taxonomy exactly. Out of scope here only because this PRD does not touch `app/`.
- **Project `success` and `error_message` onto `AuditQueryEntry`** — `GET /audit` currently cannot report a failed query at all. Additive fields on the response model; the console already proves the data is there.
- **A truthful success metric** — `count_successful_queries()` counts `success = 1`, and `query_pipeline.py` logs duplicate-blocked and pattern-blocked rows as `success=True`, so `StatsResponse.success_rate` includes them. A separate `count_answered_queries()` (`success = 1 AND was_duplicate_blocked = 0 AND suspicious_pattern IS NULL`) would give the number the current label implies.
- **Pagination and date-range filters** — `list_audit_logs(limit=100)` is the only listing query. `limit`/`offset` and a `since`/`until` pair would turn the register from a window into a real browser of the record.
- **A time dimension on stats** — every `StatsResponse` figure is all-time. Bucketed counts would make trends renderable and turn the summary into something a chart could honestly serve.
- **Stable ordering** — `list_audit_logs` orders by `timestamp DESC` on a second-resolution TEXT column, so rows written in the same second tie arbitrarily. A secondary `id DESC` would make the register's order deterministic.
- **Reading the redacted prompt** — carried over from PRD-004 Section 13; if `redacted_prompt` were stored, the register could show what actually left the building alongside the hash.
- **`DATABASE_URL` as an absolute path** — carried over from PRD-004: the relative `sqlite:///harness_ai.db` resolves against the process cwd, so an admin console launched from a different directory would read a different database than the one the chat writes. A config/deployment fix, and one this PRD makes more visible by giving the record a reader.

## 14. Risks & Mitigations

**1. The gate is a render condition, not a route guard.**
A Reflex page's protection lives in what it chooses to render, so a mistake in the condition exposes the register rather than merely misrendering it.
*Mitigation*: the read itself is gated, not just the view — `load()` returns immediately unless `authenticated` is true, so an unauthenticated page has no data in state to leak regardless of what renders. Both pages assert the condition independently, and a state-level test drives `/admin/stats` without a token and asserts the row list is empty.

**2. The console reads a wider row than `/audit` returns.**
Reading `AuditLog` in-process brings `prompt_preview` and `response_preview` into the process, one binding away from being rendered.
*Mitigation*: the row model (`AuditRow`) is a deliberate projection that has no field for either preview, so the previews are dropped at the boundary and are not present on the object components receive. A test asserts `AuditRow` has no preview attribute, and a render test asserts seeded preview text appears nowhere in the output.

**3. Splitting *fault* on `model_used` would silently misclassify.**
The obvious way to separate an upstream failure from an internal one is to check whether a model was recorded — and it is wrong, because the output-side `PiiRedactorError` arm logs one.
*Mitigation*: Section 6 fixes *fault* as a single verdict with `error_message` on disclosure, and the reasoning is recorded there so the "improvement" is not reintroduced later. Section 13 records the schema change that would make the split honest.

**4. All-time figures next to a 100-row window invite a wrong reading.**
A summary that says `3,180 queries` beside a register showing 100 rows reads as a contradiction, or worse, as a filtered view of the same set.
*Mitigation*: scope is a required part of every figure's label, and the register states its cap against the true total (`100 most recent of 3,180`). The completion label is covered by a copy test so its wording cannot drift back to "success rate".

**5. A 100-row table with client-side filtering and sorting is a lot of state to push over the Reflex event protocol.**
Every keystroke in the filter re-evaluates a computed var over the full row list.
*Mitigation*: 100 rows is the hard ceiling — there is no query that returns more — and the filtered view is a computed var over data already in state, so no database read and no round trip to `app/` occurs per keystroke. If it still proves heavy, debouncing the filter input is a UI-local change requiring nothing under `app/`.

**6. An admin screen drifts toward the dashboard default.**
Section 6.1 refuses cards, fills and an accent colour, but "admin console" is the single strongest pull toward the KPI-cards-over-striped-table layout in the whole design space — and the drift arrives one reasonable-looking component at a time, usually as a Radix card imported for convenience.
*Mitigation*: the refusals are written into Section 4's scope and Section 11's quality bar as checkable items, not left as taste. A component test asserts the register renders no element carrying a `TINT_*` value and no colour outside the four verdict inks plus the ground tokens, so the drift fails a test rather than a review.

## 15. Appendix

**Related documents**
- [PRD-001 — Harness IA](../PRD-001-harness-ia/PRD.md) — defines the audit schema, `GET /audit`, `GET /stats` and `require_admin_token`, all consumed unchanged here.
- [PRD-002 — Embedded Chat UI (Reflex)](../PRD-002-reflex-chat-ui/PRD.md) — establishes the single-process/single-port architecture, the in-process consumption pattern and the reserved-route constraint this PRD inherits. Its Section 13 first deferred the admin dashboard.
- [PRD-003 — PII Redaction](../PRD-003-pii-redaction/PRD.md) — adds `pii_detected_input`, `pii_detected_output`, `pii_entities` and the two stats counters this console renders for the first time.
- [PRD-004 — Chat UI Redesign](../PRD-004-chat-ui-redesign/PRD.md) — the immediate predecessor. Its outcome vocabulary, `theme.py` token system, centralized copy, `asyncio.to_thread` offload and catch-all error arms are all reused here. Its Section 4 out-of-scope entry and Section 13 follow-up "Admin dashboard — a Reflex page over `/audit` and `/stats`" is the item this PRD closes.

**Code dependencies (read, not modified)**
- `app/db/database.py` — `list_audit_logs`, `count_audit_logs`, `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `count_pii_detected_queries`, `top_models`, `top_users`, `top_pii_entities`
- `app/db/models.py` — `AuditLog`
- `app/config.py` — `settings.ADMIN_TOKEN`
- `chat_ui/chat_ui/theme.py` — the design tokens

**Tests that must pass unmodified**
`tests/test_admin_auth.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_db.py`, `tests/test_route_reservations.py`, `tests/test_chat_state.py`, `tests/test_copy.py`, `tests/test_contrast.py`

**Skills referenced**: frontend-design, reflex-docs, reflex-process-management
