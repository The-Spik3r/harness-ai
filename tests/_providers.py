"""File-mode registry fixture for PRD-020 tests (OD2, STORY-003).

`providers_file(...)` writes a registry YAML under `tmp_path`, points
`settings.PROVIDERS_FILE` at it, loads it and yields `current()`. On exit --
also when `load()` raised -- it calls `provider_registry.reset()`, so a test
never leaves a file-mode registry loaded for the next one. `monkeypatch` undoes
the settings afterwards; `reset()` reads no setting, so the order is safe.

Stories 004-014 build their file-mode tests on this module.
"""

import contextlib
from pathlib import Path

import pytest

from app.config import settings
from app.services import provider_registry


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
    provider_registry.reset()
