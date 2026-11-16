---
prd: PRD-017
story: STORY-001
date: 2026-11-15
conclusion: OpenCode 2.0.10 renamed shell/patch and the filePath key (mapping corrected as data), and advertises a CodeMode `execute` tool that stays tool.unknown; Cline CLI 3.0.74 has no tool drift, runs headless with --yolo --json --data-dir against a custom base URL (verified live), and accepts one complete tool_calls fragment per index; OpenCode live capture not achieved
---

# Spike: what OpenCode 2.0.10 and the Cline CLI send and expect on a tool-calling `/v1` request

**Conclusion: both clients speak plain OpenAI Chat Completions with `tools`, send no `parallel_tool_calls`, write an assistant turn that only carries tool calls as `content: null`, and accept a complete tool call (`id`, `name`, whole `arguments`) in one SSE fragment per index followed by a separate `finish_reason: "tool_calls"` chunk. OpenCode 2.0 drifted a lot from PRD-016's survey (`bash` to `shell`, `apply_patch` to `patch`, `filePath` to `path`, a new CodeMode `execute` tool), and the built-in mapping now carries both generations. Cline did not drift, and its CLI runs headless against a local base URL, which STORY-017 can use.**

## Method

- **Sources read** (all pinned, nothing executed from them):
  - OpenCode `anomalyco/opencode` at tag `v2.0.10`, commit `b8cedc1a7a5e2916bbb65dc1d4b620729c261638` (committed 2026-09-19): `packages/core/src/tool/plugin/*.ts`, `packages/core/src/tool.ts`, `packages/core/src/tool/mcp.ts`, `packages/core/src/codemode/tool.ts`, `packages/util/src/patch.ts`, `packages/ai/src/protocols/openai-chat.ts`, `packages/ai/src/protocols/utils/tool-stream.ts`, and the recorded fixture `packages/ai/test/fixtures/recordings/openai-compatible-chat/groq-llama-3-3-70b-drives-a-tool-loop.json`. v2.0.10 is **not** the latest tag: `v2.0.11` (`9eb6902a`) and `v2.0.12` (`2670273f`) exist.
  - The installed OpenCode binary `@opencode/cli/bin/opencode.exe` (`opencode --version` prints `v2.0.10`, sha256 prefix `0c621cb01093d575aed7`): a Bun single-file executable that embeds its bundle as text. The tool ids, names and first schema keys found there match the source (`shell`, `read`, `write`, `edit`, `patch`, `subagent`; `execute` is built at the same place as in `codemode/tool.ts`). Where the two could disagree, the binary was checked first. They did not.
  - Cline CLI `cline@3.0.74` (npm `latest`, 2026-10-26): `apps/cli/package.json` at `cline/cline` commit `a459f1d04dea030833b558be645011ab739c463b` (the Cline 4.1.26 commit PRD-016 surveyed) says `@cline/cli` `3.0.74`. npm carries no `gitHead`, so the pin rests on that manifest and the matching `@cline/*@0.2.0` dependencies. Read there: `apps/cli/src/runtime/tools.ts`, `sdk/packages/core/src/extensions/tools/{constants,runtime,presets,team/team-tools}.ts`, `sdk/packages/llms/src/providers/vendors/openai-compatible.ts`. The AI SDK layer is `@ai-sdk/openai-compatible@3.0.67`, the version `bun.lock` pins at that commit (`npm pack` into a fresh scratch directory, read only). The compiled `cline.exe` was also grepped for the tool names.
- **Live capture, names only.** A scratch `http.server` responder on 127.0.0.1 (never committed) answered with one SSE `tool_calls` chunk (a complete fragment) and then a finish chunk, and recorded only top-level keys, role, key sets and the *type* of `content`. **Cline: done** (it executed the tool and kept going). **OpenCode: not achieved.** `opencode run --standalone --auto` with `OPENCODE_CONFIG_CONTENT` (a custom `@ai-sdk/openai-compatible` provider), `OPENCODE_DB`, `OPENCODE_CONFIG_DIR`, `OPENCODE_TEST_HOME`, `OPENCODE_DISABLE_PROJECT_CONFIG` and HOME/XDG/APPDATA redirected into the scratch directory sent no request to the responder in 100 s and was killed. The state it wrote went under the scratch directory, not the user's home. **Every OpenCode claim below rests on source, the binary and a recorded fixture, not on a live run of 2.0.10.**
- Nothing was installed globally. One side effect on the user's home: running `opencode --version` / `--help` (to read the version and flags) touched the OpenCode log directory `~/.local/share/opencode/log`. No config or database under the home was written.

## OpenCode 2.0.10: the request

Source: `openai-chat.ts` at the tag ([`#L136-L152`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/ai/src/protocols/openai-chat.ts#L136-L152) body fields, [`#L755-L790`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/ai/src/protocols/openai-chat.ts#L755-L790) body build). `openai-compatible-chat` reuses this protocol, so a custom OpenAI-compatible provider sends the same body.

| Top-level key | When | Note |
|---|---|---|
| `model`, `messages` | always | |
| `tools` | tools active **or** tool history present | **`tools: []` is sent when the history has tool calls but no tool is active**, otherwise the key is omitted (`#L763-L767`) |
| `tool_choice` | only with active tools and a requested choice | |
| `stream` | always `true` | |
| `stream_options` `{include_usage: true}` | always by default | `detectSupportsUsageInStreaming` returns `true` (`#L688`), unless a model's compatibility flag turns it off |
| `max_tokens` or `max_completion_tokens` | when a limit is set | which one depends on the provider |
| `temperature`, `top_p`, `frequency_penalty`, `presence_penalty`, `seed`, `stop` | when set | `undefined` values are dropped by JSON |
| `store`, `prompt_cache_key`, `reasoning_effort` | when set | from provider options (`lowerOptions`) |
| `tool_stream` | zai only, with active tools | |
| **`parallel_tool_calls`** | **never** | not a field of `bodyFields` |

The recorded Groq fixture's two requests carry exactly `model, messages, tools, stream, stream_options, max_tokens, temperature`, with `tools` of function definitions and no `tool_choice` and no `parallel_tool_calls`.

## OpenCode 2.0.10: history

- **Assistant turn** ([`#L425-L431`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/ai/src/protocols/openai-chat.ts#L425-L431)): `content` is the text parts joined into **one string** (never a list); it is **`null` when there is no text and there are tool calls**, and `""` when there is neither. `tool_calls` is present only when there are calls. It may also carry `reasoning_details`, `cache_control` and a provider-specific reasoning field (a string).
- **Tool turn** ([`#L436-L462`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/ai/src/protocols/openai-chat.ts#L436-L462)): `{role: "tool", tool_call_id, content: <string>, cache_control?}`. Text parts are joined with `\n`. A tool result with files adds a **separate** message for the media afterward.
- The Groq fixture's second request shows the shape: an assistant message with `content: null` and `tool_calls: [...]`, then `{role, tool_call_id, content}`.
- `arguments` is the string the model produced. Whether the OpenCode session store re-serializes it between turns was not checked.

## OpenCode 2.0.10: stream expectations

- Tool deltas are accumulated **per index** ([`#L1025-L1066`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/ai/src/protocols/openai-chat.ts#L1025-L1066)); a delta needs an `id` and a `name` on its first appearance for that index (a missing one is held pending, and an error if the finish arrives first), and `arguments` pieces are concatenated. **One complete fragment (`id`, `name`, the whole `arguments`) per index is accepted**: it is exactly what Groq sends in the recorded fixture (one chunk with `index`, `id`, `type`, `function.name` and `function.arguments`, then a chunk with `finish_reason: "tool_calls"` and `usage`, then one with an empty `delta` and `usage`, then `[DONE]`). `index` may even be omitted.
- A `finish_reason` makes the accumulator finish every pending call (`ToolStream.finishAll`, `#L1070-L1091`). The arguments text is parsed leniently (an unparsable string becomes `{}`), so **an invalid `arguments` string does not break the stream**.
- **Content or tool deltas after a `finish_reason` are an error**: "OpenAI Chat received content after the finish reason" ([`#L985-L997`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/ai/src/protocols/openai-chat.ts#L985-L997)). A chunk that carries both the last delta **and** the `finish_reason` is fine (only an earlier finish counts). A usage-only chunk after the finish is fine.

## Cline CLI 3.0.74: the request

Source: `@ai-sdk/openai-compatible@3.0.67` (`dist/index.js`, `convertToOpenAICompatibleChatMessages` at `#L139-L235`, request args at `#L412-L445`, `includeUsage: true` set in `openai-compatible.ts#L249` of the Cline SDK). Live: one `cline@3.0.74 --yolo --json` run.

- **Top-level keys seen live**: `messages`, `model`, `stream` (`true`), `stream_options` (`{include_usage}`), `tool_choice` (a string) and `tools`. **No `parallel_tool_calls`**, no `max_tokens`, no `temperature` in that run. Source agrees: the AI SDK adds `max_tokens` / `temperature` only when the caller sets them.
- **`tools` seen live under `--yolo`**: `read_files`, `run_commands`, `editor`, `submit_and_exit`, exactly the `yolo` preset (`presets.ts#L96-L110`). Without `--yolo` the CLI also offers `search_codebase`, `fetch_web_content`, `skills`, `ask_question`, `spawn_agent` and the `team_*` tools.
- **Messages seen live**: one `system` (string), then **two `user` messages** (strings), no `parts` lists.

## Cline CLI 3.0.74: history

- **Assistant turn** (seen live and in `#L197`): `content: text || null` when there are tool calls, so **`null`** when there is no text; `tool_calls: [{id, type: "function", function: {name, arguments}}]` (the `tool_calls` key is `undefined`, i.e. omitted, when there are none); optional `reasoning_content`. An assistant turn without calls is a plain string.
- **`arguments` is re-serialized: `JSON.stringify(part.input)`** (`#L186`). The parsed input is stringified again, so a history `arguments` string is compact JSON in the model's key order, **not necessarily byte-identical to what the gateway sent**. This matters for D13 (history must be treated as opaque strings): a `tool_calls[].function.arguments` in history can differ from the one the stub emitted in whitespace.
- **Tool turn** (seen live): `{role: "tool", tool_call_id, content: <string>}`. `content` is the text value, or `JSON.stringify(value)` for a JSON result, or the denial reason for `execution-denied` (`#L212-L220`).

## Cline CLI 3.0.74: stream expectations

- The parser is `processToolCallDelta` (`dist/index.js#L536-L574`). Deltas are keyed by `index`; a delta without a `name` is buffered, and a delta **with a `name`** is forwarded with the buffered arguments. **One complete fragment per index (`id`, `name`, whole `arguments`) is accepted**, and a fragment with no `index` is passed straight to the tracker.
- **Verified live**: the responder sent exactly one such fragment and a `finish_reason: "tool_calls"` chunk (separate chunks, finish last). Cline ran `read_files`, then made the next request with the assistant `tool_calls` turn and the `tool` turn.
- **The agent loop does not end by itself.** After the plain-text answer `done`, `--yolo` mode asked again (another request with an assistant text turn and a new `user` turn), and the run only stopped when it was killed (over 2,000 requests in about two minutes). The `yolo` preset enables `submit_and_exit` for this reason. STORY-017's stub must either finish the loop with a `submit_and_exit` tool call or the run must use `-t <seconds>`, or the stub will see an unbounded stream of requests.

## Mapping drift and corrections (AC3)

SOURCES.md has the evidence (`## OpenCode 2.x`, `### Cline CLI 3.0.74`, `## Differences from the PRD-016 survey`). In words:

- **OpenCode drifted.** `shell` (was `bash`) and `patch` (was `apply_patch`) are new names, and `read` / `write` / `edit` take `path` where v1.19.5 took `filePath`. `task` became `subagent`. There is a new `execute` (CodeMode). `lsp`, `todowrite`, `plan_exit`, `invalid` and `list` are not in the direct tool set. The built-in mapping (`BUILT_IN_TOOLS`, in `app/services/action_adapters.py`, **not** in `action_config.py`) now has `shell`, `patch`, and `filePath|path` on `read` / `write` / `edit`; every v1.19.5 name stays, because v1.19.5 is still a supported release. `execute`, `subagent` and the other `none` rows are **not** mapped.
- **Cline did not drift.** The CLI is built from the commit PRD-016 surveyed. Same nine tool names and keys. It also offers `spawn_agent`, `team_*` and (model-dependent) `web_search` outside `--yolo`, none of them mapped (so `tool.unknown`).

## Driving Cline headlessly (STORY-017)

Verified on this machine with `cline@3.0.74`:

```
npm install --prefix tests/e2e/.clients/cline --save-exact --no-audit --no-fund cline@3.0.74
CLINE=tests/e2e/.clients/cline/node_modules/.bin/cline
$CLINE auth --data-dir <dir> --provider openai-compatible --apikey <key> --modelid <model> --baseurl http://127.0.0.1:<port>/v1
$CLINE --data-dir <dir> --yolo --json -c <workdir> -P openai-compatible -m <model> -t <seconds> "<prompt>"
```

- `tests/e2e/.clients/` is git-ignored (`.gitignore`). Never `npm -g`.
- `--data-dir <dir>` is accepted **by `auth` itself** and by the run command, and is documented as "isolated local state at <dir> instead of ~/.cline (enables sandbox mode)". The auth run created only `<dir>/settings`; `~/.cline` did not exist afterwards. Always pass it, for both commands.
- A base URL is accepted only for `openai-compatible` (alias `openai`) and `openai-native`.
- `--json` prints NDJSON events (`agent_event`, with `content_start` / `content_end` for each tool and its `toolCallId`, `input` and `output`). `--yolo` skips approvals and advertises only `read_files`, `run_commands`, `editor` and `submit_and_exit`. `-c` is the working directory and `-t` the timeout in seconds.
- **What this proves**: Cline accepts a one-fragment tool call, executes the tool in `-c`, and makes the follow-up request with the `tool` turn. **What the earlier fallback (replaying recorded shapes in-process) could not have proved**, and this live run did: the agent loop really executes tools and continues after one. **Not yet proved**: how Cline reacts to a denial note (the tool's text result), and to a dropped call. Those need the gateway's own behavior, so they belong to STORY-017.
- Keep the stub's first request answer small and make the loop end (see above). The scripted call must be harmless: a `read_files` of a file in a throwaway directory.

## OpenCode 2.0.10: running it against a custom base URL (STORY-016)

Not verified live (see Method). What source and the binary say: the binary reads `OPENCODE_CONFIG_CONTENT`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DB`, `OPENCODE_TEST_HOME` and `OPENCODE_DISABLE_PROJECT_CONFIG`; a custom provider is `provider.<id> = {npm: "@ai-sdk/openai-compatible", options: {baseURL, apiKey}, models: {...}}` (`packages/core/src/v1/config/provider.ts`). `opencode run` uses a **background service by default**; `--standalone` runs a private server and `--auto` auto-approves permissions. The attempt above (with all of those and HOME/XDG redirected) never reached the responder, so STORY-016 has to find out why (a different 2.x config path is the likely cause), still without touching `~/.config/opencode`.

## Hand-offs

- **STORY-008** (request translation): accept `tools: []` with tool history in the messages (OpenCode); accept a request with no `parallel_tool_calls` (both clients); tolerate the extra top-level keys (`store`, `prompt_cache_key`, `reasoning_effort`, `tool_stream`, `max_completion_tokens`, `seed`, `stop`); accept message keys beyond `role` / `content` / `tool_calls` / `tool_call_id` (`cache_control`, `reasoning_details`, `reasoning_content`, a reasoning field). Do not assume a history `arguments` string equals what the gateway sent (Cline re-stringifies it).
- **STORY-003 / STORY-008**: an assistant message with `tool_calls` has `content: null` (both clients), not `""`.
- **STORY-012** (SSE): put the finish chunk last. OpenCode errors on any content or tool delta after a `finish_reason`. A tool call needs `id` and `name` on the first delta for its index; one complete fragment per index works for both clients. Send `usage` only after the finish chunk or with it, never as content.
- **STORY-016** (E2E OpenCode): tool names are `shell` and `patch` (not `bash`, `apply_patch`); `read` / `write` / `edit` use `path`. The gpt- rule applies (`patch` replaces `edit`/`write` for model ids with `gpt-` that are not `oss` or `gpt-4`). **`execute` is advertised in every session**, so the policy file must leave `execute` out of `tools:` and out of `opaque_tools`: it stays `tool.unknown`. MCP tools are CodeMode by default (called inside `execute.code`). Isolation env vars and the unsolved headless run are above.
- **STORY-017** (E2E Cline): the install, `auth` and run commands above, with `--data-dir`; make the stub end the loop (`submit_and_exit`) or use `-t`; the policy needs the Cline 4.x names (`read_files`, `run_commands`, `editor`).
- **STORY-018** (docs): `docs/features.md:279` lists only the v1.19.5 OpenCode names; `examples/action_policy.yaml` now maps both generations (this story updated it, 7 to 9 tools).
