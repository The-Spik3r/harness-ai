---
story: STORY-014
prd: PRD-018
slug: docs-and-deployment
title: Docs, compose volume, .env.example, roadmap, and PRD close-out
type: technical
complexity: small
epic_branch: epic/PRD-018-db-resilience
created: 2026-11-17
---

# Plan: Document what a database outage does

## Summary

Docs, compose and `.env.example` only; no application code. Rewrite `docs/deployment.md`'s "hard dependency" section as "What a database outage does", describing what STORY-001..013 built (not the PRD's first draft). Add the journal volume to `docker-compose.yml`, both settings to `.env.example` and `docs/configuration.md`, the 503 / `audit_ref` / `GET /storage/status` rows to `docs/api.md` and `docs/features.md`, tick the roadmap boxes, fix every stale statement ("no volume", "fails requests instead of degrading", 500 on gate failure) in README and docs, mention `--run-chaos` in `docs/testing.md`, and close the PRD. No test pins compose, README or docs prose; the `.env.example` tests in `tests/test_config.py` are the only pins and apply to the new vars.

## User Story

As a platform operator, I want the deployment docs, compose file and env template to describe the retry, breaker, journal and its volume, so that I can run and reason about the harness during an outage without reading the code.

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-014-docs-and-deployment.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical (docs) |
| Complexity | small |
| Systems Affected | docs/, README.md, docker-compose.yml, .env.example, PRD frontmatter |
| Epic Branch | `epic/PRD-018-db-resilience` |

---

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`, which does not apply; story `skills: []`).

---

## Patterns to Follow

### Naming / voice
Existing docs are plain, concrete, first-person-plural-free prose with bold lead-ins and "stated, not hidden" caveats, e.g. `docs/deployment.md:48-50` ("There is no exception for the duplicate check ... a security decision, not a resilience detail"). Section links use GitHub anchors (`deployment.md#...`). Error tables: `docs/api.md:360-380`. Env table: `docs/configuration.md:15-34` (`| Variable | Required | Default | Description |`).

### `.env.example` comment-above-var form (pinned)
```
// SOURCE: tests/test_config.py:1098-1105 and :1480-1488
re.search(rf"(?m)^#.+\n{var}=", text)        # a comment line directly above VAR=
_env_example_value(text, "V1_TOOLS_ENABLED") == str(default).lower()   # value equals the Settings default
```
Defaults to carry: `AUDIT_BUFFER_DIR=./var/audit-buffer` (`app/config.py:429`), `AUDIT_BUFFER_MAX_BYTES=67108864` (`app/config.py:434`). Existing `tests/test_config.py:1501-1527` pins the defaults on the Settings side; STORY-014 adds the `.env.example` pins next to them. `.env.example` order must follow `Settings.model_fields` order if I add an order test (place the two vars after `ACTION_SQL_DIALECT`, where the fields sit).

### Tests
```
// SOURCE: tests/test_config.py:1089-1130 (PRD-013 STORY-018 block)
_USAGE_VARS = (...)
def test_env_example_documents_every_usage_var_with_a_comment(): ...
def test_env_example_usage_vars_appear_in_settings_field_order(): ...
def test_env_example_usage_defaults_match_settings(): ...
```
Mirror this for `_AUDIT_BUFFER_VARS` (three small tests, each citing PRD-018 STORY-014). Reuse `_env_example_value`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docs/deployment.md` | UPDATE | Rewrite `:46-50` ("The database is a hard dependency of every request") as "What a database outage does"; amend `:13` "no ... in the compose stack" only if it contradicts (it speaks of a database file, so it stays; add one sentence pointing at the journal) |
| `docker-compose.yml` | UPDATE | Named volume `harness-audit-buffer:/var/lib/harness/audit-buffer`, `environment: AUDIT_BUFFER_DIR=...`, top-level `volumes:`; amend the "No volume ... stateless" comment for the journal only |
| `.env.example` | UPDATE | Document `AUDIT_BUFFER_DIR`, `AUDIT_BUFFER_MAX_BYTES` (comment line directly above each var) |
| `docs/configuration.md` | UPDATE | Two rows after `PIPELINE_MAX_WORKERS` (`:34`) or in the storage group |
| `docs/api.md` | UPDATE | See Task 5 |
| `docs/features.md` | UPDATE | New subsection "Database outages" after "Usage limits" (`:224`) + fix the link text at `:222` |
| `docs/roadmap.md` | UPDATE | Tick first two boxes (`:30-31`), reword intro `:28`, Shipped list entry |
| `docs/testing.md` | UPDATE | `--run-chaos` (and `--run-e2e`) after the pytest option block (`:24-29`); rewrite `:146-147` troubleshooting (500 -> 503) and anchor links |
| `README.md` | UPDATE | `:285` ("no volume is involved") and Roadmap `:368-370` (Shipped list / Next up) and `:226` link text |
| `tests/test_config.py` | UPDATE | Three `.env.example` pin tests for the two vars (PRD-018 STORY-014 comment) |
| `.agents/PRDs/PRD-018-db-resilience/PRD.md` | UPDATE | Frontmatter `status: done`, `updated: 2026-11-17` (O2 and O8 already read "Resolved by the user (2026-11-17)" at `:573` and `:579`; verified, no edit) |
| story + index | UPDATE | At implement end: `status: done`, report, commit; `gen_index.py` prints `errors: none`, board 14/14 100% |

CREATE: none (the implement subagent writes the report and archives this plan under `completed/` per implement.md).

---

## Facts the docs must state (checked against code and reports)

Failure classes and retry rule (PRD 6.2/6.3; `database.py`, STORY-002/003):
- `NOT_SENT` (`tcp connect error`, plus dead-stream marker on `commit`, STORY-001 decision), `DEAD_STREAM` (on `execute`/`fetch*`), `OUTCOME_UNKNOWN` (reset, timeout, any unrecognised `Hrana:` text, restart-window 503/404), `STATEMENT` (never retried, never counts toward the breaker).
- Reads and idempotent writes retry on all three infrastructure classes; the non-idempotent ones (`admit_usage`, `charge_usage`, `append_chat_message`, `insert_user`) only on `NOT_SENT`/`DEAD_STREAM`@execute. Budget: 3 attempts, full-jitter backoff (<=50 ms, <=200 ms), no new attempt starts after 2 s. Constants, not settings. `_translated()` itself never retries; the retry is `_unit_of_work`.
- Breaker: process-local, opens after 5 consecutive infrastructure failures, stays open 10 s, then one half-open probe per process. An open breaker refuses (`StorageUnavailableError`, a `StorageError`), never admits; identity, usage gate, duplicate check fail closed; no cache of identity (D15).
- Audit writes are idempotent by client-minted `write_id` (`INSERT ... ON CONFLICT(write_id) DO NOTHING RETURNING id`), so a replay after an unknown outcome is safe. The usage charge stays fail-open (logged ERROR, audit row keeps the token counts).

Responses per ingress (STORY-006/010/011):
- `/query`: identity read unavailable -> `503 {"detail":"Storage unavailable"}` + `Retry-After`; gate (session ownership, usage admit, duplicate) caused by an outage -> `503 {"detail":"Storage unavailable: the request was not sent to the model."}` + `Retry-After`; a non-transient cause keeps the 500 and its detail. `Retry-After` = seconds to the breaker's next half-open, min 1, or 1 when the breaker is closed and only the budget ran out.
- `/v1`: `503`, `type: api_error`, `code: storage_unavailable`, retryable (no `x-should-retry`), `Retry-After`; the error object carries `"harness": null` like every `/v1` error (`ErrorDetail`). Shared rule in `app/services/storage_faults.py`. A post-commit streamed fault is an SSE `error` event with no `Retry-After` (headers already sent; unreachable today since every gate runs before the commit).
- Chat UI: fixed `internal_error` bubble (no driver text), composer unlocked; sign-in shows a storage notice, not "invalid token"; footer `audit pending` for a journaled row; headline "The harness could not record this answer." for `AuditUnavailableError`.
- Journaled success: `200`, `audit_id: null`, `audit_ref` (always present, equals the row's `write_id`), `/v1` `X-Harness-Audit-Ref` replaces `X-Harness-Audit-Id`, `id: chatcmpl-harness-ref-<write_id>`, `harness.audit_ref`. O2 (release with null id) resolved 2026-11-17.
- Row neither written nor journaled (`AuditUnavailableError`) or journal below admission headroom (`AuditHeadroomError`, checked at step 1c before step 2): `503` + `Retry-After` (1 for headroom), nothing released; on `/v1` with tools the unrecordable-decisions case is `500 internal_error` (STORY-010 R2).
- Break-glass `ADMIN_TOKEN` resolves with no database read, so it still works during an outage; user tokens cannot (the identity read fails closed).

Journal (STORY-008/009/010/011):
- `AUDIT_BUFFER_DIR` (default `./var/audit-buffer`; compose `/var/lib/harness/audit-buffer`, named volume `harness-audit-buffer`), `AUDIT_BUFFER_MAX_BYTES` (default 67108864; must be >= `PIPELINE_MAX_WORKERS x 65536 x 2`; startup error names the setting). Dir 0700, files 0600 on POSIX; holds raw `prompt_preview` (T6), contents never logged; compacted to zero bytes when drained; empty in steady state; encryption at rest not provided.
- File `audit-journal-<host>-<pid>-<boot uuid>.jsonl`; fsynced append, sha256 per line, exclusive OS lock per file; adoption of unlocked sibling journals at boot (restart, crashed sibling on a shared volume); instances without a shared volume drain only their own.
- Torn tail (corrupt LAST line only, or last line without newline) is discarded with one ERROR. A corrupt non-last line or a checksum-valid undecodable line holds the whole file back: left on disk untouched, not adopted, one ERROR, counted in `held_back_files`; a drain failure that is not an outage holds the entry back for the process lifetime (`held_back_entries`). Operator action for held-back data: inspect the file, never delete blindly.
- Drainer: daemon thread started only by the two lifespans (FastAPI `app/main.py`, Reflex `chat_ui/chat_ui/chat_ui.py`), one idempotent transaction per entry oldest first, only while the breaker is closed (idle instance recovers through the breaker's single probe), new writes go straight to the database. **Consequence: a drained row's `id` is later than rows written after it; `id` is not time order. `/audit` orders by `timestamp`.** Original timestamp is kept.
- Duplicate overlay (D12 amended): journal index consulted after the database lookup succeeds and found nothing; a failed lookup still fails closed. **Residual T4:** a resend landing on a different instance before this one drains is not held (window = drain lag).
- Journal full or failing -> fail closed (T5).
- Pre-execution decision writes never use the journal (O8 option (a), resolved 2026-11-17; PRD-023 T9). Only PRD-017's post-response release does.

Status (STORY-012):
- `GET /storage/status` (`stats:read`; break-glass works), in memory only, no database call, answers with the breaker open; `/health` unchanged. Shape: `instance`, `breaker {state, since, consecutive_failures, last_failure_class, retry_after_seconds}`, `journal {open, entries, bytes, max_bytes, headroom_bytes (the admission reserve, workers x 64 KiB, not free bytes), oldest_timestamp, draining, adopted_files, held_back_entries, held_back_files}`, `counters {retries, exhausted (keys "<op>:<class>"), breaker_opens, journal_appended, journal_drained, torn_tail_discarded}`. Process-local, reset on restart. Admin console Storage page at `/admin/storage` (fifth masthead peer), read in-process.

Residual gaps / limits to state plainly:
- Stalls are not fixed (Risk 2): the driver has no read timeout; a stalled call returns when the driver gives up (7-21 s) and the shared client serialises callers; retry fixes what a stall leaves behind, the breaker stops it repeating. The 2 s deadline cannot shorten a running attempt.
- On a Windows host a refused connect takes ~2 s, so the 2 s start deadline allows one attempt there (`reason=deadline`); Linux refuses in milliseconds (STORY-013).
- Healthy-path overhead: +0.04 ms p50 against a local file database (code overhead); over Docker Desktop the 0.5 ms budget is below the noise floor (+0.80 ms, 1.70 ms spread), stated as unresolvable, not a pass (STORY-013 report; verify exact wording in the report when writing).
- `delete_chat_session` is IDEMPOTENT: after an `OUTCOME_UNKNOWN` commit that landed, the retry finds nothing and returns `False`; data correct, UI may say "not found" for a delete that worked (STORY-003, docstring in `database.py`).
- Four chat-UI `resolve()` calls (`retry_sessions`, `select_session`, `rename_session`, `delete_session`) still sit outside the storage arm (STORY-007 follow-up); the catch-all `except Exception` in `_do_send` is unchanged.
- T4 above; journal is not encrypted or signed (T6/T7); no provider failover (PRD-022); a held-back entry is never retried by this process.

---

## Tasks

Execute in order. Docs-only: no validation beyond the checks listed.

### Task 1: `docker-compose.yml`
- **File**: `docker-compose.yml`
- **Implement**: add under `harness-ai`: `environment: - AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer` (compose `environment` wins over `env_file`, so a stray `.env` value cannot point the journal off the volume) and `volumes: - harness-audit-buffer:/var/lib/harness/audit-buffer`; top-level `volumes: harness-audit-buffer:`. Rewrite the comment `:9-12` to: the audit trail and every table live in Turso; the one local state is the audit journal (PRD-018), empty in steady state, holding rows only while the database is unreachable; `docker compose down -v` destroys unflushed journal entries, so drain first (check `GET /storage/status` `journal.entries == 0`). Image runs as root (Dockerfile has no `USER`), so the volume is writable; no Dockerfile change.
- **Validate**: `docker compose config` parses and shows the volume and env; also `docker compose -f docker-compose.yml -f tests/e2e/docker/compose.smoke.yml config` parses (the smoke test overlays it; `tests/e2e/test_docker_smoke.py:60-61` runs `down -v`-style teardown under its own project, so the new volume is removed with it, confirm in that file).

### Task 2: `.env.example` and `docs/configuration.md`
- Add, after the `ACTION_SQL_DIALECT` block (matches `Settings` field order): comment lines then `AUDIT_BUFFER_DIR=./var/audit-buffer` and `AUDIT_BUFFER_MAX_BYTES=67108864`. Comment text: where the journal lives, what it holds (raw prompt previews, 0700/0600), compose overrides it to the named volume, minimum `PIPELINE_MAX_WORKERS x 65536 x 2` (32 x 65536 x 2 = 4 MiB at the default worker count, matching `tests/test_config.py:1502`), full journal fails closed.
- **Mirror**: `.env.example` ACTION_* blocks; `docs/configuration.md:34` row style.
- **Validate**: `tests/test_config.py` (new + existing `.env.example` tests).

### Task 3: `tests/test_config.py`
- Add `_AUDIT_BUFFER_VARS`, a comment-presence test, a field-order test and a default-parity test (`AUDIT_BUFFER_MAX_BYTES` as int, `AUDIT_BUFFER_DIR` string), each docstring citing "PRD-018 STORY-014". Place after `:1527` block. No existing assertion changes.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py`.

### Task 4: `docs/deployment.md`
- Replace the section at `:46-50` with "### What a database outage does", keeping an HTML anchor-compatible fallback: other docs link to `#the-database-is-a-hard-dependency-of-every-request` (`docs/features.md:222`, `docs/roadmap.md:28`, `docs/testing.md:147`, `README.md:226`/`:370`); update all links to `#what-a-database-outage-does`. Sub-structure (bold lead-ins, short paragraphs and two tables, matching the file): (1) what still costs a round trip (keep the 5/3-statement count and ~16 ms figure, they remain true); (2) failure classes and what is retried (table: class / did it run / retried?); (3) the breaker (constants, refuses never admits, no identity cache, break-glass still resolves); (4) what each ingress returns (table: `/query`, `/v1`, chat UI; `Retry-After` rule; the two `/query` 503 texts; `"harness": null`; post-commit SSE has no `Retry-After`; non-transient causes keep 500 and the old duplicate-check `500` pin `tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500` now applies only to non-transient causes, so reword that sentence); (5) the audit journal (volume, settings, security, torn tail vs held-back, adoption, headroom, `audit_ref`); (6) drain order: `id` is not time order, `/audit` orders by `timestamp`; (7) `GET /storage/status` and the Storage page; (8) what is still not covered: T4, stalls and no driver timeout (Risk 2), Windows ~2 s refused connect, held-back entries, `delete_chat_session` residual, four chat-UI `resolve()` calls, journal not encrypted/signed, `docker compose down -v` loses undrained rows; (9) measurements from STORY-013, with the unresolvable-over-Docker caveat stated as such.
- Also edit `:13`: add that the journal is the one local file, pointing at the new section; and the intro sentence "Resilience work is the first item on the roadmap" is removed with the old paragraph.
- Check `:5` intro and `docs/deployment.md` headings for a contents list to update.

### Task 5: `docs/api.md`
- `POST /query` success (`:11-36`): add `audit_ref` to the example and a sentence (always present; `audit_id` is `null` only for a journaled row). Add `### POST /query — 503 (storage unavailable)` after the usage-limit section (`:122-137`) with both bodies, `Retry-After`, the cases (identity, gate, journal full/headroom), and the "driver text never appears" note.
- `GET /audit` entry docs at `:139-213`: note `audit_id`/`id` order is not time order after a drain; ordered by `timestamp`.
- `GET /storage/status` section after `GET /stats` (`:251-287`): curl + JSON example + field notes (`stats:read`, no DB call, process-local counters, `/health` unchanged, `headroom_bytes` meaning, `held_back_*`).
- `/v1` success (`:288-323`): `audit_ref`, `X-Harness-Audit-Ref` / `chatcmpl-harness-ref-<write_id>` for a journaled row; streaming note at `:340` that the id is the `chatcmpl-harness-ref-` form then.
- `/v1` errors table (`:360-380`): add row `Storage unavailable (identity read, duplicate check, usage gate, journal full or headroom, audit row neither written nor journaled)` -> `503`, `api_error`, `storage_unavailable`, retried **yes**, `Retry-After`; edit the existing `internal_error` row (`:376`) to non-transient storage causes and the unrecordable-decisions case; add bullets: `"harness": null`, no `Retry-After` on a post-commit SSE event, no `x-should-retry` on it.
- Update the intro line `:3` (add `GET /storage/status`).

### Task 6: `docs/features.md`
- New `### Database outages` after Usage limits (before `:226`): short operator-facing summary mirroring the deployment section (what is absorbed, what a client sees, journal, `audit_ref`, status endpoint and Storage page, residual gaps), with links to deployment and api anchors. Fix the stale link text at `:222`. Add the 503 / `Retry-After` / `audit_ref` / `X-Harness-Audit-Ref` / `GET /storage/status` mentions required by AC 3. Also check the `:226-255` /v1 section for a headers list that should mention `X-Harness-Audit-Ref`.

### Task 7: `docs/roadmap.md`, `docs/testing.md`, `README.md`
- Roadmap: tick `[x]` the first two boxes (`:30-31`) with "shipped in [PRD-018](../.agents/PRDs/PRD-018-db-resilience/PRD.md)" and a link to the new section; reword `:28` (retry, breaker and journal shipped; second provider and websocket affinity remain; the "fails requests rather than degrading them" claim is no longer true for storage, still true for OpenRouter); add a Shipped entry. Keep the unticked provider-fallback and affinity boxes.
- Testing: after `:29` add `pytest tests/ -m chaos -v --run-chaos` explanation (opt-in, restarts the dev server `harness-libsql-dev`, never in CI; `tests/test_db_resilience_chaos.py`, `tests/conftest.py:177`) and a `--run-e2e` one-liner (`tests/conftest.py:171-216`), as `docs/testing.md` currently describes neither. Rewrite the `:146-147` troubleshooting entry: with an outage the gate answers `503` + `Retry-After` and fixed text; `500` with `Usage admission failed:` now means a non-transient cause. Update anchor links.
- README: `:285` -> the container holds no database; the one local state is the audit journal on the `harness-audit-buffer` volume, empty in steady state, `down -v` removes it (drain first); Roadmap Shipped/Next up paragraphs (`:366-370`); `:226` link text.

### Task 8: PRD close-out and indexes (implement phase)
- PRD frontmatter `status: done`, `updated: 2026-11-17`; verify O2/O8 lines (done in plan: both "Resolved by the user (2026-11-17)").
- Story: `status: done`, `report`, `commit`; regenerate `PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-018` -> `errors: none`, 14/14 100%.
- Grep the repo for other `status: draft`/`active` mentions of PRD-018 (e.g. `.agents/PRDs/index` or a root board) and update if the generator does not.

---

## End-to-End Tests

- [ ] `docker compose config` parses; shows `harness-audit-buffer` volume and `AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer`; the smoke overlay config also parses
- [ ] `Grep` the docs for every old anchor `#the-database-is-a-hard-dependency-of-every-request` (zero hits) and for dead relative links added
- [ ] Facts cross-check: every number in the new docs (3 attempts, 5 failures, 10 s, 2 s, 64 MiB, 4 MiB minimum, 64 KiB reserve) re-read against `app/db/database.py`, `app/config.py`, `app/db/audit_journal.py`
- [ ] `/storage/status` example JSON validated against `StorageStatusResponse` (`app/models/schemas.py:322-365`)

## Validation

```bash
docker compose config
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_untouched_app.py tests/test_caddyfile_routes.py -q   # no app files touched; guards only
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-018   # errors: none
```
Not run: full suite (GitHub CI on push, user decision). No chat_ui file is touched, so no startup probe. No test pins compose, README or docs text (grep of `tests/*.py` and `tests/e2e/*.py` found only `.env.example` readers in `tests/test_config.py` and `tests/e2e/test_docker_smoke.py` which overlays compose).

---

## Risks

| Risk | Mitigation |
|---|---|
| Docs describe the PRD draft instead of the build | The "Facts" section above is taken from the reports and the code; implement re-reads `app/db/database.py` constants, `audit_journal.py` docstring and the STORY-013 report before writing numbers |
| Stale anchors after renaming the section | Task 4 greps all five linkers and updates them |
| Named volume vs `down -v` surprises an operator | Stated in compose comment, deployment and README |
| `environment:` in compose overriding `.env` unexpectedly | Intentional; stated in the compose comment |
| `.env.example` order/format pins | Task 3 mirrors the existing pin tests |
| `docker compose config` interpolation needs `.env` | `env_file: .env` must exist; if absent run with a temp `.env` copy from `.env.example` and delete it afterwards |

---

## Acceptance Criteria

(Copied from story `STORY-014`)

- [ ] `docs/deployment.md` "hard dependency" section rewritten as "What a database outage does": failure classes and what is retried, the 503s and `Retry-After` per ingress, the journal and its volume, drain order (`id` != time), T4 and Risk 2. (Task 4)
- [ ] `docker-compose.yml` mounts `harness-audit-buffer:/var/lib/harness/audit-buffer` with `AUDIT_BUFFER_DIR`, stateless comment amended for the journal only; `.env.example` documents both settings. (Tasks 1-3)
- [ ] `docs/api.md` and `docs/features.md` list the 503 rows, `audit_ref` / `X-Harness-Audit-Ref`, `GET /storage/status`. (Tasks 5, 6)
- [ ] `docs/roadmap.md` first two resilience boxes ticked, pointing to PRD-018. (Task 7)
- [ ] PRD `status: done`, O2 and O8 resolved 2026-11-17 (verified), `gen_index.py` prints `errors: none`, board 100%. (Task 8)
- [ ] All tasks completed; `docker compose config` parses; config tests pass; app imports; follows existing docs voice.
