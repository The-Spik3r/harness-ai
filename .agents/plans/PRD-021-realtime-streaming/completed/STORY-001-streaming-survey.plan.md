---
story: STORY-001
prd: PRD-021
slug: streaming-survey
title: Survey what providers stream and what clients display
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: Survey what providers stream and what clients display

## Summary

A spike. One script, `scripts/survey_streaming.py`, sends at most 6 tiny streamed requests (OpenRouter: one reasoning and one non-reasoning model; local `http://localhost:1235/v1` model `google/gemma-4-e4b` when reachable), saves sanitized raw `data:` lines as fixtures, and prints per-model facts plus what `parse_events` yields and drops. The client survey (OpenCode, Cline, OpenAI SDK) is done by reading installed source. The report is the deliverable. No application code changes.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-001-streaming-survey.md`
- PRD sections used: 6.2 (item 1, Errors), 8, 15 "Not verified", O5, OD2
- Systems affected: none in `app/`; new `scripts/`, `tests/fixtures/prd021_survey/`, report

## Design Decisions (binding, from the orchestrator)

- Script is not a pytest test: file name `survey_streaming.py` (not `test_*`), under `scripts/`.
- At most 6 streamed requests in total, `max_tokens <= 64`, `stream: true`, `stream_options: {"include_usage": true}`. A module-level counter refuses a 7th call.
- Request budget: 1 OpenRouter reasoning model (e.g. a `deepseek/deepseek-r1*` id, or the cheapest reasoning id; pick one, record it), 1 OpenRouter non-reasoning (e.g. `openai/gpt-4o-mini`), 1 local. Spare calls (max 3): (a) re-run the reasoning model with `reasoning: {"effort": "low"}` ONLY if the first call streamed no reasoning (answers "only with a parameter"); (b) the single retry on a transient fault or a 404 model id (fallback id). Record which ids were used.
- Key: env `OPENROUTER_API_KEY`, else `dotenv_values(".env")` (python-dotenv 1.2.3 installed). Do not import `app.config` for it. The key lives only in the `Authorization` header; any echoed error text has the key replaced with `[KEY]` first. It never appears in output, logs, fixtures or report.
- Local server unreachable (connect timeout ~2 s): print "local: unreachable", exit 0. No key or no network: clear message, write nothing, exit 0.
- Fixtures `tests/fixtures/prd021_survey/<provider>-<model-slug>.sse`: only `data: {...}` lines and `data: [DONE]`; strings in `delta.content|reasoning|reasoning_content` and `reasoning_details[].text|summary` truncated to <= 40 chars; ids, `model`, `provider`, `finish_reason`, `usage` kept. SSE comment lines (`: OPENROUTER PROCESSING`) dropped from the fixture but their presence is noted in the report. No headers.
- Parse with `app.services.upstream.sse.parse_events(lines, label)`. It reads only `delta.content` and `delta.tool_calls` (`sse.py` `_chunk_events`), so `reasoning`, `reasoning_content`, `reasoning_details`, `role` are dropped; `usage` is read from any chunk, including one with empty `choices`. Confirm empirically by feeding the saved lines and report event counts by type plus the delta keys that produced no event. Importing `app.services.upstream` runs its package `__init__` (httpx, registry); if that needs Settings, `os.environ.setdefault` dummy `OPENROUTER_API_KEY`/`ADMIN_TOKEN` before the import (as `tests/test_measure_usage_latency.py:14-15`).

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`, chat UI only).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Spike script header | `scripts/spike_pii_placeholders.py:1-20` | Docstring naming PRD/story/decisions; "records, asserts nothing; not a CI test" |
| CLI shape | `scripts/measure_usage_latency.py:56,379-420` | `argparse`, `main(argv) -> int`, `if __name__ == "__main__"` |
| Script import test | `tests/test_measure_usage_latency.py:1-30` | import the script in the suite, assert no side effects |
| SSE parse | `app/services/upstream/sse.py:23-49` | `parse_events` yields TextDelta/ToolCallDelta/UsageReport/Finish |
| Cline install | `tests/e2e/_cline.py:30` | Cline 3.0.74 pinned under `tests/e2e/.clients/cline` |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `scripts/survey_streaming.py` | CREATE | Probe, sanitizer, fixture writer, parse_events comparison, printed summary |
| `tests/fixtures/prd021_survey/*.sse` | CREATE (by the live run) | One per model actually called |
| `tests/test_survey_streaming.py` | CREATE (optional) | Offline only: imports; `main()` with no key returns 0 with a message; sanitizer truncates to 40 chars and removes a key string; counter refuses a 7th call. httpx is monkeypatched to raise if touched |
| `.agents/reports/PRD-021-realtime-streaming/STORY-001-streaming-survey.report.md` | CREATE | The deliverable |

## Tasks

### Task 1: Survey script
- **File**: `scripts/survey_streaming.py`
- **Implement**: pure helpers `sanitize_line(line, key)` and `summarize(lines)` (reasoning field names among `delta` keys: `reasoning`, `reasoning_content`, `reasoning_details`, other non-standard keys; usage chunk shape: keys of `usage`, whether `choices` is empty on that chunk, `completion_tokens_details.reasoning_tokens`; whether reasoning came before content; `parse_events` counts and dropped keys); a runner using `httpx.Client` with `client.stream("POST", f"{base}/chat/completions", ...)` and `iter_lines()`; flags `--no-local`, `--out-dir`, `--env-file`, `--reasoning-model`, `--model`. Prompt: a one-word reply request, `max_tokens: 64` (a reasoning model may spend all 64 on reasoning: record it).
- **Mirror**: `scripts/measure_usage_latency.py` bootstrap and CLI.
- **Validate**: `.venv/Scripts/python -c "import scripts.survey_streaming"`; run with no key (`--env-file` pointing at a missing file, env var unset): exits 0 with a message.

### Task 2: Optional offline test
- **File**: `tests/test_survey_streaming.py`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_survey_streaming.py`

### Task 3: Live run, exactly once (plus at most one retry on a transient fault)
- `.venv/Scripts/python scripts/survey_streaming.py`. Afterwards check, in Python (not echo), that the key value appears in no fixture, report or captured output; `git status` shows only expected files.

### Task 4: Client survey (cite file, version and matching string per finding)
- **OpenCode 2.3.2** (`opencode --version`): global install `C:\Users\nahue\AppData\Roaming\npm\node_modules\@opencode\cli`; `bin/opencode.exe` is a ~260 MB compiled binary with no JS source. `grep -a -o "reasoning_content"` matches it (bundled AI SDK code). Use `grep -a -o ".\{120\}reasoning_content.\{120\}"`, and the same for `delta.reasoning` and `reasoning_text`, to decide: `reasoning_content`, `reasoning`, or both. If inconclusive, use opencode.ai docs and cite URL and date.
- **Cline 3.0.74** (pinned local install, `tests/e2e/.clients/cline/node_modules/cline/package.json`): `node_modules/@ai-sdk/openai-compatible/dist/index.js` contains `reasoning_content`. Read the match sites (and the package version) to see whether chunks also accept `reasoning`; say which provider path Cline uses for an OpenAI-compatible base URL (its bundle under `node_modules/cline/bin`, else docs).
- **OpenAI Python SDK 3.40.0** (`.venv/Lib/site-packages/openai`): grep found no `reasoning_content` in the package; `types/chat/chat_completion_chunk.py` has no reasoning field; `_models.py` (~lines 122-150) sets `extra="allow"`, so unknown keys land in `model_extra`. Verify with an offline 3-line `ChatCompletionChunk.model_validate(...)` that `choices[0].delta.model_extra` carries it, and that the streaming accumulator (`openai/lib/streaming/chat/_completions.py`) does not display it.
- **O5 verdict**: one field (`reasoning_content`) unless a target client reads `reasoning` and not `reasoning_content`. State per client and the verdict.

### Task 5: Report
- **File**: `.agents/reports/PRD-021-realtime-streaming/STORY-001-streaming-survey.report.md`: ids used and request count; per-model table (reasoning field(s), reasoning without a request parameter, usage chunk shape, keep-alive comments, parse_events yields/drops); local result or "unreachable"; client table (version, source, which field); O5 verdict; implications for STORY-003 (field names to map; `parse_events` must read `delta.reasoning*`), STORY-014, STORY-015; fixture list; cost note; key-leak check result; `commit: pending`.

## End-to-End Tests
- [ ] The live run prints the summary and writes fixtures; key-leak check over fixtures and report is clean.
- [ ] Offline run without a key exits 0.
- [ ] Each fixture replays through `parse_events(lines, "survey")` without raising (it ends at `[DONE]`).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_survey_streaming.py tests/test_untouched_app.py
```

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Proof |
|---|---|---|
| AC1 OpenRouter reasoning and non-reasoning facts | 1, 3, 5 | live run output and report table |
| AC2 local server; unreachable is not an error | 1, 3, 5 | report row; offline test with a monkeypatched connect error |
| AC3 sanitized, replayable fixtures | 1, 3 | fixtures and the parse_events replay check |
| AC4 OpenCode/Cline/OpenAI SDK and O5 verdict | 4, 5 | report client table with sources |
| AC5 clean exit without key/network; script not collected | 1, 2 | `tests/test_survey_streaming.py::test_no_key_exits_cleanly` |

Risks: the reasoning model may spend all 64 tokens on reasoning (record it); the usage chunk may be absent or have `choices: []`; a model id may 404 (one retry with a fallback); the OpenCode binary grep may be inconclusive (fall back to docs).
