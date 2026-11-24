---
story: STORY-021
prd: PRD-023
slug: docs-and-roadmap
title: "Docs: README, features (MCP gateway and skills), roadmap, `.env.example`, examples"
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-24
---

# Plan: Docs for the MCP gateway and skills

## Summary

Documentation only, plus one docs test. Write a `### MCP gateway and skills` section in `docs/features.md`, tick the roadmap item, add README and `docs/configuration.md` entries, reword every "the harness never executes tools" sentence, and fix the leftover rule counts (25 -> 26, ten -> eleven). Everything is verified against `app/` today (below). A new `tests/test_mcp_docs.py` (pattern: `tests/test_providers_docs.py`) pins settings, counts, relative links and anchors. This is the last story: the implementer sets the PRD `status: done`.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-021-docs-and-roadmap.md`
- PRD sections used: Scope note, §4 Documentation, §6.2, §6.6, §6.8, §9.2, §9.3, §9.4, §13
- Systems affected: `docs/`, `README.md`, tests. No `app/` change; `.env.example` and `examples/mcp.yaml` already exist and are correct (see Verified facts).

## Design Decisions

none beyond the tasks. Wording rules: correlation is "correlation, not proof"; `annotations` are passed through from the upstream and unverified (`app/services/mcp_gateway.py:194-195` copies `tool.annotations` as-is); describe code as it is, not as the PRD hoped.

## Verified facts (cite these in the docs; re-open before writing)

- **Nine settings** `app/config.py:457-465`: `MCP_ENABLED=False`, `MCP_CONFIG_FILE=""`, `MCP_CALL_TIMEOUT_SECONDS=60` (1-600, `:894`), `MCP_MAX_REQUEST_BYTES=1048576` (>=1024, `:906`), `MCP_MAX_RESULT_BYTES=1048576` (>=1024, `:918`), `MCP_TOOLS_CACHE_SECONDS=60` (0-86400, 0 = no cache, `:930`), `MCP_UPSTREAM_SESSION_IDLE_SECONDS=300` (>=10, `:942`), `MCP_LINK_WINDOW_SECONDS=300` (0-86400, 0 = no linking, `:954`), `MCP_ALLOWED_ORIGINS=""` (bare origins, `:967`, property `:1113`). **Two defaults differ from the PRD §9.3 table** (cache 300 -> 60, link window 600 -> 300): document the code's. `.env.example:234-270` already carries all nine with the code's defaults, so it needs no edit (the test below confirms it).
- **Endpoint**: `POST /mcp` only, mounted when `MCP_ENABLED` (`app/main.py:58-59`, `app/routers/mcp.py:255`); methods `tools/list`, `tools/call`, `prompts/list`, `prompts/get` (`app/routers/mcp.py:242-246`); protocol versions `2025-03-26`, `2025-06-18`, `2025-11-25` (`:54`); the `2026-07-28` handshake is refused (`:~300`, D17). Gate order at `:255-275`: break-glass 403, `mcp:connect` 403, `Origin` check, size cap, JSON media type 415. `Caddyfile:5` already routes `/mcp /skills`.
- **Permissions** `app/services/authz.py:60-72,107`: `mcp:connect` (held by `admin` and `user`, not `auditor`), `skill:<id>` pattern `skill:[a-z0-9][a-z0-9-]{0,47}`; no built-in role holds a skill. `GET /skills` needs `stats:read` (`app/routers/admin.py:250-262`); MCP off answers 200 `{skills:[], mcp_config_digest:null}`.
- **Rule counts**: `len(RULE_IDS)` = 26 and `len(NON_GRANTABLE_RULES)` = 11 (run today; `app/services/action_classifiers/__init__.py:85`, `app/services/action_config.py:58-59`). The eleventh is `tool.not_in_skill` (`action_config.py:290-292`, `action_policy.py:177-178,407`). Stale: `docs/features.md:698` ("25 of them", table lacks `tool.not_in_skill`), `:728` ("Ten of them ... `tool.malformed`)" list), `docs/roadmap.md:93` ("25 rules"). Also `app/services/action_config.py:123` says "the ten" in a docstring: out of scope (app/ untouched, `test_untouched_app.py`); mention it to the orchestrator.
- **Outcomes** `app/db/models.py:545-552`: `ok, tool_error, upstream_error, timeout, result_too_large, result_blocked`. Startup warning for skill tools over 55 chars: `app/services/mcp_config.py:575-590`. Config sections: `servers`, `skills`, `v1_aliases.prefixes` (`:113-114`).
- **Client facts, with working configs to cite**: `tests/e2e/_mcp.py:153-183` (`opencode_config`: `"type": "remote"`, `"codemode": False`, static `Authorization` header, server key `harness` = `CLIENT_KEY` `:42`); `tests/e2e/_mcp.py:185-195` (`cline_settings`: `"type": "streamableHttp"`, without it Cline falls back to SSE and lists nothing); prefixes `harness_` (OpenCode) and `harness__` (Cline) `:46-47`; gateway YAML `:116-134`; run by `tests/e2e/test_mcp_clients.py` (opt-in `--run-e2e`). Versions: OpenCode 2.3.2, Cline CLI 3.0.74 (`tests/corpora/mcp/SOURCES.md`).
- **Stale "never executes" wording** (grep of docs/ and README): `docs/roadmap.md:93`, `docs/features.md:696` ("**The harness never executes tools.** It classifies ... the client ... runs it"), `README.md:167`, `README.md:230`. (`roadmap.md:79` and `features.md:483` cited by the PRD no longer carry it: those lines moved.) New wording: the harness runs no tool code; for `/v1` tool calls the client still executes; for MCP tools behind `/mcp` the harness causes execution by forwarding an allowed call to a configured server.
- **`examples/mcp.yaml` stays loaded** by `tests/test_mcp_config.py:69` `test_examples_load` (together with `examples/mcp_action_policy.yaml`, `:45`); run it.
- **Docs-link check**: none exists for md links (`tests/test_providers_docs.py` checks settings, yaml blocks and substrings only). Plan a new test (Task 6).

## Skills In Use

none (`skills: []`, `.agents/skills/` has none matching docs).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Docs test | `tests/test_providers_docs.py:30-75,122-150` | `_section(path, heading)`, `_documented_settings()`, `Settings.model_fields` lookup, substring (not sentence) assertions |
| Docs section | `docs/features.md:775-900` (`### Tool calling`, `#### Setting up OpenCode/Cline`) | heading levels, status line, per-client subsections, "what it does not cover" |
| README row | `README.md:160-167` (Features table), `:176-247` sections, TOC `:23-42` | one row + a short `## ` section with link to features |
| Config row | `docs/configuration.md:68-70` | `| NAME | No | default | purpose, link |` |
| Roadmap | `docs/roadmap.md:21-27,38-41,60-67` | `- [x]` shipped line with PRD link; open items as `- [ ]` |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `docs/features.md` | UPDATE | New `### MCP gateway and skills` (after Tool calling, i.e. after the OpenCode/Cline setup subsections at the end); fix `:698`, `:728`, `:696` |
| `docs/roadmap.md` | UPDATE | Tick MCP item (`:41` Planned -> Shipped list `:27` style; rewrite `### MCP servers and agent skills` `:69-77`); fix `:93` |
| `README.md` | UPDATE | Features row, TOC entry, `## MCP gateway and skills` section, Roadmap `:405` (drop MCP from Planned), `:167`, `:230` wording |
| `docs/configuration.md` | UPDATE | Nine rows near `:68-70` |
| `docs/api.md` | UPDATE | Intro `:3` and short `### POST /mcp` / `### GET /skills` entries, plus the `/audit/actions` filters `surface, server, outcome, linked` (check `:259-294` first) |
| `tests/test_mcp_docs.py` | CREATE | Docs checks (Task 6) |
| `.agents/PRDs/PRD-023-mcp-and-skills/PRD.md` | UPDATE | frontmatter `status: done`, `updated: 2026-11-24` |

## Tasks

### Task 1: features.md MCP section
- **Implement** (headings, in order): *What it is* (status: off by default, `MCP_ENABLED`; "the harness runs no tool code but causes execution": scope note); *Topology* (§6.2 diagram trimmed: one aggregated `POST /mcp`, names `<server>__<tool>`, stateless northbound, southbound Streamable HTTP only, credentials from env names in config, never forwarded inbound headers); *Configuration* (link to `examples/mcp.yaml`, `examples/mcp_action_policy.yaml`; the nine settings table with the code's defaults; `mcp_tools`/`mcp_opaque_tools` in `ACTION_POLICY_FILE`); *Skills* (id/version/tools/instructions/requires; role holds `skill:<id>` in `RBAC_ROLES_FILE`; visible = held skills; `tool.not_in_skill` non-grantable; prompts `skill-<id>`); *How a call is decided* (permission -> usage -> visibility -> `evaluate` -> **row committed before forwarding** -> forward -> result inspected; outcomes list; results never stored: hash, size, flags; never retried, "may have run"); *Linking `/v1` proposals to gateway calls* ("correlation, not proof", `MCP_LINK_WINDOW_SECONDS`, `linked=false` filter = a call no model response through the harness proposed); *Per-client setup* (`#### OpenCode`: `codemode: false` or tools run inside `execute` and stay `tool.unknown`; `#### Cline`: `"type": "streamableHttp"`; both: name the server `harness` or set `v1_aliases.prefixes` to the client's prefix (`harness_`, `harness__`); Cline hashes ids >55 chars so the alias does not resolve, `mcp_config.load()` warns, still callable through `/mcp`; cite `tests/e2e/_mcp.py:153-195`, versions 2.3.2 / 3.0.74, "verified against the stub, not a live model"); *Operating it* (`/audit/actions` filters, `GET /skills`, console Actions chips and Skills page, upstream credentials least-privilege, per-`(server, user)` upstream sessions, T13); *What it does not cover* (§9.4 + §13 as bullets: servers an agent reaches directly are not seen; upstream integrity; OAuth on `/mcp`; per-user upstream identity; sandboxing/stdio; results inspection is patterns only; tool `annotations` are the upstream's claim and unverified; description changes re-inspected but not pinned; no streaming/progress; no `resources`; no sampling/elicitation; server-to-client channels refused; `2026-07-28` handshake refused; a stateful upstream across instances may see one user under two sessions).
- **Also**: `:696` reword; `:698` "26 of them" and add a `tool.not_in_skill` row (Tool, deny, none); `:728` "Eleven of them" and add `tool.not_in_skill` to the list.
- **Validate**: Task 6 test.

### Task 2: roadmap.md
- Move the MCP bullet from Planned (`:41`) to Shipped (`- [x]`, PRD-023 link, one line, mention off by default `MCP_ENABLED`). Rewrite `### MCP servers and agent skills` (`:69-77`): status built; replace plan prose with what shipped; unticked items from PRD §13 (OAuth 2.1 on `/mcp`, per-user upstream credentials, OAuth client credentials southbound, skill-scoped constraints and pinned description hashes, `MCP_REQUIRE_PROPOSAL`, upstream resources and prompts, sampling through the pipeline, operator-sandboxed stdio, `2026-07-28` northbound, streaming/progress, per-server workspace roots, shared upstream registry, `tools/list` discovery rows). Fix `:93` count to 26 and reword the sentence.

### Task 3: README.md
- Features row **MCP gateway and skills** (off by default, `MCP_ENABLED`, `/mcp`); TOC + `## MCP gateway and skills` with the nine setting names, a link to `docs/features.md#mcp-gateway-and-skills`, per-client one-liners, and the not-covered pointer; `:405` Planned drops MCP; fix `:167` and `:230` ("runs no tool code; for `/v1` the client executes, for `/mcp` the gateway forwards allowed calls").

### Task 4: configuration.md and api.md
- Nine rows in the `| \`NAME\` | No | default | ... |` format with the validation ranges above. api.md: short entries only, linking to features.

### Task 5: PRD status (last step)
- PRD frontmatter `status: done`, `updated: 2026-11-24`; story frontmatter done/report/commit per implement.md; regenerate the index: `PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-023` (`errors: none`).

### Task 6: tests/test_mcp_docs.py
- `test_mcp_settings_documented`: the nine names are in `Settings.model_fields`, each appears in `docs/configuration.md` as a row and in `.env.example` as `NAME=`, and the README section names all nine; the documented default in the `configuration.md` row equals `Settings.model_fields[name].default`.
- `test_rule_counts_match_the_engine`: docs/features.md and roadmap.md state `f"{len(RULE_IDS)}"` rules and the word for `len(NON_GRANTABLE_RULES)` (map 11 -> "Eleven"); `"25 rules"`/`"Ten of them"` absent; every `RULE_IDS` member appears in the rules table.
- `test_never_executes_sentence_reworded`: none of `docs/*.md` and `README.md` contains "never executes tool" (case-insensitive).
- `test_relative_links_resolve`: for `docs/features.md`, `docs/roadmap.md`, `docs/configuration.md`, `docs/api.md`, `README.md`, every `](path)` / `](path#anchor)` that is not http(s) resolves from the file's directory (repo files exist; strip `:line` suffixes if any), and every `#anchor` resolves to a heading slug of the target file (GitHub slug: lowercase, drop punctuation, spaces to `-`). Include a negative self-check on a made-up link so the checker is not vacuous.
- `test_features_mcp_section_substance`: `_section` for the heading; substrings: `codemode`, `streamableHttp`, `v1_aliases`, `55`, `correlation`, `not proof`, `unverified`, every nine setting, "does not cover".
- Existing `tests/test_mcp_config.py::test_examples_load` keeps `examples/mcp.yaml` loaded; do not duplicate.

## End-to-End Tests

- [ ] None driven live (docs only). The opt-in `tests/e2e/test_mcp_clients.py` is not rerun (needs clients, Docker is down); the docs cite its configs.
- [ ] Read the rendered section once for the "what it does not cover" list against PRD §9.4/§13.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_docs.py tests/test_providers_docs.py tests/test_mcp_config.py -k "docs or examples_load or provider or setting"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_caddyfile_routes.py tests/test_untouched_app.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-023
```
`-m "not db"` locally (Docker is down). Full suite: GitHub CI on push (user decision). No test is renamed or removed, so the PII guard is not needed. If the link test finds a pre-existing broken link in the checked docs, fix the link (docs), not the test.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 features section (topology, config, skills, per-client, correlation, unverified, not-covered) | 1 | `test_features_mcp_section_substance` |
| AC2 roadmap ticked, sentence reworded | 2, 3 | `test_never_executes_sentence_reworded`, `test_rule_counts_match_the_engine` |
| AC3 README + `.env.example` nine settings; `examples/mcp.yaml` loaded | 3, 4 | `test_mcp_settings_documented`; `tests/test_mcp_config.py::test_examples_load` |
| AC4 every docs link resolves | 6 | `test_relative_links_resolve` |

Plus: PRD `status: done` and index regenerated (Task 5).
