"""STORY-015 (PRD-020) -- the providers documentation is checked by parsing it.

A renamed setting, a recipe that no longer loads or a deleted warning must fail
the suite, so nothing here compares against a hand-copied list. The setting
names are read out of `docs/configuration.md` and `.env.example` and looked up
in `Settings.model_fields`; every fenced `yaml` block under the `### Providers`
heading of `docs/features.md` is loaded through the real registry loader
(`tests/_providers.py`), which is the only validator; and `examples/providers.yaml`
must load with exactly the one warning its LAN provider is meant to raise.

The content assertions are substance, not sentences (the rule of
`tests/test_admin_copy.py`): a required substring, never a whole paragraph.
"""

import logging
import re
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.services import provider_registry
from tests._providers import providers_file

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / "docs" / "features.md"
CONFIGURATION = ROOT / "docs" / "configuration.md"
ENV_EXAMPLE = ROOT / ".env.example"
README = ROOT / "README.md"
EXAMPLE = ROOT / "examples" / "providers.yaml"

_RECIPES = ["Ollama", "vLLM", "LM Studio", "llama.cpp server", "LocalAI", "Hosted OpenAI-compatible cloud"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, heading: str) -> str:
    """Text from `### {heading}` to the next `### ` heading; the heading must exist."""
    text = _read(path)
    match = re.search(rf"^### {re.escape(heading)}\s*$", text, re.MULTILINE)
    assert match, f"{path.name} has no '### {heading}' heading"
    rest = text[match.end():]
    nxt = re.search(r"^### ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _yaml_blocks(text: str):
    return re.findall(r"^```yaml\s*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


def _key_envs(block: str):
    data = yaml.safe_load(block)
    return [p["key_env"] for p in data.get("providers", []) if p.get("key_env")]


def _documented_settings():
    names = set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", _read(CONFIGURATION), re.MULTILINE))
    names |= set(re.findall(r"^([A-Z][A-Z0-9_]+)=", _read(ENV_EXAMPLE), re.MULTILINE))
    return names


def _row(name: str) -> str:
    rows = [ln for ln in _read(CONFIGURATION).splitlines() if ln.startswith(f"| `{name}` |")]
    assert len(rows) == 1, f"docs/configuration.md needs exactly one row for {name}"
    return rows[0]


# Documented in the table but deliberately not harness settings: the balancer's compose file
# reads the first (PRD-019), and the second is a Reflex variable (PRD-019 Section 6.2).
_NOT_SETTINGS = {"LB_COOKIE_SECRET", "REFLEX_REDIS_URL"}


def test_documented_settings_exist_in_config():
    names = _documented_settings() - _NOT_SETTINGS
    assert names and "PROVIDERS_FILE" in names
    missing = sorted(n for n in names if n not in Settings.model_fields)
    assert not missing, f"documented but not in Settings: {missing}"


def test_every_recipe_block_loads_through_the_registry(tmp_path, monkeypatch):
    blocks = _yaml_blocks(_section(FEATURES, "Providers"))
    assert len(blocks) >= 6, "the Providers section needs one yaml recipe per server"
    for block in blocks:
        env = {name: "dummy-not-a-key" for name in _key_envs(block)}
        with providers_file(tmp_path, block, monkeypatch=monkeypatch, env=env) as reg:
            assert not reg.is_legacy and reg.providers


def test_example_registry_loads_with_only_the_insecure_http_warning(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger=provider_registry.logger.name)
    env = {"OPENROUTER_API_KEY": "dummy-not-a-key", "VLLM_API_KEY": "dummy-not-a-key"}
    with providers_file(tmp_path, _read(EXAMPLE), monkeypatch=monkeypatch, env=env) as reg:
        assert {p.name for p in reg.providers} == {"openrouter", "ollama", "gpu-box"}
        assert reg.default_model == "openai/gpt-4o"
        assert reg.models_by_id["lan/llama-3.1-70b"].roles == ("admin",)
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name == provider_registry.logger.name and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1, warnings
    assert "192.168.1.40" in warnings[0] and "insecure_http" in warnings[0]


def test_configuration_rows_state_file_mode():
    row = _row("PROVIDERS_FILE")
    assert "features.md#providers" in row and "restart" in row
    assert "unless `PROVIDERS_FILE` is set" in _row("OPENROUTER_API_KEY")
    for name in ("OPENROUTER_BASE_URL", "MODEL_ALLOWLIST", "V1_TOOL_MODELS"):
        assert "file mode" in _row(name), name
    assert "file mode" in _row("OPENROUTER_TIMEOUT_SECONDS")


def test_providers_section_has_recipes_and_warnings():
    text = _section(FEATURES, "Providers")
    for recipe in _RECIPES:
        assert re.search(rf"^#### {re.escape(recipe)}\s*$", text, re.MULTILINE), recipe
    lowered = text.lower()
    assert "receives that provider's key and every prompt" in text
    assert "plaintext" in lowered and "unencrypted" in lowered
    assert "trust: internal" in text and "pii: relaxed" in text
    # The one verified server's quirk is stated, and the others are said not to be verified.
    assert "object form of `tool_choice`" in text and "502" in text
    assert text.count("Not verified by this repo's E2E") >= 5


def test_env_example_and_readme_point_at_providers():
    lines = _read(ENV_EXAMPLE).splitlines()
    index = lines.index("PROVIDERS_FILE=")
    above = []
    for ln in reversed(lines[:index]):
        if not ln.startswith("#"):
            break
        above.append(ln)
    assert len(above) >= 3, "PROVIDERS_FILE= needs a comment block of at least three lines"
    assert "docs/features.md#providers" in _read(README)
