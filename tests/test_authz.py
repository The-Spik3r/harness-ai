import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
from pathlib import Path

import pytest

import app.services.authz as authz
from app.config import settings
from app.services.authz import (
    ACTION_PERMISSIONS,
    AuthzConfigError,
    MODEL_ALLOWLIST_WILDCARD_ROLES,
    PERMISSION_ACTION_FS_WRITE,
    PERMISSION_ACTION_NET_EGRESS,
    PERMISSION_ACTION_SECRET_READ,
    PERMISSION_ACTION_SHELL_EXEC,
    PERMISSION_ACTION_SQL_DDL,
    PERMISSION_ACTION_SQL_WRITE,
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_QUERY_BYOK,
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_REASONING_VIEW,
    PERMISSION_STATS_READ,
    PERMISSION_STREAM_REALTIME,
    PermissionDenied,
    ROLE_PERMISSIONS,
    STREAM_PERMISSIONS,
    authorize,
    authorize_model,
    holds,
    load,
)
from app.services.identity import Identity

ALL_PERMISSIONS = [
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_QUERY_BYOK,
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_STATS_READ,
]

_MATRIX_CASES = [
    (role, permission, permission in ROLE_PERMISSIONS[role])
    for role in ("admin", "auditor", "user")
    for permission in ALL_PERMISSIONS
]


# --- AC1: full matrix, grant + deny, every cell ---


@pytest.mark.parametrize("role, permission, expected_allowed", _MATRIX_CASES)
def test_matrix_cell_matches_prd_section_7(role, permission, expected_allowed):
    identity = Identity(user_id="u", role=role)

    if expected_allowed:
        assert authorize(identity, permission) is None
    else:
        with pytest.raises(PermissionDenied) as exc_info:
            authorize(identity, permission)
        assert exc_info.value.permission == permission


def test_admin_matrix_matches_prd_exactly():
    assert ROLE_PERMISSIONS["admin"] == set(ALL_PERMISSIONS)


def test_auditor_matrix_matches_prd_exactly():
    assert ROLE_PERMISSIONS["auditor"] == {
        PERMISSION_AUDIT_READ_ALL,
        PERMISSION_AUDIT_READ_OWN,
        PERMISSION_STATS_READ,
    }


def test_user_matrix_matches_prd_exactly():
    assert ROLE_PERMISSIONS["user"] == {
        PERMISSION_QUERY_SUBMIT,
        PERMISSION_AUDIT_READ_OWN,
    }


# --- AC2: unknown role denies, never a fallback grant ---


def test_unknown_role_raises_permission_denied():
    identity = Identity(user_id="u", role="superadmin")

    with pytest.raises(PermissionDenied):
        authorize(identity, PERMISSION_QUERY_SUBMIT)


# --- AC3: permission absent from role's grants raises carrying the permission name ---


def test_denied_permission_carries_the_permission_name():
    identity = Identity(user_id="u", role="user")

    with pytest.raises(PermissionDenied) as exc_info:
        authorize(identity, PERMISSION_QUERY_BYOK)

    assert exc_info.value.permission == PERMISSION_QUERY_BYOK


# --- AC4: granted permission returns None, raises nothing ---


def test_granted_permission_returns_none():
    identity = Identity(user_id="u", role="admin")

    assert authorize(identity, PERMISSION_STATS_READ) is None


# --- AC5: RBAC_ENABLED=false is a single explicit bypass branch, with its own test ---


def test_rbac_disabled_allows_even_an_unknown_role(monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    identity = Identity(user_id="u", role="superadmin")

    assert authorize(identity, PERMISSION_QUERY_BYOK) is None


# --- STORY-007: load() from RBAC_ROLES_FILE ---


@pytest.fixture
def _reset_role_permissions():
    original = authz.ROLE_PERMISSIONS
    yield
    authz.ROLE_PERMISSIONS = original


def test_load_is_noop_when_roles_file_unset(monkeypatch, _reset_role_permissions):
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", "")
    before = authz.ROLE_PERMISSIONS

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("read_text should not be called when RBAC_ROLES_FILE is empty")

    monkeypatch.setattr(Path, "read_text", _fail_if_called)

    load()

    assert authz.ROLE_PERMISSIONS is before  # same object -- never rebuilt


def test_load_replaces_matrix_wholesale_from_valid_file(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

    load()

    assert authz.ROLE_PERMISSIONS == {"user": {PERMISSION_QUERY_SUBMIT}}

    identity = Identity(user_id="u", role="user")
    assert authorize(identity, PERMISSION_QUERY_SUBMIT) is None
    # PERMISSION_AUDIT_READ_OWN was in the built-in "user" grants and is
    # omitted here -- omission is denial, not inherited from the default.
    with pytest.raises(PermissionDenied):
        authorize(identity, PERMISSION_AUDIT_READ_OWN)
    # "admin" was in the built-in matrix and is entirely absent from the
    # file -- also gone, proving replace rather than a per-role merge.
    with pytest.raises(PermissionDenied):
        authorize(Identity(user_id="a", role="admin"), PERMISSION_STATS_READ)


def test_load_raises_on_malformed_json(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text("{not valid json")
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    before = dict(authz.ROLE_PERMISSIONS)

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert str(roles_file) in str(exc_info.value)
    assert authz.ROLE_PERMISSIONS == before  # no silent fallback mutation


def test_load_raises_on_missing_file(tmp_path, monkeypatch, _reset_role_permissions):
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(missing))

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert str(missing) in str(exc_info.value)


def test_load_raises_on_unrecognized_permission(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT, "query:launch-nukes"]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert "query:launch-nukes" in str(exc_info.value)


def test_authorize_does_not_read_file_per_call(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"user": [PERMISSION_QUERY_SUBMIT]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    load()

    read_calls = []
    original_read_text = Path.read_text

    def _counting_read_text(self, *args, **kwargs):
        read_calls.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    for _ in range(3):
        authorize(Identity(user_id="u", role="user"), PERMISSION_QUERY_SUBMIT)

    assert read_calls == []


# --- STORY-011: authorize_model() ---


def test_admin_model_wildcard_allows_any_model():
    identity = Identity(user_id="root", role="admin")
    assert "admin" in MODEL_ALLOWLIST_WILDCARD_ROLES

    assert authorize_model(identity, "some-totally-unlisted-model") is None


def test_user_role_allows_models_in_allowlist():
    identity = Identity(user_id="u", role="user")

    for model in settings.model_allowlist_list:
        assert authorize_model(identity, model) is None


def test_user_role_denies_model_outside_allowlist():
    identity = Identity(user_id="u", role="user")

    with pytest.raises(PermissionDenied) as exc_info:
        authorize_model(identity, "not-a-real-model")

    assert exc_info.value.permission == "query:model:not-a-real-model"


def test_rbac_disabled_bypasses_model_check(monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    identity = Identity(user_id="u", role="user")

    assert authorize_model(identity, "not-a-real-model") is None


# --- PRD-016 STORY-003: action permissions and holds() ---

# Transcribed from PRD-016 Section 6.7, literal on purpose: the test checks
# the values, not only that six names exist.
_ACTION_PERMISSION_VALUES = (
    "action:sql:write",
    "action:sql:ddl",
    "action:shell:exec",
    "action:fs:write",
    "action:net:egress",
    "action:secret:read",
)


def test_action_permission_constants_match_prd_016_section_6_7():
    assert PERMISSION_ACTION_SQL_WRITE == "action:sql:write"
    assert PERMISSION_ACTION_SQL_DDL == "action:sql:ddl"
    assert PERMISSION_ACTION_SHELL_EXEC == "action:shell:exec"
    assert PERMISSION_ACTION_FS_WRITE == "action:fs:write"
    assert PERMISSION_ACTION_NET_EGRESS == "action:net:egress"
    assert PERMISSION_ACTION_SECRET_READ == "action:secret:read"
    assert isinstance(ACTION_PERMISSIONS, frozenset)
    assert ACTION_PERMISSIONS == frozenset(_ACTION_PERMISSION_VALUES)


def test_known_permissions_are_the_original_five_plus_the_six():
    """PRD-016 F9: the six join the known set, so RBAC_ROLES_FILE can grant
    them through load()'s existing unknown-permission check."""
    # PRD-021 D1: the two stream permissions also join the known set (13 in all).
    assert authz._KNOWN_PERMISSIONS == set(ALL_PERMISSIONS) | ACTION_PERMISSIONS | STREAM_PERMISSIONS
    assert len(authz._KNOWN_PERMISSIONS) == 13


@pytest.mark.parametrize("role", ["admin", "auditor", "user"])
def test_no_built_in_role_holds_an_action_permission(role):
    """PRD-016 D6: no built-in role holds an action permission, admin included."""
    assert ROLE_PERMISSIONS[role].isdisjoint(ACTION_PERMISSIONS)


def test_built_in_roles_are_exactly_the_three_parametrized():
    # Guards the parametrization above: a new built-in role cannot slip past it.
    assert set(ROLE_PERMISSIONS) == {"admin", "auditor", "user"}


def test_load_accepts_an_action_permission_grant(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"dba": ["query:submit", "action:sql:write"]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

    load()

    assert authz.ROLE_PERMISSIONS == {"dba": {PERMISSION_QUERY_SUBMIT, PERMISSION_ACTION_SQL_WRITE}}
    assert holds(Identity(user_id="d", role="dba"), PERMISSION_ACTION_SQL_WRITE) is True


def test_load_refuses_a_misspelled_action_permission(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"dba": ["action:sql:writ"]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    before = dict(authz.ROLE_PERMISSIONS)

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert "action:sql:writ" in str(exc_info.value)
    assert str(roles_file) in str(exc_info.value)
    assert authz.ROLE_PERMISSIONS == before


@pytest.mark.parametrize("rbac_enabled", [False, True])
@pytest.mark.parametrize("role", ["user", "admin"])
@pytest.mark.parametrize("permission", sorted(_ACTION_PERMISSION_VALUES))
def test_holds_is_false_for_a_role_without_the_permission(monkeypatch, rbac_enabled, role, permission):
    """PRD-016 D7, T4: no bypass, with RBAC off as with RBAC on."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", rbac_enabled)

    assert holds(Identity(user_id="u", role=role), permission) is False


@pytest.mark.parametrize("rbac_enabled", [False, True])
def test_holds_is_true_for_a_role_with_the_permission(monkeypatch, rbac_enabled):
    monkeypatch.setattr(settings, "RBAC_ENABLED", rbac_enabled)
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"dba": {PERMISSION_ACTION_SQL_WRITE}})
    identity = Identity(user_id="d", role="dba")

    assert holds(identity, "action:sql:write") is True
    assert holds(identity, "action:sql:ddl") is False


@pytest.mark.parametrize("rbac_enabled", [False, True])
def test_holds_is_false_for_a_role_absent_from_the_matrix(monkeypatch, rbac_enabled):
    monkeypatch.setattr(settings, "RBAC_ENABLED", rbac_enabled)

    assert holds(Identity(user_id="u", role="superadmin"), "action:sql:write") is False


def test_holds_does_not_inherit_authorize_rbac_off_bypass(monkeypatch):
    """PRD-016 D7, Section 6.7: with RBAC_ENABLED=false, authorize() still
    returns (PRD-005's escape hatch, unchanged) while holds() says False --
    the hatch never grants an action permission."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    identity = Identity(user_id="u", role="user")

    assert authorize(identity, PERMISSION_ACTION_SQL_WRITE) is None
    assert holds(identity, PERMISSION_ACTION_SQL_WRITE) is False


def test_holds_reads_the_matrix_load_installed(tmp_path, monkeypatch, _reset_role_permissions):
    # load() rebinds the module global; holds() must read it at call time.
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"dba": ["action:fs:write"]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))
    identity = Identity(user_id="d", role="dba")
    assert holds(identity, PERMISSION_ACTION_FS_WRITE) is False

    load()

    assert holds(identity, PERMISSION_ACTION_FS_WRITE) is True


# --- PRD-021 STORY-002: stream permissions (F1, D1, T8) ---


def test_stream_permission_constants_match_prd_021_f1():
    assert PERMISSION_STREAM_REALTIME == "stream:realtime"
    assert PERMISSION_REASONING_VIEW == "reasoning:view"
    assert isinstance(STREAM_PERMISSIONS, frozenset)
    assert STREAM_PERMISSIONS == frozenset({"stream:realtime", "reasoning:view"})
    assert STREAM_PERMISSIONS <= authz._KNOWN_PERMISSIONS
    # Not action permissions: action_config validates rule grants against that set.
    assert STREAM_PERMISSIONS.isdisjoint(ACTION_PERMISSIONS)


@pytest.mark.parametrize("role", ["admin", "auditor", "user"])
def test_no_built_in_role_holds_a_stream_permission(role):
    """PRD-021 D1: no built-in role holds either, admin included."""
    assert ROLE_PERMISSIONS[role].isdisjoint(STREAM_PERMISSIONS)


@pytest.mark.parametrize("permission", sorted(["stream:realtime", "reasoning:view"]))
def test_load_accepts_a_stream_permission_grant(permission, tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"dba": ["query:submit", permission]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

    load()

    assert authz.ROLE_PERMISSIONS == {"dba": {PERMISSION_QUERY_SUBMIT, permission}}
    assert holds(Identity(user_id="d", role="dba"), permission) is True
    assert holds(Identity(user_id="u", role="user"), permission) is False
    assert holds(Identity(user_id="a", role="admin"), permission) is False


def test_load_refuses_a_misspelled_stream_permission(tmp_path, monkeypatch, _reset_role_permissions):
    roles_file = tmp_path / "roles.json"
    roles_file.write_text(json.dumps({"dba": ["stream:realtim"]}))
    monkeypatch.setattr(settings, "RBAC_ROLES_FILE", str(roles_file))

    with pytest.raises(AuthzConfigError) as exc_info:
        load()

    assert "stream:realtim" in str(exc_info.value)


@pytest.mark.parametrize("rbac_enabled", [False, True])
@pytest.mark.parametrize("role", ["admin", "auditor", "user"])
@pytest.mark.parametrize("permission", sorted(["stream:realtime", "reasoning:view"]))
def test_holds_is_false_for_built_in_roles_on_stream_permissions(monkeypatch, rbac_enabled, role, permission):
    """PRD-021 T8: no RBAC-off bypass, as with RBAC on."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", rbac_enabled)

    assert holds(Identity(user_id="u", role=role), permission) is False


def test_authorize_with_rbac_off_would_pass_where_holds_refuses(monkeypatch):
    """Why grants are read with holds() (PRD-021 T8): authorize() has the
    RBAC-off escape hatch, holds() does not."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    identity = Identity(user_id="u", role="user")

    assert authorize(identity, PERMISSION_STREAM_REALTIME) is None
    assert holds(identity, PERMISSION_STREAM_REALTIME) is False
