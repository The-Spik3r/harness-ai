---
story: STORY-003
prd: PRD-012
slug: pii-benchmark-baseline
title: "Benchmark harness, baseline numbers, pinned versions and tokenizer-only analyzer feasibility"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-24
---

# Plan: Benchmark harness, baseline numbers, pinned versions and tokenizer-only analyzer feasibility

## Summary

This story adds one measurement script, `scripts/measure_pii_latency.py`, and a small test module for its pure parts. It pins three packages in `requirements.txt` and writes the report that turns the PRD's provisional values into decided ones.

The script times redaction only, not the pipeline, in three arms:
- `chat`: today's `pii_redactor.redact()`.
- `pattern-lg`: the five pattern entities on the existing `en_core_web_lg` analyzer.
- `pattern-blank`: the same entities on a tokenizer-only `spacy.blank("en")` analyzer.

Each arm runs over deterministic agent-shaped conversations of exactly 40k, 200k and 400k characters, built from `tests/corpora/pii/`. Beyond latency, the script reports:
- how every route to a tokenizer-only engine fared (feasibility);
- per-entity true and false positives over `code/`, at 0.35 for today's analyzer and at a range of thresholds for the pattern arm;
- prose recall;
- the NLP share of the cost;
- a single-message worst case;
- throughput at concurrency 1 and 4.

No file under `app/` or `chat_ui/` changes. The tokenizer-only engine lives in the script until STORY-006 moves it into `pii_redactor`.

The report applies four decision rules, written in this plan **before** any number is taken, to fix `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, the p95 budget at 200,000 characters, and whether `PERSON` stays out of `PII_ENTITIES_CODE` (D7).

## User Story

As a platform operator
I want redaction latency and false positives measured at agent-sized contexts before anything changes
So that the `code` threshold, size limit and latency budget are set from data

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md`. Relevant sections:
  - 4 (*Benchmark and baseline*)
  - 6.4 (D7)
  - 7/F1
  - 9.2 T10
  - 9.3
  - 11 (*Benchmark criteria*)
  - 14 Risk 2
- Inputs from earlier stories:
  - `.agents/reports/PRD-012-pii-for-code/STORY-001-pii-corpora.report.md`, *Findings for later stories → STORY-003*
  - `STORY-002-pii-characterization.report.md`, *Measured with*

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY. Story type `spike`: a measurement script, a report and version pins. No behaviour change |
| Complexity | HIGH (story: large) |
| Systems Affected | `scripts/` (new script), `tests/` (one new module), `requirements.txt` (3 pins), `.agents/reports/` (report). **No** `app/` or `chat_ui/` change |
| Story | STORY-003 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch; clean at `d0b1739`) |
| Depends on | STORY-001 ✅ done (`beeb0b9`) |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`, and its description (`.agents/skills/frontend-design/SKILL.md:3`) limits it to "visual design when building new UI or reshaping an existing one". This story writes a CLI script, a test module and a report. The story agrees (`skills: []`, "Skills: none applicable").

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Probed on `epic/PRD-012-pii-for-code` @ `d0b1739` with the installed presidio-analyzer 2.2.364, presidio-anonymizer 2.2.364, spaCy 3.8.16, `en_core_web_lg` 3.8.0 and phonenumbers 9.0.38, Python 3.11.9 on Windows 11. **The timings are single indicative runs from a throwaway probe.** They must not be copied into the report. They are here to size the design and to show that the decision rules below can be met.

### F-1: `NlpEngineProvider` cannot take a blank model by name, and it tries to download one

`SpacyNlpEngine.load()` calls `_download_spacy_model_if_needed(name)` (`.venv/Lib/site-packages/presidio_analyzer/nlp_engine/spacy_nlp_engine.py:65-81`). When `spacy.util.is_package(name)` and `Path(name).exists()` are both false, it calls `spacy.cli.download(name)`.
- With `model_name="blank:en"` or `"blank"`, this printed `No compatible package found for 'blank:en'` and raised **`SystemExit(1)`**. That is a `BaseException`, so `except Exception` does not catch it.
- It also makes a network call.

**Consequence:** the script must replace `spacy.cli.download` with a function that raises before it tries route 1. That keeps the attempt offline and able to run with no side effect. It must catch `BaseException` around each route and record `type(exc).__name__: exc` as "the Presidio error that shows why" (AC 2).

### F-2: Three routes, all of which load. Only one keeps today's scores

| Route | How | Loads | Context boost |
|---|---|---|---|
| 1 | `NlpEngineProvider`, `model_name="blank:en"` | ❌ `SystemExit` / refused download (F-1) | — |
| 2 | `NlpEngineProvider`, `model_name=<dir>`, where `spacy.blank("en").to_disk(dir)` | ✅ (`Path(name).exists()` passes) | ❌ lost |
| 3 | `SpacyNlpEngine` subclass whose `load()` sets `self.nlp = {"en": spacy.blank("en")}` | ✅ | ❌ lost |
| 3′ | Route 3 plus a one-line pipeline component `lower_as_lemma` that sets `token.lemma_ = token.lower_` | ✅ | ✅ matches lg on every probe |

Every route that loads keeps all pattern recognizers: Email, Phone, CreditCard, Iban, UsSsn and the rest are in `registry.recognizers`. The problem is the scores. Presidio's `LemmaContextAwareEnhancer` compares context words with `token.lemma_` (`spacy_nlp_engine.py:201`), and a blank pipeline has empty lemmas. So context words never boost:

| Probe | lg | blank (2/3) | blank + `lower_as_lemma` (3′) |
|---|---|---|---|
| `My phone is 415-555-0134 please.` | PHONE 0.75 | 0.40 | 0.75 |
| `mobile: (212) 555-0147` | PHONE 0.75 | 0.40 | 0.75 |
| `SSN 219-09-9999 (social security number)` | US_SSN 0.85 | 0.50 | 0.85 |
| `Call 415-555-0134` | PHONE 0.40 | 0.40 | 0.40 |

**Consequence:** feasibility is not just "does it load". The script tries routes 1, 2, 3 and 3′ in order and records each outcome. For every route that loads, it also records **score parity** with lg over the probe sentences and `code/` + `prose/`. The `pattern-blank` arm uses the first route with full parity. If no route has parity, it uses the first route that loads and reports the parity gap. If none loads, the arm is reported infeasible with the recorded errors, and the fallback (pattern entities on lg) is what the budget is set from (story Technical Notes; PRD Risk 2). The probe expects 3′.

### F-3: NLP is where the cost is, and entity filtering does not avoid it

200,000 characters of `code/` repeated as **one string**, three runs each:

| Analyzer | Entities | Time |
|---|---|---|
| lg | all 7 (today) | 11.36–11.44 s |
| lg | 5 pattern entities | 11.28–11.35 s |
| blank + lemma | 5 pattern entities | 2.13–2.17 s |

Removing `PERSON`/`LOCATION` from the list saves under 1% on lg, because `process_text` runs the whole pipeline whatever is asked for. That is PRD Risk 2's second question answered in advance. The script measures it properly by timing `analyzer.nlp_engine.process_text(text, "en")` on its own beside `analyze()` (the NLP share).

### F-4: Cost is superlinear in the length of *one* string, so message shape matters

The blank analyzer on a single string: 10k 0.026 s; 40k 0.15 s; 100k 0.64 s; 200k 2.12 s, roughly n^1.7. The same 200k split into 50 messages of 4k took **0.43 s** (lg: 9.74 s).

**Consequences:**
1. The agent-shaped conversation (many messages ≤ 13k) is the headline figure the AC asks for. It is not the worst case. `PII_MAX_CHARACTERS_CODE` bounds the **total** analyzable characters, and those can all arrive in one message, for example one large tool result.
2. The script therefore adds a **single-message worst case** for the pattern arm.
3. It also adds a **line-aligned chunked** variant of that worst case: analyze in ≤ 20,000-character windows cut at newlines, shift offsets, then anonymize once. Rule R3 needs to know whether chunking makes the worst case linear, because that decides between "limit = 200,000 and STORY-006 chunks" and "a lower limit".

### F-5: Pattern-only false positives over `code/` are few. NER's are many and break structure

Detections over `tests/corpora/pii/code/` (48,840 characters, 7 files) at score ≥ 0:

- **Pattern entities (lg and blank + lemma agree on the spans):**
  - `EMAIL_ADDRESS` 99, all on `example.com` / `example.org`. One is mixed case, `Jane.Doe@Example.com`, so matching must ignore case.
  - `CREDIT_CARD` 9 and `IBAN_CODE` 8, all the published test values.
  - `PHONE_NUMBER` 71. The only non-`555-01xx` spans are `078-05-1120`, the voided SSN and a deliberate near-miss (SOURCES.md), 4 times at 0.40 and once at 0.75. So the pattern false-positive count is expected to be **4 at t ≤ 0.40 and 1 at 0.40 < t ≤ 0.75**.
  - Bare `555-01xx` phones score 0.40 and context-boosted ones 0.75.
- **NER entities (lg only):**
  - `PERSON` 90. False positives include identifiers and code: `PENDING_VERIFICATION`, `SUPPORT_CONTACT_NAME`, `minReplicas`, `letsencrypt`, `contact.email`, `Email`, `str\n    expires`.
  - `PERSON` spans also swallow structure: `display_name="Patrick O\'Brien`, `Patrick O''Brien'`, `expect(dir.getUserByEmail("patrick.obrie…`, `ping Priya Raghunathan`.
  - `LOCATION` 18. False positives include `USD`, `America` (from a timezone ID), `Europe/Berlin`.

**Consequence:** "false positive" needs a written definition. The one used here (Task 5) is the corpus's value classes (SOURCES.md, *Value classes*). The script also counts spans that **contain a structural character** (`"`, `'`, `` ` ``, `\`, newline), because those are the ones that break code (PRD Section 6.6), and STORY-008 needs the count.

### F-6: The PRD's own example is a bare phone at 0.40

PRD Section 5, user story 3: "email the diff to maria.lopez@corp.com and call her on +1 415 555 0134". The phone scores **0.40** on every analyzer (`call` is not a context word; STORY-001 F-2). At the provisional `PII_SCORE_THRESHOLD_CODE = 0.5` it would **not** be masked, and that user story would fail. Rule R1 therefore includes this sentence as a required probe.

### F-7: Presidio keeps `score >= threshold`

`analyzer_engine.py:380`: `[result for result in results if result.score >= score_threshold]`. So a 0.40 phone survives a 0.40 threshold. Context enhancement and de-duplication run before this filter, so filtering a threshold-0 result list is **not** guaranteed to equal analyzing at `t`. The script calls `analyze(..., score_threshold=t)` once per candidate threshold. That is cheap: 49k characters on the blank analyzer takes well under a second.

### F-8: Environment, style and naming facts

- `app.config.settings` is built at import. `OPENROUTER_API_KEY`, `DATABASE_URL` and `ADMIN_TOKEN` have no default. `scripts/measure_history_latency.py:69-98` sets them before the first `app.` import. This script touches no database, so it sets `DATABASE_URL` to a dummy local URL with `setdefault` and does **not** need the libSQL container. The test suite still does (Task 0, Task 8).
- `scripts/` must not depend on the test tree (`scripts/measure_history_latency.py:260-261`). The cast, value classes and file discovery are therefore copied into the script, each citing its source. The **test** module checks that the copies have not drifted (Task 7).
- The PRD and story say `_RESOURCE_BOUNDS`, but no such name exists. The validator dict is `_POSITIVE_LIMIT_DESCRIPTIONS` (`app/config.py:19-24`). This matters to STORY-005, not here. The report records it for STORY-005.
- The "restart the libSQL container" note the story attributes to the README is **not in `README.md`**. It lives in PRD Section 11 (*Quality indicators*) and in test docstrings (`tests/test_query_pipeline_patterns.py:30-31`). The container is `harness-libsql-dev`.
- `requirements.txt` pins only `reflex==0.9.6.post1` and `libsql==0.1.11`, with `==` and one package per line. `en_core_web_lg` is not in it. The `Dockerfile:58-63` installs it with `python -m spacy download en_core_web_lg`, which picks the model compatible with the pinned spaCy.
- The corpus sizes are: `code/` 48,840 characters (largest file 10,861); `json/` 23,039 (largest 12,965); `prose/` 6,073 (largest 1,279). The corpus has to be cycled about 3× for 200k and 6× for 400k (STORY-001 asked the report to say how).
- There is no precedent test for `measure_history_latency.py`. `tests/test_manage_users_cli.py` imports `scripts.manage_users` after the env `setdefault`s, and that is the pattern for importing a script in a test.

---

## Decision rules (written before measuring)

The report applies these mechanically. It may add judgement **after** the mechanical result, labelled as such. It may not replace the result. The code arm below means `pattern-blank` if it is feasible, and otherwise `pattern-lg` (the fallback).

- **R1 `PII_SCORE_THRESHOLD_CODE`.** Take the candidates `0.35, 0.40, 0.50, 0.60, 0.75`, analyzed with the code arm. Choose the **highest** candidate `t` that meets both conditions:
  - (a) 100% of the declared entities in `prose/` that are pattern entities are found (`set(declared) ∩ PATTERN_ENTITIES ⊆ found` per file, the STORY-001 rule);
  - (b) every **required probe** is found. The probes are the PRD Section 5 story 3 sentence (F-6), and one bare `555-01xx` phone in prose with no context word.

  State the pattern false-positive count on `code/` at `t`, and at the next candidate up, so the reader sees what the lower threshold costs. *Expected from F-5/F-6:* `0.40`, with 4 false positives (`078-05-1120`). The provisional 0.5 fails (b).
- **R2 p95 budget at 200,000 characters.** Take `2 ×` the code arm's **agent-shaped** p95 at 200,000, rounded **up** to the next 250 ms. The 2× is headroom, because STORY-013 asserts this bound on a developer or CI machine under load. Report the ratio to `chat`'s p95 at the same size. *Expected from F-4:* on the order of 1 s, against about 10 s for `chat`.
- **R3 `PII_MAX_CHARACTERS_CODE`.** Default 200,000, which is `CONTEXT_MAX_CHARACTERS`. A larger value is inert while step 3 caps total characters at 200,000. Keep 200,000 if the **single-message** worst case at 200,000 has p95 ≤ the R2 budget, either unchunked or chunked:
  - If only the chunked variant meets it, the report makes **line-aligned chunking a requirement on STORY-006/008**. It is written into "For later stories" with the chunk size measured.
  - If neither meets it, set the limit to the largest size at which the unchunked single-message p95 ≤ budget. Interpolate log-log between the two measured sizes around the crossing, and round **down** to 10,000. Record that this refuses agent requests the context limit would admit.
- **R4 `PERSON` in `PII_ENTITIES_CODE` (D7).** PRD 6.4 says `PERSON` goes back in the default only if the round-trip corpus **and** the latency budget both still pass with it. `PERSON` forces the full lg analyzer (F-3), so the latency half is decided here: if the `pattern-lg` arm's agent-shaped p95 at 200,000 is greater than the R2 budget, `PERSON` stays out.
  - Report `PERSON`'s false positives on `code/` at `PII_SCORE_THRESHOLD_CODE` (lg), and how many of its spans contain a structural character, as the supporting evidence.
  - If the latency half passes, which F-3 makes unlikely, the report says the decision **waits on STORY-013's round-trip suite**, and `PERSON` stays out until then.

---

## Patterns to Follow

### Script docstring: a spike that records and asserts nothing
```python
# SOURCE: scripts/measure_history_latency.py:1-10
"""What sending history actually costs, measured rather than argued about.

PRD-010 STORY-015, serving PRD Section 11's quality indicator (...). This is a spike: it
*records* numbers and asserts none of them, exactly as
`tests/test_two_instance_smoke.py` does -- a wall-clock threshold asserted as
pass/fail would be a flaky test on a loaded machine, ...
```

### Env bootstrap before the first `app.` import
```python
# SOURCE: scripts/measure_history_latency.py:64-66, 88-100
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
...
def _bootstrap_environment(argv: Optional[Sequence[str]] = None) -> str:
    endpoint = _database_url(argv)
    os.environ["DATABASE_URL"] = endpoint
    os.environ.setdefault("OPENROUTER_API_KEY", "measurement-stub-key")
    os.environ.setdefault("ADMIN_TOKEN", "measurement-admin-token")
    return endpoint

_ENDPOINT = _bootstrap_environment()

from app.config import settings  # noqa: E402
```
This script uses `setdefault` for `DATABASE_URL` too, and needs no `--database-url`, because it never opens a connection (F-8).

### Timing and percentiles
```python
# SOURCE: scripts/measure_history_latency.py:309-341
class Samples:
    def summary(self) -> tuple[float, float, float]:
        """(min, p50, p95) in milliseconds. ... p95 is the *nearest-rank* percentile --
        sorted[ceil(0.95 * n) - 1] ..."""
        ordered = sorted(self.values)
        p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
        return min(ordered), statistics.median(ordered), p95

def _timed(work: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    result = work()
    return result, (time.perf_counter() - started) * 1000
```
Copy it, don't import it. Importing `scripts.measure_history_latency` runs its DB bootstrap. Cite the source line in a comment, as `Recording` does at 259-262.

### Warm before the window
```python
# SOURCE: scripts/measure_history_latency.py:29-33, 491-493
# The first redact() in a process loads the spaCy model ... Neither is latency.
pii_redactor.load()
```

### Output format
```python
# SOURCE: scripts/measure_history_latency.py:604-614, 627-648
"| arm | n | min (ms) | p50 (ms) | p95 (ms) |",
...
"--- STORY-015 history latency (PRD-010 Section 11, Risk 3) ---",
f"  python               : {platform.python_version()} on {platform.system()}",
...
"  p50 is the median; p95 is nearest-rank, sorted[ceil(0.95*n)-1].",
"  No latency here is asserted as a pass/fail bound.",
```

### CLI shape
```python
# SOURCE: scripts/measure_history_latency.py:748-794
def _build_parser() -> argparse.ArgumentParser: ... parser.set_defaults(func=_measure_command)
def main(argv: Optional[Sequence[str]] = None) -> int: ...
if __name__ == "__main__":
    sys.exit(main())
```

### The redactor being mirrored
```python
# SOURCE: app/services/pii_redactor.py:17-26, 49-74
nlp_configuration = {"nlp_engine_name": "spacy",
                     "models": [{"lang_code": "en", "model_name": settings.PII_NLP_MODEL}]}
nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
...
results = analyzer.analyze(text=text, language="en", entities=..., score_threshold=...)
if not results:
    return text, []
anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
```
The pattern arms reproduce `redact()` with a different analyzer and entity list. The comment on that function says so, as `_redact_all` does (`scripts/measure_history_latency.py:437-445`: "this comment is the only thing stopping the two drifting silently apart").

### Corpus discovery
```python
# SOURCE: tests/test_pii_corpus_files.py:47-76
_PII = Path(__file__).resolve().parent / "corpora" / "pii"
_NOT_SAMPLES = frozenset({"SOURCES.md"})
def _corpus(group): return sorted(path for path in (_PII / group).iterdir()
    if path.is_file() and path.name not in _NOT_SAMPLES and not path.name.startswith("."))
def _read(path): return path.read_text(encoding="utf-8")  # no newline normalisation
```
The header regex is `^# expect: (?P<entities>[A-Z_]+(?:, [A-Z_]+)*)\s*$`, and `_CAST` is at `tests/test_pii_corpus_files.py:100`.

### Script tests
```python
# SOURCE: tests/test_manage_users_cli.py:1-15
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
from scripts.manage_users import main
```

### Error handling
The script has no production error path.
- An infeasible route is **data**. The script catches `BaseException` (F-1), records it and carries on.
- A disabled redactor exits 1 with a stderr message, as at `scripts/measure_history_latency.py:708-714`.
- A misconfigured flag, such as a size ≤ 0 or an unknown arm, is `parser.error(...)`.
- Nothing is asserted on latency.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/measure_pii_latency.py` | CREATE | The benchmark (Tasks 1-6) |
| `tests/test_measure_pii_latency.py` | CREATE | Pure-part tests and drift guards (Task 7) |
| `requirements.txt` | UPDATE | Pin `presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364`, `spacy==3.8.16` (Task 8). Use the versions the script prints, which must equal these |
| `.agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md` | CREATE | Numbers, feasibility, decisions R1-R4 (Task 9) |
| `.agents/stories/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.md` | UPDATE | `/plan` Phase 5 (plan link, status). `/implement` fills in report and commit |
| `.agents/PRDs/PRD-012-pii-for-code/index.md` | UPDATE | Status and plan link now. Commit SHA later |

Nothing under `app/`, `chat_ui/` or `tests/corpora/`. `README.md` and `.env.example` are STORY-014's.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Preflight

- **Action**: environment only.
- **Implement**:
  1. `git status` is clean on `epic/PRD-012-pii-for-code`. Record `git rev-parse HEAD` as `BASE`.
  2. Start Docker Desktop (a user install, `%LOCALAPPDATA%\Programs\DockerDesktop`, per the STORY-002 report), then `docker start harness-libsql-dev`. Only the suite needs it; the script does not.
  3. Commit this plan and the Phase 5 story/index updates as `docs(PRD-012): STORY-003 plan` (precedent `72dfee9`).
  4. Run the full suite once and record the counts. STORY-002 ended at 2661 passed and 26 skipped.
  5. `.venv/Scripts/python.exe -m pip freeze > <scratchpad>/freeze-before.txt`, for Task 8's diff.
- **Validate**: `.venv/Scripts/python.exe -m pytest -q` is green. On mass fixture errors, restart `harness-libsql-dev` rather than bisecting (PRD Section 11).

### Task 1: Script skeleton, CLI, corpus copies

- **File**: `scripts/measure_pii_latency.py`
- **Action**: CREATE
- **Implement**:
  - **Docstring**: `"""What PII redaction costs at agent sizes, and what it wrongly masks, measured before anything changes.` Then paragraphs covering:
    - PRD-012 STORY-003: Sections 4, 6.4, 11 *Benchmark criteria*, Risk 2, T10.
    - A spike that records numbers and asserts none (copy the history script's argument).
    - The arms, and why `pattern-lg` exists: it isolates NLP cost from recognition cost (Risk 2).
    - Why 400k exceeds `CONTEXT_MAX_CHARACTERS` on purpose: to measure the analyzer, not the limit.
    - Why models are loaded and one iteration discarded before timing.
    - That it opens no database.
    - Usage lines, including `--sizes 40000,200000,400000 --runs 20`, `--concurrency 1,4`, `--no-timing`, `--show-corpus`.
  - **Bootstrap**: `REPO_ROOT` on `sys.path`, and `setdefault` for `DATABASE_URL=http://127.0.0.1:8080`, `OPENROUTER_API_KEY`, `ADMIN_TOKEN`, with the comment from F-8. Then import `settings` and `pii_redactor`.
  - **Constants**, each with a `#:` comment citing its source:
    - `PATTERN_ENTITIES = ("EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "IBAN_CODE")`, which is PRD 9.3's `PII_ENTITIES_CODE` default and the story's AC 2 list.
    - `NER_ENTITIES = frozenset({"PERSON", "LOCATION"})`.
    - `_CANDIDATE_THRESHOLDS = (0.35, 0.40, 0.50, 0.60, 0.75)`.
    - `_CHUNK_CHARACTERS = 20_000`.
  - **Corpus**: `_PII = REPO_ROOT / "tests" / "corpora" / "pii"`, and `_corpus(group)` / `_read(path)` copied from `tests/test_pii_corpus_files.py:47-73` with a "copied, not imported (scripts/ must not depend on the test tree)" comment. Also `_declared(path)` with the same header regex, and `_CAST`, copied from line 100.
  - **Parser**:
    - `--sizes` (comma ints, default `40000,200000,400000`)
    - `--runs` (int, default 20)
    - `--arms` (comma list from `chat,pattern-lg,pattern-blank`, default all)
    - `--concurrency` (comma ints, default `1,4`)
    - `--concurrency-size` (default 200000)
    - `--concurrency-rounds` (conversations per worker, default 3)
    - `--no-timing` (feasibility and false positives only)
    - `--show-corpus` (print the conversation shape per size and exit)
    - Reject values ≤ 0 and unknown arms with `parser.error`.
  - **Guard**: exit 1 with a stderr message if `settings.PII_REDACTION_ENABLED` is false.
- **Mirror**: `scripts/measure_history_latency.py:1-110, 748-794`
- **Validate**: `.venv/Scripts/python.exe scripts/measure_pii_latency.py --help` prints usage without loading any spaCy model. It should return in under about 3 s.

### Task 2: Analyzers and feasibility (AC 2)

- **File**: `scripts/measure_pii_latency.py`
- **Action**: UPDATE
- **Implement**:
  - `_lg_analyzer()` returns `pii_redactor._get_analyzer()`, the shipped analyzer and the object the `chat` arm uses. Assert `nlp_engine.nlp["en"].meta["name"] == "core_web_lg"`, as STORY-002's fixture did, so a `.env` pointing at `en_core_web_sm` fails loudly and does not produce wrong numbers.
  - `lower_as_lemma`: a `@Language.component`. Its docstring explains F-2: Presidio's context enhancer reads `token.lemma_`, which a blank pipeline leaves empty, and lower-casing is the nearest thing to a lemma a tokenizer can give.
  - `_TokenizerOnlySpacyNlpEngine(SpacyNlpEngine)` with `__init__(self, lemmas: bool)`, whose `load()` builds `spacy.blank("en")` and adds `lower_as_lemma` when `lemmas`.
  - `Route` is a frozen dataclass: `name`, `loaded: bool`, `error: Optional[str]`, `analyzer: Optional[AnalyzerEngine]`, `parity: Optional[Parity]`.
  - `_try_routes() -> list[Route]` tries four routes in order:
    1. `provider:blank:en`: `NlpEngineProvider` with `model_name="blank:en"`, inside a context manager that swaps `spacy.cli.download` for a function raising `RuntimeError("download of {name!r} refused: the benchmark never installs packages")` (F-1).
    2. `provider:path`: `spacy.blank("en").to_disk(tempdir)`, then `NlpEngineProvider` with that path.
    3. `subclass`: `_TokenizerOnlySpacyNlpEngine(lemmas=False)`.
    4. `subclass+lemma`: `_TokenizerOnlySpacyNlpEngine(lemmas=True)`.

    Each attempt catches `BaseException` except `KeyboardInterrupt`, and records `f"{type(exc).__name__}: {exc}"`.
  - `Parity`: for each loaded route, compare `analyze(text, "en", entities=PATTERN_ENTITIES, score_threshold=0)` against lg over `_PARITY_PROBES` (the four F-2 sentences, verbatim) and every `code/` and `prose/` file. Compare `(start, end, entity_type, round(score, 2))`. Record `compared`, `differing`, and up to 5 example differences.
  - `_pattern_blank_route(routes)` returns the first route with `differing == 0`, else the first loaded route, else `None`. When it is `None`, the `pattern-blank` arm is reported as **infeasible**, and every table row for it says so, citing the errors.
- **Mirror**: `app/services/pii_redactor.py:17-33`
- **Validate**: `.venv/Scripts/python.exe scripts/measure_pii_latency.py --no-timing` prints a feasibility table with four rows. Expected: route 1 not loaded (refused download), routes 2 and 3 loaded with differences, route 4 loaded with 0 differences. **No network access happens.** Check that no "Downloading" or pip output appears.

### Task 3: Redaction callables and the agent-shaped conversation

- **File**: `scripts/measure_pii_latency.py`
- **Action**: UPDATE
- **Implement**:
  - `_arm_redactors(routes) -> dict[str, Callable[[str], tuple[str, list[str]]]]`:
    - `chat` → `pii_redactor.redact`, unchanged. This is the baseline under today's code (PRD Section 11: "Baseline numbers for today's code").
    - `pattern-lg` → `_redactor(lg, PATTERN_ENTITIES, settings.PII_SCORE_THRESHOLD)`.
    - `pattern-blank` → `_redactor(route.analyzer, PATTERN_ENTITIES, settings.PII_SCORE_THRESHOLD)`, or absent when infeasible.

    `_redactor` mirrors `redact()` lines 49-74, including the empty-text and no-result early returns and the shared `AnonymizerEngine`. Its docstring carries the drift warning. The timing arms all use 0.35, the only threshold that exists today, because the threshold barely moves cost and R1 decides the threshold from the false-positive data, not from timings.
  - `_conversation(size: int) -> list[Message]` is deterministic and exact. It uses `app.models.messages.Message`.
    - **One `system` turn**: a fixed PII-free agent system prompt of about 6,000 characters. Write it in the script as a paragraph tuple repeated to length, in the style of `_ANSWERS`.
    - **Then cycle** these three turns until the total reaches `size`:
      - `user` (prose): the next `prose/` file, header line stripped.
      - `assistant`: a fixed PII-free sentence, then the first 40 lines of the next `code/` file in a ```` ``` ```` fence, then a closing sentence.
      - Tool-shaped, sent as `user` while step 0 refuses `tool` (PRD F1): the next file from `code/` + `json/`, raw and unfenced, as an agent's file read or tool result.
    - **Truncate** the final message so that `sum(len(m.content)) == size` exactly.
  - `_shape(conversation)` returns messages, the largest message, the share of characters in `system`, the share inside fences (compute with a local fence scanner, or count the assistant fence bodies the builder itself inserted; the builder knows them, so prefer that), and how many times each corpus file was used. `--show-corpus` prints it per size. The report quotes it, which is how STORY-001's "say how the corpus is repeated" is met.
  - `_single_message(size)` joins the same conversation's contents with `"\n\n"` into **one** `user` message of exactly `size` characters (F-4 worst case).
- **Mirror**: `scripts/measure_history_latency.py:119-256` for the corpus/filler style, and `:437-445` for the "reproduced, keep in sync" comment.
- **Validate**: `--show-corpus` prints, for each size, a total exactly equal to the size, a first message that is `system`, and turns that alternate as described.

### Task 4: Timing, NLP share, worst case, concurrency (AC 1, 2, 5)

- **File**: `scripts/measure_pii_latency.py`
- **Action**: UPDATE
- **Implement**:
  - `Samples` and `_timed` are copied from `measure_history_latency.py:309-341`, with a comment giving the source.
  - **Warm-up**: `pii_redactor.load()`, build the routes, then one discarded run of every arm at the smallest size.
  - **Per arm × size**: `runs` samples of `_timed(lambda: [redact(m.content) for m in conversation])`. This is the step-6 loop (`_redact_all`'s precedent), because what the pipeline pays is one `redact()` per message. The conversation is built once per size, outside the window.
  - **NLP share**, per analyzer (lg, and the chosen blank route), at 200,000 agent-shaped: `runs` samples of `process_text` over every message versus the matching arm's `redact` samples. Print p50 and `nlp / total`. This answers Risk 2's "how much of today's cost is NLP processing".
  - **Worst case** (code arm only; `pattern-lg` too if blank is infeasible), per size:
    - (i) `_single_message(size)`, unchunked;
    - (ii) the same, chunked: split at the last `\n` at or before each `_CHUNK_CHARACTERS` boundary, analyze each chunk, shift each `RecognizerResult`'s `start`/`end` by the chunk offset, then anonymize the whole text once.

    Before timing, check that the chunked variant finds the same `(start, end, type)` set as the unchunked one on the 200,000 single message. Record `identical` or the difference count. A chunk boundary can split a context window, so this may differ slightly, and the report states it.
  - **Concurrency** (T10), for arms in `{chat, <code arm>} ∩ --arms` and each `c` in `--concurrency`:
    - `ThreadPoolExecutor(max_workers=c)` runs `c × --concurrency-rounds` redactions of the `--concurrency-size` conversation.
    - Wall time is taken over the whole batch, after one warm batch.
    - Report conversations/s and characters/s, and the speed-up relative to `c=1`.

    The docstring says no budget is asserted on it, and why threads do not scale: the GIL, `PIPELINE_MAX_WORKERS`, and the process pool listed in PRD Section 13.
- **Mirror**: `scripts/measure_history_latency.py:478-542`
- **Validate**: `--sizes 40000 --runs 3 --arms pattern-blank --concurrency 1,4 --concurrency-size 40000 --concurrency-rounds 1` completes in well under a minute and prints every table with n=3.

### Task 5: False positives, prose recall and required probes (AC 1; R1, R4 inputs)

- **File**: `scripts/measure_pii_latency.py`
- **Action**: UPDATE
- **Implement**:
  - **Ground truth by value class**, from SOURCES.md *Value classes*. Cite it in a comment. `_is_true_positive(entity_type, span) -> bool`:
    - `EMAIL_ADDRESS`: the whole span matches `^[^@\s]+@example\.(com|org)$`, **case-insensitive** (F-5, `Jane.Doe@Example.com`).
    - `PHONE_NUMBER`: the digits are 10 or 11 long (a leading `1` is allowed) and the number is `NPA-555-01xx`.
    - `CREDIT_CARD`: the digits are in `{4111111111111111, 5555555555554444}`.
    - `IBAN_CODE`: the upper-cased alphanumerics are in `{GB82WEST12345698765432, DE89370400440532013000}`.
    - `US_SSN`: the digits are `219099999`.
    - `PERSON`: normalize the span first:
      - turn `''` and `\'` into `'`;
      - strip surrounding whitespace, quotes and backslashes.

      It is a true positive only if every whitespace-separated word of the result is a word of some `_CAST` name. So `Maria`, `Lopez` and `Patrick O'Brien` count; `ping Priya Raghunathan` and `display_name="Patrick O\'Brien` do not, because a span that swallows code is exactly the damage being counted.
    - `LOCATION`: the span, normalized the same way, is in `_PLACES`. `_PLACES` is a tuple the implementer fills from the city, state and country values in `code/`, **one entry per line with a `file:line` comment**. Everything else counts as a false positive, including timezone IDs, currency codes and identifiers.
  - **`_detections(analyzer, entities, threshold)`** runs over every `code/` file and returns per-type counts of true positives, false positives and structural spans (the span text contains `"`, `'`, `` ` ``, `\` or `\n`), plus the distinct false-positive span texts with their counts and max score.
  - **Rows** to compute:
    - today's analyzer (lg), `settings.pii_entities_list`, at 0.35. This is the AC 1 baseline, "under today's settings".
    - the code arm, `PATTERN_ENTITIES`, at each candidate threshold (PRD 11: "and under `code`").
    - lg with `PERSON` only, at each candidate threshold. This is R4's evidence.
  - **Prose recall** per candidate threshold: for each `prose/` file, check `set(_declared(f)) & set(PATTERN_ENTITIES) <= found`. Report files passed out of total.
  - **Required probes** (R1b), as the module constant `_REQUIRED_PROBES`:
    - the PRD Section 5 story 3 sentence, verbatim: `email the diff to maria.lopez@corp.com and call her on +1 415 555 0134`, expecting `EMAIL_ADDRESS` and `PHONE_NUMBER`;
    - `Ping me on 212-555-0147 when the deploy is done.`, expecting `PHONE_NUMBER`.

    `corp.com` is the PRD's own text, used as a probe string only and never classified. Report found or missed per threshold.
  - **Output**:
    - one table per row group: `| entity | detected | true pos | false pos | structural |`;
    - a threshold table: `| threshold | pattern FP (code/) | pattern TP (code/) | prose recall | required probes |`;
    - then every distinct false-positive span, printed with `repr()` and truncated to 60 characters, so a reviewer can audit the classification.
- **Mirror**: `tests/test_pii_corpus_files.py:47-135` for discovery and the header.
- **Validate**: `--no-timing` prints these tables. `PATTERN_ENTITIES` false positives at 0.35 should be exactly the `078-05-1120` spans (F-5). If other spans appear, inspect them. Fix the classifier only if it is wrong; never fix it to hit the expected number.

### Task 6: Report output, R1-R4 computed

- **File**: `scripts/measure_pii_latency.py`
- **Action**: UPDATE
- **Implement**:
  - A `_report(...)` in `measure_history_latency.py:617-688`'s style, with:
    - the header `--- STORY-003 PII redaction latency and false positives (PRD-012 Section 11, Risk 2) ---`;
    - `key : value` lines: python and platform, CPU count, **presidio-analyzer / presidio-anonymizer / spacy / en_core_web_lg / phonenumbers versions** (from `importlib.metadata.version`, and lg from `meta["version"]`), `PII_*` settings, `CONTEXT_MAX_CHARACTERS`, runs, sizes;
    - the feasibility table;
    - the conversation-shape table;
    - the latency tables in the `| arm | n | min (ms) | p50 (ms) | p95 (ms) |` format, one per size, then the worst-case and concurrency tables;
    - the false-positive tables;
    - the p50/p95 method note and "No latency here is asserted as a pass/fail bound."
  - A final block, **`Decision inputs (rules R1-R4, STORY-003 plan)`**, computes and prints the mechanical outcome of each rule from the data above:
    - `R1 threshold = …`
    - `R2 budget = … ms (2 × p95 …, rounded up to 250 ms)`
    - `R3 limit = …` (branch taken)
    - `R4 PERSON: out|pending STORY-013` (reason)

    The script prints them. The report adopts or annotates them.
- **Validate**: the full run in Task 9 prints the block. A dry run with `--sizes 40000,200000 --runs 3` exercises every branch that its data reaches.

### Task 7: Tests for the pure parts and drift guards

- **File**: `tests/test_measure_pii_latency.py`
- **Action**: CREATE
- **Implement**:
  - Env `setdefault`s, then `import scripts.measure_pii_latency as bench`, as in `tests/test_manage_users_cli.py:1-15`. Importing must not load a spaCy model. Assert `pii_redactor._analyzer` is unchanged by the import.
  - `test_conversation_is_exactly_the_requested_size`, parametrized over `40000, 200000, 400000, 12345`: the lengths sum to `size`, the first role is `system`, every other role is `user` or `assistant`, and there is no `tool` role (step 0 refuses it).
  - `test_single_message_worst_case_is_one_user_turn_of_the_same_size`.
  - `test_true_positive_classification`, a table of hand cases covering each branch of Task 5:
    - `Jane.Doe@Example.com` → TP; `maria.lopez@corp.com` → FP;
    - `+1 415 555 0134` → TP; `078-05-1120` → FP;
    - `Patrick O''Brien'` → TP (after normalization); `ping Priya Raghunathan` → FP; `PENDING_VERIFICATION` → FP;
    - `USD` → FP.
  - `test_nearest_rank_p95`: n=20 gives the 19th sorted value; n=1 gives the value.
  - `test_chunks_are_line_aligned_and_cover_the_text`: the chunks rejoin to the original, and every boundary except the last falls just after a `\n`.
  - Drift guards against the test tree:
    - `bench._CAST == tests.test_pii_corpus_files._CAST`;
    - the discovered `code/` / `prose/` / `json/` lists equal `_CODE_FILES` / `_PROSE_FILES` / `_JSON_FILES`;
    - `bench.PATTERN_ENTITIES` ⊆ `_KNOWN_ENTITIES`.
  - `test_tokenizer_only_route_with_lemmas_boosts_context`: build `_TokenizerOnlySpacyNlpEngine(lemmas=True)` (cheap, no lg) and check that `My phone is 415-555-0134 please.` scores 0.75 and that with `lemmas=False` it scores 0.40. This pins F-2's mechanism for STORY-006. It does **not** load lg.
  - `test_blank_route_by_name_never_downloads`: run route 1 through `_try_routes`' guarded helper with `spacy.cli.download` monkeypatched to record calls. Assert the route is not loaded and that the real download was never invoked.
- **Mirror**: `tests/test_manage_users_cli.py`, `tests/test_pii_corpus_files.py`
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_measure_pii_latency.py -q` is green in a few seconds, because no lg model loads.

### Task 8: Pin versions, then the full suite (AC 3)

- **File**: `requirements.txt`
- **Action**: UPDATE
- **Implement**:
  - Replace the three bare lines with `presidio-analyzer==2.2.364`, `presidio-anonymizer==2.2.364` and `spacy==3.8.16`. These are the versions the script prints in Task 9. If they differ from these, **the printed versions win**, and the report says why.
  - Keep the order and style (`reflex==0.9.6.post1`). Do not pin `en_core_web_lg`: the Dockerfile's `spacy download` picks the model compatible with the pinned spaCy (F-8), and the report records 3.8.0.
  - Do not pin `phonenumbers` (outside AC 3), but record its version in the report: it moves phone scores.
- **Validate**:
  - `.venv/Scripts/python.exe -m pip install -r requirements.txt` changes nothing: compare `pip freeze` against `freeze-before.txt`, and expect no diff.
  - `.venv/Scripts/python.exe -m pip check` is clean.
  - `.venv/Scripts/python.exe -m pytest -q` is green at the Task 0 count plus Task 7's tests. On mass fixture errors, restart `harness-libsql-dev` (story Technical Notes).
  - `.venv/Scripts/python.exe -m pytest tests/test_pii_characterization.py -q` is green, with 25 cases. STORY-002's pins are the proof that pinning moved nothing.

### Task 9: Run the benchmark and write the report (AC 1-5)

- **Action**: run the script, then write the report.
- **Implement**:
  1. On an otherwise idle machine, plugged in, run `.venv/Scripts/python.exe scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs 20 --concurrency 1,4 > <scratchpad>/story003-run.txt`.
     - Run it in the background. The lg arms take about 10 s per 200k conversation, so expect about 30-45 minutes in total.
     - Running arms separately with `--arms` is allowed if every run's header shows the same versions and settings. The report then says so.
  2. Write `.agents/reports/PRD-012-pii-for-code/STORY-003-pii-benchmark-baseline.report.md` in the STORY-002 report's shape (frontmatter, Summary, Tasks, Validation, Files Changed, Deviations, Tests Written, *For later stories*, Acceptance Criteria), plus these sections:
     - **Environment and versions**: the resolved presidio-analyzer, presidio-anonymizer, spacy, en_core_web_lg and phonenumbers versions, and the statement "`requirements.txt` pins exactly these three" (AC 3).
     - **Feasibility (Risk 2)**: the four routes and their errors or parity. Which route STORY-006 should use, with the `lower_as_lemma` recipe and why (F-2). If none is feasible, the fallback and "budget set from `pattern-lg`" (AC 2).
     - **Conversation shape**: how the corpus is cycled per size (STORY-001 ask).
     - **Baseline latency**: p50/p95 per arm and size, pasted from the run output (AC 1, PRD 11 "baseline before any change"). Add the NLP share, the worst case (chunked and unchunked), and concurrency throughput at 1 and 4 with no budget (AC 5).
     - **False positives**: today's analyzer at 0.35 per type (AC 1), the pattern arm per threshold, `PERSON` per threshold, and the distinct spans.
     - **Decisions**: `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE`, the p95 budget at 200,000, and `PERSON` in or out (D7). For each: the rule (R1-R4, quoted), the numbers fed in, the result, and the reasoning (AC 4). Present them as a table STORY-005 can copy: `| setting | value | rule | evidence |`.
     - **For later stories**:
       - **STORY-005**: the three values; the validator dict is `_POSITIVE_LIMIT_DESCRIPTIONS`, not `_RESOURCE_BOUNDS` (F-8).
       - **STORY-006**: the route to use, `lower_as_lemma`, the parity test to carry over, and chunking if R3 required it.
       - **STORY-008**: the structural-span counts.
       - **STORY-013**: the exact command line that reproduces the budget figure, and that the budget is on the agent-shaped conversation.
       - **STORY-014**: the README figures for both profiles.
     - **Observations**: the story's "README note" about restarting libSQL is not in the README (F-8), plus anything surprising in the run.
- **Validate**:
  - Every number in the report appears in `story003-run.txt`; spot-check five.
  - The four AC 4 values are stated with reasons.
  - `git diff --name-only $BASE -- app/ chat_ui/` is empty.
  - Commit: `feat(PRD-012): STORY-003 PII benchmark, baseline and pinned Presidio/spaCy`.

---

## End-to-End Tests

- [ ] `python scripts/measure_pii_latency.py --help` returns quickly and loads no model.
- [ ] `--show-corpus` shows exact sizes 40,000 / 200,000 / 400,000, a leading `system` turn, and no `tool` role.
- [ ] `--no-timing` prints feasibility with 4 routes (route 1 refused, with no network or pip activity), the false-positive tables and the threshold table.
- [ ] A small smoke run (`--sizes 40000 --runs 3 --concurrency 1,4 --concurrency-size 40000 --concurrency-rounds 1`) prints every table and the R1-R4 block.
- [ ] The full run (Task 9) completes. Its output has p50/p95 for each arm × 3 sizes, throughput at concurrency 1 and 4, and today's per-type false positives at 0.35.
- [ ] `pytest tests/test_measure_pii_latency.py -q` is green and fast.
- [ ] After pinning, `pip freeze` is unchanged, the full suite is green, and `tests/test_pii_characterization.py` is green.

---

## Validation

```bash
# libSQL dev server up for the suite only (container harness-libsql-dev); the script needs no DB
.venv/Scripts/python.exe scripts/measure_pii_latency.py --help
.venv/Scripts/python.exe scripts/measure_pii_latency.py --show-corpus
.venv/Scripts/python.exe scripts/measure_pii_latency.py --no-timing
.venv/Scripts/python.exe -m pytest tests/test_measure_pii_latency.py -q
.venv/Scripts/python.exe -m pip install -r requirements.txt && .venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m pytest tests/test_pii_characterization.py -q
.venv/Scripts/python.exe -m pytest -q
git diff --name-only $BASE HEAD -- app/ chat_ui/          # must be empty
```

There is no frontend lint (no frontend change) and no server start (no `app/` change). `from app.main import app` must still import. That is a one-liner smoke test, because `requirements.txt` changed.

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Route 1 downloads or installs something, or exits the process | `spacy.cli.download` is replaced for the attempt, and `BaseException` is caught (F-1). A test pins "never downloads" |
| The blank analyzer "works" but silently scores lower, so the benchmark measures a weaker detector | Parity is measured per route over the probes and the corpora (F-2). The arm uses a route with 0 differences, or reports the gap |
| Timings are noisy on a laptop (thermal, background load) | Warm-up plus a discarded run, n=20, and nearest-rank p95. R2's 2× headroom. The report records CPU count and the platform. Nothing is asserted |
| The headline figure hides the one-big-message case | Worst-case arm, unchunked and chunked (F-4). R3 is decided on the worst case, not the average |
| The false-positive definition is arguable (`NY`, `America`) | Written value-class rules, `_PLACES` entries with `file:line`, and every distinct false-positive span printed for audit |
| Scripts drift from the corpus loader or the redactor | Drift-guard tests (Task 7). "Keep in sync" docstrings on `_redactor` and the copies |
| Pinning changes the resolved environment | The pins equal the installed versions. The `pip freeze` diff is empty. Full suite, and the STORY-002 characterization, as proof |
| A long run (30-45 min) is interrupted | `--arms` lets arms run separately. The report states it if they did |
| R1's expected 0.40 keeps the 4 `078-05-1120` false positives | Accepted by rule: masking a voided SSN shaped like a phone costs little under structure-safe replacement. Missing the PRD's own story-3 phone would fail a user story (F-6) |
| lg is swapped for sm by `.env` | `_lg_analyzer()` asserts `core_web_lg` |

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given `scripts/measure_pii_latency.py --sizes 40000,200000,400000 --runs N`, when it runs on untouched code, then it prints p50/p95 of `redact()` per size over conversations built from `tests/corpora/pii/code/` plus prose filler, and the per-entity-type false-positive count over the code corpus at `PII_SCORE_THRESHOLD=0.35`.
- [ ] Given the script, when it runs with a pattern-only entity list (`EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE`) on (a) the full `en_core_web_lg` analyzer and (b) a tokenizer-only `spacy.blank("en")` analyzer, then both sets of timings are reported, or (b) is reported as infeasible with the Presidio error that shows why.
- [ ] Given the report, when it is read, then it states the resolved `presidio-analyzer`, `presidio-anonymizer` and `spacy` versions, and `requirements.txt` pins exactly those.
- [ ] Given the numbers, when the report concludes, then it fixes `PII_SCORE_THRESHOLD_CODE`, `PII_MAX_CHARACTERS_CODE` and the p95 budget at 200,000 characters, states the reasoning for each, and states whether `PERSON` stays out of `PII_ENTITIES_CODE` (D7).
- [ ] Given concurrency, when the script runs with `--concurrency 1` and `--concurrency 4` in threads, then throughput for both is reported (T10). No budget is asserted on it.
- [ ] All tasks completed
- [ ] Full suite green after pinning (plus `tests/test_pii_characterization.py` unchanged and green)
- [ ] No file under `app/` or `chat_ui/` changed
- [ ] Follows existing patterns (`measure_history_latency.py` style and output, copied-not-imported helpers, env bootstrap before `app.` imports)
