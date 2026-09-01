import argparse
import sqlite3
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
    set_user_token_hash,
)
from app.db.models import User
from app.services.identity import hash_token, issue_token

# The three fixed roles PRD-005 Section 4 defines for the MVP. STORY-006's
# app/services/authz.py will own the authoritative role->permission matrix;
# until it exists, this is the only place a role name is validated, so it
# mirrors the PRD rather than a module that isn't there yet (see plan Design
# Note 2).
_VALID_ROLES = ("admin", "auditor", "user")


def _create_user(args: argparse.Namespace) -> int:
    init_db()
    role = args.role or settings.RBAC_DEFAULT_ROLE
    token = issue_token()
    try:
        insert_user(User(user_id=args.user_id, role=role, token_hash=hash_token(token)))
    except sqlite3.IntegrityError:
        print(f"Error: a user with user_id '{args.user_id}' already exists.", file=sys.stderr)
        return 1

    print(f"Created user '{args.user_id}' with role '{role}'.")
    print(f"Token (save this now -- it cannot be recovered): {token}")
    return 0


def _list_users(args: argparse.Namespace) -> int:
    init_db()
    for user in list_users():
        print(f"{user.user_id}\t{user.role}\t{user.active}\t{user.created_at}")
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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
