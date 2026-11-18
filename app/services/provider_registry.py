"""The provider registry: where it comes from, and what stops the boot (PRD-020 Sections 4, 6.2, F1, F3, F4).

`load()` reads `PROVIDERS_FILE` into an immutable `Registry` snapshot, or -- the
setting empty -- reads no file and derives the **legacy registry** from the
LIVE settings on every access (PRD-020 D1, OD1): one implicit `openrouter`
provider, one catalogue entry per `MODEL_ALLOWLIST` item, passthrough on. The
suite monkeypatches those settings per test, so legacy mode never caches past
the values it was derived from.

Called once at startup in **both** lifespans (`app/main.py` and
`chat_ui/chat_ui/chat_ui.py`): the Reflex `api_transformer` mount bypasses the
former entirely (PRD-016 Section 6.12). Never per request.

This story (STORY-003) is the data model, the validation and the loader.
Resolution (`resolve`, `visible_models`, `supports_tools`) is STORY-004 and the
adapter is STORY-005, so nothing here sends a request.

Keys (PRD-020 T1, T6): the dataclasses hold no key field. `load()` resolves each
provider's `key_env` into `_keys`, beside the snapshot, and `api_key_for` hands
it out. No message, log record or repr in this module carries a key value or a
whole URL: validators quote scheme and host only (`config._scheme_of`'s rule).
"""

import ipaddress
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

import yaml
from dotenv import dotenv_values

from app.config import _LOOPBACK_HOSTS, _scheme_of, settings
from app.services import action_config, authz, strict_yaml

logger = logging.getLogger(__name__)


class ProviderRegistryError(ValueError):
    """`PROVIDERS_FILE` cannot be put in force; the boot stops (PRD-020 F1)."""


# --- Vocabulary (closed, PRD-020 F1) ------------------------------------------

TYPES = ("openai_compatible",)
TRUSTS = ("external", "internal")
PII_MODES = ("standard", "relaxed")
USAGE_MISSING = ("estimate", "error")

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)

_TOP_KEYS = ("version", "default_model", "providers")
_PROVIDER_KEYS = (
    "name",
    "label",
    "type",
    "base_url",
    "key_env",
    "insecure_http",
    "trust",
    "pii",
    "byok",
    "passthrough",
    "passthrough_capabilities",
    "usage_missing",
    "estimate_chars_per_token",
    "timeout_seconds",
    "roles",
    "models",
)
_PROVIDER_REQUIRED = ("name", "type", "base_url")
_MODEL_KEYS = ("id", "upstream", "roles", "capabilities")
_CAPABILITY_KEYS = ("tools", "streaming", "reasoning", "max_context_tokens")


# --- Model (frozen; NO key field anywhere, T1) --------------------------------


@dataclass(frozen=True)
class Capabilities:
    """PRD-020 F4. `max_context_tokens` None means unset."""

    tools: bool = False
    streaming: bool = False
    reasoning: bool = False
    max_context_tokens: Optional[int] = None


@dataclass(frozen=True)
class CatalogModel:
    """One catalogued model. `roles` None means "inherit the provider's, else every role" (F2)."""

    id: str
    upstream: str
    roles: Optional[tuple[str, ...]]
    capabilities: Capabilities
    provider_name: str


@dataclass(frozen=True)
class Provider:
    """One upstream. `key_env` is a variable NAME; the value lives in `_keys`, never here."""

    name: str
    label: str
    type: str
    base_url: str
    key_env: Optional[str]
    insecure_http: bool
    trust: str
    pii: str
    byok: bool
    passthrough: bool
    passthrough_capabilities: Capabilities
    usage_missing: str
    estimate_chars_per_token: float
    timeout_seconds: float
    roles: Optional[tuple[str, ...]]
    models: tuple[CatalogModel, ...]


@dataclass(frozen=True)
class Registry:
    default_model: str
    providers: tuple[Provider, ...]
    models_by_id: Mapping[str, CatalogModel]
    passthrough_provider: Optional[Provider]
    is_legacy: bool


# --- Errors -------------------------------------------------------------------
# Same shape as `action_config`: file, the offending node in path form, the rule.
# (`action_config`'s helpers are private there, so these are copied small.)


def _fail(source: str, *parts: str) -> ProviderRegistryError:
    return ProviderRegistryError(f"{source}: " + ": ".join(parts))


def _allowed(values) -> str:
    return ", ".join(sorted(values))


def _check_keys(source: str, where: str, body: Mapping, allowed, required) -> None:
    unknown = sorted(set(body) - set(allowed), key=str)
    if unknown:
        raise _fail(
            source, where, f"unknown key {unknown[0]!r} (expected one of: {_allowed(allowed)})"
        )
    missing = [key for key in required if key not in body]
    if missing:
        raise _fail(source, where, f"missing key {missing[0]!r} (required: {_allowed(required)})")


def _mapping(source: str, node: str, value: Any) -> Mapping:
    if not isinstance(value, Mapping):
        raise _fail(source, node, f"must be a mapping, got {type(value).__name__}")
    return value


# --- base_url (PRD-020 F3, D5) ------------------------------------------------


def classify_base_url(url: str) -> tuple[str, str, str]:
    """`(scheme, host, kind)` for a base_url; kind is loopback, private_ip, public_ip or hostname.

    `private_ip` is the four explicit networks of PRD-020 D5, NOT
    `ipaddress.is_private` (it also covers link-local and more, O4). Any other
    IP literal -- CGNAT, link-local, IPv4-mapped IPv6 -- is `public_ip`. An
    empty host is returned as "" for the caller to refuse.
    """
    text = url.strip()
    scheme = _scheme_of(text).lower()
    try:
        host = (urlsplit(text).hostname or "").lower()
    except ValueError:
        host = ""
    if host in _LOOPBACK_HOSTS:
        return scheme, host, "loopback"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return scheme, host, "hostname"
    if any(ip.version == net.version and ip in net for net in _PRIVATE_NETWORKS):
        return scheme, host, "private_ip"
    return scheme, host, "public_ip"


def _check_base_url(source: str, where: str, value: Any, insecure_http: bool) -> str:
    """D5's table. Messages quote scheme and host only, never the URL."""
    if not isinstance(value, str) or not value.strip():
        raise _fail(source, where, "base_url: must be a non-empty string")
    scheme, host, kind = classify_base_url(value)
    if scheme not in ("http://", "https://"):
        raise _fail(source, where, f"base_url: scheme {scheme!r} is not http:// or https://")
    if not host:
        raise _fail(source, where, f"base_url: {scheme} URL names no host")
    if scheme == "https://" or kind == "loopback":
        return value.strip()
    if kind == "private_ip":
        if insecure_http:
            return value.strip()
        raise _fail(
            source,
            where,
            f"base_url: http:// to the private address {host!r} needs 'insecure_http: true' "
            "(PRD-020 D5)",
        )
    raise _fail(
        source,
        where,
        f"base_url: http:// to {host!r} is refused ({kind}); plaintext http is allowed only on "
        "loopback, or a private IP literal with 'insecure_http: true' (PRD-020 D5)",
    )


# --- Field validators, one per rule family ------------------------------------


def _check_version(source: str, document: Any) -> Mapping:
    body = _mapping(source, "file", document)
    _check_keys(source, "file", body, _TOP_KEYS, _TOP_KEYS)
    version = body["version"]
    if isinstance(version, bool) or version != 1:
        raise _fail(source, "version", "must be 1")
    return body


def _bool(source: str, where: str, body: Mapping, key: str, default: bool) -> bool:
    value = body.get(key, default)
    if not isinstance(value, bool):
        raise _fail(source, where, f"{key}: must be true or false, got {type(value).__name__}")
    return value


def _number(source: str, where: str, key: str, value: Any, lo: float, hi: Optional[float]) -> float:
    """A real number in (lo, hi]; bools are refused where numbers are expected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(source, where, f"{key}: must be a number, got {type(value).__name__}")
    if not value > lo or (hi is not None and value > hi):
        bound = f"greater than {lo:g}" if hi is None else f"in ({lo:g}, {hi:g}]"
        raise _fail(source, where, f"{key}: must be {bound}, got {value}")
    return float(value)


def _choice(source: str, where: str, key: str, value: Any, vocab) -> str:
    if value not in vocab:
        raise _fail(source, where, f"{key}: {value!r} is not one of: {_allowed(vocab)}")
    return value


def _check_roles(source: str, where: str, value: Any) -> tuple[str, ...]:
    """A non-empty list of roles RBAC knows. A typo must not silently lock everyone out."""
    if not isinstance(value, list) or not value:
        raise _fail(
            source, where, "roles: must be a non-empty list (an empty list makes it unusable)"
        )
    known = authz.ROLE_PERMISSIONS
    for role in value:
        if not isinstance(role, str) or not role.strip():
            raise _fail(source, where, "roles: every entry must be a non-empty string")
        if role not in known:
            raise _fail(
                source, where, f"roles: unknown role {role!r} (known roles: {_allowed(known)})"
            )
    return tuple(value)


def _parse_capabilities(source: str, where: str, value: Any) -> Capabilities:
    body = _mapping(source, f"{where} capabilities", value)
    _check_keys(source, f"{where} capabilities", body, _CAPABILITY_KEYS, ())
    here = f"{where} capabilities"
    ctx = body.get("max_context_tokens")
    if "max_context_tokens" in body:
        if isinstance(ctx, bool) or not isinstance(ctx, int):
            raise _fail(source, here, "max_context_tokens: must be an integer")
        if ctx < 1:
            raise _fail(source, here, f"max_context_tokens: must be at least 1, got {ctx}")
    return Capabilities(
        tools=_bool(source, here, body, "tools", False),
        streaming=_bool(source, here, body, "streaming", False),
        reasoning=_bool(source, here, body, "reasoning", False),
        max_context_tokens=ctx,
    )


def _parse_model(source: str, where: str, value: Any, provider_name: str) -> CatalogModel:
    body = _mapping(source, where, value)
    _check_keys(source, where, body, _MODEL_KEYS, ("id",))
    model_id = body["id"]
    if not isinstance(model_id, str) or not model_id.strip():
        raise _fail(source, where, "id: must be a non-empty string")
    where = f"{where} {model_id!r}"
    upstream = body.get("upstream", model_id)
    if not isinstance(upstream, str) or not upstream.strip():
        raise _fail(source, where, "upstream: must be a non-empty string")
    return CatalogModel(
        id=model_id,
        upstream=upstream,
        roles=_check_roles(source, where, body["roles"]) if "roles" in body else None,
        capabilities=_parse_capabilities(source, where, body.get("capabilities", {})),
        provider_name=provider_name,
    )


def _parse_provider(source: str, index: int, value: Any) -> Provider:
    where = f"providers[{index}]"
    body = _mapping(source, where, value)
    _check_keys(source, where, body, _PROVIDER_KEYS, _PROVIDER_REQUIRED)
    name = body["name"]
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise _fail(source, where, f"name: must match {_NAME_RE.pattern}")
    where = f"{where} {name!r}"

    label = body.get("label", name)
    if not isinstance(label, str) or not label.strip():
        raise _fail(source, where, "label: must be a non-empty string")
    if body["type"] != "openai_compatible":
        raise _fail(
            source,
            where,
            f"type: {body['type']!r} is not supported; the only type is 'openai_compatible' "
            "(other types arrive with PRD-022)",
        )
    insecure_http = _bool(source, where, body, "insecure_http", False)
    base_url = _check_base_url(source, where, body["base_url"], insecure_http)
    _, _, kind = classify_base_url(base_url)

    key_env = body.get("key_env")
    if "key_env" in body and (not isinstance(key_env, str) or not key_env.strip()):
        raise _fail(source, where, "key_env: must be an environment variable name")

    trust = _choice(source, where, "trust", body.get("trust", "external"), TRUSTS)
    pii = _choice(source, where, "pii", body.get("pii", "standard"), PII_MODES)
    if pii == "relaxed" and trust != "internal":
        raise _fail(source, where, "pii: 'relaxed' requires 'trust: internal' (PRD-020 D7)")
    if trust == "internal" and kind == "public_ip":
        raise _fail(
            source, where, "trust: 'internal' on a public IP address is refused (PRD-020 D7)"
        )

    passthrough = _bool(source, where, body, "passthrough", False)
    byok = _bool(source, where, body, "byok", False)
    if "passthrough_capabilities" in body and not passthrough:
        raise _fail(
            source, where, "passthrough_capabilities: only valid with 'passthrough: true' (F4)"
        )
    pass_caps = _parse_capabilities(
        source, f"{where} passthrough", body.get("passthrough_capabilities", {})
    )

    raw_models = body.get("models")
    if raw_models is None and "models" not in body:
        if not passthrough:
            raise _fail(source, where, "missing key 'models' (required unless 'passthrough: true')")
        raw_models = []
    if not isinstance(raw_models, list):
        raise _fail(source, where, f"models: must be a list, got {type(raw_models).__name__}")
    models = tuple(
        _parse_model(source, f"{where} models[{i}]", m, name) for i, m in enumerate(raw_models)
    )
    if byok and not passthrough and not models:
        raise _fail(source, where, "byok: true with no models and no passthrough is unusable")

    return Provider(
        name=name,
        label=label,
        type="openai_compatible",
        base_url=base_url,
        key_env=key_env.strip() if key_env else None,
        insecure_http=insecure_http,
        trust=trust,
        pii=pii,
        byok=byok,
        passthrough=passthrough,
        passthrough_capabilities=pass_caps,
        usage_missing=_choice(
            source, where, "usage_missing", body.get("usage_missing", "estimate"), USAGE_MISSING
        ),
        estimate_chars_per_token=_number(
            source, where, "estimate_chars_per_token", body.get("estimate_chars_per_token", 4), 0, 8
        ),
        timeout_seconds=_number(
            source,
            where,
            "timeout_seconds",
            body.get("timeout_seconds", settings.OPENROUTER_TIMEOUT_SECONDS),
            0,
            None,
        ),
        roles=_check_roles(source, where, body["roles"]) if "roles" in body else None,
        models=models,
    )


def _check_registry(source: str, default_model: Any, providers: tuple[Provider, ...]) -> Registry:
    """Cross-provider rules: duplicates, one passthrough, a routable default_model."""
    seen: set[str] = set()
    by_id: dict[str, CatalogModel] = {}
    passthrough: Optional[Provider] = None
    for provider in providers:
        if provider.name in seen:
            raise _fail(source, f"provider {provider.name!r}", "duplicate provider name")
        seen.add(provider.name)
        if provider.passthrough:
            if passthrough is not None:
                raise _fail(
                    source,
                    f"provider {provider.name!r}",
                    f"passthrough: only one provider may set it (already {passthrough.name!r})",
                )
            passthrough = provider
        for model in provider.models:
            if model.id in by_id:
                raise _fail(
                    source,
                    f"provider {provider.name!r} model {model.id!r}",
                    f"duplicate model id (already served by {by_id[model.id].provider_name!r})",
                )
            by_id[model.id] = model
    if not isinstance(default_model, str) or not default_model.strip():
        raise _fail(source, "default_model", "must be a non-empty string")
    if default_model not in by_id and passthrough is None:
        raise _fail(
            source,
            "default_model",
            f"{default_model!r} is not catalogued and no provider sets 'passthrough: true'",
        )
    return Registry(
        default_model=default_model,
        providers=providers,
        models_by_id=MappingProxyType(by_id),
        passthrough_provider=passthrough,
        is_legacy=False,
    )


def _parse_document(source: str, document: Any) -> Registry:
    body = _check_version(source, document)
    raw = body["providers"]
    if not isinstance(raw, list) or not raw:
        raise _fail(source, "providers", "must be a non-empty list")
    providers = tuple(_parse_provider(source, i, p) for i, p in enumerate(raw))
    return _check_registry(source, body["default_model"], providers)


# --- Keys and warnings --------------------------------------------------------


def _resolve_keys(source: str, providers: tuple[Provider, ...]) -> dict[str, str]:
    """Resolve each `key_env` to its value. An unset or empty variable names the VARIABLE only."""
    keys: dict[str, str] = {}
    dotenv: Optional[Mapping] = None
    for provider in providers:
        name = provider.key_env
        if not name:
            continue
        if name == "OPENROUTER_API_KEY":
            value = settings.OPENROUTER_API_KEY
        else:
            value = os.environ.get(name)
            if not value:
                if dotenv is None:
                    # The same relative path pydantic reads (`config.py` env_file).
                    dotenv = dotenv_values(".env")
                value = dotenv.get(name)
        if not value:
            raise _fail(
                source,
                f"provider {provider.name!r}",
                f"key_env: environment variable {name!r} is unset or empty",
            )
        keys[provider.name] = value
    return keys


def _warn(providers: tuple[Provider, ...]) -> None:
    """The three F1 WARNINGs: one record per condition per provider, never fatal."""
    secret_globs = action_config.get_policy().secrets.env.compiled
    for provider in providers:
        scheme, host, kind = classify_base_url(provider.base_url)
        if scheme == "http://" and provider.insecure_http:
            logger.warning(
                "provider %r uses plaintext http (insecure_http) to %s%s", provider.name, scheme, host
            )
        if provider.trust == "internal" and kind == "hostname":
            logger.warning(
                "provider %r is trust: internal on hostname %s%s, which cannot be verified",
                provider.name,
                scheme,
                host,
            )
        if provider.key_env and not any(c.search(provider.key_env) for c in secret_globs):
            logger.warning(
                "provider %r key_env %s is not matched by the action policy's secrets.env globs, "
                "so reading it would not be secret.read",
                provider.name,
                provider.key_env,
            )


# --- Legacy registry (PRD-020 Section 6.2, D1) ---------------------------------


def _build_legacy() -> Registry:
    allowlist = settings.model_allowlist_list
    tool_models = settings.v1_tool_models_list
    models: dict[str, CatalogModel] = {}
    for model_id in allowlist:
        # A repeated entry is de-duplicated, first wins.
        models.setdefault(
            model_id,
            CatalogModel(
                id=model_id,
                upstream=model_id,
                roles=None,
                capabilities=Capabilities(tools=(not tool_models) or model_id in tool_models),
                provider_name="openrouter",
            ),
        )
    provider = Provider(
        name="openrouter",
        label="OpenRouter",
        type="openai_compatible",
        base_url=settings.OPENROUTER_BASE_URL,
        key_env="OPENROUTER_API_KEY",
        insecure_http=False,
        trust="external",
        pii="standard",
        byok=True,
        passthrough=True,
        # A set V1_TOOL_MODELS binds admin too (`config.py` v1 tool rule).
        passthrough_capabilities=Capabilities(tools=not tool_models),
        usage_missing="error",
        estimate_chars_per_token=4.0,
        timeout_seconds=settings.OPENROUTER_TIMEOUT_SECONDS,
        roles=None,
        models=tuple(models.values()),
    )
    return Registry(
        default_model="gpt-4",
        providers=(provider,),
        models_by_id=MappingProxyType(models),
        passthrough_provider=provider,
        is_legacy=True,
    )


# --- State and public API -----------------------------------------------------

#: File mode only. Legacy mode has no snapshot: `current()` derives it live.
_snapshot: Optional[Registry] = None
_keys: dict[str, str] = {}
#: Single-slot memo of the legacy registry, keyed by the settings it came from.
_legacy_memo: Optional[tuple[tuple, Registry]] = None


def load() -> None:
    """Read `PROVIDERS_FILE` and put its registry in force, or fall back to legacy mode, or fail startup.

    An empty `PROVIDERS_FILE` reads no file: legacy mode (`current()` derives the
    implicit provider from live settings). Otherwise every check passes, the
    keys resolve and the WARNINGs log before anything is rebound --
    `_snapshot`/`_keys` are assigned last, so a failing file leaves the previous
    state intact and logs no warning (`action_config.load()`'s shape).

    `strict_yaml.safe_load` only (a key written twice is an error). A set
    `V1_TOOL_MODELS` together with a file is already a Settings startup error
    (`config.py`), so it is not repeated here.
    """
    global _snapshot, _keys

    path = settings.PROVIDERS_FILE
    if not path:
        _snapshot, _keys = None, {}
        return

    source = f"PROVIDERS_FILE '{path}'"
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(source, "file", f"cannot be read: {exc}") from exc
    try:
        document = strict_yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise _fail(source, "file", f"is not valid YAML: {exc}") from exc

    registry = _parse_document(source, document)
    keys = _resolve_keys(source, registry.providers)
    _warn(registry.providers)
    _snapshot, _keys = registry, keys


def current() -> Registry:
    """The snapshot in file mode; otherwise the legacy registry for the settings as they are now."""
    global _legacy_memo
    if _snapshot is not None:
        return _snapshot
    signature = (
        settings.MODEL_ALLOWLIST,
        settings.V1_TOOL_MODELS,
        settings.OPENROUTER_BASE_URL,
        settings.OPENROUTER_TIMEOUT_SECONDS,
    )
    if _legacy_memo is None or _legacy_memo[0] != signature:
        _legacy_memo = (signature, _build_legacy())
    return _legacy_memo[1]


def api_key_for(provider: Provider) -> Optional[str]:
    """The provider's key, or None when it is keyless. Legacy reads the setting at call time."""
    if _snapshot is None:
        return settings.OPENROUTER_API_KEY or None
    return _keys.get(provider.name)


def reset() -> None:
    """Back to legacy mode and forget keys and the memo. Reads no setting."""
    global _snapshot, _keys, _legacy_memo
    _snapshot, _keys, _legacy_memo = None, {}, None
