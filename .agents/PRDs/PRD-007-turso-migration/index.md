# PRD-007-turso-migration: Turso / libSQL Migration — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-007-turso-migration` (base: `main`)
**Status**: active

## Progress

14/16 stories done — 88%

## Stories

All stories commit on the epic branch `epic/PRD-007-turso-migration`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Spike: verify the six risky libSQL client behaviors and record the driver decision | spike | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-001-libsql-driver-spike.plan.md) | `6e6b1c4` |
| STORY-002 | Characterization tests pinning the three driver-exception behaviors against current SQLite | technical | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-002-exception-characterization-tests.plan.md) | `403b191` |
| STORY-003 | Centralize the 27 DATABASE_URL test sites behind one conftest fixture, still SQLite-backed | technical | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-003-centralize-database-url-fixture.plan.md) | `eebfc71` |
| STORY-004 | app/db/errors.py: a module-owned exception surface, decoupling the three catch sites from sqlite3 | technical | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-004-module-owned-error-surface.plan.md) | `2961f33` |
| STORY-005 | Config: TURSO_AUTH_TOKEN, libSQL DATABASE_URL semantics, and no file fallback | feature | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-005-turso-configuration.plan.md) | `907eb6c` |
| STORY-006 | Swap app/db/database.py onto a shared libSQL client, preserving all 22 public signatures | feature | ✅ done | large | [plan](../../plans/PRD-007-turso-migration/completed/STORY-006-libsql-connection-layer.plan.md) | `86ece73` |
| STORY-007 | Make init_db() and _add_missing_columns() converge under concurrent multi-instance startup | technical | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-007-concurrent-safe-init-db.plan.md) | `efdb114` |
| STORY-008 | Fail fast and legibly when the database is unreachable or the token is missing | feature | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-008-startup-guard.plan.md) | `c924b32` |
| STORY-009 | Aggregate top_pii_entities() in SQL instead of transferring every PII-bearing row | enhancement | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-009-top-pii-entities-sql-aggregation.plan.md) | `f60471c` |
| STORY-010 | One batched database read returning all ten summary figures in a single round trip | feature | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-010-batched-summary-read.plan.md) | `b592264` |
| STORY-011 | GET /stats consumes the batched read instead of nine sequential calls | enhancement | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-011-stats-endpoint-batched.plan.md) | `94fdf4a` |
| STORY-012 | AdminState._READS consumes the batched read, preserving per-figure failure attribution | enhancement | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-012-admin-console-batched-reads.plan.md) | `784567a` |
| STORY-013 | scripts/migrate_to_turso.py: copy audit_logs and users with verification and a rollback point | feature | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-013-data-migration-script.plan.md) | `74cd352` |
| STORY-014 | Cutover: remove the harness_data volume, the build placeholder, and harness_ai.db | technical | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-014-deployment-cutover.plan.md) | `TBD` |
| STORY-015 | README: correct the persistence claim, the env table, and document multi-instance deployment | technical | ⬜ todo | small | — | — |
| STORY-016 | Prove two instances share one database: concurrent writes, cross-instance duplicate detection, no lost rows | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-004 blocked by STORY-002
- STORY-005 blocked by STORY-001
- STORY-006 blocked by STORY-001, STORY-003, STORY-004, STORY-005
- STORY-007 blocked by STORY-006
- STORY-008 blocked by STORY-006
- STORY-009 blocked by STORY-006
- STORY-010 blocked by STORY-006, STORY-009
- STORY-011 blocked by STORY-010
- STORY-012 blocked by STORY-010
- STORY-013 blocked by STORY-006
- STORY-014 blocked by STORY-006, STORY-008, STORY-013
- STORY-015 blocked by STORY-014
- STORY-016 blocked by STORY-007, STORY-014

STORY-001 through STORY-012 are done. The driver swap has landed, `init_db()` converges under concurrent multi-instance startup, an unreachable database or a rejected credential now fails at boot with a message that names the setting at fault, `top_pii_entities()` aggregates in SQL (50 PII rows in the table, 5 on the wire), and the admin summary's ten figures now come back in **one** statement (measured: 1 round trip vs 10, 2.7 ms vs 21.2 ms). The driver has no batch API (STORY-001 §2.6), so STORY-010 used the recorded §3.4 workaround -- one `SELECT` of scalar subqueries whose named columns carry the per-figure attribution Risk 6 needs, with a fallback to the ten standalone reads when the statement itself fails. **STORY-012 has now adopted it**: `AdminState.load()` makes one `to_thread` hop where it made ten, `_READS` keeps its four-slot shape and all ten entries, and the fault arm walks the table in order to name the first figure in `snapshot.errors` -- so Risk 6's per-figure `READ_LABEL_*` copy survives batching and the rendered console is unchanged (`tests/test_render_invariants.py` against a real database). Its report records how the story's AC 2 and AC 6/7 were reconciled: the transactional commit stays, attribution is what was rescued. `_READS`' "rows come first so the slowest query fails fast" comment is retired, as STORY-010's report asked. **STORY-011 has now landed too, which closes Phase 3**: `get_stats()` fills the same `StatsResponse` from one `summary_snapshot(row_limit=0)` where it made nine sequential calls, so both callers PRD Section 6 Pattern 3 named are on one round trip. Measured at the endpoint: **1** statement against `audit_logs` where there were **9** (11.0 ms vs 19.1 ms over live HTTP against a same-host endpoint, which understates the gain against a remote one). Its report answers the question the story posed — a caller **cannot** skip a figure, because `_SUMMARY_SQL` is a fixed ten-column SELECT whose column names are what carry Risk 6's attribution, but it can *empty* one: the rows subquery's `LIMIT ?` is `row_limit`, and 0 returns `[]` (verified: `[]`, not NULL) instead of up to 100 serialized audit rows crossing the network for a figure `/stats` has no field for. Byte-identity was proved by running the pre-change epic tip and the new code as two live servers against one database — `/stats` and `/audit` identical for admin, auditor and scoped callers, empty database included. `get_audit` is untouched. **STORY-013 has landed, and Phase 4's copy step is done**: `scripts/migrate_to_turso.py` copies both tables inside one `get_connection()` transaction as chunked multi-row `INSERT`s -- the driver has no batch API and `executemany` is unexercised in this repo, so a statement per chunk through the proven `execute()` path is the mechanism -- reads the source through stdlib `sqlite3` opened `mode=ro` with a SHA-256 taken before and after, and verifies in three layers: per-table counts, an exhaustive row-by-row content comparison by **column name** (a real ALTER-migrated file has a different column order than `CREATE_AUDIT_LOGS_TABLE`, so a positional copy would shift values and still match on counts), and an accessor read-back through `get_audit_log()` biased toward the rows carrying PII telemetry. A non-empty destination is refused outright with no `--force`; the single transaction is the retry path. The plan also answers the question the story posed about PRD Section 11: the `import sqlite3` exception **is** sanctioned, in writing, by STORY-014's own AC 6, and the script is a one-time operational tool rather than a production code path. Measured at the endpoint: the real `harness_ai.db` (8 rows) copied and verified clean, source SHA-256 identical before and after, and the AUTOINCREMENT sequence left at 8 so the next natural insert returned 9. **A second driver finding worth carrying forward**: the last bulk-looking API the driver still offered was measured and it is not bulk either -- `executemany` costs 1332 ms for 500 rows against 1295 ms row-at-a-time and 38 ms for the chunked multi-row `VALUES` the script uses, so nothing should adopt it assuming it batches. Two documentation inaccuracies were found rather than worked around, both for STORY-015: there is **no** `GET /audit/{id}` route (the API serves `GET /audit` as a list carrying `audit_id`; ids are addressed through `get_audit_log()`), and the three known suite failures are not all `STREAM_EXPIRED` -- run individually, `test_pii_badge.py` and `test_success_metadata_footer.py` fail at collection with `'chat_ui.chat_ui' is not a package`, which is a packaging problem the open issue currently conflates with the idle-stream one. **STORY-014 is now unblocked** and owns deleting `harness_ai.db` -- which this story deliberately did not do, and which must happen only after the operator has run the migration against the real Turso database. **Open issue, not owned by any story yet:** the shared libSQL client's Hrana stream expires after an idle window, so a whole-suite run in one process fails with `STREAM_EXPIRED` once a slow module (presidio/spacy model load) idles it out. Present since STORY-006; each suite passes alone, and STORY-012 confirmed `tests/test_chat_state.py`, `tests/test_pii_badge.py` and `tests/test_success_metadata_footer.py` fail identically on a pristine tree. See the STORY-009 report -- it likely needs its own story before STORY-016. STORY-014 now waits only on STORY-013, and it owns setting `DB_BOOTSTRAP_ENABLED=false` in the Docker builder stage (see STORY-008 report). STORY-016 still waits on STORY-014. **STORY-014 has landed, and the cutover is real**: `docker-compose.yml` declares no volume and no `environment:` block (Turso reaches the container through `env_file`, like the two secrets before it), the Dockerfile's builder placeholder is `http://127.0.0.1:8080` plus `DB_BOOTSTRAP_ENABLED=false`, and both `.db` files are deleted. Planning found what the story was actually protecting: the deployed audit trail was **not** in the repository but in the `harness-ai_harness_data` volume — **16 `audit_logs` rows and 1 `users` row**, against the 8 rows in the repo-root file STORY-013 rehearsed with and 6 more in a shadow `chat_ui/harness_ai.db`. That file was extracted and checksummed first, then migrated into **production Turso** (not a rehearsal this time) and verified three ways: the script's own layers, the application's accessors (ids 1–16 preserved, the migrated `admin` user resolving through `find_user_by_token_hash`), and the admin console rendering all 17 rows and all ten summary figures in a browser. `POST /query` returned `audit_id: 17`, continuing straight on from the migrated id 16. The other 14 rows are **archived, not migrated** — the script refuses a non-empty destination and has no `--force`, so only one file could go in, and the report says so rather than letting the deletion imply otherwise. AC 3 was answered by controlled experiment: the same import on `--network none` succeeds with `DB_BOOTSTRAP_ENABLED=false` and fails with STORY-008's guard without it, so the build-versus-guard interaction is resolved deliberately, and `docker inspect` confirms none of the four placeholders reach the shipped image. `docker compose down -v` moved the row count from 17 to 17. A positive security finding: neither `.db` file was **ever committed** (`git log --all --diff-filter=A -- '*.db'` empty, zero `.db` objects in `rev-list`), so the history-rewrite question the story raised does not arise, and `.gitignore` needed no edit. **One finding needs its own story, before STORY-016**: the test suite is *not* structurally incapable of reaching a production database, contrary to PRD Section 7.6 and `tests/conftest.py`'s own docstring. `conftest.py:55`'s `os.environ.setdefault` cannot override an inherited `DATABASE_URL`, and `tests/test_db.py:1809`'s `monkeypatch.undo()` reverts the autouse safety fixture along with the test's own patches — so the README's in-container pytest command, run against the cutover's own compose stack, read production (`assert 17 == 1`). Reads only, verified: production still holds 17 rows and no test data. Same file with `DATABASE_URL` forced to the dev server: 97 passed. STORY-016 will handle credentials the same way, so this should be fixed first. Two further items were routed to **STORY-015**: the README's in-container pytest command needs `HARNESS_TEST_LIBSQL_URL` (the container's `127.0.0.1` reaches nothing), and this host cannot run the project's Python at all — `libsql` has no wheel for Python 3.14 on Windows, so every step of this story ran in `python:3.11` containers.

## Phases

| Phase | Stories |
|-------|---------|
| 1 — Driver verification and behavior pinning | STORY-001, STORY-002, STORY-003 |
| 2 — Storage layer swap | STORY-004, STORY-005, STORY-006, STORY-007, STORY-008 |
| 3 — Network-cost remediation | STORY-009, STORY-010, STORY-011, STORY-012 |
| 4 — Data migration and cutover | STORY-013, STORY-014, STORY-015, STORY-016 |

## Skills

| Story | Skills |
|-------|--------|
| STORY-012 | `reflex-docs` — mandated by [chat_ui/AGENTS.md](../../../chat_ui/AGENTS.md) for any change to Reflex state, events, or the database read path |

All other stories: none. `.agents/skills/` holds only `frontend-design`, scoped to visual design of new or reshaped UI; this epic is required to leave rendered output identical.
