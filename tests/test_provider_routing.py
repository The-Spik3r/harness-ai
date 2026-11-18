"""PRD-020 STORY-004: route resolution, visible models and authorize_route."""

import dataclasses
import socket

import pytest

from app.config import settings
from app.services import authz, provider_registry
from app.services.authz import PermissionDenied
from app.services.identity import Identity
from app.services.provider_registry import Route, resolve, supports_tools, visible_models
from tests._providers import provider_file  # noqa: F401

SENTINEL_KEY = "sk-SENTINEL-KEY-999"

REGISTRY = """
version: 1
default_model: openai/gpt-4o
providers:
  - name: openrouter
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    passthrough: true
    passthrough_capabilities: {tools: true}
    models:
      - id: openai/gpt-4o
        capabilities: {tools: true}
      - id: anthropic/claude
        upstream: anthropic/claude-3.5-sonnet
        roles: [admin]
  - name: ollama
    type: openai_compatible
    base_url: http://127.0.0.1:11434/v1
    trust: internal
    pii: relaxed
    roles: [admin, user]
    models:
      - id: ollama/qwen2.5-coder:7b
        capabilities: {streaming: true}
      - id: ollama/open
        roles: [auditor]
  - name: openai
    type: openai_compatible
    base_url: https://api.openai.com/v1
    models:
      - id: openai/other-listed
"""

NO_PASSTHROUGH = """
version: 1
default_model: m1
providers:
  - name: p1
    type: openai_compatible
    base_url: https://example.com/v1
    models:
      - id: m1
"""


def ident(role):
    return Identity(user_id="u", role=role)


def _deny(role, model):
    with pytest.raises(PermissionDenied) as exc:
        authz.authorize_route(ident(role), model)
    return exc.value


# --- resolve (AC1) -------------------------------------------------------------


def test_resolve_catalogued(provider_file):
    provider_file(REGISTRY)
    route = resolve("anthropic/claude")
    assert route.catalogued and route.model.id == "anthropic/claude"
    assert route.upstream_model == "anthropic/claude-3.5-sonnet"
    assert route.provider.name == "openrouter"
    assert resolve("ollama/qwen2.5-coder:7b").provider.name == "ollama"
    assert resolve("ollama/qwen2.5-coder:7b").upstream_model == "ollama/qwen2.5-coder:7b"


def test_resolve_passthrough_keeps_id_as_sent(provider_file):
    provider_file(REGISTRY)
    route = resolve("some/unlisted:model")
    assert not route.catalogued and route.model is None
    assert route.upstream_model == "some/unlisted:model"
    assert route.provider.name == "openrouter"
    assert route.capabilities.tools is True


def test_resolve_none_without_passthrough(provider_file):
    provider_file(NO_PASSTHROUGH)
    assert resolve("m1") is not None
    assert resolve("nope") is None
    assert supports_tools("nope") is False


def test_resolve_no_prefix_parsing(provider_file):
    provider_file(REGISTRY)
    # a provider literally named `openai` exists, but the id is never split on "/"
    route = resolve("openai/other")
    assert not route.catalogued and route.provider.name == "openrouter"
    assert route.upstream_model == "openai/other"
    assert resolve("openai/other-listed").provider.name == "openai"
    assert not resolve("OPENAI/GPT-4O").catalogued  # case-sensitive


def test_route_frozen_and_holds_no_key(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SENTINEL_KEY)
    provider_file(REGISTRY, env={"OPENROUTER_API_KEY": SENTINEL_KEY})
    route = resolve("openai/gpt-4o")
    with pytest.raises(dataclasses.FrozenInstanceError):
        route.model_id = "x"
    assert SENTINEL_KEY not in repr(route)
    assert not any("key" in f.name for f in dataclasses.fields(Route))


# --- authorize_route (AC2-AC4) -------------------------------------------------


@pytest.mark.parametrize(
    "role,model,allowed",
    [
        ("user", "openai/gpt-4o", True),  # no model roles, no provider roles: every role
        ("auditor", "openai/gpt-4o", True),
        ("user", "anthropic/claude", False),  # model roles [admin]
        ("user", "ollama/qwen2.5-coder:7b", True),  # provider roles [admin, user]
        ("auditor", "ollama/qwen2.5-coder:7b", False),
        ("auditor", "ollama/open", True),  # model roles override provider roles
        ("user", "ollama/open", False),
    ],
)
def test_effective_roles_matrix(provider_file, monkeypatch, role, model, allowed):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    provider_file(REGISTRY)
    if allowed:
        assert authz.authorize_route(ident(role), model).model_id == model
    else:
        _deny(role, model)


def test_unknown_and_forbidden_are_indistinguishable(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    provider_file(NO_PASSTHROUGH)
    unknown = _deny("user", "ghost")
    provider_file(REGISTRY)
    forbidden = _deny("user", "anthropic/claude")
    assert unknown.permission == "query:model:ghost"
    assert forbidden.permission == "query:model:anthropic/claude"
    assert str(unknown).replace("ghost", "X") == str(forbidden).replace("anthropic/claude", "X")
    assert type(unknown) is type(forbidden)


def test_admin_wildcard_any_model(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    provider_file(REGISTRY)
    assert authz.authorize_route(ident("admin"), "ollama/open").catalogued
    assert not authz.authorize_route(ident("admin"), "free/for-all").catalogued


def test_passthrough_denied_to_non_wildcard(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    provider_file(REGISTRY)
    _deny("user", "free/for-all")


def test_wildcard_roles_setting_patch(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    provider_file(REGISTRY)
    monkeypatch.setattr(authz, "MODEL_ALLOWLIST_WILDCARD_ROLES", {"auditor"})
    assert authz.authorize_route(ident("auditor"), "anthropic/claude")
    _deny("admin", "ollama/open")  # no longer wildcard; model roles are [auditor]


def test_rbac_off_unresolvable_denied(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    provider_file(NO_PASSTHROUGH)
    err = _deny("admin", "ghost")
    assert err.permission == "query:model:ghost"


def test_rbac_off_returns_route_without_role_check(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    provider_file(REGISTRY)
    assert authz.authorize_route(ident("user"), "anthropic/claude").model_id == "anthropic/claude"
    assert authz.authorize_route(ident("nobody"), "free/for-all").catalogued is False


def test_authorize_model_returns_none(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    provider_file(REGISTRY)
    assert authz.authorize_model(ident("user"), "openai/gpt-4o") is None
    with pytest.raises(PermissionDenied):
        authz.authorize_model(ident("user"), "anthropic/claude")


# --- relaxes_input / visible_models / supports_tools (AC5) ----------------------


@pytest.mark.parametrize("pii_on", [True, False])
@pytest.mark.parametrize(
    "trust,pii", [("internal", "relaxed"), ("internal", "standard"), ("external", "standard")]
)
def test_relaxes_input_truth_table(monkeypatch, pii_on, trust, pii):
    base = provider_registry.current().passthrough_provider
    provider = dataclasses.replace(base, trust=trust, pii=pii)
    route = Route("m", "m", provider, provider.passthrough_capabilities, False, None)
    relaxed = (trust, pii) == ("internal", "relaxed")
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", pii_on)
    assert route.relaxes_input() is (pii_on and relaxed)
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", not pii_on)  # read at call time
    assert route.relaxes_input() is ((not pii_on) and relaxed)


def test_visible_models_order_and_filter(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    provider_file(REGISTRY)
    everything = [
        "openai/gpt-4o",
        "anthropic/claude",
        "ollama/qwen2.5-coder:7b",
        "ollama/open",
        "openai/other-listed",
    ]
    assert [m.id for m in visible_models(ident("admin"))] == everything
    assert [m.id for m in visible_models(ident("user"))] == [
        "openai/gpt-4o",
        "ollama/qwen2.5-coder:7b",
        "openai/other-listed",
    ]
    assert [m.id for m in visible_models(ident("auditor"))] == [
        "openai/gpt-4o",
        "ollama/open",
        "openai/other-listed",
    ]
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    assert [m.id for m in visible_models(ident("user"))] == everything


def test_supports_tools_file_mode(provider_file):
    provider_file(REGISTRY)
    assert supports_tools("openai/gpt-4o") is True
    assert supports_tools("ollama/open") is False  # catalogued, tools unset
    assert supports_tools("free/for-all") is True  # passthrough_capabilities.tools


def test_pure_no_io(provider_file, monkeypatch):
    provider_file(REGISTRY)
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)

    def boom(*a, **k):
        raise AssertionError("I/O in a pure function")

    monkeypatch.setattr("builtins.open", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    assert resolve("openai/gpt-4o")
    assert visible_models(ident("user"))
    assert supports_tools("openai/gpt-4o")
    assert authz.authorize_route(ident("user"), "openai/gpt-4o")


# --- legacy equivalence (binding) ----------------------------------------------


def _old_authorize_model(identity, model):
    if not settings.RBAC_ENABLED:
        return
    if identity.role in authz.MODEL_ALLOWLIST_WILDCARD_ROLES:
        return
    if model in settings.model_allowlist_list:
        return
    raise PermissionDenied(f"query:model:{model}")


def _outcome(fn, identity, model):
    try:
        fn(identity, model)
    except PermissionDenied as exc:
        return ("deny", exc.permission, str(exc))
    return ("ok",)


@pytest.mark.parametrize("rbac", [True, False])
@pytest.mark.parametrize("allowlist", ["a,b", ""])
@pytest.mark.parametrize("role", ["admin", "user", "auditor", "mystery"])
@pytest.mark.parametrize("model", ["a", "b", "zzz"])
def test_legacy_authorize_model_equivalence(monkeypatch, rbac, allowlist, role, model):
    provider_registry.reset()
    monkeypatch.setattr(settings, "RBAC_ENABLED", rbac)
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", allowlist)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")
    assert _outcome(authz.authorize_model, ident(role), model) == _outcome(
        _old_authorize_model, ident(role), model
    )


@pytest.mark.parametrize("tools", ["", "a"])
@pytest.mark.parametrize("model", ["a", "b", "zzz"])
def test_legacy_supports_tools_matches_v1_rule(monkeypatch, tools, model):
    provider_registry.reset()
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "a,b")
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", tools)
    tools_list = settings.v1_tool_models_list
    assert supports_tools(model) is ((not tools_list) or model in tools_list)
