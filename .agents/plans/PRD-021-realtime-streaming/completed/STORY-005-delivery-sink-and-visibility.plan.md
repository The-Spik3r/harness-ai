---
story: STORY-005
prd: PRD-021
slug: delivery-sink-and-visibility
title: DeliverySink, step 2d visibility and stage events
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: DeliverySink, step 2d visibility and stage events

## Summary

New pure module `app/services/delivery.py` (protocol, vocabularies, event dataclasses, `Visibility`, `QueueSink`) and a trailing keyword-only `sink=None` on `run_conversation`. When a sink is given, the pipeline wraps it in a fault-swallowing `_SafeSink`, emits config-only stage events at the head of steps 2, 2c, 4, 5, 6, 7c, 8, and after step 2c computes `Visibility` into a local. With `sink=None` nothing is computed. `content`/`reasoning`/`phase`/`committed` are defined but never called here.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-005-delivery-sink-and-visibility.md`
- PRD sections used: 6.1, 6.3, 6.4, 6.9, F3, F4, 7.1, D3, D11, D18, D20, T8, T10
- Systems affected: `query_pipeline.run_conversation` only (`run_query`, `/query`, routers, chat UI untouched)

## Design Decisions (orchestrator's binding points, plus choices made)

- **`Visibility`**: `@dataclass(frozen=True)` `(realtime, reasoning, upstream_streamed)`; classmethod `Visibility.compute(*, streaming_enabled, holds_realtime, holds_reasoning, caps, ingress)`. No settings import, no I/O. `caps` is a `Capabilities` (`provider_registry.py:88`; only `.streaming`/`.reasoning` are read, duck-typed, no import). Formulas as AC3: `realtime = sw and holds_rt and caps.streaming`; `reasoning = sw and holds_rv and caps.reasoning`; `upstream_streamed = sw and caps.streaming and (realtime or reasoning or ingress == "chat")`.
- **Reasoning is independent of realtime** (D3, table 6.4: buffered SSE can still carry reasoning). Do not AND it with `realtime`.
- **Where Visibility lives**: a local `visibility: Optional[Visibility] = None` in `run_conversation`, next to `admission` (`query_pipeline.py:549`). The function keeps per-request state in locals; there is no context object. STORY-006's step 7 reads the local. It is `None` iff `sink is None`.
- **`sink=None` computes nothing**: `safe = _SafeSink(sink, identity) if sink is not None else None`; every emission is `if safe is not None: safe.stage(...)`. No Visibility, no `holds()`, no `STREAMING_ENABLED` read, no stage names on that path.
- **Sink faults**: `_SafeSink` (private, in `query_pipeline.py`) has `stage/phase/content/reasoning/committed`; each calls the real method in `try/except Exception`, logs once per request (a `_faulted` flag; `logger.warning("delivery sink failed: user_id=%s method=%s", ...)`, never a payload, T9) and carries on. This is the `_emit(sink, method, *args)` helper as a class, because "once per request" needs state. STORY-006 reuses it for the other four methods.
- **Stages depend on configuration only (T10)**: emitted at the head of a step iff it runs under the settings/inputs shape. 2 always; 2c iff `settings.USAGE_LIMITS_ENABLED`; 4 always; 5 always; 6 iff `settings.PII_REDACTION_ENABLED and not relaxed` (`relaxed` is route-derived config, `route.relaxes_input()`; emit after the `relaxed` line, before the size-limit arm); 7c iff `openrouter_result.tool_calls` (response shape, not a finding); 8 (`masking_output`) iff `policy.output and settings.PII_REDACTION_ENABLED`. Never conditioned on `inspection`, `entities`, `exceeded` or any check result. A refused request emits the stages up to the refusing step and no Visibility (2d sits after 2c; 2b break-glass emits nothing). No stage for 2b, 3 or 7.
- **Event shape** (frozen dataclasses in `delivery.py`, one per sink method, consumers use `isinstance`/`match`): `StageEvent(name)`, `PhaseEvent(name, action_kind=None)`, `ContentEvent(text)`, `ReasoningEvent(text)`, `CommittedEvent(completion_id)`; `DeliveryEvent = Union[...]`. No end-of-stream sentinel here: `close()` only stops further puts. The end signal belongs to consumers (006/010/011), which know when the pipeline future finishes.
- **`QueueSink(loop, queue=None)`**: `self.queue = queue or asyncio.Queue()` (unbounded). Each method builds its event and calls `_put`: `if self._closed: return`; `try: loop.call_soon_threadsafe(self.queue.put_nowait, event)` `except RuntimeError: self._closed = True` (loop closed). `close()` sets `_closed`. Called from the executor thread (`pipeline_executor.run_in_pipeline`), consumed on the loop, hence `call_soon_threadsafe`. Implementer: check the venv's Python version for `asyncio.Queue()` creation off-loop.
- **Vocabularies**: `StageName` (the 7 names of PRD 7.1) and `PhaseName` (`waiting`, `thinking`, `writing`, `preparing_action`) as `Literal` aliases like `Ingress` at `query_pipeline.py:65`, with `get_args` tuples for tests. `phase_of` is STORY-006's.
- **`OperationKind`**: import from `app.services.action_classifiers` (it defines it; `action_adapters.py:49` only re-exports). Verify that package's imports stay settings-free; the purity test pins the allowed module set.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; no UI in this story).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Defaulted keyword | `query_pipeline.py:382-403` | trailing keyword-only param with a comment citing the PRD section and decision; `sink: Optional[DeliverySink] = None` after `tools` |
| Step-local state | `query_pipeline.py:549-551` | `admission = None`, then set under a condition: same for `visibility` |
| Per-request settings read | `query_pipeline.py:550`, `:676` | read `settings.X` in the pipeline, pass values to pure code |
| Log without content | `query_pipeline.py:682-688` | `user_id` and ids only |
| Closed vocabulary | `query_pipeline.py:65` | `Literal` alias plus `get_args` |
| Purity test | `tests/test_v1_translate_request.py:333-355` | AST walk: allowed module set + forbidden names |
| Test fixtures | `tests/test_query_pipeline_run_conversation.py:35-36,55-58` | `_JUAN`, `_fake_call_openrouter` |
| File-mode registry | `tests/_providers.py:29-50` | `providers_file(...)` with `streaming: true` / `reasoning: true` |
| Signature pin | `tests/test_query_pipeline_run_conversation.py:69-98` | parameter-list assertion |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/delivery.py` | CREATE | protocol, vocabularies, events, `Visibility`, `QueueSink` |
| `app/services/query_pipeline.py` | UPDATE | `_SafeSink`, `sink=` keyword, stage emissions, step 2d local |
| `tests/test_delivery.py` | CREATE | purity, truth table, `QueueSink` |
| `tests/test_query_pipeline_delivery.py` | CREATE | stage lists, visibility, fault isolation, refusals, `sink=None` |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE | signature test gains `"sink"` (comment citing PRD-021 STORY-005, D18) |

## Tasks

### Task 1: `app/services/delivery.py`
- **Implement**: module docstring citing 6.1/6.3/6.4, D18, T10 and the purity rule; imports limited to `asyncio`, `dataclasses`, `typing`, `app.services.action_classifiers`. Vocabularies, five event dataclasses, `DeliverySink(Protocol)` (signatures as PRD 6.3), `Visibility` + `compute`, `QueueSink`.
- **Mirror**: `app/services/pii_policy.py` (frozen dataclass, docstring style); `v1_sse.py` header for "reads no settings, the caller passes values".
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_delivery.py`

### Task 2: pipeline wiring (`query_pipeline.py`)
- **Implement**:
  1. Import `DeliverySink`, `Visibility`; `holds`, `PERMISSION_STREAM_REALTIME`, `PERMISSION_REASONING_VIEW` from `app.services.authz`. Add `_SafeSink` near `_route_fields` (`:286`).
  2. Add `sink` to the signature after `tools` (comment: PRD-021 D18, 6.9; passed only by an ingress that reports progress; `run_query` passes nothing).
  3. After step 1c create `safe`; `stage("checking_permissions")` at the head of step 2, before `authorize(identity, PERMISSION_QUERY_SUBMIT)` (`:447`).
  4. `checking_usage` just inside `if settings.USAGE_LIMITS_ENABLED:` (`:550`), before `admit()`.
  5. New "Step 2d" block after the 2c block, before step 3 (`:579-580`): under `if safe is not None`, `visibility = Visibility.compute(streaming_enabled=settings.STREAMING_ENABLED, holds_realtime=holds(identity, PERMISSION_STREAM_REALTIME), holds_reasoning=holds(identity, PERMISSION_REASONING_VIEW), caps=route.capabilities, ingress=ingress)`. Comment: after 2c on purpose (a refused caller must not learn by timing whether its role holds a grant), `holds()` not `authorize()` (T8), read by STORY-006's step 7.
  6. Stage calls for 4 (before `check_duplicate`, `:637`), 5 (before `inspect`, `:677`), 6, 7c (inside `if openrouter_result.tool_calls:`), 8 per the rules above.
- **Mirror**: step-comment style at `:516-548` (the position is the decision).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: tests
- `tests/test_delivery.py`: AST purity (imports subset; no `settings`/`open`/`logging` names); full `Visibility.compute` truth table with `itertools.product` over `(streaming_enabled, holds_rt, holds_rv, caps.streaming, caps.reasoning, ingress in {"chat","v1","query",None})` against an independent restatement of 6.1, plus named cases: chat with neither grant gives `upstream_streamed` true and `realtime`/`reasoning` false; switch off, or `caps.streaming` false, gives `upstream_streamed` false always; reasoning true with realtime false; frozen (`FrozenInstanceError`). `QueueSink`: events arrive in order from a worker thread on a running loop; after `close()` nothing is queued; on a closed loop a put is dropped without raising; vocabularies equal the PRD 7.1 lists.
- `tests/test_query_pipeline_delivery.py` (`temp_db`, injected `call_openrouter`, a recording sink, `monkeypatch.setattr(settings, ...)`):
  (a) `sink=None` result equals sink-given result; spies on `query_pipeline.holds` / `query_pipeline.Visibility` are never called with `sink=None`.
  (b) a sink whose every method raises: same result and same audit row as `sink=None`, exactly one warning record, none containing the prompt.
  (c) exact ordered stage lists for 3-4 configs: all on; usage off; PII off; `code` profile (output off) with tool calls so `evaluating_actions` appears and `masking_output` does not.
  (d) refusals: step 2 denial gives `["checking_permissions"]`; usage refusal ends at `checking_usage`; duplicate at `checking_duplicates`; suspicious at `inspecting_prompt`; none computes Visibility (spy).
  (e) the stage list is identical for a clean prompt and one with PII / a flag (T10).
  (f) visibility matrix over roles with/without each grant (grants via monkeypatched `authz.ROLE_PERMISSIONS`, as `tests/test_authz.py` does), `STREAMING_ENABLED` on/off, file-mode registry caps: the sink's `content`/`reasoning` call count is always zero, and the Visibility captured by the spy equals `compute(...)`; with `RBAC_ENABLED=false` and a role lacking the grant, `realtime` is false (T8).
  Update the signature test list in `test_query_pipeline_run_conversation.py` (add `"sink"`, default `None`, keyword-only).
- **Validate**: targeted run below.

## End-to-End Tests

- [ ] `TestClient(app)` POST `/query` returns the same body as before and writes one row (no sink possible there).
- [ ] Run `run_conversation` via `run_in_pipeline` with a `QueueSink` on a real loop and read the stage events off the queue in order.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_delivery.py tests/test_query_pipeline_delivery.py tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_usage_limits.py tests/test_query_pipeline_audit_fields.py tests/test_untouched_app.py
```
Full suite: GitHub CI on push. No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 pure module, protocol, vocabularies, Visibility, QueueSink | 1 | `tests/test_delivery.py` (purity, truth table, QueueSink closed / loop gone) |
| AC2 `sink=None` computes nothing, callers unchanged | 2 | `test_query_pipeline_delivery.py` (a); signature test; existing pipeline suites |
| AC3 step 2d after 2c per 6.1, never on refusal | 2 | truth table, refusal tests (d), RBAC-off test (f) |
| AC4 config-only stage events | 2 | ordered-list tests (c), T10 test (e) |
| AC5 content/reasoning never called; `/query` passes no sink | 2 | matrix test (f); `run_query` signature test unchanged |
| Sink-fault isolation (design point) | 2 | all-methods-raise test (b) |
