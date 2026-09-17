---
id: STORY-003
prd: PRD-010
slug: openrouter-payload-characterization
title: "Characterize today's OpenRouter request payload and /query upstream body"
type: technical
priority: high
complexity: small
phase: "1 - Model, settings, client"
status: done
labels: [backend, tests, regression]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-003-openrouter-payload-characterization.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-003-openrouter-payload-characterization.report.md
commit: 1459475
depends_on: []
blocks: [STORY-004]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-003: Characterize today's OpenRouter request payload and /query upstream body

## Description

As an integrating developer, I want the exact upstream request `/query` sends today pinned by a test before the client changes, so that the "byte-identical payload" promise is checked, not assumed.

## Acceptance Criteria

- [ ] Given `call_openrouter("hello", model="gpt-4", api_key="k", client=fake)` on **untouched** production code, when the fake client records its `post(url, headers, json)` call, then a test asserts `json == {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}` exactly: equal key set, key order and no extra keys, compared via `json.dumps(..., sort_keys=False)`.
- [ ] Given the same call, when headers are recorded, then the test asserts `{"Authorization": "Bearer k", "Content-Type": "application/json"}` and the URL `https://openrouter.ai/api/v1/chat/completions`.
- [ ] Given no `client` argument, when `call_openrouter` constructs its own `httpx.Client`, then a test (patching `httpx.Client`) asserts it was built with `timeout=30.0`. This is today's value, and the one STORY-005 deliberately changes, with a PRD-010 comment at that point.
- [ ] Given `POST /query` with a PII-free prompt through `TestClient`, when the injected upstream records what it received, then a test asserts it received the prompt text unchanged, the requested model, and `api_key=None`. This is the pipeline-level characterization STORY-004 must keep green.
- [ ] Given the full suite, when this story lands, then it is green and **no production file is modified**.

## Technical Notes

- Extend the existing `_FakeClient` in [tests/test_openrouter_client.py](../../../tests/test_openrouter_client.py) (its `post(self, url, headers=None, json=None)` already receives the payload) to record calls. Do not introduce a mocking library.
- Name the tests `test_characterization_*` and add a module-level comment: "Pinned before PRD-010 STORY-004. Assertions change only where a later story cites the decision."
- The pipeline-level test belongs beside the six outcomes, for example as a new test in [tests/test_query_outcomes_regression.py](../../../tests/test_query_outcomes_regression.py), reusing its fixtures. Rows 1–6 stay untouched.
- Following the libSQL dev-server note, mass fixture errors mean restart the container, not bisect code.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 2 (Pin before you change), 9.2 (invariants), 11, 12 (Phase 1), 14 (Risk 1)
