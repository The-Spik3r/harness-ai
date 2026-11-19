---
story: STORY-007
prd: PRD-021
slug: output-and-reasoning-gates
title: Hold-back output gate and reasoning gate
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: Hold-back output gate and reasoning gate

## Summary

A new pure-ish module `app/services/stream_redaction.py` holds (a) a Presidio-free `Segmenter` (boundaries, forced cut, tail window, fence tracking) and (b) `OutputGate`, which redacts each released segment with `redaction_spans` over `tail + segment`, keeping only spans that start inside the segment. `pii_redactor.py` gains the span-level entry point `redaction_spans`, built from the exact analysis each path does today, so replacement text is identical to step 8's. The pipeline is not touched (STORY-008 wires it).

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-007-output-and-reasoning-gates.md`
- PRD sections used: 6.5, F5, Risk 1, D7, D8, D21 (not here), T2/T3
- Systems affected: `app/services/pii_redactor.py`, new `stream_redaction.py`, tests

## Design Decisions

- **Span entry point** `pii_redactor.redaction_spans(text, policy, *, analysis=None, json_mode=True) -> list[tuple[int,int,str,str]]` = `(start, end, entity_type, replacement)`, sorted, disjoint; `[]` when `PII_REDACTION_ENABLED` is off or text empty. Plus public `apply_spans(text, spans) -> str` (wraps `_splice`, `pii_redactor.py` `_splice`, which takes `(start,end,replacement,entity)` order: reorder).
  - Chat (`not policy.structure_safe`): `redact()`'s own analyzer call (`pii_redactor.py:136-146`: `_get_analyzer()` with no argument, entities and threshold from the policy, which equal `settings.pii_entities_list`/`PII_SCORE_THRESHOLD`), then the anonymizer's conflict resolution WITHOUT the operator step: `_get_anonymizer()._copy_recognizer_results(results)`, sort by `(start, end)`, `_remove_conflicts_and_get_text_manipulation_data(results, ConflictResolutionStrategy.MERGE_SIMILAR_OR_CONTAINED)` (read the installed `presidio_anonymizer/anonymizer_engine.py:29-36,89-100,133-218`; confirm the default strategy and `merge_entities_with_spaces=False` default). Replacement is `f"<{entity_type}>"` (default `replace` operator). These are private Presidio methods: version pinned (2.2.364), and the equivalence test below is what guards them. Errors wrap as `PiiRedactorError` like `redact()`.
  - Code: `_analyze` -> `_resolve_overlaps` -> `_replacement_ranges` (`:196-330`). Extract the middle of `redact_for_policy` (`pii_redactor.py:466-481`, from `analysis =` to `ranges =`) into private `_code_spans(text, analysis, policy, is_json)`; `redact_for_policy` calls it and keeps its splice, entities and JSON post-condition unchanged. `analysis=None` means `strip_fenced_blocks(text)` when `skip_fenced_blocks`, else `text` (then `_blank_escapes` in JSON mode, as today).
  - Do NOT refactor `redact()` (it keeps `anonymizer.anonymize`; spies on `query_pipeline.redact` and `tests/test_pii_characterization.py` stay untouched). Instead pin: `apply_spans(t, redaction_spans(t, chat)) == redact(t)[0]` over `REDACT_CASES` (`tests/test_pii_characterization.py:97`), and for `code` `== redact_for_policy(t, code).text` over the code corpus (`tests/test_pii_code_corpus.py`, `tests/corpora/`). Entities are not compared (`redact()` reports pre-conflict types).
- **Gate contract (for STORY-008)**: `OutputGate(policy, holdback_max, *, final_redact=pii_redactor.redact_for_policy)`; `feed(text) -> str`; `finish() -> GateResult(released, final_text, final_entities, diverged)` (frozen dataclass). `released` = concatenation of everything `feed`/`finish` returned; `final_*` from ONE `final_redact(raw_whole, policy)`; `diverged = released != final_text`. Read-only property `released_so_far` (what was returned) for STORY-008's mid-stream-fault charge. No settings import, no I/O, no logging.
- **Per segment**: `raw = raw_tail + seg`, `analysis = analysis_tail + seg`; `spans = redaction_spans(raw, policy, analysis=analysis, json_mode=False)`; keep every span with `end > len(raw_tail)`; a span with `start < len(raw_tail)` (it crosses from the tail into the segment) is **clipped** to start at `len(raw_tail)` and keeps its replacement; shift by `-len(raw_tail)`, `apply_spans(seg, shifted)`. Orchestrator decision (3.2): the released head of a crossing entity cannot be recalled, but its continuation is masked rather than leaked; the release then differs from the final pass (`diverged=True`), which is the measured residual. A span wholly inside the tail is ignored. Then `raw_tail = (raw_tail + seg)[-200:]`. `analysis_tail` is the same window with every non-newline character of fenced segments turned into `"\n"` (what `strip_fenced_blocks` does, so `analysis[i] != text[i]` still marks fences structural in `_replacement_ranges`); equal to `raw_tail` under `chat`. `json_mode=False`: a segment is never the document step 8 would test; a whole-reply JSON is a documented source of divergence (final pass authoritative).
- **Failure**: a `PiiRedactorError` from any call propagates; the gate is then poisoned (later `feed`/`finish` re-raise), segments redacted earlier in the same failed `feed` are discarded, never returned, never released raw.
- **Segmenter** (pure, no Presidio, no policy object): `Segmenter(kind: "chat"|"code", holdback_max, skip_fenced: bool)`, `push(text) -> list[Segment]`, `flush() -> list[Segment]`, `Segment(text, fenced)`. Boundary: `chat` first `.?!…` whose NEXT char is whitespace (segment ends after that whitespace char; a terminator at buffer end waits) or first `\n`, whichever is first; `code` `\n` (segment includes it). After boundaries: while `len(buffer) > holdback_max`, cut after the last whitespace (position > 0), else exactly at `holdback_max`. `holdback_max` is validated in [100, 4000] by `config.py:761`; the module only requires `>= 1`.
- **Fences** (`code` + `skip_fenced`): copy the regexes of `pattern_detector.py:144` (`_FENCE_OPEN`) and the closer in `strip_fenced_blocks` (`:195-206`: same char, at least as long, alone on the line, `[ \t]*$`); do not import the private name. State = `(char, length) | None` plus `line_fenced` kept for the rest of a force-cut line. A line is classified when its end arrives (so an opener split across deltas is seen whole); a force-cut line is classified from its head. Opener line and closer line are fenced; unterminated runs to the end. A force-cut line can no longer be a closer (documented limit). Fenced segments go out raw and update only the tails.
- **Policy helpers**: `gate_applies(policy, redaction_enabled) -> bool` = `redaction_enabled and policy.output`. `reasoning_policy(policy)` = `get_pii_policy("chat")` (`pii_policy.py:111-116`: `output=True`, no fences, not structure-safe); idempotent; if `policy.entities` holds a type the chat list lacks, `dataclasses.replace(chat, entities=chat ∪ policy, ...)` so no entity is dropped (the spans path reads `policy.entities`; this is the one place the policy's own list beats settings). `redact_reasoning(text, policy) -> RedactionResult` = `apply_spans(text, redaction_spans(text, reasoning_policy(policy)))` plus sorted entity types, so STORY-008 can pass it as `final_redact` of `OutputGate(reasoning_policy(policy), ..., )`; it ignores `policy.output` (applies under `code` with output off). The master switch still disables it (`[]`), as all redaction. Reasoning uses `chat` boundaries because `reasoning_policy` is `chat`: build its `Segmenter` from `policy.structure_safe`, never from the content policy.
- **Segmenter kind**: `kind = "code" if policy.structure_safe else "chat"`; `skip_fenced = policy.skip_fenced_blocks and policy.structure_safe`.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; no UI here).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Pure module docstring | `app/services/stream_assembly.py:1-12` | cites PRD sections and decisions; says "reads no settings and does no I/O" |
| Frozen result type | `pii_redactor.py:25-37` (`RedactionResult` NamedTuple) | a small result type with a docstring naming the story |
| Error wrapping | `pii_redactor.py:136-160` | `raise PiiRedactorError("PII analysis failed: ...") from exc`, no text in the message |
| Policy under test | `tests/test_pii_structure_safe.py:46-66` | autouse fixture pins `PII_NLP_MODEL=en_core_web_sm`, resets `_analyzer/_anonymizer/_pattern_analyzer`; `_code(**overrides)` builds a pinned `code` policy |
| AST purity test | `tests/test_stream_assembly.py:57-62` | walk `ast.Import/ImportFrom`; here assert no `app.config` import |
| Corpus fixtures | `tests/fixtures/prd021_survey/`, `tests/test_pii_characterization.py:97` | data beside tests; `tests` is a package |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pii_redactor.py` | UPDATE | `redaction_spans`, `apply_spans`, `_code_spans` extraction (outputs byte-identical) |
| `app/services/stream_redaction.py` | CREATE | `Segment`, `Segmenter`, `GateResult`, `OutputGate`, `gate_applies`, `reasoning_policy`, `redact_reasoning` |
| `tests/fixtures/prd021_gate_corpus.py` | CREATE | one two-sentence text per default entity (context sentence first, then the entity sentence) plus `ENTITY` raw string; `CHAT_ENTITIES` taken from `PII_ENTITIES` default |
| `tests/test_stream_segments.py` | CREATE | Presidio-free tests of `Segmenter` and the purity AST test |
| `tests/test_stream_redaction.py` | CREATE | Presidio tests: span equivalence, gate, T2 corpus, fences, reasoning |

## Tasks

### Task 1: Span entry point in `pii_redactor.py`
- **Implement**: as in Design Decisions. Extract `_code_spans`; add `redaction_spans`, `apply_spans`. Leave `redact()` and the `chat` branch of `redact_for_policy` alone.
- **Mirror**: `redact_for_policy` `pii_redactor.py:456-495`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_pii_structure_safe.py tests/test_pii_code_corpus.py tests/test_pii_redactor.py tests/test_pii_characterization.py`

### Task 2: `Segmenter` (pure)
- **File**: `app/services/stream_redaction.py` (top half; imports only `re`, `dataclasses`, `typing`; the Presidio-touching half imports `pii_redactor` and `pii_policy` below it).
- **Implement**: boundary search, forced cut, fence tracking, per Design Decisions. Tail window and `analysis_tail` bookkeeping live in the gate, not here, but expose `TAIL_CHARACTERS = 200`.
- **Validate**: `tests/test_stream_segments.py` (Task 5).

### Task 3: `OutputGate`, `GateResult`, helpers
- **Implement**: per Design Decisions. `feed("")` returns `""`. `finish()` twice raises `RuntimeError("OutputGate already finished")`. `final_redact` result is unpacked as `(text, entities)` (`RedactionResult` is a NamedTuple, `pii_redactor.py:25`).
- **Mirror**: `query_pipeline.py:279-296` (`_redact` branches on `structure_safe`; STORY-008 passes it as `final_redact`).

### Task 4: Corpus fixture
- One entry per entity of the default `PII_ENTITIES` (`config.py:222`): `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `IBAN_CODE`, `LOCATION`. Each `(entity, text, raw)`; the module asserts nothing. The test asserts the precondition that `redact(text)` masks `raw` (so a recognizer miss on `en_core_web_sm` fails loudly instead of passing vacuously); pick sentences the small model detects (probe with `redact()` first; keep each text <= 90 characters).

### Task 5: Tests
`tests/test_stream_segments.py` (no Presidio import; no `pii_redactor` import):
- chat boundaries: `.`, `?`, `!`, `…` followed by whitespace; `\n`; terminator at buffer end waits; `3.5`, `a.b@c.com.` mid-word do not cut; ellipsis `...`.
- every two-way and every three-way split of a text yields the same segments as one push (determinism across deltas).
- forced cut: last whitespace; no whitespace -> exactly `holdback_max`; loop for a buffer of 3x; `flush()` releases the remainder; concatenation of all segments equals the input.
- code: only `\n` cuts; fence tracking: opener split across deltas at every offset (` ``` `, `~~~`, `````` 4 backticks, up to 3 leading spaces), closer must match char and length (a ``` line inside a 4-backtick block stays content), unterminated runs to end, inline backticks not fenced; differential test: fenced-line set equals the lines `strip_fenced_blocks` blanks (`pattern_detector.py:161`) over generated and corpus texts.
- AST: `stream_redaction.py` imports no `app.config`/`settings`; `Segmenter`'s source names no `pii_redactor`.

`tests/test_stream_redaction.py` (module-scoped fixture builds the `en_core_web_sm` analyzer once; every per-offset loop reuses it, injects `final_redact=lambda t, p: (t, [])` to halve the cost):
- span equivalence (Task 1 pins) and `redaction_spans` off-switch.
- gate: tail kept to 200 raw characters; a span wholly inside the tail is ignored and a span crossing from tail into segment is clipped (its segment part masked, `diverged=True`); replacement byte-equal to step 8 so a stream whose entities never cross a boundary has `diverged is False` for EVERY default entity (real `final_redact`), under `chat` and under `code` with the five code entities.
- **T2**: for each corpus entry and each offset `0..len`, feed two deltas then `finish()`; assert `raw not in released`; assert the precondition. Records the loop count to keep the runtime bounded (expect ~7x90 gate runs).
- risk 1 pin: with `holdback_max` below the entity length and no whitespace, a cut inside the entity may leak but `finish().diverged is True` (not an xfail; it asserts the final pass detects it).
- fences: ```` ```py\nemail a@b.com\n``` ```` is released unredacted line by line and `diverged is False`; prose email around it is masked; opener split at every offset.
- `gate_applies`: `chat` True; `code` with `output=False` False; switch off False.
- redactor error: monkeypatch `pii_redactor._get_analyzer` to raise: `feed` raises `PiiRedactorError`, nothing raw returned, gate poisoned.
- reasoning: `reasoning_policy(code with output off)` is `chat`-entity, `output=True`, not structure-safe; `redact_reasoning` masks a PERSON/LOCATION that `code` would not; works as `final_redact` of `OutputGate(reasoning_policy(code), 400, final_redact=redact_reasoning)` with `chat` boundaries (`diverged is False` on a multi-sentence text); union case (a code list with an extra type keeps it).
- a no-log/no-content check: the module has no `logging` import.

## End-to-End Tests

- [ ] None through FastAPI (the gate is not wired until STORY-008). Drive `OutputGate` directly with the real analyzer as above.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stream_segments.py tests/test_stream_redaction.py tests/test_pii_redactor.py tests/test_pii_structure_safe.py tests/test_pii_characterization.py tests/test_pii_code_corpus.py tests/test_pii_pattern_analyzer.py tests/test_pii_policy.py tests/test_pii_redaction_integration.py tests/test_untouched_app.py
```
No test is renamed or removed, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched. Presidio tests need no marker in this repo (none of the `test_pii_*` files use one); they pin the small model via the autouse fixture, as `test_pii_structure_safe.py` does.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 whole segments, tail context, spans from the segment only | 1-3 | `test_stream_redaction.py` gate/tail/ignored-tail-span tests; `test_stream_segments.py` boundary tests |
| AC2 forced cut, `finish()`, `GateResult`, `diverged` | 2, 3 | `test_stream_segments.py` forced-cut tests; `test_stream_redaction.py` divergence tests |
| AC3 T2 every entity, every offset | 3, 4, 5 | `test_stream_redaction.py::test_t2_*` |
| AC4 fences unredacted; `code` output off has no gate | 2, 3 | fence tests in both files; `gate_applies` test |
| AC5 `redact_reasoning` under any policy; pure segmenting | 3, 5 | reasoning tests; AST purity test |

## Open Risks / Notes for the Orchestrator

- `redaction_spans` for `chat` uses private Presidio anonymizer methods (version pinned); the equivalence test is the guard. If the conflict strategy differs from `redact()`'s default, the test fails at once.
- JSON-reply divergence under `code` (gate cannot know the whole text is a JSON document) is expected and left to the final pass.
- A span that starts in the tail and ends in the segment: its head was released raw (cannot be recalled), its segment part is masked by clipping (orchestrator decision); counted by the final pass. Test it with a forced cut inside a multi-word entity (e.g. a PERSON or an IBAN with spaces).
- Reasoning gate with the master switch off is a pass-through, like all redaction; STORY-008 should decide whether reasoning is shown at all then (T3).
