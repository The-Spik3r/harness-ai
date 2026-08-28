from app.config import settings
from app.services.identity import Identity

# Permission constants (PRD-005 Section 7). No caller uses a string literal
# for a permission name -- always one of these.
PERMISSION_QUERY_SUBMIT = "query:submit"
PERMISSION_QUERY_BYOK = "query:byok"
PERMISSION_AUDIT_READ_ALL = "audit:read:all"
PERMISSION_AUDIT_READ_OWN = "audit:read:own"
PERMISSION_STATS_READ = "stats:read"

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


class PermissionDenied(Exception):
    """Raised by authorize() on any denial. Carries the permission name so
    callers can report and audit it without re-deriving it."""

    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"Permission denied: {permission}")


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
