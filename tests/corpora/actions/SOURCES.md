# Action corpus: adapter sources

Where each built-in tool mapping in PRD-016 comes from. PRD-016 F1 and
STORY-004 map an OpenAI `tool_calls[i]` (a name and a JSON-string `arguments`)
to an operation by **exact tool name** and **exact argument key**. A wrong
guess here fails closed (`tool.unknown` or `tool.malformed`, PRD Risk 5), but
it also denies every ordinary call. So each name and key below was read from
the client's own source, not from its docs. STORY-004's parametrized test reads
the per-client tables, and the synthetic and evasion corpora (STORY-017) use
the same names.

Everything was fetched on **2026-11-15** (STORY-001). Each upstream link is
pinned to a full commit SHA, either a release tag's commit or a named commit.
None points at a branch. Downloads were read and grepped only. Nothing was
executed or checked in.

PRD-017 STORY-001 re-surveyed **OpenCode 2.0.10** and the **Cline CLI 3.0.74** on
2026-11-15 by the same method, and also read the installed binaries (OpenCode on
the dev machine, and the pinned Cline CLI binary). The new sections are *OpenCode
2.x*, *Cline CLI 3.0.74* and *Differences from the PRD-016 survey*.

Table conventions, fixed so a test can parse them:

- `Operation kind` is one of `shell`, `sql`, `fs_write`, `fs_read`, `http`,
  `none`. `none` means the tool performs no operation the engine classifies,
  so STORY-004 decides between `tool.unknown` and `opaque_tools`.
- `Target key` is the JSON key path inside `arguments`. `files[].path` means
  "the `path` of every element of the `files` array". `(in patch text)` means
  the paths are lines inside a string argument. A trailing `?` means the key
  is optional.
- `Multi-target` is `yes` when one call can name several targets.
- `Paths` is one of `absolute`, `relative`, `either`, `n/a`. It records what
  the schema **asks the model for**. The executor's own handling of the other
  form is in *Absolute and relative paths* below.

---

## OpenCode

- **Upstream**: `anomalyco/opencode` (formerly `sst/opencode`), `packages/opencode/src/tool/`
- **Tag**: `v1.19.5` (2026-10-28), the latest release on 2026-11-15
- **Commit**: `810c0eba1a7348036f8bdf61e6632d0c36c6876c` (lightweight tag on a commit). The last change under `src/tool/` before the tag is `b01498d3ff575b7d3e7b358ff24bf6d2b28484b6` (2026-10-27)
- **License**: MIT
- **Schema location**: the tool id is the first argument of `Tool.define(...)`. The parameters are the `Parameters` `Schema.Struct` (Effect Schema) in the same file. Registration is in `tool/registry.ts`.

| Client | Tool | Operation kind | Target key | Multi-target | Paths | Version | Commit | Schema |
|---|---|---|---|---|---|---|---|---|
| OpenCode | `bash` | `shell` | `command` | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/shell/prompt.ts#L15-L23 |
| OpenCode | `write` | `fs_write` | `filePath` | no | absolute | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/write.ts#L20-L28 |
| OpenCode | `edit` | `fs_write` | `filePath` | no | absolute | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/edit.ts#L47-L59 |
| OpenCode | `apply_patch` | `fs_write` | `patchText` (in patch text) | yes | either | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/apply_patch.ts#L18-L23 |
| OpenCode | `read` | `fs_read` | `filePath` | no | absolute | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/read.ts#L28-L69 |
| OpenCode | `webfetch` | `http` | `url` | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/webfetch.ts#L13-L25 |
| OpenCode | `glob` | `fs_read` | `path?` | no | either | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/glob.ts#L10-L18 |
| OpenCode | `grep` | `fs_read` | `path?` | no | either | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/grep.ts#L10-L21 |
| OpenCode | `lsp` | `fs_read` | `filePath` | no | either | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/lsp.ts#L23-L38 |
| OpenCode | `websearch` | `none` | — | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L101-L116 |
| OpenCode | `task` | `none` | — | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L101-L116 |
| OpenCode | `todowrite` | `none` | — | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L101-L116 |
| OpenCode | `question` | `none` | — | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L101-L116 |
| OpenCode | `skill` | `none` | — | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L101-L116 |
| OpenCode | `plan_exit` | `none` | — | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L101-L116 |
| OpenCode | `invalid` | `none` | — | no | n/a | v1.19.5 | `810c0eba` | https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L101-L116 |

The two PRD names that no longer exist:

| PRD name | Status at v1.19.5 | Evidence |
|---|---|---|
| `patch` | **Replaced by `apply_patch`.** `tool/patch.ts` and `patch.txt` were removed, and `apply_patch.ts` added, in the same commit | https://github.com/anomalyco/opencode/commit/b7ad6bd83922e2259a467fe59f27806af8060629 (2026-01-18, "feat: apply_patch tool for openai models") |
| `list` | **Removed.** `tool/ls.ts` and `ls.txt` deleted. The tool directory listing at the tag has no `ls.ts` | https://github.com/anomalyco/opencode/commit/d2ea6700aa2e6bdf5d04fe70ba893afbb320adbd (2026-04-15, "Remove dead code and documentation related to the obsolete list tool") |

Notes:

- **`bash` keeps its name, but the file is now `shell.ts`.** The id is `ShellID.ToolID`, which `tool/shell/id.ts` sets to `"bash"` "for compatibility … Rename with opencode 2.0" ([`shell/id.ts#L14-L16`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/shell/id.ts#L14-L16), [`shell.ts#L338-L339`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/shell.ts#L338-L339)). The same file lists the shell kinds `bash`, `pwsh`, `powershell` and `cmd` ([`#L1`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/shell/id.ts#L1)). So a `bash` call from OpenCode on Windows may be PowerShell or cmd text (PRD Risk 3). `workdir?` and `timeout?` are optional siblings of `command`.
- **`apply_patch` carries its paths inside `patchText`.** The headers are `*** Add File: <path>`, `*** Update File: <path>` (optionally followed by `*** Move to: <path>`) and `*** Delete File: <path>`, inside `*** Begin Patch` … `*** End Patch`. One patch may hold several file sections ([`apply_patch.txt#L1-L27`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/apply_patch.txt#L1-L27); parser [`patch/index.ts#L76-L93`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/patch/index.ts#L76-L93)). A `Delete File` is a write too.
- **`apply_patch` replaces `edit`/`write` for some models.** The registry offers `apply_patch` **instead of** `edit` and `write` when the model id contains `gpt-` and contains neither `oss` nor `gpt-4` ([`registry.ts#L297-L300`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/registry.ts#L297-L300)). A deployment that maps `edit`/`write` but not `apply_patch` therefore denies every edit an OpenCode GPT-5 session makes.
- **`glob` and `grep`: the directory is optional, and the pattern is the other half of the target.** `path?` defaults to the instance directory ([`glob.ts#L39`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/glob.ts#L39), [`grep.ts#L51-L53`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/grep.ts#L51-L53)). `glob.pattern` is a path glob that can itself name `../` or `.env*`. `grep.include` is a filename glob.
- **`lsp`** is not in the PRD. Its `filePath` is described as "The absolute or relative path to the file". It reads code.
- **No `todoread`.** PRD Section 6.6's sample `opaque_tools` names `todoread`, but v1.19.5 registers only `todowrite`.
- **MCP tools arrive prefixed.** An MCP tool is exposed as `sanitize(server) + "_" + sanitize(tool)`, where `sanitize` replaces anything outside `[a-zA-Z0-9_-]` with `_` ([`mcp/catalog.ts#L117-L119`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/mcp/catalog.ts#L117-L119), used at [`mcp/index.ts#L684`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/mcp/index.ts#L684)). A Postgres server named `postgres` sends `postgres_query`, never a bare `query`.

## OpenCode 2.x

OpenCode 2.0 is a rewrite, and it renamed tools and keys. PRD-017 STORY-001 surveyed **2.0.10**, the version installed on the dev machine, on **2026-11-15**, because PRD-017 drives it end to end.

- **Upstream**: `anomalyco/opencode`, `packages/core/src/tool/plugin/` (one file per tool). The request protocol is `packages/ai/src/protocols/openai-chat.ts`
- **Tag**: `v2.0.10`. The commit date is 2026-09-19. It is **not** the latest tag: `v2.0.11` (`9eb6902a`) and `v2.0.12` (`2670273f`) exist
- **Commit**: `b8cedc1a7a5e2916bbb65dc1d4b620729c261638` (lightweight tag on a commit)
- **License**: MIT
- **Installed binary** (ground truth for the version the dev machine runs): `@opencode/cli/bin/opencode.exe`, a Bun single-file executable that embeds its bundle as text, sha256 prefix `0c621cb01093d575aed7`. `opencode --version` prints `v2.0.10`. Each tool name, key and description below was found in the binary and matches the source at the tag (for example `Rp="shell"`, `Wj="edit"`, `Rj="patch"`, `Ip="subagent"`, `SL="read"`, `WE="write"`, with `path` / `command` / `patchText` / `agent` as their first keys). Nothing in the bundle was executed.
- **Schema location**: each tool is a plugin `{id: "opencode.tool.<x>", effect: ...}` that calls `ctx.tool.transform(editor => editor.add({name, options: {codemode: false, ...}, input: <Input>}))`. `Input` is the `Schema.Struct` in the same file. The registry is `packages/core/src/tool.ts`.

| Client | Tool | Operation kind | Target key | Multi-target | Paths | Version | Commit | Schema |
|---|---|---|---|---|---|---|---|---|
| OpenCode 2.x | `shell` | `shell` | `command` | no | n/a | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/shell.ts#L47-60 |
| OpenCode 2.x | `read` | `fs_read` | `path` | no | either | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/read.ts#L17-25 |
| OpenCode 2.x | `write` | `fs_write` | `path` | no | either | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/write.ts#L23-28 |
| OpenCode 2.x | `edit` | `fs_write` | `path` | no | either | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/edit.ts#L24-34 |
| OpenCode 2.x | `patch` | `fs_write` | `patchText` (in patch text) | yes | either | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/patch.ts#L21-25 |
| OpenCode 2.x | `webfetch` | `http` | `url` | no | n/a | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/webfetch.ts#L23-31 |
| OpenCode 2.x | `glob` | `fs_read` | `path?` | no | relative | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/glob.ts#L17-28 |
| OpenCode 2.x | `grep` | `fs_read` | `path?` | no | relative | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/grep.ts#L17-38 |
| OpenCode 2.x | `websearch` | `none` | — | no | n/a | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/websearch.ts#L24-26 |
| OpenCode 2.x | `subagent` | `none` | — | no | n/a | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/subagent.ts#L29-48 |
| OpenCode 2.x | `skill` | `none` | — | no | n/a | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/skill.ts#L12-14 |
| OpenCode 2.x | `question` | `none` | — | no | n/a | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/question.ts#L23-25 |
| OpenCode 2.x | `execute` | `none` | — | no | n/a | v2.0.10 | `b8cedc1a` | https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/codemode/tool.ts#L73-108 |

Notes:

- **What changed from v1.19.5** is in *Differences from the PRD-016 survey* below. `bash` is now `shell`, `apply_patch` is now `patch`, `task` is now `subagent` (with a new `agent` key), `read` / `write` / `edit` take `path` instead of `filePath`, and `lsp`, `todowrite`, `plan_exit`, `invalid` and `list` are gone from the direct tool set (the string `opencode.tool.lsp` and its siblings occur 0 times in the binary).
- **`execute` is the CodeMode tool, and it is advertised by default.** The snapshot in `tool.ts` splits the registered tools into `direct` (`options.codemode === false`) and CodeMode tools. It adds `execute` to the definitions whenever the permission rules do not wholly disable it, **even with no CodeMode tools registered** ([`tool.ts#L225-L260`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool.ts#L225-L260)). The built-in tools are all `codemode: false`. The `opencode` namespace tools (`session_rename`, `session_move`, `models`) are `codemode: true` ([`plugin/opencode.ts#L85-L140`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/opencode.ts#L85-L140)), so `execute` is advertised in every ordinary session. Its one key is `code`, JavaScript run in a confined interpreter. The description says `fetch` is available, and that other external access goes through `tools.<namespace>.<name>(...)` ([`codemode/tool.ts#L60-L108`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/codemode/tool.ts#L60-L108)). So one `execute` call can make HTTP requests and call MCP tools without a single `tool_calls` entry naming them. **`execute` is `none` here on purpose: it stays `tool.unknown`, and it must never be listed in `opaque_tools`.** `execute.code` is not inspected (future work).
- **MCP tools are CodeMode tools by default.** `mcp.ts` registers each one with `codemode: tool.codemode !== false` ([`tool/mcp.ts#L45`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/mcp.ts#L45)), so they are called inside `execute.code` and do not arrive as their own `tool_calls`. Only a server configured with `codemode: false` gets a direct tool, exposed as `<namespace with "." replaced by "_">_<name>`, the same `<server>_<tool>` shape as v1.19.5 (`exposedToolName` in the binary at offset 161283646: `options.namespace === undefined ? name : namespace.replaceAll(".", "_") + "_" + name`; the namespace is `server.replace(/[^a-zA-Z0-9_-]/g, "_")`, [`tool/mcp.ts#L16-L17`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/mcp.ts#L16-L17)).
- **`patch` replaces `edit` and `write` for some models, as `apply_patch` did.** The plugin's session hook deletes `edit` and `write` and keeps `patch` when the model id contains `gpt-` and contains neither `oss` nor `gpt-4`, and deletes `patch` otherwise ([`plugin/patch.ts#L296-L305`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/patch.ts#L296-L305)).
- **`patch` carries its paths inside `patchText`** with the v1.19.5 grammar: `*** Begin Patch` ... `*** End Patch`, and `*** Add File: <path>`, `*** Update File: <path>` (optionally `*** Move to: <path>`) and `*** Delete File: <path>` ([`packages/util/src/patch.ts#L48-L110`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/util/src/patch.ts#L48-L110)). 2.0 adds one thing: an optional **`*** Environment ID: <id>`** line directly after `*** Begin Patch`, which the parser skips ([`patch.ts#L63-L70`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/util/src/patch.ts#L63-L70)). It names no file, and the adapter's header scan ignores it, so it is not a target. What the id selects is not read here. The patch tool resolves each header path against the session `Location` directory (`FileAccess.resolvePath(location.directory, hunk.path)`, [`plugin/patch.ts#L88-L93`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/patch.ts#L88-L93)).
- **`read` lists directories.** `path` is "File or directory to read", with `offset` and `limit` counting lines or directory entries ([`plugin/read.ts#L17-L25`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/read.ts#L17-L25)). It is still one `fs_read` of `path`.
- **`glob` and `grep` keep their keys.** `path?` is a `RelativePath` that defaults to the working directory, `glob.pattern` is the other half of the target, and `grep` has `include?` and a new `literal?` (plain text instead of a regex). The mapping is unchanged.
- **`shell` is the new `bash`.** `command`, `workdir?`, `timeout?` (milliseconds, 0 disables) and `background?`. The description says "Commands run on <OS> using <shell>", so on Windows the text may be PowerShell or cmd, as in v1.19.5 (PRD Risk 3: the POSIX classifier must fail closed as `shell.unclassifiable`) ([`plugin/shell.ts#L25-L60`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/shell.ts#L25-L60)).
- **`websearch`, `subagent`, `skill`, `question`** perform no operation the engine classifies. `subagent` takes `agent`, `description`, `prompt`, `model?`, `sessionID?` and `background?`.
- `write` carries a source TODO about whether model-facing mutation schemas should "prefer absolute `filePath` naming for trained-in compatibility" ([`plugin/write.ts#L22`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/write.ts#L21)). So a later 2.0.x release may go back to `filePath` for `write`. That is why the built-in mapping reads both spellings.

## Cline

Cline has two tool sets. **Cline 4.x is the current client**, and its VS Code extension runs the SDK tool set. The 3.x tool names, which PRD Section 4 lists, are recorded second as additional candidates.

### Cline 4.x (current)

- **Upstream**: `cline/cline`, `sdk/packages/core/src/extensions/tools/`
- **Tag**: `v4.1.26` (2026-10-26), the latest release on 2026-11-15. `apps/vscode/package.json` at the tag says `"name": "claude-dev"`, `"version": "4.1.26"` (the VS Code extension)
- **Commit**: `a459f1d04dea030833b558be645011ab739c463b` (lightweight tag on a commit)
- **License**: Apache-2.0
- **Schema location**: names in `constants.ts` ([`#L12-L22`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/constants.ts#L12-L22)). Zod schemas in `schemas.ts`. Tool objects in `definitions.ts`, each with `inputSchema: zodToJsonSchema(<advertised schema>)` and an `execute` that validates against a more lenient **union** schema.

| Client | Tool | Operation kind | Target key | Multi-target | Paths | Version | Commit | Schema |
|---|---|---|---|---|---|---|---|---|
| Cline 4.x | `run_commands` | `shell` | `commands[]` | yes | n/a | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L127-L176 |
| Cline 4.x | `read_files` | `fs_read` | `files[].path` | yes | absolute | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L15-L106 |
| Cline 4.x | `editor` | `fs_write` | `path` | no | absolute | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L198-L233 |
| Cline 4.x | `apply_patch` | `fs_write` | `input` (in patch text) | yes | either | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L238-L253 |
| Cline 4.x | `fetch_web_content` | `http` | `requests[].url` | yes | n/a | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L181-L193 |
| Cline 4.x | `search_codebase` | `none` | — | yes | n/a | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L111-L125 |
| Cline 4.x | `skills` | `none` | — | no | n/a | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L258-L265 |
| Cline 4.x | `ask_question` | `none` | — | no | n/a | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L270-L284 |
| Cline 4.x | `submit_and_exit` | `none` | — | no | n/a | v4.1.26 | `a459f1d0` | https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/schemas.ts#L286-L298 |

Notes:

- **The extension really runs this set.** `VscodeSessionHost.create` builds a `ClineCore` with the extension's own executors for `editor`, `applyPatch` and `readFile`. It suppresses the SDK's `run_commands` and adds its own, which is built with the same SDK `createShellTool` and so has the same name and schema ([`vscode-session-host.ts#L116-L138`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/apps/vscode/src/sdk/vscode-session-host.ts#L116-L138), [`vscode-run-commands-tool.ts#L533`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/apps/vscode/src/sdk/vscode-run-commands-tool.ts#L533)). `apps/vscode/src/core/prompts/system-prompt/tools/`, where the 3.x names lived, does not exist at this tag. Cline's own docs say so: "older docs/examples reference XML-style names like `read_file`, `replace_in_file`, `execute_command` … Current SDK/ClineCore runtime uses the built-in tool names listed above" ([`all-cline-tools.mdx#L75-L77`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/docs/tools-reference/all-cline-tools.mdx#L75-L77)).
- **`editor` and `apply_patch` are alternatives.** `createDefaultTools` adds `editor` when it is enabled, else `apply_patch` (which defaults to off) ([`definitions.ts#L955-L1001`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/definitions.ts#L955-L1001)). `editor` creates the file when it is missing, so it is always a write.
- **They are OpenAI `tool_calls` on an OpenAI-compatible provider.** The LLM layer turns each tool definition into an AI SDK tool keyed by `definition.name` with `jsonSchema(inputSchema)` ([`llms/src/providers/ai-sdk.ts#L867-L887`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/llms/src/providers/ai-sdk.ts#L867-L887)). The OpenAI-compatible vendor is `createOpenAICompatible` from `@ai-sdk/openai-compatible` ([`openai-compatible.ts#L243`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/llms/src/providers/vendors/openai-compatible.ts#L243)), which sends them as function tools.
- **Advertised schema vs accepted shapes.** The model is shown the strict schema, but `execute` accepts much more. The comment at `ai-sdk.ts#L872-L876` says this is on purpose ("lenient union schemas that accept common weak-model shapes"):
  - `run_commands` accepts `{commands: string[]}`, `{commands: [{command, args?}]}`, `{commands: <one entry>}`, `[{command, args?}]`, `{command, args?}`, `{command}`, `{cmd}`, a string array or a bare string (`schemas.ts#L166-L176`). In the structured form, `command` is the executable and `args[]` its argv, with no shell parsing.
  - `read_files` accepts `files[]` of strings or objects, `{files: <one>}`, `file_paths` (array or string), `paths` (array, object or string), a bare string, and per-entry aliases `file_path` and `filePath` for `path` (`schemas.ts#L75-L106`).
  - `apply_patch` accepts `{input}` or a bare string (`schemas.ts#L250-L253`).
  - `fetch_web_content` and `editor` validate against their advertised schema only (`definitions.ts#L587`, `#L731`).

  A bare JSON string or array is not a JSON object, so it is already `tool.malformed` under PRD Section 4. The object aliases are the open question for STORY-004.
- **`apply_patch` uses the same grammar as OpenCode's**: `*** Add File: `, `*** Update File: `, `*** Delete File: `, `*** Move to: ` ([`executors/apply-patch-parser.ts#L8-L15`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/executors/apply-patch-parser.ts#L8-L15)).
- **`search_codebase`** takes `queries[]`, which are regexes run over the workspace with no path argument. It reads the workspace but names no target, so it is listed as `none`.
- **MCP tools arrive as `<server>__<tool>`.** If that raw name has a character outside `[a-zA-Z0-9_-]` or is longer than 64 characters, it is sanitized, truncated and given an 8-character SHA-1 suffix ([`mcp/name-transform.ts#L20-L35`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/mcp/name-transform.ts#L20-L35), applied in [`mcp/tools.ts#L21-L30`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/mcp/tools.ts#L21-L30), wired into the extension at [`vscode-runtime-builder.ts#L68-L94`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/apps/vscode/src/sdk/vscode-runtime-builder.ts#L68-L94)). There is no `use_mcp_tool` or `access_mcp_resource` in 4.x. These names are `tool.unknown` unless a deployment maps them.

### Cline CLI 3.0.74 (the headless client PRD-017 drives)

PRD-017 STORY-001 re-surveyed the Cline command-line client on **2026-11-15**, because PRD-017's end-to-end test drives it headlessly.

- **Package**: npm `cline@3.0.74` (the `latest` dist-tag, published 2026-10-26). Its dependencies are `@cline/{sdk,core,agents,llms,shared}@0.2.0`, and its platform binary is `@cline/cli-windows-x64@3.0.74` (`bin/cline.exe`, a compiled bundle). Apache-2.0. npm records no `gitHead`
- **Source**: `apps/cli/package.json` at the Cline 4.x commit `a459f1d04dea030833b558be645011ab739c463b` says `"name": "@cline/cli", "version": "3.0.74"`, and `sdk/packages/{core,llms}/package.json` there say `0.2.0`. So the CLI is built from **the same commit PRD-016 surveyed**, and the table above applies to it. The SDK pins `@ai-sdk/openai-compatible@3.0.67` in `bun.lock` at that commit
- **Tool set: no drift in names or keys.** `sdk/packages/core/src/extensions/tools/constants.ts#L12-L22` lists the same nine names as the Cline 4.x table, and the installed `cline.exe` contains all nine. The CLI adds no tool of its own: `apps/cli/src/runtime/tools.ts` only calls `getCoreBuiltinToolCatalog({ clientType: "cli", ... })`.
- **Which tools a run advertises** depends on the preset. The `yolo` preset (`-y/--yolo`) enables `read_files`, `run_commands`, `editor` and `submit_and_exit` only ([`presets.ts#L96-L110`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/presets.ts#L96-L110)). A live run of `cline@3.0.74 --yolo` against a local OpenAI-compatible responder sent `tools` with exactly those four names. The `act` and `plan` presets also enable `search_codebase`, `fetch_web_content`, `skills`, `ask_question`, **`spawn_agent`** and the **`team_*`** tools (17 names, `team/team-tools.ts#L197-L215`), which are new since PRD-016 and carry no file, shell or URL target. `web_search` is added only when the provider's model supports a native search tool. None of these is mapped: `spawn_agent`, `team_*` and `web_search` stay `tool.unknown` (deny), as `search_codebase` is `none`.
- The nine names are not repeated as table rows: duplicate `Cline 4.x` rows would change no mapping. `spawn_agent`, `team_*` and `web_search` are not rows either, because the `--yolo` mode the E2E uses does not advertise them.

### Cline 3.x (legacy, the names PRD Section 4 lists)

- **Upstream**: `cline/cline`, `apps/vscode/src/core/prompts/system-prompt/tools/`
- **Tag**: `v3.89.2`, the last 3.x tag
- **Commit**: `e1bdeeff68e95734901c7a4b3a31753bae54a634` (lightweight tag on a commit)
- **License**: Apache-2.0
- **Schema location**: one file per tool, each exporting `<tool>_variants`, an array of `ClineToolSpec`s. A variant is a model family (`ModelFamily` in [`shared/prompts.ts#L1-L18`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/shared/prompts.ts#L1-L18)). The tool names are the `ClineDefaultTool` enum values ([`shared/tools.ts#L8-L36`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/shared/tools.ts#L8-L36)), and they are **the same in every variant**. Only the parameter keys differ.

**Which variants are `tool_calls` and which are text.** A prompt variant sends native tools only if its config has `use_native_tools: 1` and the context has `enableNativeToolCalls`. Otherwise `tools` is `undefined` and the tool calls are XML blocks in the assistant's text ([`registry/ClineToolSet.ts#L170-L193`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/registry/ClineToolSet.ts#L170-L193), [`system-prompt/index.ts#L19`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/index.ts#L19)). The native families are `gemini3`, `gpt-5-native`, `gpt-5-1-native`, `native-next-gen` and `xs` (the five `variants/*/config.ts` files with `use_native_tools: 1`, for example [`native-gpt-5/config.ts#L19`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/variants/native-gpt-5/config.ts#L19)). On a non-Anthropic, non-Gemini provider the converter is `toolSpecFunctionDefinition`, which produces an OpenAI `{type: "function", function: {name, …}}` ([`spec.ts#L52-L127`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/spec.ts#L52-L127)).

**A native family without its own spec for a tool falls back to the `GENERIC` spec** ([`ClineToolSet.ts#L46-L68`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/registry/ClineToolSet.ts#L46-L68)). So the `GENERIC` keys reach `tool_calls` too, from `gemini3` and `xs` for `write_to_file` and `replace_in_file`. The text-only XML form never reaches the engine as a `tool_call`, so it needs no mapping. Both key spellings below can arrive as `tool_calls`.

| Client | Tool | Operation kind | Target key | Multi-target | Paths | Version | Commit | Schema |
|---|---|---|---|---|---|---|---|---|
| Cline 3.x | `execute_command` | `shell` | `command` | no | n/a | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/execute_command.ts#L5-L88 |
| Cline 3.x | `write_to_file` | `fs_write` | `absolutePath` | no | absolute | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/write_to_file.ts#L51-L78 |
| Cline 3.x | `write_to_file` | `fs_write` | `path` | no | relative | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/write_to_file.ts#L27-L49 |
| Cline 3.x | `replace_in_file` | `fs_write` | `absolutePath` | no | absolute | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/replace_in_file.ts#L87-L113 |
| Cline 3.x | `replace_in_file` | `fs_write` | `path` | no | relative | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/replace_in_file.ts#L64-L85 |
| Cline 3.x | `read_file` | `fs_read` | `path` | no | relative | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/read_file.ts#L11-L57 |
| Cline 3.x | `list_files` | `fs_read` | `path` | no | either | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/list_files.ts#L8-L60 |
| Cline 3.x | `search_files` | `fs_read` | `path` | no | relative | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/search_files.ts#L23-L88 |
| Cline 3.x | `browser_action` | `http` | `url?` | no | n/a | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/browser_action.ts#L7-L106 |
| Cline 3.x | `apply_patch` | `fs_write` | `input` (in patch text) | yes | either | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/apply_patch.ts#L79-L100 |
| Cline 3.x | `use_mcp_tool` | `none` | — (`tool.unknown` by design) | no | n/a | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/use_mcp_tool.ts#L34-L69 |
| Cline 3.x | `access_mcp_resource` | `none` | — (`tool.unknown` by design) | no | n/a | v3.89.2 | `e1bdeeff` | https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/tools/access_mcp_resource.ts#L23-L79 |

Per-variant keys, with each variant's transport:

| Tool | Variant(s) | Key(s) | Transport |
|---|---|---|---|
| `execute_command` | `GENERIC` | `command`, `requires_approval`, `timeout?` | XML in text, and native via fallback for `xs` and `gpt-5-1-native` |
| `execute_command` | `NATIVE_GPT_5`, `NATIVE_NEXT_GEN`, `GEMINI_3` | `command`, `requires_approval` | native `tool_calls` |
| `write_to_file` | `GENERIC` | `path` ("relative to the current working directory"), `content` | XML in text, and native via fallback for `gemini3` and `xs` |
| `write_to_file` | `NATIVE_NEXT_GEN`, `NATIVE_GPT_5` | `absolutePath` ("The absolute path to the file to write to."), `content` | native `tool_calls` |
| `replace_in_file` | `GENERIC` | `path` (relative), `diff` (SEARCH/REPLACE blocks, one file) | XML in text, and native via fallback for `gemini3` and `xs` |
| `replace_in_file` | `NATIVE_NEXT_GEN`, `NATIVE_GPT_5` | `absolutePath`, `diff` | native `tool_calls` |
| `read_file` | `GENERIC`, `NATIVE_GPT_5`, `NATIVE_NEXT_GEN` (one shared parameter list) | `path` (relative), `start_line?`, `end_line?` | both |
| `list_files` | `GENERIC` | `path` (relative), `recursive?` | XML in text, and native via fallback for `gemini3` and `gpt-5-1-native` |
| `list_files` | `NATIVE_GPT_5`, `NATIVE_NEXT_GEN` | `path` ("The path of the directory to list contents for."), `recursive?` | native `tool_calls` |
| `search_files` | `GENERIC`, `NATIVE_NEXT_GEN`, `NATIVE_GPT_5` | `path` (relative), `regex`, `file_pattern?` | both |
| `browser_action` | `GENERIC`, `NATIVE_NEXT_GEN` | `action`, `url?` (only for `launch`), `coordinate?`, `text?` | both |
| `apply_patch` | `NATIVE_GPT_5`, `GPT_5` | `input` | native for `NATIVE_GPT_5` (and for `gpt-5-1-native`, which has no spec of its own and falls back to a registered one); XML in text for `GPT_5` |
| `use_mcp_tool` | `GENERIC` only | `server_name`, `tool_name`, `arguments` | XML in text, and native via fallback for `gemini3` |
| `access_mcp_resource` | `GENERIC`, `NEXT_GEN`, `GPT`, `NATIVE_GPT_5`, `NATIVE_NEXT_GEN` | `server_name`, `uri` | both |

Notes:

- `replace_in_file` names **one** file per call. Its `diff` can hold several SEARCH/REPLACE blocks, but all of them apply to that file. So it is not multi-target, contrary to the STORY-001 Technical Notes' guess.
- `browser_action` reaches a URL only with `action: "launch"`. Its other actions (`click`, `type`, `scroll_*`, `close`) carry no URL, so STORY-004 decides what a `browser_action` with no `url` means.
- **MCP in 3.x native mode.** Native families do not use `use_mcp_tool`. Each MCP tool is its own function, named `server.uid + "0mcp0" + tool.name`, and skipped when that name is longer than 64 characters ([`ClineToolSet.ts#L236-L248`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/core/prompts/system-prompt/registry/ClineToolSet.ts#L236-L248), [`shared/mcp.ts#L6`](https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/apps/vscode/src/shared/mcp.ts#L6)). `use_mcp_tool`, `access_mcp_resource` and the `0mcp0` names are all `tool.unknown` by design: PRD Section 4 *Out of Scope* puts MCP payload inspection out of scope, and Section 13 names MCP payload adapters as future work.

## Aider

**No reachable Aider mode emits OpenAI `tool_calls`, so the PRD assumption "Aider needs no adapter" is confirmed.** This holds at the latest release `v0.86.0` and at `main`.

- **Upstream**: `Aider-AI/aider`
- **Tag**: `v0.86.0` (2025-08-09), the latest GitHub release on 2026-11-15 → `a4be6ccd87ebaa59b361f3f028d116ce1761b626` (lightweight tag on a commit). Tags `v0.86.2` and `v0.86.3.dev` exist without a release, and `v0.86.2` is an ancestor of `main`
- **`main`**: `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` (2026-05-22), 152 commits ahead of `v0.86.0`
- **License**: Apache-2.0

The evidence is the same at both refs. `aider/coders/__init__.py` is byte-identical, and the `send_completion` body is the same.

1. `Model.send_completion(messages, functions, stream, …)` adds `tools=[…]` and a forced `tool_choice` **only when `functions is not None`**: [v0.86.0 `models.py#L948-L972`](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/models.py#L948-L972), [main `models.py#L985-L1009`](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/models.py#L985-L1009). Its other caller, `simple_send_with_retries`, passes `"functions": None` ([v0.86.0 `#L1014-L1021`](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/models.py#L1014-L1021), [main `#L1051-L1058`](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/models.py#L1051-L1058)).
2. `Coder.functions = None` on the base class ([v0.86.0 `base_coder.py#L96`](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/base_coder.py#L96), [main `#L96`](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py#L96)). A grep of every `aider/**/*.py` at both refs for `functions =`, `tools=`, `tool_choice` and `tool_calls` finds non-`None` `functions` only in `editblock_func_coder.py`, `wholefile_func_coder.py` and `single_wholefile_func_coder.py`.
3. Those three are unreachable. `Coder.create` picks a coder by iterating `coders.__all__` for a matching `edit_format` ([v0.86.0 `base_coder.py#L190-L201`](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/base_coder.py#L190-L201), [main](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/base_coder.py#L190-L201)). None of the three is imported into `__all__`, and `SingleWholeFileFunctionCoder` is commented out ([v0.86.0 `coders/__init__.py#L16-L34`](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/__init__.py#L16-L34), [main](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/__init__.py#L16-L34)). Two of them also raise in `__init__`: `RuntimeError("Deprecated, needs to be refactored to support get_edits/apply_edits")` ([v0.86.0 `wholefile_func_coder.py#L47`](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/wholefile_func_coder.py#L47), [`editblock_func_coder.py#L61`](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/editblock_func_coder.py#L61); same lines on [main](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/coders/wholefile_func_coder.py#L47)).
4. `base_coder.py#L1850-L1852` still reads `tool_calls[0].function` from a response ([v0.86.0](https://github.com/Aider-AI/aider/blob/a4be6ccd87ebaa59b361f3f028d116ce1761b626/aider/coders/base_coder.py#L1850-L1852)). That is dead code for the registered coders, which never ask for tools.

One limit: `send_completion` merges a model's `extra_params` into the request after the `tools` block (`kwargs.update(self.extra_params)`, `models.py#L973-L974` at v0.86.0). A user who writes `tools` into a model's settings file could make the upstream return `tool_calls`. No registered coder would apply them, and the user has written that configuration themselves. Aider edits through text blocks (SEARCH/REPLACE, whole file, udiff, patch), which the engine never sees as a `tool_call`.

## Generic SQL tools

PRD Section 4 names `query`, `execute_sql` and `run_sql` as common database tool names. **The tool name is not the argument key.** Each name has its own key in the one real server found for it:

| Client | Tool | Operation kind | Target key | Multi-target | Paths | Version | Commit | Schema |
|---|---|---|---|---|---|---|---|---|
| MCP `postgres` (reference server, archived) | `query` | `sql` | `sql` | no | n/a | archive head | `9be4674d` | https://github.com/modelcontextprotocol/servers-archived/blob/9be4674d1ddf8c469e6461a27a337eeb65f76c2e/src/postgres/index.ts#L98-L118 |
| MCP `supabase` | `execute_sql` | `sql` | `query` | no | n/a | mcp-server-supabase-v0.17.0 | `9092ab90` | https://github.com/supabase-community/supabase-mcp/blob/9092ab9055509fcdfbedcb75edf02d9412feed37/packages/mcp-server-supabase/src/tools/database-operation-tools.ts#L200-L203 |
| MCP `supabase` | `apply_migration` | `sql` | `query` | no | n/a | mcp-server-supabase-v0.17.0 | `9092ab90` | https://github.com/supabase-community/supabase-mcp/blob/9092ab9055509fcdfbedcb75edf02d9412feed37/packages/mcp-server-supabase/src/tools/database-operation-tools.ts#L190-L194 |
| MCP `timeplus` | `run_sql` | `sql` | `query` | no | n/a | main head | `20c52f41` | https://github.com/timeplus-io/mcp-timeplus/blob/20c52f41b6b530152aa3458f4702fe2f30efd000/mcp_timeplus/mcp_server.py#L140-L142 |

- `modelcontextprotocol/servers-archived` (MIT) is archived. Its head is `9be4674d1ddf8c469e6461a27a337eeb65f76c2e` (2025-05-28), and `src/postgres/index.ts` last changed in `37415258b914330d10ed0ea948d67ac8a410a384` (2024-11-19). `query` declares `{sql: string}` and runs it inside `BEGIN TRANSACTION READ ONLY`.
- `supabase-community/supabase-mcp` (Apache-2.0): `execute_sql` takes `{project_id, query}`. `apply_migration` takes `{project_id, name, query}` and its description says to use it "for DDL operations". The PRD does not list `apply_migration`, but it is the DDL-bearing name. `project_id` can be injected by the server (`inject: { project_id }`), so a call may arrive without it.
- `run_sql`: Timeplus (`timeplus-io/mcp-timeplus`, Apache-2.0) defines `@mcp.tool() def run_sql(query: str)`. FastMCP derives the argument key from the parameter name, so the key is `query`. The default branch is `timeplus`, and its head `20c52f41b6b530152aa3458f4702fe2f30efd000` (2025-07-24) is pinned above. Neon's `neondatabase/mcp-server-neon` also exposes a `run_sql` (`mcp/tools/mcp-tool-names.json#L112` maps it to the operation `sql.run`), but its input schema is generated from an operations spec that was not traced here, so **Neon's key is not recorded**. Searches: `gh search code '"run_sql"'` (mostly unrelated code, no MCP definition in the first 30 hits), and a web search "MCP server run_sql tool", which pointed at Timeplus, Neon, Databricks, Dune and Preset listings on glama.ai and policylayer.com.
- **These names arrive prefixed** through both agents: OpenCode sends `<server>_<tool>` (`postgres_query`), and Cline 4.x sends `<server>__<tool>` (`supabase__execute_sql`). So a bare-name mapping matches only a caller that sends MCP tools unprefixed, or a name the deployment writes into its own `tools:`. The same key is not even consistent across servers for one name: `query` → `sql`, `execute_sql` → `query`, `run_sql` → `query`.

## Differences from the PRD-016 survey

PRD-016's survey read OpenCode v1.19.5 and Cline 4.1.26 (and 3.89.2). PRD-017 STORY-001 re-read both, plus OpenCode 2.0.10 and the Cline CLI 3.0.74.

| Client | v1.19.5 / 4.1.26 | 2.0.10 / 3.0.74 | Built-in mapping | Evidence |
|---|---|---|---|---|
| OpenCode | `bash` (`command`) | **`shell`** (`command`, `workdir?`, `timeout?`, `background?`) | `shell` added, `bash` kept | [`plugin/shell.ts#L25-L60`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/shell.ts#L25-L60) |
| OpenCode | `apply_patch` (`patchText`) | **`patch`** (`patchText`), plus an optional `*** Environment ID:` line | `patch` added, `apply_patch` kept | [`plugin/patch.ts#L21-L25`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/patch.ts#L21-L25) |
| OpenCode | `read` / `write` / `edit` take `filePath` | take **`path`** (`read` also lists directories) | `filePath\|path` | [`read.ts#L17-L25`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/read.ts#L17-L25), [`write.ts#L23-L28`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/write.ts#L23-L28), [`edit.ts#L24-L34`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/edit.ts#L24-L34) |
| OpenCode | `task` | **`subagent`** (new `agent` key) | `none`, unmapped | [`plugin/subagent.ts#L29-L48`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/subagent.ts#L29-L48) |
| OpenCode | `skill` (`name`) | `skill` (**`id`**) | `none`, unmapped | [`plugin/skill.ts#L12-L14`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool/plugin/skill.ts#L12-L14) |
| OpenCode | none | **`execute`** (CodeMode, `code`), advertised in every session | `none`, **never `opaque_tools`** | [`tool.ts#L225-L260`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/tool.ts#L225-L260), [`codemode/tool.ts#L60-L108`](https://github.com/anomalyco/opencode/blob/b8cedc1a7a5e2916bbb65dc1d4b620729c261638/packages/core/src/codemode/tool.ts#L60-L108) |
| OpenCode | `lsp`, `todowrite`, `plan_exit`, `invalid` | absent from the direct tool set | v1.19.5 rows and the `lsp` mapping kept | 0 occurrences of `opencode.tool.<name>` in the installed binary |
| OpenCode | `glob`, `grep`, `webfetch`, `websearch`, `question` | same names and target keys (`grep` gains `literal?`) | unchanged | the plugin files above |
| Cline | `run_commands`, `read_files`, `editor`, `apply_patch`, `fetch_web_content`, `search_codebase`, `skills`, `ask_question`, `submit_and_exit` | **no drift.** The CLI is built from the same commit. It also offers `spawn_agent`, `team_*` and (model-dependent) `web_search` outside `--yolo` | unchanged | *Cline CLI 3.0.74* above |

Keys are also not settled inside OpenCode 2.x: `write.ts` carries a source TODO about going back to `filePath` naming. A re-survey is due whenever the pinned version changes.

## Absolute and relative paths

This backs PRD D11 (Section 6.5) and the README's setup step.

- **OpenCode v1.19.5**: `write`, `edit` and `read` describe `filePath` as absolute ("must be absolute, not relative" for `write`). Every executor also accepts a relative path and joins it onto the instance directory: [`write.ts#L41-L43`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/write.ts#L41-L43), [`edit.ts#L80-L82`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/edit.ts#L80-L82), [`read.ts#L235-L236`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/read.ts#L235-L236). `apply_patch` resolves each header path against the instance directory ([`apply_patch.ts#L73`](https://github.com/anomalyco/opencode/blob/810c0eba1a7348036f8bdf61e6632d0c36c6876c/packages/opencode/src/tool/apply_patch.ts#L73)), and the grammar's own example uses relative paths. `lsp` says "absolute or relative". **Expect absolute paths, and handle relative ones.**
- **OpenCode 2.0.10**: `read`, `write` and `edit` take `path` ("File or directory to read", "Path to the file to write to", "File to edit"), with no absolute-path wording. `glob` and `grep` take a `RelativePath`. The executors resolve a path against the session directory (`FileAccess.resolvePath(location.directory, ...)` in `plugin/patch.ts#L90`), so relative paths work.
- **Cline 4.x**: `read_files` (`AbsolutePath`: "The absolute path of a text file to read content from") and `editor` ("The absolute path for the action to be performed on") ask for absolute paths. The SDK executors also resolve a relative path against `cwd`: [`executors/editor.ts#L47-L61`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/executors/editor.ts#L47-L61), [`apply-patch.ts#L64-L73`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/executors/apply-patch.ts#L64-L73), [`file-read.ts#L231-L233`](https://github.com/cline/cline/blob/a459f1d04dea030833b558be645011ab739c463b/sdk/packages/core/src/extensions/tools/executors/file-read.ts#L231-L233). **Expect absolute paths, the same as OpenCode.** This contradicts PRD 6.5 item 2's original "Cline's tools send relative paths".
- **Cline 3.x**: the `GENERIC` specs ask for paths "relative to the current working directory". The `NATIVE_GPT_5` and `NATIVE_NEXT_GEN` specs of `write_to_file` and `replace_in_file` ask for `absolutePath`, and native `execute_command` says "Always use absolute paths". **Both forms arrive as `tool_calls`** (see the fallback note above).
- **Aider**: n/a (no `tool_calls`).

So a deployment of either current client needs `workspace.roots` (PRD 6.5 item 4), and D11's relative-path rule still matters because every executor accepts relative paths.

## Tools that name several targets

This backs PRD F1 ("one `fs_write` per path") and the evasion corpus.

| Client | Tool | Where the targets are |
|---|---|---|
| OpenCode | `apply_patch` | every `*** Add File:`, `*** Update File:`, `*** Move to:` and `*** Delete File:` line in `patchText` |
| OpenCode 2.x | `patch` | the same headers in `patchText` (an optional `*** Environment ID:` line is not a target) |
| Cline 4.x | `apply_patch` | the same headers in `input` |
| Cline 4.x | `run_commands` | each element of `commands[]`, a string or `{command, args[]}` |
| Cline 4.x | `read_files` | `files[].path` (and the aliases listed under Cline 4.x) |
| Cline 4.x | `fetch_web_content` | `requests[].url` |
| Cline 3.x | `apply_patch` | the headers in `input` |

`edit` (OpenCode, both versions), `read` of a directory (OpenCode 2.x: still one path), `editor` (Cline 4.x) and `replace_in_file` / `write_to_file` (Cline 3.x) each name exactly one path.

## Corrections to PRD Section 4

- OpenCode `patch` **does not exist** at v1.19.5. It is `apply_patch`, the target is `patchText`, and the paths are inside the patch text, several per call. It also **replaces** `edit` and `write` for `gpt-` models (not `oss`, not `gpt-4`).
- OpenCode `list` **was removed** (2026-04-15).
- OpenCode has `lsp` (read, `filePath`), plus `websearch`, `task`, `todowrite`, `question`, `skill`, `plan_exit` and `invalid`, which the PRD does not list. There is no `todoread` (PRD 6.6 sample).
- **OpenCode 2.x renamed more** (PRD-017 STORY-001): `bash` to `shell`, `apply_patch` to `patch`, `filePath` to `path` on `read` / `write` / `edit`. See *Differences from the PRD-016 survey*.
- OpenCode `bash` keeps its name, but on Windows the command may be for `pwsh`, `powershell` or `cmd`.
- **Every Cline name in Section 4 is a 3.x name.** Cline 4.x, the current client, uses `run_commands` (`commands[]`), `read_files` (`files[].path`), `editor` (`path`), `apply_patch` (`input`), `fetch_web_content` (`requests[].url`), `search_codebase` (`queries[]`, no path), `skills`, `ask_question` and `submit_and_exit`.
- Cline 4.x targets are **arrays or patch text**, not single string keys, and its executors accept alias shapes (`cmd`, `command`, `file_paths`, `paths`, `file_path`, `filePath`, bare strings).
- In Cline 3.x, `write_to_file` and `replace_in_file` use **`absolutePath`** in the native GPT-5 and next-gen variants, and **`path`** in the generic spec, which `gemini3` and `xs` also send natively. `read_file`, `list_files` and `search_files` use `path` throughout. `browser_action`'s `url` is optional. Only the native variants matter as `tool_calls`. The XML form arrives as text.
- `replace_in_file` names **one** file per call. It is not multi-target.
- `use_mcp_tool` and `access_mcp_resource` are 3.x-only and `tool.unknown` by design. Cline 4.x names MCP tools `<server>__<tool>`, and 3.x native mode names them `<uid>0mcp0<tool>`.
- Generic SQL: `query` carries **`sql`**, while `execute_sql` and `run_sql` carry **`query`**. Supabase's DDL-bearing `apply_migration` (`query`) is not listed. Through OpenCode and Cline all of them arrive **prefixed** with the server name, so the bare names match neither client's MCP tools.
- Cline 4.x asks for **absolute** paths (PRD 6.5 item 2 and the 6.6 sample comment said relative).

## Implications for STORY-004

STORY-004's Technical Notes model a mapping as `ToolMapping(kind, target)`, a kind plus one string key whose value is one string target. The real tools above need more than that. **The mapping must be able to express each of these shapes**, or say for each one that it maps to `tool.malformed` or `tool.unknown`:

1. **A key path into an array of strings**: `run_commands.commands[]`. One `Operation` per element.
2. **A key path into an array of objects**: `read_files.files[].path` and `fetch_web_content.requests[].url`. One `Operation` per element.
3. **Elements of mixed type in one array**: `run_commands.commands[]` may hold a string or `{command, args[]}`. The structured form has no shell parsing, so its target is `command` plus `args` joined, and the shell classifier has to be told it is argv, not a shell line.
4. **Paths inside a string argument**: `apply_patch.patchText` (OpenCode) and `apply_patch.input` (Cline) need an extractor for the `*** Add File:` / `*** Update File:` / `*** Move to:` / `*** Delete File:` grammar. It yields one `fs_write` per header. A patch with no header, or one the extractor cannot read, must not yield zero operations and thereby `allow`: it is `tool.malformed`.
5. **An optional target with a defined default**: OpenCode `glob.path?` and `grep.path?` (absent means the working directory), and Cline 3.x `browser_action.url?` (absent for non-`launch` actions). Under PRD Section 4, "a missing target key" is `tool.malformed`, which would deny every plain `glob`. The mapping needs a per-tool "absent means …" value, or a marker that the target is optional.
6. **Several keys that each carry a target in one call**: `glob.pattern` is itself a path glob (`../**/.env`), next to `glob.path`. `apply_patch`'s `*** Move to:` is a second path in the same section.
7. **Aliases for one key**: Cline 4.x accepts `files`/`file_paths`/`paths`, `path`/`file_path`/`filePath`, and `commands`/`command`/`cmd`. Either the mapping lists every alias, or it reads only the advertised key and treats the others as `tool.malformed`. That is fail-closed, but it denies calls Cline itself would run.
8. **One tool name with two key spellings**: Cline 3.x `write_to_file` and `replace_in_file` send `absolutePath` or `path` depending on the model family. A single-key mapping denies one of the two.
9. **Arguments that are not a JSON object**: the Cline 4.x unions accept a bare string or array. PRD Section 4 already makes a non-object `tool.malformed`. That stays correct, and the test should cover it.
10. **Prefixed MCP names**: `<server>_<tool>` (OpenCode), `<server>__<tool>` with an optional `_<hash8>` suffix (Cline 4.x) and `<uid>0mcp0<tool>` (Cline 3.x). The built-in bare SQL names never match these. Whether the mapping supports a suffix match is STORY-004's decision. Exact-name matching plus a deployment's `tools:` is the fail-closed default.

This story records the shapes. It does not choose the model.

## What this survey shows, and what it does not

- It shows each client's tool surface at **one pinned version**: OpenCode v1.19.5 and 2.0.10, Cline v4.1.26 (the Cline CLI 3.0.74 is built from it) and v3.89.2, and Aider v0.86.0 plus `main` @ `5dc9490`. Clients rename tools: between January and April 2026, OpenCode replaced `patch` and dropped `list`, and Cline 4.x renamed its whole tool set. A renamed tool is `tool.unknown` and a renamed key is `tool.malformed`, both deny (PRD Risk 5). This file is where to look when a client upgrade starts denying ordinary calls. Re-pin and re-read it then.
- It records what the **schema advertises** and what the **executor accepts**. It does not record what a given model actually emits. Models send relative paths to tools that ask for absolute ones, and Cline's lenient unions exist because models send odd shapes.
- It does not cover the VS Code extension's own executors for `editor`, `applyPatch` and `readFile` in Cline 4.x, beyond confirming that the tool names and schemas are the SDK's. Their path handling may differ from the SDK executors cited above.
- OpenCode's `bash` can carry PowerShell or cmd text on Windows (`shell/id.ts`). The POSIX classifier will misread that, and PRD Risk 3 says it must fail closed as `shell.unclassifiable`.
- The MCP servers in *Generic SQL tools* are examples, not a census. `run_sql` has at least one more implementation (Neon) whose key was not traced.
- OpenCode 2.x's `execute` tool runs JavaScript (`code`) that can call `fetch` and MCP tools. **Its code is not inspected.** The built-in policy denies `execute` as `tool.unknown`, and it must not be put in `opaque_tools`.
