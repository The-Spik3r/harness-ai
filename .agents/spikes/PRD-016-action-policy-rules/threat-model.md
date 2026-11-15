---
prd: PRD-016
story: STORY-001
date: 2026-11-15
conclusion: 8 of 13 threats answered by a Section 6.3 rule; 5 open findings (T4, T7, T10, T11, T13); 10 new findings from the adapter survey, 3 of them gaps
---

# Spike: the action threat model, T1–T13 against the rule catalogue

**Conclusion: eight of the thirteen threats in PRD Section 9.2 are answered by a Section 6.3 rule, and five are open findings.** T1, T2, T3, T5, T6, T8, T9 and T12 each have at least one rule that fires and a proof: a corpus group (`synthetic/` or `evasion/`), a unit test, or both. T9 and T12 depend on triggers that the 6.3 table does not state. No rule answers T4, T7, T10, T11 or T13. Each of those is answered by a mechanism (`holds()`, startup validation, reason templates) or by nothing, and they are listed under *Open findings*. The adapter survey (`tests/corpora/actions/SOURCES.md`) adds ten findings, S1–S10, that the PRD did not have. In three of them (S3, S7, S9) a 6.3 rule fires but does not cover the threat: S3 is PowerShell text under a grantable `shell.unlisted`, S7 is a secret glob in `glob.pattern`, and S9 is directory searches that return secret contents.

## Method

- Threats are PRD Section 9.2 T1–T13, verbatim in substance.
- A rule is cited only if it is in the Section 6.3 catalogue, spelled exactly. "Other mechanism" is anything that is not a rule: `holds()` (D7), the policy-file validator (Section 9.3), the `evaluate()` boundary (F7), reason templates (T11).
- Corpus groups are `synthetic/` and `evasion/` (PRD F12, Section 11 *Corpus criteria*), built in STORY-017 and STORY-018. When a unit test is the real proof, the story is named, and the corpus group is still named if one also applies.
- A threat is an open finding when no 6.3 rule is what stops it, even if something else does. Such a threat is not undefended. The AC asks that it be listed, so nothing is hidden behind a rule that does not apply.

## Mapping

| # | Threat | Rule(s) in 6.3 that answer it | Other mechanism (not a rule) | Proven by (corpus group / test) | Story |
|---|---|---|---|---|---|
| T1 | A text-clean prompt yields a destructive tool call | `sql.ddl`, `sql.dcl`, `sql.unscoped_write`, `sql.write`, `shell.destructive`, `shell.package_install`, `shell.service_control`, `fs.write_protected`, `fs.write_outside_workspace`, `net.unlisted`, `secret.read` | The engine classifies the call after the model wrote it. Not enforced live until PRD-017 | `synthetic/`: every rule produced at least once, including the brief's five criteria verbatim | STORY-008–STORY-013, STORY-017 |
| T2 | Obfuscation: quoting, escapes, base64, `eval`, `$(…)`, chaining | `shell.unclassifiable`, `shell.pipe_to_interpreter`, `shell.inline_interpreter`, `shell.destructive`, `sql.unparsed` | `shlex` resolves quotes. Segment split plus most-severe-wins (D9) | `evasion/`: quoting, flag permutations, wrappers, chaining, substitution, base64-to-interpreter, nested `bash -c`, SQL comments and casing. None may be `allow` | STORY-009, STORY-010, STORY-008, STORY-018 |
| T3 | An unknown tool as a bypass | `tool.unknown`, `tool.opaque` | `opaque_tools` is the only way to open a name | `synthetic/`: an unmapped name is `deny` for every role. `evasion/`: renamed and prefixed names (`postgres_query`, `supabase__execute_sql`, `srv0mcp0query`) are not `allow` | STORY-004, STORY-014, STORY-017, STORY-018 |
| T4 | The escape hatch grants everything (`RBAC_ENABLED=false`) | — | `holds()` never consults `RBAC_ENABLED` (D7) | Unit test: the grant suite with RBAC off, every grantable rule falls to its default. `synthetic/` (the `dba` grant) runs with RBAC on only | STORY-003, STORY-014 |
| T5 | A role grant reaches a rule nobody should lift | The ten non-grantable rules: `sql.unscoped_write`, `sql.dcl`, `sql.unparsed`, `shell.destructive`, `shell.pipe_to_interpreter`, `shell.unclassifiable`, `fs.write_protected`, `net.unparsed`, `tool.unknown`, `tool.malformed` | Startup refuses a `grant` on any of them (Section 9.3) | `synthetic/`: `dba` (holding `action:sql:write`) is still denied `sql.unscoped_write`. Failing-file tests for the startup refusal | STORY-003, STORY-007, STORY-017 |
| T6 | Path tricks: `..`, mixed separators, `~`, case, drive letters | `fs.write_outside_workspace`, `fs.write_protected`, `secret.read` | Lexical normalization before matching (6.5 item 1). Symlinks are **not** answered (Risk 4) | `evasion/`: path tricks (`..`, `\`, `C:/`, case, trailing `/`). Unit test per trick | STORY-011, STORY-013, STORY-018 |
| T7 | A policy file that silently allows | — | Startup validation (Section 9.3): unknown keys, rule ids, decisions, permissions; `tools: {}` refused; `rules:` merged per id | Failing-file tests, one per Section 9.3 rule. No corpus group | STORY-005, STORY-006, STORY-007 |
| T8 | SSRF via allowlist wildcards | `net.unparsed`, `net.unlisted`, `net.allowlisted` | Wildcards never match loopback, link-local, metadata or private literals (6.5) | `evasion/`: URL tricks (userinfo, IP-in-decimal, IDNA lookalike) | STORY-012, STORY-018 |
| T9 | A classifier bug raises and the call slips through | `tool.malformed` | The `evaluate()` boundary catches, logs at `ERROR` without arguments, and returns `deny` (F7) | Unit test: a classifier patched to raise yields `deny` / `tool.malformed`. No corpus group (the corpus cannot make a classifier raise) | STORY-014 |
| T10 | Secrets in the audit (`arguments_preview`) | — | Accepted risk, behind `audit:read:*`. `ACTION_AUDIT_PREVIEW=false` is future work (Section 13) | Nothing proves it away. STORY-015 should have a test that records the accepted behaviour, so a change to it is visible | STORY-015 |
| T11 | Reason strings leak the policy | — | `reason` is a fixed per-rule template plus the matched fragment of the call, never a configured value | Unit test over every rule: the reason contains no `network.allow` host and no `workspace.roots` path. `synthetic/` can assert it on every entry | STORY-014, STORY-017 |
| T12 | ReDoS or cost: huge arguments, deep nesting | `tool.malformed` (over `ACTION_MAX_ARGUMENT_CHARACTERS`), `shell.unclassifiable` (nesting beyond depth 3) | Length checked before `json.loads`. Globs compiled at load. No user regex | Unit test: over-length `arguments`, `json.loads` never called. `evasion/`: nested `bash -c` past depth 3 | STORY-004, STORY-010, STORY-018 |
| T13 | The policy file as a vector (a writable `ACTION_POLICY_FILE`) | — | The trust boundary `RBAC_ROLES_FILE` and `PATTERNS_FILE` already sit on. No new mitigation claimed | Nothing | — |

## Open findings

Threats that no Section 6.3 rule answers.

1. **T4, `RBAC_ENABLED=false`.** Answered by `holds()` (D7), which is a function, not a rule. The proof is a unit test in STORY-003/STORY-014. The corpus cannot prove it, because F12 loads the suite with RBAC on.
2. **T7, a policy file that silently allows.** Answered at startup by the Section 9.3 validator, before any rule exists to fire. The proof is the failing-file tests (STORY-007). One gap is related: Section 9.3 refuses `tools: {}`, but a `tools:` section that maps only names the agent never sends (for example only the 3.x Cline names, with a 4.x client) is accepted, and denies everything as `tool.unknown`. That fails closed, so it is an availability problem, not a bypass.
3. **T10, secrets in the audit.** Nothing answers it. The PRD accepts it in writing. It is recorded so STORY-015 pins the behaviour rather than drifting into it.
4. **T11, reason strings leak the policy.** Answered by the reason templates (STORY-014), not by a rule.
5. **T13, the policy file as a vector.** Nothing answers it inside the harness, by design.

Two threats are answered by a rule whose 6.3 "Produced when" text does not mention the trigger:

- **T9**: 6.3 defines `tool.malformed` as bad `arguments` or over-length input. F7 also produces it when a classifier raises. The behaviour is in F7. 6.3's wording is incomplete, and STORY-003's `RuleId` docstring or STORY-014 should state the extra trigger.
- **T12**: depth beyond 3 (D3) becomes `shell.unclassifiable`, but 6.3's trigger list for that rule does not say "nesting deeper than 3". STORY-010 should test it explicitly.

## New findings from the adapter survey

From `tests/corpora/actions/SOURCES.md`. Each one either maps onto a 6.3 rule, or is a gap.

| # | Finding | Rule that answers it (6.3) | Gap or decision | Story |
|---|---|---|---|---|
| S1 | **Paths inside patch text.** OpenCode `apply_patch.patchText` and Cline `apply_patch.input` name their files on `*** Add/Update/Delete File:` and `*** Move to:` lines, several per call | `fs.write_in_workspace`, `fs.write_outside_workspace`, `fs.write_protected`, once the paths are extracted | If the adapter reads the patch as one opaque target, a write to `.env` inside a patch escapes `fs.write_protected`. A patch it cannot parse, or one with no header, must be `tool.malformed`, never zero operations (which would be `allow`) | STORY-004, STORY-011, STORY-018 |
| S2 | **Cline 4.x lenient aliases** (`cmd`, `command`, `file_paths`, `paths`, `file_path`, `filePath`) | `tool.malformed` if not mapped | Fail closed, but denies calls Cline would run. If they are mapped, every alias needs a test, or one unmapped alias is a key the classifier never reads | STORY-004 |
| S3 | **PowerShell or cmd text in a shell call.** OpenCode's `bash` may run `pwsh`/`powershell`/`cmd`. Cline's `run_commands` runs the user's shell | `shell.unclassifiable` when tokenizing fails; `shell.unlisted` otherwise | **Gap.** `Remove-Item -Recurse -Force C:\` tokenizes cleanly under POSIX `shlex`. Its head is not on `shell.allow`, so it is `shell.unlisted`, which **is grantable** (`action:shell:exec`). `shell.destructive` knows `rm`, not `Remove-Item`/`rd /s /q`/`del /s`. A role holding `action:shell:exec` would be allowed a destructive PowerShell command. Risk 3's "never `allow`" holds only without the grant. STORY-010 should add the common PowerShell/cmd destructive heads to `shell.destructive`, or say this in the README | STORY-010, STORY-018, STORY-020 |
| S4 | **Structured argv** in Cline 4.x `run_commands`: `{command, args[]}` runs without shell parsing | `shell.*` on the joined line | Joining `args` with spaces and re-tokenizing changes meaning (an arg with a space or `;`). The adapter must quote when joining, or classify argv directly | STORY-004, STORY-009 |
| S5 | **Cline 4.x asks for absolute paths** (as OpenCode does) | `fs.write_outside_workspace` (deny, grantable) | Not a bypass. With the built-in empty `workspace.roots`, every Cline 4.x write is denied (Risk 2, over-blocking). The README must tell Cline deployments to set roots too, not only OpenCode ones. PRD 6.5 corrected in STORY-001 | STORY-011, STORY-020 |
| S6 | **MCP names arrive prefixed** (`postgres_query`, `supabase__execute_sql`, `<uid>0mcp0query`, a hashed suffix past 64 characters) | `tool.unknown` | Fail closed, so not a T3 bypass. But the built-in generic SQL mapping (`query`, `execute_sql`, `run_sql`) matches neither client by default, so `sql.*` rules fire only for a deployment that maps the prefixed name in `tools:` | STORY-004, STORY-020 |
| S7 | **`glob.pattern` is a path.** OpenCode `glob` takes `pattern` (for example `../../**/.env*`) next to an optional `path` | `secret.read` and `fs.read`, only if the pattern is classified | **Gap** if the mapping reads only `path`. A secret-file enumeration via `pattern` is then `fs.read` (allow) | STORY-004, STORY-013 |
| S8 | **Optional targets.** OpenCode `glob.path?` and `grep.path?`, Cline 3.x `browser_action.url?` | `tool.malformed` under PRD Section 4 ("a missing target key") | Fail closed, but a plain `glob` would be denied every time. STORY-004 must define the default (the working directory, `.`) | STORY-004 |
| S9 | **Directory-scoped reads return file contents.** `grep` (OpenCode), `search_codebase` (Cline 4.x) and `search_files` (Cline 3.x) search a directory, which may hold `.env` | `fs.read` on the directory | **Gap.** `secret.read` matches the target path, and the target is `.` or a directory, so a regex search for `KEY=` over the workspace is `fs.read` (allow) and returns the secret. No 6.3 rule covers it. Candidates: classify the search as `secret.read` when it is not scoped away from secret globs, or record it as a stated limitation. A decision for STORY-013 | STORY-013, STORY-017 |
| S10 | **`apply_patch` replaces `edit`/`write` for OpenCode `gpt-` models** | — | Availability: a deployment `tools:` without `apply_patch` denies every edit from such a session as `tool.unknown`. The README and `examples/action_policy.yaml` should map it | STORY-007, STORY-020 |

## What this does not cover

- **Symlinks** (Risk 4) and **DNS rebinding**: the harness cannot see the client's filesystem or resolver. 6.5 and 9.4 say so, and nothing here changes it.
- **Model behaviour.** The survey records what each client's schema advertises and what its executor accepts, not what a model emits. Unexpected shapes are `tool.malformed` by default.
- **Live enforcement.** Nothing calls `evaluate()` in the request path until PRD-017, so every threat here is proven against corpora and unit tests only.
- **MCP payloads.** Out of scope (PRD Section 4 *Out of Scope*, Section 13). Every MCP tool name is `tool.unknown` unless mapped.
