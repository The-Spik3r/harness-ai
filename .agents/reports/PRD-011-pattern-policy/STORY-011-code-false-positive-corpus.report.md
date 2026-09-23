---
story: STORY-011
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-011-code-false-positive-corpus.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: 5685712
status: COMPLETE
completed: 2026-09-23
---

# Implementation Report — STORY-011: Code and agent-prompt corpus: the false-positive claim as evidence

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-011-code-false-positive-corpus.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `5685712`

## Summary

The story is test-only; no production file changed (`git diff c2f3412 -- app/ chat_ui/` is empty).

`tests/corpora/code/` holds five hand-written, plausible source files (58-84 non-blank lines each):
- Java with six `@Override`s
- TypeScript with an `override` property, accessor and methods
- C# with `public override`
- Kotlin with `override fun`
- CSS with `!important` rules and `/* override ... */` comments

`tests/corpora/agent_prompts/` holds three real coding-agent system prompts:
- OpenCode (verbatim, MIT)
- Codex CLI (verbatim, Apache-2.0)
- Gemini CLI (rendered by upstream's own code, Apache-2.0)

`SOURCES.md` records each prompt's commit SHA, URL, license and fidelity.

`tests/test_pattern_corpus.py` discovers both directories from disk and makes these checks:
- Every file passes **clean** under the built-in `code` profile: no block and no flag, each asserted separately.
- The Codex CLI prompt is blocked by the built-in `chat` profile on `keywords`/`override`. This is the PRD Risk 5 proof.
- Guard tests fail on an empty corpus, a missing AC 1 construct, a stub, or a prompt with no provenance.
- A timing test measures `inspect()` at the `CONTEXT_MAX_MESSAGES` ceiling, with no threshold.

## AC 5: inspection cost at the `CONTEXT_MAX_MESSAGES` ceiling

| | |
|---|---|
| Conversation | 100 messages (`CONTEXT_MAX_MESSAGES`), 196,856 characters (≤ `CONTEXT_MAX_CHARACTERS` 200,000). Each message is one corpus file cut to 2,000 characters; the CSS sample is shorter, hence < 200,000 |
| Roles | alternating `user` / `tool`, so **every** message is inspected under `code`; no hit, so the walk runs to the end |
| Call | `inspect(messages, BUILT_IN_POLICY.profiles["code"], max_scan_characters=settings.PATTERN_MAX_SCAN_CHARACTERS)`, identical to `query_pipeline.py:254` |
| Runs | 1 warm-up + 25 timed (`time.perf_counter`) |
| **Result** | **min 7.308 ms / median 7.391 ms / max 8.830 ms** |
| Machine | Windows 11 Pro 10.0.26200, Python 3.11.9 |

A worst-case send pays about 7.4 ms for pattern inspection under `code`. Reproduce with `pytest tests/test_pattern_corpus.py -q -s -k ceiling`. The median is also written to the JUnit property `inspect_ceiling_median_ms`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: libSQL restarted, baseline 2541 passed / 26 skipped | — | ✅ |
| 1 | Code corpus, five files | `tests/corpora/code/*` | ✅ |
| 2 | Fetch/render three agent prompts, pinned by SHA | `tests/corpora/agent_prompts/*` | ✅ |
| 3 | Provenance | `tests/corpora/agent_prompts/SOURCES.md` | ✅ |
| 4 | Module, discovery, guards | `tests/test_pattern_corpus.py` | ✅ |
| 5 | Clean-pass tests (AC 1, AC 2) | `tests/test_pattern_corpus.py` | ✅ |
| 6 | Non-vacuity (AC 3) + code-half companion | `tests/test_pattern_corpus.py` | ✅ |
| 7 | Ceiling timing (AC 5) | `tests/test_pattern_corpus.py` | ✅ |
| 8 | Guard-bite checks, full suite | — | ✅ |
| 9 | This report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | n/a: no `frontend/` npm project; no UI touched |
| `tests/test_pattern_corpus.py` | ✅ 20 passed |
| Full suite | ✅ 2561 passed, 26 skipped (baseline 2541 + 20 new; skips unchanged) |
| Production diff since `c2f3412` (`app/`, `chat_ui/`) | ✅ empty |
| E2E (plan checklist) | ✅ 4/4 |

### Guard-bite checks (Task 8, all temporary, all reverted)

| # | Mutation | Observed |
|---|---|---|
| 1 | Appended `// ignore previous instructions` to `MainActivity.kt` | `test_code_sample_passes_clean_under_code_as_a_user_turn[MainActivity.kt]` FAILED (the chat companion also failed on it, because the block came from `injection`, not `keywords`) |
| 2 | Moved every sample out of `tests/corpora/code/` | `test_the_code_corpus_holds_the_five_required_samples` FAILED. The parametrized tests reported **2 skipped**, which is exactly why the guard exists |
| 3 | Renamed `codex-cli.md` in `SOURCES.md` | `…holds_three_prompts_with_provenance` FAILED: "codex-cli.md has no provenance in SOURCES.md" |
| 4 | Added a 38-line clean `extra.go` | Picked up with no test edit (21 passed); removed (20 passed). See Deviation 2 |
| AC 3 | `_NON_VACUOUS_PROMPT` pointed at `opencode-anthropic.txt` | `test_an_agent_prompt_is_blocked_by_the_built_in_chat_profile` FAILED |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_pattern_corpus.py` | CREATE | +248 |
| `tests/corpora/code/OrderService.java` | CREATE | +95 |
| `tests/corpora/code/data-table.ts` | CREATE | +97 |
| `tests/corpora/code/PaymentProcessor.cs` | CREATE | +80 |
| `tests/corpora/code/MainActivity.kt` | CREATE | +72 |
| `tests/corpora/code/vendor-overrides.css` | CREATE | +68 |
| `tests/corpora/agent_prompts/opencode-anthropic.txt` | CREATE | +105 |
| `tests/corpora/agent_prompts/codex-cli.md` | CREATE | +275 |
| `tests/corpora/agent_prompts/gemini-cli-core.md` | CREATE | +189 |
| `tests/corpora/agent_prompts/SOURCES.md` | CREATE | +96 |
| `.agents/plans/PRD-011-pattern-policy/completed/STORY-011-…plan.md` | CREATE (archived) | — |

## Deviations from Plan

1. **Gemini CLI prompt rendered, not hand-assembled.** The plan (Task 2.4) said to copy each renderer's template text by hand and substitute tool names. Instead, upstream's `snippets.ts` at `c647533` was **executed** under Node 26 (native type stripping). Its two value imports were redirected to a stub holding the literal constants from `base-declarations.ts`, `tool-names.ts` and `memoryTool.ts` at the same commit. `getCoreSystemPrompt()` was then called with the options `promptProvider.ts` builds for a default interactive session, including the `Config` defaults `topicUpdateNarration ?? true` and `enableInteractiveShell ?? false`. The text is therefore upstream's own, and only the option choice is ours. `SOURCES.md` lists every choice. This is higher fidelity than the plan asked for, and the file is still labelled "rendered, not verbatim".
2. **The code-half companion test is scoped to the AC 1 samples.** The plan parametrized `test_code_sample_is_blocked_by_the_built_in_chat_profile` over every code file. Guard-bite check 4 showed the flaw: a clean Go sample with no `override` in it failed that test. The rule would have forced every future sample to contain `override`, which contradicts AC 4's "adding a sample needs no test edit". The test now runs over `_OVERRIDE_SAMPLES`, the files carrying one of the `_REQUIRED_CODE_SAMPLES` constructs. The five current samples all qualify, so coverage today is unchanged.
3. **Check 4 used a 38-line Go file, not the plan's 5-line snippet.** The 5-line version tripped the stub guard. That was correct behaviour, but it confounded the "no test edit" check.
4. **The optional `chat`/`assistant` floor measurement (Task 7) was not added.** It measures the role-skip path, which is a floor, not a cost, and the AC does not need it.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_corpus.py` | `test_the_code_corpus_holds_the_five_required_samples`; `test_the_agent_prompt_corpus_holds_three_prompts_with_provenance`; `test_code_sample_passes_clean_under_code_as_a_user_turn` ×5; `test_agent_prompt_passes_clean_under_code` ×6 (3 prompts × system/user); `test_an_agent_prompt_is_blocked_by_the_built_in_chat_profile`; `test_code_sample_is_blocked_by_the_built_in_chat_profile` ×5; `test_inspection_cost_at_the_context_max_messages_ceiling`. 20 in total |

## Notes for Later Stories

- **For STORY-013 (README): the PRD overstates its motivating claim.** Before choosing the prompts, six agents' prompts were measured against the built-in policy:

  | Prompt | Pre-PRD-011 patterns (substring) | `chat` / user | `code` / user |
  |---|---|---|---|
  | OpenCode `anthropic.txt`, `beast.txt`, `gemini.txt`, `codex.txt` | none | clean | clean |
  | Aider `editblock_prompts.py` | none | clean | clean |
  | Codex CLI `prompt.md` | `override` (1×, prose) | block: `override` | clean |
  | Gemini CLI core prompt | `override`, `overrides` (prose) | block: `override` | clean |

  None of them contains `execute code` or `admin mode`. PRD Section 1 ("close to every request is blocked"), Section 6.4 ("all three keywords appear in real agent system prompts") and the comment at `app/services/pattern_config.py:224-230` should not be republished as written. The supportable claim is narrower: the word `override` in ordinary prompt prose blocks every request from two major agents under `chat`, and `code` passes all six. The code-sample half of the claim holds without qualification: all five samples block under `chat` and pass under `code`.
- **For STORY-012:** reuse `_CORPORA`, `_corpus()`, `_read()` and `_describe()`. Add `"injections"` handling under a new banner. If the injection files declare their verdict in a metadata file, add its name to `_NOT_SAMPLES`. The empty-parameter-set trap applies there too: add a non-parametrized guard.
- **Line endings:** `core.autocrlf=true` and no `.gitattributes`, so the index stores LF (byte-identical to upstream) and a Windows checkout gets CRLF. The detector is indifferent, as F-7 predicted.

## Acceptance Criteria

- [x] `tests/corpora/code/` holds Java `@Override`, a TypeScript `override` member, C# `public override`, Kotlin `override fun`, and CSS with `!important` override comments. Each is plausible (≥ 58 non-blank lines, guard-enforced at ≥ 30), and each passes clean under `code` as a `user` turn.
- [x] `tests/corpora/agent_prompts/` holds three real coding-agent system prompts with provenance in `SOURCES.md` (agent, commit SHA and date, URL, license, fidelity). Each passes clean under `code` in a `system` turn and in a `user` turn.
- [x] The Codex CLI prompt, run through the **built-in `chat`** profile as a `user` turn, is blocked. This is asserted with a Risk 5 comment, and the test names `keywords`/`override`.
- [x] Files are discovered from disk (check 4); an empty corpus directory fails (check 2).
- [x] Elapsed time at the `CONTEXT_MAX_MESSAGES` ceiling is measured and recorded above, with no CI threshold.
- [x] All tasks completed
- [x] Full suite green
- [x] Follows existing patterns (prologue, `BUILT_IN_POLICY` profiles, `#:` constants, explicit ids, banners)
