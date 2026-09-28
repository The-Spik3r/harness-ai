---
story: STORY-008
prd: PRD-012
slug: redact-for-policy
title: "redact_for_policy: fence skipping, structure-safe replacement, JSON-aware mode"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: redact_for_policy: fence skipping, structure-safe replacement, JSON-aware mode

## Summary

This story adds `redact_for_policy(text, policy) -> RedactionResult` to `app/services/pii_redactor.py`. It is the `code` profile's masking primitive, and `redact()` is left untouched.

For a policy with `structure_safe=False` (only `chat`), it returns `RedactionResult(*redact(text))`, so `chat` stays byte-identical by construction. For a structure-safe policy it runs the PRD Section 6.5/6.6 pipeline:

1. **Blank.** Blank fenced blocks with `strip_fenced_blocks` when `policy.skip_fenced_blocks` is set.
2. **Analyze.** Run the blanked text through `_get_analyzer(policy.entities)` at `policy.threshold`, in line-aligned windows of at most 20,000 characters. STORY-003 made this chunking (R3) a condition of `PII_MAX_CHARACTERS_CODE = 200,000`.
3. **Resolve overlaps.** Keep the longest span first, then the earliest start, then the entity type name.
4. **Post-process.** Structure-safe splitting treats quotes, backticks, line breaks, whole escape sequences and fenced bytes as structural. In JSON-aware mode, spans are also clipped to string interiors and whole number tokens.
5. **Replace.** Replace once, in the **original** text, with our own splicing (no `AnonymizerEngine`).
6. **Check.** In JSON-aware mode, the post-condition `json.loads(result)` must succeed. Otherwise the call raises `PiiRedactorError("redaction would produce invalid JSON")`.

Nothing on the request path calls it yet. STORY-009 wires it into step 6.

## User Story

As an integrating developer
I want redaction under `code` to mask PII in prose without ever breaking a quote, a line, or a JSON document
So that the model reads my code and tool results as valid structure

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-008-redact-for-policy.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`: Sections 6.5 (D2), 6.6, 7/F7, 8, 9.2 (T6), 11, 14 (Risks 4, 5)
- Handoffs consumed:
  - **STORY-001 report.** Reuse `_JSON_FILES` / `_CODE_FILES` / `_ALL_JSON` from `tests.test_pii_corpus_files`. The edge-case location table is used in Task 8.
  - **STORY-003 report (R3).** Chunking is a requirement: line-aligned windows of ≤ 20,000 characters, offsets shifted, replaced once. `scripts/measure_pii_latency.py:385-408` (`_chunks`, `_chunked_results`) is the reference.
  - **STORY-004 report.** `strip_fenced_blocks` is length-preserving. `pattern_detector` must not mention PII, and the dependency runs one way, from `pii_redactor` to `pattern_detector`.
  - **STORY-006 report.** Always call `_get_analyzer(policy.entities)`, never the no-argument form.
  - **STORY-007 report.** `from app.services.pii_policy import PiiPolicy` is cycle-free. Apply `PII_REDACTION_ENABLED` here. Build test policies with `dataclasses.replace(get_pii_policy("code"), ...)`.

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `app/services/pii_redactor.py`, `tests/test_pii_structure_safe.py` (new) |
| Story | STORY-008 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Depends on | STORY-001 ✅ (`beeb0b9`), STORY-004 ✅ (`3c68981`), STORY-006 ✅ (`0d398aa`), STORY-007 ✅ (`50ef312`) |
| Blocks | STORY-009, STORY-013 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | None. The story's `skills: []` and "Skills: none applicable" hold. `.agents/skills/` contains only `frontend-design` (visual UI design), and this story changes no UI. | — |

---

## Findings (measured before planning)

| # | Finding | Evidence | Consequence |
|---|---------|----------|-------------|
| F-1 | `RedactionResult` does not exist anywhere in the repo. `redact()` returns a bare `Tuple[str, List[str]]`. | `grep -r RedactionResult app tests scripts` is empty; `pii_redactor.py:137-163` | This story defines it (P1). |
| F-2 | `pii_redactor` has **no logger** and never logs. | `pii_redactor.py:1-13` | Nothing is logged. Spans are PII, and the error messages carry no text either (P10). |
| F-3 | `PiiRedactorError` is a bare `pass` class. `redact()` wraps analyzer failures as `PiiRedactorError(f"PII analysis failed: {exc}") from exc`. | `pii_redactor.py:16-17, 150-151` | Reuse the same message for analysis failures, and raise the same class for the post-condition. |
| F-4 | `strip_fenced_blocks` replaces every non-newline character inside a fence with `"\n"`, so `len` and all offsets are preserved. An unterminated fence runs to the end of the text. | `pattern_detector.py:161-206` | AC 1's unterminated case needs no extra code. A position `i` is inside a fence exactly when `blanked[i] != text[i]`, or when it is a newline inside the fence (see P6). |
| F-5 | **A lone backslash is not enough to preserve an escape.** `ticket-thread-export.json:32` has `...card.\n\nThanks,\nAisha Bello` inside a JSON string. The analyzer sees the raw characters `\` and `n`. Splitting a span only around `\` still replaces the `n...` run, which gives `\<PERSON>`. That is an invalid escape in JSON and in Java, and a `SyntaxWarning` in Python. An email recognizer matching `njane@…` after a `\n` has the same effect. | corpus file; PRD 6.6 rule 1 lists `\` only | The **whole escape sequence** is structural (P6). This is a strict extension of rule 1: it keeps more characters, never fewer. Without it, AC 3's `json.loads` over the corpus could fail. |
| F-6 | `json.loads` accepts `NaN`, `Infinity` and `-Infinity`, and duplicate keys (last one wins). | stdlib behaviour | The scanner treats the three constants as literals (dropped, P7). Masking two PII keys in one object to the same `"<EMAIL_ADDRESS>"` still parses. The information loss is documented, not prevented. |
| F-7 | No valid JSON document has a raw newline inside a string, so a fence line can only sit **outside** strings, where it would make the document invalid. | JSON grammar | On a document that passes JSON detection, fence blanking is a no-op, and the two modes do not interact. |
| F-8 | The test pattern for analyzer tests is an autouse fixture that sets `PII_NLP_MODEL="en_core_web_sm"` and `PII_REDACTION_ENABLED=True`, pins `PII_ENTITIES_CODE`, and resets all three singletons. Stubs are injected with `monkeypatch.setattr(pii_redactor, "<singleton>", stub)`. | `tests/test_pii_pattern_analyzer.py:30-39, 223-242` | Mirror it. Stub spans are injected by patching `_get_analyzer`. A separate test pins that the real call is `_get_analyzer(policy.entities)`. |
| F-9 | `tests/test_pii_characterization.py` exports `REDACT_CASES` and allows it to be imported, but not copied. | `test_pii_characterization.py:33-35, 97-150` | AC 5 is parametrized over `REDACT_CASES`. |
| F-10 | `scripts/measure_pii_latency.py` is importable from tests as `scripts.measure_pii_latency as bench`. | `tests/test_measure_pii_latency.py:23, 141-153` | A drift test pins our windowing to `bench._chunks`, the R3 reference. |
| F-11 | The JSON corpus has no per-file expected-entity list. `SOURCES.md:204-238` describes the number-token phones (`crm-contact-search.json`), number-token cards (`payment-webhook.json`), PII keys (`directory-index-by-email.json`) and escapes (`ticket-thread-export.json`) in prose. | `tests/corpora/pii/SOURCES.md` | AC 3's corpus test asserts `json.loads` succeeds for every file. Targeted assertions name the documented cases (a card literal disappears as a number and appears as `"<CREDIT_CARD>"`). |

---

## Patterns to Follow

### Naming and module structure: private helpers, lazily built singletons, settings read at call time

```python
# SOURCE: app/services/pii_redactor.py:96-113
def _get_analyzer(entities: Optional[Iterable[str]] = None) -> AnalyzerEngine:
    """The analyzer for an entity list (PRD-012 F6).
    ...
    """
    global _analyzer, _pattern_analyzer
    if entities is None or not _NER_ENTITY_TYPES.isdisjoint(entities):
```

### Error handling

```python
# SOURCE: app/services/pii_redactor.py:137-151
def redact(text: str) -> Tuple[str, List[str]]:
    if not settings.PII_REDACTION_ENABLED or not text:
        return text, []
    ...
    except Exception as exc:
        raise PiiRedactorError(f"PII analysis failed: {exc}") from exc
```

### Chunking reference (R3)

```python
# SOURCE: scripts/measure_pii_latency.py:385-408
def _chunks(text: str, size: int) -> list[tuple[int, str]]:
    """(offset, chunk) windows of at most `size` characters, each ending just after a newline
    where one exists, so no line is split. The chunks rejoin to `text`."""
    ...
        for r in analyzer.analyze(text=chunk, language="en", entities=list(entities), score_threshold=threshold):
            results.append(RecognizerResult(r.entity_type, r.start + offset, r.end + offset, r.score))
```

### `#:` constant comments citing the PRD

```python
# SOURCE: app/services/pii_policy.py:62-67
#: D8. An unknown profile resolves to the strictest policy, never the most permissive one ...
FALLBACK_POLICY_NAME = "chat"
```

### Tests: autouse model and singleton reset; stub injection

```python
# SOURCE: tests/test_pii_pattern_analyzer.py:30-39
@pytest.fixture(autouse=True)
def _small_model_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    # Pinned so a developer's .env cannot change which analyzer load() selects.
    monkeypatch.setattr(settings, "PII_ENTITIES_CODE", ",".join(_CODE_ENTITIES))
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    monkeypatch.setattr(pii_redactor, "_pattern_analyzer", None)
    yield
```

```python
# SOURCE: tests/test_pii_pattern_analyzer.py:223-242 (a tripwire proves an analyzer is never touched)
monkeypatch.setattr(pii_redactor, "_analyzer", _Tripwire(tripwire_log))
```

### Tests: corpus reuse and the characterization import

```python
# SOURCE: tests/test_measure_pii_latency.py:23-24
import scripts.measure_pii_latency as bench
from tests import test_pii_corpus_files as corpus_files
```

```python
# SOURCE: tests/test_pii_characterization.py:150-153
@pytest.mark.parametrize("text,expected_text,expected_entities", REDACT_CASES, ids=_REDACT_IDS)
def test_redact_output_is_pinned(text, expected_text, expected_entities):
    assert pii_redactor.redact(text) == (expected_text, expected_entities)
```

---

## Design

### Files to CREATE
- `tests/test_pii_structure_safe.py`

### Files to UPDATE
- `app/services/pii_redactor.py`: `RedactionResult`, window and overlap helpers, structure-safe splitting, JSON scanner and clipping, `redact_for_policy`

### Dependency order
1. `RedactionResult` and the `redact_for_policy` shell (master switch, `chat` delegation)
2. Windowed analysis
3. Overlap resolution
4. Structure-safe runs (escapes, fence guard)
5. JSON detection, scanner, clipping
6. Splicing, entity list, post-condition, and the full docstring
7. Tests, one AC at a time
8. Regression sweep

### Decisions made here

| # | Decision | Why |
|---|----------|-----|
| P1 | `class RedactionResult(NamedTuple): text: str; entities: List[str]`. It is a NamedTuple, not the services' usual frozen dataclass. | AC 5 says the `chat` result "is identical to `redact(text)`". A NamedTuple compares equal to the `(text, entities)` tuple that `redact()` returns and unpacks the same way, so STORY-009 can swap one call for the other at step 6. `entities` is a sorted `list`, like `redact()`'s. |
| P2 | `if not settings.PII_REDACTION_ENABLED or not text: return RedactionResult(text, [])`, placed first. | This is the master switch (STORY-007 handoff, PRD 9.3), in `redact()`'s own guard shape. |
| P3 | `if not policy.structure_safe: return RedactionResult(*redact(text))`. | `chat` is today's `AnonymizerEngine` path by construction (PRD 6.6, last paragraph; Risk 6). `pii_policy._check_consistent` already forbids `skip_fenced_blocks` without `structure_safe`, so this branch never needs fence handling. `redact()` reads `PII_ENTITIES` and `PII_SCORE_THRESHOLD` from `settings`, and the `chat` policy is built from those same two settings (`pii_policy.py:107-122`). A test pins that equality, so a future non-chat, non-structure-safe policy cannot silently ignore its own entity list. |
| P4 | Analysis: `analysis = strip_fenced_blocks(text) if policy.skip_fenced_blocks else text`. `_analyze(analysis, policy)` calls `_get_analyzer(policy.entities)` once, then `analyze(text=chunk, language="en", entities=list(policy.entities), score_threshold=policy.threshold)` per `_analysis_windows(analysis)` window, and shifts `start`/`end` by the window offset. `_ANALYSIS_WINDOW_CHARACTERS = 20_000`, with a `#:` comment citing STORY-003 R3. `_analysis_windows` is `_chunks`, copied and not imported, because `app/` must not depend on `scripts/`. A test pins the two against each other. A failure raises `PiiRedactorError(f"PII analysis failed: {exc}") from exc`. | R3 is a condition of the 200,000 limit. At 200k, unchunked p95 is 2,712 ms, over budget, and chunked is 751 ms. Chunked and unchunked spans were identical at 200k. The error message is `redact()`'s, so the pipeline's error arm treats both the same. |
| P5 | Overlap rule, in the docstring: sort analyzer spans by `(-(end - start), start, entity_type)` and accept each span that does not overlap (`[start, end)` intersection) an accepted one. | The story requires "longest first, then earliest start" and asks for the rule to be documented. The entity-name tiebreak makes equal spans of different types deterministic too. Presidio can return a `PHONE_NUMBER` and a `US_SSN` over the same digits. |
| P6 | **Structural positions**, which are never replaced. Position `i` is structural when any of these holds: (a) `text[i]` is one of `"`, `'`, `` ` ``, `\r`, `\n`; (b) `i` is inside an escape sequence, found by one left-to-right `re.finditer(r"\\(?:u[0-9A-Fa-f]{4}\|U[0-9A-Fa-f]{8}\|x[0-9A-Fa-f]{2}\|.)", text, re.DOTALL)`, which consumes `\\` pairs correctly; (c) `analysis[i] != text[i]`, meaning inside a blanked fence. Each accepted span is split into maximal runs of non-structural positions. A run is replaced by `<TYPE>` only if it contains at least one `str.isalnum()` character. | (a) is PRD 6.6 rule 1. (b) extends rule 1 because a lone kept `\` can still produce an invalid escape (F-5): `"\u00e9"` would become `"\u<X>"` and `"\njane@x.io"` would become `"\<EMAIL_ADDRESS>"`. A bare backslash that no escape follows (`C:\` at the end of the text) is still covered by the `.` branch. (c) is a guard. The analyzer cannot match inside a run of newlines, but this guarantees fenced bytes are unchanged whatever the analyzer returns. The escape intervals are computed only when the text contains `\`, as a sorted list searched with `bisect`. |
| P7 | JSON mode is detected when `text.lstrip()[:1] in ("{", "[")` **and** `json.loads(text)` succeeds (`ValueError`, which includes `JSONDecodeError`, and `RecursionError` mean "not JSON"). `_json_tokens(text) -> list[tuple[str, int, int]]` returns `("string", start, end)` from the opening to the closing quote inclusive, and `("number", start, end)` for `-?(0\|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?`. It skips whitespace, punctuation, `true`/`false`/`null` and `NaN`/`Infinity`/`-Infinity` (F-6). It runs only on a document `json.loads` has already accepted, so it need not validate. Each accepted span is intersected with every token it overlaps: a **string** piece is clipped to the interior `[start+1, end-1)` and then split as in P6; a **number** overlap replaces the whole token with `'"<TYPE>"'`; everything else is dropped. | PRD 6.6 rule 2 and Section 8: locate tokens by offset, never reserialize, so formatting survives. The whole token is replaced even when the span covers only part of it (`-4155550134`, a phone inside a float), because a partial replacement cannot yield a JSON value. Keys are string tokens too, which covers AC 3's "string value or key". |
| P8 | Replacement ranges `(start, end, replacement, entity_type)` are generated in the P5 priority order. A range that overlaps one already taken is dropped. This happens only when two spans widen onto the same number token. Ranges are applied in start order with one `"".join` over the original text. | This avoids an `AnonymizerEngine` dependency for `code` (story Technical Notes; PRD Section 8) and keeps replacement linear. |
| P9 | `entities = sorted({entity_type of every range actually applied})`. | Under `code`, a span can be dropped entirely: punctuation only, no alphanumeric run, or entirely inside a fence. Reporting its type would feed `pii_detected_input` (PRD 6.8) with PII that was never masked. Under `chat` (P3) the list is exactly `redact()`'s. This differs from `redact()`'s "every analyzer result", and the docstring says so. |
| P10 | The post-condition runs in JSON mode only: `json.loads(result)`. On failure: `raise PiiRedactorError("redaction would produce invalid JSON") from exc`. No text or span is added to the message. | This is the story's exact message. The text is PII, and the pipeline's error arm writes `error_message` to the audit table (PRD 6.6 rule 3). Outside JSON mode no parser exists to check against. The structural-character invariant is proved by tests instead (Task 8, AC 2 over the code corpus). |
| P11 | The docstring carries PRD Section 6.6's tool-call paragraph **verbatim** ("**Tool-call arguments are never redacted.** In this PRD that holds by construction: … once PRD-016 admits it."). | This is the story's Technical Notes. It is the written contract PRD-016 must keep. |
| P12 | Imports: `import bisect, json, re`; `from typing import NamedTuple` (extending the existing `typing` line); `from app.services.pattern_detector import strip_fenced_blocks`; `from app.services.pii_policy import PiiPolicy`. Nothing is added to `pattern_detector`. | STORY-004's guard test (`tests/test_pii_dedup_isolation.py:220-228`) forbids PII words and names in `pattern_detector`, and this story does not touch it. `pii_policy` never imports `pii_redactor` (its docstring and the STORY-007 report), so there is no cycle. |
| P13 | Helpers are private module functions (`_analysis_windows`, `_analyze`, `_resolve_overlaps`, `_escape_intervals`, `_structure_safe_runs`, `_is_json_document`, `_json_tokens`, `_replacement_ranges`, `_splice`). They are pure apart from `_analyze`. | This gives each rule a unit-test seam, and gives AC 4 a seam for forcing the post-condition (P14) without a public parameter. It follows the module's `_build_*` / `_get_*` naming. |
| P14 | AC 4 is forced by combining a stub analyzer with `monkeypatch.setattr(pii_redactor, "_json_tokens", …)`. The patched scanner claims one string token over the whole document, and the stub returns a span over `a": 1` in `{"a": 1}`. The result `{"<X>"<X>}` fails `json.loads`, and the test expects `PiiRedactorError`. | With P6 and P7 correct, **no analyzer span alone can break a valid document**. Every replacement is either inside a string interior with no quote, backslash or control character, or a quoted placeholder in place of a number. That is the intent: the post-condition is a backstop (PRD Risk 5). The docstring of the AC 4 test says why a second seam is needed. |

### Risks

| Risk | Mitigation |
|------|------------|
| The escape rule (P6b) marks too much as structural in non-string contexts, for example a Windows path in prose, `C:\Users\jane`, where `\U` + `sers` is not hex and only `\U` is kept. | This errs toward keeping characters, never toward breaking structure. The PII in such a path is a username, which default `code` does not detect. Documented in the docstring. |
| Chunk boundaries cut a span in half on a line longer than 20,000 characters (the hard cut). | This is accepted by R3, and was measured identical at 200k on the corpus. A single-line minified JSON document over 20k is the realistic case: a phone cut at the boundary goes unmasked, and a half-matched span inside a string is still clipped safely. Stated in the docstring. A test pins that a PII token placed across no boundary, 30k characters in, is found with correct offsets. |
| Real-analyzer scores differ between `en_core_web_sm` and lg. | Under default `code` entities the tokenizer-only analyzer is used, and it loads no model. AC 1 and AC 3 use it. Stub analyzers cover AC 2 and AC 4. Only the `PERSON` selection test touches a model, and it asserts the analyzer selected, not scores. |
| JSON detection costs a full `json.loads` on every `{`/`[` message, up to 200k characters. | It is linear and C-accelerated, a few ms at 200k against a 1,500 ms budget. STORY-013 re-runs the benchmark and asserts the budget. |
| `chat` drifts. | P3 delegates to the unchanged `redact()`. AC 5 is parametrized over `REDACT_CASES`, and `git diff --exit-code` guards the four protected test files. |
| Duplicate masked keys lose information (`{"a@x.io": 1, "b@x.io": 2}` becomes two `"<EMAIL_ADDRESS>"` keys, and `json.loads` keeps the last). | The document still parses (F-6), as T6 requires. This is the placeholder-collision question D5's spike (STORY-012) owns. It is noted in the docstring and the handoff. |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pii_redactor.py` | UPDATE | `RedactionResult`, `_ANALYSIS_WINDOW_CHARACTERS`, the P13 helpers, `redact_for_policy` |
| `tests/test_pii_structure_safe.py` | CREATE | AC 1–5, the P4–P9 rules, and corpus-level checks |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `RedactionResult` and the `redact_for_policy` shell

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**:
  - Extend the imports (P12).
  - After `PiiRedactorError`, add `class RedactionResult(NamedTuple)` (P1). Its docstring says it is equal to and unpacks like `redact()`'s `(text, entities)`, and that `entities` is sorted.
  - At the end of the file, add `def redact_for_policy(text: str, policy: PiiPolicy) -> RedactionResult:` with P2, then P3, then `raise NotImplementedError` as a placeholder. Task 6 replaces it.
- **Mirror**: `pii_redactor.py:137-139` (guard shape)
- **Validate**: `.venv/Scripts/python.exe -c "from app.services.pii_redactor import redact_for_policy, redact, RedactionResult; from app.services.pii_policy import get_pii_policy as g; t='Mail jane.doe@example.com'; assert redact_for_policy(t, g('chat')) == redact(t)"`

### Task 2: Windowed analysis (R3)

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**:
  - `_ANALYSIS_WINDOW_CHARACTERS = 20_000` with a `#:` comment: STORY-003 R3 makes 200,000 affordable; unchunked analysis is superlinear.
  - `_analysis_windows(text, size=_ANALYSIS_WINDOW_CHARACTERS) -> list[tuple[int, str]]`: the `_chunks` algorithm, verbatim.
  - `_analyze(analysis: str, policy: PiiPolicy) -> list`: returns `RecognizerResult`-shaped results with shifted offsets. Build new `presidio_analyzer.RecognizerResult(entity_type, start + offset, end + offset, score)` objects, as the script does; do not mutate Presidio's. Wrap failures as in P4.
- **Mirror**: `scripts/measure_pii_latency.py:385-408`
- **Validate**: `.venv/Scripts/python.exe -c "import app.services.pii_redactor as p; t='a\n'*30000; w=p._analysis_windows(t); assert ''.join(c for _,c in w)==t and all(len(c)<=20000 for _,c in w)"`

### Task 3: Overlap resolution

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**: `_resolve_overlaps(results) -> list`, following P5. It returns the accepted spans **in priority order**, because P8 depends on that order. The docstring states the rule in one sentence. `redact_for_policy`'s docstring repeats it.
- **Mirror**: the docstring style of `pii_redactor.py:96-105`
- **Validate**: covered by Task 8's `test_overlapping_spans_*`

### Task 4: Structure-safe runs

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**:
  - `_STRUCTURAL_CHARACTERS = frozenset("\"'`\r\n")`, with a `#:` comment citing PRD 6.6 rule 1. It also notes that the placeholder alphabet (`<`, `>`, `A-Z`, `_`) contains none of them.
  - `_ESCAPE = re.compile(r"\\(?:u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|x[0-9A-Fa-f]{2}|.)", re.DOTALL)`, with a comment citing F-5 and the corpus line `ticket-thread-export.json:32`.
  - `_escape_intervals(text) -> list[tuple[int, int]]`: returns `[]` quickly when `"\\" not in text`.
  - `_structure_safe_runs(text, analysis, escapes, start, end) -> list[tuple[int, int]]`: the maximal runs in `[start, end)` whose positions are not structural (P6 a/b/c) and that contain at least one alphanumeric character. Use `bisect` over the escape starts, and check `analysis[i] != text[i]` for the fence guard.
- **Mirror**: n/a (new logic). Keep the `#:` constant comments.
- **Validate**: `.venv/Scripts/python.exe -c "import app.services.pii_redactor as p; t='\"Jane\\\\nDoe\"'; print(p._structure_safe_runs(t, t, p._escape_intervals(t), 0, len(t)))"` prints `[(1, 5), (7, 10)]`.

### Task 5: JSON detection, token scanner, clipping

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**:
  - `_is_json_document(text) -> bool` (P7).
  - `_json_tokens(text)`: a single forward scan. On `"`, advance past `\` + one character pairs until the unescaped closing `"`. On `-` or a digit, match `_JSON_NUMBER` at that position, **except** `-Infinity`. On a letter, skip the `[A-Za-z]+` literal. Otherwise advance one character.
  - `_replacement_ranges(text, analysis, accepted, json_tokens) -> list[tuple[int, int, str, str]]` (P6, P7, P8):
    - when `json_tokens is None`, only the structure-safe runs are used;
    - otherwise each span is intersected with the tokens it overlaps, found with `bisect` over the token starts, and ranges that overlap a taken range are dropped.
- **Mirror**: n/a (PRD Section 8, "a small token scanner")
- **Validate**: `.venv/Scripts/python.exe -c "import app.services.pii_redactor as p; t='{\"a\": [1, -2.5e3, \"x\\\\\"y\", true, null]}'; print(p._json_tokens(t))"` gives one string token for the key `"a"`, two number tokens, and one string token `"x\"y"`.

### Task 6: Splice, entities, post-condition, docstring

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**:
  - Replace the Task 1 placeholder. After P2 and P3:
    1. `analysis = …` (P4);
    2. `accepted = _resolve_overlaps(_analyze(analysis, policy))`;
    3. if `accepted` is empty, return `RedactionResult(text, [])`;
    4. `tokens = _json_tokens(text) if _is_json_document(text) else None`;
    5. build the ranges;
    6. splice (`_splice`);
    7. `entities = sorted({...})` (P9);
    8. if `tokens is not None`, run the post-condition (P10);
    9. return.
  - Run JSON detection only after a span has been accepted, so a text with no PII never pays for `json.loads`.
  - The docstring, in the style of `pattern_detector.strip_fenced_blocks`, covers:
    - the pipeline in order (PRD 6.5/6.6);
    - that analysis happens on the blanked text and replacement on the original, because blanking preserves length;
    - the overlap rule (P5);
    - the structural set, including whole escape sequences and why (F-5);
    - JSON mode and its number-to-string cost (PRD user story 4);
    - that the entities are those actually replaced (P9);
    - that `PII_REDACTION_ENABLED` applies;
    - that `chat` delegates to `redact()`;
    - the chunking condition (R3) and its hard-cut caveat;
    - `Raises: PiiRedactorError` for analysis failures and the JSON post-condition;
    - the PRD 6.6 tool-call paragraph, verbatim (P11).
- **Mirror**: `app/services/pattern_detector.py:161-190` (docstring density), `pii_redactor.py:150-151` (error wrapping)
- **Validate**: `.venv/Scripts/python.exe -c "from app.services.pii_redactor import redact_for_policy as r; from app.services.pii_policy import get_pii_policy as g; print(r('{\"id\": 7, \"contact\": \"bob@x.io\", \"phone\": 4155550134}', g('code')))"` prints `{"id": 7, "contact": "<EMAIL_ADDRESS>", "phone": "<PHONE_NUMBER>"}` with `['EMAIL_ADDRESS', 'PHONE_NUMBER']`. PRD user story 4 is the reference. If the bare number scores under 0.40, note that in the report and keep the stub-based AC 3 test as the proof.

### Task 7: Test module scaffold

- **File**: `tests/test_pii_structure_safe.py`
- **Action**: CREATE
- **Implement**:
  - The module docstring says "PRD-012 STORY-008: …", names which AC each block proves, and says that corpus round-trip and latency are STORY-013's job.
  - `os.environ.setdefault` for `OPENROUTER_API_KEY` and `ADMIN_TOKEN`.
  - Imports:
    - `dataclasses`, `json`, `pytest`;
    - `from presidio_analyzer import RecognizerResult`;
    - `import app.services.pii_redactor as pii_redactor` and `from app.services.pii_redactor import PiiRedactorError, RedactionResult, redact, redact_for_policy`;
    - `from app.services.pii_policy import get_pii_policy`;
    - `from app.services.pattern_detector import strip_fenced_blocks`;
    - `from tests import test_pii_corpus_files as corpus_files`;
    - `from tests.test_pii_characterization import REDACT_CASES`;
    - `import scripts.measure_pii_latency as bench`.
  - The autouse fixture from F-8, verbatim, including resetting `_pattern_analyzer`.
  - Helpers:
    - `_code(**overrides)`: `dataclasses.replace(get_pii_policy("code"), entities=tuple(_CODE_ENTITIES), threshold=0.40, skip_fenced_blocks=True, structure_safe=True, **overrides)`, pinned so `.env` cannot move it.
    - `_StubAnalyzer(spans)`: `analyze(**kw)` returns `[RecognizerResult(t, s, e, 1.0) for t, s, e in spans]`.
    - `_stub(monkeypatch, *spans)`: patches `pii_redactor._get_analyzer` to `lambda entities=None: stub`.
    - `_span(text, needle, entity, occurrence=0)`: returns `(entity, start, end)` for `needle`.
  - Stub texts stay under 20,000 characters, so the stub sees a single window at offset 0. The docstring says so.
- **Mirror**: `tests/test_pii_pattern_analyzer.py:1-60`
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pii_structure_safe.py -q` collects and runs 0 tests without errors.

### Task 8: Tests, grouped by AC

- **File**: `tests/test_pii_structure_safe.py`
- **Action**: UPDATE
- **Implement**:

  **AC 1: fences** (real tokenizer-only analyzer)
  - `test_fenced_email_is_unchanged_and_prose_email_is_masked` is parametrized over the ```` ``` ```` and `~~~` fences. Text: `Send it to maria.lopez@corp.com.\n```py\nOWNER = "jane.doe@example.com"\n```\nThanks.` The fenced line is byte-identical, the prose email becomes `<EMAIL_ADDRESS>`, and `entities == ["EMAIL_ADDRESS"]`.
  - `test_inline_backtick_email_is_masked`: `` Ping `ops@example.org` today. `` becomes `` Ping `<EMAIL_ADDRESS>` today. `` (D2; the corpus uses the same case at `onboarding-runbook.md:18`).
  - `test_unterminated_fence_skips_to_the_end`: an email before the fence is masked; one after an unclosed ```` ```yaml ```` line is unchanged.
  - `test_fences_are_analyzed_when_skip_is_off`: with `_code(skip_fenced_blocks=False)` the fenced email **is** masked, and its quotes stay.
  - `test_fence_guard_never_touches_fenced_bytes`: a stub span covers prose plus fenced content. Every byte inside the fence is unchanged (P6c).
  - `test_code_corpus_fenced_regions_are_byte_identical` is parametrized over `corpus_files._CODE_FILES`. At every position where `strip_fenced_blocks(t)[i] != t[i]`, the output equals the input. The positions are recomputed on the output, which has the same fence layout because nothing inside a fence changed.

  **AC 2: structure-safe** (stub analyzer unless noted)
  - `test_span_including_its_quotes_keeps_both_quotes`: a span over `"jane@example.com"` with its quotes gives `"<EMAIL_ADDRESS>"`.
  - `test_span_across_a_line_break_is_split`: `Jane\nDoe` gives `<PERSON>\n<PERSON>`.
  - `test_span_across_a_backtick_is_split`, and `test_span_containing_a_backslash_keeps_it`, with a raw `C:\` case.
  - `test_escape_sequence_is_kept_whole`, parametrized over `\n`, `\"`, `\\`, `\u00e9` and `\x41` inside a Java-style string. The escape bytes are unchanged, and the neighbouring alphanumeric runs are replaced (F-5).
  - `test_obrien_masks_as_two_placeholders`: `Patrick O'Brien` with `_code(entities=(..., "PERSON"))` gives `<PERSON>'<PERSON>` (PRD Risk 4).
  - `test_run_without_alphanumerics_is_left_alone`: a span over `jane@example.com", "` keeps `", "` byte-identical.
  - `test_structural_characters_are_preserved_across_the_code_corpus` (real analyzer, no stub), parametrized over `_CODE_FILES`: for each of `"`, `'`, `` ` ``, `\`, `\n` and `\r`, the count before equals the count after. Each `.json` file still passes `json.loads`.

  **Overlap rule (P5)**
  - `test_overlapping_spans_longest_wins`
  - `test_overlapping_spans_equal_length_earliest_start_wins`
  - `test_identical_spans_resolve_by_entity_name`: a `PHONE_NUMBER` and a `US_SSN` over the same digits give `<PHONE_NUMBER>`.

  **AC 3: JSON-aware**
  - `test_pii_in_a_string_value_is_replaced_inside_the_quotes` and `test_pii_in_a_key_is_replaced_inside_the_quotes` (stub).
  - `test_number_token_becomes_a_quoted_placeholder`: `{"phone": 4155550134}` gives `{"phone": "<PHONE_NUMBER>"}`, and `json.loads` returns a `str`.
  - `test_partial_span_over_a_number_replaces_the_whole_token` (P7), with `-4155550134`.
  - `test_spans_over_punctuation_literals_or_whitespace_are_dropped`, parametrized over `: `, `true`, `null`, `NaN` and `\n  `: the text is unchanged and `entities == []` (P9).
  - `test_span_across_several_tokens_is_clipped_to_each` (key, colon, value).
  - `test_json_formatting_survives`: indentation and line count are unchanged on a pretty-printed document.
  - `test_prd_user_story_4` (real analyzer): the exact PRD Section 5 example.
  - `test_every_json_corpus_file_still_parses` (real analyzer), parametrized over `corpus_files._ALL_JSON`. It asserts `json.loads(result.text)` and a non-empty `entities`.
  - `test_number_token_cards_become_strings`: in `payment-webhook.json`, the literal `4111111111111111` is gone and `"<CREDIT_CARD>"` is present.
  - `test_directory_keys_are_masked` (`directory-index-by-email.json`).
  - `test_non_json_brace_text_uses_structure_safe_mode_only`: `{name: "Jane"}` style JS does not raise, and top-level `"123"` / `42` are not JSON mode (P7).
  - `test_leading_whitespace_json_is_detected`.

  **AC 4: post-condition**
  - `test_post_condition_raises_on_invalid_json` (P14): stub span plus patched `_json_tokens`. Uses `pytest.raises(PiiRedactorError, match=r"^redaction would produce invalid JSON$")`. `str(excinfo.value)` does not contain the input.
  - `test_analysis_failure_is_a_pii_redactor_error`: a stub whose `analyze` raises gives `"PII analysis failed"`.

  **AC 5: chat path**
  - `test_chat_policy_equals_redact`, parametrized over `REDACT_CASES` texts: `redact_for_policy(t, get_pii_policy("chat")) == redact(t)`, and both are `isinstance(..., tuple)`.
  - `test_chat_policy_delegates_to_redact`: a spy on `pii_redactor.redact` is called exactly once. The `_get_analyzer` spy records no call with an entity list.
  - `test_chat_policy_fields_match_what_redact_reads`: `chat.entities == tuple(settings.pii_entities_list)` and `chat.threshold == settings.PII_SCORE_THRESHOLD` (P3 guard).

  **Selection, switch, windows**
  - `test_default_code_policy_never_touches_the_full_analyzer`: set `_analyzer` to a `_Tripwire`, then redact a prose email under `_code()`. The call succeeds and the tripwire log is empty (PRD Section 11).
  - `test_analyzer_is_selected_by_policy_entities`: a spy on `_get_analyzer` receives `policy.entities`.
  - `test_master_switch_off_returns_text_unchanged` and `test_empty_text_returns_empty`.
  - `test_entities_are_sorted_and_only_those_replaced`.
  - `test_analysis_windows_match_the_benchmark_reference`: for every `_CODE_FILES` text repeated to more than 40,000 characters, `pii_redactor._analysis_windows(t) == bench._chunks(t, 20_000)`.
  - `test_pii_beyond_the_first_window_is_masked_at_the_right_offset`: 30,000 characters of prose lines, then an email. The output differs from the input only at that email.
- **Mirror**: `tests/test_pii_pattern_analyzer.py:223-256` (tripwire), `tests/test_pii_characterization.py:150-153` (parametrize over cases), `tests/test_measure_pii_latency.py:141-153` (window assertions)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pii_structure_safe.py -q`
- **Sanity check (mutation)**, then revert each change and confirm with `git diff --stat`:
  1. Remove the `_ESCAPE` intervals. The escape tests fail, and `test_every_json_corpus_file_still_parses` should too; if it does not, record it in the report as evidence that the corpus did not exercise F-5.
  2. Replace the number-token branch with plain string splitting. AC 3's number tests fail.
  3. Drop the `analysis[i] != text[i]` guard. The fence-guard test fails.

### Task 9: Regression sweep

- **Implement**: no code. Run the suites this story must not move:
  - `test_pii_redactor.py`, `test_pii_characterization.py`, `test_pii_redaction_integration.py`: `redact()` and `chat` are unchanged;
  - `test_pii_pattern_analyzer.py`, `test_pii_policy.py`: STORY-006/007;
  - `test_pattern_matching.py`, `test_pattern_corpus.py`, `test_pii_dedup_isolation.py`: `pattern_detector` is untouched and still free of PII words;
  - `test_pii_corpus_files.py`, `test_measure_pii_latency.py`;
  - then the full suite.
- **Validate**: see the Validation section.

---

## End-to-End Tests

- [ ] `python -c` smoke (Task 6 Validate). The PRD user story 4 JSON example gives the documented output and still parses.
- [ ] `python -c`: PRD user story 3's text, `"email the diff to maria.lopez@corp.com and call her on +1 415 555 0134"`, under `get_pii_policy("code")` gives `email the diff to <EMAIL_ADDRESS> and call her on <PHONE_NUMBER>`. STORY-003 R1 chose the 0.40 threshold so that this phone is masked.
- [ ] `python -c`: PRD user story 1's `UserFixtures.java` line inside a ```` ``` ```` fence comes back byte-identical under `code`.
- [ ] Every file in `tests/corpora/pii/json/` redacted under `code` passes `json.loads` (Task 8, corpus test).
- [ ] `redact()` behaviour is unchanged: `test_pii_characterization.py` passes with no assertion changed.
- [ ] Nothing on the request path changed: `test_query_outcomes_regression.py` and `test_chat_outcomes_regression.py` are green (STORY-009 does the wiring).

---

## Validation

```bash
# Precondition: the libSQL dev server the conftest requires
docker start harness-libsql-dev   # or the `docker run` line in README "Running Tests"

.venv/Scripts/python.exe -c "import app.main"                          # backend imports (server-start smoke)
.venv/Scripts/python.exe -m pytest tests/test_pii_structure_safe.py -q
.venv/Scripts/python.exe -m pytest tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_redaction_integration.py tests/test_pii_pattern_analyzer.py tests/test_pii_policy.py -q
.venv/Scripts/python.exe -m pytest tests/test_pattern_matching.py tests/test_pattern_corpus.py tests/test_pii_dedup_isolation.py tests/test_pii_corpus_files.py tests/test_measure_pii_latency.py -q
git diff --exit-code HEAD -- app/services/pattern_detector.py tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_redaction_integration.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py
.venv/Scripts/python.exe -m pytest -q                                   # full suite
```

The repo has no linter configured and no npm frontend, and this story changes no UI, so there is no frontend lint step. If there are mass fixture errors, restart the libSQL container rather than bisecting code (PRD Section 11).

---

## Handoff (for later stories)

- **STORY-009 (pipeline step 6)**:
  - `redact_for_policy(m.content, policy)` for each message whose role is in `policy.input_roles`. It returns a `RedactionResult`, which unpacks like `redact()`.
  - Under `chat` it **is** `redact()`, so calling `redact_for_policy` for every policy keeps the characterization suite green.
  - A `PiiRedactorError` from the JSON post-condition uses the existing redaction-error arm. The message carries no content.
- **STORY-010**: under `skip_fenced_blocks`, count analyzable characters from `strip_fenced_blocks(content)`. This module blanks the same way, so the two agree.
- **STORY-012 (D5 spike)**:
  - Masked PII keys in one JSON object collide to the same placeholder, and the last one wins on parse. This is an input for the indexed-placeholder option.
  - Number tokens become strings (PRD user story 4).
- **STORY-013**:
  - The round-trip suite (`ast.parse` over `.py`, fenced byte identity, prose masking) builds on this module's corpus tests. Do not duplicate them; extend them.
  - The latency budget must be measured through `redact_for_policy` itself, which is now chunked.

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given `redact_for_policy(text, code_policy)`, when `text` has an email inside a ```` ``` ```` or `~~~` fence and another in prose, then the fenced one is unchanged and the prose one becomes `<EMAIL_ADDRESS>`; an email inside an inline backtick span **is** masked; an unterminated fence skips to end of text.
- [ ] Given a structure-safe policy, when a span covers `"jane@example.com"` including its quotes, or contains a backslash, a backtick or a line break, then every quote, backslash, backtick and line break stays in place, the span is split around them, and runs without an alphanumeric character are left alone (`O'Brien` masks as `<PERSON>'<PERSON>` when `PERSON` is enabled).
- [ ] Given content that is a JSON object or array, when PII sits in a string value or key, then it is replaced inside the quotes; when PII is a number token (`"phone": 4155550134`), then the whole token becomes `"<PHONE_NUMBER>"`; spans over punctuation, `true`/`false`/`null` or whitespace are dropped; and `json.loads(result)` succeeds for every file in `tests/corpora/pii/json/`.
- [ ] Given a stub analyzer that returns a span which would make the result unparseable, when JSON-aware mode runs, then `PiiRedactorError("redaction would produce invalid JSON")` is raised.
- [ ] Given `redact_for_policy(text, chat_policy)`, when it runs, then the result is identical to `redact(text)`, and `redact()` itself is unchanged (characterization green).
- [ ] All tasks completed
- [ ] Backend imports and the FastAPI app starts without error
- [ ] Full test suite green; no assertion changed in the PRD Section 11 protected files
- [ ] Follows existing patterns (lazy analyzer selection, `PiiRedactorError` wrapping, F-8 test fixture, corpus loader reuse)
