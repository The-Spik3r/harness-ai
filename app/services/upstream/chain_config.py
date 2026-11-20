"""Fallback chains: the file, its startup validation and the lookup (PRD-022 6.3, F3, 9.3, D5, D6, T1).

`PROVIDER_CHAINS_FILE` names a YAML of ordered candidates per `(model, ingress)`.
`validate_chains` is pure: it turns a parsed document, a `Registry` and a
`ChainLimits` into an immutable `ChainSnapshot` and the WARNING texts, reading
no settings, no env and no file, and logging nothing. `load()` is the only I/O
(it reads the setting and the file, builds `ChainLimits`, logs the warnings and
rebinds the snapshot last, `provider_registry.load()`'s shape).

Every per-entry check compares the candidate with the PRIMARY (`candidates[0]`),
never the previous entry (PRD-022 F3, T1): a chain `[internal A, internal B,
external C]` cannot launder C through B. Trust (D6) and capability are refused
at startup unless the entry opts in (`allow_lower_trust`, `capability_scoped`).
The same rules run per request in STORY-011/012; this module is the startup half.

Called once at startup in both lifespans, right after `provider_registry.load()`
(the chat UI bypasses `app.main`'s lifespan, PRD-016 6.12). With no file,
`chain_for` returns the single-candidate chain of PRD-020/021 (PRD-022 Mission).
Errors carry ids, provider names and the rule, never a key, URL or value (T1).
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional

import yaml

from app.config import settings
from app.services import provider_registry, strict_yaml
from app.services.provider_registry import Registry

logger = logging.getLogger(__name__)


class ChainConfigError(ValueError):
    """`PROVIDER_CHAINS_FILE` cannot be put in force; the boot stops (PRD-022 F3)."""


# --- Vocabulary (closed) ------------------------------------------------------

# Copied from `query_pipeline.Ingress` (this module stays import-light).
INGRESSES = ("query", "chat", "v1")
# The four F3 capabilities, in the order they are checked.
_CAPABILITIES = ("tools", "streaming", "reasoning", "forced_tool_choice")

_TOP_KEYS = ("version", "chains")
_CHAIN_KEYS = ("match", "candidates")
_MATCH_KEYS = ("model", "ingress")
_ENTRY_KEYS = ("model", "allow_lower_trust", "capability_scoped")


# --- Model (frozen; tuples only) ----------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One entry of a chain. Flags are meaningful for index >= 1 only."""

    model_id: str
    allow_lower_trust: bool = False
    capability_scoped: bool = False


@dataclass(frozen=True)
class Chain:
    """Ordered candidates for one `(model, ingress)`; `candidates[0].model_id == model`."""

    model: str
    ingress: Optional[str]
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class ChainLimits:
    """The settings validation needs, passed in so the validator reads none (PRD-022 9.3)."""

    max_candidates: int
    deadline_seconds: Optional[float]
    min_attempt_seconds: float


def _single(model: str, ingress: Optional[str] = None) -> Chain:
    return Chain(model, ingress, (Candidate(model),))


@dataclass(frozen=True)
class ChainSnapshot:
    """Every configured chain, keyed `(model, ingress)`; `ingress` None matches any ingress."""

    chains: Mapping[tuple[str, Optional[str]], Chain]

    def chain_for(self, model: str, ingress: Optional[str]) -> Chain:
        """Exact `(model, ingress)`, then `(model, None)`, then the single-candidate chain."""
        found = self.chains.get((model, ingress))
        if found is None:
            found = self.chains.get((model, None))
        return found if found is not None else _single(model)


# --- Errors (provider_registry's shape, copied small) -------------------------


def _fail(source: str, *parts: str) -> ChainConfigError:
    return ChainConfigError(f"{source}: " + ": ".join(parts))


def _allowed(values) -> str:
    return ", ".join(sorted(values))


def _mapping(source: str, node: str, value: Any) -> Mapping:
    if not isinstance(value, Mapping):
        raise _fail(source, node, f"must be a mapping, got {type(value).__name__}")
    return value


def _list(source: str, node: str, value: Any) -> list:
    if not isinstance(value, list) or not value:
        raise _fail(source, node, "must be a non-empty list")
    return value


def _check_keys(source: str, where: str, body: Mapping, allowed, required) -> None:
    unknown = sorted(set(body) - set(allowed), key=str)
    if unknown:
        raise _fail(
            source, where, f"unknown key {unknown[0]!r} (expected one of: {_allowed(allowed)})"
        )
    missing = [key for key in required if key not in body]
    if missing:
        raise _fail(source, where, f"missing key {missing[0]!r} (required: {_allowed(required)})")


def _bool(source: str, where: str, body: Mapping, key: str) -> bool:
    value = body.get(key, False)
    if not isinstance(value, bool):
        raise _fail(source, where, f"{key}: must be true or false, got {type(value).__name__}")
    return value


def _chain_label(model: str, ingress: Optional[str]) -> str:
    return f"chain '{model}'" + (f" ingress {ingress}" if ingress else "")


def _entry_label(chain_label: str, index: int, model_id: str, provider: str) -> str:
    return f"{chain_label} entry {index} ({model_id}, provider {provider})"


# --- Validation (pure) --------------------------------------------------------


def _parse_entry(source: str, label: str, index: int, raw: Any) -> Candidate:
    where = f"{label} entry {index}"
    body = _mapping(source, where, raw)
    _check_keys(source, where, body, _ENTRY_KEYS, ("model",))
    model = body["model"]
    if not isinstance(model, str) or not model.strip():
        raise _fail(source, where, "model: must be a non-empty string")
    return Candidate(
        model,
        _bool(source, where, body, "allow_lower_trust"),
        _bool(source, where, body, "capability_scoped"),
    )


def _check_entry(
    source: str,
    registry: Registry,
    providers: Mapping[str, Any],
    label: str,
    index: int,
    candidate: Candidate,
    primary,
    seen: set,
) -> Optional[str]:
    """One entry against the primary (F3). Returns the WARNING text for a crossing opt-in."""
    entry = registry.models_by_id.get(candidate.model_id)
    provider_name = entry.provider_name if entry is not None else "?"
    where = _entry_label(label, index, candidate.model_id, provider_name)
    if entry is None:
        raise _fail(
            source,
            where,
            "is not catalogued in PROVIDERS_FILE (a chain cannot route to an id the "
            "operator never listed)",
        )
    if candidate.model_id in seen:
        raise _fail(source, where, "repeats a model id already in this chain")
    seen.add(candidate.model_id)
    if index == 1:
        if candidate.allow_lower_trust or candidate.capability_scoped:
            raise _fail(
                source,
                where,
                "the primary (entry 1) cannot set allow_lower_trust or capability_scoped: "
                "it has nothing to be compared with",
            )
        return None

    primary_provider = providers[primary.provider_name]
    provider = providers[entry.provider_name]
    crossing = primary_provider.trust == "internal" and provider.trust == "external"
    if crossing and not candidate.allow_lower_trust:
        raise _fail(
            source,
            where,
            f"trust {provider.trust} is lower than the primary's trust {primary_provider.trust}; "
            "set allow_lower_trust: true on this entry to permit it (PRD-020 6.8 rule 1)",
        )
    if not candidate.capability_scoped:
        for name in _CAPABILITIES:
            if getattr(primary.capabilities, name) and not getattr(entry.capabilities, name):
                raise _fail(
                    source,
                    where,
                    f"lacks capability {name} that the primary has; set capability_scoped: "
                    "true on this entry to permit it (PRD-022 F3)",
                )
    if crossing:
        return (
            f"{source}: {where}: internal -> external fallback is allowed by allow_lower_trust"
        )
    return None


def validate_chains(
    source: str, document: Any, registry: Registry, limits: ChainLimits
) -> tuple[ChainSnapshot, tuple[str, ...]]:
    """Every F3 rule, first failure raised. Returns the snapshot and the WARNING texts. Pure."""
    body = _mapping(source, "file", document)
    _check_keys(source, "file", body, _TOP_KEYS, _TOP_KEYS)
    version = body["version"]
    if isinstance(version, bool) or version != 1:
        raise _fail(source, "version", "must be 1")
    raw_chains = _list(source, "chains", body["chains"])

    providers = {p.name: p for p in registry.providers}
    chains: dict[tuple[str, Optional[str]], Chain] = {}
    warnings: list[str] = []
    for number, raw in enumerate(raw_chains, start=1):
        node = f"chains[{number}]"
        item = _mapping(source, node, raw)
        _check_keys(source, node, item, _CHAIN_KEYS, _CHAIN_KEYS)
        match = _mapping(source, f"{node} match", item["match"])
        _check_keys(source, f"{node} match", match, _MATCH_KEYS, ("model",))
        model = match["model"]
        if not isinstance(model, str) or not model.strip():
            raise _fail(source, f"{node} match", "model: must be a non-empty string")
        ingress = match.get("ingress")
        if ingress is not None and ingress not in INGRESSES:
            raise _fail(
                source,
                _chain_label(model, None),
                f"match ingress {ingress!r} is not one of: {_allowed(INGRESSES)}",
            )
        label = _chain_label(model, ingress)
        raw_entries = _list(source, f"{label} candidates", item["candidates"])
        candidates = tuple(
            _parse_entry(source, label, i, entry) for i, entry in enumerate(raw_entries, start=1)
        )
        key = (model, ingress)
        if key in chains:
            raise _fail(source, label, "is configured twice (same match model and ingress)")
        if candidates[0].model_id != model:
            raise _fail(
                source,
                label,
                f"the first candidate must be the match model, got {candidates[0].model_id!r}",
            )
        if len(candidates) > limits.max_candidates:
            raise _fail(
                source,
                label,
                f"has {len(candidates)} candidates, more than "
                f"PROVIDER_CHAIN_MAX_CANDIDATES ({limits.max_candidates})",
            )

        primary = registry.models_by_id.get(model)
        seen: set = set()
        for index, candidate in enumerate(candidates, start=1):
            # Entry 1 is checked first and raises when the primary is uncatalogued,
            # so `primary` is set for every later entry and for the deadline below.
            warning = _check_entry(
                source, registry, providers, label, index, candidate, primary, seen
            )
            if warning:
                warnings.append(warning)

        effective = limits.deadline_seconds
        if effective is None:
            effective = providers[primary.provider_name].timeout_seconds
        if limits.min_attempt_seconds >= effective:
            raise _fail(
                source,
                label,
                f"PROVIDER_MIN_ATTEMPT_SECONDS ({limits.min_attempt_seconds:g}) must be less "
                f"than the chain deadline ({effective:g}s): no fallback could ever start",
            )
        chains[key] = Chain(model, ingress, candidates)

    return ChainSnapshot(MappingProxyType(chains)), tuple(warnings)


# --- State and public API (the only I/O) --------------------------------------

_snapshot: Optional[ChainSnapshot] = None


def load() -> None:
    """Read `PROVIDER_CHAINS_FILE` into force, or no chains, or fail startup.

    Empty setting: no file is read and `chain_for` answers the single-candidate
    chain. Otherwise validate, log each WARNING once, and rebind `_snapshot`
    last, so a failing file leaves the previous state and logs nothing. Reads
    `provider_registry.current()` at call time: call it after
    `provider_registry.load()`.
    """
    global _snapshot

    path = settings.PROVIDER_CHAINS_FILE
    if not path:
        _snapshot = None
        return

    source = f"PROVIDER_CHAINS_FILE '{path}'"
    registry = provider_registry.current()
    if not settings.PROVIDERS_FILE or registry.is_legacy:
        raise _fail(
            source,
            "file",
            "needs PROVIDERS_FILE: chains resolve model ids through the registry (PRD-022 D5)",
        )
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(source, "file", f"cannot be read: {exc}") from exc
    try:
        document = strict_yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise _fail(source, "file", f"is not valid YAML: {exc}") from exc

    limits = ChainLimits(
        settings.PROVIDER_CHAIN_MAX_CANDIDATES,
        settings.PROVIDER_CHAIN_DEADLINE_SECONDS,
        settings.PROVIDER_MIN_ATTEMPT_SECONDS,
    )
    snapshot, warnings = validate_chains(source, document, registry, limits)
    for text in warnings:
        logger.warning(text)
    _snapshot = snapshot


def reset() -> None:
    """No chains. Reads no setting."""
    global _snapshot
    _snapshot = None


def current() -> Optional[ChainSnapshot]:
    return _snapshot


def chain_for(model: str, ingress: Optional[str]) -> Chain:
    """The chain for a request: the loaded snapshot's, else the single-candidate chain. Never None."""
    if _snapshot is None:
        return _single(model)
    return _snapshot.chain_for(model, ingress)
