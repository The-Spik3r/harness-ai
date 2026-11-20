"""File-mode registry fixture for PRD-020 tests (OD2, STORY-003).

`providers_file(...)` writes a registry YAML under `tmp_path`, points
`settings.PROVIDERS_FILE` at it, loads it and yields `current()`. On exit --
also when `load()` raised -- it calls `provider_registry.reset()`, so a test
never leaves a file-mode registry loaded for the next one. `monkeypatch` undoes
the settings afterwards; `reset()` reads no setting, so the order is safe.

`chains_file` (PRD-022 STORY-009) loads a chains document on top of it.

Stories 004-014 build their file-mode tests on this module.
"""

import contextlib
from pathlib import Path

import pytest

from app.config import settings
from app.services import provider_registry
from app.services.upstream import chain_config


def write_registry(tmp_path: Path, text: str) -> str:
    """Write `text` as `tmp_path/providers.yaml` and return its path as a string."""
    path = Path(tmp_path) / "providers.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


@contextlib.contextmanager
def providers_file(tmp_path, yaml_text: str, *, monkeypatch, env=None):
    """Load `yaml_text` as PROVIDERS_FILE; yield the Registry; restore legacy mode on exit.

    `env` is a mapping of environment variables set for the run (the registry's
    `key_env` values). `V1_TOOL_MODELS` is forced empty: a set list with a file
    is a Settings startup error (PRD-020 D6), and a test that patches it after
    construction would bypass that check.
    """
    path = write_registry(tmp_path, yaml_text)
    monkeypatch.setattr(settings, "PROVIDERS_FILE", path)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    try:
        provider_registry.load()
        yield provider_registry.current()
    finally:
        chain_config.reset()  # PRD-022 STORY-009: chains resolve against the registry
        provider_registry.reset()


@pytest.fixture
def provider_file(tmp_path, monkeypatch):
    """Callable fixture: `provider_file(yaml_text, env=None) -> Registry`, reset on teardown."""

    def _load(yaml_text: str, env=None):
        path = write_registry(tmp_path, yaml_text)
        monkeypatch.setattr(settings, "PROVIDERS_FILE", path)
        monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")
        for name, value in (env or {}).items():
            monkeypatch.setenv(name, value)
        provider_registry.load()
        return provider_registry.current()

    yield _load
    chain_config.reset()  # PRD-022 STORY-009
    provider_registry.reset()


def write_chains(tmp_path: Path, text: str) -> str:
    """Write `text` as `tmp_path/chains.yaml` and return its path as a string."""
    path = Path(tmp_path) / "chains.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


@pytest.fixture
def chains_file(tmp_path, monkeypatch):
    """Callable fixture (PRD-022 STORY-009): `chains_file(yaml_text) -> ChainSnapshot | None`.

    Writes `chains.yaml`, sets `PROVIDER_CHAINS_FILE`, runs `chain_config.load()` (call it
    after `provider_file(...)`; a raise propagates) and resets on teardown.
    """

    def _load(yaml_text: str):
        monkeypatch.setattr(settings, "PROVIDER_CHAINS_FILE", write_chains(tmp_path, yaml_text))
        chain_config.load()
        return chain_config.current()

    yield _load
    chain_config.reset()
