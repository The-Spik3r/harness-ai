import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings
from app.db.database import (
    deactivate_user,
    get_user,
    init_db,
    insert_user,
    list_users,
    set_user_limits,
    set_user_token_hash,
)
from app.db.errors import IntegrityError
from app.db.models import User
from app.services.identity import hash_token, issue_token

# The three fixed roles PRD-005 Section 4 defines for the MVP. STORY-006's
# app/services/authz.py will own the authoritative role->permission matrix;
# until it exists, this is the only place a role name is validated, so it
# mirrors the PRD rather than a module that isn't there yet (see plan Design
# Note 2).
_VALID_ROLES = ("admin", "auditor", "user")

# The word that clears a per-user override back to NULL, "use the role's limit"
# (PRD-013 STORY-008). Not `unlimited`: that belongs to the role settings
# (Section 6.6), and an override is either a number or the role's value.
_DEFAULT_LIMIT = "default"

# argparse dest -> the `users` column it sets, in the order printed.
_LIMIT_FLAGS = {
    "token_budget_daily": "token budget",
    "requests_per_minute": "requests per minute",
}


def _limit_value(raw: str) -> Optional[int]:
    """argparse `type` for both set-limits flags. A bad value is rejected here,
    before init_db() and before any write, so the command writes nothing."""
    if raw.strip().lower() == _DEFAULT_LIMIT:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a whole number of at least 1 or '{_DEFAULT_LIMIT}', got '{raw}'"
        ) from None
    if value < 1:
        raise argparse.ArgumentTypeError(
            f"must be at least 1 or '{_DEFAULT_LIMIT}', got {value}"
        )
    return value


def _limit_text(value: Optional[int]) -> str:
    return _DEFAULT_LIMIT if value is None else str(value)


def _create_user(args: argparse.Namespace) -> int:
    init_db()
    role = args.role or settings.RBAC_DEFAULT_ROLE
    token = issue_token()
    try:
        insert_user(User(user_id=args.user_id, role=role, token_hash=hash_token(token)))
    # IntegrityError.constraint distinguishes users.user_id from users.token_hash.
    # The CLI deliberately does not branch on it yet -- one message for both cases is
    # pinned by tests/test_manage_users_cli.py:948, and changing it is its own story.
    except IntegrityError:
        print(f"Error: a user with user_id '{args.user_id}' already exists.", file=sys.stderr)
        return 1

    print(f"Created user '{args.user_id}' with role '{role}'.")
    print(f"Token (save this now -- it cannot be recovered): {token}")
    return 0


def _list_users(args: argparse.Namespace) -> int:
    init_db()
    for user in list_users():
        print(
            f"{user.user_id}\t{user.role}\t{user.active}\t{user.created_at}"
            f"\t{_limit_text(user.token_budget_daily)}"
            f"\t{_limit_text(user.requests_per_minute)}"
        )
    return 0


def _set_limits(args: argparse.Namespace) -> int:
    # Both flags default to argparse.SUPPRESS, so an omitted flag is absent from
    # the namespace and its column is left alone -- distinct from `default`,
    # which arrives as None and clears the column to NULL.
    changes = {dest: getattr(args, dest) for dest in _LIMIT_FLAGS if hasattr(args, dest)}
    if not changes:
        args.subparser.error(
            "set-limits needs --token-budget and/or --requests-per-minute"
        )

    init_db()
    if not set_user_limits(args.user_id, **changes):
        print(f"Error: no user with user_id '{args.user_id}'.", file=sys.stderr)
        return 1
    summary = ", ".join(
        f"{label} {_limit_text(changes[dest])}"
        for dest, label in _LIMIT_FLAGS.items()
        if dest in changes
    )
    print(f"Set limits for '{args.user_id}': {summary}.")
    return 0


def _deactivate_user(args: argparse.Namespace) -> int:
    init_db()
    if not deactivate_user(args.user_id):
        print(f"Error: no user with user_id '{args.user_id}'.", file=sys.stderr)
        return 1
    print(f"Deactivated user '{args.user_id}'.")
    return 0


def _issue_token(args: argparse.Namespace) -> int:
    init_db()
    if get_user(args.user_id) is None:
        print(f"Error: no user with user_id '{args.user_id}'.", file=sys.stderr)
        return 1
    token = issue_token()
    set_user_token_hash(args.user_id, hash_token(token))
    print(f"Issued a new token for '{args.user_id}'.")
    print(f"Token (save this now -- it cannot be recovered): {token}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage_users.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-user", help="Create a user and issue its first token")
    create.add_argument("--user-id", required=True)
    create.add_argument("--role", choices=_VALID_ROLES, default=None)
    create.set_defaults(func=_create_user)

    list_cmd = subparsers.add_parser("list-users", help="List all users")
    list_cmd.set_defaults(func=_list_users)

    deactivate = subparsers.add_parser("deactivate-user", help="Deactivate a user")
    deactivate.add_argument("--user-id", required=True)
    deactivate.set_defaults(func=_deactivate_user)

    issue = subparsers.add_parser("issue-token", help="Rotate a user's token")
    issue.add_argument("--user-id", required=True)
    issue.set_defaults(func=_issue_token)

    limits = subparsers.add_parser(
        "set-limits",
        help="Set or clear a user's token budget and request rate overrides",
    )
    limits.add_argument("--user-id", required=True)
    limits.add_argument(
        "--token-budget",
        dest="token_budget_daily",
        type=_limit_value,
        default=argparse.SUPPRESS,
        metavar="N|default",
        help="daily token budget; 'default' uses the role's",
    )
    limits.add_argument(
        "--requests-per-minute",
        dest="requests_per_minute",
        type=_limit_value,
        default=argparse.SUPPRESS,
        metavar="N|default",
        help="requests per minute; 'default' uses the role's",
    )
    limits.set_defaults(func=_set_limits, subparser=limits)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
