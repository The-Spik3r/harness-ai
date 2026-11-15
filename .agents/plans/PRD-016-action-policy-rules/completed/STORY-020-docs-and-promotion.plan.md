---
story: STORY-020
prd: PRD-016
slug: docs-and-promotion
title: README, docs/features.md, docs/roadmap.md, .env.example; full regression; brief promotion verified
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
---

# Plan: Action policy rules documented as shipped, and the PRD promoted

## Summary

Docs only. No file under `app/`, `chat_ui/` or `tests/*.py` changes. After the README split (`e94b2c4`) the README is a lean front page and the deep reference lives in `docs/`, so the work is: one new `### Action policy rules` section in `docs/features.md` (the anchor the story's "link the README section to `docs/features.md#action-policy-rules`" names) that carries every orchestrator note; a short README section plus Features row, Documentation row and Roadmap paragraph that link to it; the `docs/roadmap.md` section rewritten to "built, not yet wired (PRD-017)" with its checkbox left unticked; `.env.example`, `docs/configuration.md`, `docs/api.md` and `docs/deployment.md` updated for the three settings, `GET /audit/actions`, the three `/stats` fields and the new table; the PRD-numbering off-by-one in `docs/features.md` fixed; the PRD-017 hand-off written into `pre-prds/PRE-PRD-016-tool-calling.md`; and the promotion bookkeeping mirrored from PRD-015 (`3e10a2e`, `d294e59`). A throwaway link checker (scratchpad, not committed) proves every relative link in the changed docs resolves.

## User Story

As a platform operator
I want the action policy documented as shipped, with the file format, the permissions and the limits stated plainly
So that I can configure it correctly and know what it does not cover

## Story Reference

- Story file: `.agents/stories/PRD-016-action-policy-rules/STORY-020-docs-and-promotion.md`
- PRD: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` (Sections 4 Documentation, 6.6, 7 F13, 9.2 T10, 14 Risks 3, 4, 8)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (documentation) |
| Complexity | MEDIUM (small code surface, large amount of text that must match the code) |
| Systems Affected | `README.md`, `docs/*.md`, `.env.example`, `pre-prds/`, `.agents/` bookkeeping |
| Story | STORY-020 |
| PRD | PRD-016 |
| Epic Branch | `epic/PRD-016-action-policy-rules` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` holds only `frontend-design` (UI work); this story has no UI. Phase 1b done: listed the directory, nothing matches a docs story.

---

## Findings that shape the plan (opened and verified)

1. **The README no longer holds feature sections.** Features table row at `README.md:150-166`, Documentation table `README.md:299-310`, Roadmap `README.md:314-322`. Details live in `docs/features.md` (sections: Duplicate detection scope, Multi-turn context, Pattern policy `:56`, PII redaction `:134`, Usage limits `:187`, ending at `:224`-`:226`). PRD-011 STORY-013 / PRD-015 STORY-019 precedent wrote into the README *before* the split; follow their structure and tone, but put the long form in `docs/features.md`.
2. **Promotion state today** (verify, do not assume): `pre-prds/PRE-PRD-015-action-policy-rules.md` is already `status: promoted`, `prd: .agents/PRDs/PRD-016-action-policy-rules/PRD.md`; `pre-prds/README.md:28` links PRD-016 with `promoted`. Both done by `d8a0fa4`. Still `status: draft` in `.agents/PRDs/PRD-016-action-policy-rules/PRD.md:5`.
3. **PRD-015 precedent for promotion** (`git show 3e10a2e d294e59`): the docs commit `d294e59` edited `README.md`, `.env.example` and the `pre-prds/README.md` milestone line; the follow-up chore commit `3e10a2e` flipped the PRD's `status: draft` to `status: done` together with the report, story and index. Mirror exactly: pre-prds/README milestone line in the docs commit; PRD `status: done` (and `updated: 2026-11-15`) in the `chore(PRD-016): STORY-020 report; update status + index` commit. PRD-011/012/013 show the same final flip.
4. **Existing built-in policy matches the PRD rule table** (checked by importing `action_config.BUILT_IN_POLICY`): 25 rules, defaults and grants exactly as PRD 6.3; `workspace_roots`, `network_allow`, `shell_allow` all empty; 24 built-in tool mappings. The docs table can be copied from PRD 6.3 without drift.
5. **`RBAC_ROLES_FILE` replaces the matrix wholesale** (`app/services/authz.py:95-120`, JSON `{role: [permission, ...]}`). A deployment that grants `action:sql:write` to a `dba` role must restate every other role's permissions too. This is easy to get wrong; the docs example must show a complete file.
6. `tests/test_config.py:1338-1343` carries a comment that "their `.env.example` lines belong to STORY-020". No test currently checks them. Optional follow-up (see Task 9): add the three vars to a `.env.example` presence test. Not required by the story; flagged as an open question, not planned by default.
7. No test pins README/features/roadmap text (grepped `tests/*.py`); doc edits cannot break the suite except through `.env.example` parsing, which `Settings` does not do.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `docs/features.md` | UPDATE | New `### Action policy rules` section (all notes below); fix PRD numbering at lines 82, 153, 220 |
| `README.md` | UPDATE | Features row, new short `## Action policy rules` section + TOC entry, Documentation row text, Roadmap paragraph |
| `docs/roadmap.md` | UPDATE | Rewrite the `### Action policy rules` section; Planned checkbox stays `[ ]` with new text |
| `.env.example` | UPDATE | Three settings with comments, new `# Action policy rules (PRD-016)` block |
| `docs/configuration.md` | UPDATE | Three rows; extend `PATTERNS_FILE` and `RBAC_ROLES_FILE` rows |
| `docs/api.md` | UPDATE | `GET /audit/actions` section; three new `/stats` fields |
| `docs/deployment.md` | UPDATE | `action_decisions` in "What is stored"; T10; no retention |
| `pre-prds/PRE-PRD-016-tool-calling.md` | UPDATE | `## Hand-off from PRD-016` section (STORY-019 note etc.) |
| `pre-prds/README.md` | UPDATE | Milestone bullet for PRD-016 done; verify the table row (no change expected) |
| `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` | UPDATE (final chore commit only) | `status: draft` to `done`, `updated: 2026-11-15` |
| `.agents/stories/.../STORY-020-docs-and-promotion.md` | UPDATE | frontmatter (plan now; status/report/commit at the end) |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | REGENERATE | via the brief's `gen_index.py` |
| `.agents/reports/PRD-016-action-policy-rules/STORY-020-docs-and-promotion.report.md` | CREATE (implement) | report |
| `.agents/plans/PRD-016-action-policy-rules/completed/` | MOVE plan here (implement) | archive, like STORY-001..019 |

No CREATE of application files. Not touched: `examples/action_policy.yaml` (already carries `apply_patch`, `OPENROUTER_*`, the git read-only subcommands and the header comments for both replacement rules; STORY-007/018). `SECURITY.md` is not in the story; see open question 5.

---

## The section to write: `docs/features.md` -> `### Action policy rules`

Insert after the Usage limits section (after `docs/features.md:224`, before the closing `---`). Anchor must be `#action-policy-rules` (roadmap and README link to it). Suggested sub-structure, bold-lead paragraphs in the file's existing voice (not `####` headings, matching Pattern policy / Usage limits):

1. **Status, first sentence** (F13, AC1): built and tested, **not yet called by `/v1`** (PRD-017). `/v1` still refuses `tools` with `tools_not_supported` ("tool calling is not supported (PRD-017)"). Nothing in the request path calls `evaluate()` today, so no decision row is written by live traffic; the table fills when PRD-017 lands (the Actions view's empty state says so).
2. **What it is**: pure engine `action_policy.evaluate(tool_call, identity)`; adapter maps a client tool name to operations (`shell`, `sql`, `fs_write`, `fs_read`, `http`); classifiers produce rules; the most severe wins, `deny > flag > allow`, first rule at that severity reported (D9). **Plain statement (story note): the harness never executes tools.** It classifies a call the model proposed; the client runs it. Reasons are fixed per-rule strings, never config content (T11). An engine exception is a hard `deny` as `tool.malformed`, logged with the tool name and exception type only.
3. **The rule table**: 25 rules, columns Rule / Class / Built-in default / Grant, copied from PRD 6.3 (verified against `BUILT_IN_POLICY`). One line under it: a rule with no grant cannot be lifted by any role; ten rules (`NON_GRANTABLE_RULES`) never take a grant even from a file (T5).
4. **The six action permissions and how to grant them** (AC1): list `action:sql:write`, `action:sql:ddl`, `action:shell:exec`, `action:fs:write`, `action:net:egress`, `action:secret:read`; no built-in role holds any, **`admin` included** (D6); `holds()` ignores `RBAC_ENABLED` (D7) so turning RBAC off never grants them. A complete `RBAC_ROLES_FILE` JSON example restating the three built-in roles plus a `dba` role holding `action:sql:write` (finding 5: the file replaces the matrix wholesale, so omitted permissions are denied). A grant lifts only the rule it names: `cat ~/.aws/credentials` through `bash` is `secret.read` **and** `shell.unlisted`, so it needs `action:secret:read` and `action:shell:exec` (STORY-014 deviation 1); the `read` tool needs only the first.
5. **The policy file** (AC1): `ACTION_POLICY_FILE`, `examples/action_policy.yaml` (link `../examples/action_policy.yaml`), loaded once at startup in **both** processes (API and chat UI lifespans); built-in policy when unset, no file read. Sections that are present replace the built-in section wholesale (`workspace.roots`, `network.allow`, `shell.allow`, `tools`, `opaque_tools`, `secrets`); `rules:` is the one exception, merged per rule id, a field left out keeps its built-in value, `grant: null` removes a grant (Risk 7, STORY-007). `shell.allow: []` valid; `tools: {}` is a startup error. Startup errors name the file, node and rule and never fall back; list the validations (PRD 9.3: unknown key, unknown rule id, decision not allow/flag/deny, grant outside the six, grant on a non-grantable rule, relative workspace root, bad glob, bad network entry, single-label `*.` wildcard such as `*.com`, `shell.allow` entry with a shell operator, duplicate YAML key). `policy_digest` (SHA-256 over the canonical policy) is stamped on every decision row; `ACTION_SQL_DIALECT` is **not** part of it (STORY-008).
6. **Workspace roots, relative/absolute paths and the OpenCode/Cline setup step** (AC1, S5): lexical normalization (`\` to `/`, drive letter lowercased, `..` resolved); a relative path that does not escape is inside the workspace; an escaping one is `fs.write_outside_workspace`; an absolute path is inside only under a `workspace.roots` entry, and the built-in list is **empty**, so with no configuration every absolute write is denied. **Setup step: set `workspace.roots` for OpenCode and for Cline 4.x** (both send absolute paths; S5, corrected in PRD 6.5/6.6 by STORY-001). Protection is checked before containment (`.env` inside the workspace is still `fs.write_protected`). The built-in network allowlist is also empty: all egress denied until written.
7. **Tool mappings** (STORY-017, S6, S10, STORY-004): built-ins cover OpenCode v1.19.5 (`bash`, `write`, `edit`, `apply_patch`, `read`, `webfetch`, `glob`, `grep`, `lsp`) and Cline 4.x (`run_commands`, `read_files`, `editor`, `apply_patch`, `fetch_web_content`) plus Cline 3.x candidates and generic SQL names; provenance in `tests/corpora/actions/SOURCES.md`. Aider emits no `tool_calls` in any mode (STORY-001). `tools:` in a file **replaces the mapping wholesale**, so `examples/action_policy.yaml` maps OpenCode/SQL tools only: **a Cline deployment must write its own `tools:` and `shell.allow`**; with the built-in policy no Cline shell call is allowed (`shell.allow` is empty). **MCP tool names arrive prefixed** (`postgres_query`, `supabase__execute_sql`), so the built-in bare `query`/`execute_sql`/`run_sql` match only an unprefixed caller; map the prefixed name in `tools:`. **Map `apply_patch`** (OpenCode `gpt-` models send it instead of `edit`/`write`; a `tools:` without it denies every edit from such a session as `tool.unknown`); the sample does (`format: patch`, paths read from the patch headers). Unmapped tool is `tool.unknown` (deny) unless in `opaque_tools`.
8. **Cline 4.x argument shapes the built-ins do not read** (STORY-004): `run_commands` top-level `{command, args?}` / `{command}`, `read_files` with `files` as strings or as one string, `paths` as an object, and bare JSON strings/arrays are `tool.malformed` (deny). Two spellings of one target in one call are `tool.malformed` by design. Also `tool.malformed`: arguments that are not a JSON object, a duplicate JSON key, a missing/non-string target, arguments over `ACTION_MAX_ARGUMENT_CHARACTERS`.
9. **Shell classification and what it cannot read** (STORY-009/010/018, Risk 3):
   - Segments split on `;`, `&&`, `||`, `|`, `&`, newlines; wrappers `command builtin exec nice timeout stdbuf setsid` stripped with strict option tables (`sudo`/`doas`/`env` too).
   - **`shell.unclassifiable` triggers beyond PRD 6.3**: here-documents `<<`, brace expansion, `$'...'`/`$"..."`, heads with glob characters, `(`, `^`, `%VAR%`, `!`, unquoted drive-letter heads (`C:\...`, backslashes lost), `env -S`, `sudo -e`/`-h`, unknown wrapper options (`sudo --bogus`, `nice -10`), nesting deeper than 3 `-c` levels. Plus 6.3's own list (`$(...)`, backticks, `eval`, `source`, process substitution, `<<<`, unbalanced quotes, variable heads).
   - **A segment with a `sudo`/`doas` wrapper or leading `NAME=value` assignments is never `shell.allowlisted`** (`CI=1 npm test` is unlisted); **`python -m pip install` is `shell.package_install`**.
   - **An allowlist entry trusts the whole head**, except the closed table of code-carrying options (`git -c`, `--config-env`, `--upload-pack`, `--receive-pack`, `git clone -u`, `rg --pre`, `pytest -p`, npm `--script-shell`), which become `shell.inline_interpreter`. The example `shell.allow` lists read-only git subcommands only (`git status|diff|log|show`); `git clean`, `git reset --hard`, `git push --force`, `git clone` stay `shell.unlisted`, which the example sets to `flag`.
   - **PowerShell and `cmd.exe` are not classified** (Risk 3): the common destructive heads (`Remove-Item -Recurse`, `rd /s`, `del /s`, `Format-Volume`) are `shell.destructive`, `pwsh/powershell -Command` and `cmd /c` are inline interpreters, `iex` is unclassifiable; everything else that tokenizes cleanly is `shell.unlisted`. `rm -r X` without force in PowerShell keeps the 6.3 reading.
   - Not read at all: `python -c` code, `find -exec`, `awk system()`, `cat .e*` (shell globs on reader heads), `psql -f` and SQL on stdin, data piped into `tee`/`xargs`, `Microsoft.PowerShell.Core\Environment::` paths. `command -v NAME` reads NAME as the head (stricter than bash). Over-blocks: `echo env:` is `secret.read`.
10. **SQL classifier limits** (STORY-008): sqlglot 30.27.0; embedded SQL uses each client's own dialect (`psql`=postgres, `mysql`/`mariadb`=mysql, `sqlite3`=sqlite), **not** `ACTION_SQL_DIALECT`, which governs SQL tools only (`""` = sqlglot generic; a name sqlglot does not know is a startup error). Tautologies the simplifier does not fold (`id = id`) count as scoped writes; side-effecting functions inside a `SELECT` (`pg_sleep`, `lo_import`, `pg_terminate_backend`) are reads; `SET`/`USE`, `RENAME TABLE`, `CREATE USER/ROLE`, `GRANT role TO u` and `EXPLAIN ANALYZE` are `sql.unparsed` (deny, no grant), stricter than the PRD; transaction control (`BEGIN`, `COMMIT`, `ROLLBACK`) is a read; `RELEASE SAVEPOINT` and generic `START TRANSACTION READ WRITE` are unparsed.
11. **Path and secret rules** (STORY-011/013, S9, D15): lexical only. **Symlinks, hard links and 8.3 short names (`GITHUB~1`) are not resolved** (PRD Risk 4: `ln` is not on the sample `shell.allow`, so the first step of a symlink attack is `shell.unlisted`); containment is case-sensitive except the drive letter, so it fails closed on Windows; a Win32 dots-and-spaces segment is outside the workspace. Secret reads: `secrets.files` globs, `/proc/<pid>/environ`, `$NAME`/`${NAME}`/`$env:NAME`/`%NAME%` references, `env:` drive, whole-environment dumps; the reader heads (`cat`, `less`, `head`, `tail`, `source`, `printenv`, `env`, extra heads kept in STORY-013, `cp` included) are treated as secret reads. **Known over-matches of the built-in globs: `.env.example`, `src/id_utils.py` (`id_*`), `$KEYBOARD`** (grantable denies). **PRD D15: a directory search (`grep`, `search_files`, `search_codebase`) can return the contents of a secret file; the classifier sees only the directory. Keep secrets outside the workspace.** `grep`'s `include` and `search_files`' `file_pattern` are read as targets when present.
12. **Network matching is by name only** (STORY-012): no DNS. A name under an allowlisted wildcard that resolves to a private address (`*.nip.io`, DNS rebinding) is matched. IP literals match only an exact IP entry; wildcards never match `localhost`, `*.localhost` or `metadata.google.internal`; wildcards need at least two labels after `*.` and never match the apex; IDNA 2003/2008 deviation characters (`ß`, `ς`, ZWJ, ZWNJ), userinfo (`@`), obfuscated IPv4 (hex/decimal), non-http(s) schemes are `net.unparsed`. Embedded URLs (`curl`, `wget`, HTTPie) go through the same classifier, routing options (`--unix-socket`, proxies) are `net.unparsed`.
13. **The audit** (F10, T10, STORY-015/016): one `action_decisions` row per tool call, **allow included**, in a table of its own linked by a nullable `audit_id` (null until PRD-017 wires it; no foreign key). `arguments_hash` covers the full argument string. **`arguments_preview` can hold up to 500 characters of a denied secret read (T10)**; URL userinfo and query/fragment values are masked as `***` before the cut, everything else is raw. Anyone with `audit:read:*` sees `target_preview`, never the argument preview or hash (not on the API entry). No retention exists, like `audit_logs`. `ACTION_AUDIT_PREVIEW=false` is future work (PRD Section 13).
14. **Reading the decisions** (F11, STORY-016/019): `GET /audit/actions`, three `/stats` fields (details in `docs/api.md`); the admin console **Actions** view at `/admin/actions` (Denied by default, then Flagged, Allowed, All; 500 newest of the chosen kind, with the true total in the scope line). **The console is gated by `ADMIN_TOKEN` only: there is no per-permission check**, a token holder reads every row. **A truncated target shows its full text through a `title` tooltip only, so a touch device cannot read it.** The empty state names PRD-017.
15. **Evidence** (STORY-017/018): `tests/corpora/actions/` holds 70 synthetic calls and 216 evasion variants, none `allow` for any role; `evaluate()` p95 0.4151 ms over 210 calls (the STORY-017 figure; do not re-measure). Corpus and limits: `tests/test_action_corpus.py` docstring.
16. **Upgrade note (AC1, Risk 8, D13)**: `strict_yaml` now loads `PATTERNS_FILE` too. A key written twice anywhere in an existing patterns file, which PyYAML used to resolve silently to the last one, **now stops the boot** with the key and both line numbers. Fix the file; the duplicate was hiding a rule. Also `!!set` duplicates are rejected.
17. **Where this is going** (one paragraph): PRD-017 is the first caller; it decides the denial wire shape and the mixed-response rule. Link `roadmap.md#action-policy-rules`. Closing line like the other sections: full design in [PRD-016](../.agents/PRDs/PRD-016-action-policy-rules/PRD.md).

Keep it plain and long-form like Usage limits; a section this size will be roughly 12-16 bold-lead paragraphs plus the rule table. Do not claim the engine runs on live traffic anywhere.

### `docs/features.md` numbering fixes (AC from orchestrator; STORY-002 left these)

All read-checked: only these three spots are wrong; `PRD-013`, `PRD-011`, `PRD-012` references elsewhere in the file are correct.

- `:82` `(PRD-015)` after "Action policy rules" -> `(PRD-016)`; reword "which is where it is enforced" to say the engine is built (PRD-016), link the new section (`#action-policy-rules`, not `roadmap.md#...`), and that PRD-017 calls it. Keep the "flag is reachable by tests only" sentence; its `(PRD-014)` for the endpoint at the end of that sentence becomes `(PRD-015)` (it is stale twice: `/v1` has shipped and `code` now has HTTP ingress; see open question 3, which decides whether to correct the sentence or only the number).
- `:153` `(PRD-014)` -> `(PRD-015)`.
- `:220` "PRD-014 will add" -> "PRD-015 added" (the endpoint shipped; check the sentence still reads right).
- After edits: `grep -n "PRD-014\|PRD-015" docs/features.md` and confirm every hit now names the right PRD (endpoint = 015, action policy = 016, tool calling = 017, test suite = 014).

---

## README edits

- **Features table** (`README.md:150-166`): add a row **Action policy rules** after "Prompt-injection blocking": built and tested, **not yet called by `/v1`** (PRD-017); every proposed tool call classified (SQL, shell, filesystem, network, secrets), decided per role through six `action:*` permissions in `RBAC_ROLES_FILE`, deny by default, one audit row per call; the harness never executes tools; limits stated in the doc. Link `docs/features.md#action-policy-rules`.
- **New `## Action policy rules`** section between Features (ends `:166`) and Requirements (`:169`), plus a TOC line after `- [Features](#features)` (`README.md:29`): ~25 lines. Status line; a 3-step "turn it on" list (copy `examples/action_policy.yaml`, set `workspace.roots` and `ACTION_POLICY_FILE`; grant permissions in `RBAC_ROLES_FILE`; a Cline deployment writes its own `tools:`/`shell.allow`); a "what it does not cover" bullet list (PowerShell, symlinks/hard links/8.3 names, DNS, directory searches can return secrets, `arguments_preview` 500 characters T10, harness never executes tools); the upgrade note (duplicate key in `PATTERNS_FILE` now stops the boot); link to the full section. Rationale for a README section despite the split: the story's note says "Link the README section", and the PRD's F13 puts the action policy "in the README". See open question 1.
- **Documentation table** (`:305`): extend the Features-in-depth row to list action policy rules; `Configuration` and `API reference` rows already generic; update API reference text to mention `GET /audit/actions`.
- **Roadmap** (`:316-320`): add to **Shipped**: "action policy rules (the engine and its audit; not yet called by `/v1`)"; in **Planned**, change "and action policy rules for tool calls" to "tool calling on `/v1` (PRD-017), which is what calls the action policy". Pre-existing staleness to leave alone: Planned still lists "an OpenAI-compatible endpoint" though `/v1` has shipped (open question 3).
- Pre-existing broken anchor: the Features table links `#openai-compatible-endpoint` (`README.md:154,156`) but that section no longer exists in the README. Not caused by this story; the link checker will report it; open question 3.

## `docs/roadmap.md` edits (AC2)

- `:49`/Planned list (`- [ ] [Action policy rules](#action-policy-rules) - deny destructive SQL, shell, and filesystem operations`): keep **unticked**; text becomes "built, awaiting PRD-017 to call it".
- `### Action policy rules` section (`:71-84` region): replace the closing paragraph's "they are not built yet" with: what is built (engine, 25 rules, six `action:*` permissions, `ACTION_POLICY_FILE`, `action_decisions` table, `GET /audit/actions`, console Actions view, corpora) with a link to `features.md#action-policy-rules`; what PRD-017 adds (accepting `tools`, evaluating each `tool_call` before the response leaves, the denial wire shape D4, the mixed-response rule D1, `audit_id` linking, reword of the Actions empty state). Keep the rule-class table as the original intent; add a sentence that the table is now the built catalogue. Keep the file's `~~strike~~ **Answered:**` convention where an open question gets resolved. Do not touch the "Everything below this line is intended direction" sentence unless open question 3 says to.

## `.env.example` (AC3)

Append a block after the `/v1` block (`.env.example:182-190`), in the existing style (header comment naming the PRD and docs section, then `# comment` line(s) immediately before each `VAR=`; the repo's test regex is `(?m)^#.+\n{var}=`):

```
# Action policy rules (PRD-016; docs/features.md, "Action policy rules")
# Built and tested, not yet called by /v1: PRD-017 is the first caller

# Optional path to a YAML action policy; empty uses the built-in policy and reads
# no file. A file replaces each section it states wholesale (rules: merges per
# rule id) and an invalid one stops startup. Working sample:
# examples/action_policy.yaml. Relative workspace roots are refused
ACTION_POLICY_FILE=

# Ceiling on characters in one tool call's arguments; over it the call is denied as
# tool.malformed (min 1)
ACTION_MAX_ARGUMENT_CHARACTERS=100000

# sqlglot dialect for SQL tools' statements; empty uses the generic dialect. An
# unknown name stops startup. SQL embedded in a shell command (psql, mysql, sqlite3)
# always uses that client's own dialect
ACTION_SQL_DIALECT=
```

Order must follow `Settings` declaration order (`app/config.py:385,392,399`: `ACTION_POLICY_FILE`, `ACTION_MAX_ARGUMENT_CHARACTERS`, `ACTION_SQL_DIALECT`). Verify with the same regex the existing tests use, in a one-off Python check.

## Other docs

- `docs/configuration.md`: three new rows (columns Required/Default/description, `docs/configuration.md:23,35` style) with defaults, validation (min 1; dialect checked at startup) and a link to the section; `PATTERNS_FILE` row (`:35`) gains "a key written twice in the file stops startup (PRD-016 D13)"; `RBAC_ROLES_FILE` row (`:23`) gains "can grant the six `action:*` permissions".
- `docs/api.md`: after `GET /audit` add `### GET /audit/actions` (scoping `audit:read:all`/`audit:read:own` exactly like `GET /audit`; `?limit=` 1-500 default 100; `?decision=allow|flag|deny`, 422 otherwise; the 15-field entry from PRD Section 10 with `classifications` decoded; `arguments_preview`, `arguments_hash`, `session_id` deliberately not on the entry; empty until PRD-017). `GET /stats` (`docs/api.md:214-240`): add `actions_denied`, `actions_flagged`, `actions_allowed` to the JSON example and a sentence (additive, 0 until PRD-017; they count `action_decisions` rows). Mention in a note that Docker's Caddy routes `/audit/actions` (STORY-016, `tests/test_caddyfile_routes.py`).
- `docs/deployment.md` ("What is stored", `:17-30`): a paragraph for `action_decisions` (what a row holds, 500-character preview T10, no retention, no FK, `audit_logs` unchanged).
- `docs/testing.md`: one line naming `tests/test_action_corpus.py` and the benchmark command `... -m benchmark --run-benchmark` only if the file already has a place for corpora; otherwise skip (optional).

## PRD-017 hand-off: `pre-prds/PRE-PRD-016-tool-calling.md`

Add `## Hand-off from PRD-016` (before `## Open decisions`, or after `## Proposed scope`), plain bullets:

- What exists: `evaluate`/`evaluate_all`, `action_audit.record(decisions, identity, audit_id, session_id)`, `action_config.load()` in both lifespans, six `action:*` permissions, `GET /audit/actions`, `/stats` fields, console Actions view, corpora.
- What PRD-017 must do: lift the `tools_not_supported` refusal; call `evaluate_all` before the response leaves; pass `audit_id` into `record()`; decide D1 (mixed responses) and D4 (denial wire shape); reword the three "(PRD-017)" runtime strings only if wording changes (they already say PRD-017).
- **STORY-019 orchestrator note, verbatim intent**: the admin console Actions empty-state copy names PRD-017 and **must be reworded when tool calls go live**; the console is gated by `ADMIN_TOKEN` only (no per-permission check); truncated targets show full text through a `title` tooltip only (not on touch).
- Open items carried: S9 (directory-search contents) is a stated limitation not a rule; S6 (prefixed MCP names) means an agent deployment must map its MCP tools in `tools:`; Cline deployments must write `tools:` and `shell.allow`; the sample maps OpenCode only.
- Frontmatter: leave `status: draft`; it is PRD-017's brief. Do **not** renumber its `depends_on: [PRD-015, PRD-016]` (they are correct under the final numbering).

## `pre-prds/README.md`

- Verify row `:28` is already correct (`promoted`, links PRD-016). No change expected.
- Add the milestone sentence next to the Milestone bullets (`:41-42` region), mirroring `d294e59`'s Milestone 1 wording: "**PRD-016 done** (reached 2026-11-15): the action policy engine and its audit are built and merged on `epic/PRD-016-action-policy-rules` (20 stories), not yet called by `/v1`; PRD-017 wires it." Keep tense honest: the branch is not merged to `main` at this point (PRD-015's `d294e59` said "not yet merged"; its later merge commit corrected it).

---

## Tasks (execute in order; each atomic, verifiable)

### Task 1: Verify the promotion state

- **Action**: read only.
- **Implement**: confirm `PRE-PRD-015` `status: promoted`, `prd:` path resolves; `pre-prds/README.md:28` row; PRD frontmatter `status: draft`. Fix any drift found (none expected).
- **Validate**: `grep -n "status:\|prd:" pre-prds/PRE-PRD-015-action-policy-rules.md`; `test -f .agents/PRDs/PRD-016-action-policy-rules/PRD.md`.

### Task 2: `.env.example`

- **File**: `.env.example` (UPDATE). Block above. **Mirror**: `.env.example:182-190` (V1 block) and the `(?m)^#.+\n{var}=` rule used at `tests/test_config.py:64-68,224-228`.
- **Validate**: one-off Python check that each of the three vars has a comment line directly before it and appears in `Settings` order; `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py -q -p no:cacheprovider` (no test modified, proves nothing broke).

### Task 3: `docs/features.md` numbering fixes (lines 82, 153, 220)

- **Validate**: the grep in the section above.

### Task 4: `docs/features.md` Action policy rules section

- **Implement**: items 1-17. Copy the rule table from PRD 6.3 and re-verify against `action_config.BUILT_IN_POLICY` (Python snippet in Findings 4). Every factual claim is traceable to a report or the code; where unsure, re-read the named module docstring (`shell.py`, `paths.py`, `network.py`, `sql.py`, `tests/test_action_corpus.py`).
- **Mirror**: Usage limits `docs/features.md:187-224` for voice (bold lead-ins, closing "full design" line).
- **Validate**: link check (Task 11); read-through against the Story's ACs and the ten orchestrator notes (checklist below).

### Task 5: `README.md`

- Features row, TOC line, new section, Documentation row, Roadmap paragraphs. **Mirror**: other Features rows (`README.md:154-165`); README tone is short.

### Task 6: `docs/roadmap.md`

- Rewrite section and checkbox text; keep `[ ]`.

### Task 7: `docs/configuration.md`, `docs/api.md`, `docs/deployment.md` (and optional `docs/testing.md`)

- As specified above.

### Task 8: `pre-prds/PRE-PRD-016-tool-calling.md` and `pre-prds/README.md`

- As specified above.

### Task 9: (optional, only if the orchestrator says yes: open question 4) a presence test for the three vars in `.env.example`

- Default: **do not do it**; the story says docs, and `tests/test_config.py:1338` only says the lines belong to STORY-020. If approved: add one test beside `tests/test_config.py:1345` using the existing `_env_example_comment` helper (`tests/test_config.py:1330`) and a PRD-016 comment; then `tests/test_config.py` must be re-run.

### Task 10: link and anchor check (AC4, "every relative link in the changed docs resolves")

- **Implement**: a throwaway script in the scratchpad (not committed; Windows, cp1252 trap: open files with `encoding="utf-8"`) that, for each changed `.md` file, finds every `[text](target)`, skips `http(s):`/`mailto:`, resolves the path part relative to the file, asserts it exists, and, for `#anchor`, asserts the target file has a heading whose GitHub slug equals it. Run on `README.md`, `docs/features.md`, `docs/roadmap.md`, `docs/configuration.md`, `docs/api.md`, `docs/deployment.md`, `pre-prds/PRE-PRD-016-tool-calling.md`, `pre-prds/README.md`.
- **Expected pre-existing failures**: README `#openai-compatible-endpoint` anchors (see above) and any other anchor already broken on `main`. Compare against `git stash`-free baseline by running the script on `git show HEAD:<file>` text for the same files, and report only **new** failures as the story's fix list; pre-existing ones go in the report.
- **Validate**: zero new failures; new section anchors `#action-policy-rules` in features and roadmap resolve.

### Task 11: regression runs (AC4) per the brief, not the full suite

- The orchestrator runs the full suite once at the end (user decision). In the report's Validation table write "Full suite: deferred to orchestrator (user decision)". Docs-only diff, so run only:
  `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py tests/test_action_corpus.py -q -p no:cacheprovider`, plus `.venv/Scripts/python -c "from app.main import app; print('OK')"`.
- Confirm "no pre-existing assertion changed except those STORY-002 and STORY-005 changed" with `git diff main --stat -- tests/` and `git diff main -- tests/ | grep '^-' | grep -v '^---'` cross-checked against the STORY-002/005/016/019 reports' lists. STORY-016 and STORY-019 also changed pinned assertions (each with a PRD-016 comment); the story text predates them. Report this as an AC wording discrepancy, not a failure.

### Task 12: bookkeeping (Phase 5 of implement)

- Commit 1 (docs): all files above, the archived plan, the report with `commit: pending`. Stage explicitly. Message `docs(PRD-016): STORY-020 action policy rules documented as built, not yet called by /v1`.
- Commit 2 `chore(PRD-016): STORY-020 report; update status + index`: SHA into report and story, story `status: done`, `report:` path, PRD `status: done`, `updated: 2026-11-15`, regenerate index (`errors: none`). Mirrors `3e10a2e`.

---

## Orchestrator-note coverage checklist (every one must be in a named place)

| Note | Where it lands |
|---|---|
| STORY-019: PRD-017 hand-off, ADMIN_TOKEN gate, `title` tooltip | PRE-PRD-016 hand-off section; `features.md` item 14; README bullet is optional |
| STORY-018: limitations; allowlist trusts head except code-option table; example `shell.allow` read-only git | `features.md` item 9, README "does not cover" |
| STORY-017: `tools:` replaces wholesale; Cline writes own `tools:`/`shell.allow`; built-in allows no Cline shell | `features.md` item 7, README step 3 |
| STORY-013: per-client dialects not `ACTION_SQL_DIALECT`; reader heads as secret reads; `.env.example`/`$KEYBOARD` over-matches | `features.md` items 10, 11 |
| STORY-012: name-only network matching, nip.io/rebinding, IP literal rule, wildcard exclusions, IDNA deviation chars | `features.md` item 12 |
| STORY-011: lexical paths, symlinks/hard links/8.3, case-sensitive except drive letter | `features.md` item 11, README |
| STORY-010: sudo/doas/assignments never allowlisted; `python -m pip install` | `features.md` item 9 |
| STORY-009: extra `shell.unclassifiable` triggers; wrapper list with strict option tables | `features.md` item 9 |
| STORY-008: SQL limitations; dialect not in digest | `features.md` item 10, item 5 |
| STORY-004: Cline 4.x unread shapes as `tool.malformed`; two spellings malformed | `features.md` item 8 |
| STORY-001 S5, S6, S9, S10; D15 | items 6, 7, 11 |
| T10 `arguments_preview` 500 chars; harness never executes tools | items 2, 13; README |
| `PATTERNS_FILE` duplicate-key upgrade note (D13, Risk 8) | item 16; README section; configuration.md row |
| PRD numbering off-by-one | `features.md:82,153,220` |
| Three settings | `.env.example`, `docs/configuration.md`, README |
| Promotion (PRD status, brief status, `pre-prds/README.md`, roadmap) | Tasks 1, 6, 8, 12 |

Further doc items collected from the reports (not in the story text): grants lift only the rule they name (STORY-014); `RBAC_ROLES_FILE` replaces the matrix (finding 5); `rules:` per-id merge and `grant: null` (STORY-007); single-label wildcard refused, relative roots refused, shell-operator entries refused (STORY-007); the engine fails closed on any exception (STORY-014); `policy_digest` and that it excludes the dialect; URL redaction in `arguments_preview` (STORY-015); decisions are written only when PRD-017 calls `record()` (nothing in the request path calls it); `/audit/actions` is routed by Caddy (STORY-016); `evaluate()` p95 0.4151 ms (STORY-017); corpus sizes 70/216 (STORY-017/018); both lifespans load the policy so a bad file stops both the API and the chat UI (STORY-006).

---

## End-to-End Tests

- [ ] `ACTION_POLICY_FILE=examples/action_policy.yaml` loads through the real loader (already proven by `tests/test_action_corpus.py`; re-run it)
- [ ] The three `.env.example` vars parse: `Settings(_env_file=".env.example")` is not used by the repo; instead confirm the file has the lines in `Settings` order (Task 2)
- [ ] Every relative link and anchor in the changed docs resolves (Task 10)
- [ ] `grep -rn "they are not built yet" docs README.md` returns nothing

## Validation

```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_config.py tests/test_action_corpus.py -q -p no:cacheprovider
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONIOENCODING=utf-8 .venv/Scripts/python "C:/Users/nahue/AppData/Local/Temp/claude/G--coding-harness-ai/20d13059-18e1-4943-818b-68572342f8ca/scratchpad/gen_index.py"   # errors: none
git diff --stat   # only docs, pre-prds, .env.example, .agents bookkeeping; nothing under app/, chat_ui/, tests/
```

---

## Risks

| Risk | Mitigation |
|---|---|
| Docs claim something the code does not do | Every factual line is traced to a report or module docstring; the rule table is checked against `BUILT_IN_POLICY` by script; the live-traffic caveat is stated first |
| A claim that the engine "protects" `/v1` today | Wording rule: "built, not yet called"; `grep -n "enforce" ` pass over the new text |
| Link checker flags pre-existing breakage | Baseline comparison; only new failures are fixed |
| `RBAC_ROLES_FILE` example omits a role, so a reader's copy locks `admin` out of harness permissions | Example restates the full built-in matrix; verify permission names against `authz.ROLE_PERMISSIONS` when writing |
| The AC "no pre-existing assertion changed except STORY-002 and 005" is stale | Report it; STORY-016 and STORY-019 also changed pinned assertions, each commented |
| Windows encoding when scripting reads | UTF-8 explicit; `PYTHONUTF8=1` |

## Open questions (for the orchestrator)

1. README section or features.md only? Plan adds a short README section plus the long form in `docs/features.md` (story note: "link the README section"; PRD F13: "README and docs/features.md"). Cheaper alternative: Features row only.
2. No real bug found in the reports. Two fail-closed gaps are documented as limitations and not planned as code: STORY-011's relative path with an all-dots segment was later closed by STORY-018 (done); STORY-008's `RELEASE SAVEPOINT`/generic `START TRANSACTION READ WRITE` unparsed. None needs action.
3. Pre-existing staleness outside this story: `docs/roadmap.md` still lists the OpenAI-compatible endpoint under Planned and says "The only ingress that exists today is `POST /query`"; README Planned says the same and its Features table links a missing `#openai-compatible-endpoint` anchor; `docs/features.md:82/153` say `code` has no HTTP ingress. Plan: fix only the PRD numbers and the action-policy wording; report the rest. Say if you want them corrected here.
4. Add a `.env.example` presence test for the three vars (Task 9)? Default no.
5. `SECURITY.md` has no PRD references; not touched. Say if the T10 preview note belongs there.

---

## Acceptance Criteria

(Copied from STORY-020)

- [ ] `docs/features.md` and the README describe Action policy rules as built but not yet called by `/v1` (PRD-017): rule table, file format with `examples/action_policy.yaml`, six permissions and how to grant them in `RBAC_ROLES_FILE`, relative/absolute path rule and the OpenCode (and Cline) workspace-root setup step, the PowerShell and symlink limitations, and the `PATTERNS_FILE` duplicate-key upgrade note
- [ ] `docs/roadmap.md`'s Action policy rules section no longer says "not built yet"; says what is built and what PRD-017 adds; checkbox stays unticked
- [ ] `.env.example` has `ACTION_POLICY_FILE`, `ACTION_MAX_ARGUMENT_CHARACTERS`, `ACTION_SQL_DIALECT` with comments in the existing style
- [ ] Full suite green (deferred to orchestrator, user decision); no pre-existing assertion changed except those STORY-002 and STORY-005 changed (plus STORY-016 / STORY-019, see Task 11), each with a PRD-016 comment; every relative link in the changed docs resolves
- [ ] Brief `PRE-PRD-015` is `status: promoted` with `prd:` pointing at PRD-016; the track table links PRD-016; drift fixed if any
- [ ] All tasks completed; follows existing patterns
