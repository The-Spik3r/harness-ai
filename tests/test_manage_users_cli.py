import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.config import settings
from app.db.database import find_user_by_token_hash, get_user
from app.services.identity import hash_token
from scripts.manage_users import main


# --- create-user (AC1, AC2, AC3) ---


def test_create_user_prints_token_exactly_once_with_recovery_warning(temp_db, capsys):
    exit_code = main(["create-user", "--user-id", "ana", "--role", "user"])

    out = capsys.readouterr().out
    assert exit_code == 0
    user = get_user("ana")
    assert user is not None
    assert user.role == "user"
    # exactly one line carries the warning + token
    warning_lines = [line for line in out.splitlines() if "cannot be recovered" in line]
    assert len(warning_lines) == 1
    token = warning_lines[0].rsplit(": ", 1)[1]
    assert find_user_by_token_hash(hash_token(token)) is not None


def test_create_user_role_omitted_uses_rbac_default_role(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_DEFAULT_ROLE", "auditor")

    exit_code = main(["create-user", "--user-id", "bob"])

    assert exit_code == 0
    assert get_user("bob").role == "auditor"


def test_create_user_invalid_role_exits_nonzero_and_lists_valid_roles(temp_db, capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["create-user", "--user-id", "eve", "--role", "superuser"])

    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "admin" in err and "auditor" in err and "user" in err
    assert get_user("eve") is None


def test_create_user_duplicate_user_id_exits_nonzero(temp_db, capsys):
    """Also a PRD-007 STORY-002 characterization test, pinning the
    `except sqlite3.IntegrityError` arm at scripts/manage_users.py:37 by its
    observable CLI surface -- exit code, stream, and message -- so STORY-004's
    driver swap is measured against it rather than against memory.
    """
    main(["create-user", "--user-id", "ana", "--role", "user"])
    capsys.readouterr()  # drop the first create's token line

    exit_code = main(["create-user", "--user-id", "ana", "--role", "admin"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "already exists" in captured.err
    assert "ana" in captured.err  # the message names the offending user_id
    assert captured.out == ""  # the error goes to stderr, not stdout
    # A failed create must not leak a credential.
    assert "cannot be recovered" not in captured.out
    assert get_user("ana").role == "user"  # first row untouched


def test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id(
    temp_db, capsys, monkeypatch
):
    """PRD-007 STORY-002 characterization test -- pins a real gap, not a
    desirable behavior.

    scripts/manage_users.py:37 catches sqlite3.IntegrityError and prints one
    message for both constraint violations, so a duplicate token_hash on a
    *new* user_id reports "a user with user_id 'bob' already exists" -- the
    wrong cause, and false, since bob does not exist. app/db/database.py's
    insert_user() docstring says it deliberately leaves the exception uncaught
    because the caller "needs to tell those two cases apart"; the caller then
    does not.

    The story's AC4 asks that the two cases be distinguishable. They are not.
    This test pins what the CLI actually does so STORY-004's driver swap
    cannot change it by accident. Making them distinguishable is a behavior
    change and belongs in its own story.

    _create_user() issues a random token, so a hash collision cannot occur
    naturally -- hash_token is patched on the scripts.manage_users module (the
    name it bound at import, scripts/manage_users.py:21) to force one.
    """
    import scripts.manage_users as manage_users

    main(["create-user", "--user-id", "ana", "--role", "user"])
    capsys.readouterr()
    ana = get_user("ana")

    monkeypatch.setattr(manage_users, "hash_token", lambda token: ana.token_hash)
    exit_code = main(["create-user", "--user-id", "bob", "--role", "user"])

    captured = capsys.readouterr()
    assert exit_code == 1
    # Reported as a duplicate *user_id*, naming a user that was never created.
    assert captured.err == "Error: a user with user_id 'bob' already exists.\n"
    assert captured.out == ""
    assert get_user("bob") is None
    # The credential still resolves to its original owner.
    assert find_user_by_token_hash(ana.token_hash).user_id == "ana"


# --- list-users (AC4) ---


def test_list_users_prints_expected_fields_never_token_or_hash(temp_db, capsys):
    main(["create-user", "--user-id", "ana", "--role", "user"])
    capsys.readouterr()  # discard create-user's own output, including its token

    exit_code = main(["list-users"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "ana" in out
    assert "user" in out
    assert "True" in out  # active
    assert "cannot be recovered" not in out
    assert "Token" not in out


def test_list_users_empty_table_prints_nothing(temp_db, capsys):
    exit_code = main(["list-users"])

    assert exit_code == 0
    assert capsys.readouterr().out == ""


# --- deactivate-user (AC5) ---


def test_deactivate_user_blocks_next_resolve(temp_db):
    main(["create-user", "--user-id", "ana", "--role", "user"])
    user_before = get_user("ana")

    exit_code = main(["deactivate-user", "--user-id", "ana"])

    assert exit_code == 0
    assert get_user("ana").active is False
    # the credential this user was just issued no longer resolves --
    # exercised via find_user_by_token_hash, since the plaintext token
    # itself is only ever visible in create-user's captured stdout.
    assert find_user_by_token_hash(user_before.token_hash) is None


def test_deactivate_user_unknown_user_exits_nonzero(temp_db, capsys):
    exit_code = main(["deactivate-user", "--user-id", "ghost"])

    assert exit_code == 1
    assert "no user" in capsys.readouterr().err


# --- issue-token (Design Note 4: PRD Section 4 "issue tokens";
#     app/db/database.py:320-323 names this exact subcommand) ---


def test_issue_token_rotates_credential(temp_db, capsys):
    main(["create-user", "--user-id", "ana", "--role", "user"])
    old_token_hash = get_user("ana").token_hash
    capsys.readouterr()

    exit_code = main(["issue-token", "--user-id", "ana"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert get_user("ana").token_hash != old_token_hash
    assert find_user_by_token_hash(old_token_hash) is None
    warning_lines = [line for line in out.splitlines() if "cannot be recovered" in line]
    assert len(warning_lines) == 1


def test_issue_token_unknown_user_exits_nonzero(temp_db, capsys):
    exit_code = main(["issue-token", "--user-id", "ghost"])

    assert exit_code == 1
    assert "no user" in capsys.readouterr().err
