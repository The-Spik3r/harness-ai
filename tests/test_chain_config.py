"""Chain configuration and startup validation (PRD-022 STORY-009, F3, D5, D6, T1, user story 2).

`validate_chains` is pure, so most tests call it with a registry from `provider_file(...)` and a
`ChainLimits` literal; the loader tests go through `chains_file` (settings + file) and
`chain_config.load()`.
"""

import ast
import dataclasses
import inspect
import logging
from pathlib import Path

import pytest

from app.config import settings
from app.services import provider_registry
from app.services.upstream import chain_config
from app.services.upstream.chain_config import (
    Candidate,
    Chain,
    ChainConfigError,
    ChainLimits,
    ChainSnapshot,
    chain_for,
    validate_chains,
)
from tests._providers import chains_file, provider_file  # noqa: F401  (fixtures)

_CAPS = "{tools: true, streaming: true, reasoning: true, forced_tool_choice: true}"


def _provider(name, trust, models, type_="openai_compatible", extra=""):
    body = "".join(f"      - id: {i}\n        capabilities: {c}\n{x}" for i, c, x in models)
    return (
        f"  - name: {name}\n    type: {type_}\n    base_url: https://{name}.example/v1\n"
        f"    trust: {trust}\n{extra}    models:\n{body}"
    )


# a, b internal; c external (one full model + one lacking each capability); d external bare;
# e anthropic; pt passthrough (a free id such as "some/free-id" is NOT catalogued).
REGISTRY = (
    "version: 1\ndefault_model: a1\nproviders:\n"
    + _provider("a", "internal", [("a1", _CAPS, "")])
    + _provider("b", "internal", [("b1", _CAPS, "")])
    + _provider(
        "c",
        "external",
        [
            ("c1", _CAPS, ""),
            ("c-no-tools", "{streaming: true, reasoning: true, forced_tool_choice: true}", ""),
            ("c-no-streaming", "{tools: true, reasoning: true, forced_tool_choice: true}", ""),
            ("c-no-reasoning", "{tools: true, streaming: true, forced_tool_choice: true}", ""),
            ("c-no-forced", "{tools: true, streaming: true, reasoning: true}", ""),
        ],
    )
    + _provider("d", "external", [("d1", "{}", "")])
    + _provider(
        "e",
        "external",
        [("e1", _CAPS, "        default_max_tokens: 1024\n")],
        type_="anthropic",
        extra="    key_env: E_KEY\n",
    )
    + _provider("pt", "external", [("pt1", "{}", "")], extra="    passthrough: true\n")
)
_ENV = {"E_KEY": "key-sentinel-value"}
_LIMITS = ChainLimits(max_candidates=3, deadline_seconds=None, min_attempt_seconds=5.0)
_SRC = "PROVIDER_CHAINS_FILE 'chains.yaml'"
_OPT = {"allow_lower_trust": True}
_SCOPED = {"capability_scoped": True}


@pytest.fixture
def registry(provider_file):  # noqa: F811
    return provider_file(REGISTRY, env=_ENV)


def _doc(*chains, version=1):
    return {"version": version, "chains": list(chains)}


def _chain(model, *entries, ingress=None):
    match = {"model": model}
    if ingress is not None:
        match["ingress"] = ingress
    return {
        "match": match,
        "candidates": [e if isinstance(e, dict) else {"model": e} for e in entries],
    }


def _validate(registry, document, limits=_LIMITS):
    return validate_chains(_SRC, document, registry, limits)


def _yaml(chains_text):
    return "version: 1\nchains:\n" + chains_text


# --- AC3: each F3 rule is a startup error naming file, chain, entry, provider ---------------

_BAD = [
    ("version", _doc(_chain("a1", "a1"), version=2), "version: must be 1", None),
    ("version-bool", _doc(_chain("a1", "a1"), version=True), "version: must be 1", None),
    (
        "unknown-top-key",
        {"version": 1, "chains": [_chain("a1", "a1")], "x": 1},
        "unknown key 'x'",
        None,
    ),
    ("unknown-chain-key", _doc({**_chain("a1", "a1"), "extra": 1}), "unknown key 'extra'", None),
    (
        "unknown-match-key",
        _doc({"match": {"model": "a1", "extra": 1}, "candidates": [{"model": "a1"}]}),
        "unknown key 'extra'",
        None,
    ),
    (
        "unknown-entry-key",
        _doc(_chain("a1", "a1", {"model": "b1", "extra": 1})),
        "unknown key 'extra'",
        None,
    ),
    ("empty-chains", _doc(), "chains: must be a non-empty list", None),
    (
        "unknown-ingress",
        _doc(_chain("a1", "a1", ingress="web")),
        "ingress 'web' is not one of",
        None,
    ),
    (
        "entry-not-mapping",
        _doc({"match": {"model": "a1"}, "candidates": ["a1"]}),
        "entry 1: must be a mapping",
        None,
    ),
    (
        "uncatalogued",
        _doc(_chain("a1", "a1", "ghost")),
        "entry 2 (ghost, provider ?): is not catalogued in PROVIDERS_FILE",
        None,
    ),
    (
        "passthrough-only-id",
        _doc(_chain("a1", "a1", "some/free-id")),
        "is not catalogued in PROVIDERS_FILE",
        None,
    ),
    (
        "first-not-match",
        _doc(_chain("a1", "b1", "a1")),
        "the first candidate must be the match model, got 'b1'",
        None,
    ),
    ("repeated-id", _doc(_chain("a1", "a1", "b1", "b1")), "entry 3 (b1, provider b): repeats", None),
    (
        "duplicate-match",
        _doc(_chain("a1", "a1"), _chain("a1", "a1", "b1")),
        "is configured twice",
        None,
    ),
    (
        "too-many",
        _doc(_chain("a1", "a1", "b1", "c1", "d1")),
        "has 4 candidates, more than PROVIDER_CHAIN_MAX_CANDIDATES (3)",
        None,
    ),
    (
        "trust",
        _doc(_chain("a1", "a1", "c1")),
        "entry 2 (c1, provider c): trust external is lower than the primary's trust internal; "
        "set allow_lower_trust: true on this entry to permit it (PRD-020 6.8 rule 1)",
        None,
    ),
    (
        "cap-tools",
        _doc(_chain("c1", "c1", "c-no-tools")),
        "entry 2 (c-no-tools, provider c): lacks capability tools",
        None,
    ),
    (
        "cap-streaming",
        _doc(_chain("c1", "c1", "c-no-streaming")),
        "lacks capability streaming",
        None,
    ),
    (
        "cap-reasoning",
        _doc(_chain("c1", "c1", "c-no-reasoning")),
        "lacks capability reasoning",
        None,
    ),
    (
        "cap-forced",
        _doc(_chain("c1", "c1", "c-no-forced")),
        "lacks capability forced_tool_choice",
        None,
    ),
    (
        "flag-on-primary",
        _doc(_chain("a1", {"model": "a1", "capability_scoped": True}, "b1")),
        "entry 1 (a1, provider a): the primary (entry 1) cannot set",
        None,
    ),
    (
        "trust-flag-on-primary",
        _doc(_chain("a1", {"model": "a1", **_OPT})),
        "the primary (entry 1) cannot set",
        None,
    ),
    (
        "min-attempt",
        _doc(_chain("a1", "a1", "b1")),
        "PROVIDER_MIN_ATTEMPT_SECONDS (5) must be less than the chain deadline (5s)",
        ChainLimits(3, 5.0, 5.0),
    ),
    (
        "non-bool-flag",
        _doc(_chain("a1", "a1", {"model": "b1", "allow_lower_trust": "yes"})),
        "entry 2: allow_lower_trust: must be true or false, got str",
        None,
    ),
]


@pytest.mark.parametrize(
    "document,fragment,limits", [(b, c, d) for _, b, c, d in _BAD], ids=[a for a, *_ in _BAD]
)
def test_startup_error(registry, document, fragment, limits):
    with pytest.raises(ChainConfigError) as err:
        _validate(registry, document, limits or _LIMITS)
    message = str(err.value)
    assert message.startswith(_SRC + ": ")
    assert fragment in message
    assert _ENV["E_KEY"] not in message  # T1: no key value in any message


def test_error_names_the_chain_and_ingress(registry):
    with pytest.raises(ChainConfigError) as err:
        _validate(registry, _doc(_chain("a1", "a1", "c1", ingress="v1")))
    assert "chain 'a1' ingress v1 entry 2 (c1, provider c)" in str(err.value)


def test_primary_timeout_is_the_deadline_when_unset(registry):
    # PRD-022 9.3: an unset deadline means the primary's timeout_seconds.
    timeout = registry.models_by_id["a1"].provider_name
    timeout = next(p for p in registry.providers if p.name == timeout).timeout_seconds
    with pytest.raises(ChainConfigError, match="less than the chain deadline"):
        _validate(registry, _doc(_chain("a1", "a1", "b1")), ChainLimits(3, None, timeout))
    _validate(registry, _doc(_chain("a1", "a1", "b1")), ChainLimits(3, None, timeout - 1))


def test_startup_error_through_load_leaves_no_snapshot(provider_file, chains_file):  # noqa: F811
    provider_file(REGISTRY, env=_ENV)
    with pytest.raises(ChainConfigError, match="chains.yaml"):
        chains_file(_yaml("  - match: {model: a1}\n    candidates: [{model: a1}, {model: c1}]\n"))
    assert chain_config.current() is None


# --- T1: the comparison is with the primary, not the previous entry --------------------------


def test_t1_third_entry_fails(provider_file, chains_file, monkeypatch):  # noqa: F811
    provider_file(REGISTRY, env=_ENV)
    monkeypatch.setattr(settings, "PROVIDER_CHAIN_MAX_CANDIDATES", 4)
    text = _yaml(
        "  - match: {model: a1}\n    candidates:\n      - {model: a1}\n      - {model: b1}\n"
        "      - {model: c1}\n      - {model: d1, allow_lower_trust: true}\n"
    )
    with pytest.raises(ChainConfigError) as err:
        chains_file(text)
    message = str(err.value)
    assert "entry 3 (c1, provider c)" in message and "allow_lower_trust" in message
    assert chain_config.current() is None


def test_t1_counterpart_with_both_opt_ins_loads_and_warns_twice(
    provider_file, chains_file, monkeypatch, caplog  # noqa: F811
):
    provider_file(REGISTRY, env=_ENV)
    monkeypatch.setattr(settings, "PROVIDER_CHAIN_MAX_CANDIDATES", 4)
    text = _yaml(
        "  - match: {model: a1}\n    candidates:\n      - {model: a1}\n      - {model: b1}\n"
        "      - {model: c1, allow_lower_trust: true, capability_scoped: true}\n"
        "      - {model: d1, allow_lower_trust: true, capability_scoped: true}\n"
    )
    with caplog.at_level(logging.WARNING, logger=chain_config.__name__):
        snapshot = chains_file(text)
    assert [c.model_id for c in snapshot.chain_for("a1", "v1").candidates] == [
        "a1",
        "b1",
        "c1",
        "d1",
    ]
    warnings = [r.getMessage() for r in caplog.records if r.name == chain_config.__name__]
    assert len(warnings) == 2
    assert "entry 3 (c1, provider c)" in warnings[0]
    assert "entry 4 (d1, provider d)" in warnings[1]
    assert all("internal -> external fallback is allowed by allow_lower_trust" in w for w in warnings)


# --- Pass cases ----------------------------------------------------------------------------


def test_pass_cases_load(registry):
    snapshot, warnings = _validate(
        registry,
        _doc(
            _chain("c1", "c1", "a1"),  # external -> internal: no opt-in needed
            _chain("a1", "a1", "b1"),  # internal -> internal
            _chain("c-no-tools", "c-no-tools", {"model": "d1", **_SCOPED}),  # scoped
            _chain("b1", "b1", {"model": "a1", **_OPT}),  # same trust opt-in: no crossing
            _chain("e1", "e1", {"model": "c1", **_SCOPED}),  # scoped on a full candidate
        ),
    )
    assert warnings == ()
    assert len(snapshot.chains) == 5


def test_capability_the_primary_lacks_is_not_required(registry):
    # d1 has no capabilities, so falling back d1 -> c1 loses nothing.
    _validate(registry, _doc(_chain("d1", "d1", "c1")))


def test_trust_is_checked_before_capabilities(registry):
    # d1 is external AND capless: the first rule broken, in a fixed order, is trust.
    with pytest.raises(ChainConfigError, match="trust external is lower"):
        _validate(registry, _doc(_chain("a1", "a1", "d1")))
    with pytest.raises(ChainConfigError, match="lacks capability tools"):
        _validate(registry, _doc(_chain("a1", "a1", {"model": "d1", **_OPT})))


def test_same_model_with_different_ingress_is_allowed(registry):
    snapshot, _ = _validate(
        registry, _doc(_chain("a1", "a1"), _chain("a1", "a1", "b1", ingress="v1"))
    )
    assert set(snapshot.chains) == {("a1", None), ("a1", "v1")}


def test_single_candidate_chain_is_valid(registry):
    snapshot, _ = _validate(registry, _doc(_chain("a1", "a1")))
    assert snapshot.chains[("a1", None)].candidates == (Candidate("a1"),)


# --- AC4: the WARNING -----------------------------------------------------------------------


def test_warning_once_per_crossing_entry(registry):
    _, warnings = _validate(
        registry,
        _doc(_chain("a1", "a1", {"model": "c1", **_OPT}, {"model": "e1", **_OPT}, ingress="chat")),
    )
    assert warnings == (
        f"{_SRC}: chain 'a1' ingress chat entry 2 (c1, provider c): internal -> external "
        "fallback is allowed by allow_lower_trust",
        f"{_SRC}: chain 'a1' ingress chat entry 3 (e1, provider e): internal -> external "
        "fallback is allowed by allow_lower_trust",
    )


def test_no_warning_without_crossing(registry):
    _, warnings = _validate(
        registry,
        _doc(
            _chain("c1", "c1", {"model": "a1", **_OPT}),  # external -> internal
            _chain("a1", "a1", {"model": "b1", **_OPT}),  # same trust
            _chain("e1", "e1", {"model": "c1", **_OPT}),  # external -> external
        ),
    )
    assert warnings == ()


def test_warnings_log_only_after_validation_succeeds(provider_file, chains_file, caplog):  # noqa: F811
    provider_file(REGISTRY, env=_ENV)
    text = _yaml(
        "  - match: {model: a1}\n"
        "    candidates: [{model: a1}, {model: c1, allow_lower_trust: true}]\n"
        "  - match: {model: b1}\n    candidates: [{model: b1}, {model: ghost}]\n"
    )
    with caplog.at_level(logging.WARNING, logger=chain_config.__name__):
        with pytest.raises(ChainConfigError):
            chains_file(text)
    assert not [r for r in caplog.records if r.name == chain_config.__name__]


# --- AC2: lookup and immutability ------------------------------------------------------------


def test_lookup_order(registry):
    snapshot, _ = _validate(
        registry,
        _doc(
            _chain("a1", "a1", "b1"),
            _chain("a1", "a1", {"model": "c1", **_OPT, **_SCOPED}, ingress="v1"),
        ),
    )
    exact = snapshot.chain_for("a1", "v1")
    assert [c.model_id for c in exact.candidates] == ["a1", "c1"]
    assert exact.candidates[1] == Candidate("c1", True, True)  # flags and order preserved
    assert [c.model_id for c in snapshot.chain_for("a1", "chat").candidates] == ["a1", "b1"]
    # ingress=None on a chain keyed only by ingress v1 falls to the synthesised chain.
    only_v1, _ = _validate(registry, _doc(_chain("a1", "a1", "b1", ingress="v1")))
    assert only_v1.chain_for("a1", None) == Chain("a1", None, (Candidate("a1"),))
    assert snapshot.chain_for("zzz", "v1") == Chain("zzz", None, (Candidate("zzz"),))


def test_snapshot_is_immutable(registry):
    snapshot, _ = _validate(registry, _doc(_chain("a1", "a1", "b1")))
    chain = snapshot.chain_for("a1", None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        chain.model = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.chains = {}
    with pytest.raises(dataclasses.FrozenInstanceError):
        chain.candidates[0].allow_lower_trust = True
    with pytest.raises(TypeError):
        snapshot.chains[("x", None)] = chain
    assert isinstance(chain.candidates, tuple)


def test_example_file_loads(provider_file, chains_file):  # noqa: F811
    root = Path(__file__).resolve().parents[1] / "examples"
    text = (root / "providers.yaml").read_text(encoding="utf-8")
    registry = provider_file(text, env={"VLLM_API_KEY": "k"})
    snapshot = chains_file((root / "chains.yaml").read_text(encoding="utf-8"))
    assert snapshot is not None and snapshot.chains
    for chain in snapshot.chains.values():
        assert chain.candidates[0].model_id == chain.model
        assert all(c.model_id in registry.models_by_id for c in chain.candidates)


# --- AC5: off -----------------------------------------------------------------------------------


def test_no_file_is_prd020(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_CHAINS_FILE", "")
    chain_config.load()
    assert chain_config.current() is None
    assert chain_for("m", "v1") == Chain("m", None, (Candidate("m"),))
    assert chain_for("m", None).candidates[0] == Candidate("m", False, False)


def test_load_empty_setting_clears_a_previous_snapshot(provider_file, chains_file, monkeypatch):  # noqa: F811
    provider_file(REGISTRY, env=_ENV)
    assert chains_file(_yaml("  - match: {model: a1}\n    candidates: [{model: a1}, {model: b1}]\n"))
    monkeypatch.setattr(settings, "PROVIDER_CHAINS_FILE", "")
    chain_config.load()
    assert chain_config.current() is None


def test_chains_file_without_providers_file(tmp_path, monkeypatch):
    path = tmp_path / "chains.yaml"
    path.write_text(_yaml("  - match: {model: a}\n    candidates: [{model: a}]\n"), encoding="utf-8")
    monkeypatch.setattr(settings, "PROVIDERS_FILE", "")
    monkeypatch.setattr(settings, "PROVIDER_CHAINS_FILE", str(path))
    provider_registry.reset()
    with pytest.raises(ChainConfigError, match="needs PROVIDERS_FILE"):
        chain_config.load()
    assert chain_config.current() is None


def test_unreadable_and_invalid_yaml_name_the_file(provider_file, tmp_path, monkeypatch):  # noqa: F811
    provider_file(REGISTRY, env=_ENV)
    monkeypatch.setattr(settings, "PROVIDER_CHAINS_FILE", str(tmp_path / "nope.yaml"))
    with pytest.raises(ChainConfigError, match="nope.yaml.*cannot be read"):
        chain_config.load()
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\nversion: 1\nchains: []\n", encoding="utf-8")  # duplicate key
    monkeypatch.setattr(settings, "PROVIDER_CHAINS_FILE", str(bad))
    with pytest.raises(ChainConfigError, match="bad.yaml.*not valid YAML"):
        chain_config.load()
    chain_config.reset()


# --- Purity -------------------------------------------------------------------------------------


def test_only_load_reads_settings():
    tree = ast.parse(inspect.getsource(chain_config))
    offenders = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name != "load":
            offenders += [
                node.name
                for sub in ast.walk(node)
                if isinstance(sub, ast.Name) and sub.id in ("settings", "os", "open")
            ]
    assert offenders == []


def test_validation_works_with_settings_unreachable(registry, monkeypatch):
    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"settings.{name} read during validation")

    monkeypatch.setattr(chain_config, "settings", _Boom())
    snapshot, warnings = _validate(registry, _doc(_chain("a1", "a1", {"model": "c1", **_OPT})))
    assert isinstance(snapshot, ChainSnapshot) and len(warnings) == 1
    assert chain_for("a1", None).candidates[0].model_id == "a1"


# --- Wiring: both lifespans (E2E) -------------------------------------------------------------


@pytest.fixture
def _boot(temp_db, monkeypatch):
    # The lifespan calls init_db(); RBAC off because the fixture database has no seeded users.
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    yield
    chain_config.reset()


def test_lifespan_loads_the_chains_after_the_registry(_boot, provider_file, chains_file):  # noqa: F811
    from fastapi.testclient import TestClient

    from app.main import app

    provider_file(REGISTRY, env=_ENV)
    chains_file(_yaml("  - match: {model: a1}\n    candidates: [{model: a1}, {model: b1}]\n"))
    chain_config.reset()  # the lifespan, not the fixture, must put them in force
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert [c.model_id for c in chain_for("a1", "v1").candidates] == ["a1", "b1"]


def test_lifespan_refuses_a_crossing_chain_without_the_opt_in(_boot, provider_file, monkeypatch, tmp_path):  # noqa: F811
    from fastapi.testclient import TestClient

    from app.main import app
    from tests._providers import write_chains

    provider_file(REGISTRY, env=_ENV)
    text = _yaml("  - match: {model: a1}\n    candidates: [{model: a1}, {model: c1}]\n")
    monkeypatch.setattr(settings, "PROVIDER_CHAINS_FILE", write_chains(tmp_path, text))
    with pytest.raises(ChainConfigError, match="allow_lower_trust"):
        with TestClient(app):
            pass


def test_chat_ui_registers_chain_load_after_the_registry_load():
    # The chat UI bypasses app.main's lifespan (PRD-016 6.12); Reflex runs tasks in order.
    source = (Path(__file__).resolve().parents[1] / "chat_ui" / "chat_ui" / "chat_ui.py").read_text(
        encoding="utf-8"
    )
    registry = source.index("app.register_lifespan_task(provider_registry.load)")
    chains = source.index("app.register_lifespan_task(chain_config.load)")
    assert registry < chains < source.index("app.register_lifespan_task(authz.check_bootstrap)")
