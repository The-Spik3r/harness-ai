---
id: STORY-014
prd: PRD-010
slug: pipeline-concurrency-tests
title: "Concurrency: blocked upstream calls do not stall /health, /query or the chat"
type: technical
priority: high
complexity: medium
phase: "4 - Prove and document"
status: done
labels: [backend, tests, concurrency]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-014-pipeline-concurrency-tests.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-014-pipeline-concurrency-tests.report.md
commit: 0b0a077
depends_on: [STORY-006, STORY-012]
blocks: [STORY-018]
skills: []
created: 2026-09-17
updated: 2026-09-18
---

# STORY-014: Concurrency: blocked upstream calls do not stall /health, /query or the chat

## Description

As a platform operator, I want a test proving that ten slow upstream calls don't block health checks or other requests, so that the executor change is verified rather than argued.

## Acceptance Criteria

- [ ] Given the new [tests/test_pipeline_concurrency.py](../../../tests/test_pipeline_concurrency.py) with `PIPELINE_MAX_WORKERS=16` and an injected upstream that blocks on a `threading.Event` for the first ten calls, when ten `POST /query` requests are issued concurrently through `httpx.AsyncClient(transport=ASGITransport(app))` and the test waits until all ten are inside the stub, then `GET /health` returns 200 in < 1 s.
- [ ] Given the same ten blocked calls, when an eleventh `POST /query` is sent (the stub returns immediately for it), then it returns `SUCCESS` in < 1 s. After the event is set, all ten complete with `SUCCESS` and each writes exactly one audit row.
- [ ] Given ten blocked sends issued through `ChatState._do_send` (the history path, with an active session), when they are in flight, then `GET /health` and a `/query` call each still complete in < 1 s.
- [ ] Given a control run with `PIPELINE_MAX_WORKERS=10` and ten blocked calls, when an eleventh pipeline call is made, then it waits (it does not complete before release) while `/health` still answers. This documents T6 (saturation queues and does not fail) as intended.
- [ ] Given a manual smoke against a local HTTP server delaying 60 s (pointed at via a monkeypatched `_API_URL`), when ten chat sends and a `/health` probe run, then the timings are recorded in the story report. This step is not in CI.

## Technical Notes

- Never `time.sleep` to wait for the calls to be in flight. Use a `threading.Barrier`/counter plus `Event`, with a hard test timeout (for example `pytest.mark.timeout` or `asyncio.wait_for`, 10 s) so a regression fails instead of hanging.
- Always release the event in a `finally` so blocked executor threads don't leak into later tests. Shut down and reset the executor between tests via the `shutdown()` from STORY-006.
- `/health` is a sync `def`; it uses anyio's threadpool, which is exactly what must stay free.
- If `ASGITransport` doesn't exercise the anyio threadpool the way uvicorn does, add a variant that runs uvicorn in a thread on a free port (the two-instance smoke has a reusable pattern in [tests/test_two_instance_smoke.py](../../../tests/test_two_instance_smoke.py)).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-006, STORY-012
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 1 (MVP goal), 5 (story 5), 6.3, 9.2 (T6), 11 (Concurrency)
