---
story: STORY-001
prd: PRD-012
slug: pii-corpora
title: "PII corpora: code, prose and JSON samples as checked-in files"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-012-pii-for-code        # all stories commit here, no per-story branch
created: 2026-09-23
---

# Plan: PII corpora: code, prose and JSON samples as checked-in files

## Summary

This story adds checked-in data and one loader test. It changes no production code. `tests/corpora/pii/` gets three directories and a provenance file:
- **`code/`**: seven files, all synthetic and each a few hundred lines:
  - five source/config files: `.java`, `.ts`, `.py`, `.yaml`, `.json`
  - two Markdown files: one mixes ```` ``` ```` fences, `~~~` fences and unfenced code with PII in the prose around them; the other ends in an unterminated fence.

  Together they carry every edge case AC 2 names.
- **`prose/`**: human-written messages. Line 1 of each is `# expect: <ENTITY>, <ENTITY>, …`, the PRD-011 `injections/` convention.
- **`json/`**: tool-result-shaped documents. They cover PII in string values and in keys, phone and card numbers as JSON **number** tokens, nesting, and `\\` / `\"` escapes.

`tests/corpora/pii/SOURCES.md` records that every value is synthetic and where each value class comes from.

`tests/test_pii_corpus_files.py` does the following:
- **Existence.** It checks each directory exists and holds what the ACs require.
- **Syntax.** Every JSON file parses with `json.loads` and every `.py` file passes `ast.parse`.
- **Headers.** Every prose file has a readable header over a closed entity vocabulary.
- **Synthetic data.** Every email is on `example.com` / `example.org`.

**It asserts nothing about redaction.** STORY-003, STORY-008 and STORY-013 do that over these files.

## User Story

As a security admin
I want the claims about false positives and masked PII to be tested against checked-in files
So that "it works on code" is evidence a reviewer can read rather than an assertion

## Story Reference

- Story file: `.agents/stories/PRD-012-pii-for-code/STORY-001-pii-corpora.md`
- PRD: `.agents/PRDs/PRD-012-pii-for-code/PRD.md` (Sections 4 *Corpora*, 6.5, 6.6, 7/F11, 11 *MVP definition*, 14 Risks 4-5, 15 D7)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (test data + test only) |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only: a new `tests/corpora/pii/` tree and a new `tests/test_pii_corpus_files.py`. No production module, schema, setting or dependency changes |
| Story | STORY-001 |
| PRD | PRD-012 |
| Epic Branch | `epic/PRD-012-pii-for-code` (commit directly on this branch; **does not exist yet**, see Task 0) |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`. Its description (`.agents/skills/frontend-design/SKILL.md:3`) limits it to "visual design when building new UI". This story adds test data and a pytest module. The story's frontmatter (`skills: []`, "Skills: none applicable") and PRD Section 15 say the same.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Everything below was run against the checked-out tree (`epic/PRD-011-pattern-policy` @ `82b3f3d`, with the Presidio analyzer as `app/services/pii_redactor.py` builds it: presidio-analyzer 2.2.364, spaCy 3.8.16, phonenumbers 9.0.38). None of it is inferred.

### F-1: The epic branch does not exist, and PRD-011 is already in `main`

The PRD says to cut `epic/PRD-012-pii-for-code` from `main` once PRD-010 and PRD-011 are merged (Section 15, *Dependencies*). They are: `origin/main` is at `e10d191` ("Merge pull request #14 … epic/PRD-011-pattern-policy"), and `82b3f3d` is an ancestor of it. The local checkout is two commits behind `origin/epic/PRD-011-pattern-policy`. The PRD-012 PRD and stories are untracked. Task 0 cuts the branch from `origin/main` and commits the PRD and stories first, so this story's commit holds only its own files.

### F-2: A `555-01xx` number is only masked at `code`'s threshold when a context word is near it

Measured scores (threshold 0 and filtered at ≥ 0.3) for `PHONE_NUMBER`:

| Text | Score |
|---|---|
| `Please call Maria Lopez on +1 415 555 0134 tomorrow.` | **0.40** |
| `Call me at (415) 555-0134 or 415-555-0199.` | **0.40** each |
| `Her number is 555-0142.` (7 digits, no area code) | **not detected** |
| `My phone number is +1 415 555 0134.` | 0.75 |
| `phone: (415) 555-0134` / `Mobile: +1-212-555-0147` / `cell 212.555.0182` / `telephone at 415-555-0199` | 0.75 |
| `"phone": 4155550134` / `{"phone": 14155550134}` (JSON number tokens) | 0.75 |
| `String phone = "+1-415-555-0134";` | 0.75 |

Today's `chat` threshold is 0.35, so a 0.40 number is masked. The provisional `code` threshold is 0.5, so a 0.40 number is **not** masked. The context words `phone`, `telephone`, `mobile` and `cell` raise the score to 0.75. `call` does not.

What this means for the files:
- **`prose/`**: every declared phone is written in full (area code or `+1`) **with** one of those context words within a few tokens. Otherwise STORY-013's "masked under both profiles" fails for reasons that have nothing to do with the code under test.
- **`code/`**: carries both shapes on purpose, bare and context-boosted, so that STORY-003's false-positive and threshold numbers have something to separate.
- **7-digit `555-01xx`**: used nowhere as PII, because it is never detected.

### F-3: Test values that are and are not detected

| Value | Result |
|---|---|
| `4111 1111 1111 1111`, `4111111111111111`, `5555 5555 5555 4444` | `CREDIT_CARD` 1.0 |
| `GB82 WEST 1234 5698 7654 32`, `GB82WEST12345698765432`, `DE89370400440532013000` | `IBAN_CODE` 1.0 (and the word `IBAN` itself is a 0.85 `LOCATION` false positive) |
| `219-09-9999` with "social security number" | `US_SSN` 0.85 |
| `078-05-1120` (the Woolworth card) | **not** `US_SSN`; a 0.40 `PHONE_NUMBER` instead |
| `jane.doe@example.com`, `"patrick.obrien@example.org"` | `EMAIL_ADDRESS` 1.0, span stops at the quotes |
| `author = "Jane Doe"`, `Patrick O'Brien reviewed it.`, `Priya Raghunathan` | `PERSON` 0.85 (the apostrophe name is one span) |
| `path = "C:\\Users\\obrien\\notes.txt"`, `class JaneDoeFixture extends BaseFixture {}` | nothing |
| `msg = "He said \"call 415-555-0134\" twice"` | `PHONE_NUMBER` 0.75, span inside the escaped quotes |

The prose corpus uses only values from the detected rows. `078-05-1120` may go in `code/` as a realistic non-match, but never in a `prose/` header.

### F-4: `PERSON` is declared in `prose/` but is off under `code` by default (D7)

The AC requires the prose headers to cover `PERSON`. `PII_ENTITIES_CODE` defaults to pattern types only (PRD Section 6.4). The headers therefore mean **"the entity types present in this file"**. They do not mean "what every profile must mask". STORY-008 and STORY-013 must assert `declared ∩ policy.entities ⊆ found`, not `declared ⊆ found`. The loader test's docstring says so, and so does `SOURCES.md`. Keep `PERSON` in files that also carry at least one pattern entity, so that every prose file is a non-vacuous case under `code` too.

### F-5: Every test needs the libSQL container, pure file tests included

`tests/conftest.py:133` (`_libsql_endpoint`, session-scoped autouse) calls `pytest.exit(returncode=1)` when the endpoint is down. `tests/conftest.py:156` resets the database before **every** test. So `tests/test_pii_corpus_files.py` needs `harness-libsql-dev` up, like the rest of the suite. The container is up (`docker ps`). The test itself takes no DB fixture.

### F-6: A corpus `.py` file must not be named like a test

There is no `pytest.ini`, `pyproject.toml`, `setup.cfg` or `tox.ini`, so pytest's defaults apply and it recurses into `tests/corpora/`. A sample named `test_*.py` or `*_test.py` **would be collected and imported**. The Python sample is `billing_seed.py`. The loader test also asserts that no `.py` under `tests/corpora/pii/` matches the collection globs. The corpus dirs get no `__init__.py`. There is no linter config and CI runs a bare `pytest -q` (`.github/workflows/ci.yml:62`), so nothing lints the sample.

### F-7: Line endings

There is no `.gitattributes`, and `core.autocrlf=true`. The existing corpus is stored `i/lf`. The header regex tolerates a trailing `\r` (the `tests/test_pattern_corpus.py:289-291` precedent). `ast.parse` and `json.loads` accept CRLF. Files are read with `read_text(encoding="utf-8")` and no newline normalisation.

### F-8: The unterminated fence is defined by PRD-011's parser

`strip_code_spans` (`app/services/pattern_detector.py:156-212`) has these rules:
- An opener is up to three spaces, then ≥ 3 backticks or tildes.
- A closer is the **same** character, **at least as long**, alone on its line.
- An unterminated fence runs to end of text.

PRD Section 6.5 has STORY-004 extract exactly this as `strip_fenced_blocks`. The loader test checks the corpus's fence cases through `strip_code_spans`, so "unterminated" means the same thing to the corpus, STORY-004 and STORY-008. It uses no fence scanner of its own. The test only proves the corpus holds the case. It asserts nothing about redaction.

---

## Patterns to Follow

### Discovery, reading, ids
```python
# SOURCE: tests/test_pattern_corpus.py:78-81, 91-105, 118-119
_CORPORA = Path(__file__).resolve().parent / "corpora"

#: Metadata, not samples. Excluded by name so a new sample needs no test edit.
_NOT_SAMPLES = frozenset({"SOURCES.md"})

def _corpus(group: str) -> list[Path]:
    """Every sample in `tests/corpora/<group>/`, sorted, metadata excluded.

    A missing directory raises at collection, which is a loud failure.
    """
    return sorted(
        path
        for path in (_CORPORA / group).iterdir()
        if path.is_file() and path.name not in _NOT_SAMPLES and not path.name.startswith(".")
    )

def _read(path: Path) -> str:
    # No newline normalisation: the test sees the bytes a client would send.
    return path.read_text(encoding="utf-8")

def _ids(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]
```

### Env bootstrap and module docstring
```python
# SOURCE: tests/test_pattern_corpus.py:1-7, 44-49
"""PRD-011 STORY-011/012: the corpora -- code, agent prompts and injections under the built-in policy.

The "safe for code" claim of PRD-011 as evidence rather than assertion
... an empty directory fails the guard tests instead of
parametrizing to nothing (an empty parameter set is a skip, and a skip passes).
"""
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

### Non-parametrized guard with a named failure
```python
# SOURCE: tests/test_pattern_corpus.py:138-154
def test_the_code_corpus_holds_the_five_required_samples():
    assert _CODE_FILES, "tests/corpora/code/ is empty"

    for suffix, construct in _REQUIRED_CODE_SAMPLES:
        matching = [p for p in _CODE_FILES if p.suffix == suffix and construct.search(_read(p))]
        assert matching, f"no {suffix} sample containing {construct.pattern!r}"
    ...
    for path in _CODE_FILES:
        lines = [line for line in _read(path).splitlines() if line.strip()]
        assert len(lines) >= _MIN_NON_BLANK_LINES, f"{path.name}: {len(lines)} lines, a stub"
```

### Header regex tolerant of CRLF; parametrize over files, not parsed cases
```python
# SOURCE: tests/test_pattern_corpus.py:289-311, 337-343
_HEADER = re.compile(r"^# expect: (?P<expect>block|flag) role: (?P<role>user|tool)\s*$")
...
first, _, body = _read(path).partition("\n")
match = _HEADER.match(first)
...
@pytest.mark.parametrize("path", _INJECTION_FILES, ids=_ids(_INJECTION_FILES))
def test_every_injection_sample_declares_its_verdict(path):
    ...  f"{path.name}: line 1 is not {_HEADER_FORMAT!r} (got {first[:80]!r})"
```

### Provenance check
```python
# SOURCE: tests/test_pattern_corpus.py:157-166
sources = _CORPORA / "agent_prompts" / "SOURCES.md"
assert sources.is_file(), "tests/corpora/agent_prompts/SOURCES.md is missing"
provenance = _read(sources)
for path in _PROMPT_FILES:
    assert f"`{path.name}`" in provenance, f"{path.name} has no provenance in SOURCES.md"
```

### Error handling
This story has no production error path. Failure messages start with `{path.name}:` and name **what** is missing, for example `no .py sample with an escaped quote`. They never dump file content. That is the `_describe` convention in `tests/test_pattern_corpus.py:108-111`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/corpora/pii/SOURCES.md` | CREATE | Provenance: every value synthetic, value classes and their sources, the cast of names, the header format and its meaning (F-4), one section per sample |
| `tests/corpora/pii/code/CustomerFixtures.java` | CREATE | JUnit-style fixture builder: `new Customer("Patrick O'Brien", "patrick.obrien@example.org", "+1-415-555-0134")`, `\"` escapes, a `C:\\` path, Javadoc `@author` |
| `tests/corpora/pii/code/contact-directory.ts` | CREATE | TypeScript contact store with seed data, template literals, regex for email validation, test-style `describe/it` block |
| `tests/corpora/pii/code/billing_seed.py` | CREATE | Seed script: dataclasses, dict literals with PII, a raw and a non-raw Windows path, escaped quotes, f-strings, a docstring naming a person. **Not** `test_*.py` (F-6) |
| `tests/corpora/pii/code/staging-values.yaml` | CREATE | Helm-style values: on-call contacts, SMTP sender, alertmanager receivers, plain and double-quoted scalars with `\\` and `\"` |
| `tests/corpora/pii/code/seed-users.json` | CREATE | Fixture JSON a repo would hold (users, roles, nested contact blocks), the `.json` required by AC 1 |
| `tests/corpora/pii/code/onboarding-runbook.md` | CREATE | Prose with PII around ```` ``` ```` and `~~~` fences, plus unfenced code lines (AC 1 Markdown) |
| `tests/corpora/pii/code/handoff-unterminated.md` | CREATE | A handoff note whose last fence is never closed (AC 2) |
| `tests/corpora/pii/prose/*.txt` / `*.md` | CREATE | ≥ 6 messages with the header `# expect: …` (Task 3) |
| `tests/corpora/pii/json/*.json` | CREATE | ≥ 4 tool-result documents (Task 4) |
| `tests/test_pii_corpus_files.py` | CREATE | The loader test (Task 5) |
| `.agents/PRDs/PRD-012-pii-for-code/` and `.agents/stories/PRD-012-pii-for-code/` | COMMIT (already written) | Task 0: tracked on the epic branch before this story's commit |
| `.agents/stories/PRD-012-pii-for-code/STORY-001-pii-corpora.md` | UPDATE | Done by `/plan` Phase 5 (plan link, status); `/implement` fills in the report and commit |
| `.agents/PRDs/PRD-012-pii-for-code/index.md` | UPDATE | Status and plan link (this command); commit SHA later (`/implement`) |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Preflight: cut the epic branch, baseline recorded

- **Action**: git only.
- **Implement** (F-1):
  1. `git fetch origin`.
  2. `git switch -c epic/PRD-012-pii-for-code origin/main`. It should be at `e10d191` or later. Untracked `.agents/` files survive the switch.
  3. Confirm the tree is clean apart from the untracked PRD-012 directories.
  4. Commit `.agents/PRDs/PRD-012-pii-for-code/` and `.agents/stories/PRD-012-pii-for-code/` as `docs(PRD-012): PRD, stories and index`, then this plan file as `docs(PRD-012): STORY-001 plan`, so the story commit holds only its own files.
  5. Confirm `harness-libsql-dev` is up (`docker ps`).
  6. Run the full suite once and record the pass count.
- **Validate**: `git log --oneline -1 origin/main` is an ancestor of `HEAD`. `.venv/Scripts/python.exe -m pytest -q` is green. On mass fixture errors, restart the container rather than bisecting (F-5).

### Task 1: `code/` source and config files (AC 1, AC 2)

- **Files**:
  - `CustomerFixtures.java`, `contact-directory.ts`, `billing_seed.py`, `staging-values.yaml` and `seed-users.json` under `tests/corpora/pii/code/`
- **Action**: CREATE
- **Implement**: realistic files of the kind a coding agent reads. They are not lists of PII.
  - **Size**: 200-350 lines each, with comments, imports, logic, fixtures and tests interleaved as in real code (story Technical Notes: "a benchmark over 10-line toys measures nothing"). The guard floor is 150 non-blank lines.
  - **No expect-header.** Like PRD-011's `code/`, the file begins as ordinary source.
  - Every file contains all three of:
    - An **example email** on `example.com` / `example.org`.
    - A **personal name** from the cast. Use `SOURCES.md` names: Jane Doe, Patrick O'Brien, Maria Lopez, Priya Raghunathan, Kenji Watanabe, Aisha Bello, Tomás Herrera, Zoë Müller-Schmidt.
    - A **phone-shaped number** in the `555-01xx` range: `+1 415 555 0134`, `(212) 555-0147`, `415.555.0199`, `4155550182`, and so on. Mix context-boosted (`phone`, `mobile`, `cell` nearby) and bare shapes (F-2).
  - Also sprinkle in these, which STORY-003 counts:
    - The code-noisy near-misses: identifiers such as `JaneDoeFixture`, `getUserByEmail`, `maria_lopez_id`, `PHONE_REGEX`, class and package names, ISO dates, version strings, UUIDs, order numbers of 10+ digits and port numbers.
    - One test card (`4111111111111111`) and one test IBAN in the Java and Python files.
    - `078-05-1120` once, as a realistic non-match (F-3).
  - **AC 2 edge cases.** Each must appear at least once across the corpus. Put each in at least two languages where natural:
    - **`O'Brien`**: in the Java string `"Patrick O'Brien"` and the Python string `"Patrick O'Brien"`. Also once in a Python **single-quoted** string with an escaped apostrophe: `'Patrick O\'Brien'`. That is the hardest case for structure-safe splitting (PRD Risk 4).
    - **PII right against the quotes**: `"jane.doe@example.com"`, `'maria.lopez@example.org'`, `"+1-415-555-0134"` with no padding, in every language.
    - **Escaped quote**: Java/TS/Python `"He said \"call me on 415-555-0199\" and hung up"`, and a YAML double-quoted scalar with `\"`.
    - **Backslash path**: `"C:\\Users\\pobrien\\Documents\\invoices"` in Java/TS/Python/YAML. Also Python `r"C:\Users\jdoe\exports"` and a UNC path `"\\\\fileserver\\hr\\priya.raghunathan"`.
  - **Language specifics:**
    - `.py` must `ast.parse`. Use only stdlib imports so the file is realistic, even though the test never imports it.
    - `.json` must `json.loads`. It is the repo-fixture flavour of JSON. The tool-result flavour lives in `json/` (Task 4).
    - `.yaml` stays a plain YAML subset. No parse test, because PyYAML is not a declared dependency and this story adds none.
  - **Synthetic only**:
    - no real domains other than `example.com` / `example.org`
    - no real person
    - card numbers from the published test-PAN list
    - IBANs from the published examples: `GB82WEST12345698765432`, `DE89370400440532013000`
- **Validate**: `.venv/Scripts/python.exe -c "import ast,json,pathlib; p=pathlib.Path('tests/corpora/pii/code'); ast.parse((p/'billing_seed.py').read_text(encoding='utf-8')); json.loads((p/'seed-users.json').read_text(encoding='utf-8')); print('ok')"`.

### Task 2: `code/` Markdown files (AC 1 Markdown, AC 2 unterminated fence)

- **Files**: `tests/corpora/pii/code/onboarding-runbook.md`, `tests/corpora/pii/code/handoff-unterminated.md`
- **Action**: CREATE
- **Implement**:
  - **`onboarding-runbook.md`** is 150-250 lines. It is a team runbook that a user pastes into an agent. It contains:
    - Prose paragraphs with PII: "Ping Priya Raghunathan (priya.raghunathan@example.com, mobile +1 212 555 0147) before rotating keys."
    - At least two ```` ```lang ```` fences and at least two `~~~` fences containing PII-bearing code: a `curl` with `-H "X-Contact: ops@example.org"`, a SQL insert, a JSON body.
    - One ```` ```` ```` (four-backtick) fence containing a ```` ``` ```` line as content.
    - **Unfenced code**: shell lines and a Java snippet written directly in the prose with no fence. This is the case PRD Section 6.5 says gets no skipping.
    - One inline backtick span with an email (`` `ops@example.org` ``). PRD D2 says it must still be masked, so STORY-008 wants it here.
  - **`handoff-unterminated.md`** is 60-120 lines:
    - Prose with PII, then one closed fence.
    - Then more prose with PII.
    - Then a final ```` ```yaml ```` opener that is **never closed**. PII follows it to the end of the file, and the file ends inside the fence.
  - **Fence rules**: follow `strip_code_spans` exactly (F-8). Openers are at most three leading spaces followed by three or more backticks or tildes. A closer uses the same character, is at least as long, and sits alone on its line.
- **Validate** (ad-hoc):
  ```bash
  .venv/Scripts/python.exe - <<'EOF'
  import os; os.environ.setdefault("OPENROUTER_API_KEY","x"); os.environ.setdefault("ADMIN_TOKEN","x")
  import pathlib, re
  from app.services.pattern_detector import strip_code_spans as s
  for f in ("onboarding-runbook.md", "handoff-unterminated.md"):
      t = pathlib.Path("tests/corpora/pii/code", f).read_text(encoding="utf-8")
      st = s(t)
      print(f, "emails raw", len(re.findall(r"@example\.(?:com|org)", t)),
            "outside fences/spans", len(re.findall(r"@example\.(?:com|org)", st)),
            "tail blanked", st[len(t.rstrip()) - 1] == "\n")
  EOF
  ```
  The runbook should show emails both inside and outside fences, with `tail blanked False`. The unterminated file should show `tail blanked True`.

### Task 3: `prose/` messages with declared entities (AC 3)

- **Files**: `tests/corpora/pii/prose/`, at least these six:

  | File | Scenario | `# expect:` |
  |---|---|---|
  | `support-refund-request.txt` | Customer email to support asking for a refund | `EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, PERSON` |
  | `payroll-bank-change.txt` | Employee asks HR to change their salary account | `IBAN_CODE, EMAIL_ADDRESS, PERSON` |
  | `vendor-onboarding.md` | Procurement note: vendor contact and remittance details | `PERSON, EMAIL_ADDRESS, PHONE_NUMBER, IBAN_CODE` |
  | `benefits-enrollment.txt` | New hire's benefits form, typed into chat | `PERSON, US_SSN, PHONE_NUMBER` |
  | `agent-task-with-contacts.md` | A developer asking the agent to "email the diff to … and call … on …" (PRD user story 3) | `EMAIL_ADDRESS, PHONE_NUMBER` |
  | `escalation-thread.txt` | Forwarded chain with several people, cards and phones | `PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD` |

- **Action**: CREATE
- **Implement**:
  - **Line 1** is exactly `# expect: ` followed by entity names, comma-and-space separated, from the closed vocabulary: the seven names in `app/config.py:84` (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `IBAN_CODE`, `LOCATION`). Duplicates are not allowed.
  - **Line 2 onward** is the message as a person would type it, 15-60 lines. It is plain prose with **no code fences**, so that everything declared is in prose, where both profiles analyze it.
  - **Values**: use only values from F-3's detected rows. Every phone is written in full, with a context word (`phone`, `mobile`, `cell`, `telephone`) within about three tokens (F-2). `PERSON` names come from the cast and are written as first name plus surname.
  - **Coverage**: together the files cover `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `IBAN_CODE` and `PERSON` (AC 3), plus `US_SSN`.
  - Every file declares at least one non-`PERSON` type (F-4).
  - The header means "types present". It does not mean "types every profile masks" (F-4).
  - `LOCATION` false positives such as the word `IBAN` (F-3) are not declared. The header is a lower bound, not an exact set.
- **Validate** (ad-hoc, data sanity only; the loader test does not do this). The script uses today's analyzer to check two things:
  - every declared type is found at 0.35 (`chat`)
  - every declared non-NER type is found at 0.5 (`code`, provisional)
  ```bash
  .venv/Scripts/python.exe - <<'EOF'
  import os; os.environ.setdefault("OPENROUTER_API_KEY","x"); os.environ.setdefault("ADMIN_TOKEN","x")
  import pathlib
  from app.services.pii_redactor import _get_analyzer
  from app.config import settings
  a = _get_analyzer(); ents = settings.pii_entities_list
  for f in sorted(pathlib.Path("tests/corpora/pii/prose").iterdir()):
      head, _, body = f.read_text(encoding="utf-8").partition("\n")
      declared = {e.strip() for e in head.removeprefix("# expect:").split(",")}
      found = lambda t: {r.entity_type for r in a.analyze(text=body, language="en", entities=ents, score_threshold=t)}
      print(f.name, "chat-missing", declared - found(0.35),
            "code-missing", (declared - {"PERSON", "LOCATION"}) - found(0.5))
  EOF
  ```
  Every line must print two empty sets. Fix the data, not the header, until it does.

### Task 4: `json/` tool-result documents (AC 4)

- **Files**: `tests/corpora/pii/json/`, at least these four:

  | File | Shape | Covers |
  |---|---|---|
  | `crm-contact-search.json` | `{"query": …, "total": …, "results": [{"id": 7, "name": "Maria Lopez", "email": "maria.lopez@example.com", "phone": 14155550134, "address": {…}, "tags": […]}, …]}` with 20-40 records | string values, **phone as number token**, nesting ≥ 3 |
  | `payment-webhook.json` | Stripe-like event: `data.object.card.number: 4111111111111111` (number token), `billing_details`, `metadata`, a `bank_account.iban` string | **card as number token**, IBAN in a string, nesting |
  | `directory-index-by-email.json` | `{"jane.doe@example.com": {"displayName": "Jane Doe", "manager": "patrick.obrien@example.org", "mobile": "+1 415 555 0134"}, …}` | **PII in keys** |
  | `ticket-thread-export.json` | Help-desk thread: messages with `body` strings containing `\"quoted\"` speech, `\\` Windows paths (`C:\\Users\\aisha.bello\\…`), `\n` escapes, and an attachment list | `\\` and `\"` escapes, PII in long strings |

- **Action**: CREATE
- **Implement**:
  - Pretty-printed JSON, 80-300 lines each. Integers that are phones or cards are written without quotes and without a leading `+`, which JSON does not allow.
  - Values follow F-2 and F-3. A number-token phone sits under a `phone` / `mobile` key, which gives the analyzer context (0.75).
  - Also include `true`/`false`/`null`, floats and ordinary integer ids next to the PII. STORY-008's clipping rule 2c drops spans that touch only punctuation or literals, so it needs literals nearby to exercise that.
  - **No top-level scalars.** Every file is an object or an array. PRD Section 6.6 enters JSON-aware mode only when content starts with `{` or `[`.
- **Validate**: `.venv/Scripts/python.exe -c "import json,pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('tests/corpora/pii/json').glob('*.json')]; print('ok')"`

### Task 5: `SOURCES.md`

- **File**: `tests/corpora/pii/SOURCES.md`
- **Action**: CREATE
- **Implement**: mirror `tests/corpora/agent_prompts/SOURCES.md`, which has a title, an opening paragraph naming the test and the stories that consume the corpus, `---`, and then one section per sample. Content:
  - **Opening**:
    - Every value is **synthetic**. No real person's data is in the repository.
    - The consumers are STORY-003 (false-positive counts and latency over `code/`), STORY-008 and STORY-013.
    - `tests/test_pii_corpus_files.py` refuses a sample this file does not name.
  - **Value classes and their provenance**, as a table:
    - emails: RFC 2606 reserved domains `example.com` / `example.org`
    - US phones: NANP `555-0100`-`555-0199`, reserved for fiction
    - cards: published processor test PANs, which are Luhn-valid and never issued
    - IBANs: the ECBS/SWIFT registry example IBANs
    - SSN: `219-09-9999` (published as an example; Presidio accepts it) and `078-05-1120` (the Woolworth card; Presidio rejects it)
    - names: an invented cast, listed
  - **The F-2 and F-3 measurements**, briefly, with the analyzer versions. This explains why every prose phone carries a context word.
  - **The `prose/` header format and its meaning** (F-4): the entity types present in the file, a lower bound. Consumers intersect it with `policy.entities`.
  - **One `## \`<file>\`` section per sample**, each with:
    - **Directory**
    - **Shape**: what it imitates
    - **Contains**: the entity types and the AC 2 edge cases it holds
    - **Why it is here**
- **Validate**: every sample filename appears in backticks. Task 6's test enforces this.

### Task 6: The loader test (AC 5, and guards for AC 1-4)

- **File**: `tests/test_pii_corpus_files.py`
- **Action**: CREATE
- **Implement**:
  - **Docstring.** `"""PRD-012 STORY-001: the PII corpora load -- code, prose and JSON samples as checked-in files.` Then paragraphs saying:
    - Samples are discovered from disk, and an empty directory fails a guard instead of parametrizing to nothing. Quote the "a skip passes" sentence.
    - The prose header format and its "types present, lower bound" meaning (F-4). STORY-008 and STORY-013 intersect it with the policy's entities.
    - **This module asserts nothing about redaction.** It proves only that the files exist, parse and declare. STORY-003, STORY-008 and STORY-013 assert behaviour over them.
    - All data is synthetic, and `SOURCES.md` says where each value class comes from.
  - **Env bootstrap**, as in `test_pattern_corpus.py:46-49`.
  - **Imports**: `ast`, `json`, `re`, `pathlib.Path`, `pytest`, and `strip_code_spans` from `app.services.pattern_detector` (F-8).
  - **Constants and helpers**, mirroring `test_pattern_corpus.py:78-119`:
    ```python
    _PII = Path(__file__).resolve().parent / "corpora" / "pii"
    _NOT_SAMPLES = frozenset({"SOURCES.md"})

    def _corpus(group: str) -> list[Path]: ...   # same body, rooted at _PII
    def _read(path: Path) -> str: ...            # utf-8, no normalisation
    def _ids(paths): return [p.name for p in paths]

    _CODE_FILES = _corpus("code")
    _PROSE_FILES = _corpus("prose")
    _JSON_FILES = _corpus("json")
    _ALL_JSON = [p for p in _CODE_FILES if p.suffix == ".json"] + _JSON_FILES
    _ALL_PY = sorted(_PII.rglob("*.py"))

    #: The Presidio entity names the harness configures (app/config.py:84).
    #: Closed: a header naming anything else fails, so a typo cannot make a
    #: file silently declare nothing.
    _KNOWN_ENTITIES = frozenset({"PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
                                 "US_SSN", "IBAN_CODE", "LOCATION"})
    _REQUIRED_PROSE_ENTITIES = frozenset({"EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
                                          "IBAN_CODE", "PERSON"})
    _HEADER_FORMAT = "# expect: <ENTITY>, <ENTITY>, ..."
    #: `\s*$` absorbs the CR of a CRLF checkout (F-7).
    _HEADER = re.compile(r"^# expect: (?P<entities>[A-Z_]+(?:, [A-Z_]+)*)\s*$")

    _EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
    _SYNTHETIC_DOMAINS = frozenset({"example.com", "example.org"})
    _PHONE_555 = re.compile(r"555[-. ]?01\d\d|\d{3}55501\d\d")   # 555-01xx, separated or packed
    #: The invented cast (SOURCES.md). A code sample must name at least one.
    _CAST = ("Jane Doe", "Patrick O'Brien", "Maria Lopez", "Priya Raghunathan",
             "Kenji Watanabe", "Aisha Bello", "Tomás Herrera", "Zoë Müller-Schmidt")
    _MIN_NON_BLANK_LINES = 150   # "a few hundred lines", floor, not target
    _REQUIRED_CODE_SUFFIXES = (".java", ".ts", ".py", ".yaml", ".json", ".md")

    def _declared(path: Path) -> frozenset[str] | None:
        """The prose header's entities; None when line 1 is not a valid header."""
    ```
  - **Tests.** Banners follow `# --- AC n: … ---`.
    - **AC 1 guard**: `test_the_code_corpus_holds_every_required_kind_of_file`
      - `_CODE_FILES` is non-empty.
      - Each suffix in `_REQUIRED_CODE_SUFFIXES` has at least one file.
      - Every non-`.md` file has at least `_MIN_NON_BLANK_LINES` non-blank lines.
      - Every code file (Markdown included) contains an `_EMAIL` match, a `_PHONE_555` match and a `_CAST` name.
      - Failures are named, for example `f"{path.name}: no cast name"`.
    - **AC 1 Markdown**: `test_the_code_corpus_mixes_fenced_and_unfenced_code_in_markdown`. Some `.md` file must satisfy all of these:
      - It has an opener of each kind: `re.search(r"^ {0,3}```", t, re.M)` and `re.search(r"^ {0,3}~~~", t, re.M)`.
      - It has an email both inside a fence and outside one. Compare the `_EMAIL` count on the raw text with the count on `strip_code_spans(t)`: the stripped count is greater than 0 and less than the raw count.
      - It is not wholly fenced.
    - **AC 2**: one small non-parametrized test per edge case, each naming what is missing:
      - `test_the_code_corpus_has_an_apostrophe_name`: `O'Brien` in a code file.
      - `test_the_code_corpus_has_pii_against_its_quotes`: `re.search(r"[\"'][\w.+-]+@example\.(?:com|org)[\"']", t)` in each of `.java`, `.ts` and `.py`.
      - `test_the_code_corpus_has_an_escaped_quote_and_a_backslash_path`: `\"` in a string, and `re.search(r"[A-Za-z]:\\\\", t)` (a literal `C:\\`) in each of `.java`, `.ts` and `.py`.
      - `test_the_code_corpus_has_an_unterminated_fence`: some `.md` file where `strip_code_spans(t)[len(t.rstrip()) - 1] == "\n"`, so the last character of content is blanked, and where the last opener found by `re.finditer(r"^ {0,3}(`{3,}|~{3,})", t, re.M)` has no matching closer after it. The first condition alone could also be a closed fence at end of file, which is why both are checked.
    - **AC 3**:
      - `test_every_prose_sample_declares_its_entities` is parametrized over `_PROSE_FILES`, the **files** (the `test_pattern_corpus.py:337-343` precedent). It asserts:
        - `_declared(path) is not None`, with the message `f"{path.name}: line 1 is not {_HEADER_FORMAT!r} (got {first[:80]!r})"`.
        - Every entity is in `_KNOWN_ENTITIES`, with the unknown names listed.
        - There are no duplicates.
        - At least one non-`PERSON` type is declared (F-4).
      - `test_the_prose_corpus_covers_the_required_entities` checks that `_PROSE_FILES` is non-empty and that the union of the declared sets is a superset of `_REQUIRED_PROSE_ENTITIES`. The message names the missing types.
    - **AC 4**:
      - `test_every_json_sample_parses` is parametrized over `_ALL_JSON` with `json.loads(_read(path))`, and fails with the `JSONDecodeError` position.
      - `test_the_json_corpus_covers_strings_keys_numbers_nesting_and_escapes` checks that `_JSON_FILES` is non-empty. It then walks the parsed documents with a small recursive `_walk(value, depth)` that yields `(kind, key, value, depth)`. It asserts, each with a named failure:
        - some string value matches `_EMAIL`
        - some dict key matches `_EMAIL`
        - some `int` whose `str()` matches `_PHONE_555`
        - some `int` of 13-19 digits that passes Luhn, using a 5-line `_luhn(n)` helper
        - maximum depth is at least 3
        - some raw file text contains `\\\\` and some contains `\\"`
    - **AC 5 (`.py`)**: `test_every_python_sample_parses`, parametrized over `_ALL_PY`, runs `ast.parse(_read(path), filename=str(path))`. A guard asserts `_ALL_PY` is non-empty.
    - **Collection safety (F-6)**: `test_no_corpus_python_file_is_collectable_as_a_test` asserts that no `_ALL_PY` name matches `test_*.py` or `*_test.py`.
    - **Synthetic data**: `test_every_email_in_the_corpus_is_on_a_reserved_domain`. Over every sample in all three directories, every `_EMAIL` domain is in `_SYNTHETIC_DOMAINS` or is a subdomain of one. On failure, list the file and domain, never the address.
    - **Provenance**: `test_sources_names_every_sample`. `SOURCES.md` exists, and every sample from the three directories appears in it as `` `name` ``.
  - Keep `_walk`, `_luhn` and `_declared` short and in the module, not in a shared helper. No other module needs them yet. STORY-008 or STORY-013 may import `_declared` and the discovery lists from here (the `tests.test_pattern_characterization` import precedent), and the docstring says so.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pii_corpus_files.py -q` is green, with the libSQL container up (F-5).

### Task 7: Prove the guards bite, then the full suite

- **Action**: temporary edits only, all reverted before commit.
- **Implement**: each of the following must make the named test fail, and is then reverted:
  1. Delete line 1 of one prose file. `test_every_prose_sample_declares_its_entities[<file>]` fails and names it.
  2. Change a header entity to `EMAIL` (a typo). The same test fails and lists `EMAIL` as unknown.
  3. Remove every `CREDIT_CARD` from the prose headers. The coverage test fails and names `CREDIT_CARD`.
  4. Delete a closing `}` in `crm-contact-search.json`. `test_every_json_sample_parses[crm-contact-search.json]` fails with the position.
  5. Quote the phone number token in `crm-contact-search.json` and the card in `payment-webhook.json`. The number-token assertions fail.
  6. Add an unclosed `(` to `billing_seed.py`. The `ast.parse` test fails.
  7. Close the final fence in `handoff-unterminated.md`. The unterminated-fence test fails.
  8. Add `bob@corp.com` to a prose file. The reserved-domain test fails and names the file and `corp.com`.
  9. Add `tests/corpora/pii/prose/extra.txt` with a valid header. The provenance test fails until `SOURCES.md` names it. Remove the file.
  10. Copy `billing_seed.py` to `test_billing_seed.py`. The collection-safety test fails. Remove the copy.
- **Validate**:
  - `git status` shows only the intended files.
  - `.venv/Scripts/python.exe -m pytest -q` is green, with the Task 0 baseline count plus this module's cases.
  - `git diff --stat origin/main -- app/ chat_ui/ requirements*.txt` is empty.

### Task 8: Report

- **File**: `.agents/reports/PRD-012-pii-for-code/STORY-001-pii-corpora.report.md` (written by `/implement`)
- **Must contain**:
  - **For STORY-003:**
    - F-2 and F-3: `555-01xx` scores 0.40 without a context word, so a 0.5 `code` threshold misses bare phone numbers.
    - F-3: `IBAN` is itself a `LOCATION` false positive.
    - The corpus size in lines and characters per directory. STORY-003 needs at least 200k characters of agent context and must say how it repeats the corpus to get there.
  - **For STORY-008 and STORY-013 (F-4):** they assert `declared ∩ policy.entities`.
  - **For STORY-008:** where each AC 2 edge case lives, by file and line.
  - The ten guard-bite checks and their observed failures.

---

## End-to-End Tests

`code` has no pipeline behaviour in this story and no HTTP ingress until PRD-014, so the end-to-end check is the loader test plus the data-sanity scripts:

- [ ] `pytest tests/test_pii_corpus_files.py -q` is green. The expected cases are:
  - ≥ 6 prose header cases
  - ≥ 5 JSON parse cases (4 in `json/` + 1 in `code/`)
  - ≥ 1 `.py` parse case
  - about 12 guards
- [ ] Task 2's fence script shows the runbook with emails in and out of fences, and the handoff file ending blanked
- [ ] Task 3's analyzer script prints empty missing-sets for every prose file at both 0.35 and 0.5
- [ ] All ten Task 7 guard-bite checks fail as described and pass after revert
- [ ] The full suite is green
- [ ] `git diff --stat origin/main -- app/ chat_ui/ requirements*.txt` is empty

---

## Validation

```bash
# libSQL dev server must be up (tests/conftest.py:133; container harness-libsql-dev)
.venv/Scripts/python.exe -m pytest tests/test_pii_corpus_files.py -q
.venv/Scripts/python.exe -m pytest tests/test_pattern_corpus.py -q      # PRD-011 corpus unaffected
.venv/Scripts/python.exe -m pytest -q
git diff --stat origin/main -- app/ chat_ui/ requirements*.txt           # must be empty
```

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| A prose phone scores 0.40 and STORY-013 fails under `code` for a data reason | Every prose phone has a context word (F-2). Task 3's script checks at 0.5 before commit |
| `PERSON` in a prose header is read as "must be masked under `code`" | The header means types present (F-4). The docstring, `SOURCES.md` and the report all say consumers intersect with `policy.entities` |
| A corpus `.py` file gets collected or imported by pytest | It is named `billing_seed.py`, with no `__init__.py` in the corpus. A guard test forbids `test_*.py` / `*_test.py` (F-6) |
| Real PII slips in | Emails are restricted to reserved domains by a test. Cards and IBANs come from published test lists. Names come from an invented cast, recorded in `SOURCES.md` |
| The "unterminated fence" case disagrees with STORY-004's parser | Checked through `strip_code_spans`, whose fence pass *is* what STORY-004 extracts (F-8) |
| Toy-sized files make STORY-003's benchmark meaningless | 150-line guard floor, 200-350-line target. Size is reported for STORY-003 (Task 8) |
| A header typo makes a file silently declare nothing | Closed vocabulary. The header test is parametrized over **files**, so a bad header fails |
| CRLF on checkout | Header regex `\s*$`; `ast` / `json` tolerate CRLF (F-7) |
| The PRD-012 docs end up in the story commit | Task 0 commits them separately first |
| libSQL degrades across repeated runs | Restart the container on mass fixture errors (F-5) |

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given `tests/corpora/pii/code/`, when it is listed, then it holds at least one `.java`, `.ts`, `.py`, `.yaml` and `.json` file, each containing example emails, personal names and phone-shaped numbers, and at least one Markdown file mixing fenced (```` ``` ```` and `~~~`) and unfenced code with PII in the prose around the fences.
- [ ] Given the code corpus, when it is read, then it includes the named edge cases: a name with an apostrophe (`O'Brien`), a string literal whose PII sits right against its quotes, an escaped quote and a backslash path inside a string, and an unterminated fence.
- [ ] Given `tests/corpora/pii/prose/`, when each file is read, then it declares its expected entity types in a header (the PRD-011 `injections/` convention), covering at least `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `IBAN_CODE` and `PERSON`.
- [ ] Given `tests/corpora/pii/json/`, when each file is loaded with `json.loads`, then it parses; together they cover PII in string values, PII in keys, a phone and a card number as JSON **number** tokens, nesting, and `\\` / `\"` escapes inside strings.
- [ ] Given a small loader test (`tests/test_pii_corpus_files.py`), when it runs, then every JSON file parses, every `.py` file passes `ast.parse`, and every prose file has a readable expected-entities declaration. It asserts nothing about redaction yet.
- [ ] All tasks completed
- [ ] Full suite green (a test-only story; no server start needed beyond the libSQL dev container)
- [ ] Follows existing patterns (PRD-011 corpus discovery, `SOURCES.md`, header-per-file, guards that fail on empty directories, explicit ids)
