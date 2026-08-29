import json
from pathlib import Path

from app.config import settings
from app.services.identity import Identity

# Permission constants (PRD-005 Section 7). No caller uses a string literal
# for a permission name -- always one of these.
PERMISSION_QUERY_SUBMIT = "query:submit"
PERMISSION_QUERY_BYOK = "query:byok"
PERMISSION_AUDIT_READ_ALL = "audit:read:all"
PERMISSION_AUDIT_READ_OWN = "audit:read:own"
PERMISSION_STATS_READ = "stats:read"

_KNOWN_PERMISSIONS = {
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_QUERY_BYOK,
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_STATS_READ,
}

# Role -> permission matrix (PRD-005 Section 7). A policy table, not
# conditionals -- a role absent here, or a permission absent from a role's
# set, denies by default. Overridable at startup via RBAC_ROLES_FILE
# (STORY-007); this is the built-in fallback.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        PERMISSION_QUERY_SUBMIT,
        PERMISSION_QUERY_BYOK,
        PERMISSION_AUDIT_READ_ALL,
        PERMISSION_AUDIT_READ_OWN,
        PERMISSION_STATS_READ,
    },
    "auditor": {
        PERMISSION_AUDIT_READ_ALL,
        PERMISSION_AUDIT_READ_OWN,
        PERMISSION_STATS_READ,
    },
    "user": {
        PERMISSION_QUERY_SUBMIT,
        PERMISSION_AUDIT_READ_OWN,
    },
}

# Roles whose model allowlist is "*" (PRD-005 Section 7). Every other role
# is checked against settings.model_allowlist_list.
MODEL_ALLOWLIST_WILDCARD_ROLES = {"admin"}


class PermissionDenied(Exception):
    """Raised by authorize() on any denial. Carries the permission name so
    callers can report and audit it without re-deriving it."""

    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"Permission denied: {permission}")


class AuthzConfigError(Exception):
    """Raised by load() when RBAC_ROLES_FILE is set but unreadable,
    malformed, or grants an unrecognized permission. Startup fails rather
    than silently falling back to the built-in matrix (STORY-007)."""


def load() -> None:
    """Loads the role matrix from RBAC_ROLES_FILE if set, replacing
    ROLE_PERMISSIONS wholesale -- no merge, so an omitted permission denies
    (STORY-007). Empty RBAC_ROLES_FILE is a no-op: the built-in matrix stands
    and no file is read. Called once at startup (app/main.py's lifespan,
    chat_ui.py's register_lifespan_task); never call this per request."""
    global ROLE_PERMISSIONS

    path_str = settings.RBAC_ROLES_FILE
    if not path_str:
        return

    try:
        raw = Path(path_str).read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthzConfigError(f"Failed to read RBAC_ROLES_FILE '{path_str}': {exc}") from exc

    try:
        parsed = json.loads(raw)
        matrix = {role: set(permissions) for role, permissions in parsed.items()}
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise AuthzConfigError(f"Failed to parse RBAC_ROLES_FILE '{path_str}': {exc}") from exc

    granted = {permission for permissions in matrix.values() for permission in permissions}
    unknown = sorted(granted - _KNOWN_PERMISSIONS)
    if unknown:
        raise AuthzConfigError(
            f"RBAC_ROLES_FILE '{path_str}' grants unrecognized permission(s): {', '.join(unknown)}"
        )

    ROLE_PERMISSIONS = matrix


def authorize(identity: Identity, permission: str) -> None:
    """Deny-by-default authorization check. Raises PermissionDenied unless
    the identity's role is in the matrix and grants this permission. The
    RBAC_ENABLED=false bypass is the one explicit exception (PRD-005
    Section 9's documented escape hatch)."""
    if not settings.RBAC_ENABLED:
        return

    role_permissions = ROLE_PERMISSIONS.get(identity.role)
    if role_permissions is None or permission not in role_permissions:
        raise PermissionDenied(permission)


def authorize_model(identity: Identity, model: str) -> None:
    """Deny-by-default model check (PRD-005 Section 7). Raises
    PermissionDenied(f"query:model:{model}") unless the identity's role has
    an unrestricted allowlist or the model is in settings.model_allowlist_list.
    RBAC_ENABLED=false bypasses this check too, same escape hatch as
    authorize()."""
    if not settings.RBAC_ENABLED:
        return

    if identity.role in MODEL_ALLOWLIST_WILDCARD_ROLES:
        return

    if model in settings.model_allowlist_list:
        return

    raise PermissionDenied(f"query:model:{model}")
