"""The exception surface `app/db/` raises. No consumer imports a driver.

PRD-007 Section 7.2. Before this module existed, `app/services/duplicate_checker.py`
and `scripts/manage_users.py` imported `sqlite3` for the sole purpose of naming a
class in an `except` clause -- so a driver swap would have left those clauses
silently not matching, and an `except` that stops firing does not raise, it lets
the exception through.

Translation from the driver's exceptions to these lives at the `app/db/database.py`
boundary (`_translated()`), never here: this module deliberately imports no driver,
so STORY-006 replaces the client underneath it without touching a line of it.
"""

from typing import Optional


class StorageError(Exception):
    """A storage operation failed.

    Caught by `app/services/duplicate_checker.py`, which degrades the duplicate
    lookup into a `DuplicateCheckError` rather than letting a driver exception
    escape into the query pipeline.

    It is the base of the other two on purpose. It stands in for `sqlite3.Error`,
    the root of the driver hierarchy, which subsumes both the missing-relation and
    the constraint-violation cases -- so a caller catching the general failure
    keeps catching the specific ones, exactly as `except sqlite3.Error` did.
    """


class MissingRelationError(StorageError):
    """A table the statement named does not exist.

    Caught by `app/db/database.py`'s `find_user_by_token_hash()`, and there alone:
    a `users` table that `init_db()` never created folds into the same "no match"
    outcome as an unknown credential, because a caller resolving a credential needs
    a closed door -- 401, not 500 (PRD-005 Section 9).

    Deliberately narrow. A locked, unreadable, or otherwise broken database is a
    `StorageError` and must stay one; widening this type would turn a real storage
    outage into a silent 401.
    """

    def __init__(self, relation: str, message: str) -> None:
        self.relation = relation
        super().__init__(message)


class IntegrityError(StorageError):
    """A constraint was violated -- in this schema, a duplicate `user_id` or a
    duplicate `token_hash` on `insert_user()`.

    Caught by `scripts/manage_users.py`, which reports the failed create as a
    usable CLI error instead of a traceback.

    `constraint` names what failed (`"users.user_id"`, `"users.token_hash"`, or
    `None` when the driver's message cannot be parsed), so a caller *can* tell the
    two duplicates apart -- the capability `insert_user()`'s docstring has always
    claimed its caller needs. The CLI does not branch on it yet: it prints one
    message for both cases, and
    `tests/test_manage_users_cli.py::test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id`
    pins that gap deliberately. Closing it is a behavior change and belongs in its
    own story.

    The name matches the driver's *concept*, not its class. Nothing here inherits
    from `sqlite3`.
    """

    def __init__(self, constraint: Optional[str], message: str) -> None:
        self.constraint = constraint
        super().__init__(message)
