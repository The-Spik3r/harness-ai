import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import re
from pathlib import Path

from app.config import Settings, settings

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- AC1: new fields are available with the documented defaults ---


def test_rbac_settings_available_with_documented_defaults():
    assert settings.RBAC_ENABLED is True
    assert settings.RBAC_DEFAULT_ROLE == "user"
    assert settings.RBAC_ROLES_FILE == ""
    assert isinstance(settings.MODEL_ALLOWLIST, str)
    assert settings.MODEL_ALLOWLIST != ""


# --- AC2: model_allowlist_list parses exactly like pii_entities_list ---


def test_model_allowlist_list_parses_like_pii_entities_list(monkeypatch):
    monkeypatch.setattr(settings, "MODEL_ALLOWLIST", " gpt-4 , ,claude-3-sonnet ,")

    assert settings.model_allowlist_list == ["gpt-4", "claude-3-sonnet"]


def test_model_allowlist_list_default_matches_prd_default_models():
    assert settings.model_allowlist_list == [
        "gpt-4",
        "claude-3-sonnet",
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
    ]


# --- AC3: none of the new vars set -- defaults apply, nothing raises ---


def test_settings_construct_without_new_env_vars(monkeypatch):
    for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
        monkeypatch.delenv(var, raising=False)

    fresh = Settings(_env_file=None)

    assert fresh.RBAC_ENABLED is True
    assert fresh.RBAC_DEFAULT_ROLE == "user"
    assert fresh.RBAC_ROLES_FILE == ""
    assert fresh.model_allowlist_list  # non-empty


# --- AC4: .env.example documents every new variable, Settings field for field ---


def test_env_example_documents_every_new_rbac_var_with_a_comment():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for var in ("RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"):
        assert re.search(rf"(?m)^#.+\n{var}=", text), f"{var} missing from .env.example or missing its comment line"


def test_env_example_rbac_vars_appear_in_settings_field_order():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    declared_order = ["RBAC_ENABLED", "RBAC_DEFAULT_ROLE", "RBAC_ROLES_FILE", "MODEL_ALLOWLIST"]

    positions = [text.index(f"{var}=") for var in declared_order]

    assert positions == sorted(positions)
