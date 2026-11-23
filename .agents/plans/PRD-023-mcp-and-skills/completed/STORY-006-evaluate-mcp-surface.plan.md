---
story: STORY-006
prd: PRD-023
slug: evaluate-mcp-surface
title: "Engine: `evaluate(..., surface=McpSurface)` with visibility inside the fail-closed boundary"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: Engine `surface=McpSurface`

## Summary

Add a frozen `McpSurface(server, visible)` and `V1 = None` to `app/services/action_policy.py`, and a keyword-only `surface` parameter on `evaluate`. With a surface, visibility is checked first inside the existing `try` (a name outside `visible` is one `tool.not_in_skill` classification and `map_tool_call` is never called), and the mapping tables come from `policy.mcp_tools` / `mcp_opaque_tools` for the server. Everything after (`_decide`, `_fold`, `_reason`, the boundary) is unchanged. Only `action_policy.py` changes under `app/`; the rest is tests.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-006-evaluate-mcp-surface.md` (ACs live there)
- PRD sections used: 6.4, 6.3 (M6), D4, D7, T6, T9 (rows read in 9.2)
- Systems affected: `app/services/action_policy.py`, `tests/test_action_policy.py`, `tests/test_action_corpus.py`. NOT touched: `action_adapters`, `action_config`, `action_classifiers`.

## Design Decisions

Binding (orchestrator), verified against the code today (PRD line refs were stale; the real ones are below):

- `@dataclass(frozen=True) class McpSurface: server: str; visible: frozenset[str]`; `V1: Final = None`. `evaluate(call, identity, policy=None, *, surface: Optional[McpSurface] = V1)`. Keyword-only, default `V1` keeps every caller (`evaluate_all` at `action_policy.py:363`, step 7c) byte-identical. `evaluate_all` is NOT changed (gateway calls one call at a time, M6).
- `call.name` on the gateway is the bare upstream tool name. Visibility check FIRST, inside the `try` (`action_policy.py:290`): `tool_name not in surface.visible` -> `classifications = (Classification("tool.not_in_skill", None, tool_name[:_NAME_DETAIL_CAP]),)`, `opaque = None`, `operations` stays `()`, `map_tool_call` not called. Use the already-sanitised `tool_name` (non-str name -> `""`, which is never in `visible`... except if `visible` held `""`; a non-str name falls through to `""not in visible` -> `not_in_skill`, which is still a deny; acceptable and fail-closed).
- Then the unchanged `_decide` -> `_fold` -> `_reason`. `tool.not_in_skill` is `("deny", None)` in `_BUILT_IN_RULES` (`action_config.py:322`) and non-grantable, so `rule.grant is None` and no identity can lift it. `tool.opaque` is the only rule `_decide` special-cases, so no change there.
- Table selection also inside the `try`, before `map_tool_call`: `surface is None` -> `policy.tools`, `policy.opaque_tools`; else `policy.mcp_tools.get(surface.server, _EMPTY)`, `policy.mcp_opaque_tools.get(surface.server, _EMPTY)` with module-level `_EMPTY: Mapping = MappingProxyType({})`. Unknown server or a visible-but-unmapped tool -> existing `tool.unknown` (deny). Never falls back to `/v1` tables.
- Digest stays `action_config.policy_digest(policy)` computed before the `try` (`action_policy.py:278`); it already covers `mcp_tools` sections (STORY-005). No change.
- Fail-closed: visibility and selection exceptions hit the existing `except Exception` (`action_policy.py:324`), giving deny/`tool.malformed`. Tests must make the failure occur INSIDE the try: monkeypatch a seam, do not pass a broken `surface` object that fails before the try (attribute reads of `surface.visible` / `.server` are inside the try by construction, so a bad object also fails closed; test both).
- Purity: no new `app` imports (`from typing import Final` is stdlib). `test_action_policy_stays_pure` (`tests/test_action_policy.py:666`) keeps passing.
- Seams for tests (so a monkeypatch can raise inside the try without touching `map_tool_call`): factor two tiny private helpers `_is_visible(surface, name) -> bool` and `_select_tables(policy, surface) -> tuple[Mapping, Mapping]`, called through module globals (as `_classify` is, `action_policy.py:174`). Tests monkeypatch `action_policy._is_visible` / `_select_tables` to raise.

## Skills In Use

None. `.agents/skills/` holds only `frontend-design` (not applicable: no UI).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Naming/docstrings | `action_policy.py:1-61`, `:263-275` | Module docstring cites PRD sections/decisions; add a short "PRD-023 D4/D7" paragraph on the surface and keep the Purity paragraph true |
| Frozen dataclass | `action_policy.py:78-79` | `@dataclass(frozen=True)` with `#:` field comments |
| Immutable empty table | `action_config.py:209-214` | `MappingProxyType({})` |
| Fail-closed boundary | `action_policy.py:324-346` | Only the exception type is logged, never name/arguments text |
| Test helpers | `tests/test_action_policy.py:52-77` (`_call`, `_with`, `_grant`) | Reuse; `_with(mcp_tools=...)` via `dataclasses.replace` (`:59`) |
| Raising seams | `tests/test_action_policy.py:322-366` (`_boom`, `_RAISERS`) | Same log/deny assertions, `MARK` must not leak into reason or log |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_policy.py` | UPDATE | `McpSurface`, `V1`, `_EMPTY`, `_is_visible`, `_select_tables`, `evaluate(..., *, surface)`, docstring paragraph |
| `tests/test_action_policy.py` | UPDATE | New gateway tests (below); drop the `not_in_skill` exclusion at `:497-500`; the `# PRD-023 D7` comment is kept, reworded |
| `tests/test_action_corpus.py` | UPDATE | Census at `:443-453`: drop the exclusion; report the gateway-produced rule |

## Tasks

### Task 1: Engine

- **File**: `app/services/action_policy.py`
- **Implement**: Add `Final` to the typing import (`:66`). After `_FAILED_DETAIL` (`:167`) add `McpSurface`, `V1`, `_EMPTY`, `_is_visible`, `_select_tables`. In `evaluate`, inside the `try` before `map_tool_call` (`:291`):
  ```python
  if not _is_visible(surface, tool_name):   # True when surface is V1
      classifications = (Classification("tool.not_in_skill", None, tool_name[:_NAME_DETAIL_CAP]),)
  else: tables = _select_tables(policy, surface); result = map_tool_call(call, *tables, cap) ...
  ```
  Restructure minimally: compute `opaque = None`, then branch; keep the existing if/elif chain over `result` unchanged by moving the not-in-skill case to a guard that sets `classifications` and skips mapping (e.g. `result = None` sentinel handled by a leading `if` in the chain, or an early branch that jumps to `_decide`). Implementer picks the smallest diff; the `map_tool_call` call must be unreachable for a hidden name. Update the docstring: `surface` semantics, "configuration not model input" note stays (tables are selected inside the try only because `surface` comes from the caller's skills).
- **Mirror**: `action_policy.py:290-323`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_action_policy.py`

### Task 2: Tests in `tests/test_action_policy.py` (new section "PRD-023 STORY-006")

All gateway tests build `_MCP_POLICY = _with(mcp_tools=MappingProxyType({"postgres-staging": MappingProxyType({"query": ToolMapping...})}))`. Open `action_config.py` (ToolMapping, `:150-176` area) to build the entry with the same shape `_validate_tools` produces; or load it with `action_config._validate_mcp_tools` is NOT allowed (private); build from `BUILT_IN_POLICY.tools["query"]` (the existing `/v1` `query` mapping, copy its value).

- AC1: `inspect.signature(evaluate).parameters["surface"]` is KEYWORD_ONLY with default `None`; `V1 is None`; `evaluate_all` signature unchanged; omitted `surface` equals `surface=V1` (full `ActionDecision` equality) over `_SWEEP`.
- AC2: `DROP TABLE users` on `McpSurface("postgres-staging", frozenset({"query"}))`: `user` -> deny/`sql.ddl`; a role holding `action:sql:ddl` (via `_grant`) -> allow, `granted_by == "action:sql:ddl"`. Also reason text equals `/v1` equivalent.
- AC3: name `"drop_everything"` not in `visible`, role holding every `action:*` (`_grant(monkeypatch, "dba", *authz.ACTION_PERMISSIONS)`, as `:476-478`): deny/`tool.not_in_skill`, exactly one classification, detail `name[:64]` (test a 100-char name is capped), `granted_by is None`, `operations == ()`. Spy: `monkeypatch.setattr(action_adapters, "map_tool_call", spy)` records calls; assert none. Also a hidden name that IS mapped in `mcp_tools` is still `not_in_skill` (mapping not consulted). Empty `visible` -> everything `not_in_skill`. Reason is `"a tool outside the caller's skills is not permitted: <name>"`.
- Table selection: tool mapped only in top-level `tools:` (use `query` with `mcp_tools={}`) on the gateway, visible -> deny/`tool.unknown`; unknown server -> `tool.unknown`; visible-but-unmapped -> `tool.unknown`; an `mcp_tools`-only name on `/v1` (no surface) -> `tool.unknown`; `mcp_opaque_tools` entry (e.g. `create_pull_request: flag`) on server A yields flag/`tool.opaque`, same name on server B -> `tool.unknown`; `opaque_tools` of `/v1` never used on gateway.
- AC4: parametrize two seams, `action_policy._is_visible` and `action_policy._select_tables` -> `_boom` (reuse `MARK`): result deny/`tool.malformed`, detail `"classification failed"`, no raise, `MARK` absent from reason and `caplog`, error log names the tool and exception type only. Plus a surface object with no `.visible` attribute (`object()`) -> deny/`tool.malformed`, no raise.
- AC5: digest equals `action_config.policy_digest(policy)` for: `/v1`, visible allow, `not_in_skill`, and the fail-closed result; and differs when `mcp_tools` differs between two policies (proves the whole policy digest, not a per-server slice).
- Census: in `test_every_reason_is_the_fixed_template_plus_the_calls_fragment` (`:476`) also evaluate one hidden gateway call per identity into `produced` and assert `produced == set(RULE_IDS)` with the exclusion removed; keep a `# PRD-023 D7` comment saying the rule comes from the `McpSurface` case.
- Surface dataclass: frozen (`FrozenInstanceError`), `visible` accepts a frozenset. `test_action_policy_stays_pure` and `test_evaluate_does_no_io` must pass unmodified (add one gateway call to `_sweep`? NO: `_sweep` feeds census; leave it).

### Task 3: Corpus census `tests/test_action_corpus.py:443-453`

The file-based corpus (`_SYNTHETIC`, YAML cases through default-surface `evaluate`) cannot express a surface and STORY-006 must not extend the corpus schema (the MCP corpus is STORY-012). Replace the exclusion with a gateway case evaluated in the test: `gateway = evaluate(ToolCall("g1","unlisted_tool","{}"), _IDENTITIES["user"], BUILT_IN_POLICY, surface=McpSurface("s", frozenset()))`; `missing = set(RULE_IDS) - set(reported) - {gateway.rule}`; assert `gateway.rule == "tool.not_in_skill"` first. Keep the `# PRD-023 D7` comment. Add `McpSurface` to that file's `action_policy` import (check existing imports at the top).

## End-to-End Tests

- [ ] `TestClient` not needed (engine only, no route). The end-to-end check is `evaluate(...)` with `McpSurface` through the real `BUILT_IN_POLICY` and the real `authz` matrix (Task 2 AC2/AC3).
- [ ] Existing suites unchanged: `tests/test_action_policy.py`, `tests/test_action_corpus.py`, `tests/test_action_vocabulary.py`, `tests/test_action_adapters.py` (no DB needed; `test_action_corpus.py::test_every_decision_round_trips_through_record_and_the_audit_api` uses `temp_db`, so run with `-k "not round_trips"` if Docker is down and report it).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_action_policy.py tests/test_action_corpus.py tests/test_action_vocabulary.py tests/test_action_adapters.py tests/test_untouched_app.py
```
Neither a test is renamed nor removed, so `test_pii_redaction_integration.py` is not needed. Grep `tests/` for `inspect.signature(evaluate` / `evaluate_all` guards before finishing: `grep -rn "signature(.*evaluate\|action_policy.evaluate" tests/`.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 default surface unchanged | 1, 2 | `test_surface_is_keyword_only_and_v1_is_none_and_default_changes_nothing` + existing suites |
| AC2 sql.ddl deny / granted allow on gateway | 1, 2 | `test_gateway_drop_table_denied_and_granted` |
| AC3 not_in_skill, grants cannot lift, no mapping consulted | 1, 2 | `test_a_hidden_tool_is_not_in_skill_even_for_every_action_grant`, `..._does_not_call_map_tool_call` |
| AC4 fail-closed in visibility and selection | 1, 2 | `test_a_failure_in_visibility_or_table_selection_fails_closed` |
| AC5 whole-policy digest | 2 | `test_the_gateway_digest_is_the_whole_policys` |
| Census exclusions removed (story note) | 2, 3 | `test_every_reason_is_the_fixed_template_plus_the_calls_fragment`, `test_every_rule_id_is_reported_by_some_file` |

## Risks

- A hidden name sanitised to `""` (non-str) on a surface whose `visible` contains `""`: impossible from M3 (name is a str); noted, fail-closed anyway.
- Over-refactoring the `try` body: keep the existing `result` chain byte-identical for `V1` (AC1 equality test guards it).
- The corpus test's `temp_db` test needs Docker; not affected by this change.
