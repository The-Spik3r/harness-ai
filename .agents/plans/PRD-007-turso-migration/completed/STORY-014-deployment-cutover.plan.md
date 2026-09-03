---
story: STORY-014
prd: PRD-007
slug: deployment-cutover
title: "Cutover: remove the harness_data volume, the build placeholder, and harness_ai.db"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-02
---

# Plan: Cutover — remove the `harness_data` volume, the build placeholder, and `harness_ai.db`

## Summary

Two files change, two are deleted, and the ordering is the story. `docker-compose.yml` loses its
`environment:` block, its `harness_data` mount and the top-level `volumes:` key, so the Turso
connection arrives through the `env_file: .env` mechanism that already carries `OPENROUTER_API_KEY`
and `ADMIN_TOKEN`. The Dockerfile's builder-stage placeholder `DATABASE_URL=sqlite:///:memory:` —
which STORY-005 turned into a hard validation error, leaving the image build red on the epic branch
ever since — becomes `DATABASE_URL=http://127.0.0.1:8080` plus `DB_BOOTSTRAP_ENABLED=false`, the
switch STORY-008 built for exactly this line and explicitly handed to this story. That combination is
what makes `docker build` succeed with **no reachable database**: the local `http://` scheme needs no
`TURSO_AUTH_TOKEN`, so no fake secret is baked into a layer, and the disabled bootstrap means the
endpoint in the placeholder is never dialled when `reflex export` imports `chat_ui.chat_ui`.

The deletions come last, and only after the data is somewhere else. **Exploration found the actual
system of record, and it is not in the repository**: the `harness-ai_harness_data` volume on this
machine holds **16 `audit_logs` rows and 1 `users` row** (latest `2026-09-01T03:23:35Z`), against 8
rows in the repo-root `harness_ai.db` that STORY-013 rehearsed with, and 6 more in a shadow
`chat_ui/harness_ai.db` that Reflex's `chat_ui/` CWD created. Removing the volume declaration and
running `docker compose down -v` destroys that 16-row file. So the migration STORY-014's AC 5 requires
to have "been run and recorded" before deletion must be run against the **volume's** file, not the
repository's, and Task 1 extracts it before anything else is touched.

## User Story

As a platform engineer
I want every remaining trace of the local database file removed from the repository, the image and the compose stack
So that no deployment path can fall back to a file and no database file can be committed

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-014-deployment-cutover.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 4 (in scope), Section 5 story 1, Section 9 (security), Section 11 (functional requirements), Section 12 Phase 4
- Handoffs this plan consumes:
  - `.agents/reports/PRD-007-turso-migration/STORY-008-startup-guard.report.md` §"The STORY-014 handoff" — `DB_BOOTSTRAP_ENABLED=false` belongs in the builder `ENV` block, and why
  - `.agents/plans/PRD-007-turso-migration/completed/STORY-005-turso-configuration.plan.md` Task 8 — declares `Dockerfile:17` and `docker-compose.yml:12` red until this story
  - `.agents/reports/PRD-007-turso-migration/STORY-013-data-migration-script.report.md` — the run recorded there was a **rehearsal against the local dev server**; the production migration is this story's operator step

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (infrastructure cutover) |
| Complexity | MEDIUM (the story says small; the volume-data discovery adds a real migration step) |
| Systems Affected | `docker-compose.yml`, `Dockerfile`, repository root, local `.env` files. **No change to `app/`, `chat_ui/`, `scripts/` or `tests/`.** |
| Story | STORY-014 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`, scoped to the visual design of new or reshaped UI. This story touches infrastructure files and deletes data files; rendered output is untouched. The story's own frontmatter carries `skills: []`. | none |

---

## Patterns to Follow

### Secrets reach the container through `env_file`, never `environment:`

```yaml
# SOURCE: docker-compose.yml:9-12
    env_file:
      - .env
    environment:
      DATABASE_URL: sqlite:////app/data/harness_ai.db
```

`OPENROUTER_API_KEY` and `ADMIN_TOKEN` are already supplied this way and appear nowhere in the compose
file. `DATABASE_URL` and `TURSO_AUTH_TOKEN` join them — which leaves the `environment:` block with
nothing in it, so it goes away entirely rather than being emptied.

### Build-time placeholders are commented with their reason, in the builder stage only

```dockerfile
# SOURCE: Dockerfile:11-17
# Build-time-only placeholders so importing chat_ui.chat_ui (which imports
# app.main, which imports app.config.settings) doesn't fail Pydantic's
# required-field validation. Real secrets come from docker-compose's env_file
# at runtime; none of these ENV values are present in the final stage below.
ENV OPENROUTER_API_KEY=build-placeholder \
    ADMIN_TOKEN=build-placeholder \
    DATABASE_URL=sqlite:///:memory:
```

The rationale still holds and the comment stays; the value changes and one line is added. The `FROM
python:3.11-slim` at `:29` starts a fresh stage, so none of these reach the shipped image.

### The one sanctioned way to skip the boot-time database work

```python
# SOURCE: app/config.py:45-58
    # Whether startup touches the database at all -- STORY-008's reachability
    # guard and the schema migration behind it. The only sanctioned `False` is
    # the Dockerfile's builder stage: `reflex export` imports `chat_ui.chat_ui`,
    # which calls `init_db()` at import, and PRD-007 Section 11 requires the
    # build to succeed with no reachable database. STORY-014 sets it there,
    # beside the `DATABASE_URL` build placeholder it already owns.
    DB_BOOTSTRAP_ENABLED: bool = True
```

```python
# SOURCE: app/db/database.py:470-471
    if not settings.DB_BOOTSTRAP_ENABLED:
        return
```

The story asks whether STORY-008 or this story resolves the build-without-a-database constraint. **It
was resolved in STORY-008, deliberately and in writing, and this story is the line that sets it** — not
an accident of ordering. Nothing new is invented here.

### The endpoint scheme decides whether a token is required

```python
# SOURCE: app/config.py:100-112
    @model_validator(mode="after")
    def _require_token_for_remote_endpoint(self) -> "Settings":
        is_remote = self.DATABASE_URL.lower().startswith(_REMOTE_SCHEMES)
        if is_remote and not self.TURSO_AUTH_TOKEN.strip():
            raise ValueError(...)
```

This is why the build placeholder is `http://127.0.0.1:8080` rather than a `libsql://` URL: `http://`
is the local-dev scheme and takes no token, so the builder stage needs **no** `TURSO_AUTH_TOKEN` line
and no fake credential is written into an image layer. The story's Technical Note says to add the token
placeholder "if validation now requires it" — with the `http://` value it does not, and the plan says
so in a comment rather than adding a token nobody needs.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.yml` | UPDATE | Remove the `environment:` block, the `harness_data` mount and the top-level `volumes:` key |
| `Dockerfile` | UPDATE | Builder placeholder → `http://127.0.0.1:8080` + `DB_BOOTSTRAP_ENABLED=false`, comment extended |
| `harness_ai.db` | DELETE | The file PRD Section 2 says is "gone, not hidden" (8 rows — archived first) |
| `chat_ui/harness_ai.db` | DELETE | The shadow file Reflex's `chat_ui/` CWD created (6 rows — archived first) |
| `.gitignore` | VERIFY (no change) | `*.db` is already there at `:6`; `chat_ui/.gitignore:4` covers the shadow file. The AC is satisfied without an edit — confirm with `git check-ignore -v`, do not add a duplicate rule |
| `.dockerignore` | VERIFY (no change) | `*.db` at `:8` and the explicit `chat_ui/harness_ai.db` at `:14` both stay; the explicit line documents the Reflex-CWD footgun that produced that file and costs nothing |
| `.env` (untracked) | UPDATE | The local dev file still carries `DATABASE_URL=sqlite:///harness_ai.db`, which STORY-005 made a startup error |
| `chat_ui/.env` (untracked) | UPDATE | Same stale value at `:5`; read when Reflex runs with CWD `chat_ui/`, so it silently wins over the root file |

Not committed, but produced: an archive directory **outside the repository** holding the three `.db`
files (volume, root, shadow) as the rollback point PRD Section 7.5 promises.

---

## Tasks

Execute in order. The ordering is an acceptance criterion, not a convenience: AC 5 requires deletion to
follow migration and verification, and Tasks 1–3 are what make that true of the data that actually
exists.

### Task 1: Extract the deployed database out of the `harness_data` volume, before anything is edited

- **File**: none (data extraction)
- **Action**: EXTRACT
- **Implement**: The volume is the system of record and holds more than either repository file. Copy it
  to an archive directory **outside the working tree** (so no `.db` can ever be staged) and record
  counts and a SHA-256:
  ```bash
  ARCHIVE="$HOME/harness-ai-prd007-cutover-archive"
  mkdir -p "$ARCHIVE"
  docker run --rm -v harness-ai_harness_data:/data -v "$ARCHIVE":/out alpine \
      sh -c 'cp /data/harness_ai.db /out/volume-harness_ai.db'
  cp harness_ai.db         "$ARCHIVE/root-harness_ai.db"
  cp chat_ui/harness_ai.db "$ARCHIVE/chat_ui-harness_ai.db"
  sha256sum "$ARCHIVE"/*.db | tee "$ARCHIVE/SHA256SUMS"
  ```
  Expected at plan time (verified during exploration — re-confirm, do not assume): volume 16
  `audit_logs` + 1 `users`, root 8 + 0, shadow 6 (no `users` table).
- **Mirror**: the source-integrity discipline in `scripts/migrate_to_turso.py` — read-only open,
  SHA-256 before and after, source never mutated (STORY-013 report, "The real run").
- **Validate**:
  ```bash
  ls -la "$ARCHIVE" && cat "$ARCHIVE/SHA256SUMS"
  python -c "import sqlite3;c=sqlite3.connect('file:$ARCHIVE/volume-harness_ai.db?mode=ro',uri=True);print(c.execute('SELECT COUNT(*) FROM audit_logs').fetchone(),c.execute('SELECT COUNT(*) FROM users').fetchone())"
  ```

### Task 2: Decide and record which file is authoritative, then migrate it

- **File**: none (operator step, recorded in the report)
- **Action**: MIGRATE
- **Implement**: `scripts/migrate_to_turso.py` **refuses a non-empty destination and has no `--force`**
  (STORY-013 AC 5), so exactly one of the three files can be copied into a given database. Choose the
  volume's file: it is the deployed audit trail, it is the newest, and it is the only one carrying a
  `users` row — a real token hash. Then run, against the operator's real Turso endpoint:
  ```bash
  python scripts/migrate_to_turso.py --source "$ARCHIVE/volume-harness_ai.db" --dry-run
  python scripts/migrate_to_turso.py --source "$ARCHIVE/volume-harness_ai.db"
  ```
  (confirm the flag spelling against `python scripts/migrate_to_turso.py --help` before running). Paste
  both transcripts into the report. Exit status must be zero and the printed source SHA-256 must match
  Task 1's.

  **The 8 root rows and the 6 shadow rows cannot also be copied** — the destination is no longer empty
  and the script offers no append path. That is a data decision, not a technical one: record it
  explicitly in the report as *"14 rows in two development-era files were archived, not migrated"*, with
  the archive path and checksums, rather than letting Task 6's deletion imply they were carried over. If
  the operator wants them, that needs its own story (an append mode the script deliberately lacks).

  If no Turso account is available at execution time, the local libSQL dev server
  (`harness-libsql-dev`, already running on this machine, `http://127.0.0.1:8080`) is a valid rehearsal
  target — but then say in the report that the production migration is still outstanding and that Task
  6's deletions are safe only because of Task 1's archive.
- **Mirror**: `.agents/reports/PRD-007-turso-migration/STORY-013-data-migration-script.report.md`,
  "The real run, pasted verbatim" — the same transcript-in-the-report discipline.
- **Validate**: the script exits 0 and its three verification layers (per-table counts, row-by-row
  content comparison by column name, accessor read-back through `get_audit_log()`) report clean.

### Task 3: Verify the migrated data through the application, not just through the script

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: With `DATABASE_URL` / `TURSO_AUTH_TOKEN` pointing at the destination, read the trail
  back through the public surface: `count_audit_logs()` returns 16, `get_audit_log(<a preserved id>)`
  returns the row, and `find_user_by_token_hash(...)` still resolves the migrated user. This is the last
  point at which the archive can be restored without ceremony.
- **Mirror**: STORY-013 report §3 — the migration was proved through `insert_audit_log()` returning the
  next natural id, not through counts alone.
- **Validate**:
  ```bash
  python -c "from app.db.database import count_audit_logs, get_audit_log; print(count_audit_logs()); print(get_audit_log(1) is not None)"
  ```

### Task 4: `docker-compose.yml` — drop the volume, the mount and the environment override

- **File**: `docker-compose.yml`
- **Action**: UPDATE
- **Implement**: Delete `environment:` and its one entry (`:11-12`), the service `volumes:` key and its
  `harness_data:/app/data` mount (`:13-14`), and the top-level `volumes:` block (`:16-17`). The file
  ends at `env_file`. Add a short comment where the `environment:` block was, recording that
  `DATABASE_URL` and `TURSO_AUTH_TOKEN` arrive through `.env` alongside the two secrets already there,
  and that no volume is declared because the application holds no local state — that comment is what
  stops a future reader re-adding a mount "for the database". Resulting file:
  ```yaml
  services:
    harness-ai:
      build:
        context: .
        args:
          PORT: ${PORT:-8000}
      ports:
        - "${PORT:-8000}:${PORT:-8000}"
      # DATABASE_URL and TURSO_AUTH_TOKEN come from .env, like OPENROUTER_API_KEY
      # and ADMIN_TOKEN -- PRD-007 Section 9. No volume: the audit trail lives in
      # Turso, so the container is stateless and `docker compose down -v` has
      # nothing of ours to destroy (PRD Section 5, story 1).
      env_file:
        - .env
  ```
- **Mirror**: the existing `env_file:` usage at `docker-compose.yml:9-10`.
- **Validate**:
  ```bash
  docker compose config                                        # parses; no volumes key, no sqlite URL
  grep -n "harness_data\|sqlite\|/app/data" docker-compose.yml  # no hits
  ```

### Task 5: `Dockerfile` — replace the placeholder and disable the boot-time database work

- **File**: `Dockerfile`
- **Action**: UPDATE
- **Implement**: At `:15-17`, change `DATABASE_URL=sqlite:///:memory:` to
  `DATABASE_URL=http://127.0.0.1:8080` and add `DB_BOOTSTRAP_ENABLED=false` to the same `ENV` block.
  Extend the existing comment with the two facts a reader would otherwise have to reconstruct: (a) the
  `http://` local-dev scheme is chosen precisely because `app/config.py`'s
  `_require_token_for_remote_endpoint` would demand a `TURSO_AUTH_TOKEN` for a `libsql://` value, and a
  fake token in an image layer is worse than a placeholder endpoint; (b) `DB_BOOTSTRAP_ENABLED=false` is
  STORY-008's sanctioned switch, and it is what keeps `reflex export` — which imports `chat_ui.chat_ui`,
  which calls `init_db()` at import — from dialling that endpoint, so the build needs no database (PRD
  Section 11). Note that the value is never reached and never resolved: it exists to pass Pydantic
  validation and nothing else. Do **not** add `DB_BOOTSTRAP_ENABLED` to the final stage — a running
  deployment must boot with the guard and the schema migration on.
- **Mirror**: `Dockerfile:11-17`, the existing placeholder block and its comment style.
- **Validate**:
  ```bash
  grep -n "DATABASE_URL\|DB_BOOTSTRAP_ENABLED" Dockerfile   # both only in the builder ENV block
  grep -rn "sqlite" Dockerfile                              # no hits
  ```

### Task 6: Delete both `.db` files and confirm the ignore rules

- **File**: `harness_ai.db`, `chat_ui/harness_ai.db`
- **Action**: DELETE
- **Implement**: Only after Tasks 1–3 are green and their transcripts are in hand:
  ```bash
  rm harness_ai.db chat_ui/harness_ai.db
  ```
  Then confirm the AC's gitignore half is already satisfied and add nothing: `.gitignore:6` is `*.db`
  and `chat_ui/.gitignore:4` repeats it. Record in the report that **neither file was ever committed** —
  `git log --all --diff-filter=A -- '*.db'` is empty and `git rev-list --all --objects | grep '\.db$'`
  returns nothing, so no audit rows and no `users` token hash are in git history, and the
  history-rewrite question the story's Technical Notes raise **does not arise**. That is a positive
  finding and worth stating as one, rather than leaving the reader to assume the worst.
- **Mirror**: n/a (deletion).
- **Validate**:
  ```bash
  find . -name "*.db" -not -path "./.git/*" -not -path "./chat_ui/.web/*"  # no hits
  git check-ignore -v harness_ai.db chat_ui/harness_ai.db                  # both rules print
  git status --porcelain                                                   # no deletions staged: never tracked
  ```

### Task 7: Repoint the two local `.env` files so development starts again

- **File**: `.env`, `chat_ui/.env` (both untracked, both gitignored)
- **Action**: UPDATE
- **Implement**: Both still carry `DATABASE_URL=sqlite:///harness_ai.db`, which STORY-005 turned into a
  startup error — STORY-005's Task 8 predicted exactly this and asked that it be reported rather than
  patched there. Set both to the local dev endpoint (`http://127.0.0.1:8080`, no token) or to the
  operator's Turso endpoint plus `TURSO_AUTH_TOKEN`, following `.env.example`, which is already correct.
  `chat_ui/.env` matters disproportionately: Reflex runs with CWD `chat_ui/`, so pydantic-settings reads
  *that* file, and a stale value there beats a fixed root one. While in `chat_ui/.env`, note in the
  report that it is missing the RBAC and PII settings the root file carries — it is a drifted copy, not
  a supplement, and consolidating it is a STORY-015 documentation item, not a change to make here.
  **Neither file is committed**; they are listed so the cutover leaves a working machine behind.
- **Mirror**: `.env.example:1-16` — the canonical, already-migrated shape.
- **Validate**:
  ```bash
  grep -n "DATABASE_URL\|TURSO_AUTH_TOKEN" .env chat_ui/.env
  python -c "from app.config import settings; print(settings.DATABASE_URL)"
  ```

### Task 8: Prove the build succeeds with no reachable database

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: This is AC 3, and the only honest way to test it is to build while nothing answers on
  the placeholder endpoint. Either stop the local dev server for the duration, or rely on the fact that
  `127.0.0.1:8080` inside the builder container is the container's own loopback and reaches nothing
  regardless — state which of the two the run relied on, because "it built while a server happened to be
  up on the host" proves nothing:
  ```bash
  docker build -t harness-ai:cutover .
  ```
  Confirm from the log that `reflex export` completed and that no connection attempt was made.
- **Mirror**: STORY-008 report §"The STORY-014 handoff", which predicts this exact outcome.
- **Validate**: `docker build` exits 0.

### Task 9: Prove `docker compose down -v` destroys no application data

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: PRD Section 5, story 1's acceptance in one command. With the stack up against a valid
  endpoint, write a row (`POST /query`, or a direct `insert_audit_log()`), then:
  ```bash
  docker compose down -v
  docker volume ls | grep harness_data   # gone, and not recreated by `up`
  docker compose up -d
  ```
  and read the row back. Then remove the now-orphaned `harness-ai_harness_data` volume from this
  machine — but only once Task 1's archive is confirmed on disk, since that volume is where the 16 rows
  came from. Record the `docker volume rm` in the report; it is a destructive step and should be visible
  rather than silent.
- **Mirror**: PRD Section 5, story 1's own example wording.
- **Validate**: `count_audit_logs()` after the `down -v` / `up` cycle equals the count before it.

### Task 10: Run the stack end to end against Turso

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: AC 8. With valid credentials in `.env`: `docker compose up -d`, then `GET /health`, a
  `POST /query` with a per-user bearer token, and the admin console rendering its ten summary figures
  (the batched read STORY-010/011/012 landed). Confirm the startup guard's message shape while here —
  STORY-008's report asked STORY-014's "first real deployment" to confirm the text — and report any
  divergence rather than fixing it.
- **Mirror**: the endpoint list in PRD Section 10.
- **Validate**:
  ```bash
  curl -s localhost:${PORT:-8000}/health
  curl -s -X POST localhost:${PORT:-8000}/query -H "Authorization: Bearer <user-token>" \
       -H 'Content-Type: application/json' -d '{"prompt":"cutover smoke","model":"openai/gpt-4o"}'
  ```

### Task 11: The `grep -rn "sqlite"` sweep, with its exceptions named

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: AC 6 asks for the sweep and requires any exclusion to be stated explicitly. Run the
  story's literal grep, then the meaningful one:
  ```bash
  grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile
  grep -rn "^import sqlite3\|^from sqlite3" app/ chat_ui/ scripts/
  ```
  Expected, each to be listed in the report by name:
  1. `chat_ui/.web/` — Reflex's generated `node_modules`: thousands of hits, not source, not shipped
     (`.dockerignore:12`). Excluded, said out loud.
  2. `app/config.py:11-13,86` — the scheme is named **in order to reject it**; that is the feature.
  3. `app/db/database.py:77,180,228,445` and `app/db/errors.py:4,24,27,66,84` — comments describing what
     the driver swap replaced, inside `app/db/`, which PRD Section 11's wording permits explicitly.
  4. `scripts/migrate_to_turso.py:38` — the one `import sqlite3`, the documented exception this story's
     own AC 6 sanctions (STORY-013 report §1 reconciles it against PRD Section 11).
  5. `chat_ui/.env:5` — resolved by Task 7; if it still appears, Task 7 was not done.

  No production code path hits. `tests/` keeps its `sqlite3` imports and is outside the AC's scope.
- **Mirror**: `.agents/reports/PRD-007-turso-migration/STORY-013-data-migration-script.report.md` §1 —
  the same grep, the same reasoning, already agreed.
- **Validate**: the two greps above, with the five exceptions accounted for one by one.

### Task 12: Check the in-container pytest claim and hand the finding to STORY-015

- **File**: none (verification; a finding, not a fix)
- **Action**: VERIFY
- **Implement**: `Dockerfile:69-71` and `README.md:386` both promise that
  `docker-compose run --rm harness-ai pytest tests/ -v` works. The suite now needs a libSQL dev server,
  and `tests/conftest.py:44` defaults to `http://127.0.0.1:8080` — which, inside the container, is the
  container's own loopback and reaches nothing. Test whether the documented command still works, then
  whether the escape hatch `conftest.py` already provides recovers it:
  ```bash
  docker compose run --rm harness-ai pytest tests/test_db.py -q
  docker compose run --rm -e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080 harness-ai pytest tests/test_db.py -q
  ```
  Record both outcomes. If the bare command fails and the second works, that is the finding for
  STORY-015: the README command needs `HARNESS_TEST_LIBSQL_URL` and, on Linux, an `extra_hosts` entry
  for `host.docker.internal`. **Do not change the README or add `extra_hosts` here** — STORY-015 owns
  the docs and this story's scope is two committed files. Also forward the two documentation
  inaccuracies STORY-013 recorded (there is no `GET /audit/{id}` route; the suite's known failures are
  not all `STREAM_EXPIRED`) so they reach STORY-015 in one place.
- **Mirror**: `tests/conftest.py:24-32,44` — the documented dev-server workflow and its override.
- **Validate**: both commands run, and both outcomes are written down.

### Task 13: Full-suite regression and the untouched-application proof

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**: No Python changed, so the suite must be unchanged. Run it module by module against the
  local dev server — the whole-suite-in-one-process `STREAM_EXPIRED` issue is open and unowned (index
  note), so a single whole-suite run is not the baseline. Compare against the three known pre-existing
  failures STORY-013 recorded. Then prove the blast radius:
  ```bash
  git diff HEAD --stat     # docker-compose.yml and Dockerfile only
  git status --porcelain   # no .db deletions, because none were tracked
  ```
- **Mirror**: STORY-013 report, "Validation Results" table.
- **Validate**: three known failures and no fourth; `git diff HEAD --stat` names exactly two files.

---

## End-to-End Tests

- [ ] Volume file extracted and checksummed to an archive outside the repo; counts recorded (expected 16 `audit_logs`, 1 `users`)
- [ ] `python scripts/migrate_to_turso.py --source <archived volume file>` exits 0; three verification layers clean; source SHA-256 unchanged
- [ ] `count_audit_logs()` through the application returns 16 against the migrated database; a preserved id reads back through `get_audit_log()`
- [ ] `docker compose config` parses with no `volumes` key and no `sqlite:` string anywhere
- [ ] `docker build -t harness-ai:cutover .` exits 0 with nothing listening on the placeholder endpoint
- [ ] `docker compose up -d` → `GET /health` 200; `POST /query` with a per-user token returns a completion and writes an audit row
- [ ] The admin console renders all ten summary figures against Turso
- [ ] `docker compose down -v` → `docker compose up -d` → the row written before the teardown is still readable
- [ ] `docker volume ls` shows no `harness_data` volume, and `up` does not recreate one
- [ ] `find . -name "*.db"` (excluding `.git/` and `chat_ui/.web/`) returns nothing
- [ ] `grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile` → only the five documented exceptions, each named in the report
- [ ] `docker-compose run --rm harness-ai pytest tests/test_db.py -q` — outcome recorded either way, with the `HARNESS_TEST_LIBSQL_URL` variant
- [ ] Suite module by module: three known failures, no new one

## Validation

```bash
docker compose config
docker build -t harness-ai:cutover .
grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile
grep -rn "harness_data\|/app/data" docker-compose.yml Dockerfile
find . -name "*.db" -not -path "./.git/*" -not -path "./chat_ui/.web/*"
git check-ignore -v harness_ai.db chat_ui/harness_ai.db
git diff HEAD --stat
```

---

## Risks + Mitigations

**R1 — The cutover deletes the deployed audit trail.** The 16-row file in `harness-ai_harness_data` is
the real record, and `down -v` destroys it once the volume declaration is gone. It is *not* the file
STORY-013 rehearsed against.
> Task 1 extracts and checksums it before any edit; Task 2 migrates that file, not the repository's; the
> volume is removed only in Task 9, after the archive is confirmed on disk.

**R2 — Only one of the three files can be migrated.** The script refuses a non-empty destination and has
no `--force`, by design.
> Choose the volume file (newest, largest, the only one with a `users` row); archive the other 14 rows
> and state in the report that they were archived rather than migrated. Do not invent an append path.

**R3 — The build placeholder silently becomes a runtime setting.** `DB_BOOTSTRAP_ENABLED=false` leaking
into the final stage boots an application whose schema was never created — `app/config.py:51-57` states
that consequence plainly.
> The `ENV` line stays in the builder stage, which `FROM python:3.11-slim` at `:29` discards. Task 5's
> grep confirms it appears exactly once.

**R4 — A `libsql://` build placeholder would bake a fake token into an image layer.** The remote schemes
force `TURSO_AUTH_TOKEN` to be non-empty.
> Use the `http://` local-dev scheme, which takes no token, and say why in the comment.

**R5 — `chat_ui/.env` silently wins.** Reflex's CWD is `chat_ui/`, so its stale `sqlite:///` value beats
a fixed root `.env` and makes the cutover look broken on a developer machine.
> Task 7 fixes both files, and the report names the precedence, since it will surprise the next person.

**R6 — The in-container pytest promise may already be broken.** The suite now needs a reachable libSQL
server, which the container's loopback does not provide.
> Task 12 tests it rather than assuming, and routes the answer to STORY-015 instead of widening this
> story's scope into the README.

---

## Acceptance Criteria

(Copied from story STORY-014)

- [ ] `docker-compose.yml` has no `harness_data` volume, no service mount, and no `DATABASE_URL: sqlite:////app/data/harness_ai.db`; the Turso variables arrive through the existing `env_file` mechanism, as `OPENROUTER_API_KEY` and `ADMIN_TOKEN` do
- [ ] The Dockerfile's build-time `DATABASE_URL=sqlite:///:memory:` is replaced with a value that satisfies STORY-005's validation
- [ ] `docker build` succeeds with no reachable database; the interaction between import-time `init_db()` and STORY-008's guard is resolved deliberately (it is: `DB_BOOTSTRAP_ENABLED=false`, built by STORY-008, set here)
- [ ] `harness_ai.db` is gone from the repository root, and `*.db` is gitignored
- [ ] `git log` shows the deletion happening **after** STORY-013's migration and verification were run and recorded
- [ ] `grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile` shows no production-path hits; `scripts/migrate_to_turso.py` is the one documented exception, and every other exclusion is stated explicitly
- [ ] `docker compose down -v` destroys no application data
- [ ] The stack boots against valid Turso credentials, serves `POST /query`, and renders the admin console
- [ ] All tasks completed
- [ ] Backend imports cleanly and the suite shows no new failure against its known baseline
- [ ] Follows existing patterns
