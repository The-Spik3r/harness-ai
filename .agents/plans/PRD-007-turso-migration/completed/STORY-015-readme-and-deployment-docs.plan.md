---
story: STORY-015
prd: PRD-007
slug: readme-and-deployment-docs
title: "README: correct the persistence claim, the env table, and document multi-instance deployment"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-02
---

# Plan: README — correct the persistence claim, the env table, and document multi-instance deployment

## Summary

The README still describes the system PRD-007 removed. Exploration found the damage is wider than the
two lines the story names: **seven** places assert SQLite or a volume (`:74`, `:78`, `:121`, `:177`,
`:214`, `:428`, plus a `Requirements` section that never mentions a database at all), and **three more
are actively broken instructions** — both quickstarts tell a reader to `cp .env.example .env` and set
only `OPENROUTER_API_KEY` and `ADMIN_TOKEN`, which now produces a startup error because `DATABASE_URL`
has no default (`app/config.py:41`); and the in-container pytest command at `:386` fails outright
(STORY-014 report, Finding 2). This plan corrects all of them, adds one new `## Persistence &
Deployment` section carrying the multi-instance, resilience and migration-tool material the story asks
for, and rewrites `## Running Tests` around the local libSQL dev server.

Two things this plan refuses to do quietly. First, it does **not** let the README imply the topology
work is finished: PRD Section 4 puts "actually running multiple instances in production" out of scope
and Section 13 names load balancing, health checks and Reflex websocket session affinity as separate
work, so the new section says *the database blocker is gone* and lists what is not delivered. Second,
it documents the in-container test command **with** the `DATABASE_URL` override that STORY-014's
Finding 1 proved necessary — the suite there read a production database — with a one-line warning
pointing at that finding, because a documented command that can reach production is worse than no
documented command.

`.env.example` also changes: it carries an **uncommitted duplicate** `TURSO_AUTH_TOKEN=` at `:57-58`
(already documented at `:9-11`), no trailing newline, and — because `Settings` is `extra_forbidden` —
a stray key there is a hard startup crash rather than an ignored line. STORY-014's report left that
edit "for its author to resolve"; this story is the author.

## User Story

As a platform engineer
I want the README to describe how the system actually persists data
So that I do not configure a deployment against instructions that describe a design the code no longer has

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-015-readme-and-deployment-docs.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 4 (in/out of scope), Section 11 (functional requirements), Section 12 Phase 4, Section 13 (Future Considerations), Section 14 Risk 5
- Handoffs this plan consumes:
  - `.agents/reports/PRD-007-turso-migration/STORY-014-deployment-cutover.report.md` — Finding 1 (the suite can reach production), Finding 2 (the README's pytest command is broken), Finding 3 (`up` without `--build` resurrects a stale image), Finding 4 (no `libsql` wheel for Python 3.14 on Windows), Finding 5 (`.env.example`'s duplicate key; `chat_ui/.env` drift)
  - `.agents/reports/PRD-007-turso-migration/STORY-013-data-migration-script.report.md` — the migration script's real CLI, and the "no `GET /audit/{id}` route" correction
  - `.agents/reports/PRD-007-turso-migration/STORY-008-startup-guard.report.md` — the guard's message text, recorded verbatim in STORY-014's report

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (documentation correctness) |
| Complexity | MEDIUM (the story says small; ten distinct README defects, one new section, and an AC that requires a live end-to-end run) |
| Systems Affected | `README.md`, `.env.example`. **No change to `app/`, `chat_ui/`, `scripts/`, `tests/`, `Dockerfile`, `docker-compose.yml`.** |
| Story | STORY-015 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed and read: it holds exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one" — aesthetic direction, typography, layout. This story edits two text files and renders no UI. The story frontmatter carries `skills: []`, and PRD Section 15 reaches the same conclusion for the whole epic. | none |

No skill's `allowed-tools` or workflow constraints apply, so no task below is gated by one.

---

## Patterns to Follow

### The env table is a real four-column table — extend it, in place, in the existing order

```markdown
<!-- SOURCE: README.md:210-215 -->
| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | API key used to call the upstream LLM provider via OpenRouter. |
| `ADMIN_TOKEN` | Yes | — | Break-glass bearer token that always resolves to the `admin` role, independent of the `users` table. Not the primary auth mechanism — issue individual tokens with `scripts/manage_users.py` instead. |
| `DATABASE_URL` | No | `sqlite:///harness_ai.db` | SQLite connection string for the `audit_logs` database. |
```

Required-with-no-default is spelled `Yes` / `—`, exactly as the two rows above it. `DATABASE_URL`
stays in its current row position; `TURSO_AUTH_TOKEN` goes directly beneath it.

### Prose sentences carry their own justification, and name the PRD when the reason is a decision

```markdown
<!-- SOURCE: README.md:180 -->
The image bakes `en_core_web_lg` in at build time, so no model download happens at container start —
without it, a fresh container would pull ~400 MB before serving its first request. ... Accepted
tradeoff — see PRD-003 Risk 5.
```

The README already cites PRDs for deliberate tradeoffs. The resilience sentence (Risk 5) and the
out-of-scope multi-instance list (Sections 4 and 13) follow this existing convention rather than
inventing a new one.

### Troubleshooting entries are a bold verbatim error string, then a paragraph that says what to do

```markdown
<!-- SOURCE: README.md:410-411 -->
**`RbacNotBootstrappedError: RBAC_ENABLED=true but no active users exist` at startup**
Bootstrap at least one user: `python scripts/manage_users.py create-user --user-id <id> --role admin`.
This is required even when `ADMIN_TOKEN` is set — break-glass does not satisfy the bootstrap guard
(`app/services/authz.py`'s `check_bootstrap()`). ...
```

The three new entries mirror this exactly: the real string the code emits, then the fix and the file
that owns it.

### The error strings to quote are the ones the code actually raises

```python
# SOURCE: app/config.py:80-87
raise ValueError(
    "DATABASE_URL must name a libSQL endpoint, not a file. Replace the "
    "'sqlite:' URL with 'libsql://<database>-<org>.turso.io' (or "
    "'http://127.0.0.1:8080' for the local dev server). PRD-007 removed "
    ...
```

```python
# SOURCE: app/config.py:105-109
raise ValueError(
    "TURSO_AUTH_TOKEN is required when DATABASE_URL names a remote "
    "endpoint (libsql:// or https://). The local libSQL dev server on "
    "http:// takes no token."
)
```

`DatabaseUnreachableError`'s text is recorded verbatim in STORY-014's report (its
"build-without-a-database" section) and must be re-confirmed against the running code in Task 11, not
copied on trust.

### The dev-server invocation already has one canonical spelling — reuse it, do not re-type it

```python
# SOURCE: tests/conftest.py:27-31
#     docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
#       ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
#
# Point the suite somewhere else with `HARNESS_TEST_LIBSQL_URL`.
```

The digest pin is deliberate (STORY-001's driver decision). The README copies it character for
character; a paraphrased or `:latest` variant would be a second, drifting source of truth.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | Ten defects across seven sections, plus one new `## Persistence & Deployment` section and its TOC entry |
| `.env.example` | UPDATE | Remove the duplicate `TURSO_AUTH_TOKEN` at `:57-58`; restore the trailing newline |

Nothing is created. Nothing is deleted.

---

## Tasks

Execute in order. Tasks 1–10 are edits; Tasks 11–14 are the verification the story's AC 5 and AC 7
require to be **done**, not read.

### Task 1: `.env.example` — remove the duplicate `TURSO_AUTH_TOKEN`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Delete lines 56–58 (the blank line, `# Turso authentication token`, and the second
  bare `TURSO_AUTH_TOKEN=`). The canonical entry stays at `:9-11`, where it already explains that the
  token is required for `libsql://` / `https://` and empty for the local `http://` dev server. Ensure
  the file ends with a newline after `PII_NLP_MODEL=en_core_web_lg` — it currently does not
  (`\ No newline at end of file` in `git diff`).
- **Mirror**: `.env.example:4-11` — every entry is a comment block then one `KEY=value`, never a bare
  key with a second comment elsewhere.
- **Why it matters, not just tidiness**: `Settings` is `extra_forbidden`, so a stray or misspelled key
  copied from this template into a real `.env` is a hard startup crash (STORY-014 report, Finding 5).
- **Validate**: `grep -c "^TURSO_AUTH_TOKEN" .env.example` → `1`; `tail -c 1 .env.example | xxd` shows
  `0a`.

### Task 2: README Architecture diagram — the two `SQLite` labels

- **File**: `README.md` (`:74`, `:78`)
- **Action**: UPDATE
- **Implement**: `◄──── SQLite (users)` → `◄──── Turso (users)`; `◄──── SQLite (audit_logs)` →
  `◄──── Turso (audit_logs)`. Both sit inside a fixed-width ASCII box drawing — **the box borders must
  still line up**. `Turso` is one character shorter than `SQLite`, so the arrow text shortens and the
  `│` column to its left is untouched; verify by eye after the edit, not by assumption.
- **Mirror**: `README.md:60-108` — the existing diagram's alignment is the pattern.
- **Validate**: `sed -n '60,110p' README.md` renders with every `│` in a straight column.

### Task 3: README Features table and Roadmap — the two remaining "SQLite" assertions

- **File**: `README.md` (`:121`, `:428`)
- **Action**: UPDATE
- **Implement**: Two edits, grouped because they are the same claim in two voices.
  - `:121` (Features table): "writes one row to SQLite: user, device, …" → "writes one row to the
    `audit_logs` table in Turso: user, device, …". Change nothing else in the row — the PII/IP
    sentence that follows is still accurate.
  - `:428` (Roadmap → Shipped): `- [x] Full audit logging (SQLite)` → `- [x] Full audit logging
    (Turso / libSQL)`. This is a *shipped* checklist, so it must name what shipped, not what was
    replaced.
- **Also confirmed during exploration, and requiring no edit**: STORY-013's report forwarded a
  "no `GET /audit/{id}` route" correction to this story. The README never claims one —
  `grep -n "audit" README.md` shows `### GET /audit` (`:312`) as a list endpoint carrying `audit_id`,
  which is accurate. Record this in the report as checked-and-clean rather than silently dropping the
  handoff.
- **Validate**: Both rows/bullets still render (no unescaped `|` introduced); `grep -n "SQLite"
  README.md` → no hits after Tasks 2, 3 and 9.

### Task 4: README Requirements — name the database as a requirement

- **File**: `README.md` (`:128-136`)
- **Action**: UPDATE
- **Implement**: Add two bullets to the existing list, in the existing terse style:
  - A Turso database (or any libSQL endpoint) — `DATABASE_URL` has no default and the application will
    not start without one
  - For running the test suite only: a local libSQL server (see [Running Tests](#running-tests)) — no
    Turso account needed

  Also qualify the existing `Python 3.9+` bullet: the pinned `libsql==0.1.11` ships wheels for a
  bounded set of CPython versions, and on an interpreter with no wheel `pip install` falls back to
  building the Rust sdist from source, which needs a working toolchain. The Docker image is
  `python:3.11`. **Verify the wheel range against the real index before writing a number** —
  STORY-014's Finding 4 established only the 3.14-on-Windows failure, not the full supported set.
- **Mirror**: `README.md:130-136` — bullets are one line, no sub-structure.
- **Validate**: `pip index versions libsql` or the PyPI files listing confirms the stated range; Task
  12's fresh read-through confirms the bullets read cleanly.

### Task 5: README Quickstart — Local — make the instructions actually work

- **File**: `README.md` (`:138-158`)
- **Action**: UPDATE
- **Implement**: The `.env` comment currently reads `# edit .env: set OPENROUTER_API_KEY and
  ADMIN_TOKEN to real values`. It must also name `DATABASE_URL` and `TURSO_AUTH_TOKEN`, because
  without them `python app.py` raises a Pydantic validation error before anything else happens. Add
  one short paragraph after the code block: a local libSQL server is enough for a first run
  (`DATABASE_URL=http://127.0.0.1:8080`, no token); a Turso database needs both values. Link the new
  `#persistence--deployment` section for provisioning.
- **Mirror**: `README.md:150-156` — a code block, then a short paragraph of consequence, then the next
  block.
- **Validate**: Task 12 executes this block verbatim.

### Task 6: README Quickstart — Docker — same correction, plus `--build`

- **File**: `README.md` (`:160-181`)
- **Action**: UPDATE
- **Implement**: Same `.env` comment correction as Task 5. The `docker-compose up -d --build` line
  already carries `--build`; add a one-sentence note that `--build` is not optional after pulling
  changes — compose reuses an existing image, and a pre-PRD-007 image will now crash at boot rather
  than silently write to a file (STORY-014 report, Finding 3). Note that `DATABASE_URL` and
  `TURSO_AUTH_TOKEN` reach the container through `env_file: .env`, like the other two secrets.
- **Validate**: `docker compose config` still shows `env_file` and no `environment:` block — confirming
  the README matches the compose file it describes.

### Task 7: README `:177` — the persistence claim (story AC 1)

- **File**: `README.md` (`:177`)
- **Action**: UPDATE
- **Implement**: Replace *"The SQLite database persists across container restarts via a named volume —
  audit history is not lost on redeploy."* with an accurate two-sentence replacement: state lives in
  Turso, reached over the network; the container holds no database and no volume is involved, so
  container lifecycle — restart, rebuild, `docker compose down -v` — does not touch the audit history.
  Point at the new section for the deployment consequences. Keep it to the same weight as the line it
  replaces; the detail belongs in Task 8's section.
- **Evidence, because it was measured**: STORY-014 recorded 17 rows before `down -v` and 17 after. The
  README states the guarantee, not the run.
- **Validate**: `grep -n "named volume" README.md` → no hits.

### Task 8: README — new `## Persistence & Deployment` section (story AC 1, AC 3, and the migration-tool note)

- **File**: `README.md` — insert between `## Chat UI` (ends `:206`) and `## Environment Variables`
  (`:208`)
- **Action**: UPDATE (new section)
- **Implement**: Four subsections, in this order. Each one exists because an acceptance criterion or a
  PRD section asks for it — none is filler.

  1. **Where state lives.** `audit_logs` and `users` live in a Turso (libSQL) database reached over
     the network. There is no `.db` file in the repository, the image, or the compose stack, and no
     local-file fallback: a `sqlite:` `DATABASE_URL` is a startup error, by design (PRD-007 Section 2).
     Provisioning: create a database, take its `libsql://…` URL and an auth token, put both in `.env`.

  2. **Multiple instances.** State the fact plainly and then bound it. Several instances may now share
     one database — that was the point of the migration, and `init_db()` converges when they start
     simultaneously (STORY-007). Then, explicitly, **what this does not include**, as a short list so a
     reader cannot skim past it: a load balancer, health checks, and Reflex websocket session affinity
     for the chat UI are separate work (PRD-007 Section 4 "Out of Scope", Section 13). The chat UI
     holds a websocket per session, so putting instances behind a round-robin balancer without
     affinity is not a supported configuration today. Note that the two-instance proof is STORY-016 and
     is not yet done — do not write "verified".

  3. **The database is a hard dependency of every request.** One honest paragraph, per the story's
     Technical Notes and PRD Section 14 Risk 5: with the file gone, every `POST /query` makes network
     round trips for the duplicate check and the audit write, and MVP scope deliberately excludes
     retry, circuit-breaker and buffering behavior. A transient database outage therefore fails
     requests rather than degrading. Name the one existing exception — `duplicate_checker` still
     degrades gracefully rather than failing the query — and say resilience is the first item in
     PRD-007 Section 13.

  4. **Migrating an existing SQLite deployment.** `scripts/migrate_to_turso.py` copies `audit_logs`
     and `users` from a legacy `.db` file into the database named by `DATABASE_URL`. Document the real
     CLI, taken from the script's own docstring (`scripts/migrate_to_turso.py:31-34`), not invented:

     ```
     python scripts/migrate_to_turso.py --source harness_ai.db --dry-run
     python scripts/migrate_to_turso.py --source harness_ai.db
     ```

     State the four operator-relevant properties the script actually has, each verifiable in its
     source: the source file is opened read-only and is never modified; a non-empty destination is
     refused and there is no `--force`, so **one file, one run**; verification covers counts, row
     content by column name, and `audit_logs.id` preservation, and a mismatch exits non-zero; delete
     the source file only after that run succeeds. If a Docker volume holds the live database rather
     than the repository, extract it first — that is what STORY-014 hit in practice.

- **Also update the Table of Contents** (`:17-35`) with
  `- [Persistence & Deployment](#persistence--deployment)` between `Chat UI` and
  `Environment Variables`. Two hyphens in the anchor — GitHub drops the `&` and keeps both surrounding
  spaces as hyphens; check it against the existing `[Quickstart — Local](#quickstart--local)` entry,
  which has the same shape and is known good.
- **Mirror**: `README.md:183-206` (`## Chat UI`) — a `##` heading, prose, bolded run-in labels for
  sub-points, and a `**Known limitations (MVP)**` list. Subsection 2's out-of-scope list follows that
  precedent directly.
- **Validate**: TOC link resolves in the rendered preview (Task 13).

### Task 9: README `:214` — the env table (story AC 2)

- **File**: `README.md` (`:214`)
- **Action**: UPDATE
- **Implement**: Replace the `DATABASE_URL` row and add two more, in this order:

  | Variable | Required | Default | Description |
  |---|---|---|---|
  | `DATABASE_URL` | Yes | — | libSQL endpoint for the `audit_logs` and `users` database: `libsql://…`, `https://…`, or `http://127.0.0.1:8080` for the local dev server. No default, and a `sqlite:` value is a startup error — PRD-007 removed the local-file path deliberately. |
  | `TURSO_AUTH_TOKEN` | Yes for remote | — | Bearer token for the database. Required whenever `DATABASE_URL` is `libsql://` or `https://`; unused by the local `http://` dev server, which takes no token. Never logged — error messages quote the URL scheme only. |
  | `DB_BOOTSTRAP_ENABLED` | No | `true` | Whether startup probes the database and applies the schema. The only sanctioned `false` is the Docker builder stage. `false` in a running deployment boots an application whose schema was never created. |

  Wording for all three is drawn from `app/config.py:36-58` and its validators; do not paraphrase the
  `sqlite:`-is-an-error rule into something softer. `DB_BOOTSTRAP_ENABLED` is included because it is a
  real setting a reader meets in `.env.example:13-18` and in the Dockerfile, and an undocumented
  boolean that can silently produce a schema-less deployment is exactly the gap this story exists to
  close.
- **Also**: the sentence at `:230` ("All four PII settings are read once at startup") still holds —
  leave it. The `See .env.example` pointer at `:232` needs nothing after Task 1.
- **Validate**: `grep -n "sqlite:///harness_ai.db" README.md` → no hits.

### Task 10: README `## Running Tests` — the dev server, and the in-container command (story AC 4, AC 7)

- **File**: `README.md` (`:373-388`)
- **Action**: UPDATE
- **Implement**: Rewrite the section. Keep the existing spaCy-model paragraph unchanged. Add, before
  the `pytest` invocation, the local libSQL server the suite needs — **copied verbatim** from
  `tests/conftest.py:27-31`, digest pin included:

  ```bash
  docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
    ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
  ```

  State plainly, because the story's AC 4 asks for it: **no Turso account is needed to run the tests**
  — the server is local, takes no token, and `HARNESS_TEST_LIBSQL_URL` repoints the suite if 8080 is
  taken (`tests/conftest.py:42`).

  Then correct the in-container command. As documented it fails, because `127.0.0.1` inside the
  container is the container's own loopback:

  ```bash
  docker-compose run --rm \
    -e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080 \
    -e DATABASE_URL=http://host.docker.internal:8080 \
    harness-ai pytest tests/ -v
  ```

  Both variables are required, for **different** reasons — say so in one sentence each rather than
  leaving a reader to guess which is redundant:
  - `HARNESS_TEST_LIBSQL_URL` points the fixtures at a server they can reach.
  - `DATABASE_URL` overrides the one `env_file: .env` injects. Without it the value inherited from
    `.env` wins over `conftest.py`'s `setdefault`, and one test — which calls `monkeypatch.undo()` and
    thereby reverts the autouse safety fixture — runs against **the database `.env` names**. STORY-014
    observed exactly this: the suite read a production database (reads only; verified afterwards).
    Until that is fixed, always pass the override.

  Add a Linux note: `host.docker.internal` needs `--add-host=host.docker.internal:host-gateway`.

  This answers AC 7's "or the README says what changed" by making the command work **and** saying what
  changed. Also note the two known collection failures (`test_pii_badge.py`,
  `test_success_metadata_footer.py` → `'chat_ui.chat_ui' is not a package`) and the whole-suite
  `STREAM_EXPIRED` idle-stream issue, so a contributor whose first full run is not clean knows it is
  not their change — both are open, tracked in the PRD-007 index, and **not** all `STREAM_EXPIRED`
  (the STORY-013 report explicitly corrects that conflation).
- **Validate**: Task 11 runs both documented commands.

### Task 11: Verify every command and every error string this README now claims

- **File**: — (verification)
- **Action**: EXECUTE
- **Implement**: The host cannot run this project's Python (STORY-014, Finding 4: no `libsql` wheel for
  Python 3.14 on Windows, and the sdist's Rust build fails at `link.exe`), so every Python step runs in
  a `python:3.11` container, matching the Dockerfile. Run and capture:
  1. The dev-server `docker run` exactly as written → server responds on 8080.
  2. `pytest tests/ -v` against it (per-module, given the known `STREAM_EXPIRED` idle-stream issue) →
     matches the recorded baseline, no new failure.
  3. The corrected in-container command → runs, and `tests/test_db.py` passes 97 as STORY-014 measured
     with the override in place.
  4. `DATABASE_URL=sqlite:///harness_ai.db` → capture the exact `ValueError` text.
  5. A `libsql://` URL with `TURSO_AUTH_TOKEN` empty → capture the exact `ValueError` text.
  6. A reachable-scheme URL with nothing listening → capture the exact `DatabaseUnreachableError` text.
- **Validate**: Every string quoted in the README's Troubleshooting section (Task 14) is a paste of
  captured output, not a reconstruction.

### Task 12: Follow the README end to end against a fresh database (story AC 5)

- **File**: — (verification)
- **Action**: EXECUTE
- **Implement**: A **fresh** database, not the production one — production already holds 17 rows and a
  bootstrapped `admin`, so it cannot exercise the from-zero path the README describes. Provision a
  scratch Turso database (`turso db create harness-ai-readme-check`, then `turso db show --url` and
  `turso db tokens create`), point a throwaway `.env` at it, and execute the **Docker** quickstart
  verbatim, reading only the README: `cp .env.example .env` → fill the four values →
  `docker-compose up -d --build` → `create-user` → `curl /health` → `POST /query` with the printed
  token → confirm the audit row. Then drop the scratch database.
  - **If a second Turso database cannot be provisioned** (account limits, no CLI), do **not** silently
    substitute: run the identical flow against a freshly reset local libSQL server, and separately
    confirm the remote path boots and serves against the existing Turso credentials. The report must
    then say plainly that AC 5 was met in two halves rather than one, and which half was which. An
    honest split beats a claimed run.
  - `POST /query` calls OpenRouter and costs a token. Use the cheapest allowlisted model.
- **Validate**: `/health` → `{"status":"ok"}`; `POST /query` → 200 with an `audit_id`; `GET /audit`
  shows the row. Paste all three into the report.

### Task 13: The `grep` gate and the rendered read-through (story AC 6)

- **File**: — (verification)
- **Action**: EXECUTE
- **Implement**: Run `grep -rn "sqlite\|harness_data\|harness_ai.db" README.md`. Every surviving hit
  must be a deliberate historical or operational reference and must be **listed with its
  justification** in the report, the way STORY-014's report enumerated its `sqlite` sweep. Expected
  survivors: the `sqlite:`-is-a-startup-error rule (the `DATABASE_URL` row and the new section — the
  error *is* the feature), the migration subsection describing what `--source harness_ai.db` reads, and
  the Troubleshooting entry for that error. Any other hit is a miss to fix, not a survivor to explain.
  Then read the rendered file top to bottom: TOC links resolve, the architecture diagram is aligned,
  the env table has four columns in every row.
- **Validate**: The report carries the grep output and a one-line justification per hit.

### Task 14: Troubleshooting — three new entries, in the existing shape

- **File**: `README.md` (`:391-420`)
- **Action**: UPDATE
- **Implement**: Add three entries using the strings captured in Task 11, placed after the
  `OPENROUTER_API_KEY` entry, since these are also startup-configuration failures:
  1. `DATABASE_URL must name a libSQL endpoint, not a file` — you have a pre-PRD-007 `.env`; replace
     the `sqlite:` value. Point at the env table.
  2. `TURSO_AUTH_TOKEN is required when DATABASE_URL names a remote endpoint` — a `libsql://` or
     `https://` endpoint needs the token; the local `http://` dev server does not.
  3. `DatabaseUnreachableError: Cannot reach the database at …` — the endpoint is unreachable or the
     credential is rejected. This is deliberate: there is no local-file fallback to degrade to. Check
     `DATABASE_URL`, the token, and network reachability from this host.

  Also extend the existing **Docker container exits immediately** entry with the stale-image case — a
  container running a pre-PRD-007 image fails at boot in `sqlite3.connect`, a line the code no longer
  has; `docker-compose up -d --build` is the fix (STORY-014, Finding 3).
- **Mirror**: `README.md:410-411` — bold verbatim string, then the fix and the file that owns it.
- **Validate**: Task 13's read-through.

---

## Out of Scope for This Story (named, so the omission is a decision)

- **Fixing the test-safety defect** (STORY-014 Finding 1: `conftest.py:55`'s `setdefault` cannot
  override an inherited `DATABASE_URL`, and `tests/test_db.py:1809`'s `monkeypatch.undo()` reverts the
  autouse safety fixture). This story **documents the mitigation**; the fix needs code plus a
  regression test, and STORY-014's report says it should be scheduled before STORY-016. Recommend
  filing it; do not fix it here.
- **`chat_ui/.env` consolidation.** STORY-014's Finding 5 routed it here, but the file is untracked
  local dev state, not documentation. The right resolution is a code/config decision about whether
  Reflex's `chat_ui/` CWD should read the root `.env` at all. Outside this story's two-file blast
  radius; note it in the report.
- **`docker-compose.yml` `extra_hosts`.** The Linux `host.docker.internal` gap is documented as a
  command-line flag rather than fixed in the compose file, which STORY-014 just settled.
- **Fixing the `'chat_ui.chat_ui' is not a package` collection error or the `STREAM_EXPIRED` idle
  stream.** Both are documented as known, both are open, neither is a documentation defect.

---

## Risks + Mitigations

**R1 — A README that reads as "multi-instance is done."** The single most likely way this story does
harm: an operator deploys three instances behind a round-robin balancer, and the chat UI's websockets
break. *Mitigation:* Task 8's subsection 2 is written as fact-then-bound, with the out-of-scope items
as a list rather than a trailing clause, and STORY-016 named as not-yet-done.

**R2 — Documenting a command that can reach production.** Task 10's in-container command is exactly the
one that read production in STORY-014. *Mitigation:* the `DATABASE_URL` override is part of the
documented command, not an optional footnote, and the reason is stated so a reader who drops it knows
what they are risking.

**R3 — Quoting an error string that has drifted.** Three quoted strings come from code that changed
this epic. *Mitigation:* Task 11 captures all six from a running process before Task 14 writes any of
them.

**R4 — AC 5 cannot be met as literally written.** A fresh Turso database may not be provisionable.
*Mitigation:* Task 12 pre-commits to the split fallback **and** to saying so in the report, rather than
quietly running against production or the dev server and calling it done.

**R5 — Diagram misalignment.** An ASCII box edited without care is easy to break. *Mitigation:* Task 2's
validation is a visual column check, and Task 13 re-reads the rendered file.

---

## End-to-End Tests

- [ ] Local libSQL dev server starts from the README's `docker run` line verbatim
- [ ] `pytest tests/` against it matches the recorded baseline (no new failure)
- [ ] The README's corrected in-container pytest command runs; `tests/test_db.py` → 97 passed
- [ ] `sqlite:` `DATABASE_URL` → the quoted `ValueError`, verbatim
- [ ] Remote `DATABASE_URL` with no token → the quoted `ValueError`, verbatim
- [ ] Unreachable endpoint → the quoted `DatabaseUnreachableError`, verbatim
- [ ] Docker quickstart followed verbatim against a fresh database → `/health` 200, `POST /query` 200
      with an `audit_id`, `GET /audit` shows the row
- [ ] `grep -rn "sqlite\|harness_data\|harness_ai.db" README.md` → every hit justified in writing
- [ ] TOC links resolve; architecture diagram aligned; env table well-formed

## Validation

```bash
grep -rn "sqlite\|harness_data\|harness_ai.db" README.md   # every hit deliberate and justified
grep -n "named volume" README.md                            # no hits
grep -c "^TURSO_AUTH_TOKEN" .env.example                    # 1
git diff --stat                                             # exactly README.md and .env.example
docker compose config                                       # still matches what the README describes
```

---

## Acceptance Criteria

(Copied from story `STORY-015`)

- [ ] Given `README.md:177`, when it is read, then the named-volume persistence claim is replaced by an accurate description: state lives in Turso, no volume is involved, and container lifecycle no longer affects the audit history.
- [ ] Given the environment-variable table at `README.md:214`, when it is read, then `DATABASE_URL` is documented as a libSQL endpoint, required, with no default, and `TURSO_AUTH_TOKEN` is documented alongside it as a required secret for remote endpoints.
- [ ] Given the README, when a reader looks for multi-instance guidance, then it states that multiple instances may now share one database, and names what this PRD did **not** deliver: load balancing, health checks, and Reflex websocket session affinity are separate work (PRD Section 4, Section 13).
- [ ] Given a new contributor, when they follow the README to run the test suite, then it tells them how to obtain a local libSQL server and confirms no Turso account is needed.
- [ ] Given the README's setup instructions, when they are followed end to end against a fresh Turso database, then the application starts and serves a query. Verify by doing it, not by reading.
- [ ] Given `grep -rn "sqlite\|harness_data\|harness_ai.db" README.md`, when it runs, then the only hits are deliberate historical references — for example describing `scripts/migrate_to_turso.py`'s purpose — and each is accurate.
- [ ] Given `docker-compose run harness-ai pytest tests/`, when the README documents it, then the documented command actually works, or the README says what changed.
- [ ] All tasks completed
- [ ] Blast radius is exactly two files: `README.md` and `.env.example`
- [ ] Follows existing patterns
