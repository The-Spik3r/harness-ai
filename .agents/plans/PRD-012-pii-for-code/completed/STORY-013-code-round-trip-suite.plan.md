---
story: STORY-013
prd: PRD-012
slug: code-round-trip-suite
title: "Code round-trip suite and the latency-budget assertion"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: Code round-trip suite and the latency-budget assertion

## Summary

This story turns PRD-012's MVP definition (Section 11) into green tests. A new module, `tests/test_pii_code_corpus.py`, runs the three corpora through the real `code` and `chat` policies:

- **`code/` under `code`.** Fenced blocks stay byte-identical. Unfenced text keeps the count **and** positions of quotes, backslashes, backticks and line breaks, and changes only by placeholders. `.py` still passes `ast.parse`, `.json` still passes `json.loads`, and `.yaml` still loads.
- **`prose/` under `chat` and under `code`.** Declared entities are masked. The types `code` does not detect are listed by name.
- **`json/` under `code`.** Tool results still parse, and number-token PII becomes a quoted string.
- **`code/` under `chat`.** Every file changes, which proves the corpus is not vacuous.
- **Latency.** A `@pytest.mark.benchmark` test asserts that `code` p95 on the 200,000-character agent-shaped conversation is under STORY-003's 1,500 ms budget. The benchmark marker is skipped unless `--run-benchmark` is passed. `scripts/measure_pii_latency.py` gains a `code` arm that goes through `redact_for_policy`, so the script and the test measure the same thing.

**This story also fixes one production bug.** The pre-planning probe (see *Findings*) showed that AC 1's `ast.parse` fails today on `billing_seed.py`. The fix is small and changes only structure-safe replacement outside JSON mode. `chat` cannot be affected: it never reaches that code.

## User Story

As a security admin and an integrating developer
I want the MVP criteria asserted over the corpus and the benchmark
So that "code survives and prose is still masked, within budget" is a green test rather than a claim

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-013-code-round-trip-suite.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`, Sections 6.6, 7 (F11), 11 (MVP definition, Benchmark criteria, Refinement), 14 (Risks 1, 4, 5)
- Handoffs consumed:
  - **STORY-001 report.** Import `_CODE_FILES`, `_PROSE_FILES`, `_JSON_FILES`, `_ALL_JSON`, `_declared`, `_read`, `_walk` and `_ids` from `tests.test_pii_corpus_files`. Intersect the declared entities with the policy's entities.
  - **STORY-003 report.** The budget is **p95 < 1,500 ms at 200,000 characters**, measured on `_conversation(200000)`, not on a single message. Add a `code` arm beside the three existing arms rather than replacing them. `PII_SCORE_THRESHOLD_CODE = 0.40`.
  - **STORY-008 report.** Extend the corpus tests rather than duplicating them. Add a JSON corpus entry with a default-entity span right after an escape (finding M1). Measure through `redact_for_policy`, which is chunked.
  - **STORY-009 report.** `run_conversation(profile="code")` is the real path. This story tests `tool`-shaped content by calling `redact_for_policy` directly, because step 0 refuses `tool` turns.

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (a test suite, plus one structure-safe bug fix it uncovered) |
| Complexity | MEDIUM |
| Systems Affected | `app/services/pii_redactor.py` (structure-safe runs, non-JSON only), `scripts/measure_pii_latency.py`, `tests/` (new module, conftest marker, corpus file) |
| Story | STORY-013 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The story says "Skills: none applicable". `.agents/skills/` holds only `frontend-design`, and this story has no UI | — |

---

## Findings (measured before planning)

These were measured on `epic/PRD-012-pii-for-code` @ `8693933` with the real policies (`pii_policy.load()`, shipped defaults), using throwaway probe scripts in the session scratchpad. Nothing in the repo changed.

**F-1 · AC 1 fails today: `billing_seed.py` does not parse after `code` redaction.**

```
billing_seed.py:93   email='patrick.obrien@example.org',
  analyzer span (EMAIL_ADDRESS, 1.0): "email='patrick.obrien@example.org"
  result:            <EMAIL_ADDRESS>'<EMAIL_ADDRESS>',     -> SyntaxError at line 93
```

- **Cause.** Presidio's email regex allows `'`, `=` and `` ` `` in the local part, so the span starts at the keyword argument.
- **Why the existing guard misses it.** Structure-safe splitting (PRD 6.6 rule 1) keeps the quote, then masks **both** runs, `email=` and `patrick.obrien@example.org`, because each has an alphanumeric character. The quote count is unchanged, so STORY-008's `test_structural_characters_are_preserved_across_the_code_corpus` passes. The Python does not parse.
- **Where else it happens.** It occurs twice in `billing_seed.py` (lines 93 and 100, both `email='...'`). The other six code files parse, load or keep their skeleton.
- **What catches it.** The skeleton check alone would not catch it, because a placeholder may replace any non-empty run. Only the parse check and the new anchor invariant (Task 6) catch it.

**F-2 · Everything else in AC 1–3 and AC 5 already holds:**

| Check | Result |
|---|---|
| `code/` structural skeleton (split on `\ " ' `` ` `` \r \n`), every file | identical |
| `seed-users.json` `json.loads` / `staging-values.yaml` `yaml.safe_load` | ok / ok |
| `prose/` under `code`: `declared ∩ code.entities ⊆ found`, every file | ok |
| `prose/` under `chat` (lg, shipped settings): `declared ⊆ found`, every file | ok |
| Declared types across `prose/` minus `PII_ENTITIES_CODE` | exactly `{PERSON}` |
| `code/` under `chat`: text changes | 7/7 files |
| `{"m": "hi\njane.doe@example.com"}` (literal `\n`) under `code` | `"hi\n<EMAIL_ADDRESS>"`, parses |
| `{"m": "tel:\t+1 415 555 0134"}` | `"tel:\t<PHONE_NUMBER>"`, parses |

**F-3 · Latency.** `code` policy over `_conversation(200000)`: roles in `input_roles` only (no `system`), fences skipped, chunked. Five runs after a warm-up took 504–535 ms. That is about a third of the 1,500 ms budget.

---

## Patterns to Follow

### Test module header, env bootstrap, and imports of shared corpus helpers

```python
# SOURCE: tests/test_pii_structure_safe.py:1-39
"""PRD-012 STORY-008: redact_for_policy -- fence skipping, structure-safe
replacement, JSON-aware mode (PRD Sections 6.5, 6.6; F7).
...
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import json

import pytest
...
import scripts.measure_pii_latency as bench
from tests import test_pii_corpus_files as corpus_files
from tests.test_pii_characterization import REDACT_CASES
```

### Pinning settings per test (the characterization fixture: real lg, shipped values)

```python
# SOURCE: tests/test_pii_characterization.py:62-89
_SHIPPED_PII_SETTINGS = {
    "PII_REDACTION_ENABLED": True,
    "PII_SCORE_THRESHOLD": 0.35,
    "PII_ENTITIES": "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION",
    "PII_NLP_MODEL": "en_core_web_lg",
}
...
@pytest.fixture(autouse=True)
def _shipped_pii_settings(monkeypatch):
    for name, value in _SHIPPED_PII_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    cached = pii_redactor._analyzer
    if cached is not None and _model_name(cached) != _LARGE_MODEL_NAME:
        monkeypatch.setattr(pii_redactor, "_analyzer", None)
    assert _model_name(pii_redactor._get_analyzer()) == _LARGE_MODEL_NAME
    yield
```

Import `_SHIPPED_PII_SETTINGS`, `_LARGE_MODEL_NAME` and `_model_name`. Do not copy them. The module docstring allows importing from it (the `REDACT_CASES` precedent). The fixture is **not** autouse here, because only the `chat` cases need lg.

### Policies rebuilt from patched settings (the conftest restores `_policies`)

```python
# SOURCE: tests/conftest.py:214-225
@pytest.fixture(autouse=True)
def _default_pii_policy():
    """... A test that patches a `PII_*` setting calls `pii_policy.load()` itself to
    see it. `_policies` is saved and restored directly ..."""
```

### Corpus parametrization with readable ids

```python
# SOURCE: tests/test_pii_structure_safe.py:245-255
@pytest.mark.parametrize("path", corpus_files._CODE_FILES, ids=corpus_files._ids(corpus_files._CODE_FILES))
def test_structural_characters_are_preserved_across_the_code_corpus(path):
    text = corpus_files._read(path)

    result = redact_for_policy(text, _code()).text

    for character in ('"', "'", "`", _BACKSLASH, "\n", "\r"):
        assert result.count(character) == text.count(character), repr(character)
```

### Non-vacuity guard beside a corpus test

```python
# SOURCE: tests/test_pii_structure_safe.py:160-162
def test_the_code_corpus_has_fenced_content():
    """Guards the test above against passing vacuously."""
    assert any(strip_fenced_blocks(t) != t for t in map(corpus_files._read, corpus_files._CODE_FILES))
```

### Stub analyzer for single-rule tests (for the F-1 fix)

```python
# SOURCE: tests/test_pii_structure_safe.py:63-88
class _StubAnalyzer: ...
def _stub(monkeypatch, *spans): ...
def _span(text, needle, entity, occurrence=0): ...
def _stub_redact(monkeypatch, text, needle, entity="EMAIL_ADDRESS", policy=None): ...
```

### `#:` constant comments citing the PRD, and the rule being amended

```python
# SOURCE: app/services/pii_redactor.py:194-198
#: Never replaced (PRD-012 Section 6.6, rule 1): quotes, backticks and line
#: breaks. The backslash is covered by _ESCAPE, which keeps the whole escape
#: sequence. ...
_STRUCTURAL_CHARACTERS = frozenset("\"'`\r\n")
```

```python
# SOURCE: app/services/pii_redactor.py:386-389 (_replacement_ranges, the non-JSON path ends here)
        for start, end in pieces:
            for run_start, run_end in _structure_safe_runs(text, analysis, escapes, start, end):
                _take(taken, run_start, run_end, placeholder, result.entity_type)
    return taken
```

### Benchmark timing primitives (reuse, do not reimplement)

```python
# SOURCE: scripts/measure_pii_latency.py:558-608
class Samples:          # .add(ms), .summary() -> (min, p50, nearest-rank p95)
def _timed(work): ...   # (result, elapsed_ms)
def _redact_all(redact, messages): ...   # one redact() per message, every role
def _sample(label, runs, work) -> Samples: ...
```

### Error handling

No new error type. `redact_for_policy` already raises `PiiRedactorError` for analysis failure and the JSON post-condition (`app/services/pii_redactor.py:21`, `:408+`). The F-1 fix narrows which runs get masked and raises nothing. The script keeps its "records numbers, asserts none" contract. Only the pytest test asserts the budget.

---

## Design

### Files to CREATE

| File | Purpose |
|------|---------|
| `tests/test_pii_code_corpus.py` | The round-trip suite (AC 1, 2, 3, 5) and the budget assertion (AC 4) |
| `tests/corpora/pii/json/build-log-escapes.json` | The M1 entry: default-entity PII directly after `\n`, `\t` and `\"` escapes in JSON strings |

### Files to UPDATE

| File | Change |
|------|--------|
| `app/services/pii_redactor.py` | F-1 fix: outside JSON mode, a pattern-entity span that splits into several runs masks only the runs holding its anchor |
| `tests/test_pii_structure_safe.py` | **New tests only** for the F-1 rule. No existing assertion changes |
| `tests/conftest.py` | Register the `benchmark` marker, add `--run-benchmark`, and skip marked tests without the option |
| `scripts/measure_pii_latency.py` | `code` arm through `redact_for_policy`; `CODE_P95_BUDGET_MS`; report lines for the arm, the policy and the budget check |
| `tests/test_measure_pii_latency.py` | Pure tests for the new arm (role filtering, arm parsing, budget constant) |
| `tests/corpora/pii/SOURCES.md` | A section for `build-log-escapes.json` (required by `test_sources_names_every_sample`) |
| `.agents/PRDs/PRD-012-pii-for-code/PRD.md` | Section 6.6 rule 1: one sentence recording the anchor refinement and why (F-1) |

### Dependency order

1. F-1 fix and its unit tests (Tasks 1–2). AC 1 cannot pass without them.
2. M1 corpus file and `SOURCES.md` (Task 3). The corpus guards must stay green.
3. Conftest marker (Task 4).
4. Script `code` arm and its pure tests (Task 5). The benchmark test imports the helper.
5. `tests/test_pii_code_corpus.py` (Tasks 6–9).
6. PRD sentence, regression sweep, benchmark runs (Tasks 10–12).

### Decisions made here

- **D-a · Fix F-1 in production rather than weaken AC 1.** The AC names `ast.parse`. The PRD's promise is that `code` never breaks code. A placeholder replacing `email=` is exactly the corruption PRD-012 exists to remove.
- **D-b · The rule ("anchored runs").** It applies outside JSON mode, when a span's structure-safe runs number **more than one**, and when the span's entity type has an anchor:
  - The anchors are `EMAIL_ADDRESS` → a run containing `@`, and `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `IBAN_CODE` → a run containing a digit.
  - When the rule applies, only the anchored runs are masked. If **no** run holds the anchor, every run is masked as before (fail toward masking).
  - Types without an anchor (`PERSON`, `LOCATION`, anything else an operator adds) keep today's every-alphanumeric-run behaviour. That preserves PRD Risk 4's `<PERSON>'<PERSON>` and `test_obrien_masks_as_two_placeholders`.
  - **JSON mode is unchanged.** Clipping to string interiors already confines runs there, and `test_span_across_several_tokens_is_clipped_to_each` pins key masking.
  - A single-run span is unchanged, which keeps the overlap tests (`"abcdefgh"` as `PHONE_NUMBER`) green.
- **D-c · Where the suite lives.** The AC names `tests/test_pii_code_corpus.py`, so the round-trip suite goes there. STORY-008's corpus tests in `test_pii_structure_safe.py` stay as they are, because they pin STORY-008's ACs.
  - The new module is **stronger**, not a copy: it checks per-block fenced identity, skeleton positions, placeholder-only diffs, anchors, parses, prose and chat non-vacuity.
  - The structure tests (the F-1 unit tests) go in `test_pii_structure_safe.py`, which follows STORY-008's "extend, don't duplicate".
- **D-d · "Positions" is defined as the structural skeleton.** `re.split(r'(\\|["\'`\r\n])', text)` gives alternating segments and separators. The original and the result must have the same number of segments and identical separators, in order. Masking a run changes columns, so absolute offsets cannot be the meaning. Line numbers and in-line order of every structural character are what code syntax depends on, and the skeleton fixes both.
- **D-e · Placeholder-only diffs.** Every changed segment must fullmatch a regex built from the result segment, in which each `<TYPE>` becomes a lazy capture of non-empty text. Each capture must then hold its type's anchor (the same anchor table, imported from `pii_redactor`). This is the invariant that catches F-1 without depending on a parser.
- **D-f · The benchmark guard is a CLI option, not only a marker.** An unregistered or unselected marker does not skip anything. `tests/conftest.py` registers `benchmark`, adds `--run-benchmark`, and skips marked items without it. Explicit run: `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s`.
- **D-g · The budget constant lives in the script.** `CODE_P95_BUDGET_MS = 1_500`, with a `#:` comment citing the STORY-003 report, R2. The test imports it, and the script prints its own `code` p95 against it. That keeps one number in one place. The script still asserts nothing.
- **D-h · The M1 entry is a new file, not an edit.** Editing `ticket-thread-export.json` would move STORY-008's pinned corpus expectations. A new `json/` file is discovered automatically (`_corpus("json")`). It also joins the benchmark's tool-shaped rotation (12 files instead of 11), which slightly changes the 200k conversation. That is acceptable, because this story re-measures anyway. The report states it.

### Risks

| Risk | Mitigation |
|---|---|
| The F-1 fix changes a pinned STORY-008 expectation | The rule is scoped (D-b) to non-JSON, multi-run, anchored types. Task 2 runs `tests/test_pii_structure_safe.py` unmodified. If any existing assertion fails, stop and raise it. Do not edit it |
| `chat` drifts | `chat` never enters `_replacement_ranges`: `redact_for_policy` delegates to `redact()` when `structure_safe` is false. The four protected files plus `test_pii_characterization.py` run unmodified, and `git diff --exit-code` guards them |
| The latency test is flaky on a loaded machine | The budget is 2× STORY-003's measured p95, and the measured `code` path is about 0.5 s (F-3). It runs only with `--run-benchmark`. The assertion message prints all of min, p50 and p95 |
| The new JSON file shifts STORY-003 / STORY-008 corpus tests | They discover files, not counts. Task 3 runs `test_pii_corpus_files.py`, `test_pii_structure_safe.py` and `test_measure_pii_latency.py` right after adding it |
| `--run-benchmark` is unrecognized when `pytest` runs from the repo root | pytest loads `tests/conftest.py` early (it is a `test*` directory under the invocation root). Task 4 validates both `pytest --run-benchmark -q -k nothing` and `pytest tests/... --run-benchmark` |
| The anchor for a digitless IBAN-like or a letters-only phone | Every one of the four recognizers requires digits by construction (regex plus checksum). If no run is anchored, all runs are masked, so the rule can only mask less where an anchored run exists |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pii_redactor.py` | UPDATE | F-1: anchored-run rule for split pattern-entity spans outside JSON mode |
| `tests/test_pii_structure_safe.py` | UPDATE | New unit tests for the anchored-run rule (no assertion changed) |
| `tests/corpora/pii/json/build-log-escapes.json` | CREATE | M1: PII right after `\n` / `\t` / `\"` escapes |
| `tests/corpora/pii/SOURCES.md` | UPDATE | Describe the new sample |
| `tests/conftest.py` | UPDATE | `benchmark` marker and `--run-benchmark` |
| `scripts/measure_pii_latency.py` | UPDATE | `code` arm, `CODE_P95_BUDGET_MS`, report lines |
| `tests/test_measure_pii_latency.py` | UPDATE | Pure tests for the arm |
| `tests/test_pii_code_corpus.py` | CREATE | The round-trip suite and the budget test |
| `.agents/PRDs/PRD-012-pii-for-code/PRD.md` | UPDATE | Section 6.6 rule 1: the anchored-run sentence |

---

## Tasks

Execute in order. Each task is atomic and verifiable. Prefix commands with `.venv/Scripts/python.exe -m`, and start the libSQL dev container first (see *Validation*).

### Task 1: Anchored-run rule in structure-safe replacement (F-1)

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**:
  1. Next to `_STRUCTURAL_CHARACTERS`, add `#:`-commented `_RUN_ANCHORS: dict[str, Callable[[str], bool]]`:
     - `EMAIL_ADDRESS` → `"@" in run`;
     - `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `IBAN_CODE` → `any(c.isdigit() for c in run)`.
     - The comment cites PRD-012 Section 6.6 rule 1 and STORY-013 F-1, and quotes the `email='patrick.obrien@example.org'` case: Presidio's email local part admits `'` and `=`.
  2. Add `_anchored(text, runs, entity_type)`:
     - If `entity_type` has no anchor or `len(runs) <= 1`, return `runs`.
     - Otherwise return the runs whose text satisfies the anchor, or `runs` if none does.
  3. In `_replacement_ranges`, apply it **only when `json_tokens is None`**: `for run_start, run_end in _anchored(text, runs, result.entity_type)`. The JSON branch is untouched.
  4. Extend the `_structure_safe_runs` / `_replacement_ranges` docstring by one sentence, and add a line to `redact_for_policy`'s docstring rule list.
- **Mirror**: `app/services/pii_redactor.py:194-205` (constants with `#:`), `:354-389` (`_replacement_ranges`)
- **Validate**: `pytest tests/test_pii_structure_safe.py -q` passes **unmodified**. Then run `ast.parse(redact_for_policy(billing_seed, code).text)` in a one-off REPL: it no longer raises, and line 93 reads `email='<EMAIL_ADDRESS>',`.

### Task 2: Unit tests for the rule

- **File**: `tests/test_pii_structure_safe.py`
- **Action**: UPDATE (append a section `# --- STORY-013 F-1: anchored runs ---`; no existing test touched)
- **Implement**:
  - `test_split_email_span_masks_only_the_run_with_the_at_sign`: **real** analyzer, `"        email='jane.doe@example.com',\n"` → `email='<EMAIL_ADDRESS>',`.
  - `test_split_phone_span_masks_only_runs_with_digits` (stub): `PHONE_NUMBER` over `mobile='(415) 555-0172` → `mobile='<PHONE_NUMBER>`.
  - `test_split_span_with_digits_on_both_sides_masks_both` (stub): `PHONE_NUMBER` over `415\n555-0172` → `<PHONE_NUMBER>\n<PHONE_NUMBER>`.
  - `test_split_span_with_no_anchored_run_masks_every_run` (stub): `EMAIL_ADDRESS` over `ab'cd` → `<EMAIL_ADDRESS>'<EMAIL_ADDRESS>`.
  - `test_split_span_of_an_unanchored_type_masks_every_run` (stub): `URL` over `ab'cd`.
  - `test_json_mode_ignores_run_anchors` (stub): `{"a'b": 1}`-shaped, so key clipping is unchanged.
  - `test_billing_seed_parses_after_code_redaction`: the regression pin for F-1, with `ast.parse`.
  - Each docstring cites PRD-012 STORY-013 F-1.
- **Mirror**: `tests/test_pii_structure_safe.py:168-243` (stub split tests), `:222-228` (O'Brien)
- **Validate**: `pytest tests/test_pii_structure_safe.py -q`. **Guard-bite:** temporarily make `_anchored` return `runs`. The email, phone and billing tests fail. Revert.

### Task 3: M1 corpus entry

- **Files**: `tests/corpora/pii/json/build-log-escapes.json` (CREATE), `tests/corpora/pii/SOURCES.md` (UPDATE)
- **Implement**:
  - Create a CI or build tool-result document, pretty-printed, about 40–80 lines. Its string values carry default-entity PII **directly after** escapes:
    - `"notify:\njane.doe@example.com"`;
    - `"on-call:\t+1 415 555 0134"`;
    - `"reply-to \"maria.lopez@example.org\""`;
    - an IBAN after `\n`, `"payout:\nGB82 WEST 1234 5698 7654 32"`;
    - one `\\`-escaped Windows path next to an email.
  - Use only the `_CAST` names and the reserved `example.com` / `example.org` domains (`test_every_email_in_the_corpus_is_on_a_reserved_domain`).
  - Add a `### build-log-escapes.json` section under `## json/` in `SOURCES.md`, with a *Why it is here* line that cites STORY-008 finding M1.
- **Mirror**: `tests/corpora/pii/json/ticket-thread-export.json` and its `SOURCES.md` section (`SOURCES.md:232+`)
- **Validate**:
  - `pytest tests/test_pii_corpus_files.py tests/test_pii_structure_safe.py tests/test_measure_pii_latency.py -q`.
  - **Guard-bite (M1 closed):** temporarily make `_escape_intervals` return `[]`. `test_every_json_corpus_file_still_parses[build-log-escapes.json]` now **fails**, where STORY-008 recorded that no corpus file failed. Revert.

### Task 4: `benchmark` marker and `--run-benchmark`

- **File**: `tests/conftest.py`
- **Action**: UPDATE (top-level hooks, after the imports)
- **Implement**:
  - `pytest_addoption(parser)` adds `--run-benchmark`: `store_true`, with help text "run @pytest.mark.benchmark latency assertions (PRD-012 STORY-013)".
  - `pytest_configure(config)` calls `config.addinivalue_line("markers", "benchmark: latency-budget assertion; skipped unless --run-benchmark")`.
  - `pytest_collection_modifyitems(config, items)`: without the option, add `pytest.mark.skip(reason="benchmark: pass --run-benchmark")` to every item with the `benchmark` keyword.
  - Add a docstring citing the story's technical note: "so the everyday run stays fast".
- **Validate**:
  - Run `pytest --markers | grep benchmark`.
  - Run `pytest --run-benchmark -q -k no_such_test` from the repo root. The option is recognized.

### Task 5: `code` arm in the benchmark script

- **Files**: `scripts/measure_pii_latency.py`, `tests/test_measure_pii_latency.py`
- **Implement** (script):
  - Import `pii_policy` and `get_pii_policy` next to `pii_redactor`.
  - Add `#: STORY-003 report, rule R2 ... asserted by tests/test_pii_code_corpus.py (STORY-013)` and `CODE_P95_BUDGET_MS = 1_500`.
  - Add `"code"` to `_ARMS`.
  - Add `_redact_policy_roles(policy, messages)`: step 6 as `run_conversation` does it. It calls `pii_redactor.redact_for_policy(m.content, policy)` for each `m` whose `m.role` is in `policy.input_roles`, calling through the module attribute so a spy works.
  - In `_measure_command`:
    - call `pii_policy.load()` after `pii_redactor.load()`, then `code_policy = get_pii_policy("code")`;
    - build a per-arm work function, `_redact_policy_roles(code_policy, conv)` for `code` and `_redact_all(redactors[arm], conv)` otherwise, and use it for warm-up and timing;
    - accept `code` in `arms`.
  - Leave `code_arm` and rules R1–R4 on STORY-003's `pattern-*` arms (their record), and leave throughput unchanged.
  - In `_report`:
    - add a header line for the `code` policy's fields (entities, threshold, input_roles, skip_fenced_blocks);
    - after the decision inputs, add `Budget check (STORY-013): code p95 at 200000 = X ms vs CODE_P95_BUDGET_MS ms (within | OVER)`, or `n/a` when not timed;
    - keep "No latency here is asserted as a pass/fail bound.";
    - update the module docstring's arm list.
- **Implement** (tests; pure, no timing, no lg):
  - `test_arms_accept_code`: `bench._arms("code,chat") == ["code", "chat"]`.
  - `test_code_arm_redacts_only_the_policy_roles`: spy on `pii_redactor.redact_for_policy` over `bench._conversation(40_000)`. The call count equals the non-`system` messages, and the system prompt is never passed.
  - `test_code_budget_is_story_003s`: `bench.CODE_P95_BUDGET_MS == 1_500`.
- **Mirror**: `scripts/measure_pii_latency.py:596-608` (`_redact_all`, `_sample`), `:1206-1211` (`_arms`); `tests/test_measure_pii_latency.py:141-170`
- **Validate**:
  - `pytest tests/test_measure_pii_latency.py -q`.
  - `python scripts/measure_pii_latency.py --show-corpus --sizes 200000` still prints the shape.

### Task 6: `tests/test_pii_code_corpus.py`: scaffold and AC 1 (code round-trip)

- **File**: `tests/test_pii_code_corpus.py`
- **Action**: CREATE
- **Implement**:
  - **Docstring.** PRD-012 STORY-013, F11, Section 11 MVP. It explains:
    - D-d, what "positions" means;
    - that `chat` cases load `en_core_web_lg` with the shipped settings;
    - that the budget test is `@pytest.mark.benchmark`.
  - **Env bootstrap and imports** as in `test_pii_structure_safe.py:17-36`. Also import `ast`, `re`, `yaml`, `bench`, `corpus_files`, `pii_policy`, `redact_for_policy`, `strip_fenced_blocks`, `_RUN_ANCHORS`, and `_SHIPPED_PII_SETTINGS` / `_LARGE_MODEL_NAME` / `_model_name` from `tests.test_pii_characterization`.
  - **Autouse `_shipped_code_settings(monkeypatch)`.**
    - Pin `PII_REDACTION_ENABLED=True`, `PII_ENTITIES_CODE=EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE`, `PII_SCORE_THRESHOLD_CODE=0.40`, `PII_CODE_SKIP_CODE_BLOCKS=True`, `PII_CODE_REDACT_SYSTEM=False`, `PII_CODE_REDACT_OUTPUT=False` and `PII_MAX_CHARACTERS_CODE=200000`.
    - Then call `pii_policy.load()`. The **real** built policy is used, not a `dataclasses.replace`.
  - **Non-autouse `_shipped_chat(monkeypatch)`.** It mirrors the characterization fixture, then `pii_policy.load()`, and returns `get_pii_policy("chat")`.
  - **Helpers:**
    - `_code()` → `get_pii_policy("code")`;
    - `_STRUCTURE = re.compile(r'(\\|["\'`\r\n])')`;
    - `_PLACEHOLDER = re.compile(r"<([A-Z_]+)>")`;
    - `_fenced_blocks(text)`: `(start, end)` groups of positions where `strip_fenced_blocks(text)[i] != text[i]`, merged across gaps that are only `\n`;
    - `_masked_runs(original_segment, result_segment)`: a regex from the result segment with each placeholder turned into `(.+?)`, fullmatched against the original. It returns `[(entity, original_text)]`, or `None` when there is no match.
  - **AC 1 tests**, parametrized over `corpus_files._CODE_FILES` with `_ids`:
    - `test_every_fenced_block_is_byte_identical`: the lists `[text[s:e] for s, e in _fenced_blocks(text)]` and the same for the result are equal.
    - `test_the_code_corpus_has_several_fenced_blocks`: the guard. At least 2 blocks across the corpus, including one `~~~`.
    - `test_structural_characters_keep_their_count_and_positions`: the same segment count and identical separators (`split[1::2]`).
    - `test_only_placeholders_change_between_structural_characters`: every differing even segment has `_masked_runs(...) is not None`.
    - `test_every_masked_run_holds_its_entity_anchor`: every `(entity, run)` whose entity is in `_RUN_ANCHORS` satisfies its anchor. This is the parser-independent F-1 pin.
    - `test_every_code_sample_is_masked_under_code`: `result.entities` is non-empty for every file, so the checks above are not vacuous.
    - `test_every_python_sample_still_parses` (`ast.parse`, over `.py` files) and `test_every_json_code_sample_still_parses` (`json.loads`, over `.json` files in `code/`). Each has a guard that at least one such file exists.
    - `test_every_yaml_sample_still_loads` (`yaml.safe_load`). This goes beyond the AC. PyYAML is already in `requirements.txt`.
- **Mirror**: `tests/test_pii_structure_safe.py:146-162, 245-255`; `tests/test_pii_corpus_files.py:286-293`
- **Validate**:
  - `pytest tests/test_pii_code_corpus.py -q -k "not benchmark"`.
  - **Guard-bite:** with Task 1's `_anchored` temporarily returning `runs`, the `billing_seed.py` cases of the parse and anchor tests fail. Revert.

### Task 7: AC 2 (prose under both profiles) and AC 5 (non-vacuous corpus)

- **File**: `tests/test_pii_code_corpus.py`
- **Implement**:
  - **`_ABSENT_UNDER_CODE = frozenset({"PERSON"})`.** Add a `#:` comment: D7, NER types not in `PII_ENTITIES_CODE`; a name in prose under `code` is not masked (PRD 6.4).
  - **`test_the_types_code_does_not_mask_are_enumerated`.** It asserts that the union of `_declared` across `_PROSE_FILES`, minus `set(_code().entities)`, equals `_ABSENT_UNDER_CODE`. A corpus or setting change must update the list on purpose.
  - **`test_prose_declared_entities_are_masked_under_code`**, over `_PROSE_FILES`.
    - The body is the file without its header, as in `bench._prose_body`.
    - The expected set is `set(declared) - _ABSENT_UNDER_CODE`, which is ⊆ `result.entities`. Each `<TYPE>` must appear in `result.text`.
  - **`test_prose_declared_entities_are_masked_under_chat`**, over `_PROSE_FILES`, with `_shipped_chat`.
    - Every declared type is ⊆ `result.entities`, and each `<TYPE>` must appear in the text.
  - **`test_chat_changes_every_code_sample`**, over `_CODE_FILES`, with `_shipped_chat`.
    - `result.text != text`, and `_PLACEHOLDER.findall(result.text)` holds something not present in `text`: a masked identifier or literal.
    - The docstring cites PRD-011 Risk 5 / STORY-011's "not vacuous" precedent.
- **Validate**: `pytest tests/test_pii_code_corpus.py -q -k "prose or chat or enumerated"`. The first `chat` test pays the lg load once.

### Task 8: AC 3 (JSON tool results under `code`)

- **File**: `tests/test_pii_code_corpus.py`
- **Implement**:
  - **`test_code_redacts_tool_turns`.** It asserts `"tool" in _code().input_roles`. The docstring says step 0 still refuses `tool` turns, so `tool`-shaped content is tested by direct call (story technical note, PRD 6.3).
  - **`test_every_json_tool_result_parses_after_redaction`**, over `corpus_files._JSON_FILES`. `json.loads(redact_for_policy(text, _code()).text)` succeeds, and `result.entities` is non-empty.
  - **`test_number_token_pii_is_quoted`**, over `_JSON_FILES`.
    - Collect the original number values of 9 or more digits with `corpus_files._walk`.
    - After redaction, no such number remains. The redacted document holds a `"<CREDIT_CARD>"` / `"<PHONE_NUMBER>"` string value for each.
    - Add a corpus-level guard that at least one file has number-token PII.
  - **`test_escape_adjacent_pii_is_masked_and_the_escape_kept`** on `build-log-escapes.json`.
    - The result contains `\n<EMAIL_ADDRESS>`, `\t<PHONE_NUMBER>`, `\"<EMAIL_ADDRESS>\"` and `\n<IBAN_CODE>`.
    - `"jane.doe@example.com"` is absent, and the result parses.
- **Mirror**: `tests/test_pii_structure_safe.py:367-392`
- **Validate**: `pytest tests/test_pii_code_corpus.py -q -k json`

### Task 9: AC 4 (latency budget, `@pytest.mark.benchmark`)

- **File**: `tests/test_pii_code_corpus.py`
- **Implement**:
  - Add `_BENCHMARK_SIZE = 200_000` and `_BENCHMARK_RUNS = 20` (STORY-003's n).
  - Add `@pytest.mark.benchmark def test_code_p95_at_200k_is_within_the_story_003_budget(capsys)`:
    1. `conversation = bench._conversation(_BENCHMARK_SIZE)`, and `assert sum(len(m.content) for m in conversation) == _BENCHMARK_SIZE`.
    2. Run one discarded warm-up with `bench._redact_policy_roles(_code(), conversation)`.
    3. Take `samples = bench._sample("code", _BENCHMARK_RUNS, lambda: bench._redact_policy_roles(policy, conversation))`, then `minimum, p50, p95 = samples.summary()`.
    4. Inside `with capsys.disabled():`, print one line, `STORY-013 code p95 at 200000 chars: {p95:.2f} ms (min {minimum:.2f}, p50 {p50:.2f}, n=20; budget {bench.CODE_P95_BUDGET_MS} ms)`. The report quotes it.
    5. `assert p95 < bench.CODE_P95_BUDGET_MS`, with the same line as the message.
- **Validate**:
  - `pytest tests/test_pii_code_corpus.py -q` **skips** it (1 skipped).
  - `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s -q` passes and prints the line.

### Task 10: PRD Section 6.6 rule 1

- **File**: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`
- **Implement**:
  - After "Each run with at least one alphanumeric character is replaced by the placeholder.", add one sentence:
    > Outside JSON mode, when a pattern entity's span splits into several runs, only the runs holding its anchor (`@` for an email, a digit for the others) are replaced, and all of them if none does; Presidio's email local part admits `'` and `=`, so `email='jane@example.com'` would otherwise lose its keyword (STORY-013).
  - Bump `updated:` only if it is not already 2026-09-25.
- **Validate**: `git diff .agents/PRDs/PRD-012-pii-for-code/PRD.md` shows one sentence.

### Task 11: Regression sweep

- **Validate** (all must pass; protected files unchanged):
  - `git diff --exit-code HEAD -- tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_redaction_integration.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py app/services/pattern_detector.py`
  - `git diff HEAD -- tests/test_pii_structure_safe.py | grep '^-[^-]'` prints nothing, so the change is additions only.
  - `pytest tests/test_pii_structure_safe.py tests/test_pii_policy.py tests/test_pii_pattern_analyzer.py tests/test_query_pipeline_pii_profiles.py tests/test_spike_pii_placeholders.py -q`
  - `pytest -q`: the full suite; the benchmark is skipped.

### Task 12: Benchmark runs for the report

- **Run**:
  1. `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s -q`. Record the printed line (AC 4).
  2. `python scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs 20 --arms code,pattern-blank --concurrency 1 > <scratchpad>/story013-bench.txt`. This gives the `code` arm beside STORY-003's `pattern-blank` at all three sizes, plus the budget-check line. Skip `chat` and `pattern-lg`: STORY-003 recorded them, and they take about 10 s per run.
- **Report must state**:
  - the `code` p95 at 200k from the pytest test;
  - the script's table;
  - that the conversation now rotates 12 tool-shaped files (D-h);
  - F-1 and its fix;
  - the M1 guard-bite result.

---

## End-to-End Tests

For `/implement` to execute. This story has no HTTP or UI surface. The pipeline path is already covered by STORY-009's `test_query_pipeline_pii_profiles.py`, re-run in Task 11.

- [ ] `pytest tests/test_pii_code_corpus.py -q`: everything passes and exactly 1 test is skipped (the benchmark)
- [ ] `pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s -q`: 1 passed, and the p95 line is printed and under 1,500 ms
- [ ] `python -c` one-off: `ast.parse(redact_for_policy(<billing_seed.py>, get_pii_policy("code")).text)` succeeds
- [ ] Guard-bites (Tasks 2, 3, 6) each observed failing under the temporary mutation and passing after the revert, with the mutation reverted (`git diff app/` shows only Task 1)
- [ ] `python scripts/measure_pii_latency.py --sizes 200000 --runs 5 --arms code --concurrency 1` completes and prints the `code` row and the budget-check line

---

## Validation

```bash
# Precondition: the libSQL dev server the conftest requires
docker start harness-libsql-dev   # or the `docker run` line in README "Running Tests"

.venv/Scripts/python.exe -c "import app.main"                          # backend imports (server-start smoke)
.venv/Scripts/python.exe -m pytest tests/test_pii_code_corpus.py -q
.venv/Scripts/python.exe -m pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s -q
.venv/Scripts/python.exe -m pytest tests/test_pii_structure_safe.py tests/test_pii_corpus_files.py tests/test_measure_pii_latency.py -q
.venv/Scripts/python.exe -m pytest tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_redaction_integration.py tests/test_pii_pattern_analyzer.py tests/test_pii_policy.py tests/test_query_pipeline_pii_profiles.py -q
git diff --exit-code HEAD -- tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_redaction_integration.py tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py app/services/pattern_detector.py
.venv/Scripts/python.exe -m pytest -q                                   # full suite (benchmark skipped)
```

The repo has no linter configured and no npm frontend, and this story changes no UI, so there is no frontend lint step. If there are mass fixture errors, restart the libSQL container rather than bisecting code (PRD Section 11).

---

## Handoff (for later stories)

- **STORY-014 (chat regression sweep, README):**
  - Quote the `code` p95 at 200k from this story's report beside STORY-003's `chat` 10.7 s p95.
  - The README should say:
    - under `code`, names and places in prose are not masked (`_ABSENT_UNDER_CODE`);
    - PII inside fenced blocks reaches the provider (Risk 1);
    - a split email or phone span masks only its anchored part (F-1).
  - Run the benchmark explicitly with `--run-benchmark` as part of the sweep. The everyday suite skips it.
- **PRD-016 (tool turns):** `tool`-shaped content is covered by direct calls here. Once step 0 admits `tool`, add a `run_conversation` case over one `json/` file.

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given `tests/test_pii_code_corpus.py`, when it runs, then under `code` every fenced sample in `tests/corpora/pii/code/` is byte-identical after redaction, and every unfenced sample keeps its count and positions of quotes, backslashes, backticks and line breaks, with every `.py` still passing `ast.parse` and every `.json` still passing `json.loads`.
- [ ] Given `tests/corpora/pii/prose/`, when each file is redacted under both `chat` and `code`, then its declared entities are masked, except entity types absent from `PII_ENTITIES_CODE` under `code`, which the test enumerates explicitly.
- [ ] Given `tests/corpora/pii/json/`, when each file is redacted under `code`, then it parses, and number-token PII is quoted.
- [ ] Given the benchmark rerun at 200,000 characters under `code`, when p95 is measured, then it is under the budget the STORY-003 report fixed, and the number is recorded in this story's report.
- [ ] Given at least one code-corpus file, when it goes through today's `chat` policy, then it is asserted to change (a masked identifier or literal). That proves the corpus is not vacuous.
- [ ] All tasks completed
- [ ] Backend imports without error (`python -c "import app.main"`)
- [ ] No assertion changed in the protected files; `tests/test_pii_structure_safe.py` changed by additions only
- [ ] Follows existing patterns
