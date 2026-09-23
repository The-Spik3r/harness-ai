---
story: STORY-011
prd: PRD-011
slug: code-false-positive-corpus
title: "Code and agent-prompt corpus: the false-positive claim as evidence"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-011-pattern-policy        # all stories commit here, no per-story branch
created: 2026-09-23
---

# Plan: Code and agent-prompt corpus: the false-positive claim as evidence

## Summary

This story adds checked-in files and one test module, and changes no production code. `tests/corpora/code/` holds five plausible source files: Java `@Override`, a TypeScript `override` member, C# `public override`, Kotlin `override fun`, and CSS with `!important` override comments. `tests/corpora/agent_prompts/` holds three real coding-agent system prompts (OpenCode, Codex CLI, Gemini CLI), with provenance in `SOURCES.md`. `tests/test_pattern_corpus.py` discovers both directories from disk and makes these checks:
- Every file passes **clean** (no block **and** no flag) under the built-in `code` profile. Code samples run as a `user` turn; prompts run as both a `system` and a `user` turn.
- The Codex CLI prompt is **blocked** by the built-in `chat` profile on `override`. This is the Risk 5 proof that the corpus is not vacuous.
- A guard test fails if either directory is empty or missing a required sample.
- A timing test measures `inspect()` at the `CONTEXT_MAX_MESSAGES` ceiling and prints the number for the report, with no threshold.

Measuring the candidate prompts against the checked-out detector showed that the PRD overstates its motivating claim (F-1). Prompt selection is built around what was actually measured, not what the PRD says.

## User Story

As an integrating developer
I want the harness's "safe for code" claim backed by real source files and real agent system prompts in the test suite
So that a future change that reintroduces false positives fails CI instead of my requests

## Story Reference

- Story file: `.agents/stories/PRD-011-pattern-policy/STORY-011-code-false-positive-corpus.md`
- PRD: `.agents/PRDs/PRD-011-pattern-policy/PRD.md` (Sections 1, 4 *Corpora*, 6.4, 7/F8, 11 *Corpus criteria* and *Quality indicators*, 14 Risk 5)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (test-only) |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only: a new `tests/corpora/` tree and one new test module. No production module, no schema, no setting, no dependency |
| Story | STORY-011 |
| PRD | PRD-011 |
| Epic Branch | `epic/PRD-011-pattern-policy` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`. Its description (`.agents/skills/frontend-design/SKILL.md:2-3`) scopes it to visual design of UI. This story adds test data and a pytest module and touches no UI. The story's frontmatter agrees (`skills: []`, "Skills: none applicable"), and so does PRD Section 15, *Skills referenced*.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Everything below was run against the checked-out tree (`c2f3412`) or against upstream files fetched on 2026-09-23. None of it is inferred.

### F-1: Most real agent prompts do **not** trip today's list, and the PRD says they do

PRD Section 1 says "close to every request is blocked". Section 6.4 and the built-in policy comment (`app/services/pattern_config.py:224-230`) say "all three keywords appear in real agent system prompts". I fetched candidate prompts and ran them through `BUILT_IN_POLICY` as a `user` turn. I also grepped them for the seven strings as *substrings*, which is the old detector's semantics.

| Prompt (upstream path) | substring hits (old detector) | `chat` / user | `code` / user |
|---|---|---|---|
| OpenCode `packages/opencode/src/session/prompt/anthropic.txt` | none | clean | clean |
| OpenCode `beast.txt`, `gemini.txt`, `codex.txt` | none | clean | clean |
| Aider `aider/coders/editblock_prompts.py` | none | clean | clean |
| **Codex CLI `codex-rs/models-manager/prompt.md`** | `override` (l.134, prose: "user instructions (i.e. AGENTS.md) may override these guidelines") | **block: `override`** | clean |
| **Gemini CLI `packages/core/src/prompts/snippets.ts`** | `override` ×4 in prose (hook-context and conflict-resolution sections), plus `overrides` | block: `override` | clean |
| Cline `sdk/packages/shared/src/prompt/cline.ts` | `override`/`overridePrompt` at l.141-173, but these are **code identifiers**, not prompt text | n/a | n/a |

None of these prompts contains `execute code` or `admin mode`. Two of the six agents trip the list, both on `override` only, and only because of a single sentence of prose each.

Consequences:
- The non-vacuity assertion (AC 3) must use the **Codex CLI** prompt. It is the one static, verbatim prompt that the built-in `chat` profile blocks. If we had picked the three agents the PRD names by example (OpenCode, Cline, Continue), the AC 3 test could not have been written.
- The claim "all three keywords appear" is false for this sample. STORY-013 rewrites the README and must not republish it. This story records the table in its report. It does **not** edit the PRD or the `pattern_config.py` comment: that is production code, and correcting the prose belongs to STORY-013 (same handling as STORY-001's F-1).
- The true, defensible statement is narrower. The word `override` in ordinary prompt prose blocks two major agents' every request under `chat`. The `code` profile passes all six.

### F-2: The `system`-turn case is vacuous by construction, and that is fine

Under the built-in `code` profile, `roles = {"user": "block", "tool": "flag"}` (`pattern_config.py:235-239`). A `system` turn is skipped before any scan (`pattern_detector.py:316-319`), so "passes clean as a `system` turn" cannot fail while the default stays unchanged. The AC asks for it anyway, and the test pins the Section 6.4 decision: if someone adds `system: block` to the built-in `code` profile, those cases start exercising the list. The **`user`-turn case is the real evidence**, because the `injection` list is `scope: everywhere` and scans all of it. The test comment must say this so no reviewer mistakes the `system` cases for proof.

### F-3: An empty parameter set **skips**, and a skip passes

`@pytest.mark.parametrize("path", [])` with no `pytest.ini` produces one *skipped* test ("got empty parameter set"), and the run stays green. AC 4 requires that an empty corpus **fails**, so it needs a separate, non-parametrized guard test per directory. A missing directory already fails at collection (`Path.iterdir()` raises `FileNotFoundError`), which is a loud failure and is acceptable.

### F-4: Every test pays a libSQL reset, including this pure one

`tests/conftest.py:132` (`_libsql_endpoint`, session, autouse) calls `pytest.exit` if the dev server is down. `tests/conftest.py:155` (`_never_the_configured_database`, function, autouse) drops every table before each test. This module has about 20 test cases, so about 20 resets, which is acceptable. **Do not** override those fixtures locally: no other pure module does, and doing so would be a second convention. Start the server first (Task 0). Mass fixture errors mean restart the container, not bisect the code (PRD Section 11, *Quality indicators*).

### F-5: The OpenCode repository moved

`sst/opencode` now 301-redirects to `anomalyco/opencode` (MIT, default branch `dev`). `anthropic.txt` was last changed at `87795384de062abad50f86775e4803e4a23d51fc` (2026-02-10). Record the canonical name in `SOURCES.md`, not the redirect.

### F-6: Provenance and licensing

| Agent | Repo | License | File | Last commit touching it |
|---|---|---|---|---|
| OpenCode | `anomalyco/opencode` @ `dev` | MIT | `packages/opencode/src/session/prompt/anthropic.txt` | `87795384de06…` (2026-02-10) |
| Codex CLI | `openai/codex` @ `main` | Apache-2.0 | `codex-rs/models-manager/prompt.md` | `2cf2a6a844f1…` (2026-06-23) |
| Gemini CLI | `google-gemini/gemini-cli` @ `main` | Apache-2.0 | `packages/core/src/prompts/snippets.ts` | `c647533d6c01…` (2026-09-08) |

Both licenses permit redistribution with attribution. `SOURCES.md` carries each license name, the upstream URL pinned to the **blob SHA of the commit fetched** (not a branch name, which moves), and the fetch date. The implementer re-resolves the SHAs at fetch time. If a SHA differs from the table above, record the one actually fetched.

**The Gemini CLI prompt is reconstructed, not verbatim.** Upstream builds it at runtime in `getCoreSystemPrompt()` (`snippets.ts:136-164`) from about ten `render*()` functions, with interpolated tool names and optional sections. There is no static file to copy. `SOURCES.md` must say so explicitly (story Technical Notes). The OpenCode and Codex CLI files are byte-verbatim.

### F-7: Line endings are harmless

The repo has no `.gitattributes`, and `core.autocrlf=true` on this machine, so corpus files check out with CRLF. `\b` and `\s+` match across `\r\n`. Read with `encoding="utf-8"` and do not normalise: the test should see the bytes a client would send.

### F-8: Use `BUILT_IN_POLICY` directly, not `get_profile()`

The claim under test is about the **default** policy. `get_profile()` reads the module-level `_policy`, which a test calling `load()` replaces (restored by the non-autouse `_reset_policy` fixture, `tests/test_pattern_config.py:62-70`). AC 3 says "built-in `chat`" in so many words. Mirror `tests/test_pattern_detector.py:27-28`: `_CHAT = BUILT_IN_POLICY.profiles["chat"]`, `_CODE = BUILT_IN_POLICY.profiles["code"]`.

### F-9: No test globs would pick up the new files

The file-globbing guards (`tests/test_admin_palette.py:52-57`, `tests/test_admin_shell.py:132`, the `rglob("*.py")` scans in `test_chat_sessions.py:1235` and `test_pii_dedup_isolation.py:392`) are rooted at `app/` or `chat_ui/`. The corpus holds **no `.py` file**, so pytest will never try to collect a sample. Keep it that way: the Aider prompt stays out partly for this reason. The test-name census in `tests/test_pii_redaction_integration.py` only detects *removed* tests, so a new module needs no registration.

---

## Patterns to Follow

### Module prologue and docstring
```python
# SOURCE: tests/test_pattern_detector.py:1-28
"""`inspect()`: the conversation walk under a profile's role matrix.

PRD-011 STORY-008 rewrote this module around `inspect(messages, profile)`. ...
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from dataclasses import dataclass
...
from app.models.messages import Message
from app.services.pattern_config import BUILT_IN_POLICY, PatternList
...
_CHAT = BUILT_IN_POLICY.profiles["chat"]
_CODE = BUILT_IN_POLICY.profiles["code"]
```

### Reading repo files from a test
```python
# SOURCE: tests/test_pattern_config.py:754 and tests/test_admin_palette.py:45,63
_SAMPLE_FILE = Path(__file__).resolve().parents[1] / "examples" / "patterns.yaml"
...
found.extend(sorted(REPO_ROOT.glob(pattern)))
... path.read_text(encoding="utf-8")
```

### Why corpus stays separate from characterization
```python
# SOURCE: tests/test_pattern_characterization.py:55-57
#: Kept inline rather than in `tests/corpora/`: the corpora STORY-011 and
#: STORY-012 add are about the *new* policy, and mixing the two would make the
#: flip set below unreadable.
```

### Asserting a verdict
```python
# SOURCE: tests/test_pattern_characterization.py:160-166 (shape)
result = inspect([Message("user", text)], profile)
assert result.flags == ()
return result.block.pattern if result.block is not None else None
```

### Timing without a threshold
```python
# SOURCE: tests/test_two_instance_smoke.py:276-281 (reports elapsed_ms, prints it)
# Counter-example, NOT to copy: tests/test_query_router.py:311-318 asserts `elapsed < 0.5`.
```

### Section banners, `#:` constants, explicit ids
```python
# SOURCE: tests/test_pattern_config.py (banners), test_pattern_characterization.py (#: + ids=)
# --- AC 4: PATTERN_PROFILE_DEFAULT's cross-check, and get_profile ---
@pytest.mark.parametrize(..., ids=_CASE_IDS)
```

### Error handling
There is no production error path in this story. The test's failure messages must name **the file and the hit** (`list_name`, `pattern`, `role`, `message_index`) so a CI failure points at a line of corpus. They must never dump the file content: the prompts run to 8-21 KB.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/corpora/code/OrderService.java` | CREATE | Java service class with several `@Override` methods (AC 1) |
| `tests/corpora/code/data-table.ts` | CREATE | TypeScript class hierarchy with `override` members (AC 1) |
| `tests/corpora/code/PaymentProcessor.cs` | CREATE | C# abstract base + `public override` members (AC 1) |
| `tests/corpora/code/MainActivity.kt` | CREATE | Android activity with `override fun onCreate` etc. (AC 1) |
| `tests/corpora/code/vendor-overrides.css` | CREATE | Stylesheet with `!important` rules and `/* override ... */` comments (AC 1) |
| `tests/corpora/agent_prompts/opencode-anthropic.txt` | CREATE | OpenCode system prompt, verbatim (AC 2) |
| `tests/corpora/agent_prompts/codex-cli.md` | CREATE | Codex CLI system prompt, verbatim; the AC 3 sample (AC 2, AC 3) |
| `tests/corpora/agent_prompts/gemini-cli-core.md` | CREATE | Gemini CLI core system prompt, reconstructed from `snippets.ts` (AC 2) |
| `tests/corpora/agent_prompts/SOURCES.md` | CREATE | Provenance: agent, version/SHA, date, URL, license, verbatim vs reconstructed (AC 2) |
| `tests/test_pattern_corpus.py` | CREATE | Discovery, guards, clean-pass, non-vacuity, ceiling timing. STORY-012 appends the injection half |
| `.agents/stories/PRD-011-pattern-policy/STORY-011-code-false-positive-corpus.md` | UPDATE | Done by `/plan` Phase 5 (plan link, status); `/implement` fills report/commit |
| `.agents/PRDs/PRD-011-pattern-policy/index.md` | UPDATE | Status + plan link (this command); commit SHA later (`/implement`) |

No `README.md` in `tests/corpora/`: `SOURCES.md` is the only metadata file, and discovery excludes it by name. STORY-012 adds `tests/corpora/injections/` and its own metadata convention.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Preflight: libSQL up, baseline recorded

- **Action**: none to files.
- **Implement**: confirm the branch is `epic/PRD-011-pattern-policy` at or after `c2f3412`, with a clean tree. Start the libSQL dev server (the docker command is in `tests/conftest.py:29-30`). Run the full suite once and record the pass count as the baseline.
- **Validate**: `.venv/Scripts/python.exe -m pytest -q` is green. If there are mass fixture errors, restart the container rather than debugging (F-4).

### Task 1: The code corpus (five files)

- **Files**: the five `tests/corpora/code/*` files above.
- **Action**: CREATE.
- **Implement**: hand-write each file as a **plausible** file: 40-120 lines, realistic imports/package headers, several members, and comments where a real author would put them. None may be a one-line stub. Required constructs (the guard test in Task 4 checks them):
  - Java: `package` line, a class `implements`/`extends` something, **at least two** `@Override` annotations (e.g. `toString`, `equals`, a `run()` from `Runnable`).
  - TypeScript: an abstract base class and a subclass with an `override` method **and** an `override` property/accessor (TS 4.3+ syntax: `protected override render(): void`).
  - C#: `namespace`, an `abstract class` and a derived class with `public override` on a method and on `ToString()`.
  - Kotlin: `class MainActivity : AppCompatActivity()` with `override fun onCreate(savedInstanceState: Bundle?)` and at least one more `override fun`.
  - CSS: at least three `!important` declarations, and comments that use the **whole word** `override` (e.g. `/* override the vendor focus ring; their selector wins on specificity */`). Also mention `overrides` once, to show the suffix family.
- **Constraints** (so the corpus tests what it claims):
  - No file may contain any of the four injection phrases (`ignore previous instructions`, `forget everything`, `show system prompt`, `reveal password`). Otherwise it would legitimately block under `code`.
  - Every file must contain `override` as a whole word **outside** any backtick span, so the built-in `chat` profile blocks it. This is asserted in Task 6 and makes the code corpus non-vacuous too.
  - No `.py` files (F-9).
- **Validate**: the ad-hoc check below prints `code: None []` and `chat: <something> ` for every file:
  ```bash
  .venv/Scripts/python.exe -c "import pathlib;from app.models.messages import Message as M;from app.services.pattern_config import BUILT_IN_POLICY as P;from app.services.pattern_detector import inspect as I
  for f in sorted(pathlib.Path('tests/corpora/code').iterdir()):
      t=f.read_text(encoding='utf-8');c=I([M('user',t)],P.profiles['code']);h=I([M('user',t)],P.profiles['chat'])
      print(f.name,'code:',c.block,list(c.flags),'chat:',h.block and h.block.pattern)"
  ```

### Task 2: Fetch the three agent prompts

- **Files**: `tests/corpora/agent_prompts/{opencode-anthropic.txt,codex-cli.md,gemini-cli-core.md}`.
- **Action**: CREATE.
- **Implement**:
  1. Resolve each file's current commit SHA via the GitHub API. There is no `gh` on this machine, so use curl:
     `curl -sf "https://api.github.com/repos/<owner>/<repo>/commits?path=<path>&sha=<branch>&per_page=1"` and take `.sha` and `.commit.committer.date`.
  2. **OpenCode** (verbatim): `curl -sfL -o tests/corpora/agent_prompts/opencode-anthropic.txt https://raw.githubusercontent.com/anomalyco/opencode/<SHA>/packages/opencode/src/session/prompt/anthropic.txt`
  3. **Codex CLI** (verbatim): `curl -sfL -o tests/corpora/agent_prompts/codex-cli.md https://raw.githubusercontent.com/openai/codex/<SHA>/codex-rs/models-manager/prompt.md`
  4. **Gemini CLI** (reconstructed): fetch `packages/core/src/prompts/snippets.ts` at its SHA into the **scratchpad**, not the repo. Assemble `gemini-cli-core.md` in `getCoreSystemPrompt()` order (`snippets.ts:136-164`): preamble, core mandates, hook context (enabled), primary workflows (non-plan variant), operational guidelines, sandbox (the default/none branch), git repo. Copy each renderer's template-literal text. Replace every `${...}` tool-name interpolation with the literal default tool name it resolves to upstream (e.g. the shell/read-file tool constants), drop sub-agents/skills/task-tracker/yolo/user-memory sections, and keep the rest word for word. Record every such choice in `SOURCES.md`.
  - Do not edit the verbatim files. Do not strip trailing newlines. Do not "fix" them.
- **Validate**:
  - Re-run the Task 1 one-liner against `tests/corpora/agent_prompts` (skip `SOURCES.md`). It must print `code: None []` for all three and `chat: override` for **`codex-cli.md`** (F-1).
  - Also run with `Message('system', ...)`: `code: None []`.
  - If the Codex prompt no longer blocks under `chat` (upstream edited the sentence), pin the older SHA `2cf2a6a844f1fc2ddd489c8a67fa8bc2f59a6f3d` that was measured here, and say so in `SOURCES.md`.

### Task 3: `SOURCES.md`

- **File**: `tests/corpora/agent_prompts/SOURCES.md`
- **Action**: CREATE
- **Implement**: one section per prompt with these fields: **Agent**, **Corpus file**, **Upstream** (repo, path, full commit SHA, a blob URL pinned to that SHA), **Fetched** (2026-09-23 or the actual date), **License** (MIT / Apache-2.0), **Fidelity** (`verbatim` or `reconstructed`, and for Gemini CLI the exact assembly choices from Task 2.4), and **Why it is here** (one line). For Codex CLI, that line says it is the Risk 5 sample: the `chat` profile blocks it on `override`, from the sentence "user instructions (i.e. AGENTS.md) may override these guidelines".
  Add a short closing section, *What this sample shows*, with the F-1 table in summary. Six agents were checked, two trip the keyword list, both on `override` only, and none contains `execute code` or `admin mode`. The reason is so the next person to extend the corpus does not repeat the PRD's claim.
- **Validate**: every corpus file name except `SOURCES.md` appears in it (asserted in Task 4).

### Task 4: Test module skeleton, discovery, and the guards (AC 4, plus AC 1/2 shape)

- **File**: `tests/test_pattern_corpus.py`
- **Action**: CREATE
- **Implement**:
  - Docstring: `"""PRD-011 STORY-011: the false-positive corpus -- code and agent prompts under the built-in policy.` It then covers:
    - What passes clean means: no block **and** no flag.
    - That files are discovered from disk (PRD Section 7/F8).
    - That the `system`-turn cases are vacuous by construction (F-2).
    - That STORY-012 appends the injection half to this module.
    - That characterization lives elsewhere on purpose (`test_pattern_characterization.py:55-57`).
  - Prologue as in *Patterns to Follow*.
  - Constants:
    ```python
    _CORPORA = Path(__file__).resolve().parent / "corpora"
    #: Metadata, not samples. Excluded by name so a new sample needs no test edit.
    _NOT_SAMPLES = frozenset({"SOURCES.md"})

    def _corpus(group: str) -> list[Path]:
        return sorted(p for p in (_CORPORA / group).iterdir()
                      if p.is_file() and p.name not in _NOT_SAMPLES and not p.name.startswith("."))

    _CODE_FILES = _corpus("code")
    _PROMPT_FILES = _corpus("agent_prompts")
    _CHAT = BUILT_IN_POLICY.profiles["chat"]
    _CODE = BUILT_IN_POLICY.profiles["code"]
    #: The Risk 5 sample (F-1): the one verbatim prompt the built-in `chat` profile blocks.
    _NON_VACUOUS_PROMPT = "codex-cli.md"
    ```
  - Helper `_read(path) -> str` (utf-8, no normalisation, F-7). Helper `_describe(result) -> str` renders hits as `list/pattern/role/#index`, never content.
  - Guard tests (not parametrized, F-3):
    - `test_the_code_corpus_holds_the_five_required_samples`: the directory is non-empty. For each required construct there is at least one file whose suffix and content match: `.java` + `@Override`; `.ts` + regex `\boverride\s+(?:\w+\s*\(|get\b|set\b|readonly\b|\w+\s*[:=])`; `.cs` + `public override`; `.kt` + `override fun`; `.css` + `!important` + `\boverride\b` inside `/* ... */`. Each file has **≥ 30 non-blank lines** ("a plausible file, not a one-line stub").
    - `test_the_agent_prompt_corpus_holds_three_prompts_with_provenance`: `len(_PROMPT_FILES) >= 3`. `SOURCES.md` exists, and every sample's file name occurs in it. `_NON_VACUOUS_PROMPT` is among the samples.
  - ids: `ids=[p.name for p in ...]`.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pattern_corpus.py -q -k "holds"` shows 2 passed.

### Task 5: Clean-pass tests (AC 1, AC 2)

- **File**: `tests/test_pattern_corpus.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  # --- AC 1: every code sample passes clean under `code` as a user turn ---
  @pytest.mark.parametrize("path", _CODE_FILES, ids=[p.name for p in _CODE_FILES])
  def test_code_sample_passes_clean_under_code_as_a_user_turn(path):
      result = inspect([Message("user", _read(path))], _CODE)
      assert result.block is None, f"{path.name}: blocked by {_describe(result)}"
      assert result.flags == (), f"{path.name}: flagged by {_describe(result)}"

  # --- AC 2: every agent prompt passes clean under `code`, as system and as user ---
  # The `system` cases cannot fail under the built-in `code` profile, because it
  # does not inspect `system` (PRD-011 Section 6.4, F-2). They pin that
  # decision. The `user` cases are the evidence.
  @pytest.mark.parametrize("role", ["system", "user"])
  @pytest.mark.parametrize("path", _PROMPT_FILES, ids=[p.name for p in _PROMPT_FILES])
  def test_agent_prompt_passes_clean_under_code(path, role): ...
  ```
  Both asserts are separate so a failure says which one tripped. `truncated` is not asserted, because it is not a verdict. Do not pass `max_scan_characters`: these are verdict tests, and the ceiling (1,000,000) is far above every file anyway.
- **Validate**: `pytest tests/test_pattern_corpus.py -q` shows 5 + 6 + 2 passed.

### Task 6: Non-vacuity (AC 3, PRD Risk 5)

- **File**: `tests/test_pattern_corpus.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  # --- AC 3: the corpus is not vacuous (PRD-011 Risk 5) ---
  def test_an_agent_prompt_is_blocked_by_the_built_in_chat_profile():
      """The proof the corpus is not vacuous (PRD-011 Section 14, Risk 5).

      The Codex CLI system prompt passes clean under `code` (above) and is
      blocked under the built-in `chat` profile, the policy every request
      got before PRD-011. The catch is `override`, from the prose line
      "user instructions (i.e. AGENTS.md) may override these guidelines".
      So the `code` profile changes a real verdict on a real prompt, not a
      sample chosen because it happens to pass.
      """
      result = inspect([Message("user", _read(_CORPORA / "agent_prompts" / _NON_VACUOUS_PROMPT))], _CHAT)
      assert result.block is not None
      assert (result.block.list_name, result.block.pattern, result.block.role) == ("keywords", "override", "user")
  ```
  Also add the cheap companion for the code half. It is not in the AC, but it is the same argument, and Task 1 guaranteed it:
  ```python
  @pytest.mark.parametrize("path", _CODE_FILES, ids=...)
  def test_code_sample_is_blocked_by_the_built_in_chat_profile(path):
      # Same Risk 5 argument for the code half. `@Override` is a word-boundary
      # match (PRD-011 Section 6.2), so word matching alone would not have
      # passed this corpus. The `code` profile not loading `keywords` does.
      result = inspect([Message("user", _read(path))], _CHAT)
      assert result.block is not None and result.block.list_name == "keywords", path.name
  ```
- **Validate**: temporarily point `_NON_VACUOUS_PROMPT` at `opencode-anthropic.txt`. The AC 3 test must fail. Revert.

### Task 7: Inspection cost at the `CONTEXT_MAX_MESSAGES` ceiling (AC 5)

- **File**: `tests/test_pattern_corpus.py`
- **Action**: UPDATE
- **Implement**: `test_inspection_cost_at_the_context_max_messages_ceiling(record_property)`:
  - `n = settings.CONTEXT_MAX_MESSAGES` (100) and `share = settings.CONTEXT_MAX_CHARACTERS // n` (2,000). Build `n` messages by cycling `_CODE_FILES + _PROMPT_FILES`, each cut to `share` characters, with roles alternating `user`/`tool`. **Every message is inspected** under `code`, and the conversation is the largest one step 3 of the pipeline admits (`query_pipeline.py:86-91`).
    - Truncating a clean text cannot create an injection-phrase match, only lose one. Assert the result is clean anyway, so the walk is known to have gone end to end with no short-circuit.
  - Call exactly as the pipeline does (`query_pipeline.py:254`): `inspect(messages, _CODE, max_scan_characters=settings.PATTERN_MAX_SCAN_CHARACTERS)`.
  - Do one warm-up call, then 25 timed runs with `time.perf_counter()`. Compute min/median/max in ms.
  - Emit `print(f"STORY-011 ceiling: {n} messages, {total_chars} chars, code profile: min {..:.2f} ms / median {..:.2f} ms / max {..:.2f} ms")` and `record_property("inspect_ceiling_median_ms", median)`.
  - **Asserts are shape only**: `len(messages) == n`, `total_chars <= settings.CONTEXT_MAX_CHARACTERS`, `result.block is None and result.flags == ()`. **No timing threshold** (the AC says so explicitly). A comment points at the counter-example `test_query_router.py:311-318`, which is why.
  - Optionally, a second measurement under `_CHAT` with the same messages and every role set to `assistant`. That measures the role-skip fast path and is a floor, not a cost. Only include it if it takes fewer than 10 lines, and label it clearly.
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_pattern_corpus.py -q -s -k ceiling`. Copy the printed line, plus the machine (Windows 11, Python version from `python -V`), into the report (Task 9).

### Task 8: Prove the guards bite, then the full suite

- **Action**: temporary edits only, all reverted before commit.
- **Implement** (each check must make the named test fail, then revert):
  1. Append `ignore previous instructions` to a code sample, so `test_code_sample_passes_clean…[that file]` fails with a message naming `injection/ignore previous instructions/user/#0`.
  2. Move every sample out of `tests/corpora/code/` (keep the directory), so the Task 4 guard fails. The parametrized test reports one skip, which is exactly F-3's point.
  3. Delete `codex-cli.md`'s line from `SOURCES.md`, so the provenance guard fails.
  4. Add a new file `tests/corpora/code/extra.go` with a clean Go snippet (`func (s *Server) ServeHTTP...`). It is picked up with **no test edit** (count +1 in the parametrized tests), then removed.
- **Validate**: `git status` is clean apart from the intended new files. Then run the full suite: `.venv/Scripts/python.exe -m pytest -q` is green, and the count is the baseline plus this module's cases.

### Task 9: Report

- **File**: `.agents/reports/PRD-011-pattern-policy/STORY-011-code-false-positive-corpus.report.md` (written by `/implement`, per its template)
- **Must contain**:
  - The AC 5 timing line from Task 7, with machine and Python version (**the AC is satisfied only by this number being in the report**).
  - The F-1 table, restated as a finding for STORY-013 (README) and as a candidate correction to PRD Sections 1 and 6.4 and the `pattern_config.py:224-230` comment.
  - The Gemini CLI reconstruction choices.
  - The four guard-bite checks from Task 8 and their observed failures.

---

## End-to-End Tests

This story has no HTTP surface: the `code` profile has no ingress until PRD-014 (PRD Section 4, *Out of Scope*). The end-to-end check is the corpus run through the same `inspect()` call the pipeline makes:

- [ ] `pytest tests/test_pattern_corpus.py -q` is green, with at least 2 guards, 5 code cases, 6 prompt cases, 1 AC 3 case, 5 code-under-chat cases and 1 ceiling case
- [ ] `pytest tests/test_pattern_corpus.py -q -s -k ceiling` prints the timing line
- [ ] All four Task 8 guard-bite checks fail as described, then pass after revert
- [ ] Full suite green; `test_query_router.py`, `test_integration.py`, `test_query_outcomes_regression.py`, `test_pattern_characterization.py` untouched (`git diff --stat` shows only new files plus story/index/report)

---

## Validation

```bash
# libSQL dev server must be up (tests/conftest.py:29-30)
.venv/Scripts/python.exe -m pytest tests/test_pattern_corpus.py -q
.venv/Scripts/python.exe -m pytest tests/test_pattern_corpus.py -q -s -k ceiling
.venv/Scripts/python.exe -m pytest -q
git diff --stat c2f3412 -- app/ chat_ui/ requirements*.txt   # must be empty
```

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Upstream edits the Codex CLI sentence, so a re-fetch loses the AC 3 sample | Files are pinned by SHA in `SOURCES.md` and checked in, so CI never re-fetches. Task 2 names the measured fallback SHA |
| The Gemini CLI reconstruction drifts from what the agent really sends | Labelled `reconstructed` in `SOURCES.md` with every assembly choice. The two verbatim prompts carry the claim, and the reconstructed one adds breadth |
| A hand-written code sample is shaped to pass | The guard test pins the required constructs. Task 6 asserts every code sample **is** blocked under `chat`, so none passes because it avoids the vocabulary |
| The `system`-turn cases give false comfort | F-2 comment in the test and docstring. The `user`-turn cases are the evidence |
| An empty corpus passes as one skip | Non-parametrized guards (F-3), proven by Task 8.2 |
| Redistribution of third-party prompts | MIT and Apache-2.0 permit it with attribution. `SOURCES.md` carries license and upstream URL |
| A timing assertion flakes in CI | None is made. The number goes to the report (AC 5) |
| libSQL degradation across repeated runs | Restart the container on mass fixture errors (F-4) |
| STORY-012 conflicts in the shared module | Helpers (`_CORPORA`, `_corpus`, `_read`, `_describe`) are module-level and group-agnostic. STORY-012 appends a banner section and reuses them |

---

## Acceptance Criteria

(Copied from story `STORY-011`)

- [ ] Given `tests/corpora/code/`, when the suite runs, then it holds at least a Java file with `@Override`, a TypeScript file with an `override` member, a C# file with `public override`, a Kotlin file with `override fun`, and a CSS file with `!important` override comments. Each is a plausible file, not a one-line stub, and every one of them passes clean under the `code` profile as a `user` turn.
- [ ] Given `tests/corpora/agent_prompts/`, when the suite runs, then it holds three real coding-agent system prompts with provenance recorded in `SOURCES.md` (agent, version or date, where it came from), and each passes clean under the `code` profile in a `system` turn **and** in a `user` turn.
- [ ] Given at least one agent prompt, when it is run through the **built-in `chat`** profile as a `user` turn, then it is blocked. This is asserted, with a comment explaining that it is the proof the corpus is not vacuous (PRD Risk 5). The test names the pattern that catches it.
- [ ] Given every corpus file, when the test parametrizes over the directory, then files are discovered from disk rather than listed in the test body, so adding a sample needs no test edit, and an empty corpus directory fails rather than passing vacuously.
- [ ] Given the `CONTEXT_MAX_MESSAGES` ceiling, when a conversation of that many corpus messages is inspected, then the elapsed time is measured and recorded in this story's report (PRD Section 11, Quality indicators). It is a number in the report, not an assertion with a threshold in CI.
- [ ] All tasks completed
- [ ] Full suite green (no frontend in scope; no server start needed. This story touches no app code)
- [ ] Follows existing patterns (prologue, `BUILT_IN_POLICY` profiles, `#:` constants, explicit ids, banners)
