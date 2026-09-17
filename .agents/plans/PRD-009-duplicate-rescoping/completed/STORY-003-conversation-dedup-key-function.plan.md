---
story: STORY-003
prd: PRD-009
slug: conversation-dedup-key-function
title: "dedup_key(user_id, turns): a pure, versioned key over a conversation, with single-turn as the empty-prefix case"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-17
---

# Plan: dedup_key(user_id, turns): a pure, versioned key over a conversation, with single-turn as the empty-prefix case

## Summary

Add three public names to `app/services/duplicate_checker.py`: `DedupTurn` (a structural `typing.Protocol` with `role: str` and `content: str`), `DEDUP_KEY_VERSION = "v1"`, and `dedup_key(user_id, turns) -> str`. They follow PRD-009 Section 6.2 exactly. Two private helpers go with them: `_KEYED_ROLES` (a frozenset) and `_sha256_json` (canonical JSON framing into SHA-256). The key is `_sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(last.content), prefix_hash])`. `prefix_hash` is `""` for a single turn, and otherwise `_sha256_json` over the `[role, content]` pairs, hashed with `hashlib` rather than `hash_prompt`. That keeps the `hash_prompt(` census at exactly one new call site. The function is pure: no I/O, no clock, no settings. Nothing in production calls it yet (STORY-006 does). A new `tests/test_dedup_key.py` covers every F3 property, with a hard-coded digest to catch framing drift. `tests/test_pii_dedup_isolation.py` gets two deliberate, cited edits: the census becomes `duplicate_checker.py: 2`, and a PRD-003 "file unmodified on this branch" guard is narrowed (see finding 1).

Exploration turned up four facts that the story text does not mention:

1. **A PRD-003 guard fails on *any* edit to `duplicate_checker.py`, and PRD-009 Section 6.5 does not list it.** `tests/test_pii_dedup_isolation.py:200-206`, `test_dedup_and_pattern_sources_unmodified_on_this_branch`, is parametrized over `app/services/duplicate_checker.py` and `app/services/pattern_detector.py`. It asserts `git diff --name-only $(git merge-base main HEAD) -- <path>` is empty, working tree included (`_epic_base` / `_changed_since_epic_base`, `:168-197`). It was PRD-003's "RF-6: this epic must not touch either module" pin. On `epic/PRD-009-duplicate-rescoping`, whose merge-base is `57f2d67`, it goes red as soon as Task 1 lands, and it would stay red for STORY-006/007 too. This story does not delete it. It **removes the `duplicate_checker.py` parameter** and keeps `pattern_detector.py`, which PRD-009 does not touch. A comment cites PRD-009 Section 6.5 and explains that PRD-009 owns this module by design. It also names the behavioural pins that still carry PRD-003's RF-6 promise: `test_duplicate_checker_has_no_redaction_dependency`, `test_hash_prompt_is_plain_sha256_of_utf8_text`, the census, and `test_hash_prompt_only_ever_receives_raw_text`. That test's own docstring already says "behavioural pins below still apply". **Flag for the reviewer:** this is a seventh contract-test edit beyond the six rows in Section 6.5. It is recorded in the story report so the PRD table can be amended.
2. **The census is a regex over raw source, not an AST.** `:345` is `re.compile(r"(?<!def )hash_prompt\(")`. It counts comments and docstrings too. The new code must contain the text `hash_prompt(` **exactly once**, in the `dedup_key` return line. Docstrings and comments can say `hash_prompt` without the parenthesis, or refer to `prompt_hash`.
3. **The module's source must not contain `pii`, `redact` or `presidio`, in any case.** `test_duplicate_checker_has_no_redaction_dependency` (`:209-215`) lowercases `inspect.getsource(duplicate_checker)`. The natural docstring ("built from raw text, never redacted text") would fail it. Write "raw text, as `prompt_hash` stores it" instead.
4. **Even a pure test file needs the libSQL dev server.** `tests/conftest.py:106-126` is a session-autouse `_libsql_endpoint` that runs `pytest.exit` if `HARNESS_TEST_LIBSQL_URL` (default `http://127.0.0.1:8080`) does not answer, and `:129-157` resets the DB before every test. There is no opt-out marker and no pytest config file. `tests/test_dedup_key.py` requests no DB fixture, but the container must be up to run it. Per the memory note, mass fixture errors mean restarting the container, not bisecting.

`runtime_checkable` is **not** used. Section 6.2 does not specify it, nobody `isinstance`-checks turns, and a structural Protocol is the point (the story's Technical Notes). `SimpleNamespace` proves this at runtime (Task 3), since Protocols are not enforced at runtime.

## User Story

As a PRD-010 implementer
I want one function that defines the duplicate key over a list of turns
So that multi-turn feeds it the real conversation and nobody writes a second definition of "duplicate".

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-003-conversation-dedup-key-function.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`, Sections 4 (Key function), 5 (story 5), 6.2, 6.5, 7 (F3), 11
- Depends on: STORY-001 (`9abef61`, **done**)
- Blocks: STORY-006

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (pure function, no production caller yet) |
| Complexity | LOW |
| Systems Affected | `app/services/duplicate_checker.py`, `tests/test_dedup_key.py` (new), `tests/test_pii_dedup_isolation.py` |
| Story | STORY-003 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |

---

## Skills In Use

I listed `.agents/skills/` in full. It holds exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story adds a pure hashing function and tests, and renders nothing. |

The story's `skills:` frontmatter is `[]`, and both its Technical Notes and PRD Section 8 reach the same conclusion. **No skill constrains any task below.**

---

## Patterns to Follow

| Category | File:Lines | Pattern |
|----------|------------|---------|
| NAMING | `app/services/duplicate_checker.py:9` | Private module constants use a leading underscore (`_TIMESTAMP_FORMAT`). Public ones such as `DEDUP_KEY_VERSION` are spelled out by the PRD. |
| HASHING | `app/services/duplicate_checker.py:22-23`, `app/services/identity.py:36` | `hashlib.sha256(<str>.encode("utf-8")).hexdigest()` |
| FROZEN DATACLASS | `app/services/identity.py:19` | `@dataclass(frozen=True)` for value objects (used for the test turn) |
| ERRORS | `app/config.py:101-142`, `app/models/schemas.py:58-65` | A `ValueError` for bad input, with an instructive message. app/services has no ValueError precedent, so match Section 6.2's messages literally. |
| TEST PROLOGUE | `tests/test_duplicate_characterization.py:1-27` | Module docstring citing `PRD-009 STORY-00N`, then `os.environ.setdefault(...)` before app imports |
| PURE TESTS | `tests/test_pii_dedup_isolation.py:218-220` | Module-level `test_<behaviour>` functions, no classes, no DB fixture |
| CONTRACT EDIT | `tests/test_query_outcomes_regression.py:1-15` | A pinned test changes in place, with a comment naming PRD-009 and the section |

### Naming / hashing

```python
# SOURCE: app/services/duplicate_checker.py:9, 22-23
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
```

### Error handling

```python
# SOURCE: PRD-009 Section 6.2 (the spec this story implements verbatim)
if not turns:
    raise ValueError("dedup_key needs at least one turn")
if any(t.role not in _KEYED_ROLES for t in turns):
    raise ValueError("dedup_key has no rule for this role (tool turns: PRD-016)")
*prefix, last = turns
if last.role != "user":
    raise ValueError("dedup_key keys on a final user turn")
```

### Tests

```python
# SOURCE: tests/test_pii_dedup_isolation.py:1-4, 218-220
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
def test_hash_prompt_is_plain_sha256_of_utf8_text():
    for text in (_PROMPT_A, _PROMPT_B, _REDACTED_BOTH, "", "acentuación y emoji 🙂"):
        assert hash_prompt(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
```

### Census (the pin this story updates)

```python
# SOURCE: tests/test_pii_dedup_isolation.py:343-355
def test_hash_prompt_call_sites_are_exactly_the_three_audited_ones():
    """A new call site must fail here so it gets re-checked for raw-text input."""
    pattern = re.compile(r"(?<!def )hash_prompt\(")
    ...
    assert census == {
        "app/services/audit_logger.py": 2,
        "app/services/duplicate_checker.py": 1,
    }
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/duplicate_checker.py` | UPDATE | Add `DedupTurn`, `DEDUP_KEY_VERSION`, `_KEYED_ROLES`, `_sha256_json` and `dedup_key`. `check_duplicate` is untouched. |
| `tests/test_dedup_key.py` | CREATE | F3 property tests, ValueError cases, empty-prefix/`prompt_hash` agreement, SimpleNamespace, pinned digest, purity |
| `tests/test_pii_dedup_isolation.py` | UPDATE | Census → `duplicate_checker.py: 2` (cited). Narrow the RF-6 unmodified-file guard to `pattern_detector.py` (cited). |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Add the key function to `duplicate_checker.py`

- **File**: `app/services/duplicate_checker.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: add `import json`, and extend typing to `from typing import Optional, Protocol, Sequence`. Keep alphabetical, stdlib-first grouping.
  - Append **after** `check_duplicate` so existing code keeps its relative order (comments in `tests/test_two_instance_smoke.py:91,709` and `tests/test_query_router.py:193` cite line numbers; see Risks):
    ```python
    class DedupTurn(Protocol):
        role: str
        content: str


    DEDUP_KEY_VERSION = "v1"
    _KEYED_ROLES = frozenset({"system", "user", "assistant"})


    def _sha256_json(value) -> str:
        framed = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(framed.encode("utf-8")).hexdigest()


    def dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str:
        if not turns:
            raise ValueError("dedup_key needs at least one turn")
        if any(t.role not in _KEYED_ROLES for t in turns):
            raise ValueError("dedup_key has no rule for this role (tool turns: PRD-016)")
        *prefix, last = turns
        if last.role != "user":
            raise ValueError("dedup_key keys on a final user turn")
        prefix_hash = "" if not prefix else _sha256_json([[t.role, t.content] for t in prefix])
        return _sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(last.content), prefix_hash])
    ```
  - Keep the role check **before** the final-turn check, as in Section 6.2. A final `tool` turn then raises the PRD-016 message, not the "final user turn" one, and Task 2 asserts that.
  - Short docstrings/comments are optional, matching the module (it has none today). If you add any: the text `hash_prompt(` must not appear (census regex), and neither may `pii`/`redact`/`presidio` in any case (finding 3). A comment that is worth having, if one goes in: `user_id` is inside the key on purpose, as defence in depth (Section 6.2). Do not optimise it out.
- **Mirror**: PRD-009 Section 6.2 verbatim; hashing idiom `duplicate_checker.py:22-23`
- **Validate**: `python -c "from app.services.duplicate_checker import dedup_key, DedupTurn, DEDUP_KEY_VERSION; from types import SimpleNamespace as N; print(dedup_key('juan@empresa.com', [N(role='user', content=\"summarise this week's incidents\")]))"` prints `0b206c744aa7f9f63562d512657e199713e403130a76a0eda9f75c0743484652` (set `OPENROUTER_API_KEY`/`ADMIN_TOKEN` env first if settings import complains)

### Task 2: Create `tests/test_dedup_key.py`

- **File**: `tests/test_dedup_key.py`
- **Action**: CREATE
- **Implement**: the module docstring cites `PRD-009 STORY-003`, Sections 6.2 and 7 (F3). Then the `os.environ.setdefault` prologue, then imports (`dataclasses`, `hashlib`, `inspect`, `json`, `SimpleNamespace`, `pytest`, and from `app.services.duplicate_checker`: `DEDUP_KEY_VERSION`, `dedup_key`, `hash_prompt`, `duplicate_checker` module). Define a local `@dataclass(frozen=True) class _Turn: role: str; content: str` and helpers `_user(c)`, `_assistant(c)`, `_system(c)`. Tests, one per property:
  1. `test_exports_version_v1`: `DEDUP_KEY_VERSION == "v1"`, and `list(inspect.signature(dedup_key).parameters) == ["user_id", "turns"]`.
  2. `test_same_inputs_same_key`: two calls with equal but distinct `_Turn` instances give the same key.
  3. `test_key_for_a_fixed_input_is_pinned`: `dedup_key("juan@empresa.com", [_user("summarise this week's incidents")]) == "0b206c744aa7f9f63562d512657e199713e403130a76a0eda9f75c0743484652"`. Add a second pinned multi-turn case: `[_user("list files"), _assistant("README.md app tests"), _user("yes")]` → `"c63baa9722eff55aed5b2e29db3316b4972843bb43dfb7f7f38cc7068ada4705"`. Include a comment: *these digests change only with a deliberate `DEDUP_KEY_VERSION` bump; a framing change must fail here*. (Both digests were computed independently from the Section 6.2 formula with stdlib `hashlib`/`json`. Recompute once while implementing, but never "fix" the constant to match the code.)
  4. `test_different_user_id_different_key`
  5. `test_single_turn_differs_from_multi_turn_with_same_last_turn`: `[user(x)]` ≠ `[user(y), assistant(z), user(x)]`.
  6. `test_different_prefixes_same_last_turn_differ`: the PRD story-5 example (`hi/hello/yes` vs `list files/…/yes`).
  7. `test_whitespace_is_significant`: `"hello world"` ≠ `"hello world "`.
  8. `test_delimiter_injection_does_not_collide`: `[user('a","b'), user("c")]` vs `[user("a"), user('b","c')]`. Also check that a role/content swap in the prefix (`[user("assistant"), …]` vs `[assistant("user"), …]`) differs.
  9. `test_non_ascii_hashes_as_utf8`: for content `"acentuación y emoji 🙂"` in both the prefix and the last turn, the key equals a recomputation with `json.dumps(..., ensure_ascii=False, separators=(",", ":")).encode("utf-8")`. Also assert it **differs** from the same recomputation with `ensure_ascii=True`, which proves the flag matters.
  10. `test_single_turn_prefix_is_empty_string_and_last_component_is_prompt_hash`: rebuild the expected key as `sha256(json.dumps(["v1", uid, hash_prompt(content), ""], ...))` and compare. That shows the prefix component is `""` and the last-turn component is the `prompt_hash` value.
  11. `test_multi_turn_prefix_component_is_sha256_of_role_content_pairs`: rebuild with a prefix of `sha256(json.dumps([["user", y], ["assistant", z]], ...))`.
  12. `test_any_object_with_role_and_content_works`: `SimpleNamespace(role="user", content="x")` gives the same key as `_Turn("user", "x")`.
  13. `test_accepts_any_sequence`: a tuple and a list of the same turns give the same key.
  14. ValueError cases with `pytest.raises(ValueError, match=...)`:
      - empty list → `match="at least one turn"`
      - final `assistant` turn → `match="final user turn"`
      - final `system` turn → `match="final user turn"`
      - a `tool` turn anywhere (prefix **and** final) → `match="PRD-016"` (parametrize both positions)
      - an unknown role such as `"function"` or `"User"` (case-sensitive) → `match="no rule for this role"`
  15. `test_system_turn_is_keyed_in_the_prefix`: `[system("a"), user("x")]` ≠ `[user("x")]`, and it does not raise.
  16. `test_is_pure`: monkeypatch `duplicate_checker.find_duplicate_timestamp` with a function that raises, and `duplicate_checker.datetime` with a sentinel object that raises on attribute access. Call `dedup_key`; it succeeds. Also assert `"settings" not in inspect.getsource(dedup_key)` and `"datetime" not in inspect.getsource(dedup_key)`.
- **Mirror**: `tests/test_pii_dedup_isolation.py:1-4, 218-220` (prologue, pure test style); `tests/test_openrouter_client.py:80` (`pytest.raises(..., match=)`); `tests/test_duplicate_characterization.py:1-21` (docstring citing PRD/story)
- **Validate**: libSQL dev server up, then `pytest tests/test_dedup_key.py -q`, all green

### Task 3: Update the `hash_prompt` census, deliberately and cited

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE (`:343-355`)
- **Implement**: change `"app/services/duplicate_checker.py": 1` to `2`. Directly above that line, add a comment:
  `# PRD-009 STORY-003 (Section 6.5): the second site is dedup_key's last turn.`
  `# It still receives raw text only -- the caller's own turn content, the same`
  `# string check_duplicate and audit_logger hash; the prefix is hashed with`
  `# hashlib directly, so it adds no site. No production caller exists yet.`
  Leave the test name alone, even though "three" is now stale. The story AC names the test by that name, and renaming it would hide the diff. Add one sentence to the docstring saying the count is four since PRD-009 STORY-003.
  Do **not** touch `test_hash_prompt_only_ever_receives_raw_text` (`:304-340`). It is a runtime spy on `run_query`, and nothing in the pipeline calls `dedup_key` until STORY-006, so `seen` is unchanged.
- **Mirror**: cited in-place contract edit, `tests/test_query_outcomes_regression.py:8-15`
- **Validate**: `pytest tests/test_pii_dedup_isolation.py -q -k "census or call_sites or raw_text or redaction_dependency or plain_sha256"`

### Task 4: Narrow the PRD-003 RF-6 unmodified-file guard, deliberately and cited

- **File**: `tests/test_pii_dedup_isolation.py`
- **Action**: UPDATE (`:200-206`)
- **Implement**: remove `"app/services/duplicate_checker.py"` from the `parametrize` list and keep `"app/services/pattern_detector.py"`. Above the decorator, add:
  `# PRD-009 (Section 6.5; STORY-003 onward) owns duplicate_checker.py by design:`
  `# it adds dedup_key here and later rescopes check_duplicate. PRD-003's RF-6`
  `# promise -- dedup never sees masked text -- stays pinned behaviourally by`
  `# test_duplicate_checker_has_no_redaction_dependency, the hash_prompt census`
  `# and test_hash_prompt_only_ever_receives_raw_text. pattern_detector.py is`
  `# untouched by PRD-009 and stays pinned by source.`
  Keep the test name and docstring. Keep `_epic_base`/`_changed_since_epic_base`, since the remaining parameter still uses them.
- **Mirror**: same as Task 3
- **Validate**: `pytest tests/test_pii_dedup_isolation.py -q`, all green, including the `pattern_detector.py` parameter

### Task 5: Full suite

- **Action**: run only
- **Implement**: with the libSQL dev server running, run `pytest -q`. If there are mass fixture/connection errors, restart the container and rerun (see the memory note). Do not bisect the code.
- **Validate**: full suite green. `git diff --stat` shows only the three files above. `grep -rn "dedup_key(" app/` shows only the definition, with no production caller.

---

## Risks & Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Narrowing the RF-6 guard (Task 4) looks like weakening a PRD-003 pin, and Section 6.5 does not list it | The behavioural pins that guard the actual invariant stay. The comment cites PRD-009. Record the change in the story report as a Section 6.5 addendum for review. **Rejected alternative**: leave it red until PRD-009 merges. That breaks "full suite passes" (AC5) for STORY-003..007. |
| 2 | A docstring containing `hash_prompt(` or `redact` breaks census/isolation tests for a non-code reason | Finding 2/3. Task 1 forbids both strings, and Task 3 runs those tests explicitly. |
| 3 | The pinned digest gets "fixed" to match a buggy implementation | The digests were computed independently from the Section 6.2 formula (outside the module). Task 2 item 3 forbids editing them. Items 10/11 also rebuild the key from first principles. |
| 4 | New imports at the top shift line numbers cited in comments (`test_two_instance_smoke.py:91,709` cite `duplicate_checker.py:28`, `test_query_router.py:193` cites `:32`) | Cosmetic only, and no assertion reads them. `:32` is already stale (it mentions `sqlite3.Error`). Leave them. STORY-007 rewrites `check_duplicate` and is the natural place to refresh them. Mention this in the report. |
| 5 | The final-turn check order drifts from the spec (a final `tool` turn reporting "final user turn") | Keep Section 6.2's order. Task 2 item 14 asserts `match="PRD-016"` for a final `tool` turn. |
| 6 | `test_dedup_key.py` looks runnable offline but exits because of conftest | Finding 4. Validation steps say the container must be up. |

---

## End-to-End Tests

This story has no HTTP surface and no production caller, so "end to end" means the unchanged pipeline stays unchanged:

- [ ] `pytest tests/test_dedup_key.py -q`: every F3 property, ValueError case, pinned digest, SimpleNamespace and purity test passes
- [ ] `pytest tests/test_pii_dedup_isolation.py -q`: census = 2, RF-6 guard green on `pattern_detector.py`, raw-text spy sequence unchanged
- [ ] `pytest tests/test_query_outcomes_regression.py tests/test_duplicate_characterization.py -q`: still green, which shows `/query` behaviour is byte-identical (Phase 1 validation)
- [ ] `pytest tests/test_duplicate_checker.py tests/test_query_router.py -q`: `check_duplicate(prompt)` contract untouched
- [ ] `grep -rn "dedup_key(" app/` → only `def dedup_key(` in `app/services/duplicate_checker.py`

---

## Validation

```bash
# libSQL dev server must be running (tests/conftest.py:26-31)
pytest tests/test_dedup_key.py -q
pytest tests/test_pii_dedup_isolation.py -q
pytest -q
grep -rn "dedup_key(" app/
git diff --stat
```

No linter or formatter is configured in this repo. There is no frontend change and no server-start check beyond the suite's `TestClient` import of `app.main`.

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given `app/services/duplicate_checker.py`, when it is read, then it exports `DedupTurn` (a `typing.Protocol` with `role: str` and `content: str`), `DEDUP_KEY_VERSION = "v1"` and `dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str`, implemented as PRD Section 6.2 specifies. It is a pure function: no I/O, no clock, no settings.
- [ ] Given `dedup_key` with an empty sequence, a final turn whose role is not `user`, or any turn with role `tool` (or any role outside `system`/`user`/`assistant`), when it is called, then it raises `ValueError`, and the `tool` message names PRD-016.
- [ ] Given the key properties in PRD Section 7 F3, when `tests/test_dedup_key.py` runs, then each has a test:
  - the same inputs give the same key, including a hard-coded expected hex digest for one fixed input, so a framing change fails loudly
  - different `user_id` → different key
  - `[user(x)]` ≠ `[user(y), assistant(z), user(x)]`, and two different prefixes with the same last turn differ
  - `"hello world"` ≠ `"hello world "`
  - delimiter-injection pairs such as `[user("a\",\"b"), user("c")]` vs `[user("a"), user("b\",\"c")]` do not collide
  - non-ASCII content hashes as UTF-8 (`ensure_ascii=False`)
- [ ] Given a single-turn conversation, when the key is derived, then its prefix component is the empty string `""`, and its last-turn component equals `hash_prompt(content)`, the value `prompt_hash` stores.
- [ ] Given `test_hash_prompt_call_sites_are_exactly_the_three_audited_ones` in `tests/test_pii_dedup_isolation.py`, when the new call site is added, then the census is updated to `"app/services/duplicate_checker.py": 2`, with a comment citing PRD-009 Section 6.5 and stating why the new site still only receives raw text. No production caller uses `dedup_key` yet, and the full suite passes.
- [ ] All tasks completed
- [ ] RF-6 unmodified-file guard narrowed with citation, and recorded in the report as a Section 6.5 addendum
- [ ] Full test suite passes (the libSQL dev server is required)
- [ ] Follows existing patterns
