---
prd: PRD-018
story: STORY-001
feature: F1
date: 2026-11-17
conclusion: >
  Every fault in PRD Section 4 was produced against libsql==0.1.11 and the local libSQL server except a Linux
  `os error 110`. Q1 DML is NOT durable before commit(). Q2 commit()/rollback() with no open transaction is a local
  no-op (no network, never raises). Q3 a fresh writer waits about 2 s (0.7 s if the holder is dead), then succeeds.
  TRANSACTION_TIMEOUT was never produced. V1 yes (DEAD_STREAM@commit may move to NOT_SENT). V2 not testable
  (never produced; no fixture row).
---

# PRD-018 STORY-001: driver failure-surface spike

**Conclusion.** Captured live on 2026-11-17, in-network (`harness-test-net`) with the host as a comparison,
3 repeats per variant, raw `libsql` client, text through `database._redacted()` plus an SQL guard (0 of 1189
records elided; 0 hung probes; 0 aborted probes).

- **Q1** Is a DML statement durable before `commit()`? **No.** After `INSERT` the client reports
  `in_transaction=True`; a fresh client sees nothing while the writer is alive, after it exits without `commit()`,
  and 15 s later (6/6 `landed=false`). With `commit()` it lands (3/3 `true`).
- **Q2** Does `commit()` with no open transaction go to the network? **No.** It never raised: on a never-used client
  against a refused URL (3/3), on a restarted server's dead stream (F4c 3/3), on an expired stream (F5d 3/3), and
  20 calls took 0.0 s against 0.034 s for 20 `SELECT` round trips. Same for `rollback()` (F1 3/3, F5e 3/3).
  With a transaction open, `commit()` on a dead stream raises the dead-stream text (F4b, F5b, F5c).
- **Q3** A stream abandoned mid-transaction, then a fresh writer: the writer **waits 2.08-2.30 s** (holder alive, 6/6
  incl. the `timeout=1.0` variant) or **0.69-0.78 s** (holder killed, 3/3), then **succeeds** and lands (9/9).
  No `TRANSACTION_TIMEOUT` text was produced. The abandoned row never lands (9/9).
- **V1** May `DEAD_STREAM`@`commit` move to `NOT_SENT`? **Yes.** 9/9 commits (F4b, F5b, F5c) raised a dead-stream
  marker and 9/9 read-backs were `landed=false`; Q1 shows the earlier `INSERT` was never durable. Recommendation
  only: the PRD edit is the orchestrator's (PRD Section 12 Phase 1).
- **V2** Is `TRANSACTION_TIMEOUT` `NOT_SENT`? **Not testable: the text never appeared** (Q3 produced a wait and a
  success). It has no fixture row and stays `OUTCOME_UNKNOWN` by default. See the "waits about 2 s" note in Q3.

Four findings the PRD does not yet have (details below): (1) the live connect text in this driver is
`error trying to connect: tcp connect error: ...`, **not** the `error sending request for url ... client error
(Connect)` that `tests/` and `database.py:514` quote; (2) a connect timeout in-network surfaces as
`Connection refused (os error 111)` after 21.0 s, indistinguishable from a refusal by text; (3) a restart while a
request is queued yields two new server texts, `503 ... Namespace store has shutdown` and `404 ... Namespace
`default` doesn't exist`; (4) `docker pause` produces **no client-side read timeout** (blocked the full 60 s).

## Question and hypothesis

PRD-018 Section 6.2 classifies by message text and by the call that raised. Its rules were written from the text in
`database.py` and from PRD-014; this spike measures them (Section 4 faults, Section 15 assumptions, Risk 3).

## Setup

| Item | Value |
|---|---|
| Date | 2026-11-17 |
| Repo `HEAD` | `87c4b68` on `epic/PRD-018-db-resilience`; `app/` bind-mounted from the tree, nothing under `app/` or `tests/` changed |
| Driver | `libsql 0.1.11`: container Python 3.11.18, host Python 3.12.10 |
| Probe image | `harness-ai-harness-ai:latest` (`6765d09650f3`) with `app/` mounted read-only at `/work/app` (the image's own `database.py` differs from the tree) and `.agents/spikes/` at `/work/spike`; `-w /tmp`; repo root never mounted (it holds `.env`) |
| Server | `harness-libsql-dev`, `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27...3a67`, data on a Docker volume (survives restart) |
| Docker | server 29.7.2 |
| Network | `harness-test-net` did not exist; the spike created it, connected the server, and removed both at the end (start state: `bridge` only) |
| Paths | in-network `http://harness-libsql-dev:8080` (primary evidence); host `http://127.0.0.1:8080` (comparison; F1/F2 only) |
| Client | raw `libsql.connect(url, auth_token="")`, not `get_connection()` (whose `__exit__` would add its own commit/rollback). Each `execute` and `fetch*` is its own timed step |
| Read-back | always a fresh container and fresh client (PRD-007 STORY-001 rule) |
| Repeats | 3 per variant; the F2 variants have 4 in-network (one extra single-repeat discovery run per URL) |
| Scratch table | `prd018_spike_rows`, dropped at the end |
| Raw output | `captures.jsonl` in the session scratchpad (not in the repo). `rid` below is its record id |

## Procedure (per variant; every group ends with the server restored: unpause, start, `/health` 200, `SELECT 1`)

- **F1 refused**: `connect`, `execute("SELECT 1")`, `fetchone`; then a new never-used client does `commit()`, another
  `rollback()`. URL `http://127.0.0.1:1` (inside the container that is its own loopback).
- **F2 connect timeout**: same steps against `10.255.255.1:8080` then `192.0.2.1:8080`.
- **F3 pause**: warm `SELECT 1` -> `READY` -> `docker pause harness-libsql-dev` -> `GO` -> in-flight call.
  a) `INSERT`, hold 60 s, `docker unpause`; b) `INSERT`, hold 15 s, unpause; c) `INSERT`, hold 3 s,
  `docker restart -t 0` **while paused**; d) `INSERT` then in-flight `commit()`, hold 3 s, `docker restart -t 0`.
- **F4 restart**: a) `INSERT m1` (tx open) -> `docker restart -t 0` -> wait healthy -> `INSERT m2`, `commit()`,
  `rollback()`; b) `INSERT` -> restart -> `commit()`; c) `SELECT 1` only -> restart -> `commit()` -> `SELECT 1`.
- **F5 idle** (probe sleeps, no Docker action): a) `SELECT 1`, sleep 15 s, `SELECT 1`; b) `INSERT`, sleep 15 s,
  `commit()`; c) `INSERT`, sleep 15 s, `SELECT 1`, `commit()`; d) `SELECT 1`, sleep 15 s, `commit()`;
  e) same with `rollback()`; control: sleep 8 s then `SELECT 1`.
- **Q1** a) `INSERT` then `os._exit(0)` (no commit, no close), read back at once and after 15 s; b) same but read back
  while the writer is alive, after exit, after 15 s; c) `INSERT` + `commit()` control.
- **Q2-healthy**: 20 `commit()` vs 20 `SELECT 1` round trips on a live client with no transaction.
- **Q3** a) holder `INSERT` (tx open) stays alive while a fresh writer `INSERT` + `commit()` runs; b) holder killed with
  `os._exit(0)` right after its `INSERT`, writer immediately; c) as a) with the writer's `libsql.connect(timeout=1.0)`.

## Deviations from the plan / PRD recipe

1. No image rebuild: the driver is already in the image and `app/` is bind-mounted (mounting the repo root would
   expose `.env`).
2. `docker run -i` with a READY/SENT/GO stdin handshake, so the host can interrupt a call that is in flight.
3. `docker restart -t 0` (abrupt, crash-like) everywhere, not the graceful restart PRD-008 STORY-024 used. The baton
   text is byte-identical to the one that story captured (`database.py:411`), so the choice did not change it.
4. **A Linux `os error 110` was not produced.** In-network `192.0.2.1` ended after 21.0 s with `Connection refused
   (os error 111)` (a raw `socket.connect` to the same address with an 8 s timeout timed out, so the address does
   black-hole); `10.255.255.1` was refused after 2.1 s. The 110 text is not in the repo either. The only timeout
   evidence is the host's `os error 10060` (Windows, localized Spanish text, 21.0 s). Nothing was invented.
5. F2 and the host comparison ran for the two unroutable URLs separately (`--url-index`), because the first URL did
   not time out.
6. The Windows host texts are localized and reached the script already containing U+FFFD (the driver's lossy decode).
   They are comparison rows only.
7. Q3c is the optional extra from the plan; it was run.
8. After `close()` the driver panics on `client.in_transaction` (`pyo3_runtime.PanicException`, a `BaseException`,
   `src/lib.rs:359`). Only the harness's own health probes hit it; the probes catch `BaseException`, so it is a
   harness note, not a finding about production code paths.

## Captures

All rows in-network unless "host". `tx` is `in_transaction` before->after the raising call. `landed` is the fresh-client
read-back. Messages are exactly as returned by `_redacted()`; trailing double backticks are the driver's.

| fault | variant | call that raised | verbatim message | elapsed s | tx | landed | repeats agreeing | rids |
|---|---|---|---|---|---|---|---|---|
| F1 refused | `127.0.0.1:1` | `execute` (`connect` succeeds, lazy) | ``Hrana: `http error: `error trying to connect: tcp connect error: Connection refused (os error 111)`` `` | 0.00-0.02 | F->F | n/a | 3/3 | 75, 81, 87 |
| F1 refused | host | `execute` | ``Hrana: `http error: `error trying to connect: tcp connect error: No se puede establecer una conexi�n ya que el equipo de destino deneg� expresamente dicha conexi�n. (os error 10061)`` `` | 2.00-2.02 | F->F | n/a | 3/3 | 93, 99, 105 |
| F2 timeout | `10.255.255.1` | `execute` | same text as F1 in-network (os error 111) | 2.09-2.11 | F->F | n/a | 4/4 | 111, 123, 129, 135 |
| F2 timeout | `192.0.2.1` | `execute` | same text as F1 in-network (os error 111) | 21.00-21.01 | F->F | n/a | 4/4 | 117, 159, 165, 171 |
| F2 timeout | host `192.0.2.1` | `execute` | ``Hrana: `http error: `error trying to connect: tcp connect error: Se produjo un error durante el intento de conexi�n ya que la parte conectada no respondi� adecuadamente tras un periodo de tiempo, o bien se produjo un error en la conexi�n establecida ya que el host conectado no ha podido responder. (os error 10060)`` `` | 21.00-21.02 | F->F | n/a | 3/3 | 177, 183, 189 |
| F2 | host `10.255.255.1` | `execute` | as F1 host (os error 10061) | 2.09-2.11 | F->F | n/a | 3/3 | 141, 147, 153 |
| F3a pause 60 s, unpause | in-flight `INSERT` | `execute` | ``Hrana: `api error: `status=400 Bad Request, body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}`` `` | 60.06-60.07 (blocked the whole hold, no client timeout) | F->F | false 3/3 | 3/3 | 201, 224, 247 |
| F3b pause 15 s, unpause | in-flight `INSERT` | `execute` | same STREAM_EXPIRED text | 15.06 | F->F | false 3/3 | 3/3 | 290, 313, 336 |
| F3c restart while paused | in-flight `INSERT` | `execute` | rep 1: ``Hrana: `api error: `status=503 Service Unavailable, body={"error":"Namespace store has shutdown"}`` ``; reps 2-3: ``Hrana: `api error: `status=404 Not Found, body={"error":"Namespace `default` doesn't exist"}`` `` | 3.24-3.28 | F->T (rep 1), F->F | false 3/3 | text varies 1/2 | 379, 402, 425 |
| F3d restart while paused | in-flight `commit()` after `INSERT` | `commit` | 503 text (1 rep) / 404 text (2 reps), as F3c | 3.24-3.26 | T->T | false 3/3 | text varies 1/2 | 469, 493, 517 |
| F4a restart, tx open | next `INSERT` | `execute` | ``Hrana: `api error: `status=400 Bad Request, body=Received an invalid baton`` `` | 0.001 | T->T | m1 false, m2 false (3/3) | 3/3 | 564, 588, 612 |
| F4a | then `commit()` | `commit` | same invalid baton text | 0.000 | T->T | - | 3/3 | 565, 589, 613 |
| F4a | then `rollback()` | `rollback` | same invalid baton text | 0.000 | T->T | - | 3/3 | 566, 590, 614 |
| F4b restart, tx open | `commit()` | `commit` | same invalid baton text | 0.001-0.002 | T->T | false 3/3 | 3/3 | 636, 653, 670 |
| F4c restart, no tx | `commit()` | **none: did not raise** | no message | 0.000 | F->F | n/a | 3/3 | 688, 707, 726 |
| F4c | then `SELECT 1` | `execute` | same invalid baton text | 0.001-0.002 | F->F | n/a | 3/3 | 689, 708, 727 |
| F5a idle 15 s | `SELECT 1` | `execute` | the STREAM_EXPIRED text above, byte-identical to `database.py:405-407` | 0.002-0.108 | F->F | n/a | 3/3 | 757, 762, 767 |
| F5b idle 15 s, tx open | `commit()` | `commit` | STREAM_EXPIRED text | 0.001 | T->T | false 3/3 | 3/3 | 771, 780, 789 |
| F5c idle 15 s, tx open | `SELECT 1` then `commit()` | `execute`, then `commit` | STREAM_EXPIRED text on both | 0.000-0.001 | T->T | false 3/3 | 3/3 | 798/799, 808/809, 818/819 |
| F5d idle 15 s, no tx | `commit()` | **none: did not raise** | no message | 0.000 | F->F | n/a | 3/3 | 829, 834, 839 |
| F5e idle 15 s, no tx | `rollback()` | **none: did not raise** | no message | 0.000 | F->F | n/a | 3/3 | 844, 849, 854 |
| F5 control (8 s) | `SELECT 1` | none: **succeeded** | no message (window is still about 10 s) | 0.002 | F->F | n/a | 3/3 | 859, 865, 871 |
| F1 never-used client | `commit()`, `rollback()` | **none: did not raise** | no message | 0.000 | F->F | n/a | 3/3 | 77/79, 83/85, 89/91 |

Variance: none in the text or the raising call except F3c/F3d (503 once, 404 twice: which of the server's two
restart-time answers the request hit); `landed` agreed in every repeat.

F3a/F3b/F3c note: `docker pause` leaves the TCP connection open, so the driver waits. After 60 s the call was still
blocked (`after-hold probe_returned=false`, rids 199, 222, 245) and only returned after `unpause` with the
server-side `STREAM_EXPIRED`. So **no client-side read timeout exists within 60 s** (PRD Section 15 assumption
confirmed for the read side). For the connect side, 21.0 s in both the host and the container equals the OS connect
timeout, so no driver connect timeout below 21 s either.

## Q1: is DML durable before `commit()`?

Evidence: Q1a (rids 874-875, 913-914, 952-953), Q1b (887-902, 926-941, 965-980), Q1c (905-910, 944-949, 983-988).
After `INSERT` the client's `in_transaction` is `True` (Q1a `in_tx_after` True 3/3). A fresh client reads it as absent:
Q1a immediately false 3/3 and after 15 s false 3/3; Q1b while the writer was alive false 3/3, after it exited false 3/3,
after 15 s false 3/3. The `INSERT` + `commit()` control reads `true` 3/3.
**Answer: no, not durable before `commit()`; an abandoned client's work is lost.** This agrees with PRD-007 STORY-001
(`no_commit -> LOST`) and PRD-013 STORY-009 (`in_transaction=True` after DML), now against today's server.
**Effect on 6.2:** the "if the driver autocommits DML, the INSERT may already have landed" hedge on the
`DEAD_STREAM`@`commit` row does not apply to this driver and server.

## Q2: does `commit()` with no transaction touch the network, and what does it raise on a dead stream?

Evidence: F1 never-used client (77/79, 83/85, 89/91), F4c (688, 707, 726), F5d (829, 834, 839), F5e (844, 849, 854),
Q2-healthy (993, 997, 1001: 20 `commit()` = 0.0000 s, 20 `SELECT` = 0.034-0.035 s, `in_tx` False throughout).
**Answer: no network request. It is a no-op that never raises**, against a refused URL, a restarted server and an
expired stream alike. With an open transaction `commit()` does reach the server and raises the dead-stream text
(F4b 636, F5b 771). `rollback()` behaves the same (F1, F5e).
**Effect:** the phase wrapper must record `commit`/`rollback` as a call, but a commit-phase failure always means a
transaction was open, so "dead stream on `commit`" = "an open transaction was lost", never "nothing to commit".

## Q3: a stream abandoned mid-transaction, then a fresh writer (Risk 3)

Evidence: Q3a rids 1003-1048, Q3b 1051-1096, Q3c 1099-1144.

| variant | writer `INSERT` elapsed s (3 reps) | writer `commit()` s | raised | writer landed | holder row landed |
|---|---|---|---|---|---|
| Q3a holder alive | 2.14, 2.18, 2.08 | 0.18-0.21 | no | true 3/3 | false 3/3 |
| Q3b holder killed by `os._exit` | 0.73, 0.78, 0.69 | 0.16-0.22 | no | true 3/3 | false 3/3 |
| Q3c as Q3a, writer `connect(timeout=1.0)` | 2.19, 2.30, 2.29 | 0.20-0.23 | no | true 3/3 | false 3/3 |

**Answer: the writer waits (min 0.69 s, median 2.14 s, max 2.30 s over the 9 runs), then succeeds. No
`TRANSACTION_TIMEOUT` was produced,** and the wait did not follow `timeout=1.0` (2.19-2.30 s), so that argument does
not bound the remote wait. The wait is most likely a server-side busy wait that ends when the holder's transaction is dropped (inference: the
holder's row never lands; the driver text says nothing). It is **just above the 2 s per-statement budget of PRD D5**, which matters for the retry budget but is
not a failure. The holder was never given time to hit a 5 s limit; a longer-held write lock was not tried.
**Effect on Risk 3:** a fresh client does not hang or fail behind an abandoned stream on this server; the observed
cost is about 2 s. The PRD's `TRANSACTION_TIMEOUT` row remains unevidenced.

## Reused captures (cited, not re-derived)

| Text | Source | Re-observed today |
|---|---|---|
| STREAM_EXPIRED body | `database.py:405-407` | **identical**, byte for byte (F3a/b, F5a-c) |
| `Received an invalid baton` | `database.py:410-411` | **identical** (F4a-c) |
| `Hrana: `http error: error sending request for url (...): client error (Connect): tcp connect error: Connection refused (os error 111)`` | `tests/test_db.py:4958-4962`, `database.py:514-515` | **differs**: today's text is `Hrana: `http error: `error trying to connect: tcp connect error: Connection refused (os error 111)``. The shared tail (`tcp connect error: ... (os error N)`) is the only stable part; anything keyed on `client error (Connect)` or `error sending request` would miss |
| `... tcp connect error: A connection attempt failed (os error 10060)` | `tests/test_db_isolation_harness.py:224-229` | **differs** (synthetic): the live host text is localized and ends `(os error 10060)` |
| `os error 110` | PRD-014 spike:51 | **not produced** (see Deviation 4) |
| `UNIQUE constraint failed: users.token_hash`, `no such table: users`, `duplicate column name: pii_detected_input` | `database.py:372-380` | not re-observed (STATEMENT rows reused from the source) |
| `in_transaction=True` after DML | PRD-013 STORY-009 report:49-54 | **identical** |
| `no_commit -> LOST`, `close_only -> LOST` | PRD-007 STORY-001 report:68-91 | **identical** in outcome (Q1) |

## Fixture table for STORY-002 (AC 5)

Expected classes follow PRD 6.2 **as written**. `->NOT_SENT?` marks rows the V1 verdict would change.

| # | message (verbatim) | phase | expected FailureClass | source |
|---|---|---|---|---|
| 1 | ``Hrana: `http error: `error trying to connect: tcp connect error: Connection refused (os error 111)`` `` | `execute` | `NOT_SENT` | F1 in-net (0.0 s), F2 in-net (2.1 s and 21.0 s: a timeout is indistinguishable) |
| 2 | host text, `... No se puede establecer una conexi�n ya que el equipo de destino deneg� expresamente dicha conexi�n. (os error 10061)` | `execute` | `NOT_SENT` | F1 host |
| 3 | host text, `... Se produjo un error durante el intento de conexi�n ya que la parte conectada no respondi� adecuadamente ... (os error 10060)` | `execute` | `NOT_SENT` | F2 host |
| 4 | the same `tcp connect error` text, called at `commit` or `rollback` | `commit` | `NOT_SENT` (connect-phase text wins at any phase; not observed at commit) | rule, synthetic |
| 5 | STREAM_EXPIRED text | `execute` | `DEAD_STREAM` | F3a/b, F5a, F5c |
| 6 | STREAM_EXPIRED text | `commit` | `OUTCOME_UNKNOWN` ->`NOT_SENT?` (V1) | F5b, F5c |
| 7 | invalid baton text | `execute` | `DEAD_STREAM` | F4a, F4c |
| 8 | invalid baton text | `commit` | `OUTCOME_UNKNOWN` ->`NOT_SENT?` (V1) | F4a, F4b |
| 9 | invalid baton text | `rollback` | `DEAD_STREAM` (PRD 6.2 is silent on `rollback`; nothing to replay. STORY-002 to confirm) | F4a |
| 10 | ``Hrana: `api error: `status=503 Service Unavailable, body={"error":"Namespace store has shutdown"}`` `` | `execute` / `commit` | `OUTCOME_UNKNOWN` (unrecognised `Hrana:` text; `landed=false` 6/6 so far) | F3c, F3d |
| 11 | ``Hrana: `api error: `status=404 Not Found, body={"error":"Namespace `default` doesn't exist"}`` `` | `execute` / `commit` | `OUTCOME_UNKNOWN` (as 10) | F3c, F3d |
| 12 | `Hrana: `stream error: `Error { message: "SQLite error: UNIQUE constraint failed: users.token_hash", code: "SQLITE_CONSTRAINT" }`` (reused, `database.py:372-380`) | `execute` | `STATEMENT` | reused |
| 13 | `... SQLite error: no such table: users", code: "SQLITE_UNKNOWN" }` (reused) | `execute` | `STATEMENT` | reused |
| 14 | `... SQLite error: duplicate column name: pii_detected_input", code: "SQLITE_UNKNOWN" }` (reused) | `execute` | `STATEMENT` | reused |
| 15 | ``Hrana: `something the classifier has never seen`` | `execute` | `OUTCOME_UNKNOWN` | **synthetic**, by the PRD rule |
| 16 | ``Hrana: `http error: `error sending request for url (http://127.0.0.1:1/v2/pipeline): client error (Connect): tcp connect error: Connection refused (os error 111)`` `` | `execute` | `NOT_SENT` | reused wording (older driver text still to be accepted) |

```python
# PRD-018 STORY-001 (.agents/spikes/PRD-018-driver-failure-surface.md): verbatim, via _redacted()
_BATON = "Hrana: `api error: `status=400 Bad Request, body=Received an invalid baton``"
_EXPIRED = (
    'Hrana: `api error: `status=400 Bad Request, body={"message":"The stream has expired '
    'due to inactivity","code":"STREAM_EXPIRED"}``'
)
_FIXTURES = [
    # (message, phase, expected FailureClass)
    ("Hrana: `http error: `error trying to connect: tcp connect error: Connection refused (os error 111)``",
     "execute", "NOT_SENT"),  # F1 / F2 in-net
    ("Hrana: `http error: `error trying to connect: tcp connect error: No se puede establecer una conexi�n ya que "
     "el equipo de destino deneg� expresamente dicha conexi�n. (os error 10061)``",
     "execute", "NOT_SENT"),  # F1 host (localized; U+FFFD as the driver returned it)
    ("Hrana: `http error: `error trying to connect: tcp connect error: Se produjo un error durante el intento de "
     "conexi�n ya que la parte conectada no respondi� adecuadamente tras un periodo de tiempo, o bien se "
     "produjo un error en la conexi�n establecida ya que el host conectado no ha podido responder. "
     "(os error 10060)``",
     "execute", "NOT_SENT"),  # F2 host
    (_EXPIRED, "execute", "DEAD_STREAM"),   # F3a/b, F5a, F5c
    (_EXPIRED, "commit", "OUTCOME_UNKNOWN"),  # F5b, F5c: -> NOT_SENT if the orchestrator accepts V1
    (_BATON, "execute", "DEAD_STREAM"),     # F4a, F4c
    (_BATON, "commit", "OUTCOME_UNKNOWN"),  # F4a, F4b: -> NOT_SENT if the orchestrator accepts V1
    (_BATON, "rollback", "DEAD_STREAM"),    # F4a: PRD 6.2 is silent on rollback, STORY-002 to confirm
    ('Hrana: `api error: `status=503 Service Unavailable, body={"error":"Namespace store has shutdown"}``',
     "execute", "OUTCOME_UNKNOWN"),  # F3c
    ('Hrana: `api error: `status=503 Service Unavailable, body={"error":"Namespace store has shutdown"}``',
     "commit", "OUTCOME_UNKNOWN"),   # F3d
    ('Hrana: `api error: `status=404 Not Found, body={"error":"Namespace `default` doesn\'t exist"}``',
     "execute", "OUTCOME_UNKNOWN"),  # F3c
    ('Hrana: `api error: `status=404 Not Found, body={"error":"Namespace `default` doesn\'t exist"}``',
     "commit", "OUTCOME_UNKNOWN"),   # F3d
    # reused from database.py:372-380 (not re-observed today)
    ('Hrana: `stream error: `Error { message: "SQLite error: UNIQUE constraint failed: users.token_hash", '
     'code: "SQLITE_CONSTRAINT" }``', "execute", "STATEMENT"),
    ('Hrana: `stream error: `Error { message: "SQLite error: no such table: users", code: "SQLITE_UNKNOWN" }``',
     "execute", "STATEMENT"),
    ('Hrana: `stream error: `Error { message: "SQLite error: duplicate column name: pii_detected_input", '
     'code: "SQLITE_UNKNOWN" }``', "execute", "STATEMENT"),
    # SYNTHETIC (by the 6.2 rule, not captured)
    ("Hrana: `something the classifier has never seen`", "execute", "OUTCOME_UNKNOWN"),
    # reused older connect wording (tests/test_db.py:4958-4962): keep accepting it
    ("Hrana: `http error: error sending request for url (http://127.0.0.1:1/v2/pipeline): client error (Connect): "
     "tcp connect error: Connection refused (os error 111)`", "execute", "NOT_SENT"),
]
```

## Verdicts

- **V1: may `DEAD_STREAM`@`commit` move to `NOT_SENT`? YES.** Conditions in the plan: in every repeat of F4b, F5b and
  F5c `commit()` raised a dead-stream marker (9/9: rids 636/653/670, 771/780/789, 799/809/819) **and** `landed` was
  false (9/9), **and** Q1 showed DML is not durable before `commit()` (6/6 false, 3/3 true with commit). Caveats:
  abrupt `restart -t 0` and a local server, 3 repeats, and the rule covers only a dead-stream marker, never a reset or
  timeout on `commit` (those stay `OUTCOME_UNKNOWN`: no such text was produced because a paused `commit` came back as
  the 503/404 server text, F3d). This is a recommendation; recording it in PRD Section 6.2 / Phase 1 is the
  orchestrator's decision.
- **V2: is `TRANSACTION_TIMEOUT` `NOT_SENT`? NOT TESTABLE.** The text never appeared in 9 Q3 runs: a fresh writer
  waited about 2.1 s (0.7 s if the holder is dead), then succeeded and landed. No fixture row; the class stays
  `OUTCOME_UNKNOWN` by default. The only fact to carry into D5 is that a contended first statement can take about
  2 s, over a 2 s budget.

## Recommendation for STORY-002 / STORY-003

1. **Classify connect failures on `tcp connect error`** (and keep `error sending request` / `client error (Connect)`
   as an older spelling). They surface on **`execute`**, not `connect` (the client is lazy), so `phase = execute`
   with connect-phase text must still give `NOT_SENT`.
2. A connect timeout is not recognisable by text on Docker Desktop (`os error 111` after 21 s); it is the same
   `NOT_SENT` and the cost is the 21 s wait. A per-attempt wall budget (PRD D5) has to be enforced outside the driver:
   there is **no driver read timeout** (60 s blocked) and `connect(timeout=...)` did not bound the remote wait.
3. Add the two restart-time server texts (`Namespace store has shutdown`, `Namespace ... doesn't exist`) to the
   fixtures. They are `OUTCOME_UNKNOWN` by the unrecognised-text rule. `landed=false` 6/6, so a later story may
   choose to treat them as refused, but this spike's sample is only the restart window.
4. If V1 is accepted, mark rows 6 and 8 `NOT_SENT` and update the Section 6.2 rule and its "dead-stream marker on `commit`" hedge. `commit()`/`rollback()` with no open transaction are no-ops and never raise, so a commit-phase
   dead-stream always means a lost open transaction.
5. `in_transaction` can be read before a call to know whether a transaction was open, but it panics after `close()`.

## Restore evidence

Run after the last group with `host restore` (recorded 2026-11-17):

- `docker inspect -f '{{.State.Status}} paused={{.State.Paused}}' harness-libsql-dev` -> `running paused=false`
- server networks -> `bridge` (the Task 0 state); `docker network ls` -> `bridge, harness-ai_default, host, none`
  (`harness-test-net` removed, as the spike created it)
- `SELECT 1` ok on the host path (`127.0.0.1:8080`, `/health` 200) and in-network (before the network was removed)
- no `prd018_spike_%` table remains (`leftover tables: [[]]`)
- `harness-ai-harness-ai-1` still `Up` (untouched)
- `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_conftest_fixtures.py -m db -q -p no:cacheprovider` ->
  16 passed (one process, after the restore)

## Appendix A: how to rerun

```
.venv/Scripts/python .agents/spikes/PRD-018-driver-failure-surface.py host preflight --out <scratch>
.venv/Scripts/python .agents/spikes/PRD-018-driver-failure-surface.py host run smoke|refused|connect-timeout|pause|restart|idle|q1|q2|q3 --out <scratch>
.venv/Scripts/python .agents/spikes/PRD-018-driver-failure-surface.py host restore --out <scratch>   # always safe
```

`connect-timeout` takes `--where innet|host`, `--url-index 0|1`, `--repeats N`; `pause`, `restart`, `idle`, `q3` take
`--variant`. Run one group per call (F3a is about 4 min, idle about 8 min). Nothing else may use the dev server meanwhile.

## Appendix B: redacted records the tables cite (trimmed; `sql_elided` was false in all 1189)

```
rid 75  F1-refused innet execute  raised 0.0   tx F->F  "Hrana: `http error: `error trying to connect: tcp connect error: Connection refused (os error 111)``"
rid 117 F2 192.0.2.1 innet execute raised 21.004 tx F->F same text
rid 201 F3a innet execute raised 60.071 tx F->F  STREAM_EXPIRED text   (rid 199: after 60 s hold, probe_returned=false)
rid 379 F3c innet execute raised 3.263  tx F->T  503 "Namespace store has shutdown"
rid 402 F3c innet execute raised 3.255  tx F->F  404 "Namespace `default` doesn't exist"
rid 564 F4a innet execute raised 0.001  tx T->T  "Received an invalid baton"   (565 commit, 566 rollback: same)
rid 636 F4b innet commit  raised 0.002  tx T->T  "Received an invalid baton"
rid 688 F4c innet commit  ok     0.0    tx F->F  (no raise)
rid 771 F5b innet commit  raised 0.001  tx T->T  STREAM_EXPIRED text
rid 829 F5d innet commit  ok     0.0    tx F->F  (no raise)
rid 875 Q1a abandon os._exit in_tx_after=true ; rid 879/884 landed=false ; rid 910 Q1c landed=true
rid 993 Q2-healthy commit_x20_s=0.0 select_x20_s=0.0342
rid 1005 Q3a-writer execute ok 2.14 ; rid 1011 landed=true ; rid 1016 holder landed=false
rid 1054 Q3b-writer execute ok 0.726
```
