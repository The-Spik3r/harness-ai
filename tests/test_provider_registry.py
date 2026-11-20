"""PRD-020 STORY-003: the provider registry loader, validation and legacy registry."""

import dataclasses
import logging
from pathlib import Path

import pytest

from app.config import settings
from app.services import action_config, provider_registry
from app.services.provider_registry import ProviderRegistryError, classify_base_url
from tests._providers import provider_file, providers_file, write_registry  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
KEY = "sk-SECRET-VALUE-123"

FULL = """
version: 1
default_model: openai/gpt-4o
providers:
  - name: openrouter
    label: OpenRouter
    type: openai_compatible
    base_url: https://openrouter.ai/api/v1
    key_env: OPENROUTER_API_KEY
    byok: true
    passthrough: true
    passthrough_capabilities: {tools: true}
    models:
      - id: openai/gpt-4o
        capabilities: {tools: true, max_context_tokens: 128000}
  - name: ollama
    type: openai_compatible
    base_url: http://127.0.0.1:11434/v1
    trust: internal
    pii: relaxed
    usage_missing: estimate
    estimate_chars_per_token: 3
    timeout_seconds: 300
    models:
      - id: ollama/qwen
        upstream: qwen:7b
        roles: [admin]
        capabilities: {streaming: true}
"""

MINIMAL = """
version: 1
default_model: m1
providers:
  - name: p1
    type: openai_compatible
    base_url: https://example.com/v1
    models:
      - id: m1
"""


def _p(base_url="https://example.com/v1", extra="", models="      - id: m1\n"):
    return (
        "version: 1\ndefault_model: m1\nproviders:\n  - name: p1\n"
        f"    type: openai_compatible\n    base_url: {base_url}\n{extra}"
        f"    models:\n{models}"
    )


_SECOND = "  - name: p2\n    type: openai_compatible\n    base_url: https://b.example/v1\n"


_ANTHROPIC = (
    "version: 1\ndefault_model: m1\nproviders:\n  - name: p1\n"
    "    type: anthropic\n    base_url: https://api.anthropic.com\n{extra}"
    "    models:\n{models}"
)


def _a(extra="", models="      - id: m1\n        default_max_tokens: 4096\n"):
    return _ANTHROPIC.format(extra=extra, models=models)


@pytest.fixture(autouse=True)
def _restore():
    yield
    provider_registry.reset()


# --- AC1 -----------------------------------------------------------------------


def test_full_file_exposes_defaults(provider_file):
    reg = provider_file(FULL)
    assert not reg.is_legacy and reg.default_model == "openai/gpt-4o"
    openrouter, ollama = reg.providers
    assert openrouter.passthrough_capabilities.tools is True
    assert reg.passthrough_provider is openrouter
    model = reg.models_by_id["ollama/qwen"]
    assert (model.upstream, model.roles, model.provider_name) == ("qwen:7b", ("admin",), "ollama")
    assert model.capabilities == provider_registry.Capabilities(streaming=True)
    assert (ollama.pii, ollama.timeout_seconds, ollama.estimate_chars_per_token) == (
        "relaxed",
        300.0,
        3.0,
    )


def test_minimal_file_defaults(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 77.0)
    p = provider_file(MINIMAL).providers[0]
    assert (p.label, p.trust, p.pii, p.byok, p.passthrough, p.insecure_http) == (
        "p1",
        "external",
        "standard",
        False,
        False,
        False,
    )
    assert (p.usage_missing, p.estimate_chars_per_token, p.timeout_seconds) == (
        "estimate",
        4.0,
        77.0,
    )
    assert p.key_env is None and p.roles is None
    m = p.models[0]
    assert (m.upstream, m.roles, m.capabilities) == ("m1", None, provider_registry.Capabilities())
    assert p.passthrough_capabilities == provider_registry.Capabilities()


def test_snapshot_is_immutable(provider_file):
    reg = provider_file(FULL)
    with pytest.raises(dataclasses.FrozenInstanceError):
        reg.providers[0].name = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        reg.models_by_id["ollama/qwen"].capabilities.tools = True
    with pytest.raises(TypeError):
        reg.models_by_id["new"] = None


# --- AC2 -----------------------------------------------------------------------

_BAD = [
    ("unknown-top", MINIMAL + "extra: 1\n", "unknown key 'extra'"),
    ("unknown-provider", _p(extra="    colour: red\n"), "unknown key 'colour'"),
    ("unknown-model", _p(models="      - id: m1\n        foo: 1\n"), "unknown key 'foo'"),
    (
        "unknown-capability",
        _p(models="      - id: m1\n        capabilities: {x: 1}\n"),
        "unknown key 'x'",
    ),
    ("missing-name", MINIMAL.replace("    name: p1\n", "").replace("- name: p1", "- label: L"), "missing key 'name'"),
    ("missing-type", MINIMAL.replace("    type: openai_compatible\n", ""), "missing key 'type'"),
    (
        "missing-base-url",
        MINIMAL.replace("    base_url: https://example.com/v1\n", ""),
        "missing key 'base_url'",
    ),
    (
        "missing-models",
        MINIMAL.replace("    models:\n      - id: m1\n", ""),
        "missing key 'models'",
    ),
    ("version", MINIMAL.replace("version: 1", "version: 2"), "version"),
    ("missing-default", MINIMAL.replace("default_model: m1\n", ""), "missing key 'default_model'"),
    (
        "dup-provider",
        MINIMAL + MINIMAL.split("providers:\n")[1].replace("id: m1", "id: m2"),
        "duplicate provider name",
    ),
    ("dup-model", _p(models="      - id: m1\n      - id: m1\n"), "duplicate model id"),
    (
        "two-passthrough",
        _p(extra="    passthrough: true\n") + _SECOND + "    passthrough: true\n",
        "only one provider",
    ),
    (
        "default-unroutable",
        MINIMAL.replace("default_model: m1", "default_model: zzz"),
        "'zzz' is not catalogued",
    ),
    # PRD-022 F1-addition (STORY-004): "anthropic" is now a valid type, so the unknown-type row
    # uses another name and expects the allowed set (both type names) in the message.
    ("type", MINIMAL.replace("openai_compatible", "bedrock"), "'bedrock' is not one of"),
    ("type-names-anthropic", MINIMAL.replace("openai_compatible", "bedrock"), "anthropic"),
    ("type-names-openai", MINIMAL.replace("openai_compatible", "bedrock"), "openai_compatible"),
    # PRD-022 STORY-004: the catalogue fields and the anthropic-only rules.
    ("anthropic-no-max-tokens", _a(models="      - id: m1\n"), "default_max_tokens: required"),
    (
        "max-tokens-zero",
        _a(models="      - id: m1\n        default_max_tokens: 0\n"),
        "default_max_tokens: must be at least 1",
    ),
    (
        "max-tokens-bool",
        _a(models="      - id: m1\n        default_max_tokens: true\n"),
        "default_max_tokens: must be an integer",
    ),
    (
        "max-tokens-str",
        _a(models="      - id: m1\n        default_max_tokens: '8'\n"),
        "default_max_tokens: must be an integer",
    ),
    (
        "prompt-cache-bad",
        _a(models="      - id: m1\n        default_max_tokens: 9\n        prompt_cache: sometimes\n"),
        "prompt_cache: 'sometimes' is not one of",
    ),
    ("anthropic-passthrough", _a(extra="    passthrough: true\n"), "passthrough: refused"),
    ("bad-name", MINIMAL.replace("name: p1", "name: Bad_Name"), "name: must match"),
    ("pii-relaxed-external", _p(extra="    pii: relaxed\n"), "requires 'trust: internal'"),
    ("internal-public-ip", _p("https://8.8.8.8/v1", "    trust: internal\n"), "public IP"),
    ("byok-unusable", _p(extra="    byok: true\n", models="      []\n"), "unusable"),
    (
        "ctx-zero",
        _p(models="      - id: m1\n        capabilities: {max_context_tokens: 0}\n"),
        "max_context_tokens",
    ),
    (
        "ctx-bool",
        _p(models="      - id: m1\n        capabilities: {max_context_tokens: true}\n"),
        "max_context_tokens",
    ),
    ("cpt-high", _p(extra="    estimate_chars_per_token: 9\n"), "estimate_chars_per_token"),
    ("cpt-zero", _p(extra="    estimate_chars_per_token: 0\n"), "estimate_chars_per_token"),
    ("timeout-zero", _p(extra="    timeout_seconds: 0\n"), "timeout_seconds"),
    ("timeout-bool", _p(extra="    timeout_seconds: true\n"), "timeout_seconds"),
    (
        "key-env-unset",
        _p(extra="    key_env: NOPE_UNSET_KEY_VAR\n"),
        "'NOPE_UNSET_KEY_VAR' is unset or empty",
    ),
    (
        "passthrough-caps-without-passthrough",
        _p(extra="    passthrough_capabilities: {tools: true}\n"),
        "passthrough_capabilities",
    ),
    # Orchestrator addition (STORY-003): roles must be roles RBAC knows, and non-empty.
    ("provider-unknown-role", _p(extra="    roles: [admin, usr]\n"), "unknown role 'usr'"),
    ("model-unknown-role", _p(models="      - id: m1\n        roles: [ghost]\n"), "unknown role 'ghost'"),
    ("provider-empty-roles", _p(extra="    roles: []\n"), "non-empty list"),
    ("model-empty-roles", _p(models="      - id: m1\n        roles: []\n"), "non-empty list"),
]


@pytest.mark.parametrize(
    "snippet,fragment", [(b, c) for _, b, c in _BAD], ids=[a for a, _, _ in _BAD]
)
def test_startup_error(tmp_path, monkeypatch, snippet, fragment):
    monkeypatch.delenv("NOPE_UNSET_KEY_VAR", raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env
    path = write_registry(tmp_path, snippet)
    monkeypatch.setattr(settings, "PROVIDERS_FILE", path)
    with pytest.raises(ProviderRegistryError) as err:
        provider_registry.load()
    message = str(err.value)
    assert path in message and fragment in message
    assert provider_registry._snapshot is None  # nothing half-built


def test_startup_error_names_provider_and_model(tmp_path, monkeypatch):
    path = write_registry(tmp_path, _p(models="      - id: m1\n        roles: [ghost]\n"))
    monkeypatch.setattr(settings, "PROVIDERS_FILE", path)
    with pytest.raises(ProviderRegistryError, match=r"'p1'.*'m1'.*ghost"):
        provider_registry.load()


def test_unreadable_and_invalid_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDERS_FILE", str(tmp_path / "missing.yaml"))
    with pytest.raises(ProviderRegistryError, match="cannot be read"):
        provider_registry.load()
    monkeypatch.setattr(settings, "PROVIDERS_FILE", write_registry(tmp_path, "a: b\na: c\n"))
    with pytest.raises(ProviderRegistryError, match="not valid YAML"):
        provider_registry.load()


def test_known_roles_accepted(provider_file):
    reg = provider_file(_p(extra="    roles: [admin, user]\n"))
    assert reg.providers[0].roles == ("admin", "user")


def test_errors_never_echo_key_or_url(tmp_path, monkeypatch):
    texts = (
        _p(f"http://user:pw@example.com/v1?token={KEY}"),
        _p(f"ftp://user:pw@host/x?token={KEY}"),
        _p(f"http://user:pw@8.8.8.8/v1?token={KEY}", "    trust: internal\n"),
    )
    for text in texts:
        monkeypatch.setattr(settings, "PROVIDERS_FILE", write_registry(tmp_path, text))
        with pytest.raises(ProviderRegistryError) as err:
            provider_registry.load()
        for secret in (KEY, "pw", "token="):
            assert secret not in str(err.value)


# --- AC3 -----------------------------------------------------------------------

_OPT = "    insecure_http: true\n"


@pytest.mark.parametrize(
    "url,extra,ok",
    [
        ("https://example.com/v1", "", True),
        ("http://127.0.0.1:8000/v1", "", True),
        ("http://localhost/v1", "", True),
        ("http://[::1]:8000/v1", "", True),
        ("http://10.0.0.1/v1", "", False),
        ("http://10.0.0.1/v1", _OPT, True),
        ("http://172.16.0.1/v1", _OPT, True),
        ("http://172.32.0.1/v1", _OPT, False),
        ("http://192.168.1.1/v1", _OPT, True),
        ("http://[fd00::1]/v1", _OPT, True),
        ("http://100.64.0.1/v1", _OPT, False),
        ("http://169.254.1.1/v1", _OPT, False),
        ("http://gpu.internal/v1", _OPT, False),
        ("https://example.com/v1", _OPT, True),
        ("ftp://example.com/v1", "", False),
        ("https:///v1", "", False),
    ],
)
def test_base_url_matrix(tmp_path, monkeypatch, url, extra, ok):
    monkeypatch.setattr(settings, "PROVIDERS_FILE", write_registry(tmp_path, _p(url, extra)))
    if ok:
        provider_registry.load()
    else:
        with pytest.raises(ProviderRegistryError, match="base_url"):
            provider_registry.load()


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://127.0.0.1:1/x", ("http://", "127.0.0.1", "loopback")),
        ("HTTP://LocalHost/x", ("http://", "localhost", "loopback")),
        ("http://[::1]:80", ("http://", "::1", "loopback")),
        ("http://10.1.2.3", ("http://", "10.1.2.3", "private_ip")),
        ("http://[fc00::1]", ("http://", "fc00::1", "private_ip")),
        ("http://172.32.0.1", ("http://", "172.32.0.1", "public_ip")),
        ("http://100.64.0.1", ("http://", "100.64.0.1", "public_ip")),
        ("http://[::ffff:10.0.0.1]", ("http://", "::ffff:10.0.0.1", "public_ip")),
        ("https://example.com", ("https://", "example.com", "hostname")),
        ("https://", ("https://", "", "hostname")),
    ],
)
def test_classify_base_url(url, expected):
    assert classify_base_url(url) == expected


# --- AC4 -----------------------------------------------------------------------


def _warnings(caplog):
    return [
        r
        for r in caplog.records
        if r.name == provider_registry.logger.name and r.levelno == logging.WARNING
    ]


def test_warning_insecure_http(provider_file, caplog):
    caplog.set_level(logging.WARNING, logger=provider_registry.logger.name)
    provider_file(_p("http://192.168.1.40:8000/v1", _OPT))
    recs = [r.getMessage() for r in _warnings(caplog)]
    assert len(recs) == 1 and "http://192.168.1.40" in recs[0] and "insecure_http" in recs[0]


def test_no_warning_for_noop_insecure_http(provider_file, caplog):
    caplog.set_level(logging.WARNING, logger=provider_registry.logger.name)
    provider_file(_p("https://example.com/v1", _OPT))
    assert _warnings(caplog) == []


def test_warning_internal_hostname(provider_file, caplog):
    caplog.set_level(logging.WARNING, logger=provider_registry.logger.name)
    provider_file(_p("https://gpu.corp.example/v1", "    trust: internal\n"))
    recs = [r.getMessage() for r in _warnings(caplog)]
    assert len(recs) == 1 and "gpu.corp.example" in recs[0] and "cannot be verified" in recs[0]


def test_warning_key_env_not_secret_glob(provider_file, caplog):
    caplog.set_level(logging.WARNING, logger=provider_registry.logger.name)
    assert not any(c.search("PLAINNAME") for c in action_config.get_policy().secrets.env.compiled)
    provider_file(_p(extra="    key_env: PLAINNAME\n"), env={"PLAINNAME": KEY})
    recs = [r.getMessage() for r in _warnings(caplog)]
    assert len(recs) == 1 and "PLAINNAME" in recs[0]


def test_warnings_never_fail_or_leak(provider_file, caplog):
    caplog.set_level(logging.DEBUG)
    text = _p(
        "http://10.0.0.5/v1?token=" + KEY, _OPT + "    key_env: PLAINNAME\n    trust: internal\n"
    )
    reg = provider_file(text, env={"PLAINNAME": KEY})
    assert reg.providers[0].name == "p1"
    for r in caplog.records:
        assert KEY not in r.getMessage() and "token=" not in r.getMessage()


def test_failing_file_logs_no_warning(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger=provider_registry.logger.name)
    text = _p("http://10.0.0.5/v1", _OPT) + "    bogus: 1\n"
    monkeypatch.setattr(settings, "PROVIDERS_FILE", write_registry(tmp_path, text))
    with pytest.raises(ProviderRegistryError):
        provider_registry.load()
    assert _warnings(caplog) == []


# --- Keys ----------------------------------------------------------------------


def test_key_from_environ_and_keyless(provider_file):
    reg = provider_file(_p(extra="    key_env: MY_PROV_KEY\n"), env={"MY_PROV_KEY": KEY})
    assert provider_registry.api_key_for(reg.providers[0]) == KEY
    reg = provider_file(MINIMAL)
    assert provider_registry.api_key_for(reg.providers[0]) is None


def test_key_from_dotenv(tmp_path, monkeypatch, provider_file):
    monkeypatch.delenv("DOTENV_ONLY_KEY", raising=False)
    (tmp_path / ".env").write_text(f"DOTENV_ONLY_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    reg = provider_file(_p(extra="    key_env: DOTENV_ONLY_KEY\n"))
    assert provider_registry.api_key_for(reg.providers[0]) == KEY


def test_openrouter_key_comes_from_settings(provider_file, monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", KEY)
    reg = provider_file(_p(extra="    key_env: OPENROUTER_API_KEY\n"))
    assert provider_registry.api_key_for(reg.providers[0]) == KEY


def test_empty_key_env_names_only_the_variable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EMPTY_KEY_VAR", "")
    path = write_registry(tmp_path, _p(extra="    key_env: EMPTY_KEY_VAR\n"))
    monkeypatch.setattr(settings, "PROVIDERS_FILE", path)
    with pytest.raises(ProviderRegistryError, match="'EMPTY_KEY_VAR' is unset or empty"):
        provider_registry.load()


def test_repr_never_carries_a_key(provider_file):
    reg = provider_file(_p(extra="    key_env: MY_PROV_KEY\n"), env={"MY_PROV_KEY": KEY})
    assert KEY not in repr(reg) and KEY not in repr(provider_registry.current())
    names = {f.name for f in dataclasses.fields(provider_registry.Provider)}
    assert "key" not in names and "api_key" not in names


# --- AC5: legacy ---------------------------------------------------------------


def test_legacy_registry_matches_section_6_2(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDERS_FILE", "")
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "gpt-4, a/b ,gpt-4")
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "a/b")
    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 12.5)
    provider_registry.load()
    reg = provider_registry.current()
    p = reg.providers[0]
    assert reg.is_legacy and reg.default_model == "gpt-4" and reg.passthrough_provider is p
    assert (p.name, p.label, p.type, p.key_env) == (
        "openrouter",
        "OpenRouter",
        "openai_compatible",
        "OPENROUTER_API_KEY",
    )
    assert (p.base_url, p.timeout_seconds, p.trust, p.pii) == (
        "http://127.0.0.1:9999/v1",
        12.5,
        "external",
        "standard",
    )
    assert (p.byok, p.passthrough, p.usage_missing, p.estimate_chars_per_token, p.roles) == (
        True,
        True,
        "error",
        4.0,
        None,
    )
    assert list(reg.models_by_id) == ["gpt-4", "a/b"]  # de-duplicated, first wins
    assert reg.models_by_id["gpt-4"].capabilities.tools is False
    assert reg.models_by_id["a/b"].capabilities.tools is True
    assert reg.models_by_id["a/b"].upstream == "a/b" and reg.models_by_id["a/b"].roles is None
    assert p.passthrough_capabilities.tools is False  # a set list binds admin too
    assert provider_registry.api_key_for(p) == settings.OPENROUTER_API_KEY


def test_legacy_tracks_live_settings(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDERS_FILE", "")
    provider_registry.load()
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "x/one")
    assert list(provider_registry.current().models_by_id) == ["x/one"]
    assert provider_registry.current().providers[0].passthrough_capabilities.tools is True
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", "y/two,y/three")
    assert list(provider_registry.current().models_by_id) == ["y/two", "y/three"]
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "other")
    assert provider_registry.api_key_for(provider_registry.current().providers[0]) == "other"


def test_empty_load_does_no_io(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDERS_FILE", "")

    def boom(*a, **k):
        raise AssertionError("empty PROVIDERS_FILE must read no file")

    monkeypatch.setattr(Path, "read_text", boom)
    provider_registry.load()
    assert provider_registry.current().is_legacy


def test_failed_load_keeps_previous_snapshot(provider_file, tmp_path, monkeypatch):
    first = provider_file(MINIMAL)
    path = write_registry(tmp_path, MINIMAL + "bogus: 1\n")
    monkeypatch.setattr(settings, "PROVIDERS_FILE", path)
    with pytest.raises(ProviderRegistryError):
        provider_registry.load()
    assert provider_registry.current() is first


def test_reset_returns_to_legacy(provider_file):
    assert not provider_file(MINIMAL).is_legacy
    provider_registry.reset()
    assert provider_registry.current().is_legacy
    assert provider_registry._keys == {}


def test_empty_load_after_file_returns_to_legacy(provider_file, monkeypatch):
    provider_file(MINIMAL)
    monkeypatch.setattr(settings, "PROVIDERS_FILE", "")
    provider_registry.load()
    assert provider_registry.current().is_legacy


def test_lifespans_call_load_after_action_config():
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert (
        main.index("action_config.load()")
        < main.index("provider_registry.load()")
        < main.index("authz.check_bootstrap()")
    )
    ui = (ROOT / "chat_ui" / "chat_ui" / "chat_ui.py").read_text(encoding="utf-8")
    reg = "app.register_lifespan_task(provider_registry.load)"
    assert (
        ui.index("app.register_lifespan_task(action_config.load)")
        < ui.index(reg)
        < ui.index("app.register_lifespan_task(authz.check_bootstrap)")
    )


# --- AC6: fixture --------------------------------------------------------------


def test_providers_file_restores_legacy(tmp_path, monkeypatch):
    with providers_file(tmp_path, MINIMAL, monkeypatch=monkeypatch) as reg:
        assert not reg.is_legacy and provider_registry.current() is reg
    assert provider_registry.current().is_legacy


def test_providers_file_restores_on_failure(tmp_path, monkeypatch):
    with pytest.raises(ProviderRegistryError):
        with providers_file(tmp_path, MINIMAL + "bogus: 1\n", monkeypatch=monkeypatch):
            pass  # pragma: no cover
    assert provider_registry.current().is_legacy
    with pytest.raises(RuntimeError):
        with providers_file(tmp_path, MINIMAL, monkeypatch=monkeypatch):
            raise RuntimeError("test body failed")
    assert provider_registry.current().is_legacy


def test_providers_file_sets_env(tmp_path, monkeypatch):
    with providers_file(
        tmp_path, _p(extra="    key_env: FIX_KEY\n"), monkeypatch=monkeypatch, env={"FIX_KEY": KEY}
    ) as reg:
        assert provider_registry.api_key_for(reg.providers[0]) == KEY


# --- PRD-022 STORY-004: type anthropic and the catalogue fields ----------------


def test_anthropic_provider_loads_with_the_new_fields(provider_file):
    reg = provider_file(
        _a(
            extra="    usage_missing: error\n",
            models=(
                "      - id: m1\n        default_max_tokens: 4096\n        prompt_cache: auto\n"
                "        capabilities: {forced_tool_choice: true, sampling_params: true}\n"
            ),
        )
    )
    provider = reg.providers[0]
    assert provider.type == "anthropic" and provider.usage_missing == "error"
    model = reg.models_by_id["m1"]
    assert (model.default_max_tokens, model.prompt_cache) == (4096, "auto")
    assert model.capabilities.forced_tool_choice and model.capabilities.sampling_params
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.default_max_tokens = 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.capabilities.forced_tool_choice = False
    assert provider_registry.resolve("m1").provider.type == "anthropic"


def test_anthropic_missing_max_tokens_names_provider_model_and_rule(tmp_path, monkeypatch):
    path = write_registry(tmp_path, _a(models="      - id: m1\n"))
    monkeypatch.setattr(settings, "PROVIDERS_FILE", path)
    with pytest.raises(ProviderRegistryError, match=r"'p1'.*'m1'.*default_max_tokens: required"):
        provider_registry.load()


def test_mixed_registry_routes_each_type(provider_file):
    second = (
        "  - name: p2\n    type: openai_compatible\n    base_url: https://b.example/v1\n"
        "    models:\n      - id: m2\n"
    )
    provider_file(_a() + second)
    assert provider_registry.resolve("m1").provider.type == "anthropic"
    assert provider_registry.resolve("m2").provider.type == "openai_compatible"


def test_openai_compatible_model_gets_the_new_defaults(provider_file):
    model = provider_file(MINIMAL).models_by_id["m1"]
    assert model.default_max_tokens is None and model.prompt_cache == "off"
    assert model.capabilities.forced_tool_choice is False
    assert model.capabilities.sampling_params is False
