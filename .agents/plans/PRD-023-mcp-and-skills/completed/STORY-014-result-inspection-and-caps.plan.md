---
story: STORY-014
prd: PRD-023
slug: result-inspection-and-caps
title: "Results: size cap, pattern inspection under the `tool` cell, uninspected counts"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-23
---

# Plan: Results: size cap, pattern inspection under the `tool` cell, uninspected counts

## Summary

Extend M9 of `mcp_gateway.call()` (`app/services/mcp_gateway.py:397-427`) with a screening step applied only to a result that came back from upstream (`outcome.outcome` in `ok`/`error`). Serialize once with `canonical_json`, check the server's `max_result_bytes`, then (only if under the cap) inspect one `tool` message under `pattern_config.get_profile("code")`. Over cap -> `result_too_large` error text; a hit with `tool: block` -> `result_blocked` error text; otherwise the upstream result is returned unmodified. Size, hash and flags describe the upstream result in every case. `record_outcome` is widened to accept small JSON dicts in `result_flags`.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-014-result-inspection-and-caps.md`
- PRD sections used: 6.7, 6.9, 9.2 (T5, T14, T15), D11, O5
- Systems affected: `mcp_gateway.py`, `action_audit.py` (annotation/docstring only), `models.py` (comment), tests. No `database.py` change (no census impact), no new route, no new setting.

## Design Decisions

Binding (orchestrator), applied as written:

1. M9 order, only for upstream-returned results: (a) one `canonical_json` of the result dict; (b) `len(utf8) > server.max_result_bytes` -> `[harness] the result of <name> (<id>) exceeded <n> bytes and was not returned; the call ran`, `isError: true`, `result_too_large`, **no inspection** (T15); (c) else inspect; (d) hit in a list whose `tool` cell is `block` -> `[harness] the result of <name> (<id>) was withheld by the content policy; the call ran` (new constant `RESULT_BLOCKED_TEXT`; no matched text, no list or pattern name), `result_blocked`; else the same upstream object, outcome `ok`/`tool_error` as STORY-013 decides. `<n>` is the cap in bytes. `name`/`id` are capped with `NOTE_FIELD_CAP` like `TIMEOUT_TEXT` (`mcp_gateway.py:407`).
2. `result_bytes`/`result_hash` describe the upstream result whenever one came back (also too-large and blocked). Timeout / upstream_error: both `None`, flags `()`. `result_digest` becomes `result_digest(canonical: str) -> (len(utf8), duplicate_checker.hash_prompt(canonical))`, fed by the single serialization from step (a). `hash_prompt` is sha256 hex over UTF-8 (`duplicate_checker.py:24`), so stored values equal STORY-013's; the two tests that call `result_digest(result_dict)` now pass `canonical_json(result)` (each with a `PRD-023 STORY-014` comment).
3. Inspection input: one `SimpleNamespace(role="tool", content=...)` (as `_withheld_by`, `mcp_gateway.py:152`), joined with `"\n"`: every `text` block's text, `resource.text` of `resource` blocks with a str `text`, then `canonical_json(structuredContent)` when present. Profile: `pattern_config.get_profile("code")` (the literal `/v1` passes, `app/routers/v1.py:507`; reads the loaded policy, no file read), `max_scan_characters=settings.PATTERN_MAX_SCAN_CHARACTERS` as `query_pipeline.py:920-921`. Uninspected n = blocks of type `image`/`audio`/`resource_link`, any other or unknown type, a non-dict block, a `resource` without str `text` (blob only), plus 1 if `inspection.truncated` (the tail went unscanned: fail toward counting). Use `.get`, never index; never crash on odd shapes.
4. `result_flags` format (decision): JSON array whose elements are `str` (still accepted: STORY-008 tests) or small JSON-safe dicts: `{"list": <list name>, "pattern_id": <int>}` per distinct hit, then `{"uninspected": n}` only when n > 0. The gateway builds the array sorted by `(list, pattern_id)` and de-duplicated; a blocking hit is included. **`pattern_id` = zero-based index of the pattern within its list** (resolved from `profile.lists` via `hit.list_name`/`hit.pattern`), not the pattern source: `inject` returns exactly the pattern phrase, so the source would equal the matched text (AC2, T14). `record_outcome` (`action_audit.py:362-404`): signature unchanged, so `test_record_outcome_signature_has_no_content_parameter` and the field-order guards (`tests/test_mcp_audit.py:178,284`) stay green; change only the annotation (`Sequence[Union[str, Mapping[str, Union[str, int]]]]`), the docstring ("flag names or small JSON dicts, never content") and `json.dumps(..., sort_keys=True)`. `test_mcp_audit.py:218-219` (`'["injection","secret"]'`) is unaffected. Readers of `result_flags`: only `database.py:3466,3589,3660` (opaque TEXT passthrough) and the `models.py:505` comment (update it). No router, `/audit/actions` or admin code reads it yet (STORY-019 will; tell it the element shapes). `tests/test_action_audit.py:105-107` only counts columns.
5. No PII redaction (O5): this path touches no `pii_*` module. A test pins an email passing byte-identical.

Plan-level choices to confirm:
- Fail closed on a screening fault: if serialization, `get_profile` or `inspect` raises, log the class name at ERROR (T16) and withhold as `result_blocked` (flags `()`; size/hash `None` only if serialization itself failed). Reachable only by a bug; avoids returning an unscreened result.
- Inspection runs synchronously on the loop, bounded by the cap and the scan ceiling; no thread hop (keeps the 3.11/3.12 task-count tests stable).
- Logs: the existing `outcome=` INFO line is enough; log no hit, list or pattern id.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; no `chat_ui/` change).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Inspect call | `mcp_gateway.py:146-163` (`_withheld_by`) | `SimpleNamespace(role="tool", ...)`, `inspect(turns, profile, max_scan_characters=...)`, `.block`/`.flags`/`.truncated` |
| Profile access | `query_pipeline.py:920-921`, `pattern_config.py:276` | `get_profile(name)` on the loaded policy |
| Harness texts | `mcp_gateway.py:79-81`, `_harness_error` `:280` | module constants `{name} ({id})`, `[harness]` prefix |
| Per-server cap | `mcp_config.py:139,404`; `mcp_gateway.py:406` | `mcp_config.get_config().servers[server].max_result_bytes` |
| Best-effort write | `mcp_gateway.py:319-334` | `_write_outcome` stays the only M9 writer, never raises |
| Tests | `tests/test_mcp_tools_call.py:60-232`, `:561-640` | `spy` with `fake_call_tool`, `_configure`, `_post`; db variants with `real_rows`/`_rows` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/mcp_gateway.py` | UPDATE | `RESULT_TOO_LARGE_TEXT`, `RESULT_BLOCKED_TEXT`; `result_digest(canonical)`; `_inspect_result`; `_screen_result`; M9 branch; `_write_outcome(identity, row_id, outcome, duration_ms, size, digest, flags)`; docstring paragraph |
| `app/services/action_audit.py` | UPDATE | `record_outcome` annotation, docstring, `sort_keys=True` |
| `app/db/models.py` | UPDATE | `:505` comment only |
| `tests/test_mcp_results.py` | CREATE | STORY-014 tests |
| `tests/test_mcp_tools_call.py` | UPDATE | the `result_digest(...)` assertions (`:492`, `:590-592`) -> pass `action_audit.canonical_json(...)` |
| `tests/test_mcp_audit.py` | UPDATE | one test: `record_outcome` stores dict flags as JSON with sorted keys |
| `scripts/stub_mcp_server.py` | no change | `huge`, `inject` suffice (text only); other block types are built through `spy.fake_call_tool = CallOutcome(...)` |

## Tasks

### Task 1: Widen `record_outcome`
- **File**: `app/services/action_audit.py:362-404`, `app/db/models.py:505`
- **Implement**: annotation, docstring, `sort_keys=True`; keep parameter names/order and the unknown-outcome guard.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_audit.py -m "not db"`

### Task 2: Screening in the gateway
- **File**: `app/services/mcp_gateway.py`
- **Implement**: import `duplicate_checker` (confirm no import cycle; keep `hashlib`, still used at `:356`). Add `_inspect_result(content, structured) -> (hits, uninspected, blocked)` and `_screen_result(server, name, call_id, upstream, failed) -> (result, outcome, size, digest, flags)` doing (a)-(d). M9 `else` arm (`:417-420`) builds the upstream dict and calls it; the timeout / upstream_error arms pass `None, None, ()`. Update `result_digest`, `_write_outcome` and the module docstring.
- **Mirror**: `_withheld_by` (`:146-163`), M9 (`:404-427`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_tools_call.py -m "not db"`

### Task 3: Tests
- **File**: `tests/test_mcp_tools_call.py` (2 assertions), `tests/test_mcp_results.py` (CREATE; duplicate the minimal `_configure`/fixtures, skill gains `stub__huge` and `stub__inject`, and the policy YAML gets them as opaque tools like `slow`, `test_mcp_tools_call.py:34-54`).
- **Tests** (non-db with the `spy`; capture `record_outcome` args):
  1. `huge(size=5000)` against a server built `McpServer("stub", url, True, McpAuth(type="none"), 30, 2048)`: `isError`, exact text with `2048`, `result_too_large`, size/hash of the upstream, flags `()`; `pattern_detector.inspect` monkeypatched to raise: never called (T15).
  2. Boundary via `fake_call_tool`: canonical length == cap is `ok`; cap + 1 is too large.
  3. `inject` through the stub: result equals upstream, `ok`, flags `[{"list": "injection", "pattern_id": <int>}]`; the phrase absent from the captured args, `caplog` and the audit rows.
  4. Block: a profile with `tool: block` (tmp YAML through `pattern_config.load()` and `settings.PATTERN_CONFIG_FILE`, restore `_policy`; mirror the fixture in `tests/test_pattern_config.py`): the text is exactly `RESULT_BLOCKED_TEXT`, `result_blocked`, response has no phrase/list/pattern id, flags carry the hit, size/hash are the upstream's.
  5. Uninspected: `image`, `audio`, `resource_link`, `{"type": "weird"}`, a non-dict block and a blob-only resource: byte-identical pass-through, flags `[{"uninspected": 6}]`; none -> no dict.
  6. Inspected input: phrase only in `resource.text`, only in `structuredContent`, only split across two text blocks (joined) -> flagged; phrase only in an image block -> not flagged.
  7. Harness texts unscreened: timeout (stub `slow`, as `test_mcp_tools_call.py:444`) and `upstream_error` -> size/hash `None`, flags `()`, `inspect` not called.
  8. Unmodified: unit test `result["content"] is outcome.content`; an email in a text block returns byte-identical (O5).
  9. Fail closed: `inspect` raises -> `result_blocked`, ERROR log without content.
  10. De-dup and order: two hits of one pattern -> one flag; flags sorted.
  11. db-marked: real `record_outcome` stores `result_flags` JSON, `result_bytes`, `result_hash` for ok, too-large and blocked rows; no column holds result text.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_results.py tests/test_mcp_tools_call.py tests/test_mcp_audit.py -m "not db"`

## End-to-End Tests

- [ ] `TestClient` over `/mcp` with the real stub (`mcp_stub`): `huge` over the cap and `inject` (tests 1, 3).
- [ ] db-marked test 11 on CI (Docker is down locally).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_results.py tests/test_mcp_tools_call.py tests/test_mcp_audit.py tests/test_mcp_gateway.py tests/test_action_audit.py tests/test_untouched_app.py -m "not db"
```
No full suite (GitHub CI). `test_pii_redaction_integration.py` only if a test is renamed (none planned). Do not touch `_correlate` (STORY-016).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 too large, exact text, `result_too_large` | 2, 3 | `test_mcp_results.py` tests 1, 2 |
| AC2 inject unmodified, flags name list + pattern id, never text | 1, 2, 3 | tests 3, 10 |
| AC3 `tool: block` -> error result `result_blocked` | 2, 3 | test 4 |
| AC4 image/audio/resource_link uninspected + count; text, resource text, structured inspected as one message | 2, 3 | tests 5, 6 |
| AC5 `result_bytes`/`result_hash` stored (`hash_prompt`), result not stored, no PII redaction | 1, 2, 3 | tests 8, 11, updated digest assertions in `test_mcp_tools_call.py` |

Plus: all tasks completed, validation passes, follows existing patterns.
