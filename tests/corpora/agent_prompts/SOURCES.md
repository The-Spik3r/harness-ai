# Agent-prompt corpus: sources

Real coding-agent system prompts, checked in so `tests/test_pattern_corpus.py`
can show that the built-in `code` profile passes them clean (PRD-011 STORY-011,
PRD Section 11 *Corpus criteria*). Every file here except this one is a sample
and is discovered by the test from disk. To add a prompt, drop the file in and
add a section below; the test refuses a sample this file does not name.

All three were fetched on **2026-09-23**. Each upstream link is pinned to the
commit that last changed the file at that date, not to a branch.

---

## `opencode-anthropic.txt`: OpenCode

- **Agent**: OpenCode, the system prompt it sends to Anthropic models
- **Upstream**: `anomalyco/opencode` (formerly `sst/opencode`, which now
  redirects), `packages/opencode/src/session/prompt/anthropic.txt`
- **Commit**: `87795384de062abad50f86775e4803e4a23d51fc` (2026-02-10)
- **URL**: https://github.com/anomalyco/opencode/blob/87795384de062abad50f86775e4803e4a23d51fc/packages/opencode/src/session/prompt/anthropic.txt
- **License**: MIT
- **Fidelity**: **verbatim**, byte for byte
- **Why it is here**: the most widely deployed open-source coding agent. It
  contains none of the seven pre-PRD-011 patterns, not even as a substring,
  so it is a pure false-positive control.

## `codex-cli.md`: Codex CLI

- **Agent**: OpenAI Codex CLI, the base instructions (`codex-rs`)
- **Upstream**: `openai/codex`, `codex-rs/models-manager/prompt.md`
- **Commit**: `2cf2a6a844f1fc2ddd489c8a67fa8bc2f59a6f3d` (2026-06-23)
- **URL**: https://github.com/openai/codex/blob/2cf2a6a844f1fc2ddd489c8a67fa8bc2f59a6f3d/codex-rs/models-manager/prompt.md
- **License**: Apache-2.0
- **Fidelity**: **verbatim**, byte for byte
- **Why it is here**: this is the **PRD Risk 5 sample**, the proof the corpus is
  not vacuous. The built-in `chat` profile, which is the policy every request
  got before PRD-011, blocks it on `override`. The match comes from one line
  of prose: "your code and final answer should follow these coding guidelines,
  though user instructions (i.e. AGENTS.md) may override these guidelines".
  The built-in `code` profile passes it clean. If a re-fetch ever loses that
  sentence, keep this pinned commit instead.

## `gemini-cli-core.md`: Gemini CLI

- **Agent**: Google Gemini CLI, the core system prompt for current models
- **Upstream**: `google-gemini/gemini-cli`, `packages/core/src/prompts/snippets.ts`
- **Commit**: `c647533d6c017d032420e032f932953d7df900dc` (2026-09-08)
- **URL**: https://github.com/google-gemini/gemini-cli/blob/c647533d6c017d032420e032f932953d7df900dc/packages/core/src/prompts/snippets.ts
- **License**: Apache-2.0
- **Fidelity**: **rendered, not verbatim.** Gemini CLI has no static prompt
  file. It builds the prompt at runtime in `getCoreSystemPrompt()` from
  section renderers. This file is that function's output. It was produced by
  running upstream's `snippets.ts`, unmodified apart from its two value imports,
  under Node 26. The imports were redirected to a stub holding the literal
  constants from `tools/definitions/base-declarations.ts`, `tools/tool-names.ts`
  and `tools/memoryTool.ts` at the same commit. So the text is upstream's own.
  **The choice of options is ours.** They model a default interactive session,
  as `promptProvider.ts` at the same commit would build it:
  - `ApprovalMode.DEFAULT`, `interactive: true`
  - the standard tool set enabled: grep, glob, write_todos, enter_plan_mode,
    and the codebase investigator
  - `topicUpdateNarration: true` and `interactiveShellEnabled: false`: the
    `Config` defaults (`?? true`, `?? false`)
  - `hookContext` included, because `isSectionEnabled()` is true unless
    `GEMINI_PROMPT_HOOKCONTEXT` is `0`/`false`
  - sandbox mode `outside`; inside a git repository
  - no skills, no sub-agents, no user memory, not plan mode, not YOLO
  - a trailing newline added

  A real session can differ from this in exactly those sections.
- **Why it is here**: a third agent from a third vendor. The built-in `chat`
  profile also blocks it on `override`, from the prose in its hook-context
  and conflict-resolution sections. The test asserts the Codex CLI sample
  rather than this one, because that one is verbatim.

---

## What this sample shows, and what it does not

PRD-011 Section 1 says "close to every request is blocked", and Section 6.4
says "all three keywords appear in real agent system prompts". STORY-011
measured this against the built-in policy before choosing these files:

| Prompt | Pre-PRD-011 patterns present (as substrings) | built-in `chat`, user turn | built-in `code`, user turn |
|---|---|---|---|
| OpenCode `anthropic.txt`, `beast.txt`, `gemini.txt`, `codex.txt` | none | clean | clean |
| Aider `editblock_prompts.py` | none | clean | clean |
| Codex CLI `prompt.md` | `override` (once, prose) | **block: `override`** | clean |
| Gemini CLI core prompt | `override`, `overrides` (prose) | **block: `override`** | clean |

So two of the six agents checked trip the list, both on `override` alone, and
none of the six contains `execute code` or `admin mode`. The accurate claim
is narrower than the PRD's: the ordinary word `override` in prompt prose is
enough to block every request from two major coding agents under `chat`, and
the `code` profile passes all six. Do not cite the broader claim without new
evidence.
