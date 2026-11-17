---
id: STORY-008
prd: PRD-018
slug: audit-journal
title: Audit journal — append/fsync JSON Lines, exclusive lock, checksum, torn-tail recovery, adoption, bounds
type: technical
priority: high
complexity: medium
phase: "4 - Never lose a row"
status: done
labels: [backend, storage, config]
epic_branch: epic/PRD-018-db-resilience
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-008-audit-journal.plan.md
report: .agents/reports/PRD-018-db-resilience/STORY-008-audit-journal.report.md
commit: b319788
depends_on: [STORY-004]
blocks: [STORY-009, STORY-010, STORY-011, STORY-012]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-008: The on-disk audit journal

## Description

As a compliance admin, I want an audit row that cannot reach the database to be appended and fsynced to a local journal before anything is released, so that no answered request goes unrecorded because of a storage hiccup.

## Acceptance Criteria

- [ ] Given `app/db/audit_journal.py`, when `append(entry)` is called, then one JSON line (`v`, `write_id`, `appended_at`, `audit` or `null`, `audit_id`, `decisions`, `sha256` of the line without that field) is written, `flush()`ed and `os.fsync()`ed, and `append` returns only after both. A test with a patched `os.fsync` asserts the order. An I/O failure raises `AuditUnavailableError(StorageError)` (new in `app/db/errors.py`).
- [ ] Given `AUDIT_BUFFER_MAX_BYTES`, when an append would exceed it, then it raises `AuditUnavailableError` and writes nothing. `bytes()` / `entries()` / `oldest_timestamp()` report the current depth, and a `headroom_ok()` (or equivalent) answers `bytes ≤ MAX_BYTES − PIPELINE_MAX_WORKERS × _JOURNAL_ENTRY_RESERVE_BYTES` (65536) for STORY-011.
- [ ] Given a process, when it opens its journal, then the file is `AUDIT_BUFFER_DIR/audit-journal-<host>-<pid>-<boot uuid>.jsonl` under an exclusive OS lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows). A second opener cannot lock it (test with two handles or a subprocess). On POSIX the directory is created `0700` and files `0600`.
- [ ] Given a journal whose last line fails its checksum (a torn tail), when it is loaded, then that line is discarded with one `ERROR` log line (`write_id` if parseable, never contents) and the valid lines before it are kept. Given unlocked journals from another pid in the directory, when `adopt()` runs, then it locks and loads them, and skips a file locked by a live process.
- [ ] Given `app/config.py`, when settings load, then `AUDIT_BUFFER_DIR` (default `./var/audit-buffer`) and `AUDIT_BUFFER_MAX_BYTES` (default 67108864, validated `≥ PIPELINE_MAX_WORKERS × 65536 × 2`, message naming the setting) exist. A directory that cannot be created or written is a startup error naming `AUDIT_BUFFER_DIR`, raised when the journal is opened by the lifespan (STORY-009), not at import.

## Technical Notes

- Pure filesystem module: no database calls, no import-time side effects (PRD-014 D2: a non-`db` test must not meet it). Tests run on `tmp_path`.
- The checkpoint (byte offset) sidecar, compaction to zero bytes once fully drained, and the in-memory pending-row index used by the duplicate overlay are owned here as data structures, with an API that STORY-009 (drainer) and STORY-011 (overlay) call: e.g. `pending()` iterating undrained entries oldest first, `mark_drained(write_id)` advancing the checkpoint, `pending_duplicate(user_id, dedup_key, since)` (the predicate itself lands in STORY-011). Keep this story to storage-of-entries; do not start a thread.
- Entry shape: `audit` is every `AuditLog` field (including `write_id` and the original `timestamp`); `decisions` are `ActionDecisionRow` fields but `audit_id`. Serialize from the dataclasses (STORY-004 added `write_id`), so a later field is not silently dropped: add a round-trip test over `dataclasses.fields`.
- Contents are never logged (T6): only `write_id`, `user_id`, counts.
- `AuditUnavailableError` 503 mapping on the ingresses is STORY-010.
- Settings follow the `PIPELINE_MAX_WORKERS` validator style in `app/config.py` (`:260`, `:536`). `.env.example` and compose are STORY-014.
- Tests: `tests/test_audit_journal.py` (non-`db`), `tests/test_config.py`.

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-009, STORY-010, STORY-011, STORY-012

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 4 (Audit journal), 6.8 (Format, Durability, Ownership, Bounds), 9.2 (T5, T6, T7, T8), 9.3, 10 (Internal API), 15 (D9, D10)
