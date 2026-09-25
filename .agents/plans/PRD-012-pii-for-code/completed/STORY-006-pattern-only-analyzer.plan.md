---
story: STORY-006
prd: PRD-012
slug: pattern-only-analyzer
title: "Pattern-only analyzer, selected by the entity list"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-25
---

# Plan: Pattern-only analyzer, selected by the entity list

## Summary

`app/services/pii_redactor.py` gains a second Presidio `AnalyzerEngine`. Its NLP engine is a `SpacyNlpEngine` subclass over `spacy.blank("en")`, with a single pipeline component, `pii_lower_as_lemma`, that copies each token's lower-cased text into `token.lemma_`. This is STORY-003's `subclass+lemma` route, the only feasible one: 4 parity differences with lg, all of which mask more, never less.

A new module constant, `_NER_ENTITY_TYPES`, lists the five types Presidio's `SpacyRecognizer` serves. Each member has a comment saying why it is there. `_get_analyzer(entities=None)` selects an analyzer:
- no argument returns today's full analyzer, which keeps every no-argument caller working;
- a list containing any NER type returns the same full analyzer;
- a list with no NER type returns the tokenizer-only one.

Both analyzers are lazy module singletons with their own builders, so the existing `_build_analyzer` counting tests keep counting 1. `load()` prebuilds the full analyzer as today, then the one `PII_ENTITIES_CODE` selects. A failure to build the tokenizer-only analyzer raises `PiiRedactorError` out of `load()` and stops the boot. Nothing falls back to the full analyzer.

`redact()` keeps calling `_get_analyzer()` with no argument, so `chat` does not move by a byte, even when an operator's `PII_ENTITIES` happens to contain no NER type. Nothing on the request path calls the new analyzer yet; STORY-008's `redact_for_policy` is its consumer.

## User Story

As an integrating developer
I want the `code` profile to run Presidio's pattern recognizers without spaCy's NER model
So that identifiers are not tagged as people and redaction at agent sizes costs milliseconds, not seconds

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-006-pattern-only-analyzer.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md` (Sections 6.4 D7, 7 F6, 8, 14 Risk 2)
- Feasibility source: `.agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md` ("Feasibility of a tokenizer-only analyzer"; "For later stories → STORY-006")
- Handoff source: `.agents/reports/PRD-012-pii-for-code/STORY-005-pii-code-settings.report.md` ("For later stories → STORY-006": `NRP`, `ORGANIZATION`, `DATE_TIME`)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/pii_redactor.py`, `app/config.py` (one comment), `tests/test_pii_pattern_analyzer.py` (new), `tests/test_main.py` (appended block) |
| Story | STORY-006 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch) |
| Depends on | STORY-003 ✅ done (`ddf6596`), STORY-005 ✅ done (`ae97fc8`) |
| Blocks | STORY-008 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The story says "Skills: none applicable" and its `skills` field is `[]`. `.agents/skills/` holds only `frontend-design`, which covers visual UI design. This story changes no UI. | — |

---

## Findings (measured before planning)

- **F-1: Two callers use `_get_analyzer()` with no argument, and neither may change.**
  - `tests/test_pii_characterization.py:86` asserts `_model_name(pii_redactor._get_analyzer()) == "core_web_lg"` in an autouse fixture. AC 5 forbids changing that file.
  - `scripts/measure_pii_latency.py:343` and `:1057` also call it with no argument.
  - So the new parameter must be optional, and `None` must mean "the full analyzer, as today".
- **F-2: Three tests count `_build_analyzer` calls, and each expects exactly one.**
  - `tests/test_pii_redactor.py:38-51` (`test_analyzer_engine_constructed_only_once`) and `:71-83` wrap `pii_redactor._build_analyzer` as a **zero-argument** callable.
  - `tests/test_main.py:57-70` (`test_lifespan_does_not_reload_analyzer_on_first_request`) asserts `len(build_calls) == 1` across the lifespan, which will now build **both** analyzers.
  - So the tokenizer-only analyzer needs its **own** builder (`_build_pattern_analyzer`) and its own global (`_pattern_analyzer`). `_build_analyzer` keeps its name, its zero-argument signature and its body.
- **F-3: The NER-backed set is `SpacyRecognizer.supported_entities`.** Measured on Presidio 2.2.364 (`RecognizerRegistry().load_predefined_recognizers(languages=["en"])`):
  - `SpacyRecognizer` (a `LocalRecognizer`) serves `DATE_TIME, NRP, LOCATION, PERSON, ORGANIZATION`.
  - Every other recognizer is a `PatternRecognizer`, except `PhoneRecognizer`, a `LocalRecognizer` built on the `phonenumbers` library with no NER.
  - `DATE_TIME` is **also** served by the pattern `DateRecognizer`. On the blank pipeline, `"Jane Doe lives in Paris on 2024-01-02"` with `PERSON, LOCATION, DATE_TIME` at threshold 0 returns only `DATE_TIME 0.6` from `DateRecognizer`. The full analyzer adds NER's `DATE_TIME`. The two analyzers therefore disagree on `DATE_TIME`, so it has to select the full analyzer. This settles the STORY-005 handoff: all five types are NER types.
  - The PRD names only `PERSON`/`LOCATION` because those are the two in today's `PII_ENTITIES`. The story's AC 1 says "or any other NER-backed type Presidio defines".
- **F-4: The chosen route works in production form.** A probe, a scratch script built exactly as Task 1 specifies with component name `pii_lower_as_lemma`, gave these results:
  - It builds in ~100 ms with no download.
  - `analyze("jane@example.com called 415-555-0134", entities=PII_ENTITIES_CODE, score_threshold=0.40)` returns `EMAIL_ADDRESS (0,16) 1.0` and `PHONE_NUMBER (24,36) 0.75`.
  - The phone scores 0.75 because the lower-cased `called` is a context word, while lg lemmatizes it to `call`. This is STORY-003's one known difference, and it errs toward masking.
  - The default registry still contains `SpacyRecognizer`, but on a blank pipeline `doc.ents` is empty, so it yields nothing.
- **F-5: spaCy component names are global.** Registering a second function under an existing `@Language.component` name raises nothing: the later registration silently replaces the earlier one. `scripts/measure_pii_latency.py:174` already registers `lower_as_lemma`, and `tests/test_measure_pii_latency.py` imports the script and `pii_redactor` into one process. The production component therefore gets a **distinct** name, `pii_lower_as_lemma`, so neither module can swap the other's function unnoticed.
- **F-6: Presidio downloads any model name it does not recognize** (`spacy_nlp_engine.py:78-81`, a `SystemExit` on failure; STORY-003 route 1). The subclass's `load()` never calls `spacy.load` or `spacy.cli.download`. The only Presidio call on this path is `SpacyNlpEngine.__init__`, which only stores `models`. A test asserts no download or `spacy.load` happens during the build.
- **F-7: How startup failures surface.** Neither lifespan catches exceptions:
  - `app/main.py:14` calls `pii_redactor.load()` directly.
  - `chat_ui/chat_ui/chat_ui.py:195` registers `pii_redactor.load` as a zero-argument sync lifespan task, and its comment (`:190-194`) requires it to stay zero-argument, sync and `PII_REDACTION_ENABLED`-aware.
  - A `PiiRedactorError` raised from `load()` therefore stops both boots, with no change to either file. `tests/test_main.py:236-251` is the precedent test: `pytest.raises(X): with TestClient(app): pass`.
- **F-8: The existing singleton has no lock.** `_get_analyzer` / `_get_anonymizer` are check-then-build with no lock. The locked idiom (`pipeline_executor.py:30-42`) exists but is not used here. Both analyzers are prebuilt by `load()` before the first request, and a race on first use would build twice without giving a wrong answer. The new singleton follows the module's own idiom (decision P6).
- **F-9: No test is marked as needing a model.** There are no markers or `skipif`. The fast tests switch to `en_core_web_sm` through a fixture (`tests/test_pii_redactor.py:13-18`, `tests/test_main.py:32-47`). The tokenizer-only analyzer needs no model at all.
- **F-10: The test baseline needs the libSQL dev container.** `tests/conftest.py` exits the whole session if `127.0.0.1:8080` is unreachable (STORY-005 plan F-6). `/implement` starts `harness-libsql-dev` first.

---

## Patterns to Follow

### Naming and singleton: builder wraps every failure in `PiiRedactorError`; getter is check-then-build
```python
# SOURCE: app/services/pii_redactor.py:9-33
_analyzer: Optional[AnalyzerEngine] = None
_anonymizer: Optional[AnonymizerEngine] = None


class PiiRedactorError(Exception):
    pass


def _build_analyzer() -> AnalyzerEngine:
    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": settings.PII_NLP_MODEL}],
    }
    try:
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    except Exception as exc:
        raise PiiRedactorError(f"Failed to load Presidio NLP model {settings.PII_NLP_MODEL!r}: {exc}") from exc


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = _build_analyzer()
    return _analyzer
```

### The tokenizer-only engine (reference implementation, STORY-003)
```python
# SOURCE: scripts/measure_pii_latency.py:174-202, 274-277
@Language.component("lower_as_lemma")
def lower_as_lemma(doc):
    for token in doc:
        token.lemma_ = token.lower_
    return doc


class _TokenizerOnlySpacyNlpEngine(SpacyNlpEngine):
    """A SpacyNlpEngine over spacy.blank("en"): a tokenizer, no tagger, parser or NER."""

    def __init__(self, lemmas: bool):
        super().__init__(models=[{"lang_code": "en", "model_name": "blank"}])
        self._lemmas = lemmas

    def load(self) -> None:
        nlp = spacy.blank("en")
        if self._lemmas:
            nlp.add_pipe("lower_as_lemma")
        self.nlp = {"en": nlp}

def _subclass_analyzer(lemmas: bool) -> AnalyzerEngine:
    engine = _TokenizerOnlySpacyNlpEngine(lemmas=lemmas)
    engine.load()
    return AnalyzerEngine(nlp_engine=engine, supported_languages=["en"])
```

### Error handling: a startup failure stops the lifespan (test shape)
```python
# SOURCE: tests/test_main.py:236-251
def test_lifespan_fails_when_patterns_file_is_malformed(_pattern_startup, tmp_path, monkeypatch):
    """PRD-011 STORY-007 AC 1 and AC 4, FastAPI path: a malformed
    PATTERNS_FILE stops startup with PatternConfigError, before the app serves
    anything, and leaves no half-applied policy behind."""
    ...
    with pytest.raises(PatternConfigError) as excinfo:
        with TestClient(app):
            pass
```

### Tests: the constructed-once test the new analyzer gets an equivalent of
```python
# SOURCE: tests/test_pii_redactor.py:13-18, 38-51
@pytest.fixture(autouse=True)
def _small_model_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "PII_NLP_MODEL", "en_core_web_sm")
    monkeypatch.setattr(pii_redactor, "_analyzer", None)
    monkeypatch.setattr(pii_redactor, "_anonymizer", None)
    yield

def test_analyzer_engine_constructed_only_once(monkeypatch):
    build_calls = []
    original_build = pii_redactor._build_analyzer

    def _counting_build():
        build_calls.append(1)
        return original_build()

    monkeypatch.setattr(pii_redactor, "_build_analyzer", _counting_build)

    redact("first call, no pii")
    redact("second call, no pii either")

    assert len(build_calls) == 1
```

### Tests: the lemma check to carry over (STORY-003 report asks for it)
```python
# SOURCE: tests/test_measure_pii_latency.py:227-240
def _phone_score(analyzer, text):
    results = analyzer.analyze(text=text, language="en", entities=["PHONE_NUMBER"], score_threshold=0)
    assert len(results) == 1
    return round(results[0].score, 2)


def test_tokenizer_only_route_with_lemmas_boosts_context():
    with_lemmas = bench._subclass_analyzer(lemmas=True)
    without = bench._subclass_analyzer(lemmas=False)

    assert with_lemmas.nlp_engine.nlp["en"].pipe_names == ["lower_as_lemma"]
    assert _phone_score(with_lemmas, "My phone is 415-555-0134 please.") == 0.75
    assert _phone_score(without, "My phone is 415-555-0134 please.") == 0.40
    assert _phone_score(with_lemmas, "Call 415-555-0134") == 0.40  # `call` is not a context word
```

### Test module header and section banners
```python
# SOURCE: tests/test_pii_characterization.py:1-10, 38-41, 90
"""PRD-012 STORY-002: today's redact() and pipeline steps 6 and 8, pinned before anything moves.
...
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
# --- AC 1: redact() -------------------------------------------------------------
```

---

## Design

### Files to CREATE
- `tests/test_pii_pattern_analyzer.py`: AC 1-4 at the function level, the NER-set drift guard, and the chat-invariance guard.

### Files to UPDATE
- `app/services/pii_redactor.py`: the constant, the component, the engine subclass, the second singleton, the selector and `load()`.
- `tests/test_main.py`: an appended `PRD-012 STORY-006` block with AC 3 through the FastAPI lifespan (both analyzers prebuilt; a build failure stops the boot). No existing assertion changes.
- `app/config.py`: **one comment only**, above `PII_ENTITIES_CODE`. It points at `pii_redactor._NER_ENTITY_TYPES`, because the "no NER type" rule now covers five types, not two. No field, default or validator changes.

### Files deliberately NOT touched
- `tests/test_pii_redactor.py`, `tests/test_pii_characterization.py`: AC 5.
- `scripts/measure_pii_latency.py`, `tests/test_measure_pii_latency.py`: STORY-003's measurement stays reproducible as it was run. STORY-013 adds the `code` arm through `redact_for_policy`.
- `app/main.py`, `chat_ui/chat_ui/chat_ui.py`: both already call `pii_redactor.load()` at startup (F-7). `load()` stays zero-argument and sync.
- `.env.example`, README: STORY-014.

### Dependency order
Task 1 (`pii_redactor.py`) → Task 2 (config comment) → Task 3 (new test module) → Task 4 (`test_main.py` lifespan block) → Task 5 (regression sweep and AC 5 proof).

### Decisions made here

| # | Decision | Why |
|---|---|---|
| P1 | `_NER_ENTITY_TYPES = frozenset({"PERSON", "LOCATION", "ORGANIZATION", "NRP", "DATE_TIME"})`, in `pii_redactor.py`, with a comment per member | The story says "a constant beside the analyzer code, with a comment naming why each member is there". It is exactly `SpacyRecognizer`'s entities (F-3). `DATE_TIME` is included even though a pattern recognizer also serves it, because on the blank pipeline its results differ (F-3). A test pins the constant to the live `SpacyRecognizer` so a Presidio bump cannot drift it silently. Nothing infers it at runtime |
| P2 | `_get_analyzer(entities: Optional[Iterable[str]] = None)`. `None` means full. Any NER type means full. Otherwise it returns the tokenizer-only analyzer. An empty iterable means tokenizer-only | F-1 needs the no-argument form. An empty list is unreachable from settings (STORY-005 rejects it), and it contains no NER type, so the rule applies as written |
| P3 | `redact()` keeps calling `_get_analyzer()` with **no argument** | `chat` must not move by a byte (PRD Section 11, first functional requirement). If `redact()` passed `settings.pii_entities_list`, an operator who set `PII_ENTITIES=EMAIL_ADDRESS` would silently move `chat` onto the blank pipeline, where the "Called" lemma difference changes scores. `test_pii_entities_env_var_restricts_checked_types` sets exactly that. A new test pins this choice |
| P4 | A separate `_build_pattern_analyzer()` and `_pattern_analyzer` global. `_build_analyzer` is unchanged | F-2. It also makes AC 2's "the same object `redact()` uses" literally `pii_redactor._analyzer` |
| P5 | The component is registered as `pii_lower_as_lemma` at module import, not `lower_as_lemma` | F-5. The STORY-003 report asks for registration "once, at module import", and a distinct name keeps it once per function |
| P6 | No lock, the same as `_get_analyzer` today | F-8. `load()` prebuilds both before any request, and the module's existing singleton has no lock. Adding a lock to only one of the two would make them inconsistent without making either correct. A lock is a separate change for both |
| P7 | The tokenizer-only `AnalyzerEngine` uses Presidio's **default** registry. Entities are restricted at `analyze()` time | This is the configuration STORY-003 benchmarked and parity-checked (4 differences). `SpacyRecognizer` is present but inert on a blank pipeline (F-4). Hand-picking a registry would be an unmeasured variant |
| P8 | `load()` builds the full analyzer first, then `_get_analyzer(settings.pii_entities_code_list)`. When `PII_ENTITIES_CODE` contains a NER type, the second call returns the already-built full analyzer and nothing else is built | This matches AC 3 as written: "today's analyzer as before **and** the analyzer `PII_ENTITIES_CODE` selects". It is the only settings-driven selection this story can make. STORY-007's `pii_policy.load()` owns policies and needs nothing more from here, because the `code` policy's entities *are* `PII_ENTITIES_CODE` |
| P9 | A failure in `_build_pattern_analyzer` raises `PiiRedactorError("Failed to build the tokenizer-only Presidio analyzer that PII_ENTITIES_CODE selects (spacy.blank('en')): {exc}")`. `_pattern_analyzer` stays `None`. `_get_analyzer(pattern list)` never returns the full analyzer | The story's no-silent-fallback note. The message names the setting, so the operator knows what selected it and that adding `PERSON` is the documented way to get the full analyzer on purpose |
| P10 | AC 4's "spy on `en_core_web_lg`" has three parts. The full-analyzer slot holds a **tripwire** object that records any attribute access. `_build_analyzer` is wrapped to record calls. `spacy.load` and `spacy.cli.download` are wrapped to record calls. The test builds the pattern analyzer, analyzes, and asserts all three logs are empty | Loading lg to spy on it would cost seconds and prove less. The tripwire proves the full analyzer is never *reached*, and the `spacy.load` spy proves no model is *loaded*, lg or any other |

### Risks

| Risk | Mitigation |
|---|---|
| A future `redact_for_policy` caller passes `settings.pii_entities_list` and moves `chat` onto the blank pipeline | P3's test: `redact()` with a pattern-only `PII_ENTITIES` still uses `_analyzer` and never calls `_build_pattern_analyzer`. STORY-008/009 keep `chat` on `redact()` (PRD F8) |
| The `_pattern_analyzer` singleton leaks between tests | It is settings-independent (no model name), so a leaked instance is still correct. The new module's autouse fixture resets it anyway, and the `test_main.py` block does the same |
| `test_lifespan_does_not_reload_analyzer_on_first_request` now also builds the tokenizer-only analyzer | It counts `_build_analyzer` only, and P4 keeps that at 1. The new analyzer adds ~100 ms to that test |
| A Presidio upgrade adds a NER-served type, or moves one | The drift test (`_NER_ENTITY_TYPES == set(SpacyRecognizer().supported_entities)`) turns red. `requirements.txt` pins 2.2.364 |
| The duplicate component name silently replaces a function (F-5) | P5, with a test asserting `pipe_names == ["pii_lower_as_lemma"]` |
| A Presidio model download sneaks into the build (F-6) | The AC 4 test's `spacy.cli.download` / `spacy.load` spies record nothing |
| Mass fixture errors from the libSQL container (F-10) | Start the container first; rerun a single failing file in isolation before suspecting code (STORY-003/005 reports) |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/pii_redactor.py` | UPDATE | `_NER_ENTITY_TYPES`, `pii_lower_as_lemma`, `_TokenizerOnlySpacyNlpEngine`, `_pattern_analyzer`, `_build_pattern_analyzer`, `_get_analyzer(entities=None)`, `load()` prebuilds both |
| `app/config.py` | UPDATE | The comment above `PII_ENTITIES_CODE` names `pii_redactor._NER_ENTITY_TYPES` as the "NER type" set. Comment only |
| `tests/test_pii_pattern_analyzer.py` | CREATE | AC 1-4, NER-set drift guard, chat-invariance guard |
| `tests/test_main.py` | UPDATE | Appended `PRD-012 STORY-006` block: the lifespan prebuilds both analyzers; a tokenizer-only build failure stops the boot |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Tokenizer-only analyzer and selection in `pii_redactor.py`

- **File**: `app/services/pii_redactor.py`
- **Action**: UPDATE
- **Implement**:
  1. **Imports.** Add `from typing import Iterable`, alongside the existing `typing` import. Add `import spacy`, `from spacy.language import Language`, and `SpacyNlpEngine` to the `presidio_analyzer.nlp_engine` import. Keep the existing imports.
  2. **`_NER_ENTITY_TYPES`** (after `PiiRedactorError`). A `frozenset` of the five names in P1, each on its own line with a trailing comment:
     - `PERSON` and `LOCATION`: in today's `PII_ENTITIES`, the two the PRD names (D7) and the main source of false positives on code (STORY-003: 11 and 7 false positives on `code/`);
     - `ORGANIZATION` and `NRP`: served only by `SpacyRecognizer`;
     - `DATE_TIME`: served by `SpacyRecognizer` *and* `DateRecognizer`. On a blank pipeline only the pattern half runs, so the two analyzers would disagree.

     The comment block above it says four things. These are the types Presidio 2.2.364's `SpacyRecognizer` serves. A list containing any of them needs the NER model, so it gets the full analyzer. The set is written out rather than read from Presidio at runtime (story Technical Notes). `tests/test_pii_pattern_analyzer.py` pins it to the live recognizer.
  3. **`pii_lower_as_lemma`** (`@Language.component("pii_lower_as_lemma")`). The body is `for token in doc: token.lemma_ = token.lower_; return doc`. The docstring states the following:
     - Presidio's context enhancer reads `token.lemma_`. A blank pipeline leaves it empty, which loses every context boost (0.75 → 0.40).
     - STORY-003 measured this route at 4 differences from lg, all in the masking direction.
     - The name differs from the benchmark script's `lower_as_lemma` because spaCy component names are process-global (F-5).
  4. **`_TokenizerOnlySpacyNlpEngine(SpacyNlpEngine)`**:
     - `__init__(self)` calls `super().__init__(models=[{"lang_code": "en", "model_name": "blank"}])`.
     - `load()` sets `nlp = spacy.blank("en")`, calls `nlp.add_pipe("pii_lower_as_lemma")`, then sets `self.nlp = {"en": nlp}`.
     - The docstring says it has a tokenizer and lemmas, with no tagger, parser or NER. It also says why it subclasses rather than using `NlpEngineProvider`: a blank model name makes Presidio attempt a download that ends in `SystemExit` (STORY-003 route 1).
     - Mirror `scripts/measure_pii_latency.py:191-202` without the `lemmas` flag, since production always wants lemmas.
  5. **Global**: `_pattern_analyzer: Optional[AnalyzerEngine] = None`, beside `_analyzer`.
  6. **`_build_pattern_analyzer() -> AnalyzerEngine`**:
     - Inside `try`: `engine = _TokenizerOnlySpacyNlpEngine(); engine.load(); return AnalyzerEngine(nlp_engine=engine, supported_languages=["en"])`.
     - `except Exception as exc`: raise `PiiRedactorError` with P9's message `from exc`.
     - Leave `_build_analyzer` untouched.
  7. **`_get_analyzer(entities: Optional[Iterable[str]] = None) -> AnalyzerEngine`**:
     - If `entities is None` or `not _NER_ENTITY_TYPES.isdisjoint(entities)`: the existing body (`global _analyzer`, build on `None`, return).
     - Otherwise: `global _pattern_analyzer`, build it with `_build_pattern_analyzer()` if `None`, return it.
     - The docstring states the three cases, that `None` is today's no-argument contract (the characterization fixture and the benchmark script depend on it), and that there is no fallback from the tokenizer-only analyzer to the full one.
  8. **`load()`**: after the existing `_get_analyzer()`, add `_get_analyzer(settings.pii_entities_code_list)`. Add a docstring:
     - it runs at startup in both lifespans;
     - it builds both analyzers the configured profiles need, so neither is built on a request (PRD F6);
     - a failure raises `PiiRedactorError` and stops the boot;
     - the `PII_REDACTION_ENABLED=false` early return still covers both.
  9. **`redact()`**: **no change**. It keeps `analyzer = _get_analyzer()` (P3). Add a one-line comment above that call: no argument on purpose, because `chat` always runs the full analyzer whatever `PII_ENTITIES` holds.
- **Mirror**: `app/services/pii_redactor.py:17-33` (builder and getter); `scripts/measure_pii_latency.py:174-202, 274-277` (engine).
- **Validate**:
  ```
  .venv/Scripts/python.exe -c "import app.main"
  .venv/Scripts/python.exe -c "import os; os.environ.setdefault('OPENROUTER_API_KEY','x'); os.environ.setdefault('ADMIN_TOKEN','x'); import app.services.pii_redactor as p; a=p._get_analyzer(['EMAIL_ADDRESS','PHONE_NUMBER','CREDIT_CARD','US_SSN','IBAN_CODE']); print(type(a.nlp_engine).__name__, a.nlp_engine.nlp['en'].pipe_names, p._analyzer is None); print([(r.entity_type,r.start,r.end,r.score) for r in a.analyze(text='jane@example.com called 415-555-0134', language='en', entities=['EMAIL_ADDRESS','PHONE_NUMBER'], score_threshold=0.40)])"
  ```
  The second command prints `_TokenizerOnlySpacyNlpEngine ['pii_lower_as_lemma'] True`, then `[('EMAIL_ADDRESS', 0, 16, 1.0), ('PHONE_NUMBER', 24, 36, 0.75)]`. `True` means the full analyzer was never built.

### Task 2: Point the `PII_ENTITIES_CODE` comment at the constant

- **File**: `app/config.py`
- **Action**: UPDATE (comment only)
- **Implement**: In the comment above `PII_ENTITIES_CODE` (`:210-214`), change "with no NER type in the list" to name the set: "with no NER type in the list (`pii_redactor._NER_ENTITY_TYPES`: PERSON, LOCATION, ORGANIZATION, NRP, DATE_TIME)". Leave the rest as it is. Change no field, default or validator.
- **Mirror**: the existing comment style at `app/config.py:204-215`.
- **Validate**: `git diff app/config.py` shows comment lines only. `.venv/Scripts/python.exe -m pytest tests/test_config.py -q` passes.

### Task 3: `tests/test_pii_pattern_analyzer.py`

- **File**: `tests/test_pii_pattern_analyzer.py`
- **Action**: CREATE
- **Implement**:
  - **Module docstring** `"""PRD-012 STORY-006: the pattern-only analyzer, selected by the entity list. ..."""`. It says:
    - which ACs are covered here and which in `tests/test_main.py` (AC 3's lifespan path);
    - that AC 5 is proved by running two files that this story does not edit;
    - that the full analyzer runs on `en_core_web_sm` here, the `tests/test_pii_redactor.py` precedent, because these tests check *which object* is selected, not lg's scores. `tests/test_pii_characterization.py` already pins lg.
  - The `os.environ.setdefault` header, then imports: `pytest`, `spacy`, `settings`, `pii_redactor`, `SpacyRecognizer` from `presidio_analyzer.predefined_recognizers`, and `_PRESIDIO_ENTITY_NAMES` from `app.config`.
  - **Autouse fixture `_small_model_and_reset(monkeypatch)`**:
    - `PII_NLP_MODEL="en_core_web_sm"` and `PII_REDACTION_ENABLED=True`;
    - `PII_ENTITIES_CODE` pinned to the shipped default string, so a developer's `.env` cannot change the selection;
    - `_analyzer`, `_anonymizer` and `_pattern_analyzer` set to `None`.
  - `_CODE_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE"]`.
  - `_PATTERN_ONLY_TYPES = sorted(_PRESIDIO_ENTITY_NAMES - pii_redactor._NER_ENTITY_TYPES)`.

  **The NER set (Technical Notes)**
  - `test_ner_entity_types_are_exactly_what_spacy_recognizer_serves`: `pii_redactor._NER_ENTITY_TYPES == frozenset(SpacyRecognizer().supported_entities)`. The docstring says this is a drift guard: the constant is written out, never inferred at runtime.
  - `test_ner_entity_types_are_known_presidio_names`: `_NER_ENTITY_TYPES <= _PRESIDIO_ENTITY_NAMES`.

  **AC 1: no NER type → tokenizer-only, built once, cached**
  - `test_code_entities_select_the_tokenizer_only_analyzer`:
    - `a = pii_redactor._get_analyzer(_CODE_ENTITIES)`.
    - `type(a.nlp_engine) is pii_redactor._TokenizerOnlySpacyNlpEngine`.
    - `a.nlp_engine.nlp["en"].pipe_names == ["pii_lower_as_lemma"]`, so there is no `ner`.
    - `a is pii_redactor._pattern_analyzer`, and `pii_redactor._analyzer is None`: the full analyzer was never built.
  - `@pytest.mark.parametrize("entity", _PATTERN_ONLY_TYPES)` `test_every_pattern_only_type_alone_selects_the_tokenizer_only_analyzer`. Once the first build is cached, this is cheap.
  - `test_pattern_analyzer_constructed_only_once(monkeypatch)`: the equivalent of `test_analyzer_engine_constructed_only_once`, as the story's Technical Notes ask.
    - Wrap `_build_pattern_analyzer` with a counting wrapper.
    - Call `_get_analyzer(_CODE_ENTITIES)` twice and `_get_analyzer(reversed(_CODE_ENTITIES))` once; the order must not matter.
    - Assert all three returned the same object and `len(build_calls) == 1`.
  - `test_tokenizer_only_analyzer_keeps_context_boosts`: carried over from `tests/test_measure_pii_latency.py:233`, as the STORY-003 report asks. On the production analyzer:
    - `"My phone is 415-555-0134 please."` scores `PHONE_NUMBER` 0.75;
    - `"Call 415-555-0134"` scores 0.40;
    - use a local `_phone_score` helper that mirrors `:227-230`.

  **AC 2: a NER type → today's full singleton, the one `redact()` uses**
  - `@pytest.mark.parametrize("entities", [["PERSON"], ["PERSON", *_CODE_ENTITIES], ["LOCATION"], ["ORGANIZATION"], ["NRP"], ["DATE_TIME"], ["EMAIL_ADDRESS", "DATE_TIME"]])` `test_a_ner_type_selects_the_full_analyzer`. Call `pii_redactor.redact("jane@example.com")` first, then assert `pii_redactor._get_analyzer(entities) is pii_redactor._analyzer`, and `pii_redactor._pattern_analyzer is None`: nothing extra was built.
  - `test_no_argument_is_the_full_analyzer`: `_get_analyzer() is _get_analyzer(["PERSON"])`, and it is not a `_TokenizerOnlySpacyNlpEngine`. This pins F-1's contract.
  - `test_redact_uses_the_full_analyzer_even_with_a_pattern_only_pii_entities(monkeypatch)` (P3):
    - Set `PII_ENTITIES="EMAIL_ADDRESS"`.
    - Wrap `_build_pattern_analyzer` with a recorder.
    - `redact("a@b.com")` still returns `("<EMAIL_ADDRESS>", ["EMAIL_ADDRESS"])`.
    - The recorder is empty and `_pattern_analyzer is None`.
    - The docstring says `chat` must not move (PRD Section 11).

  **AC 3: `load()` prebuilds both, and a failure stops it** (function level; the lifespan is in Task 4)
  - `test_load_builds_the_full_and_the_code_analyzer(monkeypatch)`:
    - Wrap both builders with counters, then call `pii_redactor.load()`.
    - Each counter is 1, and both globals are non-`None`.
    - Then call `_get_analyzer(settings.pii_entities_code_list)` and `redact("x")`. Both counters are still 1: nothing was built on "a request".
  - `test_load_with_a_ner_type_in_code_entities_builds_only_the_full_analyzer(monkeypatch)`:
    - Set `PII_ENTITIES_CODE="PERSON,EMAIL_ADDRESS"` and call `load()`.
    - `_pattern_analyzer is None`, the pattern counter is 0 and the full counter is 1.
  - `test_load_is_a_noop_for_both_when_redaction_disabled(monkeypatch)`: with `PII_REDACTION_ENABLED=False`, both globals stay `None`.
  - `test_a_tokenizer_only_build_failure_is_a_startup_error_not_a_fallback(monkeypatch)`:
    - `monkeypatch.setattr(pii_redactor.spacy, "blank", _raising)`, where `_raising` raises `OSError("boom")`.
    - `pytest.raises(pii_redactor.PiiRedactorError)` from `load()`. The message contains `PII_ENTITIES_CODE` and `boom`.
    - `_pattern_analyzer is None`.
    - A second `_get_analyzer(_CODE_ENTITIES)` raises `PiiRedactorError` again and **does not** return `_analyzer`, which the first half of `load()` did build.
    - The docstring quotes the story's no-silent-fallback note.

  **AC 4: the pattern-only analyzer finds email and phone; nothing touches lg**
  - `test_pattern_analyzer_detects_email_and_phone_without_touching_en_core_web_lg(monkeypatch)`:
    - Install the P10 spies before building:
      - a `_Tripwire` class whose `__getattr__` appends the name to a list and raises `AssertionError`, set as `pii_redactor._analyzer`;
      - a recording wrapper on `_build_analyzer`;
      - recording wrappers on `spacy.load` and `spacy.cli.download`. The download wrapper raises, like STORY-003's `_downloads_refused`.
    - Then `results = pii_redactor._get_analyzer(_CODE_ENTITIES).analyze(text="jane@example.com called 415-555-0134", language="en", entities=_CODE_ENTITIES, score_threshold=settings.PII_SCORE_THRESHOLD_CODE)`.
    - Assert `{(r.entity_type, r.start, r.end) for r in results} == {("EMAIL_ADDRESS", 0, 16), ("PHONE_NUMBER", 24, 36)}`, and that all four spy logs are empty.
    - The docstring explains why a tripwire and a `spacy.load` spy stand in for "a spy on en_core_web_lg" (P10).
- **Mirror**: `tests/test_pii_redactor.py:13-51` (fixture, counting wrapper); `tests/test_measure_pii_latency.py:227-240` (score helper, lemma test); `tests/test_pii_characterization.py:1-10, 90` (docstring banner, AC section banners); `tests/test_measure_pii_latency.py:243-253` (download spy).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pii_pattern_analyzer.py -q`. Everything passes in a few seconds (the small model plus a blank pipeline).

### Task 4: Lifespan block in `tests/test_main.py` (AC 3, FastAPI path)

- **File**: `tests/test_main.py`
- **Action**: UPDATE (append only; change no existing test)
- **Implement**: Append a banner in the file's style:
  ```
  # --------------------------------------------------------------------------
  # PRD-012 STORY-006 -- pii_redactor.load() prebuilds the code profile's analyzer.
  # --------------------------------------------------------------------------
  ```
  - Fixture `_pii_startup(_small_model_and_reset, monkeypatch)`. It reuses the existing fixture (sm model, `temp_db`, `RBAC_ENABLED=False`), sets `pii_redactor._pattern_analyzer` to `None`, and pins `PII_ENTITIES_CODE` to the shipped default.
  - `test_lifespan_prebuilds_the_code_profiles_analyzer(_pii_startup, monkeypatch)`:
    - Wrap `_build_pattern_analyzer` with a counter.
    - `with TestClient(app) as c:` both globals are non-`None` and the counter is 1.
    - `c.get("/health")` returns 200, and the counter is still 1.
    - Docstring: `"""PRD-012 STORY-006 AC 3, FastAPI path: ..."""`.
  - `test_lifespan_fails_when_the_tokenizer_only_analyzer_cannot_be_built(_pii_startup, monkeypatch)`:
    - `monkeypatch.setattr(pii_redactor.spacy, "blank", _raising)`.
    - `with pytest.raises(PiiRedactorError): with TestClient(app): pass`.
    - `_pattern_analyzer is None`.
    - Mirror `:236-251`.
  - The Reflex lifespan is not re-tested here. `chat_ui.py:195` registers the same zero-argument `load`, unchanged (F-7). Record this in the block's comment.
- **Mirror**: `tests/test_main.py:32-70` (fixture, counting wrapper), `:192-251` (banner, failure test).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_main.py -q` passes. The three pre-existing PII lifespan tests (`:50-79`) pass unchanged.

### Task 5: Regression sweep and AC 5 proof

- **Files**: none changed.
- **Implement**: Run the suites that touch `pii_redactor`, prove the two AC 5 files are byte-unchanged, then run the full suite.
- **Validate**:
  ```
  git diff --exit-code HEAD -- tests/test_pii_redactor.py tests/test_pii_characterization.py
  .venv/Scripts/python.exe -m pytest tests/test_pii_redactor.py tests/test_pii_characterization.py tests/test_pii_pattern_analyzer.py tests/test_main.py tests/test_measure_pii_latency.py tests/test_pipeline_concurrency.py tests/test_config.py -q
  .venv/Scripts/python.exe -m pytest -q
  ```

---

## End-to-End Tests

`/implement` executes these, beyond pytest:

- [ ] `.venv/Scripts/python.exe -c "import app.main"` imports cleanly, and importing builds no analyzer: `pii_redactor._analyzer is None and pii_redactor._pattern_analyzer is None` straight after import.
- [ ] The Task 1 one-liner prints `_TokenizerOnlySpacyNlpEngine ['pii_lower_as_lemma'] True` and the two AC 4 spans.
- [ ] Start the API: `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8001`. It starts without error, and `curl http://localhost:8001/health` returns `200 {"status":"ok"}`. Stop the server.
- [ ] Boot with the NER opt-in: `PII_ENTITIES_CODE=PERSON,EMAIL_ADDRESS` with the same uvicorn command also starts and serves `/health`, having built only the full analyzer (checked in the Task 3 test; here, only that boot succeeds).
- [ ] The startup timing is sane. Run `.venv/Scripts/python.exe -c "import time,os; os.environ.setdefault('OPENROUTER_API_KEY','x'); os.environ.setdefault('ADMIN_TOKEN','x'); import app.services.pii_redactor as p; t=time.perf_counter(); p._get_analyzer(['EMAIL_ADDRESS']); print(round((time.perf_counter()-t)*1000),'ms')"`. It prints a few hundred ms at most (the probe measured ~100 ms).
- [ ] `git diff --stat HEAD` touches only `app/services/pii_redactor.py`, `app/config.py` (comment lines), `tests/test_pii_pattern_analyzer.py` and `tests/test_main.py`, plus this story's `.agents/` files. In particular, nothing changes in `tests/test_pii_redactor.py`, `tests/test_pii_characterization.py`, `scripts/`, `app/main.py`, `chat_ui/`, `.env.example` or the README.

---

## Validation

```bash
# Precondition (F-10): the libSQL dev server the conftest requires
docker start harness-libsql-dev   # or the `docker run` line tests/conftest.py prints

.venv/Scripts/python.exe -c "import app.main"                        # backend imports (server-start smoke)
.venv/Scripts/python.exe -m pytest tests/test_pii_pattern_analyzer.py -q
.venv/Scripts/python.exe -m pytest tests/test_pii_redactor.py tests/test_pii_characterization.py -q   # AC 5, unchanged files
git diff --exit-code HEAD -- tests/test_pii_redactor.py tests/test_pii_characterization.py
.venv/Scripts/python.exe -m pytest -q                                 # full suite
```

The repo has no linter configured and no npm frontend, and this story changes no UI, so there is no frontend lint step.

---

## Handoff (for later stories)

- **STORY-008 (`redact_for_policy`)**: call `pii_redactor._get_analyzer(policy.entities)`, never `_get_analyzer()`. The no-argument form is `chat`'s full analyzer. R3's 20,000-character line-aligned chunking is still STORY-008's requirement, and this story does not chunk.
- **STORY-007 (`pii_policy.load()`)**: nothing extra to prebuild. `pii_redactor.load()` already builds what `PII_ENTITIES_CODE` selects. If a future policy file brings other entity lists, `pii_redactor.load()` would have to take them. That is out of scope here, and `load()` stays zero-argument for Reflex (F-7).
- **STORY-013**: when adding the `code` arm to `scripts/measure_pii_latency.py`, go through `redact_for_policy`, which uses this story's analyzer. The script's own `lower_as_lemma` route stays as the STORY-003 baseline.
- **STORY-014 (README)**: under `code`, "NER types" means all five of `_NER_ENTITY_TYPES`. Adding any of them to `PII_ENTITIES_CODE` switches `code` to `en_core_web_lg`, at lg's cost.

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] Given an entity list containing no NER type (`PERSON`, `LOCATION`, or any other NER-backed type Presidio defines), when `_get_analyzer(entities)` is called, then it returns the tokenizer-only analyzer the STORY-003 report found feasible (or the documented fallback), built once and cached.
- [ ] Given an entity list containing `PERSON`, when `_get_analyzer(entities)` is called, then it returns today's `en_core_web_lg` analyzer singleton, the same object `redact()` uses.
- [ ] Given `pii_redactor.load()` with `PII_REDACTION_ENABLED=true`, when it runs at startup, then it builds today's analyzer as before **and** the analyzer `PII_ENTITIES_CODE` selects, so no analyzer is built on a request path.
- [ ] Given the pattern-only analyzer, when it analyzes `jane@example.com called 415-555-0134`, then it returns `EMAIL_ADDRESS` and `PHONE_NUMBER` spans, and a spy on `en_core_web_lg` records no call.
- [ ] Given `redact()`, when this story lands, then `test_pii_redactor.py` and `test_pii_characterization.py` pass unchanged.
- [ ] All tasks completed
- [ ] Backend imports / server starts without error (`import app.main`; uvicorn `/health` 200)
- [ ] Full pytest suite green (libSQL dev server running)
- [ ] Follows existing patterns
