---
story: STORY-009
prd: PRD-022
slug: chain-config-and-startup-validation
title: PROVIDER_CHAINS_FILE loader, settings, and startup validation (trust, capability, catalogue)
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Chain configuration and startup validation

## Summary

Add `app/services/upstream/chain_config.py`: a pure validator that turns a parsed chains document plus a `Registry` and a `ChainLimits` into an immutable `ChainSnapshot`, and a thin loader (`load()` / `reset()` / `chain_for()`) that is the only I/O. Four settings land in `app/config.py` (PRD 9.3). `load()` is wired after `provider_registry.load()` at both lifespans. Nothing consumes `chain_for` yet (STORY-011/012); with no file it returns the PRD-020 single-candidate chain.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-009-chain-config-and-startup-validation.md`
- PRD sections: 6.3, F3, 9.3, D5, D6, T1, user story 2
- Systems: `app/config.py`, `app/services/upstream/`, `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, `tests/_providers.py`, docs/.env.example

## Design Decisions (binding; contract for STORY-011/012)

**Return contract** (frozen dataclasses, tuples only):
```python
@dataclass(frozen=True)
class Candidate:  model_id: str; allow_lower_trust: bool = False; capability_scoped: bool = False
@dataclass(frozen=True)
class Chain:      model: str; ingress: Optional[str]; candidates: tuple[Candidate, ...]   # candidates[0].model_id == model
@dataclass(frozen=True)
class ChainLimits: max_candidates: int; deadline_seconds: Optional[float]; min_attempt_seconds: float
@dataclass(frozen=True)
class ChainSnapshot: chains: Mapping[tuple[str, Optional[str]], Chain]   # MappingProxyType over a dict built once
```
- `ChainSnapshot.chain_for(model, ingress) -> Chain`: exact `(model, ingress)`, then `(model, None)`, then `Chain(model, None, (Candidate(model),))`. Module-level `chain_for(model, ingress)` delegates to the loaded snapshot, or builds that same single-candidate chain when none is loaded. Always returns a `Chain`, never `None`; the fallback candidate has both flags `False`. `candidates[0]` is the primary and equals `model` (so equals `match.model`). An omitted `match.ingress` is keyed as `None`. `ingress` is validated against `("query", "chat", "v1")` (`query_pipeline.py:86` `Ingress` literal; copy the tuple, do not import the pipeline: chain_config stays import-light).
- Flags are meaningful only for index >= 1: entry 0 may not carry either flag (validation error: the primary has nothing to be compared with).
- **Every per-entry check compares with the PRIMARY** (`candidates[0]`, resolved through `registry.models_by_id`), never the previous entry. Trust: primary `internal` and candidate `external` needs `allow_lower_trust` (`external -> internal` and same trust pass). Capability: for each of `tools`, `streaming`, `reasoning`, `forced_tool_choice`, if primary has it and the candidate lacks it, `capability_scoped: true` is required. One error per entry, the first rule broken in a fixed order (trust, then capabilities in that order). T1 chain `[internal A, internal B, external C, external D(allow_lower_trust)]` fails on entry 3 (index 2), naming it. `max_context_tokens` and `sampling_params` are not in the F3 list; do not add them.
- **Purity**: `validate_chains(source, document, registry, limits) -> ChainSnapshot` and helpers read no settings, no env, no files, and do not log. `validate_chains` returns `(snapshot, warnings: tuple[str, ...])`; `load()` logs each once. Tests then assert on the strings without caplog, plus one caplog test through `load()`.
- **WARNING**: only for an entry with `allow_lower_trust: true` whose primary is `internal` and candidate `external`: `"{file}: chain 'X' entry N (id, provider P): internal -> external fallback is allowed by allow_lower_trust"`. On a non-crossing entry: accepted, no warning, no error.
- **Error format** (`provider_registry.py:182` `_fail` style; copy `_fail/_check_keys/_mapping/_bool` small, as `provider_registry` copied `action_config`'s; error class `ChainConfigError(ValueError)`): `"{source}: chain '{match.model}'[ ingress v1] entry {i} ({id}, provider {p}): {rule}"` where `source = f"PROVIDER_CHAINS_FILE '{path}'"` and `i` is 1-based (user story 2: "entry 2"). Chain-level errors omit the entry part. The trust message follows story 2 verbatim: `trust external is lower than the primary's trust internal; set allow_lower_trust: true on this entry to permit it (PRD-020 6.8 rule 1)`.
- **Per-chain deadline check** (PRD 9.3 "`< deadline`"): effective deadline = `limits.deadline_seconds` else the primary provider's `timeout_seconds`; `limits.min_attempt_seconds >= effective` is a chain error. Settings checks it only when the deadline is set.
- Registry reload: `load()` reads `provider_registry.current()` at call time. There is no reload mechanism to extend: `provider_registry.load()/reset()` run only at the two lifespans and in test fixtures, so `chain_config.reset()` is paired with `reset()` in fixtures and `chain_config.load()` follows `provider_registry.load()` at each call site. A chains file with no registry file: `load()` raises `ChainConfigError` (defence in depth; Settings refuses it first).
- Atomicity as `provider_registry.load()` (`provider_registry.py:625`): validate and warn first, rebind `_snapshot` last; a failure leaves the previous state and logs nothing.
- No key, URL or value echoes in errors (ids and provider names only).

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; not relevant).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Errors | `app/services/provider_registry.py:182-198` | `_fail(source, *parts)`; `_check_keys(source, where, body, allowed, required)` unknown/missing key text |
| Version/top keys | `provider_registry.py:266-272` | `_check_version`: `bool` refused for `version`, "must be 1" |
| Loader | `provider_registry.py:625-659` | read file, `strict_yaml.safe_load`, `yaml.YAMLError` -> `_fail`, warn, assign last |
| State | `provider_registry.py:661-688` | module-level `_snapshot`, `reset()` reads no setting |
| Frozen models | `provider_registry.py:96-158` | `@dataclass(frozen=True)`, tuples, `Mapping` fields |
| Settings validators | `app/config.py:518-528`, `:574-588`, `:793-806` | field validator with example in message; `_POSITIVE_LIMIT_DESCRIPTIONS`; model validator for cross-field |
| Tests | `tests/test_provider_registry.py:236-256` | `_BAD` list of `(id, snippet, fragment)` parametrized; assert path + fragment + nothing half-built |
| Registry in tests | `tests/_providers.py:28-60` | `providers_file` / `provider_file` fixtures (reset on teardown) |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/upstream/chain_config.py` | CREATE | contract types, `validate_chains`, loader, `chain_for`, `reset` |
| `app/config.py` | UPDATE | four settings + validators (below) |
| `app/main.py` | UPDATE | `chain_config.load()` right after `provider_registry.load()` (line 24); import it from `app.services.upstream` |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `app.register_lifespan_task(chain_config.load)` after line 274 (Reflex runs tasks in registration order; same bypass comment as 268-273) |
| `tests/_providers.py` | UPDATE | the two fixtures also call `chain_config.reset()` on exit; add `chains_file` helper writing `chains.yaml` and setting the setting |
| `tests/test_chain_config.py` | CREATE | validation, loader, lookup, warnings, purity |
| `tests/test_config.py` | UPDATE | new section: one test per bound (after the PRD-020 section, ~line 1700) |
| `.env.example`, `docs/configuration.md` | UPDATE | four settings (see Task 6) |
| `examples/chains.yaml` | CREATE | the F3 example (valid against `examples/providers.yaml`; adjust ids to that catalogue) |

Not touched: `provider_registry.py`, `query_pipeline.py`, `upstream/__init__.py` (do not re-export; STORY-011 decides).

## Tasks

### Task 1: Settings (`app/config.py`)
- Add near `PROVIDERS_FILE` (line 286): `PROVIDER_CHAINS_FILE: str = ""`, `PROVIDER_CHAIN_MAX_CANDIDATES: int = 3`, `PROVIDER_CHAIN_DEADLINE_SECONDS: Optional[float] = None`, `PROVIDER_MIN_ATTEMPT_SECONDS: float = 5.0`, each with a comment citing PRD-022 9.3.
- Field validators (message names the setting, the bound, the value, an example, as `config.py:518`): max candidates in 1..5; deadline `> 0` when not None; min attempt `> 0`.
- Model validator (after `_validate_providers_file_vs_v1_tool_models`, `config.py:~808`): `PROVIDER_CHAINS_FILE` set with empty `PROVIDERS_FILE` -> `ValueError` naming both settings (chains resolve ids through the registry, PRD-022 D5); and `PROVIDER_CHAIN_DEADLINE_SECONDS` set with `PROVIDER_MIN_ATTEMPT_SECONDS >= it` -> error. The effective-deadline case (unset) is Task 2's.
- Check how an empty env value parses for `Optional[float]` (`PROVIDER_CHAIN_DEADLINE_SECONDS=` must mean unset, or leave it commented in `.env.example`); do not weaken a validator.
- Settings never opens the file (the `config.py:282` note).
- **Validate**: `tests/test_config.py -k "PROVIDER_CHAIN or provider_chain or MIN_ATTEMPT"`.

### Task 2: `chain_config.py` (pure core)
- Types per the contract above. `validate_chains(source, document, registry, limits)`: `_check_version` (keys `version`, `chains`; `chains` non-empty list); per chain: keys `match` (`model` required, `ingress` optional, closed vocab), `candidates` (non-empty list); per entry keys `model` required, `allow_lower_trust`, `capability_scoped` (bool only, default False).
- Order of checks per chain: shape, duplicate `(model, ingress)` key, first candidate == `match.model`, `len(candidates) <= limits.max_candidates`, then per entry in order: catalogued (`registry.models_by_id`; passthrough-only/uncatalogued -> "is not catalogued in PROVIDERS_FILE (a chain cannot route to an id the operator never listed)"), repeated id, primary flags forbidden, trust, capabilities, then the deadline check. The first failure raises; entry numbers are 1-based.
- Provider lookup by `CatalogModel.provider_name` over `registry.providers` (`Route` is built by `resolve()` against the live registry, which would break purity: do not call it).
- Return `(ChainSnapshot, warnings)`.
- **Validate**: `tests/test_chain_config.py`.

### Task 3: Loader and lookup (same file)
- `load()`: no setting -> `_snapshot = None`; return. Set but `settings.PROVIDERS_FILE` empty or `provider_registry.current().is_legacy` -> `ChainConfigError`. Read, `strict_yaml.safe_load`, `OSError`/`UnicodeDecodeError`/`yaml.YAMLError` -> error naming file (`provider_registry.py:644-650`). Build `ChainLimits` from settings here (the only settings read), validate, log each warning via `logger.warning`, assign last.
- `reset()`; `current() -> Optional[ChainSnapshot]`; `chain_for(model, ingress)`.

### Task 4: Wiring
- `app/main.py:24` and `chat_ui.py:274` as in the table. Mirror the comment style at `chat_ui.py:268-273`.

### Task 5: Fixtures
- `tests/_providers.py`: both context manager and fixture call `chain_config.reset()` in their `finally`/teardown; add `chains_file(tmp_path, text, *, monkeypatch)` that writes `chains.yaml`, sets `PROVIDER_CHAINS_FILE`, loads, yields the snapshot, resets.

### Task 6: Docs and examples
- `.env.example`: comment block of at least 3 lines above each new variable, placed after `PROVIDERS_FILE=` (line 90); `docs/configuration.md` rows (exactly one per name; `tests/test_providers_docs.py:60-80` reads both and checks every name exists in `Settings.model_fields`). Deadline row: "unset = the primary's `timeout_seconds`". Mention restart (no hot reload) and the trust warning. No features.md rewrite (STORY-017/018 own docs).
- `examples/chains.yaml`: F3 example against `examples/providers.yaml` (check its model ids; trim to what exists).

### Task 7: Tests (`tests/test_chain_config.py`, `tests/test_config.py`)
- Registry fixture text with providers `a` (internal, tools/streaming/reasoning/forced_tool_choice true), `b` (internal, same caps), `c` (external, same caps), `d` (external, no caps), `e` (external, `anthropic` type), plus a passthrough provider. Build snapshots by calling `validate_chains` with a registry from `provider_file(...)` and a `ChainLimits(...)` literal (no settings).
- One `_BAD` parametrized test, one case per F3 rule: version != 1; unknown key (top, chain, match, entry); uncatalogued id; passthrough-only id; first != match.model; repeated id; duplicate match (also same model with different ingress is OK); `> max_candidates`; internal->external without opt-in (names file, chain, entry 2, provider, matches user story 2 text); each of the four capabilities missing without `capability_scoped` (four ids); flag on entry 1; min-attempt >= effective deadline; unknown ingress; non-bool flag. Assert path + chain + `entry N (id` + fragment, and `chain_config.current() is None` after a failed `load()`.
- T1: `[a, b, c, d(allow_lower_trust)]` raises naming entry 3 and `c`, with `max_candidates=4`; counterpart `[a, b, c(opt), d(opt)]` loads and logs two warnings.
- Pass cases: external->internal, internal->internal, `capability_scoped` accepted, same-trust `allow_lower_trust` (no warning, no error), `capability_scoped` on a candidate that has every capability.
- Warnings: exactly one per crossing entry, naming chain and entry, through `load()` with `caplog`; zero on non-crossing opt-in; logged after validation succeeds only.
- Lookup: exact beats model-only beats synthesised; `ingress=None` on a chain with `ingress: v1` falls to the synthesised chain; flags and order preserved; snapshot immutability (`dataclasses.FrozenInstanceError`, `TypeError` on mapping assignment, tuple candidates).
- Off: no setting -> `current() is None`, `chain_for("m", "v1") == Chain("m", None, (Candidate("m"),))`; `PROVIDER_CHAINS_FILE` with no `PROVIDERS_FILE` -> `ChainConfigError` from `load()` and `ValidationError` from Settings.
- Purity: AST test that `chain_config.py` outside `load()` references no `settings` (mirror an existing AST purity test; grep `ast.parse` in `tests/test_v1_translate*.py`), and a test that validation works with `settings` monkeypatched to raise on access.
- `tests/test_config.py`: per bound, valid and invalid: max candidates 0, 6, accepted 1 and 5; deadline 0, -1, accepted 0.5, default None; min attempt 0, -1; min attempt >= set deadline; chains file without providers file (message names both settings, never the path value).

## End-to-End Tests

- [ ] Boot through `TestClient(app)` lifespan with a providers file and a chains file: starts; with a crossing chain lacking the opt-in: lifespan raises `ChainConfigError`.
- [ ] No chains file: `/health` and a `/v1` call behave as before (existing suites).
- [ ] No chat UI behaviour change; `tests/test_chat_ui_startup_guard.py` covers the import.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chain_config.py tests/test_config.py tests/test_provider_registry.py tests/test_providers_docs.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py tests/test_main.py
```
(`test_providers_docs.py` is the settings/docs census: documented names must exist in `Settings.model_fields`, and `PROVIDERS_FILE=` needs a 3-line comment. There is no test that every setting is documented, so the four settings must be added to docs and `.env.example` by hand. Check `tests/test_untouched_app.py` and `tests/test_config.py` for anything enumerating `app/` files or settings and register the new module if it lists upstream modules.)

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|---|---|---|
| AC1 settings per 9.3; file needs `PROVIDERS_FILE` | 1, 3 | `tests/test_config.py` bound tests; `test_chain_config.py::test_chains_file_without_providers_file` |
| AC2 immutable snapshot, ordered candidates, `chain_for` order | 2, 3 | `test_chain_config.py::test_lookup_order`, `::test_snapshot_is_immutable`, `::test_example_file_loads` |
| AC3 each F3 rule, entry-level naming, T1 | 2 | `test_chain_config.py::test_startup_error[<rule>]`, `::test_t1_third_entry_fails` |
| AC4 one WARNING on a crossing opt-in; silent otherwise | 2, 3 | `::test_warning_once_per_crossing_entry`, `::test_no_warning_without_crossing` |
| AC5 no file: single candidate, no snapshot | 3 | `::test_no_file_is_prd020` |

## Risks

- `Optional[float]` env parsing of an empty `PROVIDER_CHAIN_DEADLINE_SECONDS=` (Task 1): verify before shipping `.env.example`.
- Chat UI lifespan order: `chain_config.load` must register after `provider_registry.load`; a stale `chain_config` snapshot after a later registry swap is possible only in tests (fixtures reset both).
- Reading `settings` inside `load()` only: STORY-011 reads limits via `ChainLimits` from the pipeline, not from this module.
