import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
from app.services.authz import (
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_QUERY_BYOK,
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_STATS_READ,
    PermissionDenied,
    ROLE_PERMISSIONS,
    authorize,
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
