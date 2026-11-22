import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import settings
from app.db.database import count_active_users
from app.services.identity import Identity

if TYPE_CHECKING:
    from app.services.provider_registry import Route

# Permission constants (PRD-005 Section 7). No caller uses a string literal
# for a permission name -- always one of these.
PERMISSION_QUERY_SUBMIT = "query:submit"
PERMISSION_QUERY_BYOK = "query:byok"
PERMISSION_AUDIT_READ_ALL = "audit:read:all"
PERMISSION_AUDIT_READ_OWN = "audit:read:own"
PERMISSION_STATS_READ = "stats:read"

# Action permissions (PRD-016 Section 6.7, D6). Each lifts one or more
# grantable action rules from their default to `allow` for a role that
# holds it; the action policy file names these, never a role. Granted
# only through RBAC_ROLES_FILE -- no built-in role holds one.
PERMISSION_ACTION_SQL_WRITE = "action:sql:write"
PERMISSION_ACTION_SQL_DDL = "action:sql:ddl"
PERMISSION_ACTION_SHELL_EXEC = "action:shell:exec"
PERMISSION_ACTION_FS_WRITE = "action:fs:write"
PERMISSION_ACTION_NET_EGRESS = "action:net:egress"
PERMISSION_ACTION_SECRET_READ = "action:secret:read"

# The closed vocabulary a rule's `grant` is validated against at startup
# (PRD-016 Section 9.3, STORY-007).
ACTION_PERMISSIONS = frozenset(
    {
        PERMISSION_ACTION_SQL_WRITE,
        PERMISSION_ACTION_SQL_DDL,
        PERMISSION_ACTION_SHELL_EXEC,
        PERMISSION_ACTION_FS_WRITE,
        PERMISSION_ACTION_NET_EGRESS,
        PERMISSION_ACTION_SECRET_READ,
    }
)

# Streaming permissions (PRD-021 F1, D1). `stream:realtime` lets a role read
# model output while it is produced; `reasoning:view` lets it read the model's
# reasoning. Granted only through RBAC_ROLES_FILE -- no built-in role holds
# one. Always read with holds(), never authorize(): holds() has no RBAC-off
# bypass (PRD-021 T8).
PERMISSION_STREAM_REALTIME = "stream:realtime"
PERMISSION_REASONING_VIEW = "reasoning:view"

STREAM_PERMISSIONS = frozenset(
    {
        PERMISSION_STREAM_REALTIME,
        PERMISSION_REASONING_VIEW,
    }
)

# MCP gateway permissions (PRD-023 Section 4, O1, D6). `mcp:connect` lets a
# role use the `/mcp` gateway; the built-in `admin` and `user` hold it, so the
# gateway works out of the box for the roles that already submit queries.
# `skill:<id>` is a dynamic family, one permission per skill, never listed in
# _KNOWN_PERMISSIONS: load() accepts it by pattern, and whether the skill
# exists is mcp_config.load()'s check (STORY-007). No built-in role holds any
# `skill:*` (D6). Always read with holds(), never authorize(): authorize()
# returns at once with RBAC off and would show every skill to every caller.
PERMISSION_MCP_CONNECT = "mcp:connect"

MCP_PERMISSIONS = frozenset({PERMISSION_MCP_CONNECT})

_SKILL_PERMISSION = re.compile(r"skill:[a-z0-9][a-z0-9-]{0,47}")


def is_skill_permission(permission: object) -> bool:
    """Whether `permission` is a well-formed `skill:<id>` (PRD-023 D6).

    A full match of one pattern (not `^...$`, whose `$` also matches before a
    trailing newline). Says nothing about whether the skill exists:
    mcp_config.load() checks that (STORY-007)."""
    return isinstance(permission, str) and _SKILL_PERMISSION.fullmatch(permission) is not None


_KNOWN_PERMISSIONS = {
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_QUERY_BYOK,
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_STATS_READ,
    # Known, so RBAC_ROLES_FILE can grant them through load()'s existing
    # unknown-permission check (PRD-016 F9).
    *ACTION_PERMISSIONS,
    # Known, so RBAC_ROLES_FILE can grant them (PRD-021 D1).
    *STREAM_PERMISSIONS,
    # Known, so RBAC_ROLES_FILE can grant it (PRD-023 O1).
    *MCP_PERMISSIONS,
}

# Role -> permission matrix (PRD-005 Section 7). A policy table, not
# conditionals -- a role absent here, or a permission absent from a role's
# set, denies by default. Overridable at startup via RBAC_ROLES_FILE
# (STORY-007); this is the built-in fallback. No built-in role holds an
# action permission, `admin` included: an agent acting for an admin is not
# administering the harness (PRD-016 D6). Likewise no built-in role holds
# `stream:realtime` or `reasoning:view`: who may read unfinished model output
# is a deployment decision, granted only through RBAC_ROLES_FILE (PRD-021 D1).
# `admin` and `user` hold `mcp:connect`; `auditor` does not, and no built-in
# role holds any `skill:*` (PRD-023 O1, D6).
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        PERMISSION_QUERY_SUBMIT,
        PERMISSION_QUERY_BYOK,
        PERMISSION_AUDIT_READ_ALL,
        PERMISSION_AUDIT_READ_OWN,
        PERMISSION_STATS_READ,
        PERMISSION_MCP_CONNECT,
    },
    "auditor": {
        PERMISSION_AUDIT_READ_ALL,
        PERMISSION_AUDIT_READ_OWN,
        PERMISSION_STATS_READ,
    },
    "user": {
        PERMISSION_QUERY_SUBMIT,
        PERMISSION_AUDIT_READ_OWN,
        PERMISSION_MCP_CONNECT,
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
    malformed, grants an unrecognized permission, or grants a malformed
    `skill:<id>` permission (PRD-023 D6). Startup fails rather
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

    # `skill:<id>` is a dynamic family (PRD-023 D6): a malformed one names the
    # role and the rule; a well-formed one skips the unknown check below.
    for role in sorted(matrix):
        for permission in sorted(matrix[role], key=str):
            if isinstance(permission, str) and permission.startswith("skill:"):
                if not is_skill_permission(permission):
                    raise AuthzConfigError(
                        f"RBAC_ROLES_FILE '{path_str}' role '{role}' grants invalid "
                        f"permission '{permission}': a skill permission must match "
                        "skill:[a-z0-9][a-z0-9-]{0,47} (PRD-023 D6)"
                    )

    granted = {
        permission
        for permissions in matrix.values()
        for permission in permissions
        if not is_skill_permission(permission)
    }
    unknown = sorted(granted - _KNOWN_PERMISSIONS)
    if unknown:
        raise AuthzConfigError(
            f"RBAC_ROLES_FILE '{path_str}' grants unrecognized permission(s): {', '.join(unknown)}"
        )

    ROLE_PERMISSIONS = matrix


class RbacNotBootstrappedError(Exception):
    """Raised by check_bootstrap() when RBAC_ENABLED=true and no active
    user exists. ADMIN_TOKEN alone does not satisfy this -- identity.resolve()
    synthesizes an admin identity from it without ever reading the users
    table, so break-glass is not a substitute for bootstrap (PRD-005 Risk 2,
    STORY-016)."""


def check_bootstrap() -> None:
    """Fail-fast startup guard (STORY-016). If RBAC_ENABLED and no active
    user is seeded, every request would resolve to a 401 with no
    explanation -- or, if only ADMIN_TOKEN is configured, the service would
    appear to work for exactly one break-glass credential and nobody else.
    Called once at startup (app/main.py's lifespan, chat_ui.py's
    register_lifespan_task) after init_db() has run."""
    if not settings.RBAC_ENABLED:
        return
    if count_active_users() > 0:
        return
    raise RbacNotBootstrappedError(
        "RBAC_ENABLED=true but no active users exist. Bootstrap one with: "
        "python scripts/manage_users.py create-user --user-id <id> "
        "--role <admin|auditor|user>"
    )


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


def holds(identity: Identity, permission: str) -> bool:
    """Whether the identity's role holds `permission` in the loaded matrix,
    with **no** RBAC_ENABLED bypass (PRD-016 D7, Section 6.7, T4).

    Not a wrapper over authorize(): authorize() returns at once when
    RBAC_ENABLED=false (PRD-005's escape hatch for running without users).
    Reused for action grants, that hatch would hand all six action
    permissions to every caller and turn every grantable action rule into
    `allow`. This reads ROLE_PERMISSIONS and nothing else -- not settings.
    With RBAC off identities still carry a role, and that role holds what
    the matrix says, which in the built-in matrix is no action permission.

    Deny by default, as authorize(): a role absent from the matrix holds
    nothing. Returns a bool rather than raising because the caller
    (action_policy.evaluate(), STORY-014) chooses between a rule's grant and
    its default; a missing grant is not an error. authorize() is unchanged.
    Also the reader for `skill:<id>` visibility (PRD-023 D6).
    """
    return permission in ROLE_PERMISSIONS.get(identity.role, ())


def sees_every_model(identity: Identity) -> bool:
    """True when the identity is not model-restricted: RBAC off, or a role in
    MODEL_ALLOWLIST_WILDCARD_ROLES (PRD-020 O1). One rule for authorize_route
    and visible_models, so the picker cannot drift from the check."""
    return (not settings.RBAC_ENABLED) or identity.role in MODEL_ALLOWLIST_WILDCARD_ROLES


def role_may_use(role: str, model, provider) -> bool:
    """Effective roles of a catalogued model (PRD-020 F2): the model's `roles`,
    else its provider's, else every role. `model` is a CatalogModel and
    `provider` a Provider (not annotated: provider_registry imports this
    module). Pure."""
    roles = model.roles if model.roles is not None else provider.roles
    return roles is None or role in roles


def authorize_route(identity: Identity, model: str) -> "Route":
    """Resolve `model` and check the role may use it (PRD-020 F2, D3, D4, T3).

    Raises PermissionDenied(f"query:model:{model}") -- the one text for every
    denial, so an unknown model and a forbidden one are indistinguishable (T3).
    An unresolvable model is denied even with RBAC off. A wildcard role reaches
    any resolvable model (O1); an uncatalogued model is for wildcard roles only
    (OD3); a catalogued one needs a role in its effective roles.
    """
    # provider_registry imports authz at module level, so import it here.
    from app.services import provider_registry

    route = provider_registry.resolve(model)
    if route is None:
        raise PermissionDenied(f"query:model:{model}")
    if sees_every_model(identity):
        return route
    if not route.catalogued or not role_may_use(identity.role, route.model, route.provider):
        raise PermissionDenied(f"query:model:{model}")
    return route


def authorize_model(identity: Identity, model: str) -> None:
    """Deny-by-default model check (PRD-005 Section 7). Raises
    PermissionDenied(f"query:model:{model}") unless the identity's role has
    an unrestricted allowlist or the model is catalogued for its role. Now
    delegates to authorize_route and discards the Route (PRD-020 D3, D4); in
    legacy mode (no PROVIDERS_FILE) the verdicts are the old allowlist check's.
    RBAC_ENABLED=false bypasses the role check too, same escape hatch as
    authorize()."""
    authorize_route(identity, model)
